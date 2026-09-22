import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flowguard_api.config import get_settings
from flowguard_api.database import get_session
from flowguard_api.models import (
    AuditDecision,
    ExceptionCase,
    ExceptionStatus,
    Notification,
    ReworkTask,
    ReworkTaskStatus,
    VideoAsset,
    VideoAudit,
    WorkOrder,
    WorkOrderStatus,
    utc_now,
)
from flowguard_api.schemas import (
    ExceptionActionRequest,
    ExceptionRead,
    NotificationRead,
    ReworkReviewRequest,
    ReworkReviewResult,
    ReworkTaskCreate,
    VideoRead,
)
from flowguard_api.services.video_audit import InvalidVideoAudit, execute_video_audit
from flowguard_api.services.video_inference import VideoInferenceError
from flowguard_api.services.work_order_state import transition_work_order
from flowguard_api.storage import FileStorage, get_file_storage, sanitize_filename

router = APIRouter(tags=["exception workflow"])
SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[FileStorage, Depends(get_file_storage)]
ALLOWED_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _get_exception(session: Session, exception_id: str) -> ExceptionCase:
    exception = session.get(ExceptionCase, exception_id)
    if exception is None:
        raise HTTPException(status_code=404, detail="异常记录不存在")
    return exception


def _get_task(session: Session, task_id: str) -> ReworkTask:
    task = session.get(ReworkTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="返工任务不存在")
    return task


def _exception_detail(session: Session, exception_id: str) -> ExceptionRead:
    exception = _get_exception(session, exception_id)
    work_order = session.get(WorkOrder, exception.work_order_id)
    audit = session.scalar(
        select(VideoAudit)
        .options(selectinload(VideoAudit.findings))
        .where(VideoAudit.id == exception.audit_id)
    )
    task = session.scalar(select(ReworkTask).where(ReworkTask.exception_id == exception.id))
    if work_order is None or audit is None:
        raise HTTPException(status_code=409, detail="异常记录关联数据不完整")
    return ExceptionRead.model_validate(
        {
            **exception.__dict__,
            "work_order_code": work_order.code,
            "decision": audit.decision,
            "audit": {
                **audit.__dict__,
                "findings": sorted(audit.findings, key=lambda item: item.sequence),
            },
            "rework_task": task,
        }
    )


@router.get("/exceptions", response_model=list[ExceptionRead])
def list_exceptions(session: SessionDependency) -> list[ExceptionRead]:
    exception_ids = session.scalars(
        select(ExceptionCase.id).order_by(ExceptionCase.created_at.desc())
    ).all()
    return [_exception_detail(session, exception_id) for exception_id in exception_ids]


@router.get("/exceptions/{exception_id}", response_model=ExceptionRead)
def read_exception(exception_id: str, session: SessionDependency) -> ExceptionRead:
    return _exception_detail(session, exception_id)


@router.post("/exceptions/{exception_id}/confirm", response_model=ExceptionRead)
def confirm_exception(
    exception_id: str,
    payload: ExceptionActionRequest,
    session: SessionDependency,
) -> ExceptionRead:
    exception = _get_exception(session, exception_id)
    work_order = session.get(WorkOrder, exception.work_order_id)
    if work_order is None or exception.status not in {
        ExceptionStatus.PENDING,
        ExceptionStatus.MANUAL_REVIEW,
    }:
        raise HTTPException(status_code=409, detail="当前异常状态不允许确认")
    transition_work_order(
        session,
        work_order,
        WorkOrderStatus.EXCEPTION_CONFIRMED,
        payload.actor_id,
        payload.reason,
    )
    exception.status = ExceptionStatus.CONFIRMED
    exception.human_reason = payload.reason
    exception.reviewed_by = payload.actor_id
    exception.reviewed_at = utc_now()
    session.commit()
    return _exception_detail(session, exception.id)


@router.post("/exceptions/{exception_id}/reject", response_model=ExceptionRead)
def reject_exception(
    exception_id: str,
    payload: ExceptionActionRequest,
    session: SessionDependency,
) -> ExceptionRead:
    exception = _get_exception(session, exception_id)
    work_order = session.get(WorkOrder, exception.work_order_id)
    if work_order is None or exception.status not in {
        ExceptionStatus.PENDING,
        ExceptionStatus.MANUAL_REVIEW,
    }:
        raise HTTPException(status_code=409, detail="当前异常状态不允许驳回")
    transition_work_order(
        session,
        work_order,
        WorkOrderStatus.EXCEPTION_REJECTED,
        payload.actor_id,
        payload.reason,
    )
    transition_work_order(
        session,
        work_order,
        WorkOrderStatus.VERIFIED,
        payload.actor_id,
        "人工确认原异常不成立",
    )
    exception.status = ExceptionStatus.REJECTED
    exception.human_reason = payload.reason
    exception.reviewed_by = payload.actor_id
    exception.reviewed_at = utc_now()
    session.commit()
    return _exception_detail(session, exception.id)


