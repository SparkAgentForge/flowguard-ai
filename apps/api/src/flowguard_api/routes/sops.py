import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from flowguard_api.config import get_settings
from flowguard_api.database import get_session
from flowguard_api.models import Document, Sop, SopRevisionEvent, SopStatus, SopStep, SopVersion
from flowguard_api.schemas import (
    DocumentRead,
    SopActionRequest,
    SopExtractRequest,
    SopUpdateRequest,
    SopVersionDetail,
)
from flowguard_api.services.sop_extractor import SopExtractor, get_sop_extractor
from flowguard_api.services.sop_workflow import InvalidSopTransition, transition_sop
from flowguard_api.storage import FileStorage, get_file_storage, sanitize_filename

router = APIRouter(tags=["SOP"])
SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
ExtractorDependency = Annotated[SopExtractor, Depends(get_sop_extractor)]
ALLOWED_SUFFIXES = {".pdf", ".docx"}


def get_sop_detail(session: Session, version_id: str) -> SopVersionDetail:
    version = session.scalar(
        select(SopVersion)
        .options(selectinload(SopVersion.steps), selectinload(SopVersion.sop))
        .where(SopVersion.id == version_id)
    )
    if version is None:
        raise HTTPException(status_code=404, detail="SOP 版本不存在")
    events = session.scalars(
        select(SopRevisionEvent)
        .where(SopRevisionEvent.sop_version_id == version_id)
        .order_by(SopRevisionEvent.created_at)
    ).all()
    return SopVersionDetail.model_validate(
        {
            **version.__dict__,
            "code": version.sop.code,
            "name": version.sop.name,
            "product_code": version.sop.product_code,
            "steps": sorted(version.steps, key=lambda item: item.sequence),
            "events": events,
        }
    )


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session: SessionDependency,
    storage: StorageDependency,
    file: Annotated[UploadFile, File()],
) -> Document:
    filename = file.filename or "document"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 PDF 和 DOCX 文档")
    content = await file.read(get_settings().max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="文档内容为空")
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="文档超过 20 MiB 限制")
    digest = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(Document).where(Document.sha256 == digest))
    if existing is not None:
        return existing
    storage_key = f"documents/{uuid.uuid4()}/{sanitize_filename(filename)}"
    storage.put(storage_key, content)
    document = Document(
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        sha256=digest,
        storage_key=storage_key,
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


@router.post("/documents/{document_id}/extract", response_model=SopVersionDetail)
def extract_sop(
    document_id: str,
    payload: SopExtractRequest,
    session: SessionDependency,
    storage: StorageDependency,
    extractor: ExtractorDependency,
) -> SopVersionDetail:
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    extracted = extractor.extract(document.filename, storage.get(document.storage_key))
    sop = session.scalar(select(Sop).where(Sop.code == extracted.code))
    if sop is None:
        sop = Sop(code=extracted.code, name=extracted.name, product_code=extracted.product_code)
        session.add(sop)
        session.flush()
    version = SopVersion(
        sop_id=sop.id,
        source_document_id=document.id,
        version=extracted.version,
        status=SopStatus.DRAFT,
    )
    session.add(version)
    session.flush()
    for step in extracted.steps:
        session.add(
            SopStep(
                sop_version_id=version.id,
                code=step.code,
                sequence=step.sequence,
                name=step.name,
                required=step.required,
                preconditions=step.preconditions,
                evidence_requirements=step.evidence_requirements,
                on_missing=step.on_missing,
                source_refs=[
                    {
                        "file_id": document.id,
                        "page": source.page,
                        "paragraph": source.paragraph,
                        "quote": source.quote,
                    }
                    for source in step.source_refs
                ],
            )
        )
    transition_sop(session, version, SopStatus.AI_EXTRACTED, payload.actor_id)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="该 SOP 版本已存在") from error
    return get_sop_detail(session, version.id)


@router.get("/sop-versions/{version_id}", response_model=SopVersionDetail)
def read_sop_version(version_id: str, session: SessionDependency) -> SopVersionDetail:
    return get_sop_detail(session, version_id)


@router.put("/sop-versions/{version_id}", response_model=SopVersionDetail)
def update_sop_version(
    version_id: str,
    payload: SopUpdateRequest,
    session: SessionDependency,
) -> SopVersionDetail:
    version = session.scalar(
        select(SopVersion)
        .options(selectinload(SopVersion.steps), selectinload(SopVersion.sop))
        .where(SopVersion.id == version_id)
    )
    if version is None:
        raise HTTPException(status_code=404, detail="SOP 版本不存在")
    if version.status not in {SopStatus.AI_EXTRACTED, SopStatus.IN_REVIEW}:
        raise HTTPException(status_code=409, detail="当前状态不允许修改 SOP")
    version.sop.name = payload.name
    version.sop.product_code = payload.product_code
    version.steps.clear()
    for step in payload.steps:
        version.steps.append(SopStep(**step.model_dump()))
    session.add(
        SopRevisionEvent(
            sop_version_id=version.id,
            event_type="SOP_CONTENT_UPDATED",
            actor_id=payload.actor_id,
            old_status=version.status,
            new_status=version.status,
            details={"step_count": len(payload.steps)},
        )
    )
    session.commit()
    return get_sop_detail(session, version.id)


def apply_sop_action(
    version_id: str,
    target_status: SopStatus,
    payload: SopActionRequest,
    session: Session,
) -> SopVersionDetail:
    version = session.get(SopVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="SOP 版本不存在")
    try:
        transition_sop(session, version, target_status, payload.actor_id)
        session.commit()
    except InvalidSopTransition as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    return get_sop_detail(session, version.id)


@router.post("/sop-versions/{version_id}/submit-review", response_model=SopVersionDetail)
def submit_review(
    version_id: str, payload: SopActionRequest, session: SessionDependency
) -> SopVersionDetail:
    return apply_sop_action(version_id, SopStatus.IN_REVIEW, payload, session)


@router.post("/sop-versions/{version_id}/approve", response_model=SopVersionDetail)
def approve_sop(
    version_id: str, payload: SopActionRequest, session: SessionDependency
) -> SopVersionDetail:
    return apply_sop_action(version_id, SopStatus.APPROVED, payload, session)


@router.post("/sop-versions/{version_id}/publish", response_model=SopVersionDetail)
def publish_sop(
    version_id: str, payload: SopActionRequest, session: SessionDependency
) -> SopVersionDetail:
    return apply_sop_action(version_id, SopStatus.PUBLISHED, payload, session)
