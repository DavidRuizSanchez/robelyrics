"""Alta VERIFICADA de un disco que falta en el catálogo (Eje C, de punta a punta).

Cuando el consenso detecta que una canción apareció por primera vez en un disco
que no tenemos ingerido, el hueco no se tapa con un dato: hay que dar de alta el
disco entero. Esto lo hace solo, pero únicamente cuando la certeza es total.

La certeza no es una corazonada: son SEIS puertas duras, y basta que falle una
para no tocar nada (y decirlo):

  1. MusicBrainz (T1) devuelve un release-group con score alto para ese título.
  2. El título casa (fuzzy ≥ 0.9) con el que afirmamos.
  3. El artista casa con el de la canción que abrió la errata.
  4. El año de MusicBrainz coincide con el que fijó el consenso de catálogo.
  5. El tracklist viene de MusicBrainz (nunca de un LLM) y no está vacío.
  6. La canción de la errata está EN ese tracklist (si no, no es el disco).

Las letras se traen de las mismas fuentes abiertas del consenso (LRCLIB,
letras.com). Una canción sin letra se crea igual, vacía y marcada: el disco y su
tracklist son verdad de catálogo aunque la letra no se haya podido bajar. Nunca
se rellena una letra "a ojo".

`data/` va montado read-only, así que el alta vive en BD; el servicio devuelve el
snippet YAML para versionarlo en `data/discography.yaml` (reproducibilidad).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx
from slugify import slugify
from sqlalchemy import select

from app.db.models import Album, Artist, Chunk, Line, Song
from app.services import consensus as mcv
from app.services.consensus import SourceRef
from app.services.lyric_guard import best_ratio, normalize

logger = logging.getLogger(__name__)

_MB = "https://musicbrainz.org/ws/2"
_HEADERS = {
    "User-Agent": "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com)",
    "Accept": "application/json",
}
# MusicBrainz pide 1 req/s. Lo respetamos (son 2 llamadas por disco).
_MB_PAUSE = 1.1

# Umbrales de las puertas duras.
MIN_MB_SCORE = 90
MIN_TITLE_RATIO = 0.9
MIN_TRACK_RATIO = 0.85


@dataclass
class AlbumEvidence:
    """Lo que MusicBrainz afirma de un disco. Dato duro, no interpretación."""

    mbid: str
    title: str
    year: int | None
    primary_type: str | None
    artist_name: str
    score: int
    release_mbid: str | None = None
    release_date: str | None = None
    tracks: list[dict] = field(default_factory=list)  # {position, title, length_ms}

    @property
    def url(self) -> str:
        return f"https://musicbrainz.org/release-group/{self.mbid}"


class AlbumNotCertain(Exception):
    """No se cumple alguna puerta: no se crea nada y se explica por qué."""


# --------------------------------------------------------------------------- #
# MusicBrainz
# --------------------------------------------------------------------------- #
def _mb_get(client: httpx.Client, path: str, params: dict, *, retries: int = 3) -> dict:
    """GET a MusicBrainz con reintentos: da timeouts sueltos y un disco no se deja
    de dar de alta porque la primera llamada tarde."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = client.get(f"{_MB}/{path}", params={**params, "fmt": "json"}, headers=_HEADERS)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(_MB_PAUSE * (attempt + 1))
    raise last if last else RuntimeError("MusicBrainz sin respuesta")


def find_release_group(title: str, artist: str) -> AlbumEvidence | None:
    """Busca el disco en MusicBrainz. Devuelve la mejor coincidencia o None."""
    query = f'artist:"{artist}" AND releasegroup:"{title}"'
    try:
        with httpx.Client(timeout=25) as client:
            data = _mb_get(client, "release-group", {"query": query, "limit": 5})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[catalog_ingest] MusicBrainz no responde: %s", exc)
        return None

    groups = sorted(data.get("release-groups") or [], key=lambda g: g.get("score", 0), reverse=True)
    if not groups:
        return None
    g = groups[0]
    date = (g.get("first-release-date") or "")[:4]
    credits = [c.get("artist", {}).get("name", "") for c in (g.get("artist-credit") or [])]
    return AlbumEvidence(
        mbid=g.get("id", ""),
        title=g.get("title", ""),
        year=int(date) if date.isdigit() else None,
        primary_type=g.get("primary-type"),
        artist_name=credits[0] if credits else "",
        score=int(g.get("score") or 0),
    )


