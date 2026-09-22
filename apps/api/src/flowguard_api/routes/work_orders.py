from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowguard_api.database import get_session
from flowguard_api.models import AuditEvent, WorkOrder
from flowguard_api.schemas import (
    WorkOrderCreate,
    WorkOrderDetail,
    WorkOrderRead,
    WorkOrderTransition,
)
from flowguard_api.services.work_order_state import (
    InvalidWorkOrderTransition,
    transition_work_order,
)

router = APIRouter(prefix="/work-orders", tags=["work orders"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.post("", response_model=WorkOrderRead, status_code=status.HTTP_201_CREATED)
def create_work_order(payload: WorkOrderCreate, session: SessionDependency) -> WorkOrder:
    work_order = WorkOrder(**payload.model_dump())
    session.add(work_order)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="工单编号已存在或 SOP 版本无效") from error
    session.refresh(work_order)
    return work_order


@router.get("/{work_order_id}", response_model=WorkOrderDetail)
def get_work_order(work_order_id: str, session: SessionDependency) -> WorkOrderDetail:
    work_order = session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.work_order_id == work_order_id)
        .order_by(AuditEvent.created_at)
    ).all()
    return WorkOrderDetail.model_validate({**work_order.__dict__, "events": events})


@router.post("/{work_order_id}/transitions", response_model=WorkOrderDetail)
def transition(
    work_order_id: str,
    payload: WorkOrderTransition,
    session: SessionDependency,
) -> WorkOrderDetail:
    work_order = session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    try:
        transition_work_order(
            session,
            work_order,
            payload.target_status,
            payload.actor_id,
            payload.reason,
        )
        session.commit()
    except InvalidWorkOrderTransition as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    session.refresh(work_order)
    return get_work_order(work_order_id, session)
