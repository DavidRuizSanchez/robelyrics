"""Generación de captions para Instagram.

Filosofía editorial:
  - El post COMENTA la noticia como contenido propio de Entre Interiores.
  - NO se menciona el medio del que salió la noticia ni se enlaza a él: la
    actualidad se cuenta con voz propia (el comentario lo genera `editorial`).
  - Solo se enlaza una fuente cuando es NUESTRA: un artículo del blog de
    entreinteriores.com. Esos posts sí llevan enlace al blog.
  - Cada post cierra con un verso de Robe/Extremoduro afín al tema y un
    gancho hacia el buscador semántico de entreinteriores.com.
"""
from __future__ import annotations

import hashlib
from datetime import date

from sqlalchemy.orm import Session

from app.services.instagram import robe_quote

# Robe Iniesta falleció el 10 de diciembre de 2025. Cada post abre con un
# contador memorial "Día X sin Robe".
_ROBE_DEATH = date(2025, 12, 10)


def _dias_sin_robe() -> int:
    return max(0, (date.today() - _ROBE_DEATH).days)

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
    "Grupos amigos": ["#RockEstatal", "#Fito", "#Marea"],
    "Cultura": ["#Poesía", "#Cultura", "#Letras"],
    "Efemérides": ["#UnDíaComoHoy", "#Historia", "#RockHistórico"],
    "Curiosidades": ["#SabíasQue", "#Curiosidades"],
    "Actualidad": ["#Noticias", "#Actualidad"],
    "Blog": ["#Blog", "#Letras", "#Cultura"],
}

# Llamadas a la acción hacia el buscador semántico de entreinteriores.com.
# Tono FESTIVO: para temas neutros o celebratorios.
PLAYFUL_CTAS = [
    "🔎 ¿Hay un verso de Robe para lo que estás viviendo? Lo hay. "
    "Métete en el buscador de entreinteriores.com, escribe lo que sientes "
    "y descubre qué canción de Extremoduro lo cuenta mejor que nadie.",

    "🎸 Este verso lo ha encontrado el buscador de entreinteriores.com. "
    "Pruébalo tú: escribe una emoción, un lío, una alegría… y te decimos "
    "en qué canción de Robe está escrito.",

    "👉 En entreinteriores.com tienes un buscador que lee como Robe: "
    "le cuentas lo que te pasa y te encuentra el verso exacto de "
    "Extremoduro. Engancha. Avisado quedas.",

    "🔥 ¿Sabes qué canción de Robe habla de TU momento? El buscador de "
    "entreinteriores.com sí. Entra, escribe, y flipa con lo que encuentra.",
]

# Tono SOBRIO: para temas luctuosos o conmemorativos (muerte, homenajes,
# reconocimientos póstumos). Sin ganchos comerciales ni efusividad.
SOBER_CTAS = [
    "En entreinteriores.com puedes recorrer su obra entera: las letras, "
    "las historias y el universo de Robe y Extremoduro.",

    "Toda su obra sigue viva en entreinteriores.com: las letras, las "
    "historias y el universo de Robe y Extremoduro.",
]


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
    lines = [f"🕯️ Día {_dias_sin_robe()} sin Robe", "",
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

    lines += ["", "—"]

    # Atribución de la foto cuando el fondo es una imagen real con licencia CC.
    credit = (topic.get("image_credit") or "").strip()
    if credit:
        lines.append(f"📷 Foto: {credit}")

    # Enlace SOLO cuando la fuente es nuestra: un artículo del blog.
    if es_blog and topic.get("url"):
        lines.append("📝 El artículo completo, en nuestro blog:")
        lines.append(f"🔗 {topic['url']}")

    # Gancho hacia el buscador, según el tono (rotación determinista por título).
    ctas = SOBER_CTAS if tone == "sober" else PLAYFUL_CTAS
    idx = int(hashlib.md5(title.encode()).hexdigest(), 16) % len(ctas)
    lines += ["", ctas[idx], ""]

    hashtags = BASE_HASHTAGS + CATEGORY_HASHTAGS.get(category, [])
    seen: list[str] = []
    for h in hashtags:
        if h not in seen:
            seen.append(h)
    lines.append(" ".join(seen))

    # Límite duro de Instagram: 2.200 caracteres.
    return "\n".join(lines)[:2190]
