"""Auto-optimización SEO semanal por URL con datos GSC reales (F2.5, paso 3).

Por cada URL publicada, detecta consultas en *striking distance* (posición 5-30,
impresiones altas) con ÁNGULO INFORMACIONAL nuevo (algo que la página aún no cubre
bien, más allá de su propio nombre) y propone mejorar el contenido para esas
consultas. SIEMPRE con datos GSC reales; nada inventado.

Seguridad (principio del proyecto: nada se auto-publica sin revisión):
- Modo por defecto = INFORME: email al admin con las oportunidades por URL. No toca nada.
- `--apply` = regenera las top-N URLs vía el pipeline profundo (`regenerate_deep`), que
  aprovecha las queries GSC (keyword_research las lee de data/gsc_queries.json) y pasa por
  TODOS los gates (rigor, lyric_guard, fact_check, linter). Con SEO_KEEP_PUBLISHED=1 refresca
  en sitio sin dejar la página a oscuras. Acotado por --limit.

Uso:
  python -m scripts.seo.gsc_optimize                    # informe + email
  python -m scripts.seo.gsc_optimize --apply --limit 8  # regenera las 8 mejores
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import unicodedata
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SITE = "https://entreinteriores.com"
_POS_MIN, _POS_MAX = 5.0, 30.0
_MIN_IMPRESSIONS = 20

_STOP = {"de", "la", "el", "los", "las", "y", "en", "del", "que", "a", "un", "una", "por", "con"}

# path /seccion/slug → entity_type para regenerate_deep
_SECTION_TYPE = {"personas": "person", "grupos": "band", "temas": "theme",
                 "lugares": "place", "conceptos": "concept"}


def _norm(s: str) -> set[str]:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return {t for t in re.findall(r"[a-z0-9]+", s) if t not in _STOP and len(t) > 1}


def _resolve_entity(path: str) -> tuple[str, str] | None:
    """URL path → (entity_type, slug) para regenerate_deep. None si no aplica."""
    parts = [p for p in path.strip("/").split("/") if p]
    if not parts:
        return None
    if parts[0] in _SECTION_TYPE and len(parts) == 2:
        return _SECTION_TYPE[parts[0]], parts[1]
    if parts[0] in ("blog", "libros", "sellos"):
        return None  # blog/libros/sellos tienen su propio flujo
    # catálogo: /artist, /artist/album, /artist/album/song
    if len(parts) == 1:
        return "artist", parts[0]
    if len(parts) == 2:
        return "album", parts[1]
    if len(parts) == 3:
        return "song", parts[2]
    return None


def opportunities(pages: dict) -> list[dict]:
    """Por URL, las queries striking-distance con ángulo informacional nuevo."""
    out = []
    for path, qs in pages.items():
        slug_tokens = _norm(path.split("/")[-1] or "home")
        opp = []
        for q in qs:
            if not (_POS_MIN <= q["position"] <= _POS_MAX and q["impressions"] >= _MIN_IMPRESSIONS):
                continue
            extra = _norm(q["query"]) - slug_tokens
            # informacional = aporta tokens de contenido más allá del nombre de la entidad
            if extra and extra != {"grupo"} and extra != {"letra"} - slug_tokens:
                opp.append(q)
        if opp:
            out.append({
                "path": path,
                "queries": opp,
                "score": sum(q["impressions"] for q in opp),
                "entity": _resolve_entity(path),
            })
    out.sort(key=lambda x: -x["score"])
    return out


def _load_pages() -> dict:
    for p in ("/app/data/gsc_page_queries.json",
              str(Path(__file__).resolve().parents[2] / "data" / "gsc_page_queries.json")):
        if Path(p).exists():
            return json.loads(Path(p).read_text(encoding="utf-8")).get("pages", {})
    logger.warning("No hay data/gsc_page_queries.json (¿corriste gsc_fetch_page_queries?).")
    return {}


def _email_report(opps: list[dict]) -> None:
    from app.config import get_settings
    from app.services.email import send_email
    to = get_settings().admin_email
    if not to or not opps:
        return
    parts = ["<h2 style='font-family:Georgia,serif'>Oportunidades SEO (GSC, striking distance)</h2>",
             "<p>Consultas donde estas URLs ya aparecen (pos 5-30) pero podrían subir si el "
             "contenido las cubre mejor. Ejecuta <code>gsc_optimize --apply</code> o regenera a mano.</p>"]
    for o in opps[:25]:
        parts.append(f"<h3><a href='{_SITE}{o['path']}'>{o['path']}</a> "
                     f"<span style='color:#888'>(pot. {o['score']} imp)</span></h3><ul>")
        for q in o["queries"][:6]:
            parts.append(f"<li>«{q['query']}» — pos {q['position']}, {q['impressions']} imp, {q['clicks']} clic</li>")
        parts.append("</ul>")
    send_email(to, f"[Entre Interiores] {len(opps)} URLs con oportunidad SEO (GSC)", "\n".join(parts))
    logger.info("Informe de %d oportunidades enviado a %s", len(opps), to)


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto-optimización SEO por URL con datos GSC.")
    ap.add_argument("--apply", action="store_true", help="regenera las top-N URLs (si no, solo informe)")
    ap.add_argument("--limit", type=int, default=8, help="máx URLs a regenerar con --apply")
    ap.add_argument("--no-email", action="store_true")
    args = ap.parse_args()

    pages = _load_pages()
    if not pages:
        return
    opps = opportunities(pages)
    logger.info("URLs con oportunidad striking-distance informacional: %d", len(opps))
    for o in opps[:15]:
        logger.info("  %s (%d imp) · %s", o["path"], o["score"],
                    ", ".join(q["query"] for q in o["queries"][:3]))

    if not args.no_email:
        _email_report(opps)

    if args.apply:
        # Regenera las mejores por tipo (regenerate_deep aprovecha las queries GSC vía
        # keyword_research). SEO_KEEP_PUBLISHED=1: refresca en sitio, gated, no deja a oscuras.
        import os
        applied = 0
        for o in opps:
            if applied >= args.limit:
                break
            ent = o["entity"]
            if not ent:
                continue
            etype, slug = ent
            logger.info("  APLICANDO: regenerando %s/%s por %d queries GSC",
                        etype, slug, len(o["queries"]))
            env = {**os.environ, "SEO_KEEP_PUBLISHED": "1"}
            subprocess.run(
                ["python", "-m", "scripts.seo.regenerate_deep", "--entity-type", etype, "--slugs", slug],
                check=False, env=env,
            )
            applied += 1
        logger.info("Regeneradas %d URLs (revisar en el site).", applied)


if __name__ == "__main__":
    main()
