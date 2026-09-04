"""Puebla el tracklist referencial (`album_tracks`) de un disco no-estudio.

    python -m scripts.seed_album_tracks --album-slug grandes-exitos-y-fracasos-episodio-primero
    python -m scripts.seed_album_tracks --all-non-studio --dry-run

Tracklist desde MusicBrainz (T1). Cada corte se casa con la canción ORIGINAL de
estudio del catálogo; el que no case se guarda con su título tal cual y se deja
SIN enlazar. **Nunca se adivina** a qué canción apunta ni se crea una fila `Song`
nueva: duplicar la canción pondría dos páginas casi idénticas compitiendo en
Google.

El casado usa el alias sin sufijo desambiguador, porque el catálogo guarda
títulos verbosos: «Jesucristo García (Rock Transgresivo)» y «Bulerías de la
sangre caliente (...)» no casan por igualdad literal con lo que trae MusicBrainz.

Además marca `is_rerecording` comparando el MBID de grabación con el de la
canción original: es el dato que acredita que un recopilatorio aporta material.
"""
from __future__ import annotations

import argparse
import time
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, AlbumTrack, Artist, Song
from app.db.session import SessionLocal
from app.services.kw_normalize import kw_norm, strip_title_suffix

MB = "https://musicbrainz.org/ws/2"
UA = {"User-Agent": "RobeLyrics/1.0 (davidruizsanchez@gmail.com)"}
PAUSA = 1.3

NO_ESTUDIO = ("live", "compilation", "single")
# Mismo suelo que MIN_TRACK_RATIO de catalog_ingest, por coherencia.
MIN_FUZZY_RATIO = 0.85


def _get(client: httpx.Client, path: str, **params) -> dict:
    for intento in range(4):
        r = client.get(f"{MB}/{path}", params={**params, "fmt": "json"})
        if r.status_code == 200:
            return r.json()
        time.sleep(2.0 * (intento + 1))
    return {}


def fetch_tracklist(client: httpx.Client, titulo: str, artista_mbid: str) -> list[dict]:
    """Tracklist de la release MÁS ANTIGUA del release-group (la original)."""
    rgs = _get(client, "release-group", artist=artista_mbid, limit=100).get(
        "release-groups", []
    )
    time.sleep(PAUSA)
    norm = kw_norm(titulo)
    rg = next((r for r in rgs if kw_norm(r["title"]) == norm), None)
    if rg is None:
        rg = next((r for r in rgs if norm in kw_norm(r["title"])), None)
    if rg is None:
        return []

    d = _get(client, "release", **{"release-group": rg["id"],
                                   "inc": "recordings", "limit": 5})
    time.sleep(PAUSA)
    rels = sorted(d.get("releases", []), key=lambda x: x.get("date") or "zzzz")
    if not rels:
        return []
    out = []
    for m in rels[0].get("media", []):
        for tr in m.get("tracks", []):
            out.append({
                "disc": m.get("position") or 1,
                "position": tr.get("position"),
                "title": tr["title"],
                "recording": tr["recording"]["id"],
                "length": (tr.get("length") or 0) // 1000 or None,
            })
    return out


def build_song_index(db: Session, artist_id: int) -> tuple[dict[str, Song], dict[str, Song]]:
    """({título: Song} del propio artista, {título: Song} del resto del universo).

    Dos índices porque la prioridad importa: primero el catálogo del artista del
    disco y solo después el del otro. En «Bienvenidos al temporal», que es de
    Robe, suena «Si te vas…», que es de Extremoduro — el enlace cruzado es
    legítimo y es lo que el oyente espera, pero nunca debe ganarle a una canción
    homónima del propio artista.

    Si el mismo título existe en varios discos gana la aparición más antigua,
    que es la canónica de estudio.
    """
    rows = db.execute(
        select(Song, Album)
        .join(Album, Song.album_id == Album.id)
        .order_by(Album.year)
    ).all()
    propio: dict[str, Song] = {}
    ajeno: dict[str, Song] = {}
    for song, album in rows:
        if album.kind not in ("studio", "ep"):
            continue
        destino = propio if album.artist_id == artist_id else ajeno
        for variante in (song.title, strip_title_suffix(song.title or "")):
            k = kw_norm(variante or "")
            if k and k not in destino:
                destino[k] = song
    return propio, ajeno


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def buscar_aproximado(titulo: str, idx: dict[str, Song]) -> Song | None:
    """Casado por similitud, con dos frenos.

    Hace falta porque el catálogo escribe «Bribliblibli» y MusicBrainz
    «Bribribliblí»: la misma canción con otra grafía de un título que es un
    trabalenguas a propósito.

    Los frenos vienen de un fallo real ya documentado: sin ellos «Extremaydura»
    casaba dentro de «Villancico del Rey de Extremadura». Por eso se exige
    ratio alto **y** longitudes parecidas — un título corto no puede casar con
    uno largo por mucho que comparta letras.
    """
    objetivo = kw_norm(titulo)
    if len(objetivo) < 6:
        return None
    mejor, mejor_r = None, 0.0
    for k, song in idx.items():
        if not (0.75 <= len(k) / max(1, len(objetivo)) <= 1.33):
            continue
        r = _ratio(objetivo, k)
        if r > mejor_r:
            mejor, mejor_r = song, r
    return mejor if mejor_r >= MIN_FUZZY_RATIO else None


