"""Atribuye cada keyword del universo a SU asset propietario.

    python -m scripts.seo.kw_attribute --run ola1-discos-v2

Por qué hace falta: el cierre transitivo arranca en un disco pero converge al
universo global de la banda. Medido — el research de «La ley innata» acababa
conteniendo clusters de «so payaso», «si te vas» y «la vereda de la puerta de
atrás», que son de *Agila*. Los 16 CSV salían casi idénticos y la
individualización que se pedía se perdía.

Regla de atribución, de lo más específico a lo más genérico:

  1. menciona el título de una CANCIÓN  → dueña la canción (y su disco por herencia)
  2. menciona el título de un DISCO     → dueño el disco
  3. solo marca genérica                → dueño el hub del artista

Gana siempre el título más largo que case, que es el más específico: «extremoduro
la vereda de la puerta de atrás» es de esa canción, no del hub, aunque contenga
«extremoduro».

Esto es a la vez el research individualizado y la defensa anti-canibalización:
cada keyword tiene UN dueño, así que dos páginas nunca compiten por ella.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db.models import Album, Artist, Song
from app.db.session import SessionLocal
from app.services.kw_normalize import kw_norm, strip_title_suffix

ROOT = Path("/app/kw_out")

SALIDA = [
    "owner_type", "owner_slug", "owner_title", "owner_url", "album_slug",
    "cluster_id", "cluster_label", "is_head", "keyword", "match_title",
    "volume_best", "volume_dataforseo", "volume_ahrefs", "volume_sources",
    "difficulty", "cpc", "intent_api", "intent_lex", "n_words",
    "discovered_round", "providers", "evidence_ref",
]


def build_index() -> tuple[list[tuple[str, dict]], dict[str, dict]]:
    """(títulos ordenados de más largo a más corto, hubs de artista)."""
    db = SessionLocal()
    try:
        entradas: list[tuple[str, dict]] = []
        hubs: dict[str, dict] = {}

        for artist in db.execute(select(Artist)).scalars():
            hubs[artist.slug] = {
                "owner_type": "artist", "owner_slug": artist.slug,
                "owner_title": artist.name, "owner_url": f"/{artist.slug}",
                "album_slug": "",
            }

        rows = db.execute(select(Album, Artist).join(Artist, Album.artist_id == Artist.id)).all()
        albumes = {}
        for album, artist in rows:
            albumes[album.id] = (album, artist)
            norm = kw_norm(strip_title_suffix(album.title))
            if norm:
                entradas.append((norm, {
                    "owner_type": "album", "owner_slug": album.slug,
                    "owner_title": album.title, "artist_slug": artist.slug,
                    "owner_url": f"/{artist.slug}/{album.slug}",
                    "album_slug": album.slug,
                }))

        srows = db.execute(select(Song, Album, Artist)
                           .join(Album, Song.album_id == Album.id)
                           .join(Artist, Album.artist_id == Artist.id)).all()
        for song, album, artist in srows:
            norm = kw_norm(strip_title_suffix(song.title or ""))
            # Los títulos de una sola palabra corta («Salir», «Puta», «Ama») no
            # atribuyen: casarían con media lengua. Caen al disco o al hub.
            if not norm or (len(norm) < 8 and len(norm.split()) == 1):
                continue
            entradas.append((norm, {
                "owner_type": "song", "owner_slug": song.slug,
                "owner_title": song.title, "artist_slug": artist.slug,
                "owner_url": f"/{artist.slug}/{album.slug}/{song.slug}",
                "album_slug": album.slug,
            }))

        # Más largo primero: el título más específico gana.
        entradas.sort(key=lambda e: -len(e[0]))
        return entradas, hubs
    finally:
        db.close()


def dueno(keyword: str, entradas, hubs) -> tuple[dict, str]:
    norm = kw_norm(keyword)
    for titulo, info in entradas:
        if titulo in norm:
            return info, titulo
    # Sin título: es del hub de la marca que mencione.
    for slug, hub in hubs.items():
        if slug in norm or kw_norm(hub["owner_title"]) in norm:
            return hub, f"(marca:{slug})"
    return hubs.get("extremoduro", next(iter(hubs.values()))), "(sin atribuir)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    src = ROOT / args.run / "entregable" / "master.csv"
    if not src.exists():
        print(f"No existe {src}. Lanza antes kw_merge.")
        return 1

    entradas, hubs = build_index()
    print(f"Índice de atribución: {len(entradas)} títulos, {len(hubs)} hubs.")

    # El universo es la UNIÓN de todos los discos, deduplicada por keyword.
    universo: dict[str, dict] = {}
    for r in csv.DictReader(src.open(encoding="utf-8")):
        k = kw_norm(r["keyword"])
        prev = universo.get(k)
        if prev is None:
            universo[k] = r
            continue
        # Conserva la observación con más información (más fuentes y volumen).
        if len(r.get("volume_sources") or "") > len(prev.get("volume_sources") or ""):
            universo[k] = r

    print(f"Universo deduplicado: {len(universo)} keywords únicas "
          f"(de {sum(1 for _ in csv.DictReader(src.open(encoding='utf-8')))} filas).")

    por_owner: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in universo.values():
        info, titulo = dueno(r["keyword"], entradas, hubs)
        fila = {
            "owner_type": info["owner_type"], "owner_slug": info["owner_slug"],
            "owner_title": info["owner_title"], "owner_url": info["owner_url"],
            "album_slug": info.get("album_slug", ""),
            "cluster_id": r.get("cluster_id", ""),
            "cluster_label": r.get("cluster_label", ""),
            "is_head": r.get("is_head", ""),
            "keyword": r["keyword"], "match_title": titulo,
            "volume_best": r.get("volume_best", ""),
            "volume_dataforseo": r.get("volume_dataforseo", ""),
            "volume_ahrefs": r.get("volume_ahrefs", ""),
            "volume_sources": r.get("volume_sources", ""),
            "difficulty": r.get("difficulty", ""), "cpc": r.get("cpc", ""),
            "intent_api": r.get("intent_api", ""), "intent_lex": r.get("intent_lex", ""),
            "n_words": r.get("n_words", ""),
            "discovered_round": r.get("discovered_round", ""),
            "providers": r.get("providers", ""),
            "evidence_ref": r.get("evidence_ref", ""),
        }
        por_owner[(info["owner_type"], info["owner_slug"])].append(fila)

    out = ROOT / args.run / "atribuido"
    (out / "by-owner").mkdir(parents=True, exist_ok=True)

    vol = lambda r: int(r["volume_best"] or 0)  # noqa: E731
    with (out / "master.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SALIDA)
        w.writeheader()
        for key in sorted(por_owner, key=lambda k: -sum(vol(r) for r in por_owner[k])):
            w.writerows(sorted(por_owner[key], key=lambda r: -vol(r)))

    resumen = []
    for (otype, oslug), filas in sorted(
        por_owner.items(), key=lambda kv: -sum(vol(r) for r in kv[1])
    ):
        filas.sort(key=lambda r: -vol(r))
        with (out / "by-owner" / f"{otype}__{oslug}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as fh:
            w = csv.DictWriter(fh, fieldnames=SALIDA)
            w.writeheader()
            w.writerows(filas)
        resumen.append({
            "tipo": otype, "slug": oslug, "titulo": filas[0]["owner_title"],
            "url": filas[0]["owner_url"], "keywords": len(filas),
            "con_volumen": sum(1 for r in filas if vol(r) > 0),
            "volumen_total": sum(vol(r) for r in filas),
            "con_ahrefs": sum(1 for r in filas if r["volume_ahrefs"]),
        })

    (out / "resumen.json").write_text(
        json.dumps({"run": args.run, "universo": len(universo),
                    "owners": len(por_owner), "detalle": resumen},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'ASSET':<52} {'KWS':>6} {'C/VOL':>6} {'VOLUMEN':>9}")
    print("-" * 78)
    for r in resumen[:26]:
        print(f"{r['tipo'] + ':' + r['slug']:<52} {r['keywords']:>6} "
              f"{r['con_volumen']:>6} {r['volumen_total']:>9,}".replace(",", "."))
    print("-" * 78)
    print(f"{len(universo)} keywords únicas repartidas en {len(por_owner)} assets.")
    print(f"Salida: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
