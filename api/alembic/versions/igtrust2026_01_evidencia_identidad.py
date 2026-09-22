"""Evidencia de un post de Instagram: de dónde salió cada cosa.

El panel enseñaba `imagen ✓` —un booleano— sobre una foto de Pep Guardiola en
una noticia que iba de la presidenta de la Junta de Extremadura, con el caption
al lado. Con eso delante, cazar el fallo exigía reconocer la cara y luego abrir
la noticia original a mano. La query que buscó la foto no se guardaba: solo
quedaba en una línea del log del cron, que rota.

Tabla aparte de `instagram_queue` porque la cola es caliente (el publicador la
escribe cada quince minutos) y esto es un registro frío de auditoría.

`needs_human` sí va en la cola: hay que filtrar por él en SQL y el aprobado en
bloque tiene que poder negarse a llevárselos por delante.

Revision ID: igtrust2026_01
Revises: news2026_01
Create Date: 2026-09-22 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "igtrust2026_01"
down_revision: str | None = "news2026_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column("needs_human", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index(
        "ix_instagram_queue_needs_human", "instagram_queue", ["needs_human"]
    )

    op.create_table(
        "instagram_post_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("material_url", sa.String(700), nullable=True),
        sa.Column("material_status", sa.String(24), nullable=True),
        sa.Column("material_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entities", _JSON, nullable=True),
        sa.Column("subject_label", sa.String(200), nullable=True),
        sa.Column("subject_qid", sa.String(32), nullable=True),
        sa.Column("subject_description", sa.String(300), nullable=True),
        sa.Column("photo_source", sa.String(32), nullable=True),
        sa.Column("photo_verdict", sa.String(40), nullable=True),
        sa.Column("photo_reason", sa.Text(), nullable=True),
        sa.Column("photo_query", sa.String(300), nullable=True),
        sa.Column("photo_page_url", sa.String(700), nullable=True),
        sa.Column("photo_site", sa.String(200), nullable=True),
        sa.Column("photo_evidence", _JSON, nullable=True),
        sa.Column("claims", _JSON, nullable=True),
        sa.Column("avisos", _JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["instagram_queue.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id"),
    )
    op.create_index(
        "ix_instagram_post_evidence_item_id", "instagram_post_evidence", ["item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_post_evidence_item_id", table_name="instagram_post_evidence")
    op.drop_table("instagram_post_evidence")
    op.drop_index("ix_instagram_queue_needs_human", table_name="instagram_queue")
    op.drop_column("instagram_queue", "needs_human")
