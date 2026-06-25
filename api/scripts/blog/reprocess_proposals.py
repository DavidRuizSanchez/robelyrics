"""Reproceso ONE-SHOT del banco de propuestas con los controles nuevos.

Para las propuestas de NOTICIA vivas (proposed/approved/scheduled):
  1. Detecta `event_date` (si falta) re-analizando el cuerpo — SOLO si la fecha
     es explícita (nunca se inventa) — y deriva `recommended_date`.
  2. Caducidad: si el evento ya pasó → crónica (si hay material) o se descarta.
  3. Foco: si el texto se desvía del tema (relleno sobre el lugar/sede), lo
     recorta con el gate de foco.

Pensado para correrse UNA vez tras desplegar la tanda de fechas+foco. Idempotente:
re-ejecutarlo no rehace lo ya saneado. SIEMPRE probar con --dry-run primero.

Uso:
    python -m scripts.blog.reprocess_proposals --dry-run
    python -m scripts.blog.reprocess_proposals
    python -m scripts.blog.reprocess_proposals --ids 146 157
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.editorial_review import review as editorial_review
from app.services.focus_check import check_focus
from app.services.news_research import plan_research, validated_event_date
from app.services.publishing import recommended_from_event
from scripts.blog.materialize_proposals import _handle_expired

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LIVE = ("proposed", "approved", "scheduled")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*", help="solo estas propuestas")
    args = parser.parse_args()

    today = date.today()
    today_iso = today.isoformat()
    stats = {
        "revisadas": 0, "fecha": 0, "caducadas": 0, "cronica": 0, "foco": 0,
        "rigor_tensado": 0, "rigor_reject": 0,
    }

    with SessionLocal() as db:
        # El rigor aplica a TODOS los tipos; los pasos de fecha/caducidad solo a noticias.
        q = (
            db.query(ContentProposal)
            .filter(ContentProposal.status.in_(LIVE))
        )
        if args.ids:
            q = q.filter(ContentProposal.id.in_(args.ids))
        props = q.order_by(ContentProposal.id).all()
        logger.info("Propuestas vivas a revisar: %d", len(props))

        for p in props:
            stats["revisadas"] += 1
            subject = (p.target_keyword or p.title or "").strip()
            logger.info("[#%s] (%s) %s", p.id, p.kind, p.title)

            # 1. Detección de fecha de evento (si falta). Solo NOTICIAS y solo si
            #    aparece LITERAL en el cuerpo (anti-invención).
            detected = None
            if p.kind == "news" and p.event_date is None and p.body_md:
                plan = plan_research(p.title, p.body_md, subject, today=today_iso)
                detected = (
                    validated_event_date(plan.get("event_date"), p.body_md)
                    if plan.get("is_event") else None
                )
                if detected:
                    stats["fecha"] += 1
                    rec = recommended_from_event(detected, today)
                    logger.info("  fecha de evento detectada: %s (sugerido %s)", detected, rec)
                    if not args.dry_run:
                        p.event_date = detected
                        if rec:
                            p.recommended_date = rec
                        db.commit()

            # 2. Caducidad (evento ya pasado → crónica o descartar). Usa la fecha
            #    efectiva (persistida o recién detectada) para que el dry-run la vea.
            effective_ed = p.event_date or detected
            if effective_ed and effective_ed < today:
                if args.dry_run:
                    logger.info("  ⏰ [dry-run] evento caducado (%s): crónica o descarte", effective_ed)
                    stats["caducadas"] += 1
                    continue
                outcome = _handle_expired(db, p, today, dry_run=False)
                stats["caducadas"] += 1
                if outcome == "cancelled":
                    continue  # descartada por caducidad sin crónica
                stats["cronica"] += 1
                # Reconvertida a crónica: NO hacemos continue — cae al gate de
                # rigor (abajo) para que la crónica también pase el listón.
                db.refresh(p)

            # 3. Foco (recorta deriva temática).
            if p.body_md:
                fr = check_focus(p.body_md, subject)
                if not fr.ok and fr.trimmed_body_md:
                    stats["foco"] += 1
                    logger.info("  foco BAJO (score %d, deriva: %s) → recorte",
                                fr.score, ", ".join(fr.drift_headings) or "—")
                    if not args.dry_run:
                        p.body_md = fr.trimmed_body_md
                        db.commit()
                elif not fr.ok:
                    logger.info("  foco BAJO (score %d) sin recorte limpio — revisar a mano", fr.score)

            # 4. RIGOR editorial: lo genérico/relleno se tensa o se descarta.
            if p.body_md:
                when = None
                if p.event_date:
                    when = "past" if p.event_date < today else "future"
                v = editorial_review(p.body_md, kind=p.kind, subject=subject, event_when=when)
                if v.verdict == "reject":
                    stats["rigor_reject"] += 1
                    logger.info("  ✗ RIGOR rechaza (score %d): %s",
                                v.score, "; ".join(v.reasons))
                    if not args.dry_run:
                        p.status = "discarded"
                        db.commit()
                elif v.verdict == "revise" and v.tightened_body_md:
                    stats["rigor_tensado"] += 1
                    logger.info("  rigor: tensado (score %d)", v.score)
                    if not args.dry_run:
                        p.body_md = v.tightened_body_md
                        db.commit()

    logger.info(
        "Reproceso %s: %d revisadas · %d con fecha · %d caducadas (%d crónica) · "
        "%d recortes foco · %d tensadas · %d DESCARTADAS por rigor",
        "[DRY-RUN]" if args.dry_run else "aplicado",
        stats["revisadas"], stats["fecha"], stats["caducadas"], stats["cronica"],
        stats["foco"], stats["rigor_tensado"], stats["rigor_reject"],
    )


if __name__ == "__main__":
    main()
