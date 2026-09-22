from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from flowguard_api.models import SopStatus, WorkOrderStatus


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


class SourceReference(ApiModel):
    file_id: str
    page: int | None = Field(default=None, ge=1)
    paragraph: str | None = None
    quote: str = Field(min_length=1, max_length=500)


class SopStepPayload(ApiModel):
    code: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)
    required: bool = True
    preconditions: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    on_missing: str = Field(default="BLOCK", max_length=50)
    source_refs: list[SourceReference] = Field(default_factory=list)


class SopExtractRequest(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)


class SopUpdateRequest(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    product_code: str = Field(min_length=1, max_length=100)
    steps: list[SopStepPayload] = Field(min_length=1)


class SopActionRequest(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)


class DocumentRead(ApiModel):
    id: str
    filename: str
    content_type: str
    sha256: str
    created_at: datetime


class SopStepRead(SopStepPayload):
    id: str


class SopRevisionEventRead(ApiModel):
    id: str
    event_type: str
    actor_id: str
    old_status: SopStatus
    new_status: SopStatus
    details: dict
    created_at: datetime


class SopVersionDetail(ApiModel):
    id: str
    sop_id: str
    code: str
    name: str
    product_code: str
    version: str
    status: SopStatus
    source_document_id: str | None
    published_at: datetime | None
    steps: list[SopStepRead]
    events: list[SopRevisionEventRead]
