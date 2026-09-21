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
import unicodedata
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Suelo de impresiones para que una consulta cuente. El del informe viejo (3) se
# queda: en un sitio de nicho lo valioso vive por debajo de 20 (medido el
# 02-08-2026: 99 páginas con 929 impresiones que nadie miraba).
MIN_QUERY_IMPRESSIONS = 3
# Suelo por OPORTUNIDAD (suma de sus consultas). Existe para que la cola quepa en
# la cabeza de una persona: una cola de cientos de filas es una cola invisible.
MIN_OPPORTUNITY_IMPRESSIONS = 25

_STOP = {
    "de", "la", "el", "los", "las", "y", "en", "del", "que", "a", "un", "una",
    "por", "con", "para", "su", "sus", "es", "al", "lo", "se", "como", "o",
}

# Palabras con las que se BUSCA, no cosas que una página pueda cubrir. Sin esta
# lista, «letras de extremoduro desarraigo» salía como hueco de contenido en una
# página que tiene la letra entera: el cuerpo dice «letra», en singular, y el
# cotejo por tokens no la encontraba. Lo mismo con quien remata la consulta con
# «wikipedia» o «youtube»: eso no es un ángulo que escribir.
_MODIFICADORES = {
    "letra", "letras", "lyrics", "wikipedia", "wiki", "youtube", "video",
    "videos", "cancion", "canciones", "tema", "temas", "musica", "grupo",
    "banda", "descargar", "escuchar", "completa", "completo", "online",
}

# Prefijo con el que se compara un token contra el texto. En español la flexión
# vive al final («miembro»/«miembros», «canta»/«cantaba»), así que comparar por
# los primeros caracteres evita falsos huecos sin abrir la mano de más.
_PREFIJO = 5


