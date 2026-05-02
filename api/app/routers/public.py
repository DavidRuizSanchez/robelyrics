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

from fastapi import APIRouter, HTTPException, Response, Depends
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Line, Song
from app.db.session import get_db

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


class PublicArtistDetailOut(PublicArtistOut):
    albums: list[PublicAlbumOut]
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None


class PublicAlbumDetailOut(PublicAlbumOut):
    artist: PublicArtistOut
    tracks: list[PublicTrackOut]
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None


class PublicSongDetailOut(BaseModel):
    slug: str
    title: str
    track_number: int | None
    artist: PublicArtistOut
    album: PublicAlbumOut
    snippet: list[str]                # máx. MAX_SNIPPET_LINES
    snippet_attribution: str          # texto de cita
    genius_url: str | None
    youtube_id: str | None = None
    seo_body: str | None = None
    seo_meta_title: str | None = None
    seo_meta_description: str | None = None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _try_get_seo(db: Session, entity_type: str, entity_id: int) -> dict | None:
    """Lee `seo_content` si la tabla existe y hay fila publicada. Si la tabla
    aún no se ha creado (Fase F.5), devuelve None silenciosamente.

    Esto evita 500 antes de que se aplique la migración correspondiente.
    """
    from sqlalchemy import text
    try:
        row = db.execute(
            text(
                "SELECT body_md, meta_title, meta_description "
                "FROM seo_content "
                "WHERE entity_type = :et AND entity_id = :eid AND published = true "
                "LIMIT 1"
            ),
            {"et": entity_type, "eid": entity_id},
        ).first()
    except Exception:
        # Tabla no existe todavía (pre-F.5). Silencioso.
        db.rollback()
        return None
    if not row:
        return None
    return {
        "body_md": row[0],
        "meta_title": row[1],
        "meta_description": row[2],
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
        seo_body=seo["body_md"] if seo else None,
        seo_meta_title=seo["meta_title"] if seo else None,
        seo_meta_description=seo["meta_description"] if seo else None,
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
    )


class PublicSearchHit(BaseModel):
    kind: str  # 'artist' | 'album' | 'song'
    slug: str
    title: str
    subtitle: str | None = None  # ej. "Extremoduro · 1996" para una canción


class PublicSearchOut(BaseModel):
    query: str
    results: list[PublicSearchHit]


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
        ))

    # Canciones
    songs = (
        db.query(Song, Album, Artist)
        .join(Album, Song.album_id == Album.id)
        .join(Artist, Album.artist_id == Artist.id)
        .filter(Song.title.ilike(pattern))
        .order_by(Album.year, Song.track_number)
        .limit(20)
        .all()
    )
    for song, album, artist in songs:
        out.append(PublicSearchHit(
            kind="song", slug=song.slug, title=song.title,
            subtitle=f"{artist.name} · {album.title} ({album.year})",
        ))

    return PublicSearchOut(query=q, results=out)
