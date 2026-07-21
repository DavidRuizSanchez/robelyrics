"""Verificador de LETRAS por consenso multi-fuente (Eje A del vuelco editorial).

Para una canción, contrasta la letra que tenemos (de Genius) contra fuentes
independientes (LRCLIB, letras.com) y, si hay CONSENSO de que una línea está mal
transcrita, la corrige sola; si es ambiguo, encola una errata para revisión.

Modos:
  # una canción por id (o por el override pendiente del YAML):
  python -m scripts.verify.lyrics_consensus --song-id 87
  python -m scripts.verify.lyrics_consensus --song-id 87 --apply      # aplica de verdad
  # todos los overrides pendientes de data/lyric_overrides.yaml:
  python -m scripts.verify.lyrics_consensus --pending --apply
  # barrido de todo el catálogo (diff completo, caro): --sweep

Sin --apply es DRY-RUN: dice qué haría sin tocar nada.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Album, Line, Song
from app.db.session import SessionLocal
from app.services import consensus as mcv
from app.services import curated_overrides as co
from app.services import lyric_fetchers
from app.services.consensus import SourceRef
from app.services.lyric_guard import best_ratio, normalize
from scripts.ingest import make_chunks, segment_lines

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ARTIST_FOR = {"robe": "Robe", "extremoduro": "Extremoduro"}

# Conectores iniciales que una fuente puede omitir sin cambiar el verso
# ("Y lleva..." vs "Lleva..."). NO incluye palabras de contenido.
_LEAD_CONNECTORS = {"y", "e", "que", "pero", "mas", "o", "u"}


def _line_tokens(s: str) -> list[str]:
    toks = normalize(s).split()
    if toks and toks[0] in _LEAD_CONNECTORS:
        toks = toks[1:]
    return toks


def _line_equivalent(a: str, b: str) -> bool:
    """Dos versos son 'el mismo' si, tras normalizar (sin puntuación ni acentos) y
    quitar un conector inicial, su secuencia de palabras coincide. Distingue
    'llega'/'lleva' (cambio de palabra) pero tolera comas y el 'Y' inicial."""
    return _line_tokens(a) == _line_tokens(b)


def _artist_name(db, song: Song) -> str:
    row = db.execute(
        select(Album).where(Album.id == song.album_id)
    ).scalar_one()
    from app.db.models import Artist
    art = db.execute(select(Artist).where(Artist.id == row.artist_id)).scalar_one()
    return _ARTIST_FOR.get(art.slug, art.name)


def _best_line(text: str, target_variants: list[str]) -> str | None:
    """De un texto de letra, la línea que mejor casa con alguna variante objetivo."""
    best, best_r = None, 0.0
    for raw in text.split("\n"):
        ln = raw.strip()
        if not ln:
            continue
        n = normalize(ln)
        for tv in target_variants:
            r = best_ratio(normalize(tv), n)
            if r > best_r:
                best_r, best = r, ln
    return best if best_r >= 0.6 else None


def verify_line(
    db,
    song: Song,
    *,
    wrong: str,
    right: str,
    external: dict[str, str],
) -> mcv.ConsensusResult:
    """Consenso sobre una línea concreta reportada por un fan. Cada fuente externa
    aporta SU versión de esa línea; evaluamos la hipótesis del fan ('right') de
    forma determinista (LRCLIB, letras.com...). El fan es una fuente más, pero su
    corrección solo se aplica si una fuente EXTERNA la corrobora."""
    variants = [wrong, right]
    sources: list[SourceRef] = [
        # el propio fan como fuente (T2); no basta sola (decide_fan_correction).
        SourceRef(name="fan (feedback)", source_kind="fan_feedback", value=right, quote=right),
    ]
    for kind, full_text in external.items():
        line = _best_line(full_text, variants)
        if line:
            sources.append(SourceRef(
                name=f"{kind}:{song.title}", source_kind=kind, value=line,
                url=None, quote=line,
            ))
    return mcv.evaluate_hypothesis(
        hypothesis=right, current_value=wrong, sources=sources, matcher=_line_equivalent,
    )


def apply_line_fix(db, song: Song, wrong: str, right: str, confidence: float) -> bool:
    """Sustituye la línea 'wrong' por 'right' en la letra y reconstruye
    lines/chunks + proveniencia. Devuelve True si tocó algo."""
    if not song.lyrics_clean:
        return False
    # match tolerante: encuentra la línea real por fuzzy y la reemplaza.
    lines = song.lyrics_clean.split("\n")
    target_n = normalize(wrong)
    replaced = False
    for i, ln in enumerate(lines):
        if best_ratio(target_n, normalize(ln)) >= 0.86:
            lines[i] = right
            replaced = True
            break
    if not replaced:
        return False
    new_clean = "\n".join(lines)
    song.lyrics_clean = new_clean
    song.lyrics_source = "consensus"
    song.lyrics_confidence = confidence
    song.lyrics_verified_at = datetime.now(timezone.utc)

    # reconstruir lines + chunks (mismo camino que la ingesta)
    db.query(Line).filter(Line.song_id == song.id).delete()
    from app.db.models import Chunk
    db.query(Chunk).filter(Chunk.song_id == song.id).delete()
    line_rows = segment_lines(new_clean)
    if line_rows:
        db.execute(Line.__table__.insert(), [{"song_id": song.id, **lr} for lr in line_rows])
    chunk_rows = make_chunks(line_rows)
    if chunk_rows:
        db.execute(Chunk.__table__.insert(), [{"song_id": song.id, **cr} for cr in chunk_rows])
    return True


def _open_errata(db, song: Song, wrong: str, right: str, result: mcv.ConsensusResult, verif):
    from app.db.models import ErrataReport
    if mcv.errata_exists(db, target_type="song_lyrics", target_id=song.id, field="lyrics_line"):
        return
    db.add(ErrataReport(
        target_type="song_lyrics",
        target_id=song.id,
        field="lyrics_line",
        reported_wrong=wrong,
        suggested_right=result.correct_value or right,
        reporter="lyrics_consensus",
        status="needs_human",
        verification_id=verif.id if verif else None,
        resolution_note=f"consenso={result.verdict} conf={result.confidence} — {result.rationale}",
    ))


def process_song_overrides(db, song: Song, overrides: list[dict], *, apply: bool) -> None:
    artist = _artist_name(db, song)
    logger.info("Trayendo letras externas de «%s» (%s)...", song.title, artist)
    external = lyric_fetchers.fetch_all(song.title, artist)
    logger.info("  fuentes que respondieron: %s", list(external.keys()) or "NINGUNA")

    changed = False
    for ov in overrides:
        for fix in (ov.get("line_fixes") or []):
            wrong, right = fix.get("wrong"), fix.get("right")
            if not wrong or not right:
                continue
            result = verify_line(db, song, wrong=wrong, right=right, external=external)
            action = mcv.decide_fan_correction(result, fan_value=right)
            logger.info(
                "  [%s] veredicto=%s conf=%.2f acción=%s → %r",
                song.title, result.verdict, result.confidence, action, result.correct_value,
            )
            verif = mcv.record_verification(
                db, claim_kind="lyric_line",
                claim_key=f"song:{song.id}:line:{normalize(wrong)[:60]}",
                result=result, song_id=song.id,
                applied=(action == "auto_apply" and apply),
            )
            db.flush()
            if action == "auto_apply":
                fix_val = result.correct_value or right
                if apply:
                    ok = apply_line_fix(db, song, wrong, fix_val, result.confidence)
                    changed = changed or ok
                    logger.info("    APLICADO: %r → %r (%s)", wrong, fix_val, "ok" if ok else "no encontró la línea")
                else:
                    logger.info("    (dry-run) auto-aplicaría: %r → %r", wrong, fix_val)
            elif action == "needs_human":
                _open_errata(db, song, wrong, right, result, verif)
                logger.info("    → errata para revisión humana")
    if apply:
        db.commit()
        if changed:
            # Propagación viva: la letra cambió → re-embed de la canción para que
            # buscador/consultorio/listas por mood la reflejen al instante.
            from app.services import freshness
            freshness.propagate(db, "lyric", song_id=song.id)
    else:
        db.rollback()


def apply_verified_overrides(db, *, apply: bool) -> None:
    """Aplica los overrides de letra marcados `status: verified` (verdad ya
    confirmada por un humano) SIN necesitar consenso externo. Necesario porque
    algunas fuentes (LRCLIB) no son alcanzables desde ciertos servidores, y una
    corrección ya validada no debe quedar atascada en la cola por eso."""
    verified = co.verified_only(co.lyric_overrides())
    if not verified:
        return
    logger.info("[verificadas] %d override(s) de letra verificado(s)", len(verified))
    changed_songs: set[int] = set()
    for ov in verified:
        song = _resolve_song(db, song_id=None, album_slug=ov.get("album_slug"),
                             title=ov.get("song_title"))
        if not song:
            logger.warning("[verificadas] sin canción: %s", ov.get("song_title"))
            continue
        for fix in (ov.get("line_fixes") or []):
            wrong, right = fix.get("wrong"), fix.get("right")
            if not (wrong and right):
                continue
            if apply:
                ok = apply_line_fix(db, song, wrong, right, 1.0)
                if ok:
                    song.lyrics_source = "override"
                    mcv.record_verification(
                        db, claim_kind="lyric_line",
                        claim_key=f"song:{song.id}:line:{normalize(wrong)[:60]}",
                        result=mcv.ConsensusResult(
                            verdict="corrected", confidence=1.0, current_value=wrong,
                            correct_value=right, sources=[SourceRef(
                                name="verificado a mano", source_kind="curated",
                                stance="supports", value=right)],
                            rationale="Override verificado por humano.",
                        ),
                        song_id=song.id, applied=True,
                    )
                if ok:
                    changed_songs.add(song.id)
                logger.info("  [%s] verificado APLICADO: %r → %r (%s)",
                            song.title, wrong, right, "ok" if ok else "no encontró línea")
            else:
                logger.info("  [%s] (dry-run) verificado aplicaría: %r → %r", song.title, wrong, right)
    if apply:
        db.commit()
        # Propagación viva: re-embed de cada canción cuya letra cambió.
        from app.services import freshness
        for sid in changed_songs:
            freshness.propagate(db, "lyric", song_id=sid)


def _resolve_song(db, *, song_id: int | None, album_slug: str | None, title: str | None) -> Song | None:
    stmt = select(Song)
    if song_id:
        return db.execute(stmt.where(Song.id == song_id)).scalar_one_or_none()
    if title:
        q = stmt.where(Song.title.ilike(title))
        if album_slug:
            q = q.join(Album, Album.id == Song.album_id).where(Album.slug == album_slug)
        return db.execute(q).scalars().first()
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Verificación de letras por consenso multi-fuente.")
    p.add_argument("--song-id", type=int)
    p.add_argument("--pending", action="store_true", help="procesa los overrides pendientes del YAML")
    p.add_argument("--apply", action="store_true", help="aplica de verdad (sin esto, dry-run)")
    args = p.parse_args()

    db = SessionLocal()
    try:
        # Los verificados a mano se aplican siempre (no dependen de consenso externo).
        apply_verified_overrides(db, apply=args.apply)
        if args.pending or args.song_id:
            pend = co.pending_only(co.lyric_overrides())
            if args.song_id:
                song = _resolve_song(db, song_id=args.song_id, album_slug=None, title=None)
                if not song:
                    logger.error("Canción id=%s no encontrada", args.song_id)
                    return
                # overrides que apliquen a esta canción (por título)
                ovs = [o for o in pend if (o.get("song_title") or "").lower() == song.title.lower()] or \
                      [{"line_fixes": []}]
                process_song_overrides(db, song, ovs, apply=args.apply)
            else:
                for ov in pend:
                    song = _resolve_song(
                        db, song_id=None,
                        album_slug=ov.get("album_slug"),
                        title=ov.get("song_title"),
                    )
                    if not song:
                        logger.warning("override sin canción en BD: %s / %s", ov.get("album_slug"), ov.get("song_title"))
                        continue
                    process_song_overrides(db, song, [ov], apply=args.apply)
        else:
            logger.info("Nada que hacer. Usa --pending o --song-id N (y --apply para aplicar).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