def flatten(texto: str | None) -> str:
    """Texto sin acentos, sin markdown y con un solo espacio: el terreno de cotejo."""
    s = unicodedata.normalize("NFD", (texto or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip() + " "


def content_tokens(query: str) -> list[str]:
    """Tokens de la consulta que representan CONTENIDO (fuera stopwords y modificadores)."""
    return [
        t
        for t in re.findall(r"[a-z0-9]+", flatten(query))
        if t not in _STOP and t not in _MODIFICADORES and len(t) > 1
    ]


def _token_en(texto_plano: str, token: str) -> bool:
    if f" {token} " in texto_plano or f" {token}" in texto_plano:
        return True
    if len(token) > _PREFIJO:
        return bool(re.search(r" " + re.escape(token[:_PREFIJO]) + r"[a-z0-9]*", texto_plano))
    return False


def cubre(texto_plano: str, query: str) -> bool:
    """¿Este texto responde a la consulta? Todos sus tokens de contenido presentes."""
    toks = content_tokens(query)
    return bool(toks) and all(_token_en(texto_plano, t) for t in toks)


def classify_queries(
    queries: list[dict], *, body_md: str | None, meta_title: str | None,
    meta_description: str | None,
) -> dict[str, list[dict]]:
    """Reparte las consultas de una URL en `body`, `meta` y `covered`."""
    body = flatten(body_md)
    meta = flatten(f"{meta_title or ''} {meta_description or ''}")
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
            meta_description=sc.meta_description,
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
def _tokens_permitidos(*textos: str | None) -> set[str]:
    permitidos: set[str] = set()
    for t in textos:
        for tok in re.findall(r"[a-z0-9]+", flatten(t)):
            permitidos.add(tok[:_PREFIJO] if len(tok) > _PREFIJO else tok)
    return permitidos


def verify_no_invention(propuesta: str, permitidos: set[str]) -> list[str]:
    """Datos de la propuesta que no salen de ninguna fuente autorizada.

    Guarda determinista, porque a un LLM al que se le pide «no inventes» le sale
    bien casi siempre, y ese «casi», en una web pública, es un dato falso
    publicado (la bio de Uoho recortada a mitad de frase lo fue).

    Vigila lo que de verdad se ha inventado alguna vez aquí: **cifras** (el año
    falso de Rock Transgresivo estuvo en 24 fichas) y **nombres propios** (Fito
    Páez por Fito Cabrales, un homónimo mexicano). El vocabulario común no, y eso
    no es dejadez: la primera versión de esta guarda tumbó una description
    correcta por la palabra «cuenta», y una guarda que rechaza lo bueno acaba
    apagada. Comparar por mayúsculas exige el texto SIN normalizar, así que se
    recorre la propuesta tal cual llega.
    """
    fuera = []
    frases = re.split(r"(?<=[.!?:;])\s+|\n", propuesta)
    for frase in frases:
        palabras = re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ'’-]+", frase)
        for i, palabra in enumerate(palabras):
            limpia = palabra.strip("'’-")
            if not limpia:
                continue
            es_cifra = any(c.isdigit() for c in limpia)
            # La primera palabra de la frase va en mayúscula por ortografía, no por
            # ser un nombre propio: mirarla daría un falso positivo en cada frase.
            es_propio = i > 0 and limpia[:1].isupper() and not limpia.isupper()
            if not (es_cifra or es_propio):
                continue
            tok = re.sub(r"[^a-z0-9]", "", flatten(limpia))
            if not tok:
                continue
            clave = tok[:_PREFIJO] if len(tok) > _PREFIJO else tok
            if clave not in permitidos:
                fuera.append(limpia)
    return fuera


def spanish_case(texto: str, fuentes: str) -> str:
    """Devuelve el texto con capitalización española.

    GPT escribe los títulos en Title Case inglés («Significado y Canciones
    Clave»), que en español chirría y delata la máquina. Se baja a minúscula toda
    palabra capitalizada que no abra frase, no vaya tras dos puntos y no aparezca
    también capitalizada en el contenido real: así los nombres propios («Agila»,
    «So Payaso», «Extremoduro») se quedan como están, porque de ahí salieron.
    """
    palabras = texto.split(" ")
    salida = []
    abre_frase = True
    for w in palabras:
        nucleo = w.strip(".,;:!?«»\"'()")
        if (not abre_frase and nucleo and nucleo[:1].isupper() and not nucleo.isupper()
                and nucleo not in fuentes):
            w = w.replace(nucleo, nucleo[0].lower() + nucleo[1:], 1)
        abre_frase = w.endswith((":", ".", "!", "?"))
        salida.append(w)
    return " ".join(salida)


def propose_meta(client, *, subject: str, body_md: str, meta_title: str | None,
                 meta_description: str | None, queries: list[dict]) -> dict:
    """Title y description nuevos, dirigidos por las consultas que la página YA responde.

    Devuelve `{"title": …, "description": …, "rechazos": [...]}`; las claves que no
    superen las guardas simplemente no vienen.
    """
    from scripts.seo.optimize_meta import DESC_MAX, DESC_MIN, TITLE_MAX, _clean_to_len

    consultas = [q.get("query", "") for q in queries[:6] if q.get("query")]
    lista = "; ".join(f"«{c}»" for c in consultas)
    permitidos = _tokens_permitidos(body_md, meta_title, meta_description,
                                    " ".join(consultas), subject)
    out: dict[str, Any] = {"rechazos": []}

    prompt = (
        f"Página sobre «{subject}». Su contenido YA responde a estas búsquedas reales "
        f"de Google, pero su title y su description no las mencionan, así que el "
        f"usuario no hace clic: {lista}.\n\n"
        f"TITLE ACTUAL: {meta_title or '(vacío)'}\n"
        f"DESCRIPTION ACTUAL: {meta_description or '(vacío)'}\n\n"
        f"CONTENIDO REAL DE LA PÁGINA (única fuente de hechos):\n\"\"\"\n{body_md[:3000]}\n\"\"\"\n\n"
        f"Reescribe los dos para que prometan lo que la página responde:\n"
        f"- title: máximo {TITLE_MAX} caracteres, en español, sin cortar palabras y con "
        f"capitalización española (solo mayúscula inicial y en nombres propios).\n"
        f"- description: entre {DESC_MIN} y {DESC_MAX} caracteres.\n"
        "Incorpora de forma natural los términos de esas búsquedas. USA SOLO lo que "
        "aparece en el contenido: no inventes datos, fechas, cifras ni nombres. "
        'Devuelve JSON {"title": "...", "description": "..."}.'
    )
    from scripts.seo.generate_deep import _chat

    try:
        data = _chat(client, prompt, max_tokens=300)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[seo-opp] propose_meta falló para %s: %s", subject, exc)
        return out
    if not isinstance(data, dict):
        return out

    fuentes_literales = f"{body_md} {meta_title or ''} {meta_description or ''}"
    nuevo_title = _clean_to_len((data.get("title") or "").strip().strip('"'), TITLE_MAX)
    nuevo_title = spanish_case(nuevo_title, fuentes_literales)
    nueva_desc = re.sub(r"\s+", " ", (data.get("description") or "").strip().strip('"'))
    nueva_desc = spanish_case(_clean_to_len(nueva_desc, DESC_MAX), fuentes_literales)

    if nuevo_title and nuevo_title != (meta_title or ""):
        fuera = verify_no_invention(nuevo_title, permitidos)
        if fuera:
            out["rechazos"].append(f"title descartado: datos sin respaldo en la página ({', '.join(fuera[:5])})")
        elif len(nuevo_title) < 20:
            out["rechazos"].append("title descartado: demasiado corto")
        else:
            out["title"] = nuevo_title
    if nueva_desc and nueva_desc != (meta_description or ""):
        fuera = verify_no_invention(nueva_desc, permitidos)
        if fuera:
            out["rechazos"].append(f"description descartada: datos sin respaldo en la página ({', '.join(fuera[:5])})")
        elif not (DESC_MIN - 10 <= len(nueva_desc) <= DESC_MAX):
            out["rechazos"].append(f"description descartada: {len(nueva_desc)} caracteres")
        else:
            out["description"] = nueva_desc

    # Si el texto nuevo sigue sin mencionar lo que se buscaba, no aporta nada.
    if "title" in out or "description" in out:
        meta_nueva = flatten(f"{out.get('title', meta_title or '')} "
                             f"{out.get('description', meta_description or '')}")
        if not any(cubre(meta_nueva, c) for c in consultas):
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
                queries=opp.queries or [],
            )
            opp.draft_title = prop.get("title")
            opp.draft_description = prop.get("description")
            opp.draft_notes = {"rechazos": prop.get("rechazos") or []}
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
            res = augment_entity(db, client, opp.entity_type, entidad,
                                 gap_hint=opp.gap_hint)
            if not res or res.get("noop"):
                opp.status = "noop"
                opp.draft_notes = {"rigor": (res or {}).get("rigor")}
                opp.error = ("el corpus no respalda nada nuevo sobre eso "
                             "(no se rellena con generalidades)")
                db.commit()
                return "noop"
            opp.draft_body = res["after"]
            opp.draft_notes = {
                "added_headings": res.get("added_headings") or [],
                "videos_added": res.get("videos_added") or [],
                "rigor": res.get("rigor"),
                "before_len": res.get("before_len"),
                "after_len": res.get("after_len"),
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
