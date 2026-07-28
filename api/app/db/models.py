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

from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
    # Imagen ilustrativa (foto CC real para concretas; arte IA para abstractas).
    image_url: Mapped[str | None] = mapped_column(String(1024))
    image_attribution: Mapped[str | None] = mapped_column(Text)
    image_license: Mapped[str | None] = mapped_column(String(64))
    image_source_url: Mapped[str | None] = mapped_column(String(1024))

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
    # Fecha exacta de lanzamiento. NULL hasta que el script de bootstrap la
    # rellena vía Wikidata/Wikipedia. Necesaria para aniversarios automáticos
    # en el día exacto del lanzamiento.
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    release_date_source: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
    # Proveniencia de la letra. La fuente de verdad ya NO es solo Genius: el
    # Motor de Consenso de Verificación (services/consensus.py) contrasta la letra
    # contra varias fuentes y, si hay consenso, la corrige. `lyrics_source` indica
    # de dónde salió la versión vigente; `lyrics_confidence` es la confianza del
    # consenso (0-1). Ver data/lyric_overrides.yaml (verdad curada que manda sobre
    # Genius en la re-ingesta).
    lyrics_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="genius", server_default="genius"
    )  # genius | lrclib | consensus | override | manual
    lyrics_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lyrics_confidence: Mapped[float | None] = mapped_column(Float)
    # Primera aparición canónica de estudio. La relación canción→álbum es 1→N que
    # la BD no modela (una canción puede estar en el debut y en recopilatorios);
    # estos campos fijan la verdad canónica (disco+año) que decide catalog_consensus,
    # para que fact_check no la tome del recopilatorio que asignó Genius.
    original_album_slug: Mapped[str | None] = mapped_column(String(256))
    original_year: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    genius_id: Mapped[int | None] = mapped_column(Integer)
    genius_url: Mapped[str | None] = mapped_column(String(512))
    youtube_id: Mapped[str | None] = mapped_column(String(32))
    youtube_match_quality: Mapped[str | None] = mapped_column(String(16))  # official|topic|search|manual
    # Metadatos del vídeo (para el VideoObject de schema.org). Los rellena
    # `match_youtube --enrich` vía YouTube Data API (videos.list).
    youtube_title: Mapped[str | None] = mapped_column(String(300))
    youtube_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    youtube_duration_sec: Mapped[int | None] = mapped_column(Integer)
    # Carátula propia para singles/EPs/clips con artwork distinto del álbum.
    # Si NULL, el frontend cae a album.cover_url. Ejemplos: "Yacuzi" tiene
    # arte de videoclip, "Jesucristo García" portada propia del 1989, etc.
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

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
    themes: Mapped[list["Theme"]] = relationship(
        secondary="song_themes", back_populates="songs"
    )
    places: Mapped[list["Place"]] = relationship(
        secondary="song_places", back_populates="songs"
    )
    concepts: Mapped[list["Concept"]] = relationship(
        secondary="song_concepts", back_populates="songs"
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


class SongCredit(Base):
    """Autoría de una canción: quién firma la letra, la música, la adaptación o el
    poema original. Nace del feedback de fans: atribuíamos a Robe textos que son
    poemas de otros musicados por él (p.ej. "Ama, ama y ensancha el alma" es un
    poema de Manolo Chinato). Sin esta tabla la autoría se asumía 100% por herencia
    Song→Album→Artist y era irrepresentable un crédito compartido.

    La puebla `scripts/verify/authorship_consensus.py` (consenso multi-fuente:
    Wikipedia/Wikidata, anotaciones de Genius verificadas, blogs, "respuestas del
    Robe", datos curados) o el seed desde `data/song_credits.yaml`. `person_id` es
    opcional: para autores sin ficha de persona se usa `credited_name`.
    """

    __tablename__ = "song_credits"
    __table_args__ = (
        UniqueConstraint(
            "song_id", "credit_role", "credited_name",
            name="uq_song_credits_song_role_name",
        ),
        Index("ix_song_credits_song", "song_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", ondelete="SET NULL"), nullable=True
    )
    # letra | musica | adaptacion | poema_original | arreglos | colaboracion
    credit_role: Mapped[str] = mapped_column(String(24), nullable=False)
    credited_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text)
    # Proveniencia del crédito (para trazabilidad/auditoría del consenso).
    source: Mapped[str | None] = mapped_column(String(24))  # consensus | override | manual
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    song: Mapped[Song] = relationship()
    person: Mapped[Person | None] = relationship()


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
    # Timestamp para invalidar todos los JWT cuyo `iat` sea anterior. Lo
    # actualizamos al hacer reset de contraseña → cierre de sesión global.
    tokens_invalid_before: Mapped[datetime | None] = mapped_column(
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


class PasswordReset(Base):
    """Token de password reset enviado al pulsar 'olvidé mi contraseña'.
    TTL corto (30 min) y single-use por seguridad. Re-issue invalida los
    tokens previos del mismo user (ver routers/auth.py)."""

    __tablename__ = "password_resets"
    __table_args__ = (
        Index("ix_password_resets_user", "user_id"),
        Index("ix_password_resets_expires", "expires_at"),
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
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
    # Entidades mencionadas (personas, lugares, bandas, discos). El frontend
    # las renderiza como schema.org `mentions` con @id local cuando hay match
    # en el corpus, o @id Wikidata si no.
    entities: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # KW objetivo de la página + secundarias (research por entidad) y el outline
    # (estructura de headings) que generó el motor profundo. `sources_count` = nº
    # de fuentes del corpus que alimentaron la página (cobertura, para el panel).
    target_keyword: Mapped[str | None] = mapped_column(String(160), nullable=True)
    secondary_keywords: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    outline: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    sources_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
            "entity_type IN ('artist', 'album', 'song', 'person', "
            "'theme', 'place', 'concept')",
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


# --- Fase 2: taxonomías SEO (temas, lugares, conceptos) ---------------------
#
# Estas tres taxonomías alimentan hubs públicos `/temas/{slug}`,
# `/lugares/{slug}` y `/conceptos/{slug}` que recogen canciones por motivo
# compartido. La relación N:M con Song permite enlazado horizontal entre
# canciones de discos/épocas distintas que tocan el mismo tema.


class Theme(Base):
    __tablename__ = "themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    songs: Mapped[list[Song]] = relationship(
        secondary="song_themes", back_populates="themes"
    )
    # Imagen ilustrativa (arte IA con la estética del proyecto para abstractos).
    image_url: Mapped[str | None] = mapped_column(String(1024))
    image_attribution: Mapped[str | None] = mapped_column(Text)
    image_license: Mapped[str | None] = mapped_column(String(64))
    image_source_url: Mapped[str | None] = mapped_column(String(1024))


class SongTheme(Base):
    __tablename__ = "song_themes"

    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    theme_id: Mapped[int] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False, default=1.0)


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    geo_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    geo_lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    songs: Mapped[list[Song]] = relationship(
        secondary="song_places", back_populates="places"
    )
    # Imagen ilustrativa (foto CC real del lugar vía Wikidata/Wikimedia).
    image_url: Mapped[str | None] = mapped_column(String(1024))
    image_attribution: Mapped[str | None] = mapped_column(Text)
    image_license: Mapped[str | None] = mapped_column(String(64))
    image_source_url: Mapped[str | None] = mapped_column(String(1024))


