"""Generación de captions para Instagram.

Filosofía editorial:
  - El post COMENTA la noticia como contenido propio de Entre Interiores.
  - NO se menciona el medio del que salió la noticia ni se enlaza a él: la
    actualidad se cuenta con voz propia (el comentario lo genera `editorial`).
  - Cada post cierra con una PREGUNTA abierta: el caption abre conversación, no
    la termina.
  - La atribución de la foto (licencias CC) va al FINAL del todo, discreta, para
    no ensuciar la imagen ni el cuerpo pero cumplir la licencia.

ESTRUCTURA (reescrita en jul-2026 tras medir los 40 posts anteriores):

    {gancho}          ← lo ÚNICO que se ve en el feed. Distinto en cada post.
    {cuerpo}          ← una frase por línea, o nada si la imagen ya se basta
    {pregunta}
    {CTA}             ← solo cuando el post empuja a la web
    {hashtags}        ← 5-7, no 14
    🕯️ Día N sin Robe ← firma de SERIE al final, ya no cabecera

Lo que se rompió a propósito: antes el 100% de los posts abría con el contador
memorial y seguía con una etiqueta de categoría en mayúsculas. Como Instagram
solo muestra la primera línea antes del «… más», ningún seguidor llegaba a ver
de qué iba el post. El contador sigue estando —importa para el proyecto— pero
como firma al pie, donde no cuesta la única línea visible.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from app.services.instagram import captions_moldes, config, robe_quote

# Solo TRES fijos. Antes eran 7 y salían en los 40 posts seguidos, con lo que la
# mitad de los hashtags no decía nada del contenido concreto.
#
# «#RobeIniesta» estaba aquí y se ha retirado: el proyecto tiene la regla dura de
# no usar nunca ese nombre (es «Robe» o «Roberto Iniesta»), y en el benchmark del
# nicho un seguidor lo dice explícitamente en comentarios — «Robe o Roberto
# Iniesta. No quería que le llamasen Robe Iniesta». Si se quisiera recuperar por
# alcance de búsqueda, es añadir una línea aquí.
BASE_HASHTAGS = [
    "#Extremoduro", "#Robe", "#EntreInteriores",
]

# Hashtag de la serie memorial, que acompaña al contador del pie.
SERIE_HASHTAG = "#DíasSinRobe"

# Tope de hashtags. El benchmark del nicho se mueve entre 4 y 7; nosotros
# veníamos de 10-14.
MAX_HASHTAGS = 7

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
    # Nunca «#RobeIniesta»: la regla del proyecto es «Robe» o «Roberto Iniesta».
    "iniesta": "#RobertoIniesta",
}

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


# Tipos cuyo contenido YA va escrito en la imagen (el verso o la cita son el
# titular de la tarjeta). Repetirlo en el caption era redundante: aquí el texto
# se queda en la atribución y el caption se mantiene corto, como hacen las
# cuentas del nicho con sus posts de verso.
IMAGEN_SE_BASTA = ("quote", "robe_quote")


def _ctx_moldes(topic: dict) -> dict:
    """Campos reales disponibles para rellenar los moldes.

    Solo entra lo que tiene dato: un molde al que le falte un campo se descarta
    en `captions_moldes`, en vez de imprimirse con un hueco.
    """
    ctx = dict(topic.get("corpus") or {})
    headline = (topic.get("headline") or topic.get("title") or "").strip()
    if headline:
        ctx["headline"] = headline
    # "Hace 12 años: «Agila»" → years=12. Lo calculó `evergreen` con la fecha
    # real del aniversario, así que se reutiliza en vez de recalcularlo a ojo.
    m = re.search(r"[Hh]ace\s+(\d+)\s+años", topic.get("title") or "")
    if m:
        ctx["years"] = m.group(1)
    if headline:
        # Para moldes que encajan el titular dentro de una frase.
        ctx["headline_min"] = headline[0].lower() + headline[1:]
        # Igual, pero ya rematado: el molde no puede añadir el punto a ciegas
        # porque el titular puede ser una pregunta y salía «…en Plasencia?.».
        minusculo = ctx["headline_min"].rstrip()
        ctx["headline_frase"] = (
            minusculo if minusculo.endswith((".", "?", "!", "…")) else f"{minusculo}."
        )
    return ctx


def _atribucion(ctx: dict) -> str:
    """«Canción» · Artista · Disco (año), reconstruida desde el corpus AHORA.

    No se reutiliza el `summary` del item: es un snapshot de cuando se encoló y
    envejece mal. Un caso real lo demostró en producción — un post preparado
    antes de corregir el catálogo seguía diciendo «Rock Transgresivo (1989)»
    cuando el disco es de 1994 (1989 era la fecha de la maqueta). El molde, que
    sí lee la BD, decía 1994 en la misma pieza: el post se contradecía solo.

    Regla del proyecto: cada dato se re-deriva de su fuente canónica en el
    momento de usarlo, nunca se arrastra de un texto anterior.
    """
    song, artist, album = ctx.get("song"), ctx.get("artist"), ctx.get("album")
    if not (song and album):
        return ""
    partes = [f"«{song}»"]
    if artist:
        partes.append(str(artist))
    anio = f" ({ctx['year']})" if ctx.get("year") else ""
    partes.append(f"{album}{anio}")
    return " · ".join(partes)


def build(db: Session, topic: dict) -> str:
    """Construye el caption final del post."""
    content_type = topic.get("content_type") or "news"
    category = topic.get("category", "Actualidad")
    tono = topic.get("tone") or "neutral"
    title = (topic.get("title") or "").strip()
    es_blog = _es_post_de_blog(topic)
    # Semilla de la rotación determinista: el mismo post da siempre el mismo
    # molde, así que re-preparar desde el panel no cambia el texto por sorpresa.
    key = topic.get("content_key") or title
    ctx = _ctx_moldes(topic)

    # 1) GANCHO — la única línea que se ve en el feed antes del «… más».
    lines = [captions_moldes.hook(content_type, ctx, key) or title]

    # 2) CUERPO. Bimodal a propósito: en los posts donde la imagen ya lleva el
    #    texto, aquí solo va la atribución; en los demás, el cuerpo largo pero
    #    troceado a una frase por línea (que es como respiran los captions que
    #    funcionan en este nicho).
    if content_type in IMAGEN_SE_BASTA:
        body = _atribucion(ctx) or (topic.get("summary") or "").strip()
        if body:
            lines += ["", body]
    else:
        body = (topic.get("caption_body") or "").strip()
        if not body:
            body = (topic.get("summary") or "").strip()
        if body:
            lines += ["", captions_moldes.one_sentence_per_line(body)]

    # 3) Verso afín al tema (solo noticias/blog: en evergreen el verso YA es el
    #    contenido). Se reutiliza el calculado en `publisher.prepare` para que
    #    coincida con el de la imagen.
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

    # 4) PREGUNTA de cierre: abre conversación. Se omite en tono sobrio, donde
    #    una pregunta de ese corte desentona (homenajes, fallecimientos).
    if tono != "sober":
        pregunta = captions_moldes.question(content_type, ctx, key)
        if pregunta:
            lines += ["", pregunta]

    # 5) CTA solo cuando el post empuja de verdad a la web. Antes iba en todos y
    #    se leía repetido; ninguna de las cuentas del benchmark lo usa siempre.
    if content_type == "product":
        cuerpo_extra = (topic.get("detalle") or "").strip()
        if cuerpo_extra:
            lines += ["", captions_moldes.one_sentence_per_line(cuerpo_extra)]
        # A /registro, NUNCA a la ruta privada: rebotaría al login y dejaría al
        # visitante en la puerta.
        lines += ["", (topic.get("cta") or
                       "Está en Entre Interiores. Cuenta gratis. 🔗 Link en la bio.")]
    elif es_blog and topic.get("url"):
        lines += ["", "📝 El artículo completo está en el blog (link en la bio)."]

    # 6) Hashtags: primero los concretos de este post, luego categoría y marca.
    subject_tag = _hashtagify(topic.get("image_query") or "")
    llm_tags = [t for t in (topic.get("hashtags") or []) if t and t.startswith("#")]
    content_tags = (
        llm_tags
        + ([subject_tag] if subject_tag else [])
        + _specific_hashtags(title, body)
    )
    # Los de categoría se limitan a 2: son los más genéricos (#Música #Disco
    # #Rock salían en todos los posts musicales) y con el tope de 7 se comían el
    # sitio de los que sí dicen algo del contenido.
    hashtags = (
        content_tags + CATEGORY_HASHTAGS.get(category, [])[:2] + BASE_HASHTAGS
    )
    seen: list[str] = []
    seen_norm: set[str] = set()
    for h in hashtags:
        norm_key = _norm(h)
        if norm_key and norm_key not in seen_norm:
            seen_norm.add(norm_key)
            seen.append(h)
    lines += ["", " ".join(seen[:MAX_HASHTAGS])]

    # 7) Firma de serie al pie: el contador memorial deja de robar la primera
    #    línea, pero sigue en todos los posts.
    lines += ["", f"🕯️ Día {config.dias_sin_robe()} sin Robe · {SERIE_HASHTAG}"]

    # 8) Atribución de la foto al FINAL del todo (discreta), si es foto con
    #    licencia CC. Cumple la licencia sin ensuciar imagen ni cuerpo.
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