def fetch_tracklist(ev: AlbumEvidence) -> AlbumEvidence:
    """Rellena el tracklist desde la edición MÁS ANTIGUA del release-group (la
    original, no la reedición). Mutar `ev` es intencionado: la evidencia crece."""
    time.sleep(_MB_PAUSE)
    try:
        with httpx.Client(timeout=25) as client:
            data = _mb_get(client, "release", {
                "release-group": ev.mbid, "inc": "recordings", "limit": 25,
            })
    except Exception as exc:  # noqa: BLE001
        logger.warning("[catalog_ingest] tracklist no disponible: %s", exc)
        return ev

    releases = data.get("releases") or []
    def _key(rel):
        d = (rel.get("date") or "9999")[:4]
        return int(d) if d.isdigit() else 9999
    releases.sort(key=_key)
    for rel in releases:
        tracks: list[dict] = []
        for medium in rel.get("media") or []:
            for t in medium.get("tracks") or []:
                tracks.append({
                    "position": t.get("position"),
                    "title": (t.get("title") or "").strip(),
                    "length_ms": t.get("length"),
                })
        if tracks:
            ev.tracks = tracks
            ev.release_mbid = rel.get("id")
            ev.release_date = rel.get("date")
            break
    return ev


# --------------------------------------------------------------------------- #
# Las seis puertas
# --------------------------------------------------------------------------- #
def certify(
    ev: AlbumEvidence | None,
    *,
    expected_title: str,
    expected_artist: str,
    expected_year: int | None,
    must_contain: str | None,
) -> AlbumEvidence:
    """Aplica las puertas duras. Lanza AlbumNotCertain con el motivo exacto."""
    if ev is None:
        raise AlbumNotCertain(f"MusicBrainz no encuentra ningún disco «{expected_title}» de {expected_artist}.")
    if ev.score < MIN_MB_SCORE:
        raise AlbumNotCertain(
            f"La coincidencia de MusicBrainz es floja (score {ev.score} < {MIN_MB_SCORE}): «{ev.title}»."
        )
    if best_ratio(normalize(expected_title), normalize(ev.title)) < MIN_TITLE_RATIO:
        raise AlbumNotCertain(
            f"MusicBrainz devuelve «{ev.title}», que no es «{expected_title}»."
        )
    if best_ratio(normalize(expected_artist), normalize(ev.artist_name)) < 0.8:
        raise AlbumNotCertain(
            f"El disco de MusicBrainz es de {ev.artist_name}, no de {expected_artist}."
        )
    if expected_year and ev.year and ev.year != expected_year:
        raise AlbumNotCertain(
            f"Discrepancia de año: el consenso fijó {expected_year} y MusicBrainz dice "
            f"{ev.year}. Con dos años distintos no se da nada de alta solo."
        )
    if not ev.tracks:
        raise AlbumNotCertain("MusicBrainz no da tracklist de ese disco: no me invento las canciones.")
    if must_contain:
        target = normalize(must_contain)
        hit = any(best_ratio(target, normalize(t["title"])) >= MIN_TRACK_RATIO for t in ev.tracks)
        if not hit:
            raise AlbumNotCertain(
                f"«{must_contain}» no aparece en el tracklist de «{ev.title}»: no es el disco."
            )
    return ev


