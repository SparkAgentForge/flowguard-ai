import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flowguard_api.config import get_settings
from flowguard_api.core.inference import VideoInferenceError
from flowguard_api.core.storage import FileStorage, sanitize_filename
from flowguard_api.infrastructure.database import get_session
from flowguard_api.infrastructure.storage.factory import get_file_storage
from flowguard_api.models import (
    AuditDecision,
    ExceptionCase,
    ExceptionStatus,
    VideoAsset,
    VideoAudit,
    VideoAuditStatus,
    WorkOrder,
    WorkOrderStatus,
    utc_now,
)
from flowguard_api.schemas import (
    ReviewRequestRead,
    ReviewRequestResolve,
    VideoAuditRead,
    VideoAuditRequest,
    VideoRead,
)
from flowguard_api.services.video_audit import InvalidVideoAudit, execute_video_audit
from flowguard_api.services.video_preview import VideoPreviewError, ensure_browser_preview
from flowguard_api.services.work_order_state import transition_work_order

router = APIRouter(prefix="/work-orders", tags=["video audits"])
SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
ALLOWED_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _get_work_order(session: Session, work_order_id: str) -> WorkOrder:
    work_order = session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="工作单不存在")
    return work_order


def _get_audit_detail(session: Session, audit_id: str) -> VideoAuditRead:
    audit = session.scalar(
        select(VideoAudit)
        .options(selectinload(VideoAudit.findings))
        .where(VideoAudit.id == audit_id)
    )
    if audit is None:
        raise HTTPException(status_code=404, detail="视频审计不存在")
    return VideoAuditRead.model_validate(
        {**audit.__dict__, "findings": sorted(audit.findings, key=lambda item: item.sequence)}
    )


@router.get("/{work_order_id}/audits", response_model=list[VideoAuditRead])
def list_video_audits(work_order_id: str, session: SessionDependency) -> list[VideoAuditRead]:
    _get_work_order(session, work_order_id)
    audit_ids = session.scalars(
        select(VideoAudit.id)
        .where(
            VideoAudit.work_order_id == work_order_id,
        )
        .order_by(VideoAudit.created_at.desc())
    ).all()
    return [_get_audit_detail(session, audit_id) for audit_id in audit_ids]


@router.get("/{work_order_id}/videos", response_model=list[VideoRead])
def list_videos(work_order_id: str, session: SessionDependency) -> list[VideoAsset]:
    _get_work_order(session, work_order_id)
    return session.scalars(
        select(VideoAsset)
        .where(VideoAsset.work_order_id == work_order_id)
        .order_by(VideoAsset.created_at.desc())
    ).all()


@router.get("/{work_order_id}/videos/{video_id}/content")
def video_content(
    work_order_id: str,
    video_id: str,
    session: SessionDependency,
    storage: StorageDependency,
) -> Response:
    _get_work_order(session, work_order_id)
    video = session.scalar(
        select(VideoAsset).where(
            VideoAsset.id == video_id, VideoAsset.work_order_id == work_order_id
        )
    )
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在或不属于该工作单")
    try:
        preview_key = ensure_browser_preview(storage, video)
    except VideoPreviewError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        return RedirectResponse(storage.get_url(preview_key, expires_seconds=3600))
    except RuntimeError:
        return Response(content=storage.get(preview_key), media_type="video/mp4")


