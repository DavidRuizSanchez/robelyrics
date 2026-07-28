"""Investigación ADAPTATIVA para posts de noticia.

El protagonista de una noticia puede ser una persona, una banda, un disco, un
evento/concierto, un lugar, un premio... Este módulo:
  1. Clasifica el TEMA principal y su tipo.
  2. Reúne información REAL ajustada a ese tipo: web (Google vía DataForSEO),
     nuestro corpus, vídeo relevante (YouTube) y foto del protagonista.
  3. Devuelve todo para que el generador escriba el post con el MÁXIMO de
     información relevante, SIN acreditar al medio fuente y SIN inventar.

Degradación elegante: cualquier paso que falle devuelve vacío/None; el post se
genera igual con lo que haya.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from sqlalchemy import select

from app.services.content_generator import _call
from app.services.instagram import web_image

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"
_SERP = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
_LOCATION_ES = 2724
_LANG_ES = "es"


def _json(
    system: str, user: str, max_tokens: int = 700, *, temperature: float = 0.3
) -> dict[str, Any]:
    """Llamada JSON ligera (clasificación/selección), sin los campos que exige
    el generador de posts. `temperature` por defecto baja (0.3) para tareas
    deterministas; súbela para tareas creativas (p.ej. titulares variados)."""
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {}
    try:
        resp = OpenAI(api_key=key).chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[news_research] _json falló: %s", exc)
        return {}


# --------------------------------------------------------------------------- #
# 1. Clasificación del tema + plan de investigación (ADAPTATIVO)
# --------------------------------------------------------------------------- #
_PLAN_SYS = (
    "Eres un documentalista de un medio sobre Robe y Extremoduro. "
    "Identificas el TEMA PRINCIPAL de una noticia y planificas cómo investigarlo "
    "para dar el máximo de información relevante. Respondes solo JSON."
)


def plan_research(
    headline: str, excerpt: str, matched_term: str, *, today: str | None = None
) -> dict[str, Any]:
    today_line = f"Fecha de hoy: {today}\n" if today else ""
    user = f"""\
{today_line}Noticia:
Titular: {headline}
Extracto: {excerpt[:1500]}
Término que la enganchó: {matched_term}

Devuelve SOLO un JSON con:
  "is_relevant": true si la noticia trata DE VERDAD del universo Robe/Extremoduro
    (su gente, versiones, homenajes, discos, conciertos, lugares...); false si es
    un falso positivo del rastreador.
  "topic_type": el tipo del PROTAGONISTA principal del post, uno de:
    "persona", "banda", "disco", "cancion", "evento", "lugar", "premio",
    "efemeride", "otro".
  "subject": el nombre propio del protagonista (la banda/persona/disco/evento del
    que VA la noticia; si es un homenaje/versión, QUIEN lo hace, no Robe).
  "is_event": true si la noticia trata de un EVENTO con fecha concreta (concierto,
    festival, homenaje, gala, presentación, firma de discos...); false si es
    atemporal (biografía, análisis, efeméride recurrente, opinión).
  "event_date": la fecha del evento en formato ISO "YYYY-MM-DD", SOLO si aparece
    EXPLÍCITA y completa en el titular o el extracto (o es deducible sin ambigüedad
    con la fecha de hoy). REGLA DURA: si no hay una fecha exacta y verificable en el
    texto, devuelve null. NUNCA inventes ni estimes una fecha. Si el evento dura
    varios días, usa el PRIMER día.
  "web_query": una consulta de Google para investigar ese protagonista, ADAPTADA
    al tipo (p.ej. banda -> "X grupo trayectoria"; disco -> "X disco año sello";
    evento -> "X fecha lugar"; persona -> "X músico biografía"). Con contexto
    suficiente para no traer homónimos.
  "image_query": consulta para una FOTO del protagonista (banda/persona/disco/
    lugar), con contexto. Vacío si no hay nada fotografiable claro.
  "video_query": consulta de YouTube del vídeo MÁS relevante del tema (la versión,
    la actuación, la entrevista, el videoclip...). Vacío si no aplica un vídeo.
  "focus": en una frase, QUÉ información es la más relevante a destacar según el
    tipo (de un disco: fecha, sello, tracklist, contexto; de un evento: fecha,
    lugar, QUIÉN actúa/asiste y los GUIÑOS a Robe/Extremoduro; de una persona/banda:
    quiénes son, trayectoria, relación con Robe; etc.).
