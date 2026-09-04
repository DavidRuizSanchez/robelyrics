"""instagram_queue: last_attempt_at + error_code (cortacircuitos de publicación)

Meta restringió la cuenta el 24-ago-2026 (code 25 / subcode 2207050). El código
no distinguía un bloqueo GLOBAL de un fallo del post, así que cada intento
quemaba un intento del item; y como el cron dispara cada 15 min y el guard de
cadencia solo frena tras un ÉXITO, los 47 posts de la cola se condenaron en día
y medio, en silencio.

Estas dos columnas cierran las dos puertas:
  - `last_attempt_at` espacia los reintentos (RETRY_COOLDOWN_H).
  - `error_code` guarda el "25/2207050" para clasificar y para deducir de la
    propia cola si la publicación está bloqueada, sin flag que apagar a mano.

Revision ID: igblock2026_01
Revises: robename2026_01
"""
import sqlalchemy as sa

from alembic import op

revision = "igblock2026_01"
down_revision = "robename2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instagram_queue",
        sa.Column("error_code", sa.String(24), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instagram_queue", "error_code")
    op.drop_column("instagram_queue", "last_attempt_at")