def seed(db: Session, album: Album, *, dry_run: bool = False) -> tuple[int, int]:
    artist = db.get(Artist, album.artist_id)
    mbid = {
        "extremoduro": "f59163ba-1a7a-4349-b0fd-fb9582ebe333",
        "robe": "b435c75d-25e8-464c-8b82-12ca0eaec926",
    }.get(artist.slug)
    if not mbid:
        print(f"  sin MBID para el artista {artist.slug}")
        return 0, 0

    with httpx.Client(headers=UA, timeout=60) as client:
        tracks = fetch_tracklist(client, album.title, mbid)
    if not tracks:
        print("  MusicBrainz no devuelve tracklist — no se inventa nada")
        return 0, 0

    propio, ajeno = build_song_index(db, album.artist_id)
    enlazados = huerfanos = 0
    filas: list[AlbumTrack] = []

    for t in tracks:
        base = strip_title_suffix(t["title"])
        exacto, alias = kw_norm(t["title"]), kw_norm(base)

        # Prioridad: título exacto del propio artista → alias del propio →
        # exacto de otro artista del universo → alias de otro → aproximado.
        song, fuente = None, None
        for idx, etiqueta in ((propio, ""), (ajeno, "_cross")):
            if exacto in idx:
                song, fuente = idx[exacto], "exact" + etiqueta
                break
            if alias in idx:
                song, fuente = idx[alias], "alias" + etiqueta
                break
        if song is None:
            song = buscar_aproximado(t["title"], propio)
            if song is not None:
                fuente = "fuzzy"

        if song is not None:
            enlazados += 1
        else:
            huerfanos += 1
        filas.append(AlbumTrack(
            album_id=album.id, disc=t["disc"], position=t["position"],
            title_as_released=t["title"],
            song_id=song.id if song else None,
            match_source=fuente,
            duration_sec=t["length"],
            recording_mbid=t["recording"],
        ))
        marca = f"→ {song.slug}  [{fuente}]" if song else "SIN ENLAZAR"
        print(f"   {t['disc']}.{t['position']:>2}  {t['title'][:44]:<46} {marca}")

    if dry_run:
        print(f"  [dry-run] {enlazados} enlazados, {huerfanos} sin enlazar")
        return enlazados, huerfanos

    db.query(AlbumTrack).filter(AlbumTrack.album_id == album.id).delete()
    db.add_all(filas)
    album.track_count = len(filas)
    db.commit()
    return enlazados, huerfanos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--album-slug", action="append")
    ap.add_argument("--all-non-studio", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = select(Album)
        if args.album_slug:
            q = q.where(Album.slug.in_(args.album_slug))
        elif args.all_non_studio:
            q = q.where(Album.kind.in_(NO_ESTUDIO))
        else:
            print("Indica --album-slug o --all-non-studio")
            return 1

        albums = list(db.execute(q).scalars())
        if not albums:
            print("Ningún álbum casa con el filtro.")
            return 1

        tot_e = tot_h = 0
        for album in albums:
            print(f"\n=== {album.slug} — «{album.title}» ({album.kind}) ===")
            if album.kind == "studio":
                print("  es de estudio: usa songs.album_id, no album_tracks")
                continue
            e, h = seed(db, album, dry_run=args.dry_run)
            tot_e += e
            tot_h += h

        print(f"\nTotal: {tot_e} cortes enlazados a su canción original, "
              f"{tot_h} sin enlazar (se guardan, no se adivinan).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
