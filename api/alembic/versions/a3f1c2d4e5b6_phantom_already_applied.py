"""Placeholder para la revisión a3f1c2d4e5b6 que la BD declara aplicada
pero cuyo fichero de migración nunca se commiteó al repo.

La BD ya contiene las tablas que esta revisión creó (`seo_templates`,
`email_verifications`, `terms_acceptances`) y la cadena de alembic apunta a
ella como down_revision de `b7e9f1c4a2d3_revoked_tokens`. Sin este archivo,
`alembic` falla con KeyError al cargar el mapa de revisiones.

Upgrade y downgrade son no-ops idempotentes: si alguien levanta la BD desde
cero, el resto de migraciones nuevas (ej. Fase 2 taxonomías) seguirán
funcionando porque están abajo en la cadena.

Revision ID: a3f1c2d4e5b6
Revises: 567cb06d73eb
Create Date: 2026-04-30 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a3f1c2d4e5b6"
down_revision: str | None = "567cb06d73eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: las tablas (seo_templates, email_verifications, terms_acceptances)
    # ya existen en cualquier entorno donde el `alembic_version` apunte aquí.
    # En entornos vírgenes, una migración posterior dedicada las creará en
    # caso necesario.
    pass


def downgrade() -> None:
    pass
