"""Amplía el CHECK de seo_templates.entity_type con las taxonomías.

`seo_content` no tiene CHECK en entity_type (solo lo restringe la app), así
que admite 'theme'/'place'/'concept' sin tocar nada. Pero `seo_templates`
sí tiene `ck_seo_templates_entity_type` limitado a artist/album/song/person.
Lo ampliamos para que el sistema de plantillas SEO pueda cubrir también las
páginas de taxonomía.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-20 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_seo_templates_entity_type", "seo_templates", type_="check"
    )
    op.create_check_constraint(
        "ck_seo_templates_entity_type",
        "seo_templates",
        "entity_type IN ('artist', 'album', 'song', 'person', "
        "'theme', 'place', 'concept')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_seo_templates_entity_type", "seo_templates", type_="check"
    )
    op.create_check_constraint(
        "ck_seo_templates_entity_type",
        "seo_templates",
        "entity_type IN ('artist', 'album', 'song', 'person')",
    )