def build_consensus(ev: AlbumEvidence, *, expected_year: int | None) -> mcv.ConsensusResult:
    """Traza de consenso del alta: MusicBrainz (T1) + corroboración web si la hay."""
    year = ev.year or expected_year
    sources = [SourceRef(
        name=f"MusicBrainz · {ev.title}", source_kind="musicbrainz", stance="supports",
        value=str(year), url=ev.url,
        quote=f"{ev.primary_type or 'Album'} de {ev.artist_name}, {len(ev.tracks)} cortes.",
    )]
    try:
        from app.services.web_verify import classify_fact

        res = classify_fact(
            f"El disco «{ev.title}» de {ev.artist_name} se publicó en {year} "
            f"y contiene {len(ev.tracks)} canciones."
        )
        src = (res.get("source") or "").lower()
        kind = "wikipedia" if "wiki" in src else "google_serp"
        if res.get("verdict") == "supported":
            sources.append(SourceRef(name=f"web:{res.get('source') or 'web'}", source_kind=kind,
                                     stance="supports", value=str(year),
                                     quote=(res.get("evidence") or "")[:200]))
        elif res.get("verdict") == "contradicted":
            sources.append(SourceRef(name=f"web:{res.get('source') or 'web'}", source_kind=kind,
                                     stance="contradicts", value="__OTHER__",
                                     quote=(res.get("evidence") or "")[:200]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[catalog_ingest] web_verify no disponible: %s", exc)

    return mcv.ConsensusResult(
        verdict="corrected", confidence=mcv.aggregate_confidence(sources, str(year)),
        current_value=None, correct_value=f"{ev.title} ({year})", sources=sources,
        rationale=f"Alta de disco ausente respaldada por MusicBrainz ({len(ev.tracks)} cortes).",
    )


# --------------------------------------------------------------------------- #
# Alta en BD
# --------------------------------------------------------------------------- #
def _pick_lyrics(title: str, artist: str) -> tuple[str | None, str, float | None]:
    """Letra de las fuentes abiertas. Devuelve (texto, source, confianza).
    Si dos fuentes coinciden, la confianza sube; si solo hay una, se marca como tal."""
    from app.services import lyric_fetchers

    got = lyric_fetchers.fetch_all(title, artist)
    if not got:
        return None, "", None
    kinds = list(got)
    if len(kinds) >= 2:
        a, b = normalize(got[kinds[0]]), normalize(got[kinds[1]])
        if a and b and best_ratio(a[:400], b) >= 0.9:
            return got[kinds[0]], "consensus", 0.9
    return got[kinds[0]], kinds[0][:16], 0.6


def create_album(
    db,
    ev: AlbumEvidence,
    *,
    artist_id: int,
    slug: str,
    kind: str = "studio",
    with_lyrics: bool = True,
) -> dict:
    """Crea el Album y sus Songs (tracklist de MusicBrainz) + letras si se pueden
    bajar. NO comitea: lo hace quien llama. Devuelve un resumen."""
    from scripts.ingest import make_chunks, segment_lines

    artist = db.get(Artist, artist_id)
    album = Album(
        artist_id=artist_id, title=ev.title, slug=slug,
        year=ev.year, kind=kind, track_count=len(ev.tracks),
    )
    if ev.release_date and len(ev.release_date) == 10:
        from datetime import date as _date
        try:
            album.release_date = _date.fromisoformat(ev.release_date)
            album.release_date_source = "musicbrainz"
        except ValueError:
            pass
    db.add(album)
    db.flush()

    created, with_text = 0, 0
    for i, t in enumerate(ev.tracks, start=1):
        title = t["title"]
        song = Song(
            album_id=album.id,
            track_number=t.get("position") or i,
            title=title,
            slug=slugify(title)[:240] or f"track-{i}",
            duration_sec=int(t["length_ms"] / 1000) if t.get("length_ms") else None,
            lyrics_source="musicbrainz",  # de momento solo el corte, sin letra
        )
        if with_lyrics:
            text, source, conf = _pick_lyrics(title, artist.name if artist else "Extremoduro")
            if text:
                song.lyrics_raw = text
                song.lyrics_clean = text
                song.lyrics_source = source or "lrclib"
                song.lyrics_confidence = conf
                with_text += 1
        db.add(song)
        db.flush()

        if song.lyrics_clean:
            rows = segment_lines(song.lyrics_clean)
            if rows:
                db.execute(Line.__table__.insert(), [{"song_id": song.id, **r} for r in rows])
                chunks = make_chunks(rows)
                if chunks:
                    db.execute(Chunk.__table__.insert(), [{"song_id": song.id, **c} for c in chunks])
        created += 1

    return {
        "album_id": album.id, "album_title": album.title, "year": album.year,
        "songs_created": created, "songs_with_lyrics": with_text,
    }


def bare_title(title: str) -> str:
    """«La Hoguera (Rock Transgresivo)» → «la hoguera». Quita el sufijo de versión
    entre paréntesis/corchetes y normaliza."""
    import re

    return normalize(re.sub(r"[\(\[].*?[\)\]]", "", title or ""))


def link_original_versions(db, album: Album, *, artist_id: int) -> int:
    """Marca `original_album_slug`/`original_year` en las OTRAS versiones (directo,
    recopilatorio, regrabación posterior) de las canciones del disco recién dado de
    alta. Verdad canónica que fact_check ya respeta.

    Dos cautelas que costaron caras en pruebas:
      - Título por IGUALDAD normalizada, no por solapamiento: con `best_ratio`,
        «Extremaydura» casaba dentro de «Villancico del Rey de Extremadura».
      - Solo se marca si el disco nuevo es ANTERIOR al que contiene la versión. Si
        la canción ya vive en un disco de estudio igual o más antiguo, su primera
        aparición NO es esta: no se toca (mejor un hueco que un dato falso).
    """
    titles = {bare_title(s.title) for s in db.execute(
        select(Song).where(Song.album_id == album.id)).scalars()}
    titles.discard("")
    if not titles or album.year is None:
        return 0
    others = db.execute(
        select(Song, Album).join(Album, Album.id == Song.album_id)
        .where(Album.artist_id == artist_id, Song.album_id != album.id)
    ).all()
    n = 0
    for song, host in others:
        if bare_title(song.title) not in titles:
            continue
        if host.year is not None and host.year <= album.year:
            continue  # el disco nuevo no es la primera aparición de esa versión
        if song.original_album_slug != album.slug or song.original_year != album.year:
            song.original_album_slug = album.slug
            song.original_year = album.year
            n += 1
    return n


def schedule_content_fill(album_slug: str) -> bool:
    """Lanza la generación de las fichas SEO del disco nuevo y sus canciones.

    Sin ficha, `/[artist]/[album]` responde 404 aunque el listado de discografía
    ya enlace el disco: dar de alta el catálogo sin esto deja enlaces rotos. Cada
    ficha cuesta ~2 min de motor profundo, así que va DESATENDIDO (el request no
    puede esperar) y el cron lo repesca si se corta. Devuelve True si arrancó."""
    import subprocess
    import sys

    try:
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "scripts.seo.fill_missing_content",
             "--album-slug", album_slug],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[catalog_ingest] no se pudo lanzar el relleno de fichas: %s", exc)
        return False


def yaml_snippet(ev: AlbumEvidence, slug: str, kind: str = "studio") -> str:
    """Entrada para versionar el alta en data/discography.yaml (montado read-only,
    así que esto se pega a mano en el repo y queda en git)."""
    lines = [
        f'      - slug: {slug}',
        f'        title: "{ev.title}"',
        f'        year: {ev.year}',
        f'        kind: {kind}',
    ]
    if ev.release_date and len(ev.release_date) == 10:
        lines.append(f'        release_date: {ev.release_date}')
    return "\n".join(lines)
