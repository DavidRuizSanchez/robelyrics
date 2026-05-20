"""Cimientos editoriales post-muerte de Robe.

Cubre:
  - Tabla `persons` y `band_memberships` (knowledge graph)
  - `posts`: campos para imagen con atribución, scheduling (cap 2/sem) y
    tracking de newsletter on-publish
  - `albums`: release_date para aniversarios automáticos
  - `news_source_runs`: observabilidad del scraper
  - Extiende ck_kind y ck_status de posts para nuevos tipos (spotlight,
    evergreen, album-anniversary) y estado scheduled
  - Extiende ck de seo_templates.entity_type para soportar 'person'

Revision ID: e1a2b3c4d5e6
Revises: 5ee24c23d924
Create Date: 2026-05-19 14:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a2b3c4d5e6"
down_revision: str | None = "5ee24c23d924"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----- albums: fecha exacta de lanzamiento para aniversarios -----
    op.add_column("albums", sa.Column("release_date", sa.Date(), nullable=True))
    op.add_column(
        "albums",
        sa.Column("release_date_source", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_albums_release_date",
        "albums",
        ["release_date"],
        postgresql_where=sa.text("release_date IS NOT NULL"),
    )

    # ----- posts: imagen con atribución + scheduling + newsletter tracking -----
    op.add_column(
        "posts",
        sa.Column("hero_image_attribution", sa.Text(), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("hero_image_license", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("hero_image_source_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column(
            "newsletter_dispatched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_posts_scheduled_for",
        "posts",
        ["scheduled_for"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.create_index(
        "ix_posts_newsletter_dispatched_at",
        "posts",
        ["newsletter_dispatched_at"],
    )

    # Extender ck_posts_kind: añadimos spotlight, evergreen, album-anniversary
    op.drop_constraint("ck_posts_kind", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_kind",
        "posts",
        "kind IN ('editorial', 'news', 'anniversary', 'spotlight', "
        "'evergreen', 'album-anniversary')",
    )

    # Extender ck_posts_status: añadimos scheduled
    op.drop_constraint("ck_posts_status", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_status",
        "posts",
        "status IN ('draft', 'pending_review', 'approved', 'scheduled', "
        "'published', 'rejected')",
    )

    # ----- seo_templates: aceptar entity_type='person' -----
    op.drop_constraint(
        "ck_seo_templates_entity_type", "seo_templates", type_="check"
    )
    op.create_check_constraint(
        "ck_seo_templates_entity_type",
        "seo_templates",
        "entity_type IN ('artist', 'album', 'song', 'person')",
    )

    # ----- persons -----
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("full_name", sa.String(length=256), nullable=False),
        sa.Column("stage_name", sa.String(length=128), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("death_date", sa.Date(), nullable=True),
        sa.Column("birth_place", sa.String(length=200), nullable=True),
        sa.Column("bio_short", sa.Text(), nullable=True),
        sa.Column("wikipedia_url", sa.String(length=500), nullable=True),
        sa.Column("wikidata_id", sa.String(length=20), nullable=True),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("image_attribution", sa.Text(), nullable=True),
        sa.Column("image_license", sa.String(length=64), nullable=True),
        sa.Column("image_source_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_persons_stage_name", "persons", ["stage_name"])
    op.create_index("ix_persons_wikidata_id", "persons", ["wikidata_id"])

    # ----- band_memberships (N:M Person↔Artist con role + era) -----
    op.create_table(
        "band_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "person_id",
            sa.Integer(),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artist_id",
            sa.Integer(),
            sa.ForeignKey("artists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("era", sa.String(length=64), nullable=True),
        sa.Column("is_founder", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "person_id",
            "artist_id",
            "role",
            "era",
            name="uq_band_memberships_person_artist_role_era",
        ),
    )
    op.create_index(
        "ix_band_memberships_person", "band_memberships", ["person_id"]
    )
    op.create_index(
        "ix_band_memberships_artist", "band_memberships", ["artist_id"]
    )

    # ----- news_source_runs (observabilidad del scraper) -----
    op.create_table(
        "news_source_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "items_inserted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "items_scheduled", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "items_published", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_news_source_runs_started_at",
        "news_source_runs",
        ["started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_source_runs_started_at", table_name="news_source_runs")
    op.drop_table("news_source_runs")

    op.drop_index("ix_band_memberships_artist", table_name="band_memberships")
    op.drop_index("ix_band_memberships_person", table_name="band_memberships")
    op.drop_table("band_memberships")

    op.drop_index("ix_persons_wikidata_id", table_name="persons")
    op.drop_index("ix_persons_stage_name", table_name="persons")
    op.drop_table("persons")

    op.drop_constraint(
        "ck_seo_templates_entity_type", "seo_templates", type_="check"
    )
    op.create_check_constraint(
        "ck_seo_templates_entity_type",
        "seo_templates",
        "entity_type IN ('artist', 'album', 'song')",
    )

    op.drop_constraint("ck_posts_status", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_status",
        "posts",
        "status IN ('draft', 'pending_review', 'approved', 'published', 'rejected')",
    )

    op.drop_constraint("ck_posts_kind", "posts", type_="check")
    op.create_check_constraint(
        "ck_posts_kind",
        "posts",
        "kind IN ('editorial', 'news', 'anniversary')",
    )

    op.drop_index("ix_posts_newsletter_dispatched_at", table_name="posts")
    op.drop_index("ix_posts_scheduled_for", table_name="posts")
    op.drop_column("posts", "newsletter_dispatched_at")
    op.drop_column("posts", "scheduled_for")
    op.drop_column("posts", "hero_image_source_url")
    op.drop_column("posts", "hero_image_license")
    op.drop_column("posts", "hero_image_attribution")

    op.drop_index("ix_albums_release_date", table_name="albums")
    op.drop_column("albums", "release_date_source")
    op.drop_column("albums", "release_date")
