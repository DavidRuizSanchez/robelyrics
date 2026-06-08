"""Selección de los temas del día para Instagram.

Combina noticias agregadas (`news_items`, puntuadas por relevancia + frescura
+ variedad de categoría) con efemérides y curiosidades cuando la actualidad
escasea. Instagram usa TODO el corpus de noticias (cualquier `policy`): solo
enlaza y atribuye al medio original, nunca reescribe contenido ajeno.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select as sql_select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, NewsItem
from app.services.instagram import config, efemerides

logger = logging.getLogger(__name__)

# Ventana temporal para deduplicar temas (noticia repetida o misma temática).
DEDUP_WINDOW_DAYS = 30
# No encolar dos posts de relleno (efeméride/curiosidad) del mismo tipo dentro
# de esta ventana: evita "Curiosidad del universo Extremoduro" dos días seguidos
# cuando escasea la actualidad. Mejor publicar poco que repetir.
FILLER_COOLDOWN_DAYS = 7

# Contenido que NO es un hecho noticiable propio: encuestas, votaciones,
# rankings, quizzes, listicles. Como el post lo comenta como nuestro, este
# tipo de contenido de terceros no debe entrar.
_NO_COMENTABLE = re.compile(
    r"\b(encuesta|votaci[oó]n|v[oó]ta(?:lo|la|r)?|elige\s+tu|"
    r"ranking|top\s?\d+|los\s+\d+\s+mejores|"
    r"qu[ií]z|adivina|cu[aá]l\s+(?:fue|es)\s+(?:el|la|tu)\s+mejor)\b",
    re.IGNORECASE,
)

# La muerte de Robe (diciembre 2025) es un HECHO CONSOLIDADO, no actualidad.
# Los medios reeditan obituarios con fecha reciente y se colarían como noticia
# fresca. El anuncio de su muerte nunca debe entrar como tema (sí los homenajes
# o reconocimientos posteriores, que son actualidad real y los trata `tone`).
_MUERTE_CONSOLIDADA = re.compile(
    r"\b(muere|muri[oó]|ha\s+muerto|fallec\w+|fallecimiento|nos\s+dej[oó]|"
    r"adi[oó]s\s+a\s+robe|obituario|a\s+los\s+\d{2}\s+a[ñn]os)\b",
    re.IGNORECASE,
)


def _es_comentable(news: NewsItem) -> bool:
    """True si la noticia es un hecho real comentable (no encuesta/ranking/quiz)."""
    return _NO_COMENTABLE.search(f"{news.title} {news.summary or ''}") is None


def _es_muerte_consolidada(news: NewsItem) -> bool:
    """True si la noticia es (un refrito de) el anuncio de la muerte de Robe."""
    return _MUERTE_CONSOLIDADA.search(f"{news.title} {news.summary or ''}") is not None


def _demasiado_vieja(news: NewsItem) -> bool:
    """True si el artículo supera la ventana de frescura (última semana)."""
    stamp = news.published_at or news.fetched_at
    if stamp is None:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).days > config.FRESHNESS_DAYS


def _freshness(news: NewsItem) -> float:
    """Bonus por frescura: las noticias de hoy puntúan más."""
    stamp = news.published_at or news.fetched_at
    if stamp is None:
        return 0.0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - stamp).total_seconds() / 3600
    if hours < 24:
        return 4.0
    if hours < 48:
        return 2.0
    if hours < 96:
        return 1.0
    return 0.0


# Palabras que NO distinguen un tema (vacías + ubicuas del dominio: aparecen en
# casi todos los titulares, así que no sirven para medir si dos temas se repiten).
_STOPWORDS = {
    "de", "la", "el", "los", "las", "en", "con", "una", "uno", "del", "por",
    "para", "que", "sobre", "su", "sus", "al", "un", "y", "o", "a", "se", "lo",
    "le", "como", "mas", "este", "esta", "fue", "ser", "es", "su", "the",
    "robe", "iniesta", "roberto", "extremoduro",
}


def _stem(w: str) -> str:
    """Stemming ligero para unir plurales (premios→premio, musicas→musica)."""
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]
    return w


def _keywords(text: str) -> set[str]:
    """Palabras significativas (sin tildes, sin stopwords, con stem) de un texto.
    Sirven para medir si dos titulares tratan del mismo tema."""
    norm = "".join(
        c for c in __import__("unicodedata").normalize("NFD", text or "")
        if __import__("unicodedata").category(c) != "Mn"
    ).lower()
    words = re.findall(r"[a-z0-9]+", norm)
    return {_stem(w) for w in words if len(w) > 3 and w not in _STOPWORDS}


def _too_similar(kw: set[str], previas: list[set[str]], thr: float = 0.4) -> bool:
    """True si las keywords solapan demasiado (Jaccard) con algún tema previo."""
    if not kw:
        return False
    for prev in previas:
        if not prev:
            continue
        inter = len(kw & prev)
        union = len(kw | prev)
        if union and inter / union >= thr:
            return True
    return False


def _filler_reciente(db: Session, category: str, dias: int = FILLER_COOLDOWN_DAYS) -> bool:
    """True si ya hay un post de relleno de esa categoría (Efemérides/Curiosidades)
    encolado o publicado en los últimos `dias`. Sirve para no repetir el mismo
    tipo de relleno en días seguidos."""
    ventana = datetime.now(timezone.utc) - timedelta(days=dias)
    existe = db.execute(
        sql_select(InstagramQueueItem.id).where(
            InstagramQueueItem.category == category,
            InstagramQueueItem.status.in_(["published", "prepared", "pending"]),
            InstagramQueueItem.created_at >= ventana,
        ).limit(1)
    ).first()
    return existe is not None


def select(db: Session, count: int = 3) -> list[dict]:
    """Selecciona los `count` temas del día.

    Reglas:
      1. Las noticias se ordenan por relevancia + frescura.
      2. Se evita repetir categoría para dar variedad.
      3. Se descartan las URLs que ya están en la cola de Instagram.
      4. Si no hay noticias suficientes, se rellena con efeméride del día y/o
         curiosidad temática.
    """
    candidatos = db.execute(
        sql_select(NewsItem).order_by(NewsItem.relevance_score.desc()).limit(200)
    ).scalars().all()

    # URLs ya encoladas (cualquier estado): no repetir un tema reciente.
    ya_en_cola = set(
        db.execute(
            sql_select(InstagramQueueItem.source_url).where(
                InstagramQueueItem.source_url.is_not(None)
            )
        ).scalars().all()
    )

    # Keywords de los temas encolados/publicados en los últimos 30 DÍAS: para NO
    # repetir la misma temática (p.ej. cuatro posts de los Premios de la Música,
    # o la misma noticia agregada bajo dos URLs distintas de Google News). Antes
    # solo se miraban los últimos 10 items y un tema se "salía" de la ventana en
    # pocos días, colándose duplicado. Ahora la ventana es temporal.
    ventana = datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)
    recientes_titulos = db.execute(
        sql_select(InstagramQueueItem.title)
        .where(
            InstagramQueueItem.status.in_(["published", "prepared", "pending"]),
            InstagramQueueItem.created_at >= ventana,
        )
        .order_by(InstagramQueueItem.created_at.desc())
        .limit(300)
    ).scalars().all()
    recent_kwsets = [_keywords(t) for t in recientes_titulos if t]

    rankeadas = sorted(
        candidatos,
        key=lambda n: (n.relevance_score or 0) + _freshness(n),
        reverse=True,
    )

    temas: list[dict] = []
    categorias_usadas: set[str] = set()
    urls_usadas: set[str] = set()
    # Arranca con los temas recientes para no repetirlos en esta tanda.
    kwsets_usados: list[set[str]] = list(recent_kwsets)

    def _admisible(n: NewsItem) -> bool:
        if n.url in ya_en_cola or n.url in urls_usadas:
            return False
        if _demasiado_vieja(n):
            return False
        if _es_muerte_consolidada(n):
            return False
        if (n.relevance_score or 0) + _freshness(n) < 3:
            return False
        return _es_comentable(n)

    # Primera pasada: máxima variedad de categoría Y de temática.
    for n in rankeadas:
        if len(temas) >= count:
            break
        cat = n.category or "Actualidad"
        kw = _keywords(n.title)
        if cat in categorias_usadas or not _admisible(n):
            continue
        if _too_similar(kw, kwsets_usados):
            continue
        temas.append(_tema_de_noticia(n))
        categorias_usadas.add(cat)
        urls_usadas.add(n.url)
        kwsets_usados.append(kw)

    # Segunda pasada: rellenar aunque repita categoría, pero NO la temática.
    for n in rankeadas:
        if len(temas) >= count:
            break
        if not _admisible(n):
            continue
        kw = _keywords(n.title)
        if _too_similar(kw, kwsets_usados):
            continue
        temas.append(_tema_de_noticia(n))
        urls_usadas.add(n.url)
        kwsets_usados.append(kw)

    # Tercera pasada: efeméride del día. Solo si NO se publicó otra efeméride en
    # la última semana (cooldown) y su contenido no solapa con lo ya elegido.
    if len(temas) < count and not _filler_reciente(db, "Efemérides"):
        for ef in efemerides.for_today():
            if len(temas) >= count:
                break
            kw = _keywords(ef)
            if _too_similar(kw, kwsets_usados):
                continue
            temas.append({
                "news_item_id": None,
                "title": "Un día como hoy en la historia de Extremoduro",
                "category": "Efemérides",
                "summary": ef,
                "source": "Entre Interiores · Efemérides",
                "url": "",
            })
            kwsets_usados.append(kw)

    # Cuarta pasada: curiosidad temática. Mismo cooldown: nunca dos curiosidades
    # seguidas. El cuerpo rota por día pero el título es fijo y se veían calcadas.
    if len(temas) < count and not _filler_reciente(db, "Curiosidades"):
        curiosidad = efemerides.curiosidad_del_dia()
        if not _too_similar(_keywords(curiosidad), kwsets_usados):
            temas.append({
                "news_item_id": None,
                "title": "Curiosidad del universo Extremoduro",
                "category": "Curiosidades",
                "summary": curiosidad,
                "source": "Entre Interiores · Curiosidades",
                "url": "",
            })

    return temas[:count]


def _tema_de_noticia(n: NewsItem) -> dict:
    return {
        "news_item_id": n.id,
        "title": n.title,
        "category": n.category or "Actualidad",
        "summary": n.summary or "",
        "source": n.source_medium or n.source_name,
        "url": n.url,
    }