class SongPlace(Base):
    __tablename__ = "song_places"

    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    place_id: Mapped[int] = mapped_column(
        ForeignKey("places.id", ondelete="CASCADE"), primary_key=True
    )
    context: Mapped[str | None] = mapped_column(Text)


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    songs: Mapped[list[Song]] = relationship(
        secondary="song_concepts", back_populates="concepts"
    )
    # Imagen ilustrativa (arte IA con la estética del proyecto para abstractos).
    image_url: Mapped[str | None] = mapped_column(String(1024))
    image_attribution: Mapped[str | None] = mapped_column(Text)
    image_license: Mapped[str | None] = mapped_column(String(64))
    image_source_url: Mapped[str | None] = mapped_column(String(1024))


class SongConcept(Base):
    __tablename__ = "song_concepts"

    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )


class Band(Base):
    """Grupo / sello afín al universo Robe-Extremoduro (bandas amigas como
    Fito & Fitipaldis, Marea, Platero y Tú, The Flying Rebollos, o el sello
    El Dromedario Records). Espejo de `Person` pero para grupos: NO está en el
    corpus de canciones (eso es solo Extremoduro/Robe), es ampliación del
    knowledge graph. Su seo_content lleva entity_type='band'.
    """

    __tablename__ = "bands"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="band")  # band|label
    founded_year: Mapped[int | None] = mapped_column(Integer)
    dissolved_year: Mapped[int | None] = mapped_column(Integer)
    bio_short: Mapped[str | None] = mapped_column(Text)
    bio_long: Mapped[str | None] = mapped_column(Text)          # artículo Wikipedia completo (contexto generación)
    wikipedia_url: Mapped[str | None] = mapped_column(String(500))
    wikidata_id: Mapped[str | None] = mapped_column(String(20), index=True)
    image_url: Mapped[str | None] = mapped_column(String(1024))
    image_attribution: Mapped[str | None] = mapped_column(Text)
    image_license: Mapped[str | None] = mapped_column(String(64))
    image_source_url: Mapped[str | None] = mapped_column(String(1024))
    members: Mapped[list | None] = mapped_column(JSONB)          # [{name, role}]
    related_note: Mapped[str | None] = mapped_column(Text)       # vínculo con Robe/Extremoduro
    relation_type: Mapped[str | None] = mapped_column(String(16))  # 'family' | 'friend' | None
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RelatedVideo(Base):
    """Vídeo de YouTube relacionado (colaboración, entrevista, vídeo oficial)
    anclado a una o más entidades del universo Robe vía RelatedVideoEntity.

    NO es el vídeo canónico de una canción (eso es Song.youtube_id): aquí
    caben entrevistas, colaboraciones de Robe con otros artistas, vídeos
    oficiales de terceros que le involucran, etc. Sembrado desde
    data/related_videos.yaml (idempotente por youtube_id).
    """

    __tablename__ = "related_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # collaboration|interview|official|live
    upload_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    entities: Mapped[list[RelatedVideoEntity]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class RelatedVideoEntity(Base):
    """Ancla un RelatedVideo a una entidad por (entity_type, entity_slug). Sin
    FK a las tablas de entidad para poder anclar a cualquier tipo (person,
    artist, band, song) sin acoplar el esquema."""

    __tablename__ = "related_video_entities"
    __table_args__ = (
        UniqueConstraint(
            "video_id",
            "entity_type",
            "entity_slug",
            name="uq_related_video_entity",
        ),
        Index(
            "ix_related_video_entities_type_slug",
            "entity_type",
            "entity_slug",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(
        ForeignKey("related_videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # person|artist|band|song
    entity_slug: Mapped[str] = mapped_column(String(160), nullable=False)

    video: Mapped[RelatedVideo] = relationship(back_populates="entities")


class Book(Base):
    """Libro del universo Extremoduro/Robe (sección /libros): biografías
    (De Profundis, Talento innato), ensayos (Poesía básica), monográficos
    (Cuaderno Efe Eme) y la única novela de Robe (El viaje íntimo de la
    locura). NO está en el corpus de canciones: es ampliación del knowledge
    graph + futura vía de afiliación. Metadatos bibliográficos VERIFICABLES,
    sembrados desde data/books.yaml (curados a mano, nunca inventados ni
    generados por LLM). `buy_links` queda preparado para los enlaces de
    compra/afiliado, que de momento NO se renderizan.
    """

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(300))
    authors: Mapped[list | None] = mapped_column(JSONB)          # ["Javier Menéndez Flores"]
    year: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str | None] = mapped_column(String(200))
    isbn: Mapped[str | None] = mapped_column(String(20))
    pages: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="es")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="biografia")
    # biografia|ensayo|novela|monografico|poesia
    availability: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    # new|secondhand|out_of_print
    cover_url: Mapped[str | None] = mapped_column(String(1024))
    cover_attribution: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)            # sinopsis corta (listado + meta)
    body_md: Mapped[str | None] = mapped_column(Text)            # ficha larga (markdown, H2)
    buy_links: Mapped[list | None] = mapped_column(JSONB)        # [{store,url,label}] — afiliados (futuro)
    about: Mapped[list | None] = mapped_column(JSONB)            # ["extremoduro","robe"] → @graph
    meta_title: Mapped[str | None] = mapped_column(String(300))
    meta_description: Mapped[str | None] = mapped_column(String(400))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConsultQuestion(Base):
    """Registro de cada pregunta hecha al consultorio "Pregúntale al viento".

    Sirve para moderación (detectar abuso/ofensas), medir coste/uso y curar
    nuevas citas a partir de lo que la gente pregunta. Una fila por pregunta.
    """

    __tablename__ = "consult_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str | None] = mapped_column(String(16))  # pragmatic | philosophical
    grounded: Mapped[bool | None] = mapped_column(Boolean)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answer_preview: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FeatureQuery(Base):
    """Registro de uso de las features de búsqueda/descubrimiento (F2.4).

    Complementa a ConsultQuestion (consultorio): captura qué buscan los usuarios en
    el buscador semántico, en "completar" y en las listas por mood, para conocer el
    uso real y qué huecos de contenido revelan las consultas. El RATIO de uso agregado
    vive en GA4 (eventos); aquí guardamos el TEXTO (que no debe ir a analytics por PII).
    """

    __tablename__ = "feature_queries"
    __table_args__ = (Index("ix_feature_queries_feature_created", "feature", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feature: Mapped[str] = mapped_column(String(24), nullable=False)  # search | complete | mood
    query: Mapped[str] = mapped_column(Text, nullable=False)
    n_results: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Fase 3: blog/noticias --------------------------------------------------


class Post(Base):
    """Entrada de blog/noticias en la web pública.

    `kind`:
      - 'editorial':         artículo manual del admin (long-form).
      - 'news':              noticia raspada de fuente externa whitelisted.
      - 'anniversary':       efeméride Robe (nacimiento/muerte). Excepción al
                             cap semanal: siempre se publica el día exacto.
      - 'album-anniversary': aniversario de lanzamiento de un disco. Misma
                             excepción al cap que `anniversary`.
      - 'spotlight':         análisis editorial de una canción del catálogo,
                             generado por rotación semanal.
      - 'evergreen':         pieza sobre una taxonomía (tema/lugar/concepto),
                             relleno cuando el resto no llega al mínimo.

    `status`:
      draft → pending_review → approved → scheduled → published (o rejected).
      `scheduled` significa "esperando hueco" cuando el cap de 2/sem ya está
      ocupado; el cron `flush_scheduled_due` lo promueve a `published` cuando
      llega su `scheduled_for`.
    Solo las publicadas se muestran en /blog y entran al sitemap.
    """

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    hero_image_url: Mapped[str | None] = mapped_column(String(1000))
    # ALT descriptivo de la imagen hero (accesibilidad + SEO). Describe la FOTO
    # real (p.ej. "Robe en directo en Villaviciosa, 2007"), no el título del post.
    hero_image_alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Atribución y licencia de la imagen (Wikimedia Commons). Renderizadas en
    # el footer del post para cumplir con la licencia (CC-BY/CC-BY-SA exigen
    # author + licencia + enlace a la fuente).
    hero_image_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    hero_image_license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hero_image_source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # URLs largas (Google News genera URLs de >500 chars).
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_name: Mapped[str | None] = mapped_column(String(200))
    meta_title: Mapped[str | None] = mapped_column(String(256))
    meta_description: Mapped[str | None] = mapped_column(String(512))
    # Keyword objetivo a la que apunta el artículo (anti-canibalización: no dos
    # posts a la misma KW). `target_keyword_slug` es la versión normalizada para
    # el índice/dedup. Lo setea `materialize_proposals` desde la propuesta.
    target_keyword: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_keyword_slug: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    # Huella estable del tema (anti-duplicados transversal). Copiada desde la
    # propuesta al materializar; ver `ContentProposal.content_key`.
    content_key: Mapped[str | None] = mapped_column(String(160), index=True)
    anniversary_year: Mapped[int | None] = mapped_column(Integer)
    # Fecha real del evento de la noticia (copiada de la propuesta al
    # materializar); permite detectar contenido caducado. Ver ContentProposal.
    event_date: Mapped[date | None] = mapped_column(Date)
    # Override del admin: publicar "sí o sí" aunque no pase el gate de calidad
    # (rigor/longitud/foco). Se mantiene el fact-check canónico. Copiado de la
    # propuesta al materializar.
    force_publish: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cuando status='scheduled', momento en que el scheduler lo publicará.
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Marca de cuándo se incluyó este post en un envío de newsletter (legacy,
    # mantenido por compatibilidad con el dispatcher diario). Para el flujo
    # newsletter-on-publish (cap 2/sem) usamos `newsletter_dispatched_at`.
    newsletter_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Idempotencia del envío de email al publicar el post. NOT NULL → ya
    # mandado, no se vuelve a enviar aunque rearranque el cron.
    newsletter_dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Entidades mencionadas (Person, MusicGroup, Place, etc.) para enriquecer
    # schema.org `mentions`. Mismo formato que SeoContent.entities.
    entities: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Vídeo embebido del post (YouTube), con metadatos REALES para el
    # VideoObject (JSON-LD): {youtube_id, title, upload_date (ISO), channel}.
    video: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Lista de vídeos (posts premium/flagship llevan varios: oficial + directo +
    # entrevista). Cada uno {youtube_id, title, upload_date, channel}. `video`
    # (arriba) se mantiene por compatibilidad = primer elemento de `videos`.
    videos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Engagement (WS B): score 0-100 de interés para un fan real y tier derivado
    # (standard|premium|flagship) que modula extensión, profundidad y multimedia.
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('editorial', 'news', 'anniversary', 'spotlight', "
            "'evergreen', 'album-anniversary')",
            name="ck_posts_kind",
        ),
        CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'scheduled', "
            "'published', 'rejected')",
            name="ck_posts_status",
        ),
    )


# --- Fase 3: newsletter -----------------------------------------------------


class Subscriber(Base):
    """Suscriptor de la newsletter de Entre Interiores.

    Doble opt-in: una fila se crea en 'pending' tras el form de suscripción y
    pasa a 'confirmed' solo después de visitar el link de confirmación que
    envía el email. La fila se conserva tras unsubscribe (compliance RGPD y
    para que reintentar suscribirse no requiera nueva doble confirmación).
    """

    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    confirm_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(40))  # footer|blog|...

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'unsubscribed', 'bounced')",
            name="ck_subscribers_status",
        ),
    )


