from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.database import get_session
from flowguard_api.infrastructure.storage.factory import get_file_storage
from flowguard_api.models import AuditEvent, WorkOrder
from flowguard_api.schemas import (
    WorkOrderCreate,
    WorkOrderDeleteRequest,
    WorkOrderDetail,
    WorkOrderRead,
    WorkOrderTransition,
)
from flowguard_api.services.work_order_deletion import (
    WorkOrderDeleteConfirmationError,
    WorkOrderDeletionBlocked,
    WorkOrderNotFoundError,
    delete_work_order,
)
from flowguard_api.services.work_order_state import (
    InvalidWorkOrderTransition,
    transition_work_order,
)

router = APIRouter(prefix="/work-orders", tags=["work orders"])
SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[FileStorage, Depends(get_file_storage)]


@router.get("", response_model=list[WorkOrderRead])
def list_work_orders(session: SessionDependency) -> list[WorkOrder]:
    return session.scalars(select(WorkOrder).order_by(WorkOrder.created_at.desc())).all()


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


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    work_order_id: str,
    payload: WorkOrderDeleteRequest,
    session: SessionDependency,
    storage: StorageDependency,
) -> Response:
    try:
        delete_work_order(
            session,
            storage,
            work_order_id,
            payload.actor_id,
            payload.confirmation,
        )
    except WorkOrderNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except WorkOrderDeleteConfirmationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except WorkOrderDeletionBlocked as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
