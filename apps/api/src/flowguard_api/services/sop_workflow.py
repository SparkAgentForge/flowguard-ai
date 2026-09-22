from datetime import UTC, datetime

from sqlalchemy.orm import Session

from flowguard_api.models import SopRevisionEvent, SopStatus, SopVersion


class InvalidSopTransition(ValueError):
    pass


ALLOWED_SOP_TRANSITIONS: dict[SopStatus, frozenset[SopStatus]] = {
    SopStatus.DRAFT: frozenset({SopStatus.AI_EXTRACTED}),
    SopStatus.AI_EXTRACTED: frozenset({SopStatus.IN_REVIEW}),
    SopStatus.IN_REVIEW: frozenset({SopStatus.APPROVED}),
    SopStatus.APPROVED: frozenset({SopStatus.PUBLISHED}),
    SopStatus.PUBLISHED: frozenset({SopStatus.RETIRED}),
    SopStatus.RETIRED: frozenset(),
}


def transition_sop(
    session: Session,
    version: SopVersion,
    target_status: SopStatus,
    actor_id: str,
    details: dict | None = None,
) -> SopRevisionEvent:
    old_status = version.status
    if target_status not in ALLOWED_SOP_TRANSITIONS[old_status]:
        message = f"不允许从 {old_status.value} 转换到 {target_status.value}"
        raise InvalidSopTransition(message)
    version.status = target_status
    if target_status is SopStatus.PUBLISHED:
        version.published_at = datetime.now(UTC)
    event = SopRevisionEvent(
        sop_version_id=version.id,
        event_type=f"SOP_{target_status.value}",
        actor_id=actor_id,
        old_status=old_status,
        new_status=target_status,
        details=details or {},
    )
    session.add(event)
    session.flush()
    return event
