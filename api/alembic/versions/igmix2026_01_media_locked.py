"""instagram_queue: marcar el formato fijado a mano (media_locked)

El repartidor de formatos asigna foto/carrusel/reel a los posts programados para
que el feed no salga monótono. Pero si el admin ha elegido el formato de un post
a mano, ese no se toca: `media_locked` distingue "lo eligió una persona" de "lo
puso el automático".

Revision ID: igmix2026_01
Revises: igmedia2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "igmix2026_01"
down_revision = "igmedia2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column(
            "media_locked", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )
    op.alter_column("instagram_queue", "media_locked", server_default=None)


def downgrade() -> None:
    op.drop_column("instagram_queue", "media_locked")
