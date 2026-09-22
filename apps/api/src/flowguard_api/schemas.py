from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from flowguard_api.models import WorkOrderStatus


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class WorkOrderCreate(ApiModel):
    code: str = Field(min_length=1, max_length=100)
    product_code: str = Field(min_length=1, max_length=100)
    sop_version_id: str
    current_assignee: str | None = Field(default=None, max_length=100)


class WorkOrderTransition(ApiModel):
    target_status: WorkOrderStatus
    actor_id: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)


class WorkOrderRead(ApiModel):
    id: str
    code: str
    product_code: str
    sop_version_id: str
    status: WorkOrderStatus
    current_assignee: str | None
    created_at: datetime
    updated_at: datetime


class AuditEventRead(ApiModel):
    id: str
    event_type: str
    actor_id: str
    old_status: WorkOrderStatus
    new_status: WorkOrderStatus
    reason: str | None
    created_at: datetime


class WorkOrderDetail(WorkOrderRead):
    events: list[AuditEventRead]
