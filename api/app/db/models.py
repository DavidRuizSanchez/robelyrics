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
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    genius_id: Mapped[int | None] = mapped_column(Integer)
    genius_url: Mapped[str | None] = mapped_column(String(512))
    youtube_id: Mapped[str | None] = mapped_column(String(32))
    youtube_match_quality: Mapped[str | None] = mapped_column(String(16))  # official|topic|search|manual
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


class SongConcept(Base):
    __tablename__ = "song_concepts"

    song_id: Mapped[int] = mapped_column(
        ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[int] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
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
    hero_image_url: Mapped[str | None] = mapped_column(String(500))
    # Atribución y licencia de la imagen (Wikimedia Commons). Renderizadas en
    # el footer del post para cumplir con la licencia (CC-BY/CC-BY-SA exigen
    # author + licencia + enlace a la fuente).
    hero_image_attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    hero_image_license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hero_image_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_name: Mapped[str | None] = mapped_column(String(200))
    meta_title: Mapped[str | None] = mapped_column(String(256))
    meta_description: Mapped[str | None] = mapped_column(String(512))
    anniversary_year: Mapped[int | None] = mapped_column(Integer)
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
