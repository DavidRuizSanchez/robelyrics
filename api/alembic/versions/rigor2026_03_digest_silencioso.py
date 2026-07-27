"""Digest que solo suena si hay algo que hacer + traza de auto-arreglo.

Tres piezas:
  - verification_records.applied_at: cuándo se aplicó DE VERDAD la corrección
    (checked_at se re-sella cada noche, y por eso el digest repetía siempre las
    mismas auto-correcciones como si fueran nuevas).
  - errata_reports.notified_at: última vez que la errata salió en un digest.
  - notification_digests: firma del último envío por tipo, para no mandar dos
    mañanas seguidas exactamente lo mismo.

Backfill: las verificaciones ya aplicadas heredan checked_at como applied_at, así
el primer digest tras la migración no las anuncia como recién aplicadas.

Revision ID: rigor2026_03
Revises: rigor2026_02
Create Date: 2026-07-27 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "rigor2026_03"
down_revision: str | None = "rigor2026_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verification_records",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "errata_reports",
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE verification_records SET applied_at = checked_at WHERE auto_applied IS TRUE"
    )
    op.create_table(
        "notification_digests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notification_digests_kind", "notification_digests", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_notification_digests_kind", table_name="notification_digests")
    op.drop_table("notification_digests")
    op.drop_column("errata_reports", "notified_at")
    op.drop_column("verification_records", "applied_at")
