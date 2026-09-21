"""Amplía posts del blog atascados en `pending_review` SIN perder nada de lo que
ya dicen.

El motor de augmentación (`scripts.seo.augment_deep`) solo sabía de fichas de
entidad: `augment_entity` busca su `SeoContent` por `entity_id` y sin eso no hace
nada. Los posts del blog no tienen ficha, así que la cola de revisión no tenía
forma de mejorar: o se publicaba floja, o se rechazaba. Este runner ancla el post
a su entidad central (`blog_anchor`) y le aplica el MISMO contrato, reutilizando
las piezas del motor —no copiándolas—: `_corpus_gap_section` para escribir lo que
falta a partir del dossier real, y el gate anti-paja que compara el rigor de
antes y después.

Contrato (idéntico al de las fichas):
  - Se AÑADE, nunca se reescribe: el cuerpo actual se conserva íntegro.
  - `len(after) >= len(before)` siempre.
  - Si la ampliación no sube el rigor, se descarta y se conserva el original.
  - Sin material real en el corpus → no-op. Nunca se rellena por rellenar.

Uso:
    python -m scripts.blog.augment_posts --plan            # qué se puede anclar (sin coste)
    python -m scripts.blog.augment_posts --ids 20 22       # prueba en memoria
    python -m scripts.blog.augment_posts --ids 20 --apply  # persiste
"""
from __future__ import annotations

import argparse
import logging
import re

from openai import OpenAI

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.blog_anchor import resolve_central_entity
from app.services.deep_research import gather_entity_dossier
from app.services.editorial_review import review as editorial_review
from app.services.entity_resolver import autolink_corpus, build_corpus_index, load_link_stats
from app.services.text_sanitizer import normalize_headings, strip_ai_tells
from scripts.seo.augment_deep import _corpus_gap_section

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _ancla(db, post: Post):
    """La entidad central del post, o None si no hay match claro (blog_anchor es
    conservador a propósito: sin ancla fiable no se amplía nada)."""
    return resolve_central_entity(
        db, primary_keyword=post.target_keyword, title=post.title,
        angle=post.excerpt,
    )


