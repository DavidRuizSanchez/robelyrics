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
import re
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
            if not norm:
                continue
            # Los títulos de una sola palabra corta («Salir», «Puta», «Ama»)
            # casarían con media lengua, así que NO atribuyen por sí solos —
            # pero descartarlos del todo era peor: dejaba a esas canciones sin
            # una sola keyword propia, y son 8 del catálogo (puta, salir, mama,
            # golfa, tomás, decidí, pedrá, sucede). Ahora entran exigiendo que la
            # keyword nombre además al artista: «extremoduro puta» es suya,
            # «puta» a secas no.
            requiere_marca = len(norm) < 8 and len(norm.split()) == 1
            entradas.append((norm, {
                "owner_type": "song", "owner_slug": song.slug,
                "owner_title": song.title, "artist_slug": artist.slug,
                "owner_url": f"/{artist.slug}/{album.slug}/{song.slug}",
                "album_slug": album.slug,
                "requiere_marca": requiere_marca,
                "marca": kw_norm(artist.name or artist.slug),
                "artista_slug_norm": kw_norm(artist.slug),
            }))

        # Más largo primero: el título más específico gana.
        entradas.sort(key=lambda e: -len(e[0]))
        return entradas, hubs
    finally:
        db.close()


def _menciona_marca(norm: str, info: dict) -> bool:
    marca = info.get("marca") or ""
    slug = info.get("artista_slug_norm") or ""
    return bool((marca and marca in norm) or (slug and slug in norm))


def cargar_traccion() -> dict[str, tuple[int, float]]:
    """Por URL: (impresiones, mejor posición) de las últimas 12 semanas.

    Es el árbitro para decidir qué versión de una canción se queda la keyword
    genérica. Un criterio de escritorio («la de estudio», «la del slug corto»)
    puede contradecir lo que Google ya está haciendo; esto no.
    """
    for ruta in (Path("/app/data/gsc_page_queries.json"),
                 Path(__file__).resolve().parents[3] / "data" / "gsc_page_queries.json"):
        if not ruta.exists():
            continue
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out = {}
        for url, queries in (data.get("pages") or {}).items():
            if not queries:
                continue
            out[url.rstrip("/")] = (
                sum(int(q.get("impressions", 0)) for q in queries),
                min((float(q["position"]) for q in queries if q.get("position")),
                    default=999.0),
            )
        return out
    return {}


def _desempatar(norm: str, candidatos: list[dict],
                traccion: dict[str, tuple[int, float]] | None = None) -> dict:
    """Varias versiones de la MISMA canción casan con el título. ¿De cuál es?

    `strip_title_suffix` colapsa «Jesucristo García (Rock Transgresivo)» y
    «Jesucristo García (En Directo)» al mismo texto que la de estudio, así que
    las tres compiten por cada keyword. Antes ganaba la primera de la lista —un
    accidente del orden de inserción— y las otras se quedaban a cero PARA
    SIEMPRE: por eso `song__jesucristo-garcia` no tenía CSV y sí lo tenía la
    versión con sufijo.

    El desempate mira lo que la propia keyword dice: si nombra el directo, es de
    la versión en vivo; si nombra un disco, es la de ese disco; si no dice nada,
    se queda con la de estudio (la que no lleva sufijo en el slug), que es la que
    la gente busca por defecto.
    """
    if len(candidatos) == 1:
        return candidatos[0]
    quiere_directo = bool(re.search(r"\ben directo\b|\bdirecto\b|\bvivo\b", norm))
    en_vivo = [c for c in candidatos if "en-directo" in c["owner_slug"]]
    if quiere_directo and en_vivo:
        return en_vivo[0]
    # La keyword nombra un disco concreto → esa versión.
    for c in candidatos:
        album = kw_norm(strip_title_suffix(c.get("album_slug", "").replace("-", " ")))
        if album and album in norm:
            return c
    # Keyword genérica: se la queda la versión que Google YA posiciona mejor.
    # Medido el 03-08-2026 con las tres «Jesucristo García»: las tres competían
    # por «jesucristo garcía significado» —el directo en pos 9,1, el debut en
    # 6,9— y la de Rock Transgresivo no tenía ni una impresión. Repartirlas por
    # un criterio de escritorio habría contradicho el dato.
    if traccion:
        con_datos = [(traccion.get(c["owner_url"].rstrip("/")), c) for c in candidatos]
        con_datos = [(t, c) for t, c in con_datos if t]
        if con_datos:
            # Manda el VOLUMEN que ya recibe, no la posición: una página con 7
            # impresiones en la posición 9 tiene más tracción real que otra con
            # 1 en la posición 6, y es sobre la primera donde el trabajo rinde.
            # La posición solo desempata.
            con_datos.sort(key=lambda par: (-par[0][0], par[0][1]))
            return con_datos[0][1]
    # Sin señal en la keyword: gana el slug más corto, que es el que no lleva
    # sufijo de desambiguación («jesucristo-garcia» antes que
    # «jesucristo-garcia-rock-transgresivo»). Es un criterio neutro y estable —
    # no depende del orden de inserción— y deja la keyword genérica en la ficha
    # con el nombre más limpio, que es la que la gente busca.
    de_estudio = [c for c in candidatos if "en-directo" not in c["owner_slug"]]
    return sorted(de_estudio or candidatos, key=lambda c: len(c["owner_slug"]))[0]


def dueno(keyword: str, entradas, hubs, traccion=None) -> tuple[dict, str]:
    norm = kw_norm(keyword)
    for titulo, _ in entradas:
        if titulo not in norm:
            continue
        # Todas las entradas con ESTE título compiten: son versiones del mismo
        # tema. Se recogen todas antes de decidir, en vez de coger la primera.
        candidatos = [i for t, i in entradas if t == titulo]
        elegibles = [c for c in candidatos
                     if not c.get("requiere_marca") or _menciona_marca(norm, c)]
        if not elegibles:
            continue        # título corto sin marca: no es suyo, sigue buscando
        return _desempatar(norm, elegibles, traccion), titulo
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

    traccion = cargar_traccion()
    if traccion:
        print(f"Tracción real de GSC cargada: {len(traccion)} URLs con datos. "
              "Desempata qué versión de una canción se queda lo genérico.")
    else:
        print("Sin datos de GSC: el desempate entre versiones caerá al slug más "
              "corto. Refresca con scripts.seo.gsc_fetch_page_queries.")

    por_owner: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in universo.values():
        info, titulo = dueno(r["keyword"], entradas, hubs, traccion)
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
