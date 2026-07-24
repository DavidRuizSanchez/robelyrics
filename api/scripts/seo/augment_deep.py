"""Motor de AUGMENTACIÓN de contenido (estándar de regeneración sin pérdida).

Filosofía (decisión de David, jul-2026): NO regenerar de cero (es un dado que pierde
información y encoge). En su lugar, coger el `body_md` publicado como SUELO y AMPLIARLO
con material verificado que aún no cubre: huecos del corpus, eventos recientes con fuente
web, y vídeos relevantes. Contrato duro:

  - No se pierde información: el contenido actual se conserva íntegro (se AÑADE, no se
    reescribe) → gate trivial de "no-info-loss".
  - Se amplía y se crean secciones nuevas cuando hay material real que las sostenga.
  - `len(after) >= len(before)` SIEMPRE (nunca encoge).
  - Vídeos: los ya embebidos se conservan (son parte del body actual) y se AÑADEN nuevos
    relevantes verificados (news_research.find_video), en su propia línea (el front los
    convierte en embed vía embed_youtube_links).
  - Cada sección nueva pasa `_verify_section` (factual vs material) y el conjunto pasa
    `editorial_review`. Si no hay nada verificado que añadir → no-op (se conserva la actual).

`augment_entity()` NO persiste: devuelve el resultado para que el runner (augment_all) lo
revise/aplique con backup. Reutiliza el motor profundo existente (generate_deep) y los
verificadores (web_verify, fact_check), sin duplicar lógica.
"""
from __future__ import annotations

import logging
import re

from openai import OpenAI

from app.services.deep_research import gather_entity_dossier
from app.services.entity_resolver import (
    autolink_corpus,
    build_corpus_index,
    load_link_stats,
)
from app.services.text_sanitizer import normalize_headings, strip_ai_tells
from scripts.seo.generate_deep import _chat, _verify_section, _write_section

logger = logging.getLogger(__name__)

_YT_LINE = re.compile(
    r"^\s*(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+)\s*$", re.M
)


def _existing_videos(body_md: str) -> list[str]:
    return _YT_LINE.findall(body_md or "")


