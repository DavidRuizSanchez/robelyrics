"""Monitor de cambios del sitio: pasadas, última foto por URL y cambios.

Petición de David (26-10-2026): avisar cuando cambia el title, la description,
los headings, el contenido, el robots, el canonical o el status de cualquier
página. Ver `app/services/page_monitor.py`.

Revision ID: monitor2026_01
Revises: corpus2026_02
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "monitor2026_01"
down_revision: str | None = "corpus2026_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "page_monitor_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("urls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("changed_urls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("baseline", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("global_event", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "page_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("path", sa.String(500), nullable=False, unique=True),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("final_url", sa.Text, nullable=False),
        sa.Column("cadena", JSONB, nullable=False, server_default="[]"),
        sa.Column("ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("campos", JSONB, nullable=False, server_default="{}"),
        sa.Column("in_sitemap", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "page_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer,
                  sa.ForeignKey("page_monitor_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("campo", sa.String(32), nullable=False),
        sa.Column("severidad", sa.String(16), nullable=False),
        sa.Column("antes", sa.Text),
        sa.Column("despues", sa.Text),
        sa.Column("detalle", JSONB, nullable=False, server_default="{}"),
        sa.Column("causa", sa.Text),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_page_changes_run_id", "page_changes", ["run_id"])
    op.create_index("ix_page_changes_path", "page_changes", ["path"])
    op.create_index("ix_page_changes_seen_detected", "page_changes", ["seen_at", "detected_at"])


def downgrade() -> None:
    op.drop_table("page_changes")
    op.drop_table("page_snapshots")
    op.drop_table("page_monitor_runs")
