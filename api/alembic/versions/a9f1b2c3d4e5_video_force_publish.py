"""ContentProposal: video (JSONB) + force_publish; Post: force_publish.

- `video`: metadatos del vídeo embebido (YouTube) para el VideoObject JSON-LD,
  que antes se descartaba en el camino propuesta→post.
- `force_publish`: override del admin para publicar "sí o sí" saltando el gate de
  calidad (rigor/longitud/foco), manteniendo el fact-check canónico.

Revision ID: a9f1b2c3d4e5
Revises: c2d3e4f5a6b7
Create Date: 2026-06-25 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9f1b2c3d4e5"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_proposals",
        sa.Column("video", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "content_proposals",
        sa.Column("force_publish", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )
    op.add_column(
        "posts",
        sa.Column("force_publish", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("posts", "force_publish")
    op.drop_column("content_proposals", "force_publish")
    op.drop_column("content_proposals", "video")
