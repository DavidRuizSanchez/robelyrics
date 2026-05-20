"""Genera propuestas editoriales en el banco `content_proposals`.

NO llama al LLM: crea propuestas con título y ángulo mecánicos. El body
editorial se genera después, cuando el admin programa la propuesta y el
materializador la convierte en Post.

FOCO: actualidad. Por orden de prioridad editorial:
  1. news        — las trae el scraper (`scrape_news`), no este script.
  2. album-anniversary — aniversarios de discos en los próximos 90 días.
  3. anniversary — cumpleaños (16/5) y muerte (10/12) de Robe si se acercan.
  4. evergreen   — temas/lugares/conceptos: REPOSITORIO de fondo de armario,
                   para publicar cuando no hay actualidad. Secundario.

Las crónicas/análisis de canciones sueltas (spotlights) NO se generan en
masa: el foco es lo que pasa, no repasar el catálogo disco a disco.

Idempotente: la UNIQUE (kind, source_type, source_id) evita duplicar.

Uso:
    python -m scripts.blog.generate_proposals
    python -m scripts.blog.generate_proposals --dry-run
    python -m scripts.blog.generate_proposals --anniversary-window 120
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Album, Artist, Concept, ContentProposal, Place, Theme
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TAX_LABEL = {"theme": "el tema", "place": "el lugar", "concept": "el concepto"}

ROBE_BIRTH = (5, 16)
ROBE_DEATH = (12, 10)


def _insert(db, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = (
        pg_insert(ContentProposal)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_content_proposals_kind_source")
        .returning(ContentProposal.id)
    )
    return len(db.execute(stmt).fetchall())


def _days_until(today: date, month: int, day: int) -> int:
    """Días hasta el próximo aniversario (mes, día) a partir de hoy."""
    this_year = date(today.year, month, day)
    target = this_year if this_year >= today else date(today.year + 1, month, day)
    return (target - today).days


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--anniversary-window",
        type=int,
        default=90,
        help="ventana en días para proponer aniversarios próximos",
    )
    args = parser.parse_args()

    today = date.today()
    window = args.anniversary_window

    with SessionLocal() as db:
        actualidad: list[dict] = []
        repositorio: list[dict] = []

        # --- Aniversarios de discos próximos (ACTUALIDAD) ---
        albums = (
            db.query(Album, Artist)
            .join(Artist, Album.artist_id == Artist.id)
            .filter(Album.release_date.isnot(None))
            .all()
        )
        for album, artist in albums:
            rd = album.release_date
            d = _days_until(today, rd.month, rd.day)
            if d > window:
                continue
            years = today.year - rd.year
            if (today.month, today.day) < (rd.month, rd.day):
                years = today.year - rd.year - 1
            years += 1  # el aniversario que viene
            anniv_date = date(
                today.year if date(today.year, rd.month, rd.day) >= today
                else today.year + 1,
                rd.month, rd.day,
            )
            actualidad.append({
                "kind": "album-anniversary",
                "source_type": "album",
                "source_id": album.id,
                "title": f"{years}º aniversario de {album.title}",
                "angle": (
                    f"El {anniv_date.isoformat()} se cumplen {years} años del "
                    f"lanzamiento de {album.title} ({artist.name}, {rd.year})."
                ),
            })

        # --- Efemérides de Robe próximas (ACTUALIDAD) ---
        for label, (m, d), src in (
            ("cumpleaños", ROBE_BIRTH, "robe-birth"),
            ("aniversario de la muerte", ROBE_DEATH, "robe-death"),
        ):
            if _days_until(today, m, d) <= window:
                actualidad.append({
                    "kind": "anniversary",
                    "source_type": src,
                    "source_id": 0,  # valor fijo para que la UNIQUE dedup funcione
                    "title": f"Robe Iniesta · {label}",
                    "angle": (
                        f"Se acerca el {label} de Robe Iniesta "
                        f"({d:02d}/{m:02d}). Homenaje editorial actualizado."
                    ),
                })

        # --- Evergreens: taxonomías (REPOSITORIO de fondo) ---
        for kind_key, model in (("theme", Theme), ("place", Place), ("concept", Concept)):
            for t in db.query(model).order_by(model.id).all():
                repositorio.append({
                    "kind": "evergreen",
                    "source_type": kind_key,
                    "source_id": t.id,
                    "title": t.name,
                    "angle": (
                        f"Pieza de fondo sobre {TAX_LABEL[kind_key]} «{t.name}» "
                        "en el cancionero de Robe y Extremoduro."
                    ),
                })

        logger.info(
            "Candidatas: %d de actualidad (aniversarios), %d de repositorio (evergreen)",
            len(actualidad), len(repositorio),
        )

        if args.dry_run:
            print("--- ACTUALIDAD ---")
            for r in actualidad:
                print(f"  [{r['kind']}] {r['title']} — {r['angle']}")
            print(f"--- REPOSITORIO ({len(repositorio)}) ---")
            for r in repositorio[:8]:
                print(f"  [{r['kind']}] {r['title']}")
            return

        n_act = _insert(db, actualidad)
        n_rep = _insert(db, repositorio)
        db.commit()
        logger.info(
            "Propuestas NUEVAS: %d de actualidad + %d de repositorio = %d",
            n_act, n_rep, n_act + n_rep,
        )


if __name__ == "__main__":
    main()