# --- Fase 4: knowledge graph (personas + band memberships) ------------------


class Person(Base):
    """Persona del universo editorial (miembro de banda, colaborador, líder
    de grupo amigo, etc.). Independiente de `Artist` porque una persona puede
    pertenecer a varias bandas con roles distintos en eras distintas.

    `wikidata_id` (Q-ID, ej. 'Q3500822') permite enriquecer datos y emitir
    `sameAs` en JSON-LD para que Google una entidades cross-source.
    """

    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    stage_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    death_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    birth_place: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bio_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_long: Mapped[str | None] = mapped_column(Text, nullable=True)  # artículo Wikipedia completo (contexto generación)
    instruments: Mapped[list] = mapped_column(  # Wikidata P1303 [{name, wikidata_id, ...}]
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    wikipedia_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    image_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Enriquecimiento desde Wikidata. Estructura común para los 3:
    #   [{"name": str, "wikidata_id": str, "wikidata_url": str,
    #     "wikipedia_url": str | None}]
    other_bands: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    notable_works: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    occupations: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    memberships: Mapped[list["BandMembership"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class BandMembership(Base):
    """Relación N:M Person↔Artist con `role` (vocalista, guitarrista, etc.) y
    `era` (string libre tipo "1987-2014" o "Etapa Pedrá") para distinguir
    pertenencias múltiples a una misma banda en momentos distintos.
    """

    __tablename__ = "band_memberships"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "artist_id",
            "role",
            "era",
            name="uq_band_memberships_person_artist_role_era",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    era: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_founder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    person: Mapped[Person] = relationship(back_populates="memberships")
    artist: Mapped[Artist] = relationship()


# --- Observabilidad scraper -------------------------------------------------


class NewsSourceRun(Base):
    """Run del scraper de noticias. Una fila por fuente y por ejecución, para
    poder diagnosticar fuentes que dejen de funcionar (parser cambia, RSS se
    cae, etc.).
    """

    __tablename__ = "news_source_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_scheduled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_published: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# --- Banco de propuestas editoriales ----------------------------------------


class ContentProposal(Base):
    """Idea editorial en el banco de propuestas.

    El cron `generate_proposals` crea propuestas ligeras (sin body) de todo
    el catálogo; el scraper crea propuestas `kind='news'` con body ya hecho.
    El admin las valida (aprobar/rechazar) y las programa desde la pestaña
    /biblioteca/admin/blog, máximo 3 por semana. Al llegar la fecha, el
    materializador genera el body si falta y crea el `Post`.

    `status`: proposed → approved → scheduled → used (o discarded).
    """

    __tablename__ = "content_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'approved', 'scheduled', 'used', "
            "'discarded')",
            name="ck_content_proposals_status",
        ),
        CheckConstraint(
            "kind IN ('news', 'spotlight', 'evergreen', 'anniversary', "
            "'album-anniversary')",
            name="ck_content_proposals_kind",
        ),
        UniqueConstraint(
            "kind", "source_type", "source_id",
            name="uq_content_proposals_kind_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(16))  # song|theme|place|concept|album
    source_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    angle: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    meta_title: Mapped[str | None] = mapped_column(String(256))
    meta_description: Mapped[str | None] = mapped_column(String(512))
    hero_image_url: Mapped[str | None] = mapped_column(String(1000))
    hero_image_alt: Mapped[str | None] = mapped_column(Text)
    hero_image_attribution: Mapped[str | None] = mapped_column(Text)
    hero_image_license: Mapped[str | None] = mapped_column(String(64))
    hero_image_source_url: Mapped[str | None] = mapped_column(String(1000))
    # URLs largas (Google News genera URLs de >500 chars).
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_name: Mapped[str | None] = mapped_column(String(200))
    entities: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Keywords objetivo con volumen de búsqueda (DataForSEO). Estructura:
    # [{"keyword": str, "volume": int, "cpc": float|None, "competition": float|None}]
    keywords: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Keyword principal de la propuesta (la de mayor prioridad de `keywords`),
    # su volumen, si es long-tail y de qué señal viene (corpus|dataforseo|gsc).
    target_keyword: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_keyword_slug: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    search_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_longtail: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    signal_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed"
    )
    # Huella estable del tema para deduplicar entre tipos y semanas (mismo
    # patrón que `InstagramQueueItem.content_key`). P.ej. "spotlight:song_123",
    # "evergreen:<kw-slug>", "anniversary:<album-slug>_2008",
    # "news:<evento-normalizado>". La rellena el productor de la propuesta.
    content_key: Mapped[str | None] = mapped_column(String(160), index=True)
    # Fecha SUGERIDA para programar (la de la efeméride: aniversario de disco,
    # cumpleaños/muerte de Robe). Solo es una sugerencia que el panel pre-rellena;
    # `scheduled_for` sigue siendo la fecha real elegida por el admin.
    recommended_date: Mapped[date | None] = mapped_column(Date)
    # Fecha REAL del evento del que trata la noticia (concierto, festival,
    # homenaje…), SOLO si aparece explícita en la fuente (nunca inventada). Si
    # es futura, gobierna la antelación de publicación; si llega pasada, dispara
    # la caducidad (crónica o cancelación). NULL = pieza atemporal.
    event_date: Mapped[date | None] = mapped_column(Date)
    # Vídeo embebido (YouTube) con metadatos REALES para el VideoObject (JSON-LD):
    # {youtube_id, title, upload_date, channel}. Lo provee research_and_write; se
    # copia a Post.video al materializar.
    video: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Lista de vídeos (premium/flagship). Se copia a Post.videos al materializar.
    videos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Engagement (WS B): score 0-100 y tier (standard|premium|flagship).
    engagement_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Override del admin: publicar "sí o sí" saltando el gate de calidad
    # (rigor/longitud/foco); el fact-check canónico se mantiene.
    force_publish: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    scheduled_for: Mapped[date | None] = mapped_column(Date)
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Noticias agregadas + cola de Instagram ----------------------------------


class NewsItem(Base):
    """Noticia agregada del universo Robe / Extremoduro.

    El agregador (`scripts/news/aggregate.py`) descarga las fuentes de
    `data/news_sources.yaml` y guarda aquí titular + enlace + extracto breve
    + atribución (nunca el cuerpo del artículo). Es el almacén ÚNICO del que
    beben los dos consumidores:

      - blog:      filtra `policy` que incluya 'blog' → reescribe → propuestas.
      - instagram: usa todas → selecciona temas → publica enlazando al medio.

    `policy` se denormaliza de la fuente para poder filtrar sin joins.
    Las noticias con más de 7 días se purgan en cada ciclo del agregador.
    """

    __tablename__ = "news_items"
    __table_args__ = (
        CheckConstraint(
            "policy IN ('blog+ig', 'ig-only')",
            name="ck_news_items_policy",
        ),
        Index("ix_news_items_fetched_at", "fetched_at"),
        Index("ix_news_items_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(700), nullable=False, unique=True)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Medio real cuando el feed es un agregador (el <source> de Google News).
    source_medium: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(40))
    policy: Mapped[str] = mapped_column(String(16), nullable=False)
    relevance_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # True cuando el consumidor del blog ya generó una propuesta a partir de ella.
    consumed_blog: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class InstagramQueueItem(Base):
    """Post encolado para publicar en Instagram (@entreinterioresrobe).

    Cada fila es un tema del día (noticia agregada, artículo del blog o
    efeméride) ya preparado con su caption e imagen. El cron diario encola
    `POSTS_PER_DAY` items; el admin puede encolar/quitar a mano desde
    /biblioteca/admin/instagram. El cron de publicación coge el siguiente
    `pending` y lo sube vía la Graph API de Meta.

    `status`: proposed → pending → prepared → published (o failed / discarded).
    Los items `proposed` (evergreen sin noticia) esperan aprobación del admin en
    el panel antes de pasar a `pending` y entrar en la cola de publicación.

    `content_type`: news | blog | quote | ephemeris | anecdote | robe_quote.
    """

    __tablename__ = "instagram_queue"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'pending', 'prepared', 'published', "
            "'failed', 'discarded')",
            name="ck_instagram_queue_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    news_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_items.id", ondelete="SET NULL")
    )
    blog_post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL")
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Orden manual de publicación (menor = antes). Lo reordena el admin
    # arrastrando en el planner; `slot`/`day`/`created_at` quedan de desempate.
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True
    )
    # Tipo de contenido: news | blog | quote | ephemeris | anecdote | robe_quote.
    # Distingue la actualidad (news/blog) del evergreen anclado al corpus.
    content_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="news"
    )
    # Huella estable del contenido para deduplicar entre semanas (no repetir el
    # mismo verso/efeméride/cita/anécdota). P.ej. "quote:line_1234",
    # "ephemeris:album_la-ley-innata_2008", "robe_quote:<hash>".
    content_key: Mapped[str | None] = mapped_column(String(160), index=True)
    # Fecha fija de publicación para contenido con efeméride (aniversario de
    # disco, cumpleaños): si está, el item SOLO se publica ese día exacto y NO
    # entra en el goteo normal. NULL = evergreen normal (cuentagotas).
    publish_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Programación EXACTA hecha a mano desde el panel (fecha + hora). Convive con
    # `publish_on`, que es de día suelto y lo pone el generador de efemérides:
    # aquí el admin decide el momento. Si está, el item no entra en el goteo.
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Snapshot del tema (sobrevive aunque se borre la noticia / el post).
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(700))
    caption: Mapped[str | None] = mapped_column(Text)
    # Formato del post. Los cinco son lo mismo desde la cola: formas que puede
    # tomar una publicación.
    #   IMAGE    · una foto
    #   CAROUSEL · 2-10 diapositivas
    #   REELS    · vídeo propio (verso animado, sin audio)
    #   CLIP     · fragmento de vídeo de otro canal, con su sonido
    #   PRODUCT  · pieza que enseña una funcionalidad de la web
    media_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="IMAGE"
    )
    # True si el formato lo eligió una PERSONA en el panel. El repartidor
    # automático de formatos no toca los bloqueados.
    media_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Espejo de la diapositiva 0. Se conservan aunque el post sea un carrusel:
    # así el camino de foto única sigue intacto y la previsualización del panel
    # no depende de la tabla hija.
    image_url: Mapped[str | None] = mapped_column(String(700))
    image_path: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    ig_media_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    media: Mapped[list["InstagramQueueMedia"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="InstagramQueueMedia.position",
        lazy="selectin",
    )


class InstagramQueueMedia(Base):
    """Una pieza de media (imagen o vídeo) de un post de Instagram.

    Un post de foto única tiene exactamente una fila (posición 0); un carrusel,
    entre 2 y 10. Se modela como tabla hija y no como JSONB porque el panel
    reordena y regenera diapositivas sueltas mientras el cron puede estar
    leyendo: con un array habría que reescribirlo entero en cada cambio.
    """

    __tablename__ = "instagram_queue_media"
    __table_args__ = (
        CheckConstraint("kind IN ('image','video')", name="ck_iqm_kind"),
        # En Postgres esta restricción se crea DEFERRABLE INITIALLY DEFERRED (ver
        # la migración igmedia2026_01): reordenar N diapositivas colisiona a
        # mitad del bucle si se comprueba fila a fila. Aquí no se declara porque
        # SQLite —que es lo que usan los tests— no entiende DEFERRABLE.
        UniqueConstraint(
            "item_id", "position", name="uq_instagram_queue_media_item_pos"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_queue.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="image")
    # Layout que la generó: cover | verse | fact | list | timeline | closing.
    role: Mapped[str | None] = mapped_column(String(16))
    local_path: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(700))
    # Permite limpiar en Cloudinary lo que quede huérfano de un carrusel fallido.
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(200))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    cover_url: Mapped[str | None] = mapped_column(String(700))
    ig_container_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    item: Mapped["InstagramQueueItem"] = relationship(back_populates="media")


