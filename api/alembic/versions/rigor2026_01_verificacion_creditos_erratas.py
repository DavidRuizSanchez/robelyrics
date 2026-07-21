"""Vuelco editorial de rigor: proveniencia de letra + autoría + verificación + erratas.

Añade la fundación del Motor de Consenso de Verificación (MCV) y del modelo de
autoría, a partir del feedback de fans:
  - songs: proveniencia de la letra (lyrics_source/verified_at/confidence) y
    primera aparición canónica (original_album_slug/original_year).
  - song_credits: autoría (letra/música/adaptación/poema_original) — resuelve la
    atribución de poemas de Manolo Chinato musicados por Robe.
  - verification_records: traza persistente de cada verificación multi-fuente.
  - errata_reports: cola de erratas de fans (auto-resueltas por el MCV o al humano).

Revision ID: rigor2026_01
Revises: bc546b48786d
Create Date: 2026-07-21 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "rigor2026_01"
down_revision: str | None = "bc546b48786d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- songs: proveniencia de letra + primera aparición canónica ---
    op.add_column(
        "songs",
        sa.Column(
            "lyrics_source",
            sa.String(length=16),
            nullable=False,
            server_default="genius",
        ),
    )
    op.add_column("songs", sa.Column("lyrics_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("songs", sa.Column("lyrics_confidence", sa.Float(), nullable=True))
    op.add_column("songs", sa.Column("original_album_slug", sa.String(length=256), nullable=True))
    op.add_column("songs", sa.Column("original_year", sa.Integer(), nullable=True))

    # --- song_credits ---
    op.create_table(
        "song_credits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "song_id",
            sa.Integer(),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sa.Integer(),
            sa.ForeignKey("persons.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("credit_role", sa.String(length=24), nullable=False),
        sa.Column("credited_name", sa.String(length=200), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("song_id", "credit_role", "credited_name", name="uq_song_credits_song_role_name"),
    )
    op.create_index("ix_song_credits_song", "song_credits", ["song_id"])

    # --- verification_records ---
    op.create_table(
        "verification_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("claim_kind", sa.String(length=24), nullable=False),
        sa.Column("claim_key", sa.String(length=256), nullable=False),
        sa.Column(
            "song_id",
            sa.Integer(),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sources", JSONB(), nullable=False, server_default="[]"),
        sa.Column("auto_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reverted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("claim_kind", "claim_key", name="uq_verification_claim"),
    )
    op.create_index("ix_verification_kind", "verification_records", ["claim_kind"])
    op.create_index("ix_verification_verdict", "verification_records", ["verdict"])
    op.create_index("ix_verification_records_song_id", "verification_records", ["song_id"])

    # --- errata_reports ---
    op.create_table(
        "errata_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(length=24), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("field", sa.String(length=120), nullable=True),
        sa.Column("reported_wrong", sa.Text(), nullable=True),
        sa.Column("suggested_right", sa.Text(), nullable=True),
        sa.Column("reporter", sa.String(length=120), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column(
            "verification_id",
            sa.Integer(),
            sa.ForeignKey("verification_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_errata_status", "errata_reports", ["status"])
    op.create_index("ix_errata_target", "errata_reports", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_errata_target", table_name="errata_reports")
    op.drop_index("ix_errata_status", table_name="errata_reports")
    op.drop_table("errata_reports")

    op.drop_index("ix_verification_records_song_id", table_name="verification_records")
    op.drop_index("ix_verification_verdict", table_name="verification_records")
    op.drop_index("ix_verification_kind", table_name="verification_records")
    op.drop_table("verification_records")

    op.drop_index("ix_song_credits_song", table_name="song_credits")
    op.drop_table("song_credits")

    op.drop_column("songs", "original_year")
    op.drop_column("songs", "original_album_slug")
    op.drop_column("songs", "lyrics_confidence")
    op.drop_column("songs", "lyrics_verified_at")
    op.drop_column("songs", "lyrics_source")
