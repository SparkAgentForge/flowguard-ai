"""add exception rework workflow

Revision ID: c4a91bc7e2f0
Revises: 8e7d4d7f2c91
Create Date: 2026-09-22 20:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a91bc7e2f0"
down_revision: str | None = "8e7d4d7f2c91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

audit_decision_enum = sa.Enum(
    "PASS", "VIOLATION", "INSUFFICIENT_EVIDENCE", name="auditdecision"
)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        audit_decision_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "video_audits",
        sa.Column(
            "decision",
            audit_decision_enum,
            nullable=False,
            server_default="VIOLATION",
        ),
    )
    op.create_table(
        "exceptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "MANUAL_REVIEW",
                "CONFIRMED",
                "REJECTED",
                "REWORK_ASSIGNED",
                "REWORK_SUBMITTED",
                "REWORK_REVIEW",
                "RESOLVED",
                name="exceptionstatus",
            ),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("human_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["audit_id"], ["video_audits.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exceptions_audit_id", "exceptions", ["audit_id"], unique=True)
    op.create_index("ix_exceptions_status", "exceptions", ["status"])
    op.create_index("ix_exceptions_work_order_id", "exceptions", ["work_order_id"])
    op.create_table(
        "rework_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("exception_id", sa.String(length=36), nullable=False),
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("assignee_id", sa.String(length=100), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ASSIGNED", "SUBMITTED", "IN_REVIEW", "APPROVED", name="reworktaskstatus"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["exception_id"], ["exceptions.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rework_tasks_assignee_id", "rework_tasks", ["assignee_id"])
    op.create_index("ix_rework_tasks_exception_id", "rework_tasks", ["exception_id"], unique=True)
    op.create_index("ix_rework_tasks_status", "rework_tasks", ["status"])
    op.create_index("ix_rework_tasks_work_order_id", "rework_tasks", ["work_order_id"])
    with op.batch_alter_table("video_assets") as batch_op:
        batch_op.add_column(sa.Column("rework_task_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_video_assets_rework_task_id", "rework_tasks", ["rework_task_id"], ["id"]
        )
    op.create_index("ix_video_assets_rework_task_id", "video_assets", ["rework_task_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("rework_task_id", sa.String(length=36), nullable=True),
        sa.Column("recipient_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rework_task_id"], ["rework_tasks.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_event_type", "notifications", ["event_type"])
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
    op.create_index("ix_notifications_rework_task_id", "notifications", ["rework_task_id"])
    op.create_index("ix_notifications_work_order_id", "notifications", ["work_order_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_work_order_id", table_name="notifications")
    op.drop_index("ix_notifications_rework_task_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_index("ix_notifications_event_type", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_video_assets_rework_task_id", table_name="video_assets")
    with op.batch_alter_table("video_assets") as batch_op:
        batch_op.drop_constraint("fk_video_assets_rework_task_id", type_="foreignkey")
        batch_op.drop_column("rework_task_id")
    op.drop_index("ix_rework_tasks_work_order_id", table_name="rework_tasks")
    op.drop_index("ix_rework_tasks_status", table_name="rework_tasks")
    op.drop_index("ix_rework_tasks_exception_id", table_name="rework_tasks")
    op.drop_index("ix_rework_tasks_assignee_id", table_name="rework_tasks")
    op.drop_table("rework_tasks")
    op.drop_index("ix_exceptions_work_order_id", table_name="exceptions")
    op.drop_index("ix_exceptions_status", table_name="exceptions")
    op.drop_index("ix_exceptions_audit_id", table_name="exceptions")
    op.drop_table("exceptions")
    op.drop_column("video_audits", "decision")
    if op.get_bind().dialect.name == "postgresql":
        audit_decision_enum.drop(op.get_bind(), checkfirst=True)
