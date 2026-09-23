"""Saber si un «concierto» es en realidad una foto quieta con el audio encima.

No se puede deducir del título ni de la descripción: de los 45 conciertos
catalogados, solo 2 declaran ser audio, y el que se coló («GIRA 2012 | Robando
Perchas en el Hotel») no decía nada. Hay que mirar el vídeo.

Revision ID: igfija2026_01
Revises: igdirecto2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "igfija2026_01"
down_revision: str | None = "igdirecto2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_assets", sa.Column("imagen_fija", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("video_assets", "imagen_fija")
