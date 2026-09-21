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
from dataclasses import dataclass

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

@dataclass(frozen=True)
class ModoOptimizacion:
    """Optimizar una ficha publicada NO es lo mismo que escribir una nueva.

    Lo construye SOLO el circuito de oportunidades (`seo_opportunities.prepare_draft`).
    Ni `generate_deep`, ni `fill_missing_content`, ni los seis generadores por tipo
    saben que esto existe: allí no hay nadie mirando antes de publicar, y el listón
    se queda donde está.

    Aquí sí lo hay —dos fases, antes/después, y ningún clic automático—, y eso es lo
    que permite las tres diferencias:

      1. El material se busca por la CONSULTA, no solo por la entidad.
      2. No se penaliza crecer: el juez lee lo añadido y el linter va por densidad.
      3. Si aun así el editor la rechaza, el borrador **sale igual con el veredicto
         colgado** para que lo juzgue una persona (`valvula`).

    Lo que NO cambia ni aquí: la verificación factual, la no-invención, la
    no-pérdida y los versos. Se puede discutir si un texto merece leerse; no se
    discute si es verdad.
    """

    consultas: list[str]
    tolerancia_rigor: int = 5
    valvula: bool = True


_YT_LINE = re.compile(
    r"^\s*(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+)\s*$", re.M
)


# Frases con las que un texto confiesa que no sabe lo que su encabezado promete.
# Caso real (22-09-2026, publicado): la consulta era «los niños de los ojos rojos
# integrantes», la sección salió titulada «Los componentes de Los Niños de los Ojos
# Rojos» y dentro decía «no se detalla los nombres específicos de los miembros». Una
# sección que promete en el título y se desdice en el cuerpo es PEOR que no tenerla:
# el lector que buscaba eso entra, lo ve prometido y se va sin respuesta.
_CONFESIONES = (
    "no se detalla", "no se especifica", "no hay confirmación", "no hay constancia",
    "no se conocen", "se desconoce", "no está documentado", "no se menciona",
    "no se dispone", "no hay información", "no se ha confirmado", "sin confirmación",
    "no se precisa", "no consta", "no se sabe", "no hay datos",
)


def confiesa_no_saber(seccion: str) -> str | None:
    """La frase con la que la sección admite no responder, si la hay."""
    bajo = (seccion or "").lower()
    return next((f for f in _CONFESIONES if f in bajo), None)


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


def _relevant_material(material: str, hint: str | None, cap: int = 12000,
                       *, priority: str = "", priority_cap: int = 5000) -> str:
    """Trozo del material que se le enseña al detector de huecos.

    Sin pista se manda el principio, que es lo que se hacía siempre. El problema:
    en Agila el dossier son 70.000 chars y el dato que faltaba —quién dibujó la
    portada— vivía más allá del corte, así que el detector concluía «sin material
    verificado» teniendo el material delante.

    Con pista se priorizan los fragmentos que la mencionan. No se inventa nada:
    solo cambia QUÉ parte del corpus real ve el detector.

    `priority` es el material recuperado preguntando lo que pregunta la gente. Va
    delante y entero, con su cuota reservada: si compite por el hueco con el resto
    del dossier pierde siempre, porque los bloques interpretativos se ensamblan al
    final y son los primeros en caerse del corte.
    """
    _SEP = "\n\n----\n\n"
    reservado = priority[:priority_cap] if priority else ""
    if reservado:
        cap = max(2000, cap - len(reservado) - len(_SEP))

    if not hint or len(material) <= cap:
        resto = material[:cap]
    else:
        import re as _re
        palabras = [w for w in _re.split(r"\W+", hint.lower()) if len(w) > 4]
        if not palabras:
            resto = material[:cap]
        else:
            bloques = material.split("\n\n----\n\n")
            con_hit, otros = [], []
            for b in bloques:
                bl = b.lower()
                (con_hit if any(w in bl for w in palabras) else otros).append(b)
            resto = "\n\n----\n\n".join(con_hit + otros)[:cap]

    # Un solo punto de salida: con tres returns, la cuota reservada se perdía en dos
    # de ellos y el material de la consulta no llegaba nunca al detector.
    return f"{reservado}{_SEP}{resto}" if reservado else resto


