"""add execution trace and evidence fields

Revision ID: 5f9a4c3e8d21
Revises: a037d195fb22
Create Date: 2026-09-25 16:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f9a4c3e8d21"
down_revision: str | None = "a037d195fb22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video_audits", sa.Column("execution_trace", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("video_audits", sa.Column("review_requests", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("audit_findings", sa.Column("evidence_status", sa.String(length=40), nullable=False, server_default="CONFIRMED"))
    op.add_column("audit_findings", sa.Column("evidence_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("audit_findings", sa.Column("occluded", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("audit_findings", sa.Column("chunk_idx", sa.Integer(), nullable=True))
    op.add_column("audit_findings", sa.Column("cv_boundary_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_findings", "cv_boundary_score")
    op.drop_column("audit_findings", "chunk_idx")
    op.drop_column("audit_findings", "occluded")
    op.drop_column("audit_findings", "evidence_score")
    op.drop_column("audit_findings", "evidence_status")
    op.drop_column("video_audits", "review_requests")
    op.drop_column("video_audits", "execution_trace")
