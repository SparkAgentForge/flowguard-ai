"""Deletion workflow for disposable, non-archived work orders."""

import logging
from collections.abc import Iterable

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from flowguard_api.core.storage import FileStorage
from flowguard_api.models import (
    AuditEvent,
    AuditFinding,
    ExceptionCase,
    Notification,
    Report,
    ReworkTask,
    VideoAsset,
    VideoAudit,
    WorkOrder,
    WorkOrderStatus,
)

logger = logging.getLogger("flowguard.work_order_deletion")


class WorkOrderNotFoundError(ValueError):
    pass


class WorkOrderDeleteConfirmationError(ValueError):
    pass


class WorkOrderDeletionBlocked(ValueError):
    pass


PROTECTED_STATUSES = {WorkOrderStatus.RELEASED, WorkOrderStatus.ARCHIVED}


def _frame_asset_keys(audits: Iterable[VideoAudit]) -> set[str]:
    keys: set[str] = set()
    for audit in audits:
        raw_response = audit.raw_response or {}
        frame_keys = raw_response.get("frame_asset_keys", [])
        if isinstance(frame_keys, list):
            keys.update(key for key in frame_keys if isinstance(key, str) and key)
    return keys


def delete_work_order(
    session: Session,
    storage: FileStorage,
    work_order_id: str,
    actor_id: str,
    confirmation: str,
) -> None:
    """Delete one disposable work order and every owned record/object.

    SOPs and source documents are shared assets, so they are deliberately left
    untouched. Storage deletes happen before the transaction commits; all
    providers implement them idempotently, which makes retries safe.
    """

    work_order = session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise WorkOrderNotFoundError("工单不存在")
    if confirmation != work_order.code:
        raise WorkOrderDeleteConfirmationError("请输入完全一致的工单编号进行确认")
    if work_order.status in PROTECTED_STATUSES:
        raise WorkOrderDeletionBlocked("已发布或已归档的工单不能删除，请保留其生产追溯记录")

    audits = session.scalars(
        select(VideoAudit).where(VideoAudit.work_order_id == work_order_id)
    ).all()
    reports = session.scalars(
        select(Report).where(Report.work_order_id == work_order_id)
    ).all()
    videos = session.scalars(
        select(VideoAsset).where(VideoAsset.work_order_id == work_order_id)
    ).all()
    storage_keys = {
        *(video.storage_key for video in videos),
        *(report.pdf_storage_key for report in reports),
        *_frame_asset_keys(audits),
    }

    try:
        for key in storage_keys:
            storage.delete(key)

        audit_ids = [audit.id for audit in audits]
        exception_ids = session.scalars(
            select(ExceptionCase.id).where(ExceptionCase.work_order_id == work_order_id)
        ).all()

        # Delete children first because the existing schema intentionally keeps
        # foreign keys explicit instead of relying on database-wide cascades.
        if audit_ids:
            session.execute(delete(AuditFinding).where(AuditFinding.audit_id.in_(audit_ids)))
        session.execute(delete(Notification).where(Notification.work_order_id == work_order_id))
        # Rework videos point back to their task while the task points to an
        # exception and the exception points to an audit. Break that cycle
        # before deleting the dependent rows on PostgreSQL.
        session.execute(
            update(VideoAsset)
            .where(VideoAsset.work_order_id == work_order_id)
            .values(rework_task_id=None)
        )
        if exception_ids:
            session.execute(delete(ReworkTask).where(ReworkTask.exception_id.in_(exception_ids)))
        session.execute(delete(ExceptionCase).where(ExceptionCase.work_order_id == work_order_id))
        if audit_ids:
            session.execute(delete(VideoAudit).where(VideoAudit.id.in_(audit_ids)))
        session.execute(delete(VideoAsset).where(VideoAsset.work_order_id == work_order_id))
        session.execute(delete(Report).where(Report.work_order_id == work_order_id))
        session.execute(delete(AuditEvent).where(AuditEvent.work_order_id == work_order_id))
        session.delete(work_order)
        session.commit()
    except Exception:
        session.rollback()
        raise

    logger.info(
        "工单已删除 work_order_id=%s code=%s actor_id=%s storage_objects=%d audits=%d",
        work_order_id,
        work_order.code,
        actor_id,
        len(storage_keys),
        len(audits),
    )