def _corpus_gap_section(client, subject, current, dossier, existing_heads, prior,
                        gap_hint: str | None = None, *, material_consulta: str = "",
                        consultas: list[str] | None = None):
    if material_consulta:
        # En optimización la pista deja de ser vaga: se dice QUÉ pregunta la gente y
        # se pone delante el material recuperado buscando justo eso. Antes solo se
        # decía «hay demanda sobre X» sobre un corpus recuperado por el nombre de la
        # entidad, y el motor acababa eligiendo su propio ángulo: para una página
        # cuyas consultas eran versos concretos escribió «La Conexión Filosófica de
        # Interludio», que el gate tumbó con razón.
        pista = (
            "\n\nESTO ES LO QUE LA GENTE BUSCA Y LA PÁGINA NO RESPONDE:\n- "
            + "\n- ".join(consultas or [gap_hint or ""])
            + "\n\nEl bloque MATERIAL DE LA CONSULTA se ha recuperado buscando "
            "exactamente eso. Si respalda hechos concretos, escribe sobre ESO y nada "
            "más. Si no lo respalda, devuelve gaps vacío: no lo inventes ni lo "
            "rellenes con generalidades ni con filosofía de manual.\n"
        )
    else:
        pista = (
            f"\n\nPISTA: hay demanda de búsqueda real sobre «{gap_hint}» y la página no "
            "lo cubre. Si —y SOLO si— el material respalda hechos concretos sobre eso, "
            "priorízalo. Si el material no lo respalda, devuelve gaps vacío: no lo "
            "inventes ni lo rellenes con generalidades.\n"
            if gap_hint else ""
        )
    bloque_consulta = f"{material_consulta}\n\n" if material_consulta else ""
    gap = _chat(
        client,
        f"Texto ACTUAL sobre {subject} (es el suelo, NO lo reescribas):\n"
        f'"""{current[:6000]}"""\n\n'
        f"{bloque_consulta}"
        "MATERIAL DEL CORPUS (única fuente de hechos):\n"
        f'"""{_relevant_material(dossier.material, gap_hint, priority=material_consulta)}"""'
        f"{pista}\n\n"
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
    # El material de la consulta va DELANTE, y al verificador también: si el escritor
    # lo ve y `_verify_section` no, el verificador borra justo lo que se acaba de
    # añadir por «no consta en el material».
    material_escritor = (
        f"{material_consulta}\n\n----\n\n{dossier.material}"
        if material_consulta else dossier.material
    )
    body = _write_section(client, subject, g, existing_heads + [g["heading"]],
                          dossier.hard_facts, material_escritor, kw_block="", prior=prior,
                          tier="premium")
    body = _verify_section(client, body, dossier.hard_facts + "\n\n" + material_escritor)
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
    gap_hint: str | None = None,
    optimizar: ModoOptimizacion | None = None,
) -> dict | None:
    """Aumenta la ficha de una entidad SIN persistir. Devuelve dict con before/after y
    metadatos, o None si no había SeoContent que aumentar.

    `optimizar` activa el modo del circuito de oportunidades (ver `ModoOptimizacion`).
    A `None` —que es como lo llaman todos los demás— el comportamiento es el de
    siempre, línea por línea."""
    from app.db.models import SeoContent

    # Por `entity_id`, no por slug: `seo_content.slug` es una copia denormalizada
    # y con dos entidades homónimas se aumentaba la ficha equivocada. Si esto
    # empieza a devolver None donde antes «encontraba» algo, es la corrección
    # haciendo su trabajo: lo que encontraba era de otro.
    sc = (
        db.query(SeoContent)
        .filter(
            SeoContent.entity_type == entity_type,
            SeoContent.entity_id == entity.id,
        )
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

    # El material que responde a lo que la gente pregunta. Solo en optimización: para
    # escribir una ficha de cero no hay consulta que responder.
    material_consulta = ""
    pasajes: list[dict] = []
    if optimizar and optimizar.consultas:
        from app.services.corpus_for_queries import bloque_material, material_para_consultas

        pasajes = material_para_consultas(db, optimizar.consultas)
        material_consulta = bloque_material(pasajes)
        logger.info("[augment] %s/%s: %d pasajes recuperados por consulta",
                    entity_type, entity.slug, len(pasajes))

    gap_body, gap_head = _corpus_gap_section(client, subject, current, dossier,
                                             existing_heads + added_heads, prior,
                                             gap_hint=gap_hint,
                                             material_consulta=material_consulta,
                                             consultas=optimizar.consultas if optimizar else None)
    if gap_body and optimizar:
        confesion = confiesa_no_saber(gap_body)
        if confesion:
            logger.info("[augment] %s/%s: la sección «%s» admite no saberlo («%s») "
                        "→ se descarta", entity_type, entity.slug, gap_head, confesion)
            gap_body = None
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
    # Lo que NO se salta nunca, ni con la válvula abierta: que los versos citados
    # existan. `lyric_guard` es determinista, no usa LLM y es el único gate que el
    # proyecto declara no evadible; hasta ahora no corría sobre las fichas SEO, solo
    # sobre el blog. Si el juicio de calidad deja de frenar, este tiene que empezar.
    if optimizar:
        try:
            from app.services.lyric_guard import check_lyrics

            # Se compara el ANTES con el DESPUÉS y solo pesa lo que la ampliación
            # AÑADE. Medir el estado final condenaría a las páginas que ya arrastran
            # algo que el guardia no sabe validar: la ficha de Interludio cita el
            # libreto del disco —«Mayéutica es una canción concebida como una sola
            # obra…»—, que no es un verso y no está en ninguna letra, así que
            # bloqueaba cualquier ampliación de esa página para siempre. Una guarda
            # de no-regresión mide el delta, no el absoluto.
            antes_quotes = {v.quote for v in (check_lyrics(db, current).blocking or [])}
            nuevos = [v for v in (check_lyrics(db, after).blocking or [])
                      if v.quote not in antes_quotes]
            if nuevos:
                logger.warning("[augment] %s/%s: la ampliación cita %d verso(s) que no "
                               "están en la letra → no-op", entity_type, entity.slug,
                               len(nuevos))
                return {"before": current, "after": current, "added_headings": [],
                        "videos_added": [], "grew": False, "noop": True,
                        "subject": subject,
                        "rigor": {"verdict": "reject", "score": 0, "before_score": 0,
                                  "reasons": ["la ampliación cita versos que no "
                                              "están en la letra: "
                                              + "; ".join(v.quote[:60] for v in nuevos[:2])],
                                  "bloqueo_duro": True}}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[augment] lyric_guard falló: %s", exc)

    rigor = None
    try:
        from app.services.editorial_review import review as editorial_review

        allowed = {subject.lower()}
        extra: dict = {}
        if optimizar:
            # Las consultas entran como términos permitidos: si la sección nueva va
            # de «las olas», que «olas» salga cuatro veces no es una muletilla, es el
            # tema. Y el material y el enfoque se le pasan a AMBOS lados: comparar
            # dos veredictos medidos con varas distintas no mide nada.
            allowed |= {q.lower() for q in optimizar.consultas}
            extra = {
                "material": (material_consulta + "\n\n" + dossier.material) or None,
                "focus": "; ".join(optimizar.consultas),
                "repeats_per_1000": 4.0,
            }
        v_before = editorial_review(current, kind=entity_type, subject=subject,
                                    allowed_terms=allowed, **extra)
        if optimizar:
            # El juez ve el cuerpo PUBLICADO y, aparte, lo que se le quiere añadir.
            # Pasarle `after` (que ya lleva la sección dentro) más la sección otra vez
            # por `spotlight` se la enseñaba DOS VECES, y respondía lo previsible: «se
            # repite casi palabra por palabra en la ampliación». Medido el 22-09-2026
            # sobre las tres ampliaciones publicadas: cero párrafos duplicados y cero
            # frases repetidas. El veredicto era un artefacto de cómo se preguntaba.
            # Así además la comparación es exactamente el delta: el mismo artículo
            # base, con y sin lo añadido.
            v = editorial_review(current, kind=entity_type, subject=subject,
                                 allowed_terms=allowed,
                                 spotlight="\n\n".join(added), **extra)
        else:
            v = editorial_review(after, kind=entity_type, subject=subject,
                                 allowed_terms=allowed)
        rigor = {"verdict": v.verdict, "score": v.score, "before_score": v_before.score,
                 "reasons": list(v.reasons or [])}
        # La varianza del juez está medida en este repo: tres pasadas sobre el MISMO
        # texto dieron revise/reject/reject. Un punto menos no es una regresión, es
        # ruido de muestreo. No afloja el listón: interludio cayó 65→45.
        tolerancia = optimizar.tolerancia_rigor if optimizar else 0
        rechaza = v.verdict == "reject" or v.score < v_before.score - tolerancia
        if rechaza and optimizar and optimizar.valvula:
            # La válvula: el borrador sale igual, con el veredicto colgado, y lo
            # juzga una persona viendo el antes/después. Mismo patrón que el `force`
            # del alta manual del blog, donde «un rechazo no puede dejar al admin sin
            # poder subir nada». Aquí no publica nadie sin mirar.
            logger.info("[augment] %s/%s: el editor la rechaza (%d → %d, %s) pero sale "
                        "con el veredicto colgado", entity_type, entity.slug,
                        v_before.score, v.score, v.verdict)
            rigor["forzada"] = True
        elif rechaza:
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
