"""Contenido evergreen de Instagram: tipos de publicación variados anclados al
corpus (frases de canciones, efemérides/aniversarios, anécdotas, citas de Robe).

Añade a `instagram_queue`:
  - `content_type`: news | blog | quote | ephemeris | anecdote | robe_quote.
  - `content_key`: huella estable para deduplicar entre semanas.
  - nuevo estado `proposed` en el CHECK de `status` (espera aprobación del admin).

Backfill de `content_type` según el origen del item ya existente.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-08 20:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column(
            "content_type", sa.String(length=24), nullable=False,
            server_default="news",
        ),
    )
    op.add_column(
        "instagram_queue",
        sa.Column("content_key", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ix_instagram_queue_content_key", "instagram_queue", ["content_key"]
    )

    # Backfill del tipo según el origen del item ya encolado.
    op.execute(
        """
        UPDATE instagram_queue
           SET content_type = CASE
               WHEN blog_post_id IS NOT NULL THEN 'blog'
               WHEN news_item_id IS NOT NULL THEN 'news'
               WHEN category = 'Efemérides'   THEN 'ephemeris'
               WHEN category = 'Curiosidades' THEN 'anecdote'
               ELSE 'news'
           END
        """
    )

    # Amplía el CHECK de status para admitir el estado `proposed`.
    op.drop_constraint(
        "ck_instagram_queue_status", "instagram_queue", type_="check"
    )
    op.create_check_constraint(
        "ck_instagram_queue_status",
        "instagram_queue",
        "status IN ('proposed', 'pending', 'prepared', 'published', "
        "'failed', 'discarded')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_instagram_queue_status", "instagram_queue", type_="check"
    )
    op.create_check_constraint(
        "ck_instagram_queue_status",
        "instagram_queue",
        "status IN ('pending', 'prepared', 'published', 'failed', "
        "'discarded')",
    )
    op.drop_index(
        "ix_instagram_queue_content_key", table_name="instagram_queue"
    )
    op.drop_column("instagram_queue", "content_key")
    op.drop_column("instagram_queue", "content_type")
