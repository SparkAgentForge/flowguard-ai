"""add video audit tables

Revision ID: 8e7d4d7f2c91
Revises: 23c94ebddde8
Create Date: 2026-09-22 18:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e7d4d7f2c91"
down_revision: str | None = "23c94ebddde8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_video_assets_work_order_id", "video_assets", ["work_order_id"])
    op.create_index("ix_video_assets_sha256", "video_assets", ["sha256"])
    op.create_table(
        "video_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.Enum("COMPLETED", "FAILED", name="videoauditstatus"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("overall_pass", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["video_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_audits_work_order_id", "video_audits", ["work_order_id"])
    op.create_index("ix_video_audits_video_id", "video_audits", ["video_id"])
    op.create_table(
        "audit_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("sop_step_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=255), nullable=False),
        sa.Column("detected", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Integer(), nullable=True),
        sa.Column("end_seconds", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("frame_timestamps", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["audit_id"], ["video_audits.id"]),
        sa.ForeignKeyConstraint(["sop_step_id"], ["sop_steps.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_findings_audit_id", "audit_findings", ["audit_id"])
    op.create_index("ix_audit_findings_sop_step_id", "audit_findings", ["sop_step_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_findings_sop_step_id", table_name="audit_findings")
    op.drop_index("ix_audit_findings_audit_id", table_name="audit_findings")
    op.drop_table("audit_findings")
    op.drop_index("ix_video_audits_video_id", table_name="video_audits")
    op.drop_index("ix_video_audits_work_order_id", table_name="video_audits")
    op.drop_table("video_audits")
    op.drop_index("ix_video_assets_sha256", table_name="video_assets")
    op.drop_index("ix_video_assets_work_order_id", table_name="video_assets")
    op.drop_table("video_assets")