def discover_recent_events(client: OpenAI, subject: str, *, max_events: int = 3) -> list[dict]:
    """Descubre eventos recientes VERIFICADOS sobre `subject` (figuras clave).

    Propone candidatos con el LLM, los contrasta uno a uno con `web_verify.classify_fact`
    (SERP real) y solo acepta los `supported` con fuente. Añade vídeo si `find_video` lo
    encuentra. Nunca inventa: lo no corroborado se descarta.
    """
    from app.services.news_research import find_video
    from app.services.web_verify import classify_fact

    try:
        cand = _chat(
            client,
            "Eres un archivero musical riguroso. Lista hasta 5 posibles HECHOS RECIENTES "
            f"(2023-2026) sobre «{subject}» (premios, homenajes, fallecimiento, discos, "
            "giras, reconocimientos) que una ficha enciclopédica debería recoger. Para cada "
            "uno da una query corta para buscar su vídeo si lo hubiera. NO inventes: si no "
            "estás seguro de un hecho, no lo incluyas. Devuelve JSON "
            '{"events":[{"fact":"<frase concreta y datable>","video_query":"<query o vacío>"}]}.',
            max_tokens=700,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[augment] discover falló para %s: %s", subject, exc)
        return []

    out: list[dict] = []
    for e in (cand.get("events") or [])[:5]:
        fact = (e.get("fact") or "").strip()
        if not fact:
            continue
        try:
            v = classify_fact(fact)
        except Exception:  # noqa: BLE001
            continue
        if (v.get("verdict") or "").lower() != "supported":
            continue  # solo hechos corroborados por web
        ev = {"fact": fact, "source": v.get("source") or "web verificada",
              "evidence": (v.get("evidence") or "")[:200]}
        vq = (e.get("video_query") or "").strip()
        if vq:
            try:
                vid = find_video(vq, subject)
                if vid:
                    ev["video"] = f"https://www.youtube.com/watch?v={vid['youtube_id']}"
            except Exception:  # noqa: BLE001
                pass
        out.append(ev)
        if len(out) >= max_events:
            break
    return out


def _write_recent_section(client, subject, events, existing_heads, hard, prior):
    material = "EVENTOS RECIENTES VERIFICADOS (con fuente; NO añadas nada fuera de esto):\n" + \
        "\n".join(f"- {e['fact']} (fuente: {e.get('source', 'web')})" for e in events)
    covers = "; ".join(e["fact"] for e in events)
    sec = {"heading": "Sus últimos años y los homenajes", "covers": covers}
    body = _write_section(client, subject, sec, existing_heads + [sec["heading"]],
                          hard, material, kw_block="", prior=prior, tier="premium")
    body = _verify_section(client, body, material)
    if not body.strip():
        return None, []
    vids = [e["video"] for e in events if e.get("video")]
    if vids:
        body = body.strip() + "\n\n" + "\n\n".join(vids)
    return body.strip(), vids


def _corpus_gap_section(client, subject, current, dossier, existing_heads, prior):
    gap = _chat(
        client,
        f"Texto ACTUAL sobre {subject} (es el suelo, NO lo reescribas):\n"
        f'"""{current[:6000]}"""\n\n'
        f'MATERIAL DEL CORPUS (única fuente de hechos):\n"""{dossier.material[:12000]}"""\n\n'
        "Lista SOLO hechos/ángulos VERACES del material que NO estén ya cubiertos en el "
        "texto y merezcan una sección nueva con sustancia (fechas, obras, colaboraciones, "
        "hechos concretos). NADA que ya esté en el texto. Máximo 1. Devuelve JSON "
        '{"gaps":[{"heading":"<H2 concreto>","covers":"<qué cubre, nuevo>"}]}. '
        'Si no hay hueco real, {"gaps":[]}.',
        max_tokens=600,
    )
    gaps = (gap.get("gaps") or []) if isinstance(gap, dict) else []
    if not gaps:
        return None, None
    g = gaps[0]
    body = _write_section(client, subject, g, existing_heads + [g["heading"]],
                          dossier.hard_facts, dossier.material, kw_block="", prior=prior,
                          tier="premium")
    body = _verify_section(client, body, dossier.hard_facts + "\n\n" + dossier.material)
    return (body.strip() or None), g.get("heading")


def augment_entity(
    db,
    client: OpenAI,
    entity_type: str,
    entity,
    *,
    recent_events: list[dict] | None = None,
    discover_web: bool = False,
    corpus_index=None,
    link_stats=None,
) -> dict | None:
    """Aumenta la ficha de una entidad SIN persistir. Devuelve dict con before/after y
    metadatos, o None si no había SeoContent que aumentar."""
    from app.db.models import SeoContent

    sc = (
        db.query(SeoContent)
        .filter(SeoContent.entity_type == entity_type, SeoContent.slug == entity.slug)
        .first()
    )
    if not sc or not (sc.body_md or "").strip():
        logger.info("[augment] %s/%s sin body_md; nada que aumentar", entity_type, entity.slug)
        return None

    current = sc.body_md
    subject = (getattr(entity, "stage_name", None) or getattr(entity, "name", None)
               or getattr(entity, "full_name", None) or getattr(entity, "title", None)
               or entity.slug)
    existing_heads = re.findall(r"^##\s+(.*)$", current, re.M)
    dossier = gather_entity_dossier(db, entity_type, entity)

    events = list(recent_events or [])
    if discover_web:
        events += discover_recent_events(client, subject)

    added: list[str] = []
    added_heads: list[str] = []
    videos: list[str] = []
    prior = current

    if events:
        sec, vids = _write_recent_section(client, subject, events, existing_heads,
                                          dossier.hard_facts, prior)
        if sec:
            added.append(sec); added_heads.append("Sus últimos años y los homenajes")
            videos += vids; prior = prior + "\n\n" + sec

    gap_body, gap_head = _corpus_gap_section(client, subject, current, dossier,
                                             existing_heads + added_heads, prior)
    if gap_body:
        added.append(gap_body); added_heads.append(gap_head or "Más"); prior = prior + "\n\n" + gap_body

    if not added:
        return {"before": current, "after": current, "added_headings": [], "videos_added": [],
                "grew": False, "noop": True, "subject": subject}

    after = current.rstrip() + "\n\n" + "\n\n".join(added)
    # El LLM a veces devuelve el heading envuelto en <> (eco del placeholder de la
    # plantilla): «## <Título>». Se limpia para que no rompa el markdown.
    after = re.sub(r"^(#{2,3}\s*)<\s*(.+?)\s*>\s*$", r"\1\2", after, flags=re.M)
    added_heads = [re.sub(r"^<\s*(.+?)\s*>$", r"\1", h) for h in added_heads]
    after = normalize_headings(after) or after
    after = strip_ai_tells(after) or after
    after = autolink_corpus(
        after, corpus_index if corpus_index is not None else build_corpus_index(db),
        max_links=6, exclude_slug=entity.slug,
        link_stats=link_stats if link_stats is not None else load_link_stats(),
    )

    # GATE ANTI-PAJA (bloqueante): la ampliación SOLO se aplica si mejora o mantiene
    # la calidad. Se compara el rigor del cuerpo ORIGINAL vs el aumentado; si el
    # añadido es relleno (conexiones temáticas genéricas, redundancia) el rigor lo
    # castiga → se DESCARTA la ampliación y se conserva el original (no-op). Sin esto,
    # el auto-detector de huecos metía secciones de "paja" en canciones/discos.
    rigor = None
    try:
        from app.services.editorial_review import review as editorial_review
        allowed = {subject.lower()}
        v_before = editorial_review(current, kind=entity_type, subject=subject,
                                    allowed_terms=allowed)
        v = editorial_review(after, kind=entity_type, subject=subject, allowed_terms=allowed)
        rigor = {"verdict": v.verdict, "score": v.score, "before_score": v_before.score}
        if v.verdict == "reject" or v.score < v_before.score:
            logger.info("[augment] %s/%s: la ampliación no mejora (antes %d → después %d, %s) "
                        "→ no-op (se conserva el original)",
                        entity_type, entity.slug, v_before.score, v.score, v.verdict)
            return {"before": current, "after": current, "added_headings": [],
                    "videos_added": [], "grew": False, "noop": True,
                    "subject": subject, "rigor": rigor}
        if v.verdict == "revise" and v.tightened_body_md and len(v.tightened_body_md) >= len(current):
            after = v.tightened_body_md  # tensado, pero nunca por debajo del original
    except Exception as exc:  # noqa: BLE001
        logger.warning("[augment] rigor falló: %s", exc)

    grew = len(after) >= len(current)
    return {
        "seo_id": sc.id, "subject": subject,
        "before": current, "after": after,
        "before_len": len(current), "after_len": len(after),
        "added_headings": added_heads, "videos_added": videos,
        "existing_videos": _existing_videos(current),
        "grew": grew, "noop": False, "rigor": rigor,
    }
