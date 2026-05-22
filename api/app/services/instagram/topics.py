"""Selección de los temas del día para Instagram.

Combina noticias agregadas (`news_items`, puntuadas por relevancia + frescura
+ variedad de categoría) con efemérides y curiosidades cuando la actualidad
escasea. Instagram usa TODO el corpus de noticias (cualquier `policy`): solo
enlaza y atribuye al medio original, nunca reescribe contenido ajeno.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select as sql_select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, NewsItem
from app.services.instagram import efemerides

logger = logging.getLogger(__name__)

# Contenido que NO es un hecho noticiable propio: encuestas, votaciones,
# rankings, quizzes, listicles. Como el post lo comenta como nuestro, este
# tipo de contenido de terceros no debe entrar.
_NO_COMENTABLE = re.compile(
    r"\b(encuesta|votaci[oó]n|v[oó]ta(?:lo|la|r)?|elige\s+tu|"
    r"ranking|top\s?\d+|los\s+\d+\s+mejores|"
    r"qu[ií]z|adivina|cu[aá]l\s+(?:fue|es)\s+(?:el|la|tu)\s+mejor)\b",
    re.IGNORECASE,
)


def _es_comentable(news: NewsItem) -> bool:
    """True si la noticia es un hecho real comentable (no encuesta/ranking/quiz)."""
    return _NO_COMENTABLE.search(f"{news.title} {news.summary or ''}") is None


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

    rankeadas = sorted(
        candidatos,
        key=lambda n: (n.relevance_score or 0) + _freshness(n),
        reverse=True,
    )

    temas: list[dict] = []
    categorias_usadas: set[str] = set()
    urls_usadas: set[str] = set()

    def _admisible(n: NewsItem) -> bool:
        if n.url in ya_en_cola or n.url in urls_usadas:
            return False
        if (n.relevance_score or 0) + _freshness(n) < 3:
            return False
        return _es_comentable(n)

    # Primera pasada: máxima variedad de categoría.
    for n in rankeadas:
        if len(temas) >= count:
            break
        cat = n.category or "Actualidad"
        if cat in categorias_usadas or not _admisible(n):
            continue
        temas.append(_tema_de_noticia(n))
        categorias_usadas.add(cat)
        urls_usadas.add(n.url)

    # Segunda pasada: rellenar con buenas noticias aunque repitan categoría.
    for n in rankeadas:
        if len(temas) >= count:
            break
        if not _admisible(n):
            continue
        temas.append(_tema_de_noticia(n))
        urls_usadas.add(n.url)

    # Tercera pasada: efeméride del día.
    if len(temas) < count:
        for ef in efemerides.for_today():
            if len(temas) >= count:
                break
            temas.append({
                "news_item_id": None,
                "title": "Un día como hoy en la historia de Extremoduro",
                "category": "Efemérides",
                "summary": ef,
                "source": "Entre Interiores · Efemérides",
                "url": "",
            })

    # Cuarta pasada: curiosidad temática.
    if len(temas) < count:
        temas.append({
            "news_item_id": None,
            "title": "Curiosidad del universo Extremoduro",
            "category": "Curiosidades",
            "summary": efemerides.curiosidad_del_dia(),
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
