import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SopStatus(StrEnum):
    DRAFT = "DRAFT"
    AI_EXTRACTED = "AI_EXTRACTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class WorkOrderStatus(StrEnum):
    CREATED = "CREATED"
    INSPECTING = "INSPECTING"
    VERIFIED = "VERIFIED"
    EXCEPTION_PENDING = "EXCEPTION_PENDING"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    EXCEPTION_CONFIRMED = "EXCEPTION_CONFIRMED"
    EXCEPTION_REJECTED = "EXCEPTION_REJECTED"
    REWORK_ASSIGNED = "REWORK_ASSIGNED"
    REWORK_SUBMITTED = "REWORK_SUBMITTED"
    REWORK_REVIEW = "REWORK_REVIEW"
    RELEASED = "RELEASED"
    ARCHIVED = "ARCHIVED"


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)


class Sop(Base, TimestampMixin):
    __tablename__ = "sops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    product_code: Mapped[str] = mapped_column(String(100), index=True)
    versions: Mapped[list["SopVersion"]] = relationship(back_populates="sop")


class SopVersion(Base, TimestampMixin):
    __tablename__ = "sop_versions"
    __table_args__ = (UniqueConstraint("sop_id", "version", name="uq_sop_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sop_id: Mapped[str] = mapped_column(ForeignKey("sops.id"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    version: Mapped[str] = mapped_column(String(50))
    status: Mapped[SopStatus] = mapped_column(Enum(SopStatus), default=SopStatus.DRAFT)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sop: Mapped[Sop] = relationship(back_populates="versions")
    steps: Mapped[list["SopStep"]] = relationship(
        back_populates="sop_version", cascade="all, delete-orphan"
    )


class SopStep(Base, TimestampMixin):
    __tablename__ = "sop_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sop_version_id: Mapped[str] = mapped_column(ForeignKey("sop_versions.id"), index=True)
    code: Mapped[str] = mapped_column(String(100))
    sequence: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    preconditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    on_missing: Mapped[str] = mapped_column(String(50), default="BLOCK")
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sop_version: Mapped[SopVersion] = relationship(back_populates="steps")


class SopRevisionEvent(Base):
    __tablename__ = "sop_revision_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sop_version_id: Mapped[str] = mapped_column(ForeignKey("sop_versions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    old_status: Mapped[SopStatus] = mapped_column(Enum(SopStatus))
    new_status: Mapped[SopStatus] = mapped_column(Enum(SopStatus))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkOrder(Base, TimestampMixin):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    product_code: Mapped[str] = mapped_column(String(100), index=True)
    sop_version_id: Mapped[str] = mapped_column(ForeignKey("sop_versions.id"), index=True)
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus), default=WorkOrderStatus.CREATED, index=True
    )
    current_assignee: Mapped[str | None] = mapped_column(String(100))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    old_status: Mapped[WorkOrderStatus] = mapped_column(Enum(WorkOrderStatus))
    new_status: Mapped[WorkOrderStatus] = mapped_column(Enum(WorkOrderStatus))
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