"""
    plan = _json(_PLAN_SYS, user)
    plan.setdefault("is_relevant", True)
    plan.setdefault("topic_type", "otro")
    plan.setdefault("is_event", False)
    plan.setdefault("event_date", None)
    return plan


# --------------------------------------------------------------------------- #
# 2. Investigación: web (snippets de Google) + corpus propio
# --------------------------------------------------------------------------- #
def web_research(query: str, n: int = 6) -> list[dict]:
    """Títulos + snippets de Google (no scrapea páginas): material factual para
    el LLM, no copia. Vía DataForSEO."""
    login = os.environ.get("DATAFORSEO_LOGIN")
    pwd = os.environ.get("DATAFORSEO_PASSWORD")
    if not query or not login or not pwd:
        return []
    try:
        payload = [{
            "keyword": query, "location_code": _LOCATION_ES,
            "language_code": _LANG_ES, "depth": n,
        }]
        with httpx.Client(timeout=30.0) as c:
            r = c.post(_SERP, auth=(login, pwd), json=payload)
            r.raise_for_status()
            items = r.json()["tasks"][0]["result"][0]["items"] or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[news_research] SERP falló '%s': %s", query, exc)
        return []
    out = []
    for it in items:
        if it.get("type") == "organic" and (it.get("title") or it.get("description")):
            out.append({
                "title": it.get("title") or "",
                "snippet": it.get("description") or "",
                "url": it.get("url") or "",
            })
        if len(out) >= n:
            break
    logger.info("[news_research] web '%s' -> %d resultados", query, len(out))
    return out


def corpus_research(db, query: str, n: int = 4) -> list[dict]:
    """Extractos de NUESTRO corpus (interpretation_sources) que mencionen el
    tema. Conocimiento propio para enriquecer y cruzar."""
    if db is None or not query:
        return []
    try:
        from app.db.models import InterpretationSource
        rows = db.execute(
            select(InterpretationSource.title, InterpretationSource.content_clean)
            .where(InterpretationSource.content_clean.ilike(f"%{query}%"))
            .limit(n)
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[news_research] corpus falló: %s", exc)
        return []
    return [{"title": t or "", "excerpt": (c or "")[:600]} for t, c in rows]


def entity_dossiers(db, blob: str, *, max_songs: int = 2) -> str:
    """Dossier de las ENTIDADES del catálogo que menciona la noticia.

    `corpus_research` busca por el sujeto tal cual lo nombra el titular, y eso deja
    fuera lo mejor que tenemos: una noticia sobre el bar Umore Ona daba 0 resultados,
    cuando va de «Calle Esperanza S/N» —canción nuestra, con letra, créditos y
    fuentes—. Aquí se detecta de qué canciones del catálogo habla el texto y se trae
    su dossier completo (el mismo que alimenta las páginas SEO profundas), más el de
    su disco. SUMA a `corpus_research`, no lo sustituye.

    Devuelve "" si no reconoce ninguna entidad: entonces no hay nada que añadir."""
    if db is None or not blob:
        return ""
    try:
        from app.db.models import Album, Song
        from app.services.deep_research import gather_entity_dossier
        from scripts.research.common import find_referenced_titles, get_all_song_titles

        song_ids = find_referenced_titles(blob, get_all_song_titles(db))
        if not song_ids:
            return ""
        songs = db.query(Song).filter(Song.id.in_(song_ids[:max_songs])).all()
        if not songs:
            return ""

        def _fmt(kind: str, title: str, dossier, cap: int) -> str:
            """Datos duros + corpus del dossier, capados. `hard_facts` es lo canónico
            (año, disco, créditos): va primero para que sobreviva al recorte."""
            hard = (dossier.hard_facts or "").strip()
            mat = (dossier.material or "").strip()
            body = "\n\n".join(p for p in (hard, mat[: max(cap - len(hard), 0)]) if p)
            return f"### {kind} «{title}»\n{body}" if body else ""

        blocks: list[str] = []
        for s in songs:
            blk = _fmt("Canción", s.title, gather_entity_dossier(db, "song", s), 6000)
            if blk:
                blocks.append(blk)

        # El disco de la primera canción reconocida: contexto del álbum (año, sello,
        # tracklist, recepción) sin repetir dossieres por cada corte del mismo disco.
        album_ids = [s.album_id for s in songs if s.album_id]
        if album_ids:
            album = db.query(Album).filter(Album.id == album_ids[0]).first()
            if album is not None:
                blk = _fmt("Disco", album.title,
                           gather_entity_dossier(db, "album", album), 4000)
                if blk:
                    blocks.append(blk)

        if not blocks:
            return ""
        return (
            "DOSSIER DE NUESTRO CATÁLOGO (entidades reconocidas en la noticia; es "
            "material PROPIO y verificado: úsalo para aportar lo que ningún medio "
            "tiene, sin inventar nada que no esté aquí)\n\n" + "\n\n".join(blocks)
        )
    except Exception as exc:  # noqa: BLE001 — el dossier es un extra, nunca un bloqueo
        logger.warning("[news_research] dossier de entidades falló: %s", exc)
        return ""


# --------------------------------------------------------------------------- #
# 3. Vídeo relevante (YouTube) — con selección por el LLM para no embeber uno
#    equivocado (homónimo / canal ajeno).
# --------------------------------------------------------------------------- #
def find_video(query: str, subject: str) -> dict | None:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not query or not key:
        return None
    try:
        with httpx.Client(timeout=20.0) as c:
            s = c.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"part": "snippet", "q": query, "type": "video",
                        "maxResults": 5, "key": key},
            ).json()
            cands = [
                {"id": it["id"]["videoId"],
                 "title": it["snippet"]["title"],
                 "channel": it["snippet"]["channelTitle"]}
                for it in s.get("items", [])
            ]
            if not cands:
                return None
            # El LLM elige el vídeo correcto del sujeto, o ninguno.
            sel = _json(
                "Eliges el vídeo de YouTube correcto para un tema, o ninguno. JSON.",
                f"Tema/protagonista: {subject}\nCandidatos:\n"
                + "\n".join(f"{i}. [{v['channel']}] {v['title']}"
                            for i, v in enumerate(cands))
                + "\n\nDevuelve {\"index\": N} con el candidato que sea CLARAMENTE "
                  "del protagonista (su canal oficial o título inequívoco), o "
                  "{\"index\": -1} si ninguno encaja con seguridad. Ante la duda, -1.",
                max_tokens=50,
            )
            idx = sel.get("index", -1)
            if not isinstance(idx, int) or idx < 0 or idx >= len(cands):
                return None
            vid = cands[idx]["id"]
            v = c.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "snippet", "id": vid, "key": key},
            ).json()
            sn = v["items"][0]["snippet"]
            return {"youtube_id": vid, "title": sn["title"],
                    "upload_date": sn["publishedAt"][:10],
                    "channel": sn["channelTitle"]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[news_research] vídeo falló '%s': %s", query, exc)
        return None


def find_image(query: str) -> dict | None:
    """Foto web del sujeto de la noticia como PAQUETE hero coherente, o None.

    Para noticias el usuario autoriza foto web sin crédito CC (la investigación es
    nuestra): `attribution`/`license` van a None de forma coherente, `source`
    conserva la URL original (procedencia). El paquete tiene la forma canónica de
    `hero_io` para aplicarse con `apply_hero` sin desincronizar campos.
    """
    if not query:
        return None
    cands = web_image.search(query)
    if not cands:
        return None
    top = cands[0]
    url = top.get("url")
    if not url:
        return None
    return {
        "url": url,
        "alt": (top.get("title") or "").strip() or None,
        "attribution": None,
        "license": None,
        "source": url,
    }


# --------------------------------------------------------------------------- #
# 4. Orquestador: investiga + escribe el post (sin acreditar al medio)
# --------------------------------------------------------------------------- #
_WRITE_SYS = (
    "Eres el redactor de Entre Interiores, un sitio sobre Robe y "
    "Extremoduro. Escribes en español de España, cercano y con criterio, en "
    "tercera persona cálida (sin 'yo' vivencial). Refiérete a él como 'Robe' o "
    "'Roberto Iniesta', NUNCA 'Robe Iniesta' (no le gustaba). NUNCA mencionas ni acreditas "
    "al medio del que sale la noticia (ni 'según', ni 'vía', ni el nombre del "
    "medio): la investigación es nuestra. ROBE FALLECIÓ: enmárcalo en pasado. "
    "REGLA CRÍTICA: no inventes datos; usa solo lo que aparezca en el material. "
    "FECHAS Y NÚMEROS: no afirmes fechas, años ni números de edición ('3ª "
    "edición', 'Premios 2023') que NO aparezcan explícitamente en el material; "
    "si no constan, no los pongas (mejor omitir el año que inventarlo). No "
    "mezcles eventos distintos en uno: céntrate en el hecho de la noticia. "
    "FOCO (IMPRESCINDIBLE): el post va del HECHO de la noticia y de sus "
    "PROTAGONISTAS (quién participa/actúa/asiste, qué hace, cuándo, y la relación "
    "o los guiños a Robe/Extremoduro). NO dediques secciones ni párrafos al "
    "LUGAR/RECINTO/SEDE ni a su historia, arquitectura o contexto general (p.ej. "
    "el museo donde se celebra): como mucho, una mención de pasada. Nada de "
    "relleno enciclopédico ajeno al protagonista. No uses la raya larga."
)


_VERIFY_SYS = (
    "Eres un verificador de hechos ESTRICTO de Entre Interiores. Te doy un "
    "ARTÍCULO y el MATERIAL en el que debe basarse. Tu trabajo: devolver el "
    "artículo corregido eliminando o suavizando TODA afirmación concreta "
    "—fechas, años, números de edición ('3ª edición', '2023'), cifras de "
    "asistentes/premios, nombres propios, lugares y eventos— que NO aparezca o "
    "no se deduzca CLARAMENTE del material. Reglas: (1) si un dato no está en el "
    "material, quítalo o reescribe la frase sin él (mejor sin el dato que con "
    "uno inventado); (2) NO añadas información nueva; (3) no mezcles eventos "
    "distintos: si el artículo cuela un evento que no está en el material, "
    "elimínalo; (4) conserva el estilo, los encabezados y los enlaces markdown "
    "tal cual. Devuelve SOLO JSON: {\"body_md\": \"<artículo corregido>\"}."
)


def verify_facts(body_md: str, material: str) -> str:
    """Pasada de verificación factual contra el material. Quita lo no respaldado
    (anti-alucinación). Si falla, devuelve el cuerpo original."""
    if not body_md.strip():
        return body_md
    out = _json(
        _VERIFY_SYS,
        f"MATERIAL (única fuente de verdad):\n\"\"\"{material[:7000]}\"\"\"\n\n"
        f"ARTÍCULO A VERIFICAR:\n\"\"\"{body_md}\"\"\"",
        max_tokens=2600,
    )
    verified = (out.get("body_md") or "").strip()
    return verified if len(verified) > 200 else body_md


def _parse_event_date(value: Any):
    """Convierte un ISO 'YYYY-MM-DD' del LLM en date, o None. Conservador: solo
    acepta fechas completas y plausibles (no inventa nada)."""
    from datetime import date as _date

    if not value or not isinstance(value, str):
        return None
    try:
        d = _date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
    # Descarta fechas absurdas (fuera de un rango razonable del proyecto).
    if d.year < 1980 or d.year > 2100:
        return None
    return d


_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _date_mentioned(d, text: str) -> bool:
    """True si la fecha `d` aparece LITERALMENTE en `text` (en alguna de las
    formas habituales en español). Guardia anti-invención: el LLM a veces
    devuelve una fecha (p.ej. la de hoy) que NO está en la fuente; solo la
    aceptamos si el texto la respalda de verdad."""
    if not d or not text:
        return False
    t = text.lower()
    month = _MONTHS_ES[d.month - 1]
    forms = [
        f"{d.day} de {month}",                       # 11 de junio
        f"{d.isoformat()}",                          # 2026-06-11
        f"{d.day:02d}/{d.month:02d}/{d.year}",       # 11/06/2026
        f"{d.day}/{d.month}/{d.year}",               # 11/6/2026
        f"{d.day:02d}/{d.month:02d}",                # 11/06
        f"{d.day}/{d.month}",                        # 11/6
        f"{d.day:02d}-{d.month:02d}-{d.year}",       # 11-06-2026
    ]
    return any(f in t for f in forms)


def validated_event_date(value: Any, text: str):
    """`event_date` validada: la parsea y SOLO la devuelve si aparece literal en
    `text` (la fuente). Si el LLM la inventó (no está en el texto), devuelve None.
    Cumple la regla dura: nunca una fecha que no esté en el material."""
    d = _parse_event_date(value)
    if d is None:
        return None
    return d if _date_mentioned(d, text) else None


def _slugify(s: str) -> str:
    """Slug kebab-case determinista (sin acentos, máx 6 palabras). Más fiable
    que pedírselo al LLM (que a veces alucina el slug)."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    parts = [p for p in re.sub(r"[^a-zA-Z0-9]+", "-", s).lower().split("-") if p]
    return "-".join(parts[:6])[:80]


