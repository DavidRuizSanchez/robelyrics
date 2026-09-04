"""Procedencia de las portadas: de dónde salió cada una y con qué licencia.

`docs/legal-audit.md` §3.5 lo tiene como tarea pendiente desde el principio:
Cover Art Archive distribuye covers subidas por la comunidad con una licencia
declarada por cada upload, pero **no garantiza que quien la subió tuviera
derechos**. La recomendación era revisar esa licencia y sustituir las
restrictivas — y no se podía hacer, porque `match_covers.py` descartaba el MBID
tras descargar el JPG y la licencia dejaba de ser re-consultable.

Con estas tres columnas la pregunta «¿de dónde salió esta portada?» tiene
respuesta sin volver a buscar a ciegas — que es justo lo que ya coló la portada
de «Rock transgresivo» como si fuera la de «Tú en tu casa…»
(data/reference/rock_transgresivo_y_tu_en_tu_casa.md).

Revision ID: cover2026_01
Revises: albtrk2026_01
"""
from alembic import op
import sqlalchemy as sa

revision = "cover2026_01"
down_revision = "albtrk2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # release-group de MusicBrainz del que se bajó la imagen. Es la clave para
    # re-consultar la licencia en CAA sin repetir la búsqueda por nombre.
    op.add_column("albums", sa.Column("cover_mbid", sa.String(length=64), nullable=True))
    # Licencia TAL COMO la declara el uploader en CAA. NULL = no consultada
    # todavía; nunca se rellena con una suposición.
    op.add_column("albums", sa.Column("cover_license", sa.String(length=64), nullable=True))
    # caa | manual — de dónde vino el fichero.
    op.add_column("albums", sa.Column("cover_source", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("albums", "cover_source")
    op.drop_column("albums", "cover_license")
    op.drop_column("albums", "cover_mbid")
