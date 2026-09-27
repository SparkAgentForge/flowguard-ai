"""add durable processing status for video audits

Revision ID: c7a2d9e4f810
Revises: b1e6c4a20f77
Create Date: 2026-09-27 16:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7a2d9e4f810"
down_revision: str | None = "b1e6c4a20f77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE videoauditstatus ADD VALUE IF NOT EXISTS 'PROCESSING'"
        )


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place. The status is
    # additive and older application versions simply never write it.
    pass
