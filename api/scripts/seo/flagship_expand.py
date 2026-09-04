"""Regenera a tier CORNERSTONE (máxima profundidad) las fichas CORTAS que tienen
material real sin usar (según measure_headroom), para llevarlas a "flagship" SIN paja.

El motor `generate_deep` ya escala al material (`_section_cap`), así que en un sujeto
flaco no infla; aquí forzamos cornerstone SOLO sobre las expandibles y con guardas que
garantizan mejora real y no regresión:

  - GREW: el cuerpo nuevo es ≥20% más largo que el actual (si no crece, no había
    material → se descarta y se conserva el actual).
  - RIGOR: el veredicto no puede ser 'reject' (nada de paja).
  - NO OVER-NAMING: el nombre del sujeto no supera 1 por ~550c (se corrige en origen
    quitándolo de la exención del linter anti-muletillas de `_polish`).
  - SIN PÉRDIDA DE ENLACES: el nuevo conserva ≥80% de los enlaces internos del actual.

Backup por stdout (base64). SIEMPRE --sample primero.

Uso:
  python -m scripts.seo.measure_headroom            # ver qué expandir
  python -m scripts.seo.flagship_expand --sample --slugs el-viento,pedra,salir
  python -m scripts.seo.flagship_expand --apply --slugs <lista de expandibles>
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import re
from datetime import datetime, timezone

from openai import OpenAI

from app.config import get_settings
from app.db.models import (
    Album, Artist, Band, Concept, Person, Place, SeoContent, Song, Theme,
)
from app.db.session import SessionLocal
from app.services.deep_research import gather_entity_dossier
from app.services.editorial_review import review as editorial_review
from app.services.entity_resolver import (
    autolink_corpus, build_corpus_index, load_link_stats,
)
from app.services.text_sanitizer import strip_ai_tells
from scripts.seo.generate_deep import (
    _coverage_hint, _meta, _outline, _polish, _verify_section, _write_section,
    apply_catalog_check,
)
from scripts.seo.generate_flagship import _sanitize_links

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_MODEL = {"song": Song, "album": Album, "band": Band, "person": Person,
          "place": Place, "theme": Theme, "concept": Concept, "artist": Artist}
_LINK = re.compile(r"\]\((https?://[^)]+)\)")
GREW_RATIO = 1.20
CHARS_PER_NAME = 550
_ANTINAME = ("\nESTILO: no repitas el nombre completo del sujeto en exceso; a partir de "
             "la primera mención en cada sección, varía con pronombres o referencias "
             "(«el disco», «el álbum», «la banda», «esta obra», «el tema»…).\n")


def _links(body: str) -> set[str]:
    return set(_LINK.findall(body or ""))


def _name_count(body: str, name: str) -> int:
    return len(re.findall(re.escape(name), body or "", flags=re.I)) if name else 0


def _allowed_terms(entity, subject: str) -> set[str]:
    """Como generate_for_entity PERO sin el nombre desnudo del sujeto (para que el
    linter de _polish SÍ reduzca su sobre-repetición). Se conservan disco/artista y
    la letra (repeticiones legítimas)."""
    terms: set[str] = set()
    try:
        alb = getattr(entity, "album", None)
        if alb is not None:
            terms.add((alb.title or "").lower())
            art = getattr(alb, "artist", None)
            if art is not None:
                terms.add((art.name or "").lower())
        lyr = getattr(entity, "lyrics_clean", None)
        if lyr:
            terms.add(lyr.lower())
    except Exception:  # noqa: BLE001
        pass
    return {t for t in terms if t}


def _regen(db, client, etype, ent, corpus_index, link_stats) -> str | None:
    dossier = gather_entity_dossier(db, etype, ent)
    if len(dossier.material) < 400:
        return None
    subject = dossier.subject
    coverage = _coverage_hint(etype) + _ANTINAME
    outline = _outline(client, subject, "", dossier.hard_facts, dossier.material,
                       coverage, tier="cornerstone")
    if not outline:
        return None
    headings = [s["heading"] for s in outline]
    full = f"{dossier.hard_facts}\n\n{dossier.material}"
    parts: list[str] = []
    for s in outline:
        sec = _write_section(client, subject, s, headings, dossier.hard_facts,
                             dossier.material, "", prior="\n\n".join(parts),
                             coverage=coverage, tier="cornerstone")
        sec = _verify_section(client, sec, full)
        if sec.strip():
            parts.append(sec.strip())
    body = "\n\n".join(parts)
    if len(body) < 400:
        return None
    allowed = _allowed_terms(ent, subject)
    body = _polish(client, subject, body, allowed_terms=allowed) or body
    body = _sanitize_links(body, dossier.allowed_urls)
    body = autolink_corpus(body, corpus_index, max_links=8, exclude_slug=ent.slug,
                           link_stats=link_stats)
    body = apply_catalog_check(db, body)
    body = strip_ai_tells(body) or body
    return body


def _evaluate(subject, etype, old, new):
    ratio = len(new) / max(len(old), 1)
    res = {"before": len(old), "after": len(new), "ratio": round(ratio, 2),
           "name": _name_count(new, subject)}
    if ratio < GREW_RATIO:
        res["ok"] = False; res["reason"] = f"no crece ({ratio:.2f}x) → sin material extra"
        return res
    ol, nl = _links(old), _links(new)
    kept = len(ol & nl) / max(len(ol), 1) if ol else 1.0
    if kept < 0.80:
        res["ok"] = False; res["reason"] = f"pierde enlaces ({kept:.0%} conservados)"
        return res
    # El over-naming NO se juzga aquí (para conceptos de nombre común como «el viento»
    # es lenguaje natural, no stuffing); lo limpia después el pase de de-repetición, y
    # el rigor ya penaliza la repetición egregia. Aquí: crecer con sustancia sin paja.
    v = editorial_review(new, kind=etype, subject=subject)
    res["score"] = v.score; res["verdict"] = v.verdict
    if v.verdict == "reject":
        res["ok"] = False; res["reason"] = f"rigor reject ({v.score}): paja"
        return res
    if v.verdict == "revise" and v.tightened_body_md and len(v.tightened_body_md) >= len(old) * GREW_RATIO:
        res["new_tightened"] = v.tightened_body_md
    res["ok"] = True
    res["reason"] = f"OK ({len(old)}→{len(new)}c, rigor {v.verdict} {v.score}, nombre {res['name']}×)"
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--slugs", required=True)
    ap.add_argument("--entity-type", default=None,
                    help="acota a un tipo; sin esto, un slug repetido entre tipos "
                         "(o entre discos) arrastra fichas que no son")
    args = ap.parse_args()

    client = OpenAI(api_key=get_settings().openai_api_key)
    slugs = {s.strip() for s in args.slugs.split(",")}
    with SessionLocal() as db:
        corpus_index = build_corpus_index(db)
        link_stats = load_link_stats()
        _q = db.query(SeoContent).filter(SeoContent.slug.in_(slugs))
        if args.entity_type:
            _q = _q.filter(SeoContent.entity_type == args.entity_type)
        targets = _q.all()
        if len(targets) > len(slugs):
            logger.warning(
                "%d fichas para %d slug(s): hay slugs repetidos. Acota con "
                "--entity-type o revisa que sean las que quieres.",
                len(targets), len(slugs),
            )
        applied = skip = 0
        for sc in targets:
            model = _MODEL.get(sc.entity_type)
            ent = db.get(model, sc.entity_id) if model else None
            if not ent:
                continue
            old = sc.body_md or ""
            new = _regen(db, client, sc.entity_type, ent, corpus_index, link_stats)
            if not new:
                logger.info("  %s/%s: sin regen (corpus escaso)", sc.entity_type, sc.slug)
                skip += 1; continue
            subject = (getattr(ent, "title", None) or getattr(ent, "name", None)
                       or getattr(ent, "stage_name", None) or sc.slug)
            ev = _evaluate(subject, sc.entity_type, old, new)
            final = ev.pop("new_tightened", None) or new
            logger.info("  %s/%s: %s", sc.entity_type, sc.slug, ev["reason"])
            if args.sample:
                print(f"\n===== {sc.entity_type}/{sc.slug} — aplica={ev['ok']} =====")
                print(f"[{ev['before']}→{ev['after']}c · rigor {ev.get('verdict')} "
                      f"{ev.get('score')} · nombre {ev['name']}×]")
                print(final[:2400])
                continue
            if args.apply and ev["ok"]:
                print("<<<BACKUP>>>" + json.dumps({
                    "seo_id": sc.id, "slug": sc.slug, "entity_type": sc.entity_type,
                    "old_body_b64": base64.b64encode(old.encode()).decode()}))
                meta = _meta(client, subject, None, final)
                sc.body_md = final
                if meta.get("meta_title"):
                    sc.meta_title = meta["meta_title"][:60]
                if meta.get("meta_description"):
                    sc.meta_description = meta["meta_description"][:155]
                sc.generated_at = datetime.now(timezone.utc)
                sc.generated_by = "flagship-" + (sc.generated_by or "")
                db.commit(); applied += 1
                logger.info("    ✓ aplicado")
            elif args.apply:
                skip += 1
        if args.apply:
            logger.info("Flagship: %d aplicadas · %d saltadas", applied, skip)


if __name__ == "__main__":
    main()
