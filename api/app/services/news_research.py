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


def _json(system: str, user: str, max_tokens: int = 700) -> dict[str, Any]:
    """Llamada JSON ligera (clasificación/selección), sin los campos que exige
    el generador de posts."""
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
            temperature=0.3,
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


def plan_research(headline: str, excerpt: str, matched_term: str) -> dict[str, Any]:
    user = f"""\
Noticia:
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
    lugar, quién; de una persona/banda: quiénes son, trayectoria, relación con
    Robe; etc.).
"""
    plan = _json(_PLAN_SYS, user)
    plan.setdefault("is_relevant", True)
    plan.setdefault("topic_type", "otro")
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


def find_image(query: str) -> str | None:
    if not query:
        return None
    cands = web_image.search(query)
    return cands[0]["url"] if cands else None


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
    "mezcles eventos distintos en uno: céntrate en el hecho de la noticia. No "
    "uses la raya larga."
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


def research_and_write(
    *, db, headline: str, source_excerpt: str, matched_term: str,
    today=None,
) -> dict[str, Any]:
    """Investiga el tema (adaptado a su tipo) y escribe el post. Devuelve el
    dict del post + 'video' (metadatos reales o None) + 'image_url' (o None) +
    'is_relevant'. NO acredita al medio."""
    plan = plan_research(headline, source_excerpt, matched_term)
    if not plan.get("is_relevant", True):
        return {"title": "", "is_relevant": False}

    subject = (plan.get("subject") or matched_term or "").strip()
    web = web_research(plan.get("web_query") or subject)
    corpus = corpus_research(db, subject)
    video = find_video(plan.get("video_query") or "", subject)
    image = find_image(plan.get("image_query") or "")

    web_txt = "\n".join(f"- {r['title']}: {r['snippet']}" for r in web) or "(sin resultados web)"
    corpus_txt = "\n".join(f"- {r['title']}: {r['excerpt']}" for r in corpus) or "(sin material en el corpus)"

    # Material unificado (única fuente de hechos) + datos duros + KW objetivo.
    hard = (
        f"Titular de partida: {headline}\n"
        f"Tipo de tema: {plan.get('topic_type')}\n"
        f"Protagonista: {subject}\n"
        f"Enfoque (qué destacar): {plan.get('focus') or ''}"
    )
    material = (
        f"EXTRACTO DE LA NOTICIA (punto de partida, NO copiar literal):\n"
        f"\"\"\"{source_excerpt[:4000]}\"\"\"\n\n"
        f"INVESTIGACIÓN WEB:\n{web_txt}\n\n"
        f"NUESTRO CORPUS:\n{corpus_txt}"
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

        from scripts.seo.generate_deep import _outline, _verify_section, _write_section

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        outline = _outline(client, subject, kw_block, hard, material)
        headings = [s["heading"] for s in outline]
        parts: list[str] = []
        for s in outline:
            sec = _write_section(client, subject, s, headings, hard, material, kw_block)
            sec = _verify_section(client, sec, material)
            if sec.strip():
                parts.append(sec.strip())
        body_md = "\n\n".join(parts)
    except Exception as exc:  # noqa: BLE001 — degradar al one-shot
        logger.warning("[news_research] motor profundo falló (%s); fallback one-shot", exc)

    # Fallback one-shot si el motor profundo no dio cuerpo suficiente.
    if len((body_md or "").strip()) < 400:
        oneshot = _call(
            f"Escribe un post de Entre Interiores sobre «{subject}» "
            f"({plan.get('topic_type')}). Enfoque: {plan.get('focus') or ''}. Da el "
            f"MÁXIMO de información relevante.\n\nMATERIAL:\n{material}\n\n"
            "Adapta al tipo (disco->salida/sello/tracklist; evento->fecha/lugar; "
            "persona/banda->trayectoria y relación con Robe/Extremoduro). 600-900 "
            "palabras, 2-3 H2. No acredites al medio. No inventes. Devuelve JSON "
            "con body_md.",
            max_tokens=2600, system_prompt=_WRITE_SYS,
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
    out["image_url"] = image
    out["is_relevant"] = True
    return out