def _news_meta(subject: str, body_md: str) -> dict[str, Any]:
    """Title/excerpt/meta/slug del post a partir del cuerpo ya escrito."""
    return _json(
        "Eres editor de Entre Interiores. Devuelves SOLO JSON. Refiérete al "
        "protagonista como 'Robe' o 'Roberto Iniesta', NUNCA 'Robe Iniesta'.",
        f"Para este post sobre «{subject}», a partir del CUERPO, devuelve JSON con: "
        "title (titular atractivo y honesto, <=70 chars), excerpt (1 frase gancho, "
        "<=160 chars), meta_title (<=60 chars, con el protagonista al inicio), "
        "meta_description (<=155 chars), slug (kebab-case, 3-5 palabras).\n\n"
        f"CUERPO:\n\"\"\"{body_md[:4500]}\"\"\"",
        max_tokens=300,
    )


def suggest_titles(
    body_md: str,
    current_title: str,
    *,
    subject: str | None = None,
    n: int = 3,
) -> list[dict[str, str]]:
    """Propone `n` titulares ALTERNATIVOS a partir del cuerpo ya escrito.

    No persiste nada: el llamador muestra los candidatos y guarda el elegido.
    Cada candidato es {title (<=70), meta_title (<=60)}, distinto del actual y
    saneado (anti em-dash + política de nombre: nunca 'Robe Iniesta').
    """
    from app.services.text_sanitizer import enforce_name_policy, strip_ai_tells

    body = (body_md or "").strip()
    if not body:
        return []
    hint = (subject or current_title or "").strip()
    out = _json(
        "Eres editor de Entre Interiores, un sitio sobre Robe y Extremoduro. "
        "Devuelves SOLO JSON. Refiérete al protagonista como 'Robe' o 'Roberto "
        "Iniesta', NUNCA 'Robe Iniesta'. No uses la raya larga.",
        f"A partir del CUERPO de este post"
        + (f" sobre «{hint}»" if hint else "")
        + f", propón {n} TITULARES alternativos, atractivos y honestos. "
        "CADA UNO con un ÁNGULO CLARAMENTE DISTINTO entre sí y distinto del "
        f"titular actual («{current_title}»): p.ej. (1) informativo y directo "
        "(el hecho concreto: qué pasa, quién), (2) evocador o emocional (un verso, "
        "una imagen, el tono), (3) con un gancho o detalle específico que aparezca "
        "en el cuerpo (un nombre, un lugar, una cifra real). Varía la estructura y "
        "las palabras de inicio; NO repitas el mismo molde ('Robe: X y su Y'). No "
        "inventes datos que no estén en el cuerpo. "
        "Devuelve JSON {\"candidates\": [{\"title\": <=70 chars, "
        "\"meta_title\": <=60 chars con el protagonista al inicio}, ...]}.\n\n"
        f"CUERPO:\n\"\"\"{body[:4500]}\"\"\"",
        max_tokens=400,
        temperature=0.95,
    )
    raw = out.get("candidates") if isinstance(out, dict) else None
    if not isinstance(raw, list):
        return []
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for c in raw:
        if not isinstance(c, dict) or not c.get("title"):
            continue
        title = (enforce_name_policy(strip_ai_tells(str(c["title"]))) or "").strip()[:240]
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        meta = c.get("meta_title")
        meta_title = (
            (enforce_name_policy(strip_ai_tells(str(meta))) or "").strip()[:60]
            if meta
            else title[:60]
        )
        candidates.append({"title": title, "meta_title": meta_title})
        if len(candidates) >= n:
            break
    return candidates


