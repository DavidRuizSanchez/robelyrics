"""Rescate de evergreen DESCARTADAS que el rigor tumbó por genéricas cuando su
ángulo específico se ancló a una entidad demasiado amplia (p.ej. "canciones de
amor de Extremoduro" anclada a la banda entera → pieza genérica de banda).

Re-ancla cada una a la entidad CORRECTA (una temática, una persona…) para que el
motor profundo tire del dossier acertado (todas las letras de amor, la ficha real
de Albert Pla…), regenera con reintentos (varianza del juez) y, si pasa el rigor,
la revive a 'approved' (vuelve a la cola para que David la programe). Si ni así
pasa, se queda descartada.

Mapeo explícito (decidido a mano; NO se auto-re-ancla nada dudoso):
    215 → theme/amor        (Canciones de amor de Extremoduro)
    235 → theme/amor        (Letras de amor y rebeldía)
    274 → person/albert-pla (El universo de Albert Pla)

Uso:
    python -m scripts.blog.rescue_evergreen --dry-run
    python -m scripts.blog.rescue_evergreen --apply
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import Concept, ContentProposal, Person, Place, Song, Theme
from app.db.session import SessionLocal
from app.services.draft_generator import _deep_body, _post_process, _primary_keyword
from app.services.editorial_review import review as editorial_review
from app.services.hero_io import apply_hero

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# proposal_id → (nuevo source_type, slug de la entidad ancla)
_RESCUE = {
    215: ("theme", "amor"),
    235: ("theme", "amor"),
    274: ("person", "albert-pla"),
}

_MODEL = {"theme": Theme, "concept": Concept, "place": Place,
          "person": Person, "song": Song}


def _entity_id(db, source_type: str, slug: str) -> int | None:
    model = _MODEL.get(source_type)
    if not model:
        return None
    ent = db.query(model).filter(model.slug == slug).first()
    return ent.id if ent else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--attempts", type=int, default=3)
    args = ap.parse_args()

    with SessionLocal() as db:
        revived = failed = 0
        for pid, (stype, slug) in _RESCUE.items():
            p = db.get(ContentProposal, pid)
            if not p:
                logger.warning("#%s no existe", pid)
                continue
            eid = _entity_id(db, stype, slug)
            if not eid:
                logger.warning("#%s: ancla %s/%s no resuelve — salto", pid, stype, slug)
                continue
            ent = db.query(_MODEL[stype]).filter(_MODEL[stype].slug == slug).first()
            name = (getattr(ent, "name", None) or getattr(ent, "stage_name", None)
                    or getattr(ent, "full_name", None) or getattr(ent, "title", None) or slug)
            logger.info("[#%s] %s → ancla %s/%s (id %s)", pid, p.title, stype, slug, eid)
            if not args.apply:
                continue

            # Genera con el MOTOR PROFUNDO anclado a la entidad correcta, pero SIN
            # tocar source_type/source_id (evita la constraint única kind+source y no
            # roba el ancla a la ficha de esa entidad). El framing conserva la
            # intención de búsqueda del titular original.
            subject = (p.target_keyword or p.title or "").strip()
            framing = (
                f"{p.title}. Pieza a fondo sobre «{name}» en la obra de Robe/Extremoduro, "
                "anclada al corpus: cita versos REALES (copiados LITERAL del material "
                "[LETRA]; nunca inventes un verso) e ilústralo con canciones y hechos "
                f"concretos. Responde a lo que busca quien teclea «{_primary_keyword(p)}». "
                "Nada genérico ni de relleno."
            )
            winner = None
            best_reject = None
            for n in range(1, args.attempts + 1):
                deep = _deep_body(db, entity_type=stype, entity=ent, framing=framing,
                                  tier="flagship")
                if not deep or not deep.get("body_md"):
                    logger.warning("  intento %d: motor profundo no produjo cuerpo", n)
                    continue
                body, hero = _post_process(db, deep["body_md"], [], subject,
                                           title=deep.get("title") or p.title)
                v = editorial_review(body, kind="evergreen", subject=subject)
                logger.info("  intento %d/%d: %dc · rigor=%s (score %d)",
                            n, args.attempts, len(body), v.verdict, v.score)
                if v.verdict in ("pass", "revise"):
                    if v.verdict == "revise" and v.tightened_body_md and \
                            len(v.tightened_body_md) >= 250:
                        body = v.tightened_body_md
                    winner = {"body": body, "hero": hero, "deep": deep, "v": v}
                    break
                if best_reject is None or v.score > best_reject.score:
                    best_reject = v

            if winner:
                d = winner["deep"]
                p.body_md = winner["body"]
                p.title = (d.get("title") or p.title)[:240]
                p.excerpt = d.get("excerpt") or p.excerpt
                p.meta_title = (d.get("meta_title") or None)
                p.meta_description = (d.get("meta_description") or None)
                if winner["hero"]:
                    apply_hero(p, winner["hero"])  # paquete completo, sin desincronizar
                p.quality_tier = "flagship"
                p.status = "approved"  # vuelve a la cola (David la programa)
                db.commit()
                revived += 1
                logger.info("  ✓ REVIVIDA a 'approved' (rigor %s score %d): «%s»",
                            winner["v"].verdict, winner["v"].score, p.title)
            else:
                db.rollback()
                failed += 1
                logger.info("  ✗ sigue sin pasar (mejor score %s) → queda descartada",
                            best_reject.score if best_reject else "—")

        logger.info("Rescate %s: %d revividas · %d siguen fuera",
                    "aplicado" if args.apply else "[DRY-RUN]", revived, failed)


if __name__ == "__main__":
    main()
