from sqlalchemy.orm import Session

from flowguard_api.models import AuditEvent, WorkOrder, WorkOrderStatus


class InvalidWorkOrderTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[WorkOrderStatus, frozenset[WorkOrderStatus]] = {
    WorkOrderStatus.CREATED: frozenset({WorkOrderStatus.INSPECTING}),
    # A provider failure must release the work order so the operator can retry.
    # This is a technical recovery transition, not a quality decision.
    WorkOrderStatus.INSPECTING: frozenset(
        {WorkOrderStatus.CREATED, WorkOrderStatus.VERIFIED, WorkOrderStatus.EXCEPTION_PENDING}
    ),
    WorkOrderStatus.VERIFIED: frozenset({WorkOrderStatus.ARCHIVED}),
    WorkOrderStatus.EXCEPTION_PENDING: frozenset(
        {
            WorkOrderStatus.MANUAL_REVIEW,
            WorkOrderStatus.EXCEPTION_CONFIRMED,
            WorkOrderStatus.EXCEPTION_REJECTED,
        }
    ),
    WorkOrderStatus.MANUAL_REVIEW: frozenset(
        {WorkOrderStatus.EXCEPTION_CONFIRMED, WorkOrderStatus.EXCEPTION_REJECTED}
    ),
    WorkOrderStatus.EXCEPTION_CONFIRMED: frozenset({WorkOrderStatus.REWORK_ASSIGNED}),
    WorkOrderStatus.EXCEPTION_REJECTED: frozenset({WorkOrderStatus.VERIFIED}),
    WorkOrderStatus.REWORK_ASSIGNED: frozenset({WorkOrderStatus.REWORK_SUBMITTED}),
    WorkOrderStatus.REWORK_SUBMITTED: frozenset({WorkOrderStatus.REWORK_REVIEW}),
    WorkOrderStatus.REWORK_REVIEW: frozenset(
        {WorkOrderStatus.RELEASED, WorkOrderStatus.REWORK_ASSIGNED}
    ),
    WorkOrderStatus.RELEASED: frozenset({WorkOrderStatus.ARCHIVED}),
    WorkOrderStatus.ARCHIVED: frozenset(),
}


def transition_work_order(
    session: Session,
    work_order: WorkOrder,
    target_status: WorkOrderStatus,
    actor_id: str,
    reason: str | None = None,
) -> AuditEvent:
    old_status = work_order.status
    if target_status not in ALLOWED_TRANSITIONS[old_status]:
        message = f"不允许从 {old_status.value} 转换到 {target_status.value}"
        raise InvalidWorkOrderTransition(message)

    work_order.status = target_status
    event = AuditEvent(
        work_order_id=work_order.id,
        event_type="WORK_ORDER_STATUS_CHANGED",
        actor_id=actor_id,
        old_status=old_status,
        new_status=target_status,
        reason=reason,
    )
    session.add(event)
    session.flush()
    return event