def _boost_queries(topic_type: str, subject: str) -> list[str]:
    """Consultas de refuerzo por tipo de tema, para cuando el primer intento sale
    sin sustancia. Buscan lo CONCRETO que un fan quiere leer (declaraciones,
    anécdotas, fechas, nombres), que es justo lo que echa en falta el gate."""
    common = [
        f"{subject} Extremoduro Robe relación historia",
        f"{subject} declaraciones entrevista qué dijo",
    ]
    by_type = {
        "lugar": [
            f"{subject} historia anécdotas músicos que pasaron",
            f"{subject} cierre año qué fue testimonios",
        ],
        "persona": [
            f"{subject} biografía trayectoria discos",
            f"{subject} colaboración Robe Extremoduro",
        ],
        "banda": [
            f"{subject} grupo formación miembros discos",
            f"{subject} versión homenaje Extremoduro",
        ],
        "disco": [f"{subject} disco grabación sello críticas", f"{subject} canciones tracklist"],
        "cancion": [f"{subject} letra significado grabación", f"{subject} directo versiones"],
        "evento": [f"{subject} fecha lugar entradas cartel", f"{subject} quién actúa invitados"],
    }
    return common + by_type.get(topic_type, [f"{subject} qué es contexto detalles"])


def research_and_write(
    *, db, headline: str, source_excerpt: str, matched_term: str,
    today=None, tense: str = "informativo", boost: bool = False,
) -> dict[str, Any]:
    """Investiga el tema (adaptado a su tipo) y escribe el post. Devuelve el
    dict del post + 'video' (metadatos reales o None) + 'image_url' (o None) +
    'event_date' (date o None, solo si explícita) + 'is_relevant'. NO acredita al
    medio.

    `tense`:
      - "informativo" (def.): redacta el hecho tal cual (futuro o presente).
      - "cronica": el evento YA pasó; redacta en PASADO como crónica de lo que
        ocurrió (lo usa la caducidad cuando hay material de crónica).

    `boost`: segunda pasada tras un rechazo del gate de rigor. Amplía la búsqueda
    web con consultas por tipo de tema (`_boost_queries`). NO relaja ningún
    criterio: solo trae más material real para que haya de qué escribir.
    """
    today_iso = today.isoformat() if hasattr(today, "isoformat") else today
    plan = plan_research(headline, source_excerpt, matched_term, today=today_iso)
    if not plan.get("is_relevant", True):
        return {"title": "", "is_relevant": False}

    subject = (plan.get("subject") or matched_term or "").strip()
    # Solo aceptamos la fecha si aparece LITERAL en la fuente (anti-invención).
    event_date = validated_event_date(plan.get("event_date"), source_excerpt)
    web = web_research(plan.get("web_query") or subject)
    if boost:
        seen_urls = {r.get("url") for r in web if r.get("url")}
        for q in _boost_queries(str(plan.get("topic_type") or ""), subject):
            for r in web_research(q, n=4):
                if r.get("url") and r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    web.append(r)
    corpus = corpus_research(db, subject)
    video = find_video(plan.get("video_query") or "", subject)
    image = find_image(plan.get("image_query") or "")

    # CRÓNICA: investigación REFORZADA de los específicos que un fan quiere (setlist,
    # qué se dijo de Robe, quién más estuvo, anécdotas). Sin esto, el texto sale
    # genérico y lo mata el gate de rigor; con esto, hay base real (validada).
    cronica_txt = ""
    if tense == "cronica":
        extra: list[dict] = []
        for q in (
            f"{subject} setlist canciones que tocaron",
            f"{subject} crónica reseña qué pasó",
            f"{subject} homenaje Robe Extremoduro qué dijo",
            f"{subject} invitados asistentes quién estuvo",
        ):
            extra.extend(web_research(q, n=4))
        # Dedup por URL/título.
        seen_u: set[str] = set()
        uniq = []
        for r in extra:
            kref = r.get("url") or r.get("title") or ""
            if kref and kref not in seen_u:
                seen_u.add(kref)
                uniq.append(r)
        cronica_txt = "\n".join(f"- {r['title']}: {r['snippet']}" for r in uniq[:10])
        # Validación contra BD: qué canciones de nuestro catálogo aparecen en el
        # material de la crónica (para citar setlist real, no inventado/ajeno).
        try:
            from scripts.research.common import find_referenced_titles, get_all_song_titles
            blob = " ".join(f"{r['title']} {r['snippet']}" for r in uniq)
            song_ids = find_referenced_titles(blob, get_all_song_titles(db))
            if song_ids:
                from app.db.models import Song
                rows = db.query(Song.title).filter(Song.id.in_(song_ids)).all()
                titles = ", ".join(t for (t,) in rows)
                if titles:
                    cronica_txt += f"\n\nCANCIONES DEL CATÁLOGO DETECTADAS (setlist real validado): {titles}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("[news_research] validación setlist falló: %s", exc)

    web_txt = "\n".join(f"- {r['title']}: {r['snippet']}" for r in web) or "(sin resultados web)"
    corpus_txt = "\n".join(f"- {r['title']}: {r['excerpt']}" for r in corpus) or "(sin material en el corpus)"

    # Dossier de las entidades del catálogo que nombra la noticia. Va APARTE del
    # corpus por sujeto (que se busca por el titular y a veces no engancha nada) y
    # es lo que permite aportar algo que ningún medio tiene.
    dossier_txt = entity_dossiers(
        db, " ".join([headline, source_excerpt[:4000], web_txt])
    )

    # En modo crónica el evento ya ocurrió: redacta en pasado, sin anunciar nada
    # a futuro. En informativo, respeta el tiempo del hecho.
    tense_line = (
        "TIEMPO: el evento YA OCURRIÓ. Redacta en PASADO, como CRÓNICA de PRIMERA "
        "MANO. OBLIGATORIO ser ESPECÍFICO: qué canciones concretas sonaron, qué se "
        "dijo/dedicó sobre Robe o Extremoduro, quién más estuvo (con nombre), alguna "
        "anécdota o momento. Usa SOLO lo que conste en el material (incl. el setlist "
        "validado). Si no hay específicos, escribe MUY POCO y honesto: NO inventes ni "
        "rellenes con generalidades. NUNCA lo anuncies como futuro.\n"
        if tense == "cronica"
        else ""
    )
    # Material unificado (única fuente de hechos) + datos duros + KW objetivo.
    # El veto a hablar del lugar nació para que la crónica de un concierto no derive
    # en la historia de la sala. Cuando el protagonista ES el lugar, ese veto deja al
    # texto sin nada que desarrollar y sale dando vueltas: ahí se invierte.
    if plan.get("topic_type") == "lugar":
        foco_line = (
            "FOCO OBLIGATORIO: el protagonista ES el lugar. Cuéntalo con lo concreto "
            "que haya en el material (qué fue, quién pasó por allí con nombre, qué "
            "canciones o discos lo nombran, qué queda hoy) y ATA el relato a nuestro "
            "catálogo: si el dossier trae una canción, el ancla es ella —de qué habla "
            "su letra, en qué disco salió—, no el bar en abstracto. Nada de párrafos "
            "de ambiente ni de repetir la misma idea con otras palabras."
        )
    else:
        foco_line = (
            "FOCO OBLIGATORIO: céntrate en el hecho y sus protagonistas (quién, qué, "
            "cuándo, actuaciones, guiños a Robe/Extremoduro). Prohibido dedicar "
            "secciones al lugar/recinto/sede o su historia: solo mención de pasada."
        )
    hard = (
        f"{tense_line}"
        f"Titular de partida: {headline}\n"
        f"Tipo de tema: {plan.get('topic_type')}\n"
        f"Protagonista: {subject}\n"
        f"Enfoque (qué destacar): {plan.get('focus') or ''}\n"
        f"{foco_line}"
    )
    material = (
        f"EXTRACTO DE LA NOTICIA (punto de partida, NO copiar literal):\n"
        f"\"\"\"{source_excerpt[:4000]}\"\"\"\n\n"
        f"INVESTIGACIÓN WEB:\n{web_txt}\n\n"
        + (f"CRÓNICA / ESPECÍFICOS DEL EVENTO:\n{cronica_txt}\n\n" if cronica_txt else "")
        + f"NUESTRO CORPUS:\n{corpus_txt}"
        + (f"\n\n{dossier_txt}" if dossier_txt else "")
    )
    target_kw = subject  # KW primaria del post = el protagonista de la noticia
    kw_block = (
        f"KEYWORD OBJETIVO: «{target_kw}» (úsala con naturalidad en el título y "
        "algún H2). Construye los headings teniéndola en cuenta, sin forzar; "
        "prima el conocimiento real del material.\n"
    )

    # Generación PROFUNDA: mismo motor que las páginas SEO (outline adaptativo +
    # sección a sección + verificación factual por sección). Sustituye al antiguo
    # one-shot de 2600 tokens que salía flaco. Import perezoso (contexto script).
    body_md = ""
    try:
        from openai import OpenAI

        from scripts.seo.generate_deep import (
            _outline, _polish, _verify_section, _write_section,
        )

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        outline = _outline(client, subject, kw_block, hard, material)
        headings = [s["heading"] for s in outline]
        parts: list[str] = []
        prior = ""
        for s in outline:
            # `prior` evita que cada sección repita lo ya dicho (anti-redundancia).
            sec = _write_section(client, subject, s, headings, hard, material, kw_block, prior=prior)
            sec = _verify_section(client, sec, material)
            if sec.strip():
                parts.append(sec.strip())
                prior = "\n\n".join(parts)
        body_md = "\n\n".join(parts)
        # Pulido final: colapsa repeticiones y quita relleno (no estaba en el camino
        # de noticias; es la causa de las 8 repeticiones de "banda tributo").
        if len(body_md.strip()) > 400:
            body_md = _polish(client, subject, body_md) or body_md
    except Exception as exc:  # noqa: BLE001 — degradar al one-shot
        logger.warning("[news_research] motor profundo falló (%s); fallback one-shot", exc)

    # Fallback one-shot si el motor profundo no dio cuerpo suficiente. SIN suelo de
    # palabras: longitud PROPORCIONAL a la sustancia real (mejor corto y denso que
    # largo y vacío). Prohibido rellenar/repetir.
    if len((body_md or "").strip()) < 300:
        oneshot = _call(
            f"Escribe un post de Entre Interiores sobre «{subject}» "
            f"({plan.get('topic_type')}). Enfoque: {plan.get('focus') or ''}.\n\n"
            f"MATERIAL (única fuente de hechos):\n{material}\n\n"
            "REGLAS DURAS: usa SOLO datos CONCRETOS del material (nombres, canciones, "
            "fechas, citas, anécdotas). La longitud la marca la sustancia real: si hay "
            "poco material, escribe POCO (incluso 3-4 frases). PROHIBIDO rellenar, "
            "repetir la misma idea o usar fórmulas vacías ('rindió homenaje', 'conectó "
            "con el público', 'dejó huella'). No acredites al medio. No inventes nada. "
            "Devuelve JSON con body_md.",
            max_tokens=2200, system_prompt=_WRITE_SYS,
        )
        body_md = verify_facts(oneshot.get("body_md") or body_md, material)

    # Saneado final (anti em-dash + política de nombre: nunca 'Robe Iniesta').
    from app.services.text_sanitizer import strip_ai_tells
    body_md = strip_ai_tells(body_md) or body_md

    # Metadatos del post a partir del cuerpo final.
    meta = _news_meta(subject, body_md)
    out = {
        "title": meta.get("title") or subject,
        "excerpt": meta.get("excerpt") or "",
        "body_md": body_md,
        "meta_title": meta.get("meta_title") or "",
        "meta_description": meta.get("meta_description") or "",
        "slug": _slugify(meta.get("title") or subject),
        "target_keyword": target_kw,
    }

    # El vídeo se embebe poniendo su URL en su propia línea (MarkdownArticle lo
    # detecta) y se publica su VideoObject vía posts.video.
    if video:
        out["body_md"] = (out.get("body_md") or "").rstrip() + (
            f"\n\nhttps://www.youtube.com/watch?v={video['youtube_id']}\n"
        )
    out["video"] = video
    # Paquete hero coherente (url+alt+attribution+license+source) para apply_hero.
    # `image_url` se mantiene por compatibilidad con lectores antiguos.
    out["hero"] = image
    out["image_url"] = image["url"] if image else None
    out["event_date"] = event_date  # date o None (solo si explícita en la fuente)
    out["is_event"] = bool(plan.get("is_event"))
    out["is_relevant"] = True
    return out
