"""Cola de oportunidades SEO: detectar, preparar borradores y ver el estado.

El circuito completo, en dos clics y sin que nada se publique solo:

  1. `--detect`   cruza el volcado de GSC con el contenido publicado, encola lo
                  accionable y manda el correo del diagnóstico. (cron semanal)
  2. [clic]       «preparar borrador» → el servidor lo prepara y manda el correo
                  del antes/después.
  3. `--prepare`  red de seguridad: recoge lo aprobado que se quedó a medias (un
                  deploy entre el clic y el borrador basta). (cron)
  4. [clic]       «publicar» → se aplica a la ficha y se revalida la caché.

Uso:
  python -m scripts.seo.seo_queue --detect            # detecta + correo
  python -m scripts.seo.seo_queue --detect --no-email --dry-run
  python -m scripts.seo.seo_queue --prepare --limit 5
  python -m scripts.seo.seo_queue --status
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_pages() -> tuple[dict, str | None]:
    for p in ("/app/data/gsc_page_queries.json",
              str(Path(__file__).resolve().parents[2] / "data" / "gsc_page_queries.json")):
        if Path(p).exists():
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            per = data.get("period") or {}
            periodo = f"{per.get('start')}..{per.get('end')}" if per else None
            return data.get("pages", {}), periodo
    logger.warning("No hay data/gsc_page_queries.json (¿corriste gsc_fetch_page_queries?).")
    return {}, None


def _covered_stats(db, pages: dict) -> dict:
    """Cuánto de lo que se ve en GSC ya está cubierto en cuerpo Y metadata.

    Va al correo a propósito: es el grupo más grande y el único sin acción posible.
    Sin este dato, el informe parece decir que todo lo demás es culpa del contenido.
    """
    from app.db.models import SeoContent
    from app.services.seo_opportunities import classify_queries
    from scripts.seo.gsc_optimize import _resolve_entity

    n = imp = 0
    for path, queries in pages.items():
        ent = _resolve_entity(db, path)
        if not ent:
            continue
        sc = (db.query(SeoContent)
              .filter(SeoContent.entity_type == ent[0], SeoContent.entity_id == ent[1])
              .first())
        if not sc or not (sc.body_md or "").strip():
            continue
        cub = classify_queries(queries, body_md=sc.body_md, meta_title=sc.meta_title,
                               meta_description=sc.meta_description)["covered"]
        n += len(cub)
        imp += sum(int(q.get("impressions") or 0) for q in cub)
    return {"queries": n, "impressions": imp}


def cmd_detect(args) -> None:
    from datetime import datetime

    from app.db.session import SessionLocal
    from app.services import seo_opportunities as svc

    pages, periodo = _load_pages()
    if not pages:
        return
    with SessionLocal() as db:
        if args.dry_run:
            from app.db.models import SeoContent
            from scripts.seo.gsc_optimize import _resolve_entity

            resumen = {"meta": [0, 0], "body": [0, 0], "covered": [0, 0]}
            for path, queries in pages.items():
                ent = _resolve_entity(db, path)
                if not ent:
                    continue
                sc = (db.query(SeoContent)
                      .filter(SeoContent.entity_type == ent[0],
                              SeoContent.entity_id == ent[1]).first())
                if not sc or not (sc.body_md or "").strip():
                    continue
                rep = svc.classify_queries(queries, body_md=sc.body_md,
                                           meta_title=sc.meta_title,
                                           meta_description=sc.meta_description)
                for k, v in rep.items():
                    resumen[k][0] += len(v)
                    resumen[k][1] += sum(int(q.get("impressions") or 0) for q in v)
            for k, (n, imp) in resumen.items():
                logger.info("  %-8s %4d consultas · %6d impresiones", k, n, imp)
            return

        # Los imports que tocan la tabla van aquí y no arriba: el dry-run tiene que
        # poder correr contra un despliegue que aún no tenga la migración aplicada.
        from app.db.models import SeoOpportunity
        from app.services.seo_opportunity_mail import send_detected

        creadas = svc.detect(db, pages, period=periodo,
                             min_impressions=args.min_impressions)
        logger.info("Oportunidades nuevas: %d", len(creadas))
        pendientes = (
            db.query(SeoOpportunity)
            .filter(SeoOpportunity.status == "detected")
            .order_by(SeoOpportunity.impressions.desc())
            .all()
        )
        for o in pendientes[:15]:
            logger.info("  [%s] %s · %d imp · %s", o.action, o.path, o.impressions,
                        (o.gap_hint or "")[:70])
        if args.no_email or not pendientes:
            return
        covered = _covered_stats(db, pages)
        if send_detected(pendientes[:args.limit], covered=covered):
            ahora = datetime.now(UTC)
            for o in pendientes[:args.limit]:
                o.notified_detected_at = ahora
            db.commit()
            logger.info("Correo de diagnóstico enviado (%d oportunidades).",
                        min(len(pendientes), args.limit))


def cmd_prepare(args) -> None:
    from app.services.seo_opportunities import run_prepare

    logger.info("Resultado: %s", run_prepare(limit=args.limit, notify=not args.no_email))


def cmd_status(_args) -> None:
    from sqlalchemy import func

    from app.db.models import SeoOpportunity
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        filas = (db.query(SeoOpportunity.status, SeoOpportunity.action,
                          func.count(SeoOpportunity.id), func.sum(SeoOpportunity.impressions))
                 .group_by(SeoOpportunity.status, SeoOpportunity.action).all())
        if not filas:
            logger.info("La cola está vacía.")
            return
        for status, action, n, imp in sorted(filas):
            logger.info("  %-10s %-5s %3d filas · %6d imp", status, action, n, imp or 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detect", action="store_true", help="detecta y encola desde el volcado GSC")
    ap.add_argument("--prepare", action="store_true", help="prepara borradores de lo aprobado")
    ap.add_argument("--status", action="store_true", help="resumen de la cola")
    ap.add_argument("--dry-run", action="store_true", help="con --detect: solo cuenta, no encola")
    ap.add_argument("--no-email", action="store_true")
    # Sin valor propio por comando: 25 URLs en un correo se leen, pero preparar 25
    # borradores de cuerpo son 25 pasadas del motor profundo y su factura de OpenAI.
    ap.add_argument("--limit", type=int, default=None,
                    help="con --detect, cuántas van al correo (25); con --prepare, cuántas se preparan (5)")
    ap.add_argument("--min-impressions", type=int, default=None,
                    help="suelo de impresiones por oportunidad (por defecto 25)")
    args = ap.parse_args()
    if args.min_impressions is None:
        from app.services.seo_opportunities import MIN_OPPORTUNITY_IMPRESSIONS

        args.min_impressions = MIN_OPPORTUNITY_IMPRESSIONS

    if args.detect:
        args_detect = argparse.Namespace(**vars(args))
        args_detect.limit = args.limit if args.limit is not None else 25
        cmd_detect(args_detect)
    if args.prepare:
        args_prep = argparse.Namespace(**vars(args))
        args_prep.limit = args.limit if args.limit is not None else 5
        cmd_prepare(args_prep)
    if args.status or not (args.detect or args.prepare):
        cmd_status(args)


if __name__ == "__main__":
    main()
