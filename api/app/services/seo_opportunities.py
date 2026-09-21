"""Circuito de aprobación SEO en dos fases (oportunidades detectadas en GSC).

El correo de los lunes llevaba meses siendo **solo un informe**: listaba URLs con
consultas en *striking distance* y terminaba pidiendo que alguien ejecutara
`gsc_optimize --apply` a mano. Nadie lo ejecutaba nunca, y el `--apply` además
hacía algo distinto de lo que el informe diagnosticaba (regeneraba el cuerpo
entero, incluso cuando lo que fallaba era el title).

Aquí vive el circuito acordado:

    detectar → [clic] aprobar → preparar borrador → [clic] aplicar

Nada se publica solo: el primer clic autoriza a PREPARAR, el segundo a PUBLICAR,
y entre medias llega un correo con el antes/después.

## Cómo se decide qué le pasa a una URL

No por posición, sino midiendo **qué cubre de verdad la página**. La heurística
por posición no se sostenía: medido el 21-09-2026 contra el contenido publicado,
los tres casos que el informe destacaba como «buena posición, pocos clics» ya
tenían el title y la description impecables —`/robe/mayeutica/interludio` abre su
description con el verso «Dejo las ventanas sin cerrar…» y aun así se lleva 0
clics de esa consulta—. Ahí no falla el contenido: falla la posición.

Por cada consulta con impresiones reales se mira dónde está respondida:

  - ni en el cuerpo               → `body`: falta contenido    (131 consultas, 3.087 imp)
  - en el cuerpo pero no en meta  → `meta`: falta promesa      (183 consultas, 4.185 imp)
  - en ambos                      → NO entra en la cola        (266 consultas, 12.176 imp)

El tercer caso es el más grande de los tres, y es justamente el que no admite
acción de contenido. Fabricarle una sería inventarse trabajo.

## Qué motor ejecuta cada acción

  - `meta` → `propose_meta`: reescribe SOLO title y description, usando el cuerpo
    ya publicado como única fuente. Guarda determinista: toda cifra y todo nombre
    propio del texto nuevo tiene que existir ya en el cuerpo, en la metadata
    anterior o en la consulta objetivo. Si aparece uno inventado, se descarta.
  - `body` → `augment_entity` con `gap_hint`: amplía sin tocar lo que ya dice
    (contrato de no-pérdida) y pasa el gate anti-paja. Si el corpus no respalda
    nada nuevo, devuelve no-op y la oportunidad muere como `noop`: es la puerta
    que impide rellenar con generalidades lo que no se puede documentar.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.services import seo_style

logger = logging.getLogger(__name__)

# Suelo de impresiones para que una consulta cuente. El del informe viejo (3) se
# queda: en un sitio de nicho lo valioso vive por debajo de 20 (medido el
# 02-08-2026: 99 páginas con 929 impresiones que nadie miraba).
MIN_QUERY_IMPRESSIONS = 3
# Suelo por OPORTUNIDAD (suma de sus consultas). Existe para que la cola quepa en
# la cabeza de una persona: una cola de cientos de filas es una cola invisible.
MIN_OPPORTUNITY_IMPRESSIONS = 25

# Las primitivas de texto y el criterio editorial viven en `seo_style`, que es la
# única fuente y no depende de nada. Se re-exportan con el nombre de aquí porque
# este módulo era su casa hasta el 22-09-2026.
_STOP = seo_style._STOP
_MODIFICADORES = seo_style._MODIFICADORES
_PREFIJO = seo_style._PREFIJO
flatten = seo_style.flatten
content_tokens = seo_style.content_tokens
_token_en = seo_style._token_en
cubre = seo_style.cubre
_tokens_permitidos = seo_style.tokens_permitidos
verify_no_invention = seo_style.verify_no_invention
spanish_case = seo_style.spanish_case


def nombre_alias_index(db) -> dict[str, str]:
    """Formas equivalentes de nombrar a cada persona del universo.

    «Robe» y «Roberto Iniesta» son la misma persona, y una ficha que dice lo
    primero responde a quien busca lo segundo. Sale de la BD —`stage_name` y
    `full_name` de cada `Person`— y no de una lista a mano, para que valga también
    para Uoho/Iñaki Antón, El Drogas/Enrique Villarreal o Milindris/Iñaki Setién.

    Devuelve {token distintivo → todas las formas}, listo para `expandir_alias`.
    """
    from app.db.models import Person

    idx: dict[str, str] = {}
    for p in db.query(Person).all():
        formas = [f for f in (p.stage_name, p.full_name) if (f or "").strip()]
        if len(formas) < 2:
            continue
        todas = " ".join(flatten(f).strip() for f in formas)
        for f in formas:
            for tok in content_tokens(f):
                # Un token que también es palabra común (o el apellido de otro)
                # metería ruido; se exigen 4 letras y unicidad por persona.
                if len(tok) >= 4:
                    idx.setdefault(tok, todas)
    return idx


def classify_queries(
    queries: list[dict], *, body_md: str | None, meta_title: str | None,
    meta_description: str | None, alias: dict[str, str] | None = None,
) -> dict[str, list[dict]]:
    """Reparte las consultas de una URL en `body`, `meta` y `covered`."""
    body = seo_style.expandir_alias(flatten(body_md), alias)
    meta = seo_style.expandir_alias(
        flatten(f"{meta_title or ''} {meta_description or ''}"), alias)
    out: dict[str, list[dict]] = {"body": [], "meta": [], "covered": []}
    for q in queries:
        if int(q.get("impressions") or 0) < MIN_QUERY_IMPRESSIONS:
            continue
        if not content_tokens(q.get("query") or ""):
            continue
        if not cubre(body, q["query"]):
            out["body"].append(q)
        elif not cubre(meta, q["query"]):
            out["meta"].append(q)
        else:
            out["covered"].append(q)
    return out


def _gap_hint(queries: list[dict]) -> str:
    """Las consultas que sostienen el hueco, en palabras, para `augment_entity`."""
    vistos: list[str] = []
    for q in sorted(queries, key=lambda x: -int(x.get("impressions") or 0)):
        texto = (q.get("query") or "").strip()
        if texto and texto not in vistos:
            vistos.append(texto)
        if len(vistos) >= 4:
            break
    return "; ".join(vistos)


# --------------------------------------------------------------------------- #
# Fase 0 — detección
# --------------------------------------------------------------------------- #
def detect(db, pages: dict, *, period: str | None = None,
           min_impressions: int = MIN_OPPORTUNITY_IMPRESSIONS) -> list:
    """Cruza el volcado de GSC con el contenido publicado y encola lo accionable.

    Idempotente: si ya hay una oportunidad VIVA para esa URL y acción, se le
    refresca la evidencia en vez de duplicarla; las ya decididas (`applied`,
    `discarded`, `noop`) no se resucitan solas.
    """
    from app.db.models import SeoContent, SeoOpportunity
    from scripts.seo.gsc_optimize import _resolve_entity

    alias = nombre_alias_index(db)
    creadas = []
    for path, queries in pages.items():
        ent = _resolve_entity(db, path)
        if not ent:
            continue
        entity_type, entity_id = ent
        sc = (
            db.query(SeoContent)
            .filter(SeoContent.entity_type == entity_type,
                    SeoContent.entity_id == entity_id)
            .first()
        )
        if not sc or not (sc.body_md or "").strip():
            continue
        reparto = classify_queries(
            queries, body_md=sc.body_md, meta_title=sc.meta_title,
            meta_description=sc.meta_description, alias=alias,
        )
        for action in ("meta", "body"):
            qs = reparto[action]
            if not qs:
                continue
            imp = sum(int(q.get("impressions") or 0) for q in qs)
            if imp < min_impressions:
                continue
            viva = (
                db.query(SeoOpportunity)
                .filter(
                    SeoOpportunity.path == path,
                    SeoOpportunity.action == action,
                    SeoOpportunity.status.in_(
                        ["detected", "approved", "drafted", "failed"]
                    ),
                )
                .first()
            )
            qs_ord = sorted(qs, key=lambda x: -int(x.get("impressions") or 0))
            if viva:
                # Se refresca la evidencia, pero NO el estado: una oportunidad ya
                # aprobada no vuelve a pedir permiso porque llegue un volcado nuevo.
                viva.queries = qs_ord
                viva.impressions = imp
                viva.period = period
                viva.gap_hint = _gap_hint(qs_ord)
                continue
            fila = SeoOpportunity(
                path=path, action=action, status="detected",
                entity_type=entity_type, entity_id=entity_id,
                seo_content_id=sc.id, queries=qs_ord, impressions=imp,
                period=period, gap_hint=_gap_hint(qs_ord),
            )
            db.add(fila)
            creadas.append(fila)
    db.commit()
    return creadas


# --------------------------------------------------------------------------- #
# Fase 1 — preparar el borrador (NO publica)
# --------------------------------------------------------------------------- #
def propose_meta(client, *, subject: str, body_md: str, meta_title: str | None,
                 meta_description: str | None, queries: list[dict],
                 entity_type: str = "", target_keyword: str | None = None,
                 reintento: bool = True) -> dict:
    """Title y description nuevos, dirigidos por las consultas que la página YA responde.

    El criterio —y las guardas que lo verifican— viven en `seo_style`. Aquí solo se
    pide, se comprueba y, si los avisos dicen que se puede hacer mejor, se pide UNA
    vez más con la pista puesta. Devuelve `{"title": …, "description": …,
    "rechazos": [...], "avisos": [...]}`; lo que no supera las guardas no viene.

    Lo que esto NO hace, a propósito: forzar el término principal. Si no cabe
    natural en un title que represente la página, se queda fuera y se anota. Es la
    regla que se saltó el borrador que abría con «Miembros y origen de Barricada»
    para una página que va del grupo.
    """
    consultas = [q.get("query", "") for q in queries[:6] if q.get("query")]
    lista = "; ".join(f"«{c}»" for c in consultas)
    permitidos = seo_style.tokens_permitidos(body_md, meta_title, meta_description,
                                             " ".join(consultas), subject)
    fuentes = f"{body_md} {subject} {meta_title or ''}"
    out: dict[str, Any] = {"rechazos": [], "avisos": []}

    def _pedir(pista: str = "") -> dict:
        prompt = (
            f"Página sobre «{subject}». Su contenido YA responde a estas búsquedas "
            f"reales de Google, pero su title y su description no las mencionan, así "
            f"que el usuario no hace clic: {lista}.\n\n"
            f"TITLE ACTUAL: {meta_title or '(vacío)'}\n"
            f"DESCRIPTION ACTUAL: {meta_description or '(vacío)'}\n\n"
            f"CONTENIDO REAL DE LA PÁGINA (única fuente de hechos):\n"
            f'"""\n{body_md[:3000]}\n"""\n\n'
            f"{seo_style.PROMPT_META_RULES}\n\n{seo_style.EJEMPLOS_ORO}\n\n"
            f"Reescríbelos para que la página prometa lo que responde, SIN cambiar de "
            f"qué va. USA SOLO lo que aparece en el contenido: no inventes datos, "
            f"fechas, cifras ni nombres.{pista}\n"
            'Devuelve JSON {"title": "...", "description": "..."}.'
        )
        from scripts.seo.generate_deep import _chat

        try:
            data = _chat(client, prompt, max_tokens=400)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[seo-opp] propose_meta falló para %s: %s", subject, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def _evaluar(data: dict) -> tuple[str | None, str | None, list[str], list[str]]:
        motivos, avisos = [], []
        t = seo_style.spanish_case((data.get("title") or "").strip().strip('"'), fuentes)
        d = re.sub(r"\s+", " ", (data.get("description") or "").strip().strip('"'))
        d = seo_style.spanish_case(d, fuentes)

        titulo_ok = None
        if t and t != (meta_title or ""):
            fuera = seo_style.verify_no_invention(t, permitidos)
            v = seo_style.title_verdict(t, body_md=body_md, subject=subject,
                                        entity_type=entity_type, anterior=meta_title,
                                        target_keyword=target_keyword)
            if fuera:
                motivos.append(f"title descartado: datos sin respaldo ({', '.join(fuera[:4])})")
            elif not v.ok:
                motivos += [f"title descartado: {m}" for m in v.motivos]
            else:
                titulo_ok = t
                avisos += v.avisos

        desc_ok = None
        if d and d != (meta_description or ""):
            v = seo_style.desc_verdict(d, title=titulo_ok or meta_title or "",
                                       body_md=body_md, entity_type=entity_type,
                                       anterior=meta_description)
            if not v.ok:
                motivos += [f"description descartada: {m}" for m in v.motivos]
            else:
                desc_ok = d
                avisos += v.avisos
        return titulo_ok, desc_ok, motivos, avisos

    titulo, desc, motivos, avisos = _evaluar(_pedir())

    # Un reintento, con lo que falló puesto delante. Potenciar es dar MÁS criterio,
    # nunca aflojar el listón: las guardas son las mismas en la segunda pasada.
    if reintento and (motivos or avisos) and not (titulo and desc and not avisos):
        pista = "\n\nEN TU PRIMER INTENTO FALLÓ ESTO, corrígelo:\n- " + "\n- ".join(
            (motivos + avisos)[:5]
        )
        t2, d2, m2, a2 = _evaluar(_pedir(pista))
        # Se queda lo mejor de las dos pasadas, no lo último.
        if t2 and (not titulo or (avisos and not a2)):
            titulo, avisos = t2, a2
        if d2 and not desc:
            desc = d2
        motivos = m2 if (t2 or d2) else motivos

    if titulo:
        out["title"] = titulo
    if desc:
        out["description"] = desc
    out["rechazos"] = motivos
    out["avisos"] = avisos

    # Si el texto nuevo sigue sin mencionar lo que se buscaba, no aporta nada.
    if "title" in out or "description" in out:
        meta_nueva = seo_style.flatten(
            f"{out.get('title', meta_title or '')} "
            f"{out.get('description', meta_description or '')}"
        )
        if not any(seo_style.cubre(meta_nueva, c) for c in consultas):
            out["rechazos"].append("propuesta descartada: sigue sin cubrir ninguna consulta")
            out.pop("title", None)
            out.pop("description", None)
    return out


_MODELOS = {
    "artist": "Artist", "album": "Album", "song": "Song", "person": "Person",
    "band": "Band", "theme": "Theme", "place": "Place", "concept": "Concept",
}


def _entidad(db, entity_type: str, entity_id: int):
    from app.db import models

    modelo = getattr(models, _MODELOS.get(entity_type, ""), None)
    return db.get(modelo, entity_id) if modelo else None


def prepare_draft(db, opp) -> str:
    """Prepara el borrador de una oportunidad aprobada. NO publica nada.

    Devuelve el estado nuevo: `drafted`, `noop` (no había material) o `failed`.
    """
    from openai import OpenAI

    from app.config import get_settings
    from app.db.models import SeoContent

    opp.attempts = (opp.attempts or 0) + 1
    sc = db.query(SeoContent).filter(SeoContent.id == opp.seo_content_id).first()
    if not sc:
        sc = (
            db.query(SeoContent)
            .filter(SeoContent.entity_type == opp.entity_type,
                    SeoContent.entity_id == opp.entity_id)
            .first()
        )
    if not sc or not (sc.body_md or "").strip():
        opp.status = "failed"
        opp.error = "la página ya no tiene ficha SEO con cuerpo"
        db.commit()
        return "failed"

    # El antes se sella AHORA, no al detectar: entre una cosa y otra pueden haber
    # pasado días y el correo tiene que enseñar lo que hay, no lo que hubo.
    opp.seo_content_id = sc.id
    opp.before_title = sc.meta_title
    opp.before_description = sc.meta_description
    opp.before_body = sc.body_md
    ahora = datetime.now(UTC)
    client = OpenAI(api_key=get_settings().openai_api_key)

    try:
        if opp.action == "meta":
            entidad = _entidad(db, opp.entity_type, opp.entity_id)
            subject = (
                getattr(entidad, "stage_name", None) or getattr(entidad, "name", None)
                or getattr(entidad, "full_name", None) or getattr(entidad, "title", None)
                or (sc.h1 or sc.meta_title or sc.slug)
            )
            prop = propose_meta(
                client, subject=subject, body_md=sc.body_md,
                meta_title=sc.meta_title, meta_description=sc.meta_description,
                queries=opp.queries or [], entity_type=opp.entity_type,
                target_keyword=sc.target_keyword,
            )
            opp.draft_title = prop.get("title")
            opp.draft_description = prop.get("description")
            # Los avisos viajan al correo y al panel: no bloquean, pero son
            # exactamente lo que una persona querría mirar antes de publicar.
            opp.draft_notes = {"rechazos": prop.get("rechazos") or [],
                               "avisos": prop.get("avisos") or []}
            if not opp.draft_title and not opp.draft_description:
                opp.status = "noop"
                opp.error = "; ".join(prop.get("rechazos") or []) or "sin propuesta válida"
                db.commit()
                return "noop"
        else:
            from scripts.seo.augment_deep import augment_entity

            entidad = _entidad(db, opp.entity_type, opp.entity_id)
            if entidad is None:
                opp.status = "failed"
                opp.error = f"entidad {opp.entity_type}#{opp.entity_id} no encontrada"
                db.commit()
                return "failed"
            from scripts.seo.augment_deep import ModoOptimizacion

            # Optimizar no es escribir de cero: se busca material por la CONSULTA, no
            # se penaliza crecer, y si el editor jefe aun así la rechaza, el borrador
            # sale con el veredicto colgado para que lo juzgue una persona. Nada de
            # esto llega a la generación de fichas nuevas.
            consultas = [q.get("query", "") for q in (opp.queries or []) if q.get("query")]
            res = augment_entity(db, client, opp.entity_type, entidad,
                                 gap_hint=opp.gap_hint,
                                 optimizar=ModoOptimizacion(consultas=consultas[:6]))
            if not res or res.get("noop"):
                rigor = (res or {}).get("rigor") or {}
                opp.status = "noop"
                opp.draft_notes = {"rigor": rigor}
                opp.error = (
                    "hay versos citados que no están en la letra"
                    if rigor.get("bloqueo_duro")
                    else "el corpus no respalda nada nuevo sobre eso "
                         "(no se rellena con generalidades)"
                )
                db.commit()
                return "noop"
            rigor = res.get("rigor") or {}
            opp.draft_body = res["after"]
            opp.draft_notes = {
                "added_headings": res.get("added_headings") or [],
                "videos_added": res.get("videos_added") or [],
                "rigor": rigor,
                "before_len": res.get("before_len"),
                "after_len": res.get("after_len"),
                # El veredicto en contra va donde ya se pinta: el correo y el panel
                # leen `avisos` desde el 22-09, así que aparece en los dos sitios sin
                # tocar una línea más.
                "avisos": (
                    [f"el editor jefe la RECHAZA (rigor {rigor.get('before_score')} → "
                     f"{rigor.get('score')}) y se te enseña igual para que decidas tú: "
                     + "; ".join((rigor.get("reasons") or [])[:2])]
                    if rigor.get("forzada") else []
                ),
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[seo-opp] fallo preparando %s (%s)", opp.path, opp.action)
        opp.status = "failed"
        opp.error = f"{type(exc).__name__}: {exc}"[:500]
        db.commit()
        return "failed"

    opp.status = "drafted"
    opp.drafted_at = ahora
    opp.error = None
    db.commit()
    return "drafted"


# --------------------------------------------------------------------------- #
# Fase 2 — aplicar (esto sí publica)
# --------------------------------------------------------------------------- #
def apply_draft(db, opp) -> bool:
    """Vuelca el borrador sobre la ficha publicada y revalida la caché de Next."""
    from app.db.models import SeoContent

    if opp.status != "drafted":
        return False
    sc = db.query(SeoContent).filter(SeoContent.id == opp.seo_content_id).first()
    if not sc:
        opp.status = "failed"
        opp.error = "la ficha SEO ya no existe"
        db.commit()
        return False

    # El cuerpo de la ficha pudo cambiar entre el borrador y el clic (otro cron,
    # una edición a mano). Aplicar a ciegas se cargaría ese trabajo, así que se
    # comprueba que el suelo sigue siendo el mismo.
    if opp.action == "body" and (sc.body_md or "") != (opp.before_body or ""):
        opp.status = "failed"
        opp.error = ("el contenido cambió después de preparar el borrador; "
                     "hay que volver a prepararlo para no pisar lo nuevo")
        db.commit()
        return False

    if opp.action == "meta":
        if opp.draft_title:
            sc.meta_title = opp.draft_title
        if opp.draft_description:
            sc.meta_description = opp.draft_description
    else:
        sc.body_md = opp.draft_body
    sc.reviewed_at = datetime.now(UTC)
    opp.status = "applied"
    opp.applied_at = datetime.now(UTC)
    db.commit()

    from app.services.publishing import revalidate_paths

    revalidate_paths([opp.path])
    logger.info("[seo-opp] aplicada %s (%s)", opp.path, opp.action)
    return True


# --------------------------------------------------------------------------- #
# Runner — el trabajo que dispara el primer clic
# --------------------------------------------------------------------------- #
# Un borrador de cuerpo tarda minutos (investiga, escribe, verifica y pasa el gate),
# así que esto NO cabe en la petición HTTP: Cloudflare corta a los 100 s. El clic
# solo marca `approved` y deja esto corriendo en segundo plano, con su propia
# sesión de BD, igual que el alta manual de noticias.
MAX_PREPARE_ATTEMPTS = 3


def run_prepare(ids: list[int] | None = None, *, limit: int = 10,
                notify: bool = True) -> dict:
    """Prepara los borradores de las oportunidades aprobadas y avisa por correo.

    Sin `ids` recoge todo lo aprobado que quede pendiente: es la red de seguridad
    del cron para lo que se quedó a medias si el servidor se reinició entre el
    clic y el borrador (un deploy basta).
    """
    from app.db.models import SeoOpportunity
    from app.db.session import SessionLocal
    from app.services.seo_opportunity_mail import send_drafted

    resumen = {"drafted": 0, "noop": 0, "failed": 0}
    preparadas, sin_material = [], []
    with SessionLocal() as db:
        q = db.query(SeoOpportunity).filter(
            SeoOpportunity.status.in_(["approved", "failed"]),
            SeoOpportunity.attempts < MAX_PREPARE_ATTEMPTS,
        )
        if ids:
            q = q.filter(SeoOpportunity.id.in_(ids))
        # Primero lo que más impresiones se juega.
        filas = q.order_by(SeoOpportunity.impressions.desc()).limit(limit).all()
        for opp in filas:
            estado = prepare_draft(db, opp)
            resumen[estado if estado in resumen else "failed"] += 1
            if estado == "drafted":
                preparadas.append(opp)
            elif estado in ("noop", "failed"):
                sin_material.append(opp)
        if (preparadas or sin_material) and notify and send_drafted(
            preparadas, sin_material=sin_material
        ):
            ahora = datetime.now(UTC)
            for opp in preparadas:
                opp.notified_drafted_at = ahora
            db.commit()
    logger.info("[seo-opp] borradores preparados: %s", resumen)
    return resumen