class VideoClip(Base):
    """Un fragmento de vídeo de YouTube usado en una publicación de Instagram.

    La decisión editorial es publicar clips de canales ajenos sin pedir permiso
    previo y atender las reclamaciones si llegan. Esta tabla es lo que hace eso
    sostenible: guarda DE DÓNDE salió cada clip (vídeo, canal, tramo exacto),
    quién lo aprobó y en qué publicación acabó, de modo que ante un aviso se
    puede responder en minutos y retirarlo con un botón.

    Mismo ciclo que `YoutubeIngestQueue`, y por la misma razón: la IP del
    servidor está bloqueada por YouTube, así que la descarga la hace un daemon
    en la Mac y empuja el resultado por HTTP.

    Estados: requested → downloading → ready → published → retired | failed.
    """

    __tablename__ = "video_clips"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','downloading','ready','published',"
            "'retired','failed')",
            name="ck_video_clips_status",
        ),
        CheckConstraint("end_s > start_s", name="ck_video_clips_tramo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # --- Procedencia: lo que se enseña si alguien reclama ---
    video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    video_title: Mapped[str | None] = mapped_column(String(500))
    channel_title: Mapped[str | None] = mapped_column(String(200))
    channel_url: Mapped[str | None] = mapped_column(String(500))
    # --- Tramo utilizado ---
    start_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    # --- Ciclo de vida ---
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", index=True
    )
    local_path: Mapped[str | None] = mapped_column(String(500))
    url_cdn: Mapped[str | None] = mapped_column(String(700))
    cloudinary_public_id: Mapped[str | None] = mapped_column(String(200))
    duration_s: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    # --- Trazabilidad ---
    requested_by: Mapped[str | None] = mapped_column(String(200))
    queue_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_queue.id", ondelete="SET NULL")
    )
    ig_media_id: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @property
    def atribucion(self) -> str:
        """Texto de crédito que va SIEMPRE con el clip, en la pieza y el caption."""
        canal = (self.channel_title or "").strip()
        return f"🎬 Vídeo: {canal}" if canal else "🎬 Vídeo de YouTube"



