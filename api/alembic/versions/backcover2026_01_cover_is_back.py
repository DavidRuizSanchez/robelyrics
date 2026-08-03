"""albums.cover_is_back — distinguir una contraportada de una portada

Revision ID: backcover2026_01
Revises: cover2026_01
Create Date: 2026-08-03

«Tú en tu casa, nosotros en la hoguera» era el único disco sin imagen, y no por
descuido: su portada original no circula por ningún sitio —lo que Cover Art
Archive sirve como tal es en realidad la de «Rock transgresivo»— y el JPG que
había puesto era la CONTRAPORTADA, que se estaba publicando con
`alt="Portada de…"`. Se retiró por eso.

La trasera es material auténtico del disco (se lee el tracklist y «© 1990 AVISPA
· Diseño de portada: Rafael Gallego»), así que se puede enseñar. Lo que no se
puede es llamarla portada. Este flag deja que la página muestre la imagen
diciendo lo que es.
"""
from alembic import op
import sqlalchemy as sa

revision = "backcover2026_01"
down_revision = "cover2026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "albums",
        sa.Column("cover_is_back", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("albums", "cover_is_back")
