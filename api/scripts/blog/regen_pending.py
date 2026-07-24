"""Regenera la cola de blog PENDIENTE de publicar con el pipeline nuevo (scoring
de engagement + motor profundo), para que nada flojo ("paja") llegue a producción.

Contexto: muchas propuestas del banco se crearon con el motor viejo (one-shot de
500-900 palabras) y tienen `quality_tier` NULL. `materialize_proposals` las
publicaba tal cual. Este script las regenera de golpe:

  - evergreen 'seo' → se ancla a su entidad central (blog_anchor) y se genera con
    el motor profundo; si no hay ancla fiable, one-shot clásico (lo retiene el rigor).
  - spotlight / album-anniversary / anniversary / evergreen de taxonomía → motor
    profundo directo (ya anclados).
  - news → NO se regenera el cuerpo (viene del scraper, no hay entidad que
    profundizar); solo se le backfillea el score y pasa por el gate de rigor.

Tras regenerar, corre el gate de RIGOR: si no llega, la propuesta va a 'discarded'
(o el post a revisión). El estado de las que pasan se conserva (scheduled sigue
scheduled).

Modos:
  --plan                 Solo informe de anclajes (SIN coste LLM). Empieza por aquí.
  --sample --ids A B     Regenera en MEMORIA (no persiste) e imprime before/after.
  --apply                Regenera y PERSISTE (con gate de rigor). Conserva estado.
  --apply --ids A B      Solo esas propuestas.
  --apply --post-ids 35  Además, regenera el/los post ya PUBLICADOS (vía su
                         propuesta origen) y los re-publica si pasan el rigor.

SIEMPRE: --plan → --sample de unas pocas → validar → --apply.
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal, Post
from app.db.session import SessionLocal
from app.services.blog_anchor import resolve_central_entity
from app.services.draft_generator import (
    _primary_keyword,
    generate_proposal_draft,
)
from app.services.editorial_review import review as editorial_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LIVE = ("proposed", "approved", "scheduled")


def _anchor_label(db, p: ContentProposal) -> str:
    """Descripción de cómo se generaría (para --plan), sin generar nada."""
    if p.kind == "news":
        return "news (cuerpo del scraper; solo rescore + rigor)"
    if p.kind == "spotlight":
        return "PROFUNDO ← canción (spotlight)"
    if p.kind == "album-anniversary":
        return "PROFUNDO ← disco (aniversario)"
    if p.kind == "anniversary":
        return "PROFUNDO ← Robe (efeméride)"
    if p.kind == "evergreen":
        if p.source_type in ("theme", "place", "concept", "person", "artist", "band"):
            return f"PROFUNDO ← {p.source_type} (ya anclado)"
        if p.source_type == "seo":
            a = resolve_central_entity(
                db, primary_keyword=_primary_keyword(p), title=p.title, angle=p.angle
            )
            if a:
                return f"PROFUNDO ← {a.entity_type}/«{a.name}» (score {a.score}, match {a.matched_in})"
            return "one-shot (sin ancla fiable → lo juzga el rigor)"
    return f"{p.kind}/{p.source_type}"


def _plan(db, ids: list[int] | None) -> None:
    q = db.query(ContentProposal).filter(ContentProposal.status.in_(LIVE))
    if ids:
        q = q.filter(ContentProposal.id.in_(ids))
    props = q.order_by(ContentProposal.status, ContentProposal.scheduled_for.nulls_last()).all()
    logger.info("Plan de regeneración para %d propuestas vivas:\n", len(props))
    deep = oneshot = news = 0
    for p in props:
        label = _anchor_label(db, p)
        if label.startswith("PROFUNDO"):
            deep += 1
        elif label.startswith("news"):
            news += 1
        else:
            oneshot += 1
        chars = len(p.body_md or "")
        print(f"  #{p.id:<4} {p.status:<9} {p.kind:<17} {chars:>5}c  {label}")
        print(f"        «{(p.title or '')[:70]}»")
    print(f"\n  → {deep} profundos · {oneshot} one-shot (sin ancla) · {news} news")


def _regen_one(db, p: ContentProposal, *, persist: bool) -> tuple[bool, str]:
    """Regenera una propuesta. Devuelve (ok, motivo). Con persist=False no toca BD."""
    before = len(p.body_md or "")
    before_tier = p.quality_tier
    # Fuerza el pipeline nuevo: borra tier (rescore) y, salvo news, borra cuerpo
    # para que se regenere por el motor profundo.
    p.quality_tier = None
    p.engagement_score = None
    if p.kind != "news":
        p.body_md = None
    ok = generate_proposal_draft(db, p, persist=persist)
    if not ok:
        return False, "generate_proposal_draft falló"
    after = len(p.body_md or "")
    return True, f"{before}c ({before_tier}) → {after}c ({p.quality_tier})"


def _sample(db, ids: list[int]) -> None:
    props = db.query(ContentProposal).filter(ContentProposal.id.in_(ids)).all()
    for p in props:
        logger.info("=== MUESTRA #%s (%s/%s) — %s", p.id, p.kind, p.source_type, p.title)
        logger.info("    ancla: %s", _anchor_label(db, p))
        ok, info = _regen_one(db, p, persist=False)
        if not ok:
            logger.warning("    ✗ %s", info)
            db.rollback()
            continue
        v = editorial_review(p.body_md, kind=p.kind,
                             subject=(p.target_keyword or p.title or "").strip())
        logger.info("    %s · rigor=%s (score %s)", info, v.verdict, v.score)
        print("\n----- CUERPO NUEVO (sin persistir) -----")
        print(p.body_md)
        print("----- fin -----\n")
        db.rollback()  # NO persistir: muestra


def _apply_proposals(db, ids: list[int] | None) -> None:
    q = db.query(ContentProposal).filter(ContentProposal.status.in_(LIVE))
    if ids:
        q = q.filter(ContentProposal.id.in_(ids))
    props = q.order_by(ContentProposal.id).all()
    logger.info("Regenerando %d propuestas vivas…", len(props))
    stats = {"ok": 0, "descartadas": 0, "fallo": 0}
    for p in props:
        logger.info("[#%s] (%s) %s", p.id, p.kind, p.title)
        ok, info = _regen_one(db, p, persist=True)
        if not ok:
            stats["fallo"] += 1
            logger.warning("  ✗ %s", info)
            db.rollback()
            continue
        logger.info("  %s", info)
        v = editorial_review(p.body_md, kind=p.kind,
                             subject=(p.target_keyword or p.title or "").strip())
        if v.verdict == "reject":
            p.status = "discarded"
            db.commit()
            stats["descartadas"] += 1
            logger.info("  ✗ rigor rechaza (score %d): %s → discarded",
                        v.score, "; ".join(v.reasons))
            continue
        if v.verdict == "revise" and v.tightened_body_md:
            p.body_md = v.tightened_body_md
        db.commit()
        stats["ok"] += 1
        logger.info("  ✓ regenerada (rigor %s, score %d)", v.verdict, v.score)
    logger.info("Propuestas: %d OK · %d descartadas · %d fallo",
                stats["ok"], stats["descartadas"], stats["fallo"])


def _apply_posts(db, post_ids: list[int], *, attempts: int = 4) -> None:
    """Regenera posts YA publicados vía su propuesta origen. Como la generación y
    el juez de rigor tienen VARIANZA, reintenta hasta `attempts` veces y se queda
    con el PRIMER cuerpo que pase el rigor (pass/revise). NUNCA deja vivo un cuerpo
    rechazado: si todos los intentos caen, el post NO se toca (se conserva su cuerpo
    previo) y se avisa para intervención manual."""
    from app.services.publishing import auto_publish_post
    for pid in post_ids:
        post = db.get(Post, pid)
        if not post:
            logger.warning("post #%s no existe", pid)
            continue
        prop = (db.query(ContentProposal)
                .filter(ContentProposal.post_id == pid)
                .order_by(ContentProposal.id.desc()).first())
        if not prop:
            logger.warning("post #%s sin propuesta origen — no se regenera", pid)
            continue
        logger.info("[post #%s ← prop #%s] %s", pid, prop.id, post.title)

        winner = None  # dict con el borrador que pasa el rigor
        best_reject = None  # (score, reasons) del mejor intento fallido, para el aviso
        for n in range(1, attempts + 1):
            ok, info = _regen_one(db, prop, persist=True)
            if not ok:
                logger.warning("  intento %d/%d: %s", n, attempts, info)
                db.rollback()
                continue
            v = editorial_review(prop.body_md, kind=prop.kind,
                                 subject=(prop.target_keyword or prop.title or "").strip())
            logger.info("  intento %d/%d: %s · rigor=%s (score %d)",
                        n, attempts, info, v.verdict, v.score)
            if v.verdict in ("pass", "revise"):
                body = v.tightened_body_md if (v.verdict == "revise" and v.tightened_body_md) \
                    else prop.body_md
                winner = {
                    "body": body, "title": (prop.title or post.title)[:240],
                    "excerpt": prop.excerpt or post.excerpt,
                    "meta_title": prop.meta_title or post.meta_title or None,
                    "meta_description": prop.meta_description or post.meta_description or None,
                    "hero_image_url": prop.hero_image_url or post.hero_image_url,
                    "hero_image_alt": prop.hero_image_alt or post.hero_image_alt,
                    "entities": prop.entities or post.entities,
                    "videos": prop.videos or post.videos, "video": prop.video or post.video,
                    "engagement_score": prop.engagement_score, "quality_tier": prop.quality_tier,
                    "score": v.score, "verdict": v.verdict,
                }
                break
            if best_reject is None or v.score > best_reject[0]:
                best_reject = (v.score, v.reasons)

        if not winner:
            # Todos los intentos rechazados: NO tocamos el post vivo (mejor su cuerpo
            # actual que uno rechazado). Se avisa para intervención manual.
            db.rollback()
            reasons = "; ".join(best_reject[1]) if best_reject else "—"
            logger.warning("  ✗ post #%s: %d intentos y NINGUNO pasa el rigor (mejor score %s). "
                           "Post SIN cambios; requiere intervención manual. Motivos: %s",
                           pid, attempts, best_reject[0] if best_reject else "—", reasons)
            continue

        for k, val in winner.items():
            if k in ("score", "verdict"):
                continue
            setattr(post, k, val)
        auto_publish_post(db, post, factcheck=False, rigor=False)
        db.commit()
        logger.info("  ✓ post #%s republicado (tier %s, rigor %s score %d): /blog/%s",
                    pid, post.quality_tier, winner["verdict"], winner["score"], post.slug)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", action="store_true", help="solo informe de anclajes (sin coste)")
    ap.add_argument("--sample", action="store_true", help="regenera en memoria (no persiste)")
    ap.add_argument("--apply", action="store_true", help="regenera y persiste")
    ap.add_argument("--ids", type=int, nargs="*", help="solo estas propuestas")
    ap.add_argument("--post-ids", type=int, nargs="*", help="posts publicados a regenerar")
    args = ap.parse_args()

    with SessionLocal() as db:
        if args.plan:
            _plan(db, args.ids)
            return
        if args.sample:
            if not args.ids:
                ap.error("--sample requiere --ids")
            _sample(db, args.ids)
            return
        if args.apply:
            if args.ids is not None or not args.post_ids:
                _apply_proposals(db, args.ids)
            if args.post_ids:
                _apply_posts(db, args.post_ids)
            return
        ap.error("indica un modo: --plan | --sample | --apply")


if __name__ == "__main__":
    main()
