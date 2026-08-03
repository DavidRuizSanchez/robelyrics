"""Diagnóstico de huecos de UNA página, cruzando su keyword research con lo publicado.

    docker compose exec -T api python /app/skill_diagnose.py --asset album:agila
    ... --asset song:so-payaso --json

Responde a una pregunta concreta: **de todo lo que la gente busca sobre este
asset, ¿qué cubre ya la página y qué no?** Y sobre lo que no cubre, ¿hay material
real en el corpus para escribirlo, o sería paja?

No llama a ninguna API de pago: todo sale de datos ya descargados (el research en
`kw_out/`, GSC en `data/gsc_page_queries.json`, el corpus en la BD).

No escribe nada. La escritura la dispara después `augment_all --apply`, que tiene
el contrato de no-pérdida y el gate anti-paja.

Dos decisiones que lo separan de `gsc_optimize`:

- **Sin umbral de impresiones.** `gsc_optimize` exige 20 y por eso devuelve CERO
  oportunidades para `/extremoduro/agila`, cuya mejor query (`agila
  contraportada`, posición 8,0) tiene 6 impresiones. En un sitio de nicho lo
  valioso vive por debajo de ese umbral.
- **Agrupa por TEMÁTICA, no por keyword.** Una página no se optimiza para
  «agila contraportada»: se optimiza escribiendo sobre la portada del disco. La
  keyword es la señal, el bloque de contenido es la acción.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.db.models import Album, Artist, SeoContent, Song  # noqa: E402

KW_ROOT = Path(os.environ.get("KW_OUT", "/app/kw_out"))
GSC_PATH = Path("/app/data/gsc_page_queries.json")

# Familias temáticas. El orden importa: gana la primera que casa.
# Ver reference/exclusiones.md para el porqué de las tres excluidas.
TEMATICAS: list[tuple[str, str, bool]] = [
    # (nombre, patrón, incluida_por_defecto)
    ("Descarga y piratería",
     r"descarg|torrent|mega\b|mediafire|utorrent|\brar\b|320|flac|gratis|disco completo|album completo", False),
    ("Merchandising",
     r"camiset|sudader|taza|poster|tatuaj|parche|chapa", False),
    ("Ediciones físicas y compra",
     r"vinilo|\blp\b|\bcd\b|comprar|precio|fnac|amazon|segunda mano", False),
    ("Portada y arte",
     r"portada|contraportad|caratul|carátul|album cover|\bcover\b|artwork|diseñ", True),
    ("Significado y sentido",
     r"signific|que es|qué es|por que|por qué|explicac|interpretac|de que trata|de qué trata|de que habla", True),
    ("Letras", r"letra|lyrics", True),
    ("Acordes y tablatura", r"acorde|\btabs?\b|guitarra|bajo|tablatur|partitur", True),
    ("Tributo y versiones", r"tributo|versi[oó]n|cover band|homenaje|directo|en vivo", True),
    ("Tracklist y canciones", r"cancion|canción|tracklist|temas|lista de", True),
    ("Ficha técnica (año, sello, duración)",
     r"\baño\b|19\d\d|20\d\d|fecha|duraci|sello|discogr[aá]fic|productor|grabaci", True),
    ("Escucha (streaming, vídeo)", r"escuchar|youtube|spotify|v[ií]deo|online", True),
]

EXCLUIDAS_POR_DEFECTO = {n for n, _, inc in TEMATICAS if not inc}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ\s]", " ", s)).strip()


def clasificar(keyword: str) -> str:
    k = keyword.lower()
    for nombre, patron, _ in TEMATICAS:
        if re.search(patron, k):
            return nombre
    return "Navegacional (marca + título)"


def latest_run() -> Path | None:
    """El run de keyword research más reciente que tenga salida atribuida."""
    if not KW_ROOT.exists():
        return None
    runs = [d for d in KW_ROOT.iterdir() if (d / "atribuido" / "by-owner").is_dir()]
    return max(runs, key=lambda d: d.stat().st_mtime) if runs else None


def cargar_keywords(run: Path, asset_type: str, slug: str) -> list[dict]:
    import csv
    f = run / "atribuido" / "by-owner" / f"{asset_type}__{slug}.csv"
    if not f.exists():
        return []
    return list(csv.DictReader(f.open(encoding="utf-8")))


def cargar_gsc(url_path: str) -> tuple[list[dict], str]:
    """Queries reales de esta URL. SIN filtro de impresiones — a propósito.

    Devuelve (queries, periodo). El fichero anida las páginas bajo la clave
    `pages`; leerlo desde la raíz devolvía siempre vacío.
    """
    if not GSC_PATH.exists():
        return [], ""
    try:
        data = json.loads(GSC_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], ""
    pages = data.get("pages", data)
    per = data.get("period") or {}
    periodo = f"{per.get('start', '?')} → {per.get('end', '?')}"
    filas = pages.get(url_path) or pages.get(url_path.rstrip("/")) or []
    out = []
    for q in filas:
        out.append({
            "query": q.get("query") or (q.get("keys") or [""])[0],
            "impressions": q.get("impressions", 0),
            "clicks": q.get("clicks", 0),
            "position": q.get("position"),
        })
    return out, periodo


def resolver_asset(db, asset_type: str, slug: str):
    """Devuelve (entity, titulo, url_path) o (None, None, None)."""
    if asset_type == "album":
        row = db.execute(
            select(Album, Artist).join(Artist, Album.artist_id == Artist.id)
            .where(Album.slug == slug)
        ).first()
        if not row:
            return None, None, None
        a, ar = row
        return a, a.title, f"/{ar.slug}/{a.slug}"
    if asset_type == "song":
        row = db.execute(
            select(Song, Album, Artist)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
            .where(Song.slug == slug)
        ).first()
        if not row:
            return None, None, None
        s, al, ar = row
        return s, s.title, f"/{ar.slug}/{al.slug}/{s.slug}"
    if asset_type == "artist":
        a = db.execute(select(Artist).where(Artist.slug == slug)).scalar_one_or_none()
        return (a, a.name, f"/{a.slug}") if a else (None, None, None)
    return None, None, None


def cubre(body: str, tematica: str, keywords: list[str]) -> tuple[bool, str]:
    """¿El cuerpo publicado habla ya de esta temática?

    Heurística deliberadamente conservadora: se busca el vocabulario propio de la
    temática en el cuerpo, no la keyword literal. Una página cubre «Portada y
    arte» si habla de la portada, aunque nunca escriba «portada agila».
    """
    b = norm(body)
    vocab = {
        "Portada y arte": ["portada", "contraportada", "caratula", "ilustracion", "diseno", "artwork"],
        "Significado y sentido": ["significa", "significado", "quiere decir", "titulo viene", "se llama"],
        "Letras": ["letra", "verso", "estribillo"],
        "Acordes y tablatura": ["acorde", "tablatura", "afinacion"],
        "Tributo y versiones": ["tributo", "version", "homenaje", "directo"],
        "Tracklist y canciones": ["cancion", "tema", "corte", "tracklist"],
        "Ficha técnica (año, sello, duración)": ["grabo", "grabado", "estudio", "sello", "produjo", "productor"],
        "Escucha (streaming, vídeo)": ["youtube", "spotify", "video"],
        "Ediciones físicas y compra": ["vinilo", "reedicion", "edicion"],
        "Merchandising": ["camiseta", "tatuaje"],
        "Descarga y piratería": [],
        "Navegacional (marca + título)": [],
    }.get(tematica, [])
    # Lo navegacional lo cubre el título de la página por definición: nadie
    # escribe un bloque sobre «agila extremoduro». Marcarlo como hueco es ruido
    # y encima lo pone el primero, porque es el de más volumen.
    if not vocab:
        return True, "la cubre el propio título"
    hits = [v for v in vocab if v in b]
    if hits:
        return True, f"menciona: {', '.join(hits[:3])}"
    return False, "sin vocabulario de esta temática en el cuerpo"


def corpus_tapado(db) -> tuple[int, int]:
    """(fuentes sin vectorizar, total). Un corpus tapado invalida el diagnóstico.

    No basta con documentarlo en el SKILL.md: si el motor no ve la mitad del
    material, escribe genérico y optimizar es tirar el dinero. Medido el
    03-08-2026: 355 de 695 fuentes sin indexar y `audit_quality` daba 15
    aprobados de 180 páginas.
    """
    from sqlalchemy import text
    try:
        total = db.execute(
            text("SELECT count(*) FROM interpretation_sources WHERE content_clean IS NOT NULL")
        ).scalar() or 0
    except Exception:  # noqa: BLE001
        return 0, 0
    try:
        from qdrant_client import QdrantClient
        from app.config import get_settings
        q = QdrantClient(url=get_settings().qdrant_url)
        vistos: set[int] = set()
        offset = None
        while True:
            pts, offset = q.scroll(collection_name="interpretations_v1", limit=1000,
                                   offset=offset, with_payload=["source_id"],
                                   with_vectors=False)
            for p in pts:
                sid = (p.payload or {}).get("source_id")
                if isinstance(sid, int):
                    vistos.add(sid)
            if offset is None:
                break
        return max(0, total - len(vistos)), total
    except Exception:  # noqa: BLE001 — sin Qdrant no se puede afirmar nada
        return -1, total


def material_disponible(db, titulo: str) -> int:
    """Cuántas fuentes del corpus mencionan el asset.

    Este es el paso que evita proponer paja: si no hay material, no hay bloque
    que escribir por mucho volumen que tenga la keyword. En los discos dados de
    alta ayer `augment_deep` devolvió no-op justamente por esto.
    """
    from sqlalchemy import text
    try:
        return db.execute(
            text("SELECT count(*) FROM interpretation_sources WHERE content_clean ILIKE :p"),
            {"p": f"%{titulo}%"},
        ).scalar() or 0
    except Exception:  # noqa: BLE001 — sin corpus el diagnóstico sigue siendo útil
        return -1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asset", required=True, help="tipo:slug — p.ej. album:agila")
    ap.add_argument("--run", help="run de kw_out (default: el más reciente)")
    ap.add_argument("--incluir", action="append", default=[],
                    help="incluir una familia excluida por defecto (compra|merch|descarga)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if ":" not in args.asset:
        print("--asset debe ser tipo:slug (album:agila)", file=sys.stderr)
        return 2
    asset_type, slug = args.asset.split(":", 1)

    run = Path(args.run) if args.run else latest_run()
    if run is None:
        print(f"No hay ningún run con salida atribuida en {KW_ROOT}", file=sys.stderr)
        return 1

    incluir = set()
    for i in args.incluir:
        for n in EXCLUIDAS_POR_DEFECTO:
            if norm(i)[:5] in norm(n):
                incluir.add(n)

    db = SessionLocal()
    try:
        entity, titulo, url_path = resolver_asset(db, asset_type, slug)
        if entity is None:
            print(f"No existe {asset_type}:{slug} en la BD", file=sys.stderr)
            return 1

        seo = db.execute(
            select(SeoContent).where(
                SeoContent.entity_type == asset_type, SeoContent.entity_id == entity.id
            )
        ).scalar_one_or_none()
        body = (seo.body_md if seo else "") or ""

        kws = cargar_keywords(run, asset_type, slug)
        gsc, gsc_periodo = cargar_gsc(url_path)
        n_material = material_disponible(db, titulo)
        sin_indexar, total_fuentes = corpus_tapado(db)

        # Agrupar por temática
        grupos: dict[str, list[dict]] = defaultdict(list)
        for r in kws:
            grupos[clasificar(r["keyword"])].append(r)

        # GSC por temática: la señal más valiosa, porque es posición REAL
        gsc_por_tema: dict[str, list[dict]] = defaultdict(list)
        for q in gsc:
            gsc_por_tema[clasificar(q["query"])].append(q)

        vol = lambda r: int(r.get("volume_best") or 0)  # noqa: E731
        filas = []
        for tema in {*grupos, *gsc_por_tema}:
            rs = grupos.get(tema, [])
            qs = gsc_por_tema.get(tema, [])
            excluida = tema in EXCLUIDAS_POR_DEFECTO and tema not in incluir
            ya, motivo = cubre(body, tema, [r["keyword"] for r in rs])
            posiciones = [q["position"] for q in qs if q.get("position")]
            filas.append({
                "tematica": tema,
                "keywords": len(rs),
                "volumen": sum(vol(r) for r in rs),
                "cubierta": ya,
                "motivo": motivo,
                "excluida": excluida,
                "gsc_queries": len(qs),
                "gsc_impresiones": sum(q["impressions"] for q in qs),
                "gsc_clics": sum(q["clicks"] for q in qs),
                "mejor_posicion": round(min(posiciones), 1) if posiciones else None,
                "top_keywords": [r["keyword"] for r in sorted(rs, key=lambda r: -vol(r))[:5]],
                "top_gsc": sorted(qs, key=lambda q: q.get("position") or 999)[:4],
            })

        # Prioridad: lo NO cubierto, no excluido, y con señal real de Google
        # (una posición buena vale más que volumen estimado).
        def prio(f):
            if f["excluida"] or f["cubierta"]:
                return (2, 0)
            pos = f["mejor_posicion"] or 999
            return (0 if pos <= 20 else 1, -(1000 - pos) if pos <= 100 else -f["volumen"])

        filas.sort(key=prio)

        salida = {
            "asset": args.asset, "titulo": titulo, "url": url_path, "run": run.name,
            "publicado": bool(seo and seo.published),
            "palabras": len(body.split()),
            "target_keyword": (seo.target_keyword if seo else None),
            "meta_title": (seo.meta_title if seo else None) or None,
            "fuentes_corpus": n_material,
            "corpus_sin_indexar": sin_indexar,
            "corpus_total": total_fuentes,
            "keywords_totales": len(kws),
            "volumen_total": sum(vol(r) for r in kws),
            "gsc_queries": len(gsc),
            "gsc_periodo": gsc_periodo,
            "gsc_clics": sum(q["clicks"] for q in gsc),
            "tematicas": filas,
        }

        if args.json:
            print(json.dumps(salida, ensure_ascii=False, indent=2))
            return 0

        print(f"\n{'='*78}")
        print(f"  {titulo}   —   {url_path}")
        print(f"{'='*78}")
        print(f"  contenido: {salida['palabras']} palabras · "
              f"{'publicado' if salida['publicado'] else 'BORRADOR'} · "
              f"target_kw: {salida['target_keyword'] or '— (sin asignar)'}")
        if not salida["meta_title"]:
            print("  ⚠️  meta_title VACÍO")
        print(f"  research:  {salida['keywords_totales']} keywords · "
              f"{salida['volumen_total']}/mes")
        print(f"  GSC:       {salida['gsc_queries']} queries · "
              f"{salida['gsc_clics']} clics · {gsc_periodo or 'sin datos'}")
        print(f"  corpus:    {n_material} fuentes mencionan «{titulo}»"
              if n_material >= 0 else "  corpus:    n/d")
        if sin_indexar > 0:
            pct = 100 * sin_indexar / max(1, total_fuentes)
            print()
            print(f"  ⚠️  CORPUS TAPADO: {sin_indexar} de {total_fuentes} fuentes "
                  f"({pct:.0f}%) SIN vectorizar.")
            print("      El motor no las ve, así que escribirá genérico y optimizar")
            print("      no servirá de nada. Destápalo antes:")
            print("        docker compose exec -T api python -m "
                  "scripts.research.embed_interpretations --only-missing")
        print()
        print(f"  {'TEMÁTICA':<38} {'KWS':>4} {'VOL':>6} {'POS':>6}  ESTADO")
        print(f"  {'-'*76}")
        for f in filas:
            if f["excluida"]:
                estado = "excluida por norma"
            elif f["cubierta"]:
                estado = f"cubierta ({f['motivo']})"
            else:
                estado = "◄ HUECO"
            pos = f"{f['mejor_posicion']}" if f["mejor_posicion"] else "—"
            print(f"  {f['tematica'][:37]:<38} {f['keywords']:>4} {f['volumen']:>6} "
                  f"{pos:>6}  {estado}")

        huecos = [f for f in filas if not f["excluida"] and not f["cubierta"]]
        if huecos:
            print(f"\n  {'-'*76}")
            print("  HUECOS, por orden de oportunidad:\n")
            for i, f in enumerate(huecos[:5], 1):
                print(f"  {i}. {f['tematica']}  ·  {f['volumen']}/mes  ·  "
                      f"{f['keywords']} keywords")
                if f["top_gsc"]:
                    print("     Google ya te posiciona aquí:")
                    for q in f["top_gsc"]:
                        print(f"       pos {q['position']:>5.1f}  {q['impressions']:>3} impr  "
                              f"{q['clicks']} clics   «{q['query']}»")
                if f["top_keywords"]:
                    print(f"     keywords: {', '.join(f['top_keywords'][:4])}")
                print()
            if n_material == 0:
                print("  ⚠️  Cero fuentes del corpus mencionan este asset: cualquier bloque")
                print("      que se escriba sería paja. `augment_deep` devolverá no-op.")
        else:
            print("\n  Sin huecos accionables.")
        print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