@router.post(
    "/exceptions/{exception_id}/rework-task",
    response_model=ExceptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_rework_task(
    exception_id: str,
    payload: ReworkTaskCreate,
    session: SessionDependency,
) -> ExceptionRead:
    exception = _get_exception(session, exception_id)
    if exception.status != ExceptionStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="只有已确认异常才能派发返工")
    if session.scalar(select(ReworkTask).where(ReworkTask.exception_id == exception.id)):
        raise HTTPException(status_code=409, detail="该异常已存在返工任务")
    work_order = session.get(WorkOrder, exception.work_order_id)
    if work_order is None:
        raise HTTPException(status_code=409, detail="异常关联工作单不存在")
    transition_work_order(
        session,
        work_order,
        WorkOrderStatus.REWORK_ASSIGNED,
        payload.actor_id,
        payload.instructions,
    )
    task = ReworkTask(
        exception_id=exception.id,
        work_order_id=work_order.id,
        assignee_id=payload.assignee_id,
        instructions=payload.instructions,
        created_by=payload.actor_id,
    )
    session.add(task)
    session.flush()
    session.add(
        Notification(
            work_order_id=work_order.id,
            rework_task_id=task.id,
            recipient_id=payload.assignee_id,
            event_type="REWORK_ASSIGNED",
            title=f"{work_order.code} 需要返工",
            message=payload.instructions,
        )
    )
    exception.status = ExceptionStatus.REWORK_ASSIGNED
    session.commit()
    return _exception_detail(session, exception.id)


@router.post(
    "/rework-tasks/{task_id}/videos",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_rework_video(
    task_id: str,
    session: SessionDependency,
    storage: StorageDependency,
    file: Annotated[UploadFile, File()],
) -> VideoAsset:
    task = _get_task(session, task_id)
    if task.status != ReworkTaskStatus.ASSIGNED:
        raise HTTPException(status_code=409, detail="当前返工任务状态不允许提交视频")
    filename = file.filename or "rework.mp4"
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持常见视频格式")
    content = await file.read(get_settings().max_video_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="视频内容为空")
    if len(content) > get_settings().max_video_bytes:
        raise HTTPException(status_code=413, detail="视频超过大小限制")
    digest = hashlib.sha256(content).hexdigest()
    storage_key = f"rework/{task.id}/{uuid.uuid4()}/{sanitize_filename(filename)}"
    storage.put(storage_key, content)
    video = VideoAsset(
        work_order_id=task.work_order_id,
        rework_task_id=task.id,
        filename=filename,
        content_type=file.content_type or "video/mp4",
        sha256=digest,
        storage_key=storage_key,
    )
    work_order = session.get(WorkOrder, task.work_order_id)
    exception = _get_exception(session, task.exception_id)
    if work_order is None:
        raise HTTPException(status_code=409, detail="返工任务关联工作单不存在")
    transition_work_order(
        session,
        work_order,
        WorkOrderStatus.REWORK_SUBMITTED,
        task.assignee_id,
        "返工视频已提交",
    )
    task.status = ReworkTaskStatus.SUBMITTED
    exception.status = ExceptionStatus.REWORK_SUBMITTED
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


@router.post("/rework-tasks/{task_id}/review", response_model=ReworkReviewResult)
def review_rework(
    task_id: str,
    payload: ReworkReviewRequest,
    session: SessionDependency,
    storage: StorageDependency,
) -> ReworkReviewResult:
    task = _get_task(session, task_id)
    if task.status != ReworkTaskStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="当前返工任务状态不允许复核")
    video = session.scalar(
        select(VideoAsset).where(
            VideoAsset.id == payload.video_id,
            VideoAsset.rework_task_id == task.id,
        )
    )
    if video is None:
        raise HTTPException(status_code=404, detail="返工视频不存在或不属于该任务")
    work_order = session.get(WorkOrder, task.work_order_id)
    exception = _get_exception(session, task.exception_id)
    if work_order is None:
        raise HTTPException(status_code=409, detail="返工任务关联工作单不存在")
    transition_work_order(
        session,
        work_order,
        WorkOrderStatus.REWORK_REVIEW,
        payload.actor_id,
        payload.notes,
    )
    task.status = ReworkTaskStatus.IN_REVIEW
    exception.status = ExceptionStatus.REWORK_REVIEW
    try:
        audit = execute_video_audit(session, work_order, video, storage)
    except (InvalidVideoAudit, VideoInferenceError) as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error

    task.reviewed_by = payload.actor_id
    task.review_notes = payload.notes
    if audit.decision == AuditDecision.PASS:
        transition_work_order(
            session,
            work_order,
            WorkOrderStatus.RELEASED,
            payload.actor_id,
            "返工复核通过",
        )
        task.status = ReworkTaskStatus.APPROVED
        task.completed_at = utc_now()
        exception.status = ExceptionStatus.RESOLVED
    else:
        transition_work_order(
            session,
            work_order,
            WorkOrderStatus.REWORK_ASSIGNED,
            payload.actor_id,
            audit.summary,
        )
        task.status = ReworkTaskStatus.ASSIGNED
        exception.status = ExceptionStatus.REWORK_ASSIGNED
        session.add(
            Notification(
                work_order_id=work_order.id,
                rework_task_id=task.id,
                recipient_id=task.assignee_id,
                event_type="REWORK_REJECTED",
                title=f"{work_order.code} 返工复核未通过",
                message=audit.summary,
            )
        )
    session.commit()
    session.refresh(task)
    session.refresh(work_order)
    audit = session.scalar(
        select(VideoAudit)
        .options(selectinload(VideoAudit.findings))
        .where(VideoAudit.id == audit.id)
    )
    return ReworkReviewResult.model_validate(
        {"task": task, "audit": audit, "work_order": work_order}
    )


@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(recipient_id: str, session: SessionDependency) -> list[Notification]:
    return session.scalars(
        select(Notification)
        .where(Notification.recipient_id == recipient_id)
        .order_by(Notification.created_at.desc())
    ).all()
