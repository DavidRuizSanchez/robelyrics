"""El texto que se quema en el vídeo deja de ser el título del post.

Eran el mismo string: `solicitar` lo usaba para `instagram_queue.title` y para
`video_clips.subtitle`, que es lo que ve `drawtext`. Un titular descriptivo no
sirve de rótulo — y encima no cabía: medido, «Robe, desde el escenario — La
Cubierta, Leganés, 09-10-1999» ocupa 1622 px y el hueco son 1044, así que
ffmpeg se comía unos 20 caracteres por los dos lados.

Revision ID: igrotulo2026_01
Revises: igfija2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "igrotulo2026_01"
down_revision: str | None = "igfija2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("video_clips", sa.Column("overlay", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("video_clips", "overlay")
