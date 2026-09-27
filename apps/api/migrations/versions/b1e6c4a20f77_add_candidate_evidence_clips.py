"""add candidate evidence ranges for video findings

Revision ID: b1e6c4a20f77
Revises: 5f9a4c3e8d21
Create Date: 2026-09-27 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1e6c4a20f77"
down_revision: str | None = "5f9a4c3e8d21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_findings", sa.Column("candidate_start_seconds", sa.Integer(), nullable=True)
    )
    op.add_column(
        "audit_findings", sa.Column("candidate_end_seconds", sa.Integer(), nullable=True)
    )
    op.add_column(
        "audit_findings",
        sa.Column("candidate_frame_timestamps", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("audit_findings", "candidate_frame_timestamps")
    op.drop_column("audit_findings", "candidate_end_seconds")
    op.drop_column("audit_findings", "candidate_start_seconds")
