"""instagram_queue: reintentos de publicación (attempts)

Un post que fallaba al publicar se quedaba en `failed` y ahí moría. No por
decisión: los dos selectores de la cola (`next_pending` y `due_pinned`) filtran
por pending/prepared, así que nadie lo volvía a mirar nunca. Un tropiezo
transitorio —el CDN, un timeout de Meta— borraba del calendario un post
programado, en silencio y sin reintento posible.

Se vio con el clip de la sala Vértigo (item 226), programado para el 29-jul-2026
a las 20:30: el vídeo estaba montado y subido, falló la publicación por otro
motivo y la publicación no salió ni volvió a intentarse.

`attempts` cuenta los intentos gastados. Los selectores repescan lo `failed`
mientras queden (`config.MAX_PUBLISH_ATTEMPTS`, 3 por defecto), y solo gastan
intento los fallos atribuibles al item: si lo que está caído es la conexión con
Meta, el fallo es global y no se le quema un intento a nadie.

Revision ID: igretry2026_01
Revises: igfmt2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "igretry2026_01"
down_revision = "igfmt2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    # Las filas que ya existen arrancan a 0: lo que esté en `failed` ahora mismo
    # entra con los tres intentos intactos, que es justo lo que se quiere (hasta
    # hoy no había reintento ninguno, así que no han gastado nada).


def downgrade() -> None:
    op.drop_column("instagram_queue", "attempts")
