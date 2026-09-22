"""Material real del artículo en news_items: sin cuerpo, el modelo escribe a ciegas.

Hasta ahora esta tabla guardaba solo titular + enlace + extracto de 280 chars,
por respeto de derechos tipo agregador. El problema medido el 22-09-2026 sobre
la cola de Instagram: **177 de 212 noticias (83,5%) ni siquiera tenían extracto**
—los feeds de Google News repiten el titular en la descripción y el agregador lo
vacía—, así que el LLM escribía cuatro frases, elegía foto y montaba un carrusel
de cinco diapositivas a partir de UNA línea. De ahí salió un post que confundió a
la protagonista con un homónimo famoso y le atribuyó una afinidad con Robe que
ninguna fuente mencionaba.

Se guarda el cuerpo, pues, pero sigue sin ser un archivo: `purge_old` limpia esta
tabla a los 7 días, así que es caché de trabajo. Y el cuerpo NO se copia al
snapshot de `instagram_queue`, que es lo que sobrevive para siempre: de un
artículo ajeno ahí sigue quedando titular, enlace y extracto.

`body_url` es la URL del medio DE VERDAD: el 84,4% de las filas traen en `url`
un enlace `news.google.com` que no redirige y hay que traducir.

Revision ID: news2026_01
Revises: seoq2026_01
Create Date: 2026-09-22 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "news2026_01"
down_revision: str | None = "seoq2026_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_items", sa.Column("body_url", sa.String(700), nullable=True))
    op.add_column("news_items", sa.Column("body_text", sa.Text(), nullable=True))
    op.add_column(
        "news_items",
        sa.Column("body_chars", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "news_items",
        sa.Column(
            "body_status",
            sa.String(24),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "news_items",
        sa.Column("body_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Para que el agregador encuentre barato lo que le queda por bajar.
    op.create_index(
        "ix_news_items_body_status", "news_items", ["body_status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_news_items_body_status", table_name="news_items")
    for col in ("body_fetched_at", "body_status", "body_chars", "body_text", "body_url"):
        op.drop_column("news_items", col)
