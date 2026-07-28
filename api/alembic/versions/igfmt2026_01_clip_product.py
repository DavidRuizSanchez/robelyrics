"""instagram_queue: CLIP y PRODUCT como formatos de publicación

Los clips de vídeo externos y las piezas que enseñan la web se habían montado
como «fuentes de material» con su propio flujo (un botón aparte, una asignación
desde otro panel). Es confuso: desde el punto de vista de quien maneja la cola,
son lo mismo que una foto o un carrusel — **formas que puede tomar un post**.

Ahora el selector de formato tiene las cinco opciones y el flujo es uno solo:
eliges el formato, preparas, y el motor sabe de dónde sacar el material.

Revision ID: igfmt2026_01
Revises: igclip2026_01
"""
from alembic import op

revision = "igfmt2026_01"
down_revision = "igclip2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_instagram_queue_media_type", "instagram_queue", type_="check"
    )
    op.create_check_constraint(
        "ck_instagram_queue_media_type",
        "instagram_queue",
        "media_type IN ('IMAGE','CAROUSEL','REELS','CLIP','PRODUCT')",
    )


def downgrade() -> None:
    # Lo que use los formatos nuevos vuelve al genérico antes de estrechar.
    op.execute(
        "UPDATE instagram_queue SET media_type = 'REELS' WHERE media_type = 'CLIP'"
    )
    op.execute(
        "UPDATE instagram_queue SET media_type = 'IMAGE' WHERE media_type = 'PRODUCT'"
    )
    op.drop_constraint(
        "ck_instagram_queue_media_type", "instagram_queue", type_="check"
    )
    op.create_check_constraint(
        "ck_instagram_queue_media_type",
        "instagram_queue",
        "media_type IN ('IMAGE','CAROUSEL','REELS')",
    )
