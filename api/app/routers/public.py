"""Endpoints públicos sin auth para la capa SEO indexable.

Diseño legal:
  - Lista de artistas / álbumes / canciones (metadata): libre.
  - Letras: solo `snippet` (≤ 4 líneas centrales) + link a Genius (cita LPI 32).
  - NO se exponen interpretaciones fan (CC-BY-NC incompatible con ads).
  - El contenido SEO (markdown editorial) vive en `seo_content` (creado en F.5)
    y solo se sirve cuando `published=true`. Mientras la tabla no exista, los
    endpoints devuelven `seo_body=None` sin romper.

Se mantiene aparte del router auth-only de `catalog.py`. NO duplica código común
(reusa los modelos SQLAlchemy y la sesión).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, Depends
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    Concept,
    Line,
    Place,
    SeoContent,
    Song,
    Theme,
)
from app.db.session import get_db
from app.services.seo_templates import resolve_all

router = APIRouter(prefix="/public", tags=["public"])

# Cache HTTP largo para CDN/Cloudflare cuando se despliegue.
_CACHE_HEADER = "public, max-age=3600, stale-while-revalidate=86400"

# Snippet: máximo de líneas a exponer públicamente. Cita LPI 32.
MAX_SNIPPET_LINES = 4


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class PublicArtistOut(BaseModel):
    slug: str
    name: str
    active_years: str | None = None


class PublicAlbumOut(BaseModel):
    slug: str
    title: str
    year: int
    kind: str
    cover_url: str | None = None


class PublicTrackOut(BaseModel):
    slug: str
    title: str
    track_number: int | None
    youtube_id: str | None = None


class PublicArtistMember(BaseModel):
    """Miembro del grupo (resuelto via BandMembership) para mostrar en la
    página de artist como sección "Miembros" e interconectar SEO."""
    slug: str
    full_name: str
    stage_name: str | None = None
    role: str
    era: str | None = None
    is_founder: bool = False
    image_url: str | None = None


class PublicArtistDetailOut(PublicArtistOut):
    albums: list[PublicAlbumOut]
    members: list[PublicArtistMember] = []
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None
    seo_h1: str | None = None


class PublicAlbumDetailOut(PublicAlbumOut):
    artist: PublicArtistOut
    tracks: list[PublicTrackOut]
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None
    seo_h1: str | None = None


class PublicTaxonomyPill(BaseModel):
    """Item compacto de taxonomía para listar en chips dentro de la canción."""
    kind: str  # 'theme' | 'place' | 'concept'
    slug: str
    name: str


class PublicSongDetailOut(BaseModel):
    slug: str
    title: str
    track_number: int | None
    artist: PublicArtistOut
    album: PublicAlbumOut
    # Cover propia de la canción (single/EP/clip con artwork distinto del álbum).
    # Si NULL, el frontend cae a `album.cover_url`.
    cover_url: str | None = None
    snippet: list[str]                # máx. MAX_SNIPPET_LINES
    snippet_attribution: str          # texto de cita
    genius_url: str | None
    youtube_id: str | None = None
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None
    seo_h1: str | None = None
    themes: list[PublicTaxonomyPill] = []
    places: list[PublicTaxonomyPill] = []
    concepts: list[PublicTaxonomyPill] = []


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _try_get_seo(db: Session, entity_type: str, entity_id: int) -> dict | None:
    """Lee `seo_content` publicado y resuelve title/description/h1 aplicando
    plantillas si no hay override. Devuelve None si no hay fila publicada (la
    página pública responde 404)."""
    try:
        row = (
            db.query(SeoContent)
            .filter(
                SeoContent.entity_type == entity_type,
                SeoContent.entity_id == entity_id,
                SeoContent.published.is_(True),
            )
            .first()
        )
    except Exception:
        # Tabla no existe todavía (pre-F.5) o esquema desfasado. Silencioso.
        db.rollback()
        return None
    if not row:
        return None
    resolved = resolve_all(db, row)
    return {
        "body_md": row.body_md,
        "meta_title": resolved["title"] or None,
        "meta_description": resolved["description"] or None,
        "h1": resolved["h1"] or None,
    }


def _snippet_lines(db: Session, song_id: int) -> list[str]:
    """Devuelve las líneas centrales del corpus de la canción (máx. MAX_SNIPPET_LINES).

    Estrategia: tomar las líneas del centro, no del principio (más representativas
    del tema sin spoilear el inicio canónico). Si la canción tiene menos de
    MAX_SNIPPET_LINES, devolverlas todas.
    """
    lines = (
        db.query(Line.text)
        .filter(Line.song_id == song_id)
        .order_by(Line.line_index)
        .all()
    )
    if not lines:
        return []
    texts = [r[0] for r in lines]
    n = len(texts)
    if n <= MAX_SNIPPET_LINES:
        return texts
    start = (n - MAX_SNIPPET_LINES) // 2
    return texts[start:start + MAX_SNIPPET_LINES]


def _set_cache(response: Response) -> None:
    response.headers["Cache-Control"] = _CACHE_HEADER


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/artists", response_model=list[PublicArtistOut])
def list_public_artists(
    response: Response,
    db: Session = Depends(get_db),
) -> list[PublicArtistOut]:
    _set_cache(response)
    rows = db.query(Artist).order_by(Artist.slug).all()
    return [
        PublicArtistOut(slug=a.slug, name=a.name, active_years=a.active_years)
        for a in rows
    ]


@router.get("/artists/{slug}", response_model=PublicArtistDetailOut)
def public_artist_detail(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicArtistDetailOut:
    _set_cache(response)
    artist = db.query(Artist).filter(Artist.slug == slug).first()
    if not artist:
        raise HTTPException(status_code=404, detail="artist not found")
    albums = (
        db.query(Album)
        .filter(Album.artist_id == artist.id)
        .order_by(Album.year, Album.id)
        .all()
    )
    # Carga miembros del grupo via BandMembership. Lazy import para no
    # complicar el bloque de imports del módulo.
    from app.db.models import BandMembership as _BM, Person as _P
    members_raw = (
        db.query(_BM, _P)
        .join(_P, _BM.person_id == _P.id)
        .filter(_BM.artist_id == artist.id)
        .order_by(_BM.position, _BM.era)
        .all()
    )
    seo = _try_get_seo(db, "artist", artist.id)
    return PublicArtistDetailOut(
        slug=artist.slug,
        name=artist.name,
        active_years=artist.active_years,
        albums=[
            PublicAlbumOut(
                slug=a.slug, title=a.title, year=a.year, kind=a.kind,
                cover_url=a.cover_url,
            )
            for a in albums
        ],
        members=[
            PublicArtistMember(
                slug=p.slug,
                full_name=p.full_name,
                stage_name=p.stage_name,
                role=m.role,
                era=m.era,
                is_founder=m.is_founder,
                image_url=p.image_url,
            )
            for m, p in members_raw
        ],
        seo_body=seo["body_md"] if seo else None,
        seo_meta_title=seo["meta_title"] if seo else None,
        seo_meta_description=seo["meta_description"] if seo else None,
        seo_h1=seo["h1"] if seo else None,
    )


@router.get("/albums/{slug}", response_model=PublicAlbumDetailOut)
def public_album_detail(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicAlbumDetailOut:
    _set_cache(response)
    album = db.query(Album).filter(Album.slug == slug).first()
    if not album:
        raise HTTPException(status_code=404, detail="album not found")
    songs = (
        db.query(Song)
        .filter(Song.album_id == album.id)
        .order_by(Song.track_number.nulls_last(), Song.id)
        .all()
    )
    artist = album.artist
    seo = _try_get_seo(db, "album", album.id)
    return PublicAlbumDetailOut(
        slug=album.slug,
        title=album.title,
        year=album.year,
        kind=album.kind,
        cover_url=album.cover_url,
        artist=PublicArtistOut(
            slug=artist.slug, name=artist.name, active_years=artist.active_years,
        ),
        tracks=[
            PublicTrackOut(
                slug=s.slug,
                title=s.title,
                track_number=s.track_number,
                youtube_id=s.youtube_id,
            )
            for s in songs
        ],
        seo_body=seo["body_md"] if seo else None,
        seo_meta_title=seo["meta_title"] if seo else None,
        seo_meta_description=seo["meta_description"] if seo else None,
        seo_h1=seo["h1"] if seo else None,
    )


@router.get("/songs/{slug}", response_model=PublicSongDetailOut)
def public_song_detail(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicSongDetailOut:
    _set_cache(response)
    song = db.query(Song).filter(Song.slug == slug).first()
    if not song:
        raise HTTPException(status_code=404, detail="song not found")
    album = song.album
    artist = album.artist
    snippet = _snippet_lines(db, song.id)
    seo = _try_get_seo(db, "song", song.id)
    return PublicSongDetailOut(
        slug=song.slug,
        title=song.title,
        track_number=song.track_number,
        artist=PublicArtistOut(
            slug=artist.slug, name=artist.name, active_years=artist.active_years,
        ),
        album=PublicAlbumOut(
            slug=album.slug, title=album.title, year=album.year, kind=album.kind,
            cover_url=album.cover_url,
        ),
        cover_url=song.cover_url,
        snippet=snippet,
        snippet_attribution=(
            f"Fragmento citado de «{song.title}» — © sus autores · "
            "Letra completa en Genius"
        ),
        genius_url=song.genius_url,
        youtube_id=song.youtube_id,
        seo_body=seo["body_md"] if seo else None,
        seo_meta_title=seo["meta_title"] if seo else None,
        seo_meta_description=seo["meta_description"] if seo else None,
        seo_h1=seo["h1"] if seo else None,
        themes=[
            PublicTaxonomyPill(kind="theme", slug=t.slug, name=t.name)
            for t in song.themes
        ],
        places=[
            PublicTaxonomyPill(kind="place", slug=p.slug, name=p.name)
            for p in song.places
        ],
        concepts=[
            PublicTaxonomyPill(kind="concept", slug=c.slug, name=c.name)
            for c in song.concepts
        ],
    )


class PublicSearchHit(BaseModel):
    kind: str  # 'artist' | 'album' | 'song'
    slug: str
    title: str
    subtitle: str | None = None  # ej. "Extremoduro · 1996" para una canción
    url_path: str  # ruta canónica completa
    lyric_match: str | None = None  # verso citado si el match fue en letra


class PublicSearchOut(BaseModel):
    query: str
    results: list[PublicSearchHit]


class PublicSitemapEntry(BaseModel):
    url_path: str            # ej. "/extremoduro/agila/asco"
    last_modified: datetime  # generated_at o reviewed_at
    entity_type: str


@router.get("/sitemap-entries", response_model=list[PublicSitemapEntry])
def public_sitemap_entries(
    response: Response,
    db: Session = Depends(get_db),
) -> list[PublicSitemapEntry]:
    """Lista de entidades con seo_content publicado, para construir sitemap.xml.
    Devuelve la URL canónica relativa y la última fecha de revisión.
    """
    _set_cache(response)
    from sqlalchemy import text
    try:
        rows = db.execute(text(
            """
            SELECT sc.entity_type,
                   sc.slug,
                   COALESCE(sc.reviewed_at, sc.generated_at) AS last_mod,
                   CASE
                     WHEN sc.entity_type='artist' THEN '/' || sc.slug
                     WHEN sc.entity_type='album'  THEN '/' || ar.slug || '/' || sc.slug
                     WHEN sc.entity_type='song'   THEN '/' || ar2.slug || '/' || al.slug || '/' || sc.slug
                     WHEN sc.entity_type='person' THEN '/personas/' || sc.slug
                   END AS url_path
            FROM seo_content sc
            LEFT JOIN albums al_a ON sc.entity_type='album' AND al_a.id = sc.entity_id
            LEFT JOIN artists ar  ON al_a.artist_id = ar.id
            LEFT JOIN songs s     ON sc.entity_type='song' AND s.id = sc.entity_id
            LEFT JOIN albums al   ON s.album_id = al.id
            LEFT JOIN artists ar2 ON al.artist_id = ar2.id
            WHERE sc.published = true
            ORDER BY sc.entity_type, sc.slug
            """
        )).all()
    except Exception:
        db.rollback()
        return []
    return [
        PublicSitemapEntry(
            url_path=r.url_path,
            last_modified=r.last_mod,
            entity_type=r.entity_type,
        )
        for r in rows if r.url_path
    ]


@router.get("/search", response_model=PublicSearchOut)
def public_search(
    q: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicSearchOut:
    """Búsqueda pública SOLO por metadata (títulos de canción/álbum/artista).

    Deliberadamente NO busca en `lines.text` ni en `lyrics_clean`. Eso queda
    para el buscador semántico de la capa privada.
    """
    _set_cache(response)
    q = (q or "").strip()
    if len(q) < 2:
        return PublicSearchOut(query=q, results=[])
    pattern = f"%{q}%"

    out: list[PublicSearchHit] = []

    # Artistas
    artists = (
        db.query(Artist)
        .filter(Artist.name.ilike(pattern))
        .order_by(Artist.slug)
        .limit(5)
        .all()
    )
    for a in artists:
        out.append(PublicSearchHit(
            kind="artist", slug=a.slug, title=a.name,
            subtitle=a.active_years,
            url_path=f"/{a.slug}",
        ))

    # Álbumes
    albums = (
        db.query(Album, Artist)
        .join(Artist, Album.artist_id == Artist.id)
        .filter(Album.title.ilike(pattern))
        .order_by(Album.year)
        .limit(10)
        .all()
    )
    for album, artist in albums:
        out.append(PublicSearchHit(
            kind="album", slug=album.slug, title=album.title,
            subtitle=f"{artist.name} · {album.year}",
            url_path=f"/{artist.slug}/{album.slug}",
        ))

    # Canciones por título
    songs = (
        db.query(Song, Album, Artist)
        .join(Album, Song.album_id == Album.id)
        .join(Artist, Album.artist_id == Artist.id)
        .filter(Song.title.ilike(pattern))
        .order_by(Album.year, Song.track_number)
        .limit(20)
        .all()
    )
    seen_song_ids: set[int] = set()
    for song, album, artist in songs:
        seen_song_ids.add(song.id)
        out.append(PublicSearchHit(
            kind="song", slug=song.slug, title=song.title,
            subtitle=f"{artist.name} · {album.title} ({album.year})",
            url_path=f"/{artist.slug}/{album.slug}/{song.slug}",
        ))

    # Canciones por letra (lines.text). Devolvemos el primer verso que matchea
    # como `lyric_match` para que el usuario vea por qué aparece. Solo
    # canciones con seo_content publicado (las que tienen página pública).
    # Limitamos a 20 para no saturar.
    lyric_rows = db.execute(text(
        """
        SELECT DISTINCT ON (s.id)
            s.id, s.slug, s.title,
            al.slug AS album_slug, al.title AS album_title, al.year,
            ar.slug AS artist_slug, ar.name AS artist_name,
            l.text AS line_text
        FROM songs s
        JOIN albums al ON al.id = s.album_id
        JOIN artists ar ON ar.id = al.artist_id
        JOIN lines l ON l.song_id = s.id
        JOIN seo_content sc ON sc.entity_type = 'song' AND sc.entity_id = s.id
            AND sc.published = TRUE
        WHERE l.text ILIKE :pattern
        ORDER BY s.id, l.line_index
        LIMIT 20
        """
    ), {"pattern": pattern}).all()
    for r in lyric_rows:
        if r.id in seen_song_ids:
            continue  # ya estaba por match de título
        seen_song_ids.add(r.id)
        # Cita corta del verso (máx 100 chars).
        verse = (r.line_text or "").strip()
        if len(verse) > 100:
            verse = verse[:97].rstrip() + "…"
        out.append(PublicSearchHit(
            kind="song", slug=r.slug, title=r.title,
            subtitle=f"{r.artist_name} · {r.album_title} ({r.year})",
            url_path=f"/{r.artist_slug}/{r.album_slug}/{r.slug}",
            lyric_match=verse,
        ))

    return PublicSearchOut(query=q, results=out)


# --------------------------------------------------------------------------- #
# Taxonomías (Fase 2): themes / places / concepts
# --------------------------------------------------------------------------- #
class PublicTaxonomyListItem(BaseModel):
    slug: str
    name: str
    description: str | None = None
    song_count: int


class PublicTaxonomySongRef(BaseModel):
    title: str
    url_path: str
    artist_name: str
    album_title: str
    year: int | None = None


class PublicTaxonomyDetailOut(BaseModel):
    slug: str
    name: str
    description: str | None = None
    kind: str  # 'theme' | 'place' | 'concept'
    extra: dict | None = None  # places: {geo_lat, geo_lng}
    songs: list[PublicTaxonomySongRef]


def _is_live_version(slug: str, title: str) -> bool:
    """True si la canción es una versión 'en directo'."""
    s = slug.lower()
    t = title.lower()
    return s.endswith("-en-directo") or "(en directo)" in t or "[en directo]" in t


def _base_slug(slug: str) -> str:
    """Devuelve el slug sin el sufijo `-en-directo` para emparejar versiones."""
    if slug.lower().endswith("-en-directo"):
        return slug[: -len("-en-directo")]
    return slug


def _dedupe_studio_vs_live(songs):
    """Si en la lista hay versión estudio + versión en directo de la misma
    canción, mantenemos solo la de estudio. Si solo existe la versión en
    directo, esa entra. Las canciones únicas no se ven afectadas.

    `songs` es iterable de objetos Song (no de SongRefs). Devuelve lista.
    """
    songs = list(songs)
    studio_bases: set[str] = {
        s.slug for s in songs if not _is_live_version(s.slug, s.title)
    }
    out = []
    for s in songs:
        if _is_live_version(s.slug, s.title) and _base_slug(s.slug) in studio_bases:
            continue
        out.append(s)
    return out


def _published_songs(db: Session, songs) -> list:
    """Filtra canciones cuyo seo_content esté publicado. Devuelve lista."""
    out = []
    for s in songs:
        pub = db.query(SeoContent).filter(
            SeoContent.entity_type == "song",
            SeoContent.entity_id == s.id,
            SeoContent.published.is_(True),
        ).first()
        if pub:
            out.append(s)
    return out


# Umbral de canciones para exponer un hub. Themes/concepts requieren al menos
# 2 (evita thin content para temas abstractos repetibles). Places admiten 1
# porque un lugar geográfico nombrado en una sola canción ya tiene entidad y
# es contenido SEO valioso (ej. El Piornal en *Viajando por el interior*).
_MIN_SONGS_BY_KIND = {"theme": 2, "concept": 2, "place": 1}


def _list_taxonomy(
    db: Session, model, kind: str = "theme"
) -> list[PublicTaxonomyListItem]:
    """Lista todas las entradas con count de canciones publicadas (dedup
    estudio vs directo). Aplica umbral mínimo según `kind`."""
    rows = (
        db.query(model)
        .order_by(model.name)
        .all()
    )
    threshold = _MIN_SONGS_BY_KIND.get(kind, 2)
    result: list[PublicTaxonomyListItem] = []
    for r in rows:
        published = _published_songs(db, r.songs)
        deduped = _dedupe_studio_vs_live(published)
        count = len(deduped)
        if count < threshold:
            continue
        result.append(PublicTaxonomyListItem(
            slug=r.slug, name=r.name, description=r.description, song_count=count,
        ))
    return result


def _detail_taxonomy(
    db: Session, model, slug: str, kind: str
) -> PublicTaxonomyDetailOut:
    row = db.query(model).filter(model.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"{kind} not found")

    published = _published_songs(db, row.songs)
    deduped = _dedupe_studio_vs_live(published)

    songs: list[PublicTaxonomySongRef] = []
    for s in deduped:
        al = s.album
        ar = al.artist
        songs.append(PublicTaxonomySongRef(
            title=s.title,
            url_path=f"/{ar.slug}/{al.slug}/{s.slug}",
            artist_name=ar.name,
            album_title=al.title,
            year=al.year,
        ))

    threshold = _MIN_SONGS_BY_KIND.get(kind, 2)
    if len(songs) < threshold:
        # Coherente con _list_taxonomy.
        raise HTTPException(status_code=404, detail=f"{kind} sin suficientes canciones publicadas")

    extra = None
    if kind == "place" and (row.geo_lat or row.geo_lng):
        extra = {"geo_lat": float(row.geo_lat) if row.geo_lat else None,
                 "geo_lng": float(row.geo_lng) if row.geo_lng else None,
                 "kind": row.kind}

    return PublicTaxonomyDetailOut(
        slug=row.slug,
        name=row.name,
        description=row.description,
        kind=kind,
        extra=extra,
        songs=songs,
    )


@router.get("/themes", response_model=list[PublicTaxonomyListItem])
def public_themes_list(response: Response, db: Session = Depends(get_db)):
    _set_cache(response)
    return _list_taxonomy(db, Theme, kind="theme")


@router.get("/themes/{slug}", response_model=PublicTaxonomyDetailOut)
def public_theme_detail(slug: str, response: Response, db: Session = Depends(get_db)):
    _set_cache(response)
    return _detail_taxonomy(db, Theme, slug, "theme")


@router.get("/places", response_model=list[PublicTaxonomyListItem])
def public_places_list(response: Response, db: Session = Depends(get_db)):
    _set_cache(response)
    return _list_taxonomy(db, Place, kind="place")


@router.get("/places/{slug}", response_model=PublicTaxonomyDetailOut)
def public_place_detail(slug: str, response: Response, db: Session = Depends(get_db)):
    _set_cache(response)
    return _detail_taxonomy(db, Place, slug, "place")


@router.get("/concepts", response_model=list[PublicTaxonomyListItem])
def public_concepts_list(response: Response, db: Session = Depends(get_db)):
    _set_cache(response)
    return _list_taxonomy(db, Concept, kind="concept")


@router.get("/concepts/{slug}", response_model=PublicTaxonomyDetailOut)
def public_concept_detail(slug: str, response: Response, db: Session = Depends(get_db)):
    _set_cache(response)
    return _detail_taxonomy(db, Concept, slug, "concept")


# --------------------------------------------------------------------------- #
# Blog (Fase 3): /blog y /blog/{slug}
# --------------------------------------------------------------------------- #
from app.db.models import BandMembership, Person, Post  # noqa: E402


# --------------------------------------------------------------------------- #
# Personas (knowledge graph)
# --------------------------------------------------------------------------- #
class PublicPersonMembership(BaseModel):
    artist_slug: str
    artist_name: str
    role: str
    era: str | None = None
    is_founder: bool = False
    is_current: bool = False


class PublicPersonListItem(BaseModel):
    slug: str
    full_name: str
    stage_name: str | None = None
    birth_date: str | None = None
    death_date: str | None = None
    image_url: str | None = None


class PublicPersonDetailOut(PublicPersonListItem):
    birth_place: str | None = None
    bio_short: str | None = None
    wikipedia_url: str | None = None
    wikidata_id: str | None = None
    image_attribution: str | None = None
    image_license: str | None = None
    image_source_url: str | None = None
    memberships: list[PublicPersonMembership] = []
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None
    schema_jsonld: dict | None = None


@router.get("/persons", response_model=list[PublicPersonListItem])
def public_persons_list(
    response: Response,
    db: Session = Depends(get_db),
) -> list[PublicPersonListItem]:
    _set_cache(response)
    persons = (
        db.query(Person)
        .order_by(Person.full_name)
        .all()
    )
    return [
        PublicPersonListItem(
            slug=p.slug,
            full_name=p.full_name,
            stage_name=p.stage_name,
            birth_date=p.birth_date.isoformat() if p.birth_date else None,
            death_date=p.death_date.isoformat() if p.death_date else None,
            image_url=p.image_url,
        )
        for p in persons
    ]


@router.get("/persons/{slug}", response_model=PublicPersonDetailOut)
def public_person_detail(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicPersonDetailOut:
    _set_cache(response)
    person = db.query(Person).filter(Person.slug == slug).first()
    if not person:
        raise HTTPException(status_code=404, detail="person not found")

    memberships_raw = (
        db.query(BandMembership, Artist)
        .join(Artist, BandMembership.artist_id == Artist.id)
        .filter(BandMembership.person_id == person.id)
        .order_by(BandMembership.position, BandMembership.era)
        .all()
    )
    memberships = [
        PublicPersonMembership(
            artist_slug=a.slug,
            artist_name=a.name,
            role=m.role,
            era=m.era,
            is_founder=m.is_founder,
            is_current=m.is_current,
        )
        for m, a in memberships_raw
    ]

    # SEO content si está publicado
    seo = (
        db.query(SeoContent)
        .filter(
            SeoContent.entity_type == "person",
            SeoContent.entity_id == person.id,
            SeoContent.published.is_(True),
        )
        .first()
    )

    return PublicPersonDetailOut(
        slug=person.slug,
        full_name=person.full_name,
        stage_name=person.stage_name,
        birth_date=person.birth_date.isoformat() if person.birth_date else None,
        death_date=person.death_date.isoformat() if person.death_date else None,
        birth_place=person.birth_place,
        bio_short=person.bio_short,
        wikipedia_url=person.wikipedia_url,
        wikidata_id=person.wikidata_id,
        image_url=person.image_url,
        image_attribution=person.image_attribution,
        image_license=person.image_license,
        image_source_url=person.image_source_url,
        memberships=memberships,
        seo_body=seo.body_md if seo else None,
        seo_meta_title=seo.meta_title if seo else None,
        seo_meta_description=seo.meta_description if seo else None,
        schema_jsonld=seo.schema_jsonld if seo else None,
    )


class PublicPostListItem(BaseModel):
    slug: str
    kind: str
    title: str
    excerpt: str | None = None
    hero_image_url: str | None = None
    published_at: datetime


class PublicPostDetail(PublicPostListItem):
    body_md: str
    meta_title: str | None = None
    meta_description: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    anniversary_year: int | None = None


@router.get("/posts", response_model=list[PublicPostListItem])
def public_posts_list(
    response: Response,
    db: Session = Depends(get_db),
    limit: int = 30,
) -> list[PublicPostListItem]:
    _set_cache(response)
    rows = (
        db.query(Post)
        .filter(Post.status == "published")
        .order_by(Post.published_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return [
        PublicPostListItem(
            slug=p.slug,
            kind=p.kind,
            title=p.title,
            excerpt=p.excerpt,
            hero_image_url=p.hero_image_url,
            published_at=p.published_at,
        )
        for p in rows
    ]


@router.get("/posts/{slug}", response_model=PublicPostDetail)
def public_post_detail(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
) -> PublicPostDetail:
    _set_cache(response)
    p = (
        db.query(Post)
        .filter(Post.slug == slug, Post.status == "published")
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    return PublicPostDetail(
        slug=p.slug,
        kind=p.kind,
        title=p.title,
        excerpt=p.excerpt,
        hero_image_url=p.hero_image_url,
        published_at=p.published_at,
        body_md=p.body_md,
        meta_title=p.meta_title,
        meta_description=p.meta_description,
        source_url=p.source_url,
        source_name=p.source_name,
        anniversary_year=p.anniversary_year,
    )


# --------------------------------------------------------------------------- #
# Newsletter (Fase 3): suscripción doble opt-in
# --------------------------------------------------------------------------- #
import logging  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
from datetime import timezone  # noqa: E402

from app.db.models import Subscriber  # noqa: E402
from app.services.email import (  # noqa: E402
    EmailError,
    render_newsletter_confirm_email,
    send_email,
)
from app.services.newsletter import dispatch_to_subscriber  # noqa: E402

logger = logging.getLogger(__name__)


def _site_url() -> str:
    import os
    return os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")


class NewsletterSubscribeIn(BaseModel):
    email: str
    source: str | None = None


class NewsletterSubscribeOut(BaseModel):
    status: str  # 'pending_confirmation' | 'already_subscribed' | 'invalid_email'
    message: str


class NewsletterStatusOut(BaseModel):
    status: str
    message: str


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@router.post("/newsletter/subscribe", response_model=NewsletterSubscribeOut)
def newsletter_subscribe(
    body: NewsletterSubscribeIn,
    db: Session = Depends(get_db),
) -> NewsletterSubscribeOut:
    """Form de suscripción → crea pending + email de confirmación.

    Idempotente: si el email ya está confirmed, devolvemos status
    'already_subscribed' sin re-enviar. Si está pending o unsubscribed,
    regeneramos el confirm_token y reenviamos confirmación.
    """
    email = (body.email or "").strip().lower()
    if not email or not _EMAIL_RE.match(email) or len(email) > 256:
        return NewsletterSubscribeOut(
            status="invalid_email", message="Email no válido.",
        )

    row = db.query(Subscriber).filter(Subscriber.email == email).first()
    confirm_token = secrets.token_urlsafe(32)

    if row:
        if row.status == "confirmed":
            return NewsletterSubscribeOut(
                status="already_subscribed",
                message="Ya estás suscrito · gracias.",
            )
        # pending / unsubscribed / bounced → regeneramos token y reenviamos.
        row.confirm_token = confirm_token
        row.status = "pending"
        row.subscribed_at = datetime.now(timezone.utc)
        row.unsubscribed_at = None
        row.source = body.source or row.source
    else:
        row = Subscriber(
            email=email,
            status="pending",
            confirm_token=confirm_token,
            unsubscribe_token=secrets.token_urlsafe(32),
            source=body.source,
        )
        db.add(row)
    db.commit()

    confirm_url = f"{_site_url()}/newsletter/confirmar?token={confirm_token}"
    html, text = render_newsletter_confirm_email(confirm_url)
    try:
        send_email(
            to=email,
            subject="Confirma tu suscripción · Entre Interiores",
            html=html,
            text=text,
        )
    except EmailError as e:
        # No bloqueamos al usuario: la fila queda pending, podrá reintentar.
        logger.warning("Newsletter subscribe email failed for %s: %s", email, e)

    return NewsletterSubscribeOut(
        status="pending_confirmation",
        message="Te hemos enviado un email para confirmar.",
    )


@router.get("/newsletter/confirm", response_model=NewsletterStatusOut)
def newsletter_confirm(
    token: str,
    db: Session = Depends(get_db),
) -> NewsletterStatusOut:
    row = db.query(Subscriber).filter(Subscriber.confirm_token == token).first()
    if not row:
        return NewsletterStatusOut(status="invalid_token", message="Enlace no válido o caducado.")
    if row.status == "confirmed":
        return NewsletterStatusOut(status="already_confirmed", message="Tu suscripción ya estaba activa.")
    row.status = "confirmed"
    row.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    # Disparo inmediato: si hay entradas publicadas pendientes para este
    # subscriber, le mandamos el digest ahora — no tiene que esperar al cron.
    # Cualquier fallo de envío se loguea pero no rompe la confirmación.
    try:
        sent = dispatch_to_subscriber(db, row)
        db.commit()
        if sent:
            return NewsletterStatusOut(
                status="confirmed",
                message=(
                    "¡Listo! Te acabamos de mandar el contenido más reciente "
                    "al email. Te llegarán las próximas entradas en cuanto se "
                    "publiquen."
                ),
            )
    except Exception as e:
        logger.warning("Confirm dispatch failed for %s: %s", row.email, e)

    return NewsletterStatusOut(
        status="confirmed",
        message="¡Listo! Te llegarán las nuevas entradas del diario.",
    )


@router.get("/newsletter/unsubscribe", response_model=NewsletterStatusOut)
def newsletter_unsubscribe(
    token: str,
    db: Session = Depends(get_db),
) -> NewsletterStatusOut:
    row = db.query(Subscriber).filter(Subscriber.unsubscribe_token == token).first()
    if not row:
        return NewsletterStatusOut(status="invalid_token", message="Enlace no válido.")
    if row.status == "unsubscribed":
        return NewsletterStatusOut(status="already_unsubscribed", message="Ya estabas dado de baja.")
    row.status = "unsubscribed"
    row.unsubscribed_at = datetime.now(timezone.utc)
    db.commit()
    return NewsletterStatusOut(
        status="unsubscribed",
        message="Te hemos dado de baja. Sin preguntas. Si te arrepientes, vuelve cuando quieras.",
    )


# --------------------------------------------------------------------------- #
# Admin action via mail (one-click approve/reject)
# --------------------------------------------------------------------------- #
from fastapi.responses import HTMLResponse  # noqa: E402

from app.services.auth import decode_admin_action_token  # noqa: E402


def _render_admin_action_page(message: str, *, success: bool) -> str:
    color = "#ede4d3" if success else "#e85050"
    accent_border = "#a83a3a"
    return f"""\
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>{'Acción completada' if success else 'No se pudo'} · Entre Interiores</title>
<style>
body {{ margin:0; padding:48px 24px; background:#0d0b0a; color:#ede4d3;
       font-family:Georgia,serif; }}