# --- Listas de reproducción (zona privada) ---------------------------------


class Playlist(Base):
    """Lista de reproducción manual de un usuario. Las listas por estado de
    ánimo se generan al vuelo (embeddings) y NO se persisten aquí."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    items: Mapped[list["PlaylistItem"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistItem.position",
    )


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (
        UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), index=True, nullable=False
    )
    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    playlist: Mapped[Playlist] = relationship(back_populates="items")
    song: Mapped[Song] = relationship()


class EntityEdge(Base):
    """Grafo de conocimiento unificado: una arista entre dos entidades del
    corpus (artist/album/song/person/band/theme/place/concept).

    Derivado e IDEMPOTENTE: lo repuebla `scripts/graph/build_graph.py` a partir
    de las tablas relacionales (FK, SongTheme/Place/Concept, BandMembership) y
    los JSONB (Person.other_bands, SeoContent/Post.entities). Consultable en
    ambos sentidos (índices en src y dst). `edge_type` ∈ {song_of_album,
    album_of_artist, song_theme, song_place, song_concept, member_of,
    other_band, video_of, mentions, lyrics_by, music_by, adapted_from}.

    Los tres últimos (autoría) los genera `build_graph.py` desde `SongCredit`:
    conectan una canción con la persona que firma su letra/música o el poema
    original adaptado (p.ej. song → person Manolo Chinato vía adapted_from).
    """

    __tablename__ = "entity_edges"
    __table_args__ = (
        UniqueConstraint(
            "src_type", "src_id", "edge_type", "dst_type", "dst_id",
            name="uq_entity_edges",
        ),
        Index("ix_entity_edges_src", "src_type", "src_id"),
        Index("ix_entity_edges_dst", "dst_type", "dst_id"),
        Index("ix_entity_edges_type", "edge_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    src_type: Mapped[str] = mapped_column(String(16), nullable=False)
    src_id: Mapped[int] = mapped_column(Integer, nullable=False)
    src_slug: Mapped[str] = mapped_column(String(180), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dst_type: Mapped[str] = mapped_column(String(16), nullable=False)
    dst_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dst_slug: Mapped[str] = mapped_column(String(180), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Verificación multi-fuente (MCV) y erratas de fans ---------------------


class VerificationRecord(Base):
    """Traza persistente de una verificación del Motor de Consenso (MCV).

    Antes la única caché de verificación era un JSON efímero en /tmp y el veredicto
    no se guardaba. Aquí se persiste cada claim verificado (letra/autoría/catálogo)
    con su veredicto, la confianza del consenso y las fuentes que votaron, para:
    (1) no re-consultar fuentes externas en cada barrido, (2) dar proveniencia
    auditable a toda auto-corrección, (3) permitir revertir.

    `claim_kind` ∈ {lyric_line, song_authorship, song_album, song_year, album_year}.
    `verdict` ∈ {confirmed, corrected, conflict, not_found}. `sources` es una lista
    de dicts {name, tier, url, quote} — las fuentes que respaldan/contradicen.
    """

    __tablename__ = "verification_records"
    __table_args__ = (
        UniqueConstraint("claim_kind", "claim_key", name="uq_verification_claim"),
        Index("ix_verification_kind", "claim_kind"),
        Index("ix_verification_verdict", "verdict"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    # Clave estable del claim (p.ej. "song:123:line:14" o "song:123:authorship").
    claim_key: Mapped[str] = mapped_column(String(256), nullable=False)
    song_id: Mapped[int | None] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sources: Mapped[list | None] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # True si el veredicto se APLICÓ (auto-corrección); False si solo se registró
    # o quedó pendiente de humano. `auto_applied` permite el feed de auditoría.
    auto_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reverted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Momento en que la corrección se aplicó DE VERDAD (o cambió de valor). Distinto
    # de `checked_at`, que se re-sella en cada barrido nocturno aunque no cambie nada:
    # sin esta columna el digest diario repetía eternamente las mismas correcciones
    # como si fueran de las últimas 24h.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    song: Mapped[Song | None] = relationship()


class ErrataReport(Base):
    """Errata reportada por un fan de confianza (o encolada por el barrido).

    Filosofía: una errata NO va directa al humano. Al llegar dispara el MCV sobre
    ese claim; si el consenso confirma la corrección se auto-resuelve y solo queda
    en el feed de auditoría. Solo el residuo ambiguo (fuentes en conflicto, sin
    cobertura, alto riesgo) queda `needs_human` en la cola admin.

    `target_type` ∈ {song_lyrics, authorship, catalog, interpretation}.
    `status`: pending → (auto_resolved | needs_human) → (applied | rejected).
    """

    __tablename__ = "errata_reports"
    __table_args__ = (
        Index("ix_errata_status", "status"),
        Index("ix_errata_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer)  # song_id / post_id según target
    field: Mapped[str | None] = mapped_column(String(120))
    reported_wrong: Mapped[str | None] = mapped_column(Text)
    suggested_right: Mapped[str | None] = mapped_column(Text)
    reporter: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    # Enlace al veredicto del MCV que la resolvió (si lo hubo).
    verification_id: Mapped[int | None] = mapped_column(
        ForeignKey("verification_records.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Última vez que esta errata salió en el digest al admin. Evita repetir cada
    # mañana lo mismo: se re-avisa solo pasado `DIGEST_REMINDER_DAYS`.
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDigest(Base):
    """Huella del último digest enviado al admin, por tipo.

    El digest diario sonaba aunque no hubiera nada nuevo que hacer. Guardamos la
    FIRMA de lo pendiente (qué erratas, qué posts, qué auto-correcciones) y solo
    se envía si la firma cambió: si no ha pasado nada desde ayer, no hay correo.
    """

    __tablename__ = "notification_digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- Cola de ingesta de YouTube (Juancares + entrevistas de Robe) ----------


class YouTubeIngestQueue(Base):
    """Vídeos de YouTube pendientes de transcribir e ingerir al corpus.

    Arquitectura "1 click → autónomo" (ver project_robelyrics_youtube_juancares):
    el cron del server DETECTA uploads nuevos de @juancaraes y siembra las
    entrevistas de Robe de data/robe_interviews.yaml (no se puede descargar desde
    la IP del datacenter: antibot de YouTube). Manda al admin un email con un CTA
    firmado; al hacer click, el batch pasa a `approved`. Un daemon launchd en la
    Mac (IP residencial) hace polling de los `approved`, descarga/transcribe con
    yt-dlp+Whisper y empuja la transcripción a prod por HTTP, marcando `done`.

    `status`: detected → approved → processing → done (o failed).

    `target` agrupa el destino (UX del email + colección Qdrant):
      - `corpus`     → fan-content de Juancares → interpretations_v1 (embed_interpretations).
      - `robe_voice` → entrevistas/contexto → robe_voice_v1 (embed_robe_voice).

    `kind`/`author` viajan EXPLÍCITOS por fila (no se derivan del target) para no
    mislabelar a terceros como Robe: `author_is_robe = kind != 'about_robe'` en
    embed_robe_voice. Mapeo: youtube_transcript (Juancares) · robe_interview (habla
    Robe) · about_robe (homenaje/análisis de terceros, jamás citado como Robe).
    """

    __tablename__ = "youtube_ingest_queue"
    __table_args__ = (
        CheckConstraint(
            "status IN ('detected', 'approved', 'processing', 'done', 'failed')",
            name="ck_youtube_ingest_status",
        ),
        CheckConstraint(
            "target IN ('corpus', 'robe_voice')",
            name="ck_youtube_ingest_target",
        ),
        CheckConstraint(
            "kind IN ('youtube_transcript', 'robe_interview', 'about_robe')",
            name="ck_youtube_ingest_kind",
        ),
        UniqueConstraint("video_id", "target", name="uq_youtube_ingest_video_target"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    # Canal/fuente de origen ("juancaraes", o el handle de la entrevista).
    channel: Mapped[str | None] = mapped_column(String(120))
    target: Mapped[str] = mapped_column(
        String(16), nullable=False, default="corpus"
    )
    # kind final del InterpretationSource (decide author_is_robe en robe_voice_v1).
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="youtube_transcript"
    )
    # Autor/fuente del material (canal, entrevistador). Para youtube_transcript
    # de Juancares = "Juancares". NO se usa para flag de voz (eso es por kind).
    author: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="detected", index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UrlIngestJob(Base):
    """Alta manual de una noticia desde una URL, ejecutada en SEGUNDO PLANO.

    El motor tarda de 2 a 4 minutos (planifica, investiga, escribe sección a
    sección verificando cada una y, si el gate de rigor la rechaza, reintenta con
    investigación reforzada). Cloudflare corta cualquier petición a los 100 s: por
    HTTP síncrono el admin recibía un `524` y NUNCA llegaba a ver el resultado —
    ni la propuesta creada ni las razones del rechazo—, aunque el servidor hubiera
    terminado bien. Medido en prod: 264,8 s de punta a punta.

    Ahora la petición solo encola. El trabajo lo ejecuta el servidor, así que
    sobrevive a cerrar la pestaña, y el estado vive en BD (no en memoria) porque
    uvicorn corre con varios workers y el polling puede caer en otro distinto.

    `status`: running → done | rejected | failed
      - `done`     → `proposal_id` apunta a la propuesta creada.
      - `rejected` → el editor jefe la tumbó; `score` y `reasons` explican por qué.
      - `failed`   → se rompió algo; `error` lo cuenta.
    """

    __tablename__ = "url_ingest_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'rejected', 'failed')",
            name="ck_url_ingest_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # La petición, tal cual, para poder reintentarla sin volver a pegar el texto.
    url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(String(240))
    body_text: Mapped[str | None] = mapped_column(Text)
    rewrite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", index=True
    )
    proposal_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(240))
    rewritten: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warning: Mapped[str | None] = mapped_column(Text)
    # Veredicto del gate cuando rechaza (para pintarlo en el panel).
    score: Mapped[int | None] = mapped_column(Integer)
    reasons: Mapped[list | None] = mapped_column(JSONB)
    boosted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- #
# Política de nombre (REGLA DURA): la forma "Robe Iniesta" NUNCA debe persistir
# en contenido (a él no le gustaba). Listeners a nivel ORM → cualquier escritura
# (scripts, cron, API, manual) sobre estas tablas la convierte en "Robe". No
# toca "Roberto Iniesta" ni los slugs (ver text_sanitizer.enforce_name_policy).
# --------------------------------------------------------------------------- #
from sqlalchemy import event as _event  # noqa: E402
from app.services.text_sanitizer import enforce_name_policy as _fix_name  # noqa: E402


def _make_name_policy_listener(fields: tuple[str, ...]):
    def _listener(mapper, connection, target):  # noqa: ANN001
        import json as _json
        for f in fields:
            v = getattr(target, f, None)
            if isinstance(v, str) and v:
                setattr(target, f, _fix_name(v))
            elif isinstance(v, (dict, list)) and v:
                # Campos JSONB (p.ej. schema_jsonld): era el hueco por donde se
                # colaba "Robe Iniesta". Se sanea el JSON serializado.
                raw = _json.dumps(v, ensure_ascii=False)
                clean = _fix_name(raw)
                if clean != raw:
                    setattr(target, f, _json.loads(clean))
    return _listener


# Cubre el contenido generado (incl. schema_jsonld) Y los campos de nombre de las
# entidades (Person/Artist/Album/Band), que antes quedaban fuera. Ojo: para
# persons.full_name lo correcto es "Roberto Iniesta"; la política solo actúa si
# aparece literalmente "Robe Iniesta" (previene la violación, no toca "Roberto").
for _model, _fields in (
    (SeoContent, ("body_md", "meta_title", "meta_description", "h1", "schema_jsonld", "entities")),
    (Post, ("body_md", "title", "excerpt", "meta_title", "meta_description")),
    (InstagramQueueItem, ("caption",)),
    (Person, ("full_name", "stage_name", "bio_short", "bio_long")),
    (Artist, ("name",)),
    (Album, ("title",)),
    (Band, ("name",)),
):
    _lst = _make_name_policy_listener(_fields)
    _event.listen(_model, "before_insert", _lst)
    _event.listen(_model, "before_update", _lst)
