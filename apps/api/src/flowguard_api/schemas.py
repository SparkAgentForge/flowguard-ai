from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from flowguard_api.models import (
    AuditDecision,
    ExceptionStatus,
    ReworkTaskStatus,
    SopStatus,
    VideoAuditStatus,
    WorkOrderStatus,
)


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
    current_assignee: str | None = None
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


class SopVersionSummary(ApiModel):
    id: str
    sop_id: str
    code: str
    name: str
    product_code: str
    version: str
    status: SopStatus
    published_at: datetime | None


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


class VideoRead(ApiModel):
    id: str
    work_order_id: str
    filename: str
    content_type: str
    sha256: str
    created_at: datetime


class AlignmentTraceRead(ApiModel):
    expected_code: str
    observed_code: str | None
    status: str
    reason: str


class ExecutionTraceRead(ApiModel):
    schema_version: str | None = None
    decision: str = "VIOLATION"
    overall_pass: bool = False
    summary: str = ""
    missing_steps: list[str] = Field(default_factory=list)
    misordered_steps: list[str] = Field(default_factory=list)
    uncertain_steps: list[str] = Field(default_factory=list)
    trace: list[AlignmentTraceRead] = Field(default_factory=list)
    graph: dict = Field(default_factory=dict)


class ReviewRequestRead(ApiModel):
    id: str
    step_code: str
    step_name: str
    start_seconds: int
    end_seconds: int
    question: str
    reason: str
    status: str
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    note: str | None = None


class VideoAuditRequest(ApiModel):
    video_id: str
    actor_id: str = Field(min_length=1, max_length=100)


class AuditFindingRead(ApiModel):
    id: str
    sop_step_id: str
    sequence: int
    step_name: str
    detected: bool
    confidence: int
    evidence_status: str
    evidence_score: int
    occluded: bool
    chunk_idx: int | None = None
    cv_boundary_score: float | None = None
    start_seconds: int | None
    end_seconds: int | None
    evidence: str
    frame_timestamps: list[int]


class VideoAuditRead(ApiModel):
    id: str
    work_order_id: str
    video_id: str
    status: VideoAuditStatus
    decision: AuditDecision
    provider: str
    model_name: str
    overall_pass: bool
    summary: str
    created_at: datetime
    completed_at: datetime
    execution_trace: ExecutionTraceRead = Field(default_factory=ExecutionTraceRead)
    review_requests: list[ReviewRequestRead] = Field(default_factory=list)
    findings: list[AuditFindingRead]


class ReviewRequestResolve(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)
    decision: str = Field(pattern="^(CONFIRMED|REJECTED)$")
    note: str | None = Field(default=None, max_length=1000)


class ExceptionActionRequest(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class ReworkTaskCreate(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)
    assignee_id: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=2000)


class ReworkReviewRequest(ApiModel):
    actor_id: str = Field(min_length=1, max_length=100)
    video_id: str
    notes: str | None = Field(default=None, max_length=1000)


class ReworkTaskRead(ApiModel):
    id: str
    exception_id: str
    work_order_id: str
    assignee_id: str
    instructions: str
    status: ReworkTaskStatus
    created_by: str
    reviewed_by: str | None
    review_notes: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExceptionRead(ApiModel):
    id: str
    work_order_id: str
    work_order_code: str
    audit_id: str
    status: ExceptionStatus
    decision: AuditDecision
    rule_code: str
    facts: list[str]
    human_reason: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    audit: VideoAuditRead
    rework_task: ReworkTaskRead | None


class ReworkReviewResult(ApiModel):
    task: ReworkTaskRead
    audit: VideoAuditRead
    work_order: WorkOrderRead


class NotificationRead(ApiModel):
    id: str
    work_order_id: str
    rework_task_id: str | None
    recipient_id: str
    event_type: str
    title: str
    message: str
    read_at: datetime | None
    created_at: datetime


class ReportRead(ApiModel):
    id: str
    work_order_id: str
    work_order_code: str
    version: int
    content: dict
    pdf_sha256: str
    archived_at: datetime
    created_at: datetime


class ReportSummary(ApiModel):
    id: str
    work_order_id: str
    work_order_code: str
    product_code: str
    work_order_status: WorkOrderStatus
    version: int
    outcome: str
    archived_at: datetime