.box {{ max-width:560px; margin:0 auto; padding:32px;
       border:1px solid rgba(237,228,211,0.1); background:rgba(237,228,211,0.02); }}
.tag {{ font-family:'Courier New',monospace; font-size:10px; letter-spacing:3px;
       text-transform:uppercase; color:{accent_border}; margin:0 0 16px; }}
.msg {{ font-size:22px; color:{color}; line-height:1.4; margin:0 0 24px; }}
a {{ display:inline-block; padding:12px 24px; border:1px solid {accent_border};
     color:{accent_border}; text-decoration:none;
     font-family:'Courier New',monospace; font-size:11px; letter-spacing:3px;
     text-transform:uppercase; }}
</style>
</head>
<body>
<div class="box">
<p class="tag">entre interiores · acción admin</p>
<p class="msg">{message}</p>
<a href="/biblioteca/admin/posts">Ir al panel</a>
</div>
</body>
</html>"""


@router.get("/admin-action", response_class=HTMLResponse)
def admin_action(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """One-click desde el email de revisión. Token JWT firmado con
    {post_id, action} y purpose='admin_action'. Idempotente: si el post
    ya está en el estado destino, no rompe, solo informa."""
    data = decode_admin_action_token(token)
    if not data:
        return HTMLResponse(
            _render_admin_action_page(
                "Enlace inválido o caducado.", success=False
            ),
            status_code=400,
        )
    post = db.query(Post).filter(Post.id == data["post_id"]).first()
    if post is None:
        return HTMLResponse(
            _render_admin_action_page("Post no encontrado.", success=False),
            status_code=404,
        )

    if data["action"] == "approve":
        if post.status == "published":
            return HTMLResponse(
                _render_admin_action_page(
                    f"«{post.title}» ya estaba publicado.", success=True,
                )
            )
        if post.status == "rejected":
            return HTMLResponse(
                _render_admin_action_page(
                    f"«{post.title}» había sido rechazado. No lo publico.",
                    success=False,
                ),
                status_code=409,
            )
        from app.services.publishing import auto_publish_post  # lazy
        auto_publish_post(db, post)
        return HTMLResponse(
            _render_admin_action_page(
                f"✓ Publicado: «{post.title}»", success=True,
            )
        )

    # action == "reject"
    if post.status == "rejected":
        return HTMLResponse(
            _render_admin_action_page(
                f"«{post.title}» ya estaba rechazado.", success=True,
            )
        )
    if post.status == "published":
        return HTMLResponse(
            _render_admin_action_page(
                f"«{post.title}» ya está publicado. Despublica desde el panel.",
                success=False,
            ),
            status_code=409,
        )
    post.status = "rejected"
    db.commit()
    return HTMLResponse(
        _render_admin_action_page(
            f"✗ Rechazado: «{post.title}»", success=True,
        )
    )
