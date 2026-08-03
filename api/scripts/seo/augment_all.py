"""Runner del motor de AUGMENTACIÓN (augment_deep) con guarda de seguridad.

Recorre entidades, las aumenta (sin pérdida, ampliando + vídeos) y SOLO reemplaza el
`body_md` publicado si el resultado creció y no es no-op. Antes de cada escritura emite
un BACKUP del body anterior por stdout (base64) para rollback. Mantiene `published` como
estaba (refresco in situ, sin dejar la página a oscuras).

Uso:
  python -m scripts.seo.augment_all --entity-type person --slugs robe-iniesta            # dry-run
  python -m scripts.seo.augment_all --entity-type person --slugs robe-iniesta --apply     # aplica
  python -m scripts.seo.augment_all --entity-type person --limit 10 --discover-web --apply
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
from datetime import datetime, timezone

from openai import OpenAI

from app.config import get_settings
from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    Person,
    Place,
    SeoContent,
    Song,
    Theme,
)
from app.db.session import SessionLocal
from app.services.entity_resolver import build_corpus_index, load_link_stats
from scripts.seo.augment_deep import augment_entity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Figuras (person/band/artist) admiten eventos recientes/homenajes; el resto
# (song/album/theme/place/concept) se aumentan solo por HUECOS del corpus.
_MODELS = {
    "person": Person, "band": Band, "artist": Artist,
    "song": Song, "album": Album, "theme": Theme, "place": Place, "concept": Concept,
}

# Eventos recientes verificados a mano para figuras clave (post-corte del LLM: el
# descubrimiento web automático no siempre los ve). Cada uno con fuente real.
_CURATED: dict[tuple[str, str], list[dict]] = {
    ("person", "robe-iniesta"): [
        {"fact": "Robe Iniesta falleció el 10 de diciembre de 2025; su muerte marcó el "
                 "final definitivo de Extremoduro, banda que ya se había disuelto años antes.",
         "source": "efeméride canónica"},
        {"fact": "En la gala de los Premios Goya 2026 (febrero de 2026, Barcelona), durante "
                 "el segmento In memoriam, Belén Aguilera y Dani Fernández interpretaron «Si "
                 "te vas» de Extremoduro como homenaje a Robe; fue uno de los momentos más "
                 "aplaudidos y comentados de la noche.",
         "source": "Premios Goya (oficial), Deia, Forbes, MariskalRock (2026)",
         "video": "https://www.youtube.com/watch?v=zBLZ9iDcdDs"},
    ],
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Augmentación sin pérdida con guarda.")
    ap.add_argument("--entity-type", choices=list(_MODELS))
    ap.add_argument("--slugs", help="lista separada por comas. OJO con las "
                                    "canciones: la unicidad de `songs` es "
                                    "(album_id, slug), así que un slug puede "
                                    "existir en dos discos. Para esas, --ids")
    ap.add_argument("--ids", help="ids de entidad separados por comas. Es la vía "
                                  "correcta para canciones homónimas")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--discover-web", action="store_true",
                    help="descubre eventos recientes por web (figuras clave)")
    ap.add_argument("--apply", action="store_true", help="persiste (si no, dry-run)")
    ap.add_argument("--gap-hint",
                    help="temática con demanda que la página no cubre; la aporta "
                         "el diagnóstico del skill optimizar-pagina. Solo dirige "
                         "la MIRADA al material: si no lo respalda, no se escribe")
    ap.add_argument("--force", action="store_true",
                    help="reprocesa aunque ya esté aumentado (por defecto se saltan)")
    args = ap.parse_args()

    client = OpenAI(api_key=get_settings().openai_api_key)
    types = [args.entity_type] if args.entity_type else list(_MODELS)
    only = {s.strip() for s in args.slugs.split(",")} if args.slugs else None
    only_ids = ({int(i) for i in args.ids.split(",") if i.strip()}
                if args.ids else None)

    with SessionLocal() as db:
        corpus_index = build_corpus_index(db)
        link_stats = load_link_stats()
        targets = []
        # Ya aumentados (generated_by empieza por "augment-") → se saltan para no
        # doble-aumentar, salvo --force.
        #
        # El set va por (entity_type, entity_id), NO por slug. Con slug, dos
        # canciones homónimas de discos distintos —«Jesucristo García» está en
        # tres— se pisaban: aumentar una marcaba la otra como hecha y se la
        # saltaba para siempre, en silencio. `augment_deep` sí resolvía por
        # entity_id; el filtro de aquí era el que mentía.
        done = set()
        if not args.force:
            for et2, eid2 in db.query(SeoContent.entity_type, SeoContent.entity_id).filter(
                SeoContent.generated_by.like("augment-%")
            ).all():
                done.add((et2, eid2))
        for et in types:
            for ent in db.query(_MODELS[et]).order_by(_MODELS[et].slug).all():
                if only_ids is not None and ent.id not in only_ids:
                    continue
                if only and ent.slug not in only:
                    continue
                if (et, ent.id) in done:
                    continue
                targets.append((et, ent))
        if args.limit:
            targets = targets[: args.limit]
        logger.info("AUGMENTACIÓN: %d entidades · %s", len(targets),
                    "APLICA" if args.apply else "dry-run")

        applied = skipped = 0
        for et, ent in targets:
            curated = _CURATED.get((et, ent.slug))
            res = augment_entity(db, client, et, ent, recent_events=curated,
                                 discover_web=args.discover_web,
                                 corpus_index=corpus_index, link_stats=link_stats,
                                 gap_hint=args.gap_hint)
            if not res:
                logger.info("  %s/%s: sin body; salto", et, ent.slug); skipped += 1; continue
            if res.get("noop") or not res.get("grew"):
                logger.info("  %s/%s: sin material verificado que añadir (no-op)", et, ent.slug)
                skipped += 1
                continue
            logger.info("  %s/%s: %d→%d (+%d) · secciones: %s · vídeos+: %d · rigor %s",
                        et, ent.slug, res["before_len"], res["after_len"],
                        res["after_len"] - res["before_len"], res["added_headings"],
                        len(res["videos_added"]), (res.get("rigor") or {}).get("score"))
            if args.apply:
                # BACKUP del body anterior (rollback) por stdout, antes de escribir.
                print("<<<BACKUP>>>" + json.dumps({
                    "seo_id": res["seo_id"], "slug": ent.slug, "entity_type": et,
                    "old_body_b64": base64.b64encode(res["before"].encode()).decode(),
                }))
                sc = db.get(SeoContent, res["seo_id"])
                sc.body_md = res["after"]
                sc.generated_at = datetime.now(timezone.utc)
                sc.generated_by = "augment-" + (sc.generated_by or "")
                # published NO se toca: refresco en sitio.
                db.commit()
                applied += 1
            else:
                skipped += 1  # dry-run no cuenta como aplicado

        logger.info("FIN: aplicadas %d · saltadas/no-op %d · de %d",
                    applied, skipped, len(targets))


if __name__ == "__main__":
    main()