@router.post(
    "/{work_order_id}/videos",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video(
    work_order_id: str,
    session: SessionDependency,
    storage: StorageDependency,
    file: Annotated[UploadFile, File()],
) -> VideoAsset:
    _get_work_order(session, work_order_id)
    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 MP4、MOV、AVI、MKV 和 WebM 视频")
    settings = get_settings()
    content = await file.read(settings.max_video_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="视频内容为空")
    if len(content) > settings.max_video_bytes:
        raise HTTPException(status_code=413, detail="视频超过大小限制")
    digest = hashlib.sha256(content).hexdigest()
    existing = session.scalar(
        select(VideoAsset).where(
            VideoAsset.work_order_id == work_order_id,
            VideoAsset.sha256 == digest,
        )
    )
    if existing is not None:
        return existing
    storage_key = f"videos/{work_order_id}/{uuid.uuid4()}/{sanitize_filename(filename)}"
    storage.put(storage_key, content)
    video = VideoAsset(
        work_order_id=work_order_id,
        filename=filename,
        content_type=file.content_type or "video/mp4",
        sha256=digest,
        storage_key=storage_key,
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


@router.post(
    "/{work_order_id}/inspect",
    response_model=VideoAuditRead,
    status_code=status.HTTP_201_CREATED,
)
def inspect_video(
    work_order_id: str,
    payload: VideoAuditRequest,
    session: SessionDependency,
    storage: StorageDependency,
) -> VideoAuditRead:
    work_order = _get_work_order(session, work_order_id)
    video = session.scalar(
        select(VideoAsset).where(
            VideoAsset.id == payload.video_id,
            VideoAsset.work_order_id == work_order_id,
        )
    )
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在或不属于该工作单")
    existing = session.scalar(
        select(VideoAudit)
        .where(VideoAudit.video_id == video.id)
        .order_by(VideoAudit.created_at.desc())
    )
    if existing is not None and existing.status == VideoAuditStatus.COMPLETED:
        return _get_audit_detail(session, existing.id)
    if work_order.status == WorkOrderStatus.CREATED:
        transition_work_order(
            session, work_order, WorkOrderStatus.INSPECTING, payload.actor_id, "开始视频检测"
        )
    elif work_order.status != WorkOrderStatus.INSPECTING:
        raise HTTPException(status_code=409, detail="当前工作单状态不允许重新检测")

    try:
        audit = execute_video_audit(session, work_order, video, storage)
    except (InvalidVideoAudit, VideoInferenceError) as error:
        audit = VideoAudit(
            work_order_id=work_order_id,
            video_id=video.id,
            status=VideoAuditStatus.FAILED,
            decision=AuditDecision.VIOLATION,
            provider=get_settings().inference_provider,
            model_name="unknown",
            overall_pass=False,
            summary=str(error),
            raw_response={"error": str(error)},
        )
        session.add(audit)
        # Do not leave the work order in INSPECTING after a provider or media
        # failure. The uploaded video remains available for a retry.
        if work_order.status == WorkOrderStatus.INSPECTING:
            transition_work_order(
                session,
                work_order,
                WorkOrderStatus.CREATED,
                payload.actor_id,
                f"视频检测失败，可重试：{error}",
            )
        session.commit()
        raise HTTPException(status_code=422, detail=str(error)) from error

    if audit.decision == AuditDecision.PASS:
        transition_work_order(
            session, work_order, WorkOrderStatus.VERIFIED, payload.actor_id, audit.summary
        )
    else:
        transition_work_order(
            session,
            work_order,
            WorkOrderStatus.EXCEPTION_PENDING,
            payload.actor_id,
            audit.summary,
        )
        exception_status = ExceptionStatus.PENDING
        if audit.decision == AuditDecision.INSUFFICIENT_EVIDENCE:
            transition_work_order(
                session,
                work_order,
                WorkOrderStatus.MANUAL_REVIEW,
                payload.actor_id,
                "关键步骤证据不足",
            )
            exception_status = ExceptionStatus.MANUAL_REVIEW
        missing = [
            finding
            for finding in audit.findings
            if finding.evidence_status in {"MISSING", "MISORDERED", "UNCERTAIN"}
        ]
        session.add(
            ExceptionCase(
                work_order_id=work_order.id,
                audit_id=audit.id,
                status=exception_status,
                rule_code=(
                    "INSUFFICIENT_VISUAL_EVIDENCE"
                    if audit.decision == AuditDecision.INSUFFICIENT_EVIDENCE
                    else "REQUIRED_STEP_MISSING"
                ),
                facts=[finding.evidence for finding in missing],
            )
        )
    session.commit()
    return _get_audit_detail(session, audit.id)


@router.get("/{work_order_id}/audits/{audit_id}", response_model=VideoAuditRead)
def read_video_audit(
    work_order_id: str, audit_id: str, session: SessionDependency
) -> VideoAuditRead:
    audit = session.scalar(
        select(VideoAudit).where(
            VideoAudit.id == audit_id, VideoAudit.work_order_id == work_order_id
        )
    )
    if audit is None:
        raise HTTPException(status_code=404, detail="视频审计不存在")
    return _get_audit_detail(session, audit.id)


@router.get(
    "/{work_order_id}/audits/{audit_id}/review-requests",
    response_model=list[ReviewRequestRead],
)
def list_review_requests(
    work_order_id: str, audit_id: str, session: SessionDependency
) -> list[dict]:
    audit = session.scalar(
        select(VideoAudit).where(
            VideoAudit.id == audit_id, VideoAudit.work_order_id == work_order_id
        )
    )
    if audit is None:
        raise HTTPException(status_code=404, detail="视频审计不存在")
    return audit.review_requests or []


@router.post(
    "/{work_order_id}/audits/{audit_id}/review-requests/{request_id}/resolve",
    response_model=list[ReviewRequestRead],
)
def resolve_review_request(
    work_order_id: str,
    audit_id: str,
    request_id: str,
    payload: ReviewRequestResolve,
    session: SessionDependency,
) -> list[dict]:
    audit = session.scalar(
        select(VideoAudit).where(
            VideoAudit.id == audit_id, VideoAudit.work_order_id == work_order_id
        )
    )
    if audit is None:
        raise HTTPException(status_code=404, detail="视频审计不存在")
    requests = list(audit.review_requests or [])
    target = next((item for item in requests if item.get("id") == request_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="复核请求不存在")
    if target.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="复核请求已经处理")
    target.update(
        {
            "status": payload.decision,
            "resolved_by": payload.actor_id,
            "resolved_at": utc_now().isoformat(),
            "note": payload.note,
        }
    )
    audit.review_requests = requests
    session.commit()
    return requests
