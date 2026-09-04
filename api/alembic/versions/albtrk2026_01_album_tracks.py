"""Tracklist referencial para discos que no son de estudio + vocabulario de `kind`.

Dos cosas que van juntas:

1. `album_tracks` — un directo o un recopilatorio necesita su tracklist sin
   duplicar filas `Song`. La relación canción↔disco es N:M y `songs.album_id`
   solo modela 1:N; sin esta tabla, dar de alta «Grandes éxitos y fracasos»
   habría creado 33 páginas de canción compitiendo en Google con las originales.

2. `albums.kind` era `String(32)` **sin constraint**: admitía cualquier typo, y
   `catalog_consensus._has_studio` compara por igualdad literal contra "studio",
   así que un «Studio» mal escrito lo dejaba fuera en silencio. Se fija el
   vocabulario y se amplía con `compilation`, `single` y `demo`, que hacían
   falta para el barrido de discografía.

Revision ID: albtrk2026_01
Revises: igretry2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "albtrk2026_01"
down_revision = "igretry2026_01"
branch_labels = None
depends_on = None

KINDS = ("studio", "ep", "live", "compilation", "single", "demo")
_KINDS_SQL = ", ".join(f"'{k}'" for k in KINDS)


def upgrade() -> None:
    op.create_table(
        "album_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("album_id", sa.Integer(), nullable=False),
        sa.Column("disc", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title_as_released", sa.String(length=256), nullable=False),
        sa.Column("song_id", sa.Integer(), nullable=True),
        sa.Column("match_source", sa.String(length=16), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("recording_mbid", sa.String(length=64), nullable=True),
        sa.Column("is_rerecording", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        # SET NULL y no CASCADE: si se borra una canción, el corte del
        # recopilatorio sigue existiendo, solo se queda sin enlazar.
        sa.ForeignKeyConstraint(["song_id"], ["songs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("album_id", "disc", "position", name="uq_album_tracks_pos"),
    )
    op.create_index("ix_album_tracks_song", "album_tracks", ["song_id"])

    op.create_check_constraint("ck_albums_kind", "albums", f"kind IN ({_KINDS_SQL})")


def downgrade() -> None:
    op.drop_constraint("ck_albums_kind", "albums", type_="check")
    op.drop_index("ix_album_tracks_song", table_name="album_tracks")
    op.drop_table("album_tracks")