def augmentar(db, client: OpenAI, post: Post, *, corpus_index, link_stats,
              gap_hint: str | None = None, solo_anadir: bool = False) -> dict:
    """Amplía un post SIN persistir. Devuelve el before/after y por qué.

    `solo_anadir` endurece el contrato para lo que YA ESTÁ PUBLICADO: el texto
    resultante debe empezar por el actual, carácter a carácter. Sin eso, el
    «tensado» del editor jefe puede reescribir una pieza que Google ya indexó, y
    eso no es ampliar: es cambiarla por otra a espaldas de quien la aprobó.
    """
    current = (post.body_md or "").strip()
    if not current:
        return {"post_id": post.id, "noop": True, "motivo": "sin cuerpo"}

    anchor = _ancla(db, post)
    if anchor is None:
        return {"post_id": post.id, "noop": True, "motivo": "sin ancla fiable"}

    subject = anchor.name
    heads = re.findall(r"^##\s+(.*)$", current, re.M)
    dossier = gather_entity_dossier(db, anchor.entity_type, anchor.entity)

    gap_body, gap_head = _corpus_gap_section(
        client, subject, current, dossier, heads, current, gap_hint=gap_hint,
    )
    if not gap_body:
        return {"post_id": post.id, "noop": True, "motivo": "el corpus no da para más",
                "subject": subject}

    if solo_anadir:
        # En lo YA PUBLICADO se limpia y enlaza SOLO el trozo nuevo. El enlazado
        # interno reescribe el cuerpo entero metiendo enlaces markdown, así que
        # pasárselo al original rompería la promesa de no tocar lo que Google ya
        # indexó — y de paso haría imposible comprobar que no se ha tocado.
        nuevo = re.sub(r"^(#{2,3}\s*)<\s*(.+?)\s*>\s*$", r"\1\2", gap_body, flags=re.M)
        nuevo = normalize_headings(nuevo) or nuevo
        nuevo = strip_ai_tells(nuevo) or nuevo
        nuevo = autolink_corpus(nuevo, corpus_index, max_links=6,
                                exclude_slug=anchor.entity.slug, link_stats=link_stats)
        after = current.rstrip() + "\n\n" + nuevo.strip() + "\n"
    else:
        after = current.rstrip() + "\n\n" + gap_body
        after = re.sub(r"^(#{2,3}\s*)<\s*(.+?)\s*>\s*$", r"\1\2", after, flags=re.M)
        after = normalize_headings(after) or after
        after = strip_ai_tells(after) or after
        after = autolink_corpus(after, corpus_index, max_links=6,
                                exclude_slug=anchor.entity.slug, link_stats=link_stats)

    # GATE ANTI-PAJA: la ampliación solo vale si MEJORA. Si el añadido es relleno,
    # el rigor lo castiga y se conserva el original.
    allowed = {subject.lower()}
    v_before = editorial_review(current, kind=post.kind, subject=subject,
                                allowed_terms=allowed)
    v_after = editorial_review(after, kind=post.kind, subject=subject,
                               allowed_terms=allowed)
    if v_after.verdict == "reject" or v_after.score < v_before.score:
        return {"post_id": post.id, "noop": True, "subject": subject,
                "motivo": f"no mejora ({v_before.score} → {v_after.score}, {v_after.verdict})",
                "before_score": v_before.score, "after_score": v_after.score}
    if (v_after.verdict == "revise" and v_after.tightened_body_md
            and len(v_after.tightened_body_md) >= len(current)
            and not solo_anadir):
        after = v_after.tightened_body_md

    if solo_anadir and not after.startswith(current.rstrip()):
        # Se ha tocado algo de lo que ya había: no es una ampliación.
        return {"post_id": post.id, "noop": True, "subject": subject,
                "motivo": "el resultado no conserva el texto publicado intacto"}

    if len(after) < len(current):  # cinturón: nunca encoge
        return {"post_id": post.id, "noop": True, "subject": subject,
                "motivo": "el resultado encogía"}

    return {
        "post_id": post.id, "subject": subject, "noop": False,
        "before": current, "after": after,
        "before_len": len(current), "after_len": len(after),
        "added": gap_body, "heading": gap_head, "before_score": v_before.score,
        "after_score": v_after.score, "verdict": v_after.verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="*", type=int, help="ids de post concretos")
    parser.add_argument("--status", default="pending_review",
                        choices=["pending_review", "published", "draft", "all"],
                        help="qué estado mirar. `published` activa el modo solo-añadir")
    parser.add_argument("--gap-hint", dest="gap_hint",
                        help="por dónde ampliar (p.ej. «el fallecimiento de Robe»)")
    parser.add_argument("--plan", action="store_true",
                        help="solo dice qué ancla tiene cada uno (sin coste LLM)")
    parser.add_argument("--apply", action="store_true", help="persiste el resultado")
    args = parser.parse_args()

    with SessionLocal() as db:
        # `--ids` restringe, pero el ESTADO lo elige `--status`: antes el filtro
        # de `pending_review` era fijo, así que un post ya publicado no se podía
        # ampliar aunque se pidiera por id (salía «Posts a mirar: 0»).
        q = db.query(Post)
        if args.status != "all":
            q = q.filter(Post.status == args.status)
        if args.ids:
            q = q.filter(Post.id.in_(args.ids))
        posts = q.order_by(Post.created_at).all()
        logger.info("Posts a mirar: %d", len(posts))

        if args.plan:
            for post in posts:
                anchor = _ancla(db, post)
                destino = f"{anchor.entity_type}/{anchor.entity.slug}" if anchor else "— SIN ANCLA"
                logger.info("#%s %-52s → %s", post.id, post.title[:52], destino)
            return

        client = OpenAI()
        corpus_index = build_corpus_index(db)
        link_stats = load_link_stats()
        crecidos = 0
        for post in posts:
            logger.info("#%s %s", post.id, post.title[:60])
            try:
                res = augmentar(db, client, post, corpus_index=corpus_index,
                                link_stats=link_stats, gap_hint=args.gap_hint,
                                solo_anadir=post.status == "published")
            except Exception:
                logger.exception("  falló la ampliación de #%s", post.id)
                continue
            if res.get("noop"):
                logger.info("  no-op: %s", res.get("motivo"))
                continue
            logger.info("  %d → %d caracteres · rigor %d → %d · «%s»",
                        res["before_len"], res["after_len"],
                        res["before_score"], res["after_score"], res.get("heading"))
            crecidos += 1
            if not args.apply:
                # Sin --apply esto es una MUESTRA para validar a ojo: se enseña
                # tal cual lo añadido, que es lo único que cambia.
                print("\n----- LO QUE AÑADE -----")
                print(res["added"].strip())
                print("----- fin -----\n")
            if args.apply:
                estaba_publicado = post.status == "published"
                post.body_md = res["after"]
                db.commit()
                logger.info("  ✓ aplicado")
                if estaba_publicado:
                    # Lo publicado se sirve cacheado: sin esto, el cambio tarda
                    # hasta diez minutos en verse y parece que no se aplicó.
                    from app.services.publishing import _revalidate_next
                    _revalidate_next(post.slug)
                    logger.info("  ✓ revalidado en la web")
        logger.info("Ampliados: %d/%d%s", crecidos, len(posts),
                    "" if args.apply else " (en memoria; usa --apply para persistir)")


if __name__ == "__main__":
    main()
