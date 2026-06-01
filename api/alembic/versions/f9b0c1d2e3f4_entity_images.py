"""Campos de imagen en artists, themes, places, concepts.

Clona el patrón de `persons` para que toda entidad pueda tener imagen
ilustrativa con atribución (foto CC real o arte IA), cumpliendo el estándar.

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-01 15:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9b0c1d2e3f4"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("artists", "themes", "places", "concepts")


def upgrade() -> None:
    for t in _TABLES:
        op.add_column(t, sa.Column("image_url", sa.String(length=1024), nullable=True))
        op.add_column(t, sa.Column("image_attribution", sa.Text(), nullable=True))
        op.add_column(t, sa.Column("image_license", sa.String(length=64), nullable=True))
        op.add_column(t, sa.Column("image_source_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    for t in _TABLES:
        op.drop_column(t, "image_source_url")
        op.drop_column(t, "image_license")
        op.drop_column(t, "image_attribution")
        op.drop_column(t, "image_url")
