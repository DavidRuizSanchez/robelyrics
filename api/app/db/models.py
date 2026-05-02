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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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
    fetched_at: Mapped[datetime] = mapped_column(
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
