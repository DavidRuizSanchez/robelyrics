"""instagram_queue: programar con fecha Y hora (publish_at)

Hasta ahora la única forma de fijar cuándo sale un post era `publish_on`, que es
un `Date`: servía para las efemérides ("este va el día de su cumpleaños") pero no
permitía programar a una hora concreta, y además el panel ni siquiera podía
escribirlo — solo lo ponía el generador de efemérides.

`publish_at` (timestamptz) convive con `publish_on`:
  - `publish_on`  → efeméride de día fijo, sin hora. Se conserva tal cual.
  - `publish_at`  → programación exacta hecha a mano desde el panel.

Revision ID: igsched2026_01
Revises: ingest2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "igsched2026_01"
down_revision = "ingest2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
    )
    # El cron busca lo vencido en cada pasada: sin índice sería un seq scan por
    # ejecución sobre toda la cola histórica.
    op.create_index(
        "ix_instagram_queue_publish_at", "instagram_queue", ["publish_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_queue_publish_at", table_name="instagram_queue")
    op.drop_column("instagram_queue", "publish_at")
