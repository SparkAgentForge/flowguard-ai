"""add archived reports

Revision ID: a037d195fb22
Revises: c4a91bc7e2f0
Create Date: 2026-09-22 21:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a037d195fb22"
down_revision: str | None = "c4a91bc7e2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("pdf_storage_key", sa.String(length=500), nullable=False),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pdf_storage_key"),
        sa.UniqueConstraint("work_order_id", "version", name="uq_report_version"),
    )
    op.create_index("ix_reports_work_order_id", "reports", ["work_order_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_work_order_id", table_name="reports")
    op.drop_table("reports")
