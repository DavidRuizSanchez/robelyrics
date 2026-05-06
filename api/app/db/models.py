"""Modelos SQLAlchemy de RobeLyrics.

Cobertura:
  - Catálogo: Artist, Album, Song, Line, Chunk
  - Auth:     User
  - Fase 0:   InterpretationSource, SongInterpretation

FTS:
  - Line.text_tsv y Song.lyrics_clean_tsv son columnas tsvector mantenidas
    por triggers definidos en la migración inicial. No se escriben desde la
    aplicación.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #
class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # extremoduro | robe
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active_years: Mapped[str | None] = mapped_column(String(32))  # ej. "1989-2014"

    albums: Mapped[list["Album"]] = relationship(
        back_populates="artist", cascade="all, delete-orphan"
    )


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("artist_id", "slug", name="uq_albums_artist_slug"),
        Index("ix_albums_artist_year", "artist_id", "year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="studio")
    track_count: Mapped[int | None] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(String(512))

    artist: Mapped[Artist] = relationship(back_populates="albums")
    songs: Mapped[list["Song"]] = relationship(
        back_populates="album", cascade="all, delete-orphan"
    )


class Song(Base):
    __tablename__ = "songs"
    __table_args__ = (
        UniqueConstraint("album_id", "slug", name="uq_songs_album_slug"),
        Index("ix_songs_genius_id", "genius_id", unique=True),
        Index(
            "ix_songs_lyrics_clean_tsv",
            "lyrics_clean_tsv",
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"), nullable=False
    )
    track_number: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    lyrics_raw: Mapped[str | None] = mapped_column(Text)
    lyrics_clean: Mapped[str | None] = mapped_column(Text)
    lyrics_clean_tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    genius_id: Mapped[int | None] = mapped_column(Integer)
    genius_url: Mapped[str | None] = mapped_column(String(512))
    youtube_id: Mapped[str | None] = mapped_column(String(32))
    youtube_match_quality: Mapped[str | None] = mapped_column(String(16))  # official|topic|search|manual

    album: Mapped[Album] = relationship(back_populates="songs")
    lines: Mapped[list["Line"]] = relationship(
        back_populates="song",
        cascade="all, delete-orphan",
        order_by="Line.line_index",
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="song", cascade="all, delete-orphan"
    )
    interpretation: Mapped["SongInterpretation | None"] = relationship(
        back_populates="song", uselist=False, cascade="all, delete-orphan"
    )


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = (
        UniqueConstraint("song_id", "line_index", name="uq_lines_song_index"),
        Index(
            "ix_lines_text_tsv",
            "text_tsv",
            postgresql_using="gin",
        ),
        Index(
            "ix_lines_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stanza_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    start_seconds: Mapped[int | None] = mapped_column(Integer)  # timestamp dentro del audio (lrclib)

    song: Mapped[Song] = relationship(back_populates="lines")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("song_id", "start_line_index", name="uq_chunks_song_start"),
        CheckConstraint(
            "end_line_index >= start_line_index",
            name="ck_chunks_index_order",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    song: Mapped[Song] = relationship(back_populates="chunks")


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmailVerification(Base):
    """Token de verificación de email enviado al registrarse o cambiar email."""

    __tablename__ = "email_verifications"
    __table_args__ = (
        Index("ix_email_verifications_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RevokedToken(Base):
    """JWTs revocados (logout, force-logout). El claim `jti` del token se
    busca aquí en cada request autenticado: si está, 401.

    Una entrada por token revocado. `expires_at` permite limpiar entradas
    cuyo TTL ya pasó (cron periódico opcional, no urgente con TTL ≤7d).
    """

    __tablename__ = "revoked_tokens"
    __table_args__ = (
        Index("ix_revoked_tokens_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TermsAcceptance(Base):
    """Histórico de aceptaciones de términos por user. Una fila por (user, version)."""

    __tablename__ = "terms_acceptances"
    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_terms_acceptances_user_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


# --------------------------------------------------------------------------- #
# Fase 0 — Knowledge Base
# --------------------------------------------------------------------------- #
class InterpretationSource(Base):
    """Pieza de fan-content recuperada (post Reddit, video YT, hilo de foro, etc.)."""

    __tablename__ = "interpretation_sources"
    __table_args__ = (
        UniqueConstraint("kind", "url", name="uq_interp_sources_kind_url"),
        Index("ix_interp_sources_kind", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # kind ∈ {reddit, youtube_transcript, youtube_comment, forum, blog, genius_annotation, book, thesis}
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(256))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_raw: Mapped[str | None] = mapped_column(Text)
    content_clean: Mapped[str | None] = mapped_column(Text)
    referenced_song_ids: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    quality_score: Mapped[float | None] = mapped_column()
    # Si es True, esta fuente NO se usa para destilar interpretaciones fan
    # (rama privada con citation obligatoria). Solo el generador de contenido SEO
    # de la capa pública la consume. Útil para prensa comercial (Mondo Sonoro,
    # Efe Eme, Rockdelux, El País, etc.) cuyo tono mezcla redacción y cita y
    # rompe la regla de citation pura del destilador.
    for_seo_only: Mapped[bool] = mapped_column(default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SeoContent(Base):
    """Contenido SEO editorial generado para una entidad pública (artist/album/song).

    `body_md` es el artículo en Markdown (~1500-3000 palabras dependiendo de la
    entidad). `published=False` significa que la página pública correspondiente
    devuelve 404 — permite generar masivamente con LLM y publicar solo lo
    revisado.
    """

    __tablename__ = "seo_content"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", name="uq_seo_content_entity"),
        Index("ix_seo_content_published", "published"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # artist|album|song
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(String(256))
    meta_description: Mapped[str | None] = mapped_column(String(512))
    h1: Mapped[str | None] = mapped_column(String(256))
    schema_jsonld: Mapped[dict | None] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False, default="gpt-4o")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published: Mapped[bool] = mapped_column(default=False, nullable=False)


class SeoTemplate(Base):
    """Plantilla parametrizable para los campos SEO (title, description, h1) por
    tipo de entidad y kind opcional.

    Ejemplo:
      entity_type='album', kind='studio', field='title',
      template='{{title}} ({{year}}) — {{artist}} | Entre Interiores'

    Resolución: si SeoContent.<field> es NULL, se aplica la plantilla más
    específica que coincida (entity_type, kind exacto). Si no existe, fallback
    a (entity_type, kind=NULL). Variables disponibles según entity_type.
    """

    __tablename__ = "seo_templates"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('artist', 'album', 'song')",
            name="ck_seo_templates_entity_type",
        ),
        CheckConstraint(
            "field IN ('title', 'description', 'h1')",
            name="ck_seo_templates_field",
        ),
        Index(
            "uq_seo_templates_entity_kind_field",
            "entity_type",
            text("COALESCE(kind, '')"),
            "field",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(16), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SongInterpretation(Base):
    """Destilado fan por canción. Una fila por canción (max).

    Estructura del JSONB `payload` (validada por Pydantic en la app):
      {
        "themes": [str, ...],
        "key_metaphors": [{"phrase": str, "meaning": str, "source_ids": [int, ...]}],
        "references": [{"type": "biographical|intertextual|cultural", "description": str}],
        "fan_consensus": str
      }
    """

    __tablename__ = "song_interpretations"

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)  # high|medium|low
    source_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    distilled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_song_interpretations_confidence",
        ),
    )

    song: Mapped[Song] = relationship(back_populates="interpretation")
