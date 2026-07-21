"""Verificador de CATÁLOGO por consenso (Eje C del vuelco editorial).

Fija la primera aparición canónica (disco de estudio + año) de una canción cuando
Genius/la BD la atribuyen a un recopilatorio o disco en directo. Caso real: "Amor
castúo" solo está en BD como versión en directo de 1997, cuando es un tema del
primer disco (1989). Verifica el año contra Wikipedia/Google (web_verify) y:
  - si se corrobora → escribe Song.original_album_slug/original_year (fact_check ya
    los respeta como verdad canónica sobre el recopilatorio).
  - si la versión de ESTUDIO no está ingerida en la BD (hueco de datos) → abre una
    errata needs_human para que David reingesta el disco correcto.

Uso:
  python -m scripts.verify.catalog_consensus --pending          # dry-run
  python -m scripts.verify.catalog_consensus --pending --apply
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.db.models import Album, ErrataReport, Song
from app.db.session import SessionLocal
from app.services import consensus as mcv
from app.services import curated_overrides as co
from app.services.consensus import SourceRef
from app.services.lyric_guard import best_ratio, normalize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_songs(db, title: str) -> list[Song]:
    """Todas las canciones cuyo título casa (difuso) con `title` (versiones incluidas)."""
    out = []
    for s in db.execute(select(Song)).scalars():
        if best_ratio(normalize(title), normalize(s.title)) >= 0.8:
            out.append(s)
    return out


def _has_studio(db, songs: list[Song]) -> bool:
    for s in songs:
        alb = db.execute(select(Album).where(Album.id == s.album_id)).scalar_one()
        if alb.kind == "studio":
            return True
    return False


def _web_year_source(song_title: str, year: int, album: str | None) -> SourceRef | None:
    from app.services.web_verify import classify_fact

    claim = (
        f"La canción «{song_title}» de Extremoduro apareció por primera vez en {year}"
        + (f", en el disco «{album}»" if album else " (su primer disco)")
        + "."
    )
    res = classify_fact(claim)
    v = res.get("verdict")
    src = (res.get("source") or "").lower()
    kind = "wikipedia" if "wiki" in src else "google_serp"
    if v == "supported":
        return SourceRef(name=f"web:{res.get('source') or 'web'}", source_kind=kind,
                         stance="supports", value=str(year), quote=(res.get("evidence") or "")[:200])
    if v == "contradicted":
        return SourceRef(name=f"web:{res.get('source') or 'web'}", source_kind=kind,
                         stance="contradicts", value="__OTHER__", quote=(res.get("evidence") or "")[:200])
    return None


def process(db, entry: dict, *, apply: bool) -> None:
    title = entry.get("song_title", "")
    year = int(entry.get("original_year") or 0)
    album = entry.get("original_album")
    album_slug = entry.get("original_album_slug")
    songs = _resolve_songs(db, title)
    if not songs:
        logger.warning("catálogo: canción no encontrada en BD: %s", title)
        return

    fan = SourceRef(name="fan (feedback)", source_kind="fan_feedback", stance="supports", value=str(year))
    sources = [fan]
    web = _web_year_source(title, year, album)
    if web:
        sources.append(web)
    result = mcv.evaluate_hypothesis(hypothesis=str(year), current_value=None, sources=sources)
    action = mcv.decide_fan_correction(result, fan_value=str(year))
    has_studio = _has_studio(db, songs)
    logger.info("«%s»: veredicto=%s conf=%.2f acción=%s | estudio_en_BD=%s",
                title, result.verdict, result.confidence, action, has_studio)

    verif = mcv.record_verification(
        db, claim_kind="song_year",
        claim_key=f"catalog:{normalize(title)}:year",
        result=result, song_id=songs[0].id, applied=(action == "auto_apply" and apply and has_studio),
    )
    db.flush()

    # Aunque el año se corrobore, si NO hay versión de estudio en BD es un hueco de
    # datos: se marca el año canónico en las versiones existentes Y se abre errata.
    if action == "auto_apply":
        if apply:
            for s in songs:
                s.original_year = year
                if album_slug:
                    s.original_album_slug = album_slug
            logger.info("  original_year=%d fijado en %d versión(es)", year, len(songs))
        else:
            logger.info("  (dry-run) fijaría original_year=%d en %d versión(es)", year, len(songs))
    else:
        logger.info("  → año no corroborado por consenso; a revisión")

    if not has_studio:
        if apply:
            db.add(ErrataReport(
                target_type="catalog", target_id=songs[0].id, field="original_album",
                reported_wrong=f"solo existe versión en directo/recopilatorio de «{title}»",
                suggested_right=f"reingesta el disco de estudio: «{album}» ({year})",
                reporter="catalog_consensus", status="needs_human",
                verification_id=verif.id,
                resolution_note="Hueco de datos: falta la versión de estudio en el catálogo.",
            ))
        logger.info("  → ERRATA: falta la versión de ESTUDIO en el catálogo (reingesta «%s» %s)", album, year)

    db.commit() if apply else db.rollback()


def main() -> None:
    p = argparse.ArgumentParser(description="Verificación de catálogo por consenso.")
    p.add_argument("--pending", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    db = SessionLocal()
    try:
        for entry in co.pending_only(co.canonical_tracklists()):
            process(db, entry, apply=args.apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
