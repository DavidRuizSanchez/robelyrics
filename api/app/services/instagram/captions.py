"""Generación de captions para Instagram.

Filosofía editorial:
  - El post COMENTA la noticia como contenido propio de Entre Interiores.
  - NO se menciona el medio del que salió la noticia ni se enlaza a él: la
    actualidad se cuenta con voz propia (el comentario lo genera `editorial`).
  - El cierre invita a seguir en Entre Interiores ("link en la bio"), porque
    Instagram no permite enlaces clicables en el caption.
  - Cada post cierra con un verso de Robe/Extremoduro afín al tema.
  - La atribución de la foto (licencias CC) va al FINAL del todo, discreta, para
    no ensuciar la imagen ni el cuerpo pero cumplir la licencia.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from sqlalchemy.orm import Session

from app.services.instagram import config, robe_quote

CATEGORY_EMOJI = {
    "Conciertos": "🎤", "Música": "🎸", "Colaboraciones": "🤝",
    "Grupos amigos": "🔥", "Cultura": "📖", "Efemérides": "📅",
    "Curiosidades": "💡", "Actualidad": "📰", "Blog": "📝",
}

BASE_HASHTAGS = [
    "#Extremoduro", "#RobeIniesta", "#Robe", "#RockEspañol",
    "#EntreInteriores", "#Plasencia", "#RockTransgresivo",
]

CATEGORY_HASHTAGS = {
    "Conciertos": ["#Concierto", "#Gira", "#EnDirecto"],
    "Música": ["#Música", "#Disco", "#Rock"],
    "Colaboraciones": ["#Colaboración", "#Música"],
    "Grupos amigos": ["#RockEstatal"],
    "Cultura": ["#Poesía", "#Cultura", "#Letras"],
    "Efemérides": ["#UnDíaComoHoy", "#Historia", "#RockHistórico"],
    "Curiosidades": ["#SabíasQue", "#Curiosidades"],
    "Actualidad": ["#Actualidad"],
    "Blog": ["#Blog", "#Letras", "#Cultura"],
}

# Entidades del universo Robe/Extremoduro → hashtag específico. Se detectan por
# substring (normalizado) en el título + cuerpo para enriquecer los hashtags
# con lo concreto de cada publicación.
ENTITY_HASHTAGS = {
    "leiva": "#Leiva",
    "fito": "#FitoYFitipaldis",
    "marea": "#Marea",
    "kutxi": "#Marea",
    "rosendo": "#Rosendo",
    "platero": "#PlateroYTú",
    "uoho": "#Uoho",
    "iñaki antón": "#Uoho",
    "extrechinato": "#Extrechinato",
    "chinato": "#ManoloChinato",
    "el drogas": "#ElDrogas",
    "barricada": "#Barricada",
    "plasencia": "#Plasencia",
    "caceres": "#Cáceres",
    "extremadura": "#Extremadura",
    "iniesta": "#RobeIniesta",
}

# Llamadas a la acción: invitan a seguir en Entre Interiores (link en la bio).
# Tono FESTIVO: para temas neutros o celebratorios.
PLAYFUL_CTAS = [
    "Lo típico de esto y mucho más sobre Robe y Extremoduro, en Entre Interiores. 🔗 Link en la bio.",
    "En Entre Interiores lo contamos a fondo: las letras, las historias y todo el universo de Robe. 🔗 Link en la bio.",
    "Esto y todo el universo Extremoduro, en Entre Interiores. Tienes el enlace en la bio. 🔗",
    "¿Quieres más? El universo de Robe y Extremoduro al completo, en Entre Interiores. 🔗 Link en la bio.",
]

# Tono SOBRIO: para temas luctuosos o conmemorativos. Sin efusividad.
SOBER_CTAS = [
    "Toda su obra sigue viva en Entre Interiores: las letras, las historias y el universo de Robe y Extremoduro. 🔗 Link en la bio.",
    "Recorre su legado en Entre Interiores: las letras, las historias, su universo entero. 🔗 Link en la bio.",
]


def _norm(s: str) -> str:
    s = "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )
    return s.lower()


def _hashtagify(name: str) -> str:
    """'Caída libre' → '#CaidaLibre'. Conserva tildes en la salida visible."""
    cleaned = re.sub(r"[^\w\s]", "", name or "", flags=re.UNICODE).strip()
    if not cleaned:
        return ""
    camel = "".join(w.capitalize() for w in cleaned.split())
    return f"#{camel}" if camel else ""


def _specific_hashtags(title: str, body: str) -> list[str]:
    """Hashtags concretos del contenido: entidades del universo mencionadas.

    NO se incluye la canción del verso ornamental: no es el tema del post y
    generaba hashtags larguísimos y repetidos entre publicaciones.
    """
    text = _norm(f"{title} {body}")
    tags: list[str] = []
    for key, tag in ENTITY_HASHTAGS.items():
        if _norm(key) in text and tag not in tags:
            tags.append(tag)
    return tags[:5]


def _es_post_de_blog(topic: dict) -> bool:
    """True si el tema procede de nuestro propio blog (entreinteriores.com)."""
    return topic.get("category") == "Blog" or "Blog" in (topic.get("source") or "")


def build(db: Session, topic: dict) -> str:
    """Construye el caption final del post."""
    category = topic.get("category", "Actualidad")
    tone = topic.get("tone") or "neutral"
    emoji = CATEGORY_EMOJI.get(category, "📰")
    # En tono sobrio nunca el emoji de fuego: desentona en un homenaje.
    if tone == "sober" and emoji == "🔥":
        emoji = "🎵"
    title = (topic.get("title") or "").strip()
    es_blog = _es_post_de_blog(topic)

    # Cuerpo: comentario editorial reescrito (noticias) o el extracto propio
    # (posts del blog). Nunca se cita ningún medio externo.
    body = (topic.get("caption_body") or "").strip()
    if not body:
        summary = (topic.get("summary") or "").strip()
        body = f"{title}\n\n{summary}".strip() if summary else title

    # Apertura memorial fija en todos los posts.
    lines = [f"🕯️ Día {config.dias_sin_robe()} sin Robe", "",
             f"{emoji} {category.upper()}", "", body]

    # Verso de Robe/Extremoduro afín al tema. Se reutiliza el ya calculado en
    # `publisher.prepare` (para que coincida con el de la imagen); si no, se
    # busca aquí (buscador semántico in-process).
    verse = topic.get("verse")
    if verse is None:
        verse = robe_quote.find_verse(db, f"{title}. {body}")
    if verse:
        attribution = verse["artist"]
        if verse["song"]:
            attribution += f', «{verse["song"]}»'
        if verse.get("year"):
            attribution += f" ({verse['year']})"
        lines += ["", f"🎵 «{verse['line']}»", f"   — {attribution}"]

    # Enlace SOLO cuando la fuente es nuestra: un artículo del blog. En IG no
    # hay enlaces clicables → se remite a la bio.
    if es_blog and topic.get("url"):
        lines += ["", "📝 El artículo completo está en el blog (link en la bio)."]

    # Gancho hacia Entre Interiores, según el tono (rotación determinista).
    ctas = SOBER_CTAS if tone == "sober" else PLAYFUL_CTAS
    idx = int(hashlib.md5(title.encode()).hexdigest(), 16) % len(ctas)
    lines += ["", ctas[idx]]

    # Hashtags. Orden: específicos del contenido PRIMERO (lo concreto de este
    # post: #MilongasExtremas, etc.), luego categoría y base genérica.
    #   - topic['hashtags']: los que generó el LLM (nombres propios citados).
    #   - el sujeto de la foto (image_query) hashtagificado.
    #   - entidades del universo detectadas + la canción del verso.
    subject_tag = _hashtagify(topic.get("image_query") or "")
    llm_tags = [t for t in (topic.get("hashtags") or []) if t and t.startswith("#")]
    content_tags = (
        llm_tags
        + ([subject_tag] if subject_tag else [])
        + _specific_hashtags(title, body)
    )
    hashtags = content_tags + CATEGORY_HASHTAGS.get(category, []) + BASE_HASHTAGS
    seen: list[str] = []
    seen_norm: set[str] = set()
    for h in hashtags:
        key = _norm(h)
        if key and key not in seen_norm:
            seen_norm.add(key)
            seen.append(h)
    lines += ["", " ".join(seen[:14])]

    # Atribución de la foto al FINAL del todo (discreta), si es foto con
    # licencia CC. Cumple la licencia sin ensuciar imagen ni cuerpo.
    credit = (topic.get("image_credit") or "").strip()
    if credit:
        lines += ["", f"📷 {credit}"]

    caption = "\n".join(lines)[:2190]

    # Red de seguridad anti-alucinación: corrige errores de catálogo (canción↔
    # álbum↔año) contra la BD antes de publicar. Determinista, no reescribe.
    try:
        from app.services.fact_check import check_body, correct_body
        rep = check_body(db, caption, use_web=False)
        if rep.autofixes:
            caption, _ = correct_body(db, caption, rep)
    except Exception:  # noqa: BLE001 — best-effort, nunca bloquea la publicación
        pass

    return caption
