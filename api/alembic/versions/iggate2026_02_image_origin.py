"""`instagram_queue.image_origin`: de dónde salió la imagen publicada.

Revision ID: iggate2026_02
Revises: iggate2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "iggate2026_02"
down_revision: str | None = "iggate2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instagram_queue", sa.Column("image_origin", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("instagram_queue", "image_origin")
