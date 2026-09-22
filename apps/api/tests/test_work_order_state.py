import pytest
from sqlalchemy.orm import Session

from flowguard_api.models import Sop, SopVersion, WorkOrder, WorkOrderStatus
from flowguard_api.services.work_order_state import (
    InvalidWorkOrderTransition,
    transition_work_order,
)


def create_work_order(session: Session) -> WorkOrder:
    sop = Sop(code="PUMP-COVER", name="泵体端盖装配", product_code="PUMP-A01")
    version = SopVersion(sop=sop, version="1.0")
    work_order = WorkOrder(
        code="WO-001",
        product_code="PUMP-A01",
        sop_version_id=version.id,
    )
    session.add_all([sop, version])
    session.flush()
    work_order.sop_version_id = version.id
    session.add(work_order)
    session.flush()
    return work_order


def test_valid_transition_creates_audit_event(session: Session) -> None:
    work_order = create_work_order(session)

    event = transition_work_order(
        session,
        work_order,
        WorkOrderStatus.INSPECTING,
        actor_id="operator-01",
        reason="开始视频检测",
    )

    assert work_order.status is WorkOrderStatus.INSPECTING
    assert event.old_status is WorkOrderStatus.CREATED
    assert event.new_status is WorkOrderStatus.INSPECTING
    assert event.reason == "开始视频检测"


def test_illegal_transition_is_rejected(session: Session) -> None:
    work_order = create_work_order(session)

    with pytest.raises(InvalidWorkOrderTransition, match="不允许从 CREATED 转换到 ARCHIVED"):
        transition_work_order(
            session,
            work_order,
            WorkOrderStatus.ARCHIVED,
            actor_id="quality-01",
        )

    assert work_order.status is WorkOrderStatus.CREATED
