"""Cola de altas manuales desde URL, para sacarlas del ciclo de petición HTTP.

El alta manual de una noticia tarda de 2 a 4 minutos (investiga, escribe sección a
sección verificando cada una y, si el gate de rigor la rechaza, reintenta con
investigación reforzada). Cloudflare corta a los 100 s, así que el admin recibía un
`524` y no llegaba a ver NUNCA el resultado —ni la propuesta ni las razones del
rechazo—, aunque el servidor terminara bien. Medido en producción: 264,8 s.

Con esta tabla la petición solo encola: el trabajo corre en el servidor (sobrevive a
cerrar la pestaña) y el panel consulta el estado. En BD y no en memoria porque
uvicorn corre con varios workers y el polling puede caer en otro.

Revision ID: ingest2026_01
Revises: rigor2026_03
Create Date: 2026-07-28 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ingest2026_01"
down_revision: str | None = "rigor2026_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "url_ingest_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        # La petición tal cual, para poder reintentar sin volver a pegar el texto.
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("topic", sa.String(length=240), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("rewrite", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="running"
        ),
        sa.Column("proposal_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("rewritten", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("warning", sa.Text(), nullable=True),
        # Veredicto del gate cuando rechaza, para pintarlo en el panel.
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("boosted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'rejected', 'failed')",
            name="ck_url_ingest_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_url_ingest_jobs_url", "url_ingest_jobs", ["url"])
    op.create_index("ix_url_ingest_jobs_status", "url_ingest_jobs", ["status"])
    op.create_index("ix_url_ingest_jobs_created_at", "url_ingest_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_url_ingest_jobs_created_at", table_name="url_ingest_jobs")
    op.drop_index("ix_url_ingest_jobs_status", table_name="url_ingest_jobs")
    op.drop_index("ix_url_ingest_jobs_url", table_name="url_ingest_jobs")
    op.drop_table("url_ingest_jobs")
