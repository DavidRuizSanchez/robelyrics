"""Clips de UNA canción, cortados en su estribillo.

Criterio de David (09-10-2026): un clip es una canción y su estribillo, no un
momento rescatado de un concierto entero transcrito. `video_assets` admite
vídeos de una sola canción (`live_song`) con la canción a la que pertenecen, y
`video_clips` sabe qué canción es y si el tramo está por LOCALIZAR: el daemon
escucha el audio, busca el estribillo de esa canción y, si no lo oye, no hay
clip.

Revision ID: clipcancion2026_01
Revises: revblockby2026_01
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "clipcancion2026_01"
down_revision: str | None = "revblockby2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_video_assets_kind", "video_assets", type_="check")
    op.create_check_constraint(
        "ck_video_assets_kind", "video_assets",
        "kind IN ('interview','live_fan','live_song')",
    )
    op.add_column("video_assets", sa.Column(
        "song_id", sa.Integer(), sa.ForeignKey("songs.id", ondelete="SET NULL"), nullable=True))
    op.add_column("video_clips", sa.Column(
        "song_id", sa.Integer(), sa.ForeignKey("songs.id", ondelete="SET NULL"), nullable=True))
    op.add_column("video_clips", sa.Column(
        "buscar_estribillo", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("video_clips", "buscar_estribillo")
    op.drop_column("video_clips", "song_id")
    op.drop_column("video_assets", "song_id")
    op.drop_constraint("ck_video_assets_kind", "video_assets", type_="check")
    op.create_check_constraint(
        "ck_video_assets_kind", "video_assets", "kind IN ('interview','live_fan')")
