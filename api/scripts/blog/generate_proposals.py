"""Genera propuestas editoriales en el banco `content_proposals`.

Dos fuentes:
  1. ACTUALIDAD: aniversarios de discos próximos + efemérides de Robe.
  2. SEO-DRIVEN: keyword research long-tail anclado al corpus
     (`app.services.keyword_research`) → ideas de artículo transversales con
     keyword objetivo, volumen, flag long-tail y señal (corpus/dataforseo/gsc).

El research deduplica contra las KW ya publicadas y las ya propuestas (memoria
semanal), así que el banco deja de repetir los mismos temas cada lunes.

Uso:
    python -m scripts.blog.generate_proposals
    python -m scripts.blog.generate_proposals --dry-run
    python -m scripts.blog.generate_proposals --no-research   (solo efemérides)
"""
from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import date

from openai import OpenAI
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db.models import Album, Artist, ContentProposal
from app.db.session import SessionLocal
from app.services import keyword_research

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROBE_BIRTH = (5, 16)
ROBE_DEATH = (12, 10)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _slug_int(text: str) -> int:
    """Hash determinista y estable de un texto → int para la UNIQUE de
    (kind, source_type, source_id). Evita duplicar la misma idea."""
    h = 0
    for ch in _norm(text):
        h = (h * 31 + ord(ch)) % 2_000_000_000
    return h or 1


def _days_until(today: date, month: int, day: int) -> int:
    this_year = date(today.year, month, day)
    target = this_year if this_year >= today else date(today.year + 1, month, day)
    return (target - today).days


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-research", action="store_true",
        help="salta DataForSEO + LLM, solo genera efemérides",
    )
    parser.add_argument("--anniversary-window", type=int, default=90)
    args = parser.parse_args()

    today = date.today()
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    with SessionLocal() as db:
        actualidad: list[dict] = []
        seo_rows: list[dict] = []

        # --- Aniversarios de discos próximos ---
        for album, artist in (
            db.query(Album, Artist).join(Artist, Album.artist_id == Artist.id)
            .filter(Album.release_date.isnot(None)).all()
        ):
            rd = album.release_date
            if _days_until(today, rd.month, rd.day) > args.anniversary_window:
                continue
            anniv = date(
                today.year if date(today.year, rd.month, rd.day) >= today
                else today.year + 1, rd.month, rd.day,
            )
            years = anniv.year - rd.year
            actualidad.append({
                "kind": "album-anniversary",
                "source_type": "album",
                "source_id": album.id,
                "title": f"{years}º aniversario de {album.title}",
                "angle": (
                    f"El {anniv.isoformat()} se cumplen {years} años del "
                    f"lanzamiento de {album.title} ({artist.name}, {rd.year})."
                ),
            })

        # --- Efemérides de Robe ---
        for label, (m, d), src in (
            ("cumpleaños", ROBE_BIRTH, "robe-birth"),
            ("aniversario de la muerte", ROBE_DEATH, "robe-death"),
        ):
            if _days_until(today, m, d) <= args.anniversary_window:
                actualidad.append({
                    "kind": "anniversary",
                    "source_type": src,
                    "source_id": 0,
                    "title": f"Robe Iniesta · {label}",
                    "angle": (
                        f"Se acerca el {label} de Robe Iniesta ({d:02d}/{m:02d}). "
                        "Homenaje editorial actualizado."
                    ),
                })

        # --- Propuestas SEO-driven (keyword research long-tail del corpus) ---
        if not args.no_research and client is not None:
            seo_rows = keyword_research.build_proposal_rows(
                client, db, slug_int=_slug_int
            )
        elif not args.no_research:
            logger.warning("OPENAI_API_KEY no configurada, salto research SEO")

        logger.info(
            "Candidatas: %d actualidad, %d SEO-driven", len(actualidad), len(seo_rows)
        )

        if args.dry_run:
            print("--- ACTUALIDAD ---")
            for r in actualidad:
                print(f"  [{r['kind']}] {r['title']}")
            print("--- SEO-DRIVEN (long-tail anclado al corpus) ---")
            for r in seo_rows:
                lt = "LT" if r.get("is_longtail") else "  "
                print(f"  [{lt}] {r['title']}  · KW: {r.get('target_keyword')} "
                      f"({r.get('search_volume')}/mes, {r.get('signal_source')})")
            return

        n_act = _insert(db, actualidad)
        n_seo = _insert(db, seo_rows)
        db.commit()
        logger.info(
            "Propuestas NUEVAS: %d actualidad + %d SEO-driven = %d",
            n_act, n_seo, n_act + n_seo,
        )


if __name__ == "__main__":
    main()
