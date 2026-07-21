"""Verificador de AUTORÍA por consenso multi-fuente (Eje B del vuelco editorial).

Resuelve la atribución de poemas de otros musicados por Robe (el caso Chinato:
"Ama, ama y ensancha el alma" es un poema de Manolo Chinato, no una letra de Robe).
Contrasta la hipótesis (de fan o curada) contra:
  - Wikipedia + Google (web_verify.classify_fact) → señal autoritativa T1/T2.
  - El corpus fan ya ingerido (InterpretationSource: anotaciones de Genius, blogs
    especializados, entrevistas) que atribuya el texto a ese autor → T1/T2/T3.
Si hay corroboración externa y ninguna T1 lo contradice, escribe los SongCredit;
si es ambiguo, encola una errata (needs_human) + (futuro) email de revisión.

Uso:
  python -m scripts.verify.authorship_consensus --pending          # dry-run
  python -m scripts.verify.authorship_consensus --pending --apply
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.db.models import Album, Person, Song, SongCredit
from app.db.session import SessionLocal
from app.services import consensus as mcv
from app.services import curated_overrides as co
from app.services.consensus import SourceRef
from app.services.lyric_guard import best_ratio, normalize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _resolve_song(db, title: str, album_slug: str | None) -> Song | None:
    """Resuelve la canción por título tolerante (BD tiene 'Ama, Ama, Ama y…' con 3
    'ama'; el YAML puede traer 2). Filtra por álbum si se da."""
    q = select(Song)
    if album_slug:
        q = q.join(Album, Album.id == Song.album_id).where(Album.slug == album_slug)
    best, best_r = None, 0.0
    for s in db.execute(q).scalars():
        r = best_ratio(normalize(title), normalize(s.title))
        if r > best_r:
            best_r, best = r, s
    return best if best_r >= 0.75 else None


def _web_source(claim: str, author: str) -> SourceRef | None:
    """Señal Wikipedia/Google para el claim de autoría."""
    from app.services.web_verify import classify_fact

    res = classify_fact(claim)
    verdict = res.get("verdict")
    src = (res.get("source") or "").lower()
    kind = "wikipedia" if "wiki" in src else "google_serp"
    if verdict == "supported":
        return SourceRef(name=f"web:{res.get('source') or 'wikipedia/google'}",
                         source_kind=kind, stance="supports", value=author,
                         quote=(res.get("evidence") or "")[:200])
    if verdict == "contradicted":
        return SourceRef(name=f"web:{res.get('source') or 'wikipedia/google'}",
                         source_kind=kind, stance="contradicts", value="__OTHER__",
                         quote=(res.get("evidence") or "")[:200])
    return None  # not_found → sin señal


_CORPUS_SYS = (
    "Eres un documentalista. Te doy PASAJES de fan-content sobre una canción y una "
    "AFIRMACIÓN de autoría. ¿Los pasajes RESPALDAN que el texto/letra es de ese autor? "
    'Responde SOLO JSON: {"attributes": true|false, "quote": "<frase que lo respalda o vacío>"}. '
    "true solo si algún pasaje dice o implica claramente esa autoría. No inventes."
)


def _corpus_sources(db, song: Song, author: str) -> list[SourceRef]:
    """Busca en InterpretationSource pasajes que mencionen la canción y el autor, y
    deja que un juez barato decida si le ATRIBUYEN la autoría. Un SourceRef por kind."""
    from app.db.models import InterpretationSource
    from app.services.news_research import _json

    author_key = normalize(author).split()[-1]  # "chinato"
    title_key = normalize(song.title)
    rows = db.execute(
        select(InterpretationSource).where(
            InterpretationSource.content_clean.ilike(f"%{author_key}%")
        )
    ).scalars().all()

    # nos quedamos con los que además mencionan la canción (fuzzy por título)
    hits: dict[str, list[str]] = {}
    for r in rows:
        content = (r.content_clean or "")
        if title_key.split()[0] not in normalize(content):
            continue
        # extraer un fragmento alrededor de la mención del autor
        low = content.lower()
        idx = low.find(author_key)
        frag = content[max(0, idx - 200): idx + 200] if idx >= 0 else content[:400]
        hits.setdefault(r.kind, [])
        if len(hits[r.kind]) < 3:
            hits[r.kind].append(frag)

    sources: list[SourceRef] = []
    for kind, frags in hits.items():
        judge = _json(
            _CORPUS_SYS,
            f"AFIRMACIÓN: el texto de «{song.title}» es un poema/letra de {author}.\n\n"
            "PASAJES:\n" + "\n---\n".join(frags)[:5000],
            max_tokens=150,
        )
        if judge.get("attributes"):
            # mapear kind del corpus a source_kind con su tier
            sk = {
                "genius_annotation": "genius_annotation",  # T3 (sin flag verified aquí)
                "blog": "blog_especializado",
                "forum": "respuestas_del_robe",
                "robe_interview": "robe_voice",
                "about_robe": "blog_especializado",
                "press": "google_serp",
            }.get(kind, "unknown")
            sources.append(SourceRef(
                name=f"corpus:{kind}", source_kind=sk, stance="supports",
                value=author, quote=(judge.get("quote") or "")[:200],
            ))
    return sources


def verify_credit(db, song: Song, author: str, role: str) -> mcv.ConsensusResult:
    """Consenso sobre 'el texto de esta canción es de <author>' (rol autoral)."""
    claim = (
        f"El texto de la canción «{song.title}» de Extremoduro es un poema/letra "
        f"escrito por {author} (no compuesto líricamente por Robe)."
        if role == "poema_original" else
        f"En la canción «{song.title}», {author} firma la parte de {role}."
    )
    fan = SourceRef(name="fan (feedback)", source_kind="fan_feedback",
                    stance="supports", value=author)
    sources = [fan]
    web = _web_source(claim, author)
    if web:
        sources.append(web)
    sources.extend(_corpus_sources(db, song, author))
    # evaluamos la hipótesis "<author>" (las fuentes que la respaldan comparten ese value)
    return mcv.evaluate_hypothesis(
        hypothesis=author, current_value="Robe (atribución previa)", sources=sources,
    )


def apply_credits(db, song: Song, credits: list[dict], confidence: float) -> int:
    """Inserta los SongCredit del YAML (idempotente por uq). Devuelve nº insertados."""
    n = 0
    for c in credits:
        role, name = c.get("role"), c.get("name")
        if not role or not name:
            continue
        exists = db.execute(select(SongCredit).where(
            SongCredit.song_id == song.id,
            SongCredit.credit_role == role,
            SongCredit.credited_name == name,
        )).scalar_one_or_none()
        if exists:
            continue
        person_id = None
        if c.get("person_slug"):
            p = db.execute(select(Person).where(Person.slug == c["person_slug"])).scalar_one_or_none()
            person_id = p.id if p else None
        db.add(SongCredit(
            song_id=song.id, person_id=person_id, credit_role=role,
            credited_name=name, is_primary=bool(c.get("primary")),
            note=c.get("note"), source="consensus", confidence=confidence,
        ))
        n += 1
    return n


def _open_errata(db, song: Song, author: str, result, verif):
    from app.db.models import ErrataReport
    db.add(ErrataReport(
        target_type="authorship", target_id=song.id, field="credit",
        reported_wrong="atribución actual a Robe",
        suggested_right=f"{author} (autoría)", reporter="authorship_consensus",
        status="needs_human", verification_id=verif.id if verif else None,
        resolution_note=f"consenso={result.verdict} conf={result.confidence}",
    ))


def process(db, entry: dict, *, apply: bool) -> None:
    song = _resolve_song(db, entry.get("song_title", ""), entry.get("album_slug"))
    if not song:
        logger.warning("crédito sin canción en BD: %s", entry.get("song_title"))
        return
    credits = entry.get("credits") or []
    # el claim ARRIESGADO es el autor del poema/letra (no "musica: Robe")
    key = next((c for c in credits if c.get("role") in ("poema_original", "letra", "adaptacion")), None)
    if not key:
        return
    author = key["name"]
    logger.info("Verificando autoría de «%s» → %s (%s)...", song.title, author, key["role"])
    result = verify_credit(db, song, author, key["role"])
    action = mcv.decide_fan_correction(result, fan_value=author)
    ext = [s.source_kind for s in result.sources if s.stance == "supports" and s.source_kind != "fan_feedback"]
    logger.info("  veredicto=%s conf=%.2f acción=%s corroboran=%s",
                result.verdict, result.confidence, action, ext)
    verif = mcv.record_verification(
        db, claim_kind="song_authorship",
        claim_key=f"song:{song.id}:authorship:{normalize(author)}",
        result=result, song_id=song.id, applied=(action == "auto_apply" and apply),
    )
    db.flush()
    applied = False
    if action == "auto_apply":
        if apply:
            n = apply_credits(db, song, credits, result.confidence)
            applied = n > 0
            logger.info("  APLICADO: %d créditos insertados en song_credits", n)
        else:
            logger.info("  (dry-run) auto-aplicaría créditos: %s",
                        [f"{c['role']}:{c['name']}" for c in credits])
    else:
        _open_errata(db, song, author, result, verif)
        logger.info("  → errata para revisión humana")
    if apply:
        db.commit()
        if applied:
            # Propagación viva: crédito nuevo → marca grafo sucio (aristas de autoría)
            # + re-embed por si la letra se cita. El barrido corre build_graph al final.
            from app.services import freshness
            freshness.propagate(db, "authorship", song_id=song.id)
    else:
        db.rollback()


def main() -> None:
    p = argparse.ArgumentParser(description="Verificación de autoría por consenso multi-fuente.")
    p.add_argument("--pending", action="store_true")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    db = SessionLocal()
    try:
        for entry in co.pending_only(co.song_credits()):
            process(db, entry, apply=args.apply)
    finally:
        db.close()


if __name__ == "__main__":
    main()
