"""Auditoría de CALIDAD (rigor) de TODAS las páginas de contenido del proyecto.

Read-only: NO modifica nada. Pasa cada ficha por el gate `editorial_review` (el mismo
juez que usa el pipeline) y reporta verdict + score, para localizar qué páginas no
llegan al listón (paja) antes de decidir qué regenerar/augmentar.

Cubre todas las entidades con SeoContent (song, album, band [grupos+sellos], person,
place [geografía], theme, concept [bestiario], artist) + los libros (tabla books).

Salida: resumen por tipo + listado de las que FALLAN (reject, o revise con score bajo),
peor primero, y un CSV completo en /tmp/audit_quality.csv.

Uso:
    python -m scripts.seo.audit_quality
    python -m scripts.seo.audit_quality --entity-type song
    python -m scripts.seo.audit_quality --low 55   # umbral de "revise flojo"
"""
from __future__ import annotations

import argparse
import csv
import logging
from concurrent.futures import ThreadPoolExecutor

from app.db.models import Book, SeoContent
from app.db.session import SessionLocal
from app.services.editorial_review import review as editorial_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEO_TYPES = ("song", "album", "band", "person", "place", "theme", "concept", "artist")


def _collect(db, only_type: str | None) -> list[dict]:
    """Carga (type, slug, subject, kind_hint, body) de todas las páginas. Un solo
    pase por BD; el juicio (LLM) va después, sin sesión, para poder paralelizar."""
    rows: list[dict] = []
    types = [only_type] if only_type else list(SEO_TYPES)
    for et in types:
        for sc in db.query(SeoContent).filter(SeoContent.entity_type == et).all():
            if not (sc.body_md or "").strip():
                continue
            # subject legible: H1 de la página, o meta_title, o el slug.
            subject = (sc.h1 or sc.meta_title or sc.slug)
            rows.append({"type": et, "slug": sc.slug, "subject": subject,
                         "kind": et, "chars": len(sc.body_md), "body": sc.body_md})
    if not only_type or only_type == "book":
        for b in db.query(Book).all():
            if not (b.body_md or "").strip():
                continue
            rows.append({"type": "book", "slug": b.slug, "subject": b.title,
                         "kind": "book", "chars": len(b.body_md), "body": b.body_md})
    return rows


def _judge(row: dict) -> dict:
    try:
        v = editorial_review(row["body"], kind=row["kind"], subject=row["subject"])
        return {**row, "verdict": v.verdict, "score": v.score,
                "reason": (v.reasons or [""])[0][:160]}
    except Exception as exc:  # noqa: BLE001
        return {**row, "verdict": "error", "score": -1, "reason": str(exc)[:160]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity-type", default=None)
    ap.add_argument("--low", type=int, default=55,
                    help="score por debajo del cual un 'revise' se marca como flojo")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    with SessionLocal() as db:
        rows = _collect(db, args.entity_type)
    logger.info("Auditando %d páginas…", len(rows))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, res in enumerate(ex.map(_judge, rows), 1):
            results.append(res)
            if i % 25 == 0:
                logger.info("  %d/%d", i, len(rows))

    # CSV completo (drop body).
    with open("/tmp/audit_quality.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["type", "slug", "chars", "verdict", "score", "subject", "reason"])
        for r in sorted(results, key=lambda x: (x["score"], x["type"])):
            w.writerow([r["type"], r["slug"], r["chars"], r["verdict"], r["score"],
                        r["subject"], r["reason"]])

    # Resumen por tipo.
    print("\n===== RESUMEN POR TIPO =====")
    print(f"{'tipo':<10} {'n':>4} {'pass':>5} {'revise':>7} {'reject':>7} {'flojos':>7} {'score_med':>9}")
    by_type: dict[str, list[dict]] = {}
    for r in results:
        by_type.setdefault(r["type"], []).append(r)
    total_fail = 0
    for et in sorted(by_type):
        rs = by_type[et]
        npass = sum(r["verdict"] == "pass" for r in rs)
        nrev = sum(r["verdict"] == "revise" for r in rs)
        nrej = sum(r["verdict"] == "reject" for r in rs)
        nlow = sum(r["verdict"] == "revise" and r["score"] < args.low for r in rs)
        fails = nrej + nlow
        total_fail += fails
        avg = round(sum(max(r["score"], 0) for r in rs) / max(len(rs), 1))
        print(f"{et:<10} {len(rs):>4} {npass:>5} {nrev:>7} {nrej:>7} {nlow:>7} {avg:>9}")
    print(f"\nTOTAL páginas: {len(results)} · que FALLAN (reject + revise<{args.low}): {total_fail}")

    # Listado de las que fallan (peor primero).
    fails = [r for r in results if r["verdict"] == "reject"
             or (r["verdict"] == "revise" and r["score"] < args.low)
             or r["verdict"] == "error"]
    fails.sort(key=lambda x: x["score"])
    print(f"\n===== FALLAN ({len(fails)}) — peor primero =====")
    for r in fails:
        print(f"  [{r['score']:>3}] {r['verdict']:<7} {r['type']:<8} {r['slug']:<45} · {r['reason']}")
    print("\nCSV completo en /tmp/audit_quality.csv")


if __name__ == "__main__":
    main()
