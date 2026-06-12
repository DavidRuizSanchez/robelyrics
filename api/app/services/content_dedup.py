"""Red anti-duplicados transversal para el contenido del blog.

Calcula una huella estable (`content_key`) por tipo de contenido y comprueba
si ya existe una propuesta viva o un post publicado reciente con esa misma
huella. Evita que el mismo tema/noticia/efeméride se proponga o publique dos
veces, aunque venga por vías o fuentes distintas.

Patrón calcado de `InstagramQueueItem.content_key`. La huella la rellena el
productor de la propuesta (scrape_news, generate_proposals, keyword_research,
publish_song_spotlight) y la copia `materialize_proposals` al `Post`.

Formato de huella: "<tipo>:<identificador>". Ejemplos:
  - "spotlight:song_123"
  - "evergreen:robe-iniesta-letras"
  - "anniversary:album_la-ley-innata_2008"
  - "news:aurora-beltran-version-extremoduro"
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from app.db.models import ContentProposal, Post

# Estados de propuesta que cuentan como "vivos" (ocupan el tema).
LIVE_PROPOSAL_STATES = ("proposed", "approved", "scheduled")

# Ventana por defecto para considerar un post publicado como "todavía cubre"
# el tema. Las noticias caducan antes; el evergreen/efeméride mucho después.
DEFAULT_RECENCY_DAYS = 365
NEWS_RECENCY_DAYS = 45

# Palabras vacías que se eliminan al normalizar titulares de noticias.
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "a", "y", "o", "u", "e", "en", "con", "por", "para", "que", "su", "sus",
    "lo", "se", "le", "les", "como", "mas", "más", "ya", "the", "of", "to",
}


def slugify(text: str) -> str:
    """Normaliza a slug ASCII estable (minúsculas, sin tildes, guiones)."""
    norm = unicodedata.normalize("NFKD", text or "")
    ascii_text = norm.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-")


def _event_fingerprint(title: str, *, max_words: int = 6) -> str:
    """Huella de un titular de noticia: slug de sus palabras significativas
    ordenadas alfabéticamente, para que dos medios contando el mismo evento
    con titulares parecidos colisionen."""
    base = slugify(title)
    words = [w for w in base.split("-") if w and w not in _STOPWORDS and len(w) > 2]
    words = sorted(set(words))[:max_words]
    return "-".join(words) or base


def content_key_for(kind: str, **kw) -> str | None:
    """Huella estable por tipo. Devuelve None si no hay datos suficientes
    (en cuyo caso el llamador se apoya en sus dedups específicos).

    kwargs aceptados según tipo:
      - spotlight:           song_id
      - evergreen:           target_keyword_slug | slug
      - anniversary:         entity_slug, year  (o source_type/source_id)
      - album-anniversary:   entity_slug, year
      - news:                title | url
    """
    if kind == "spotlight":
        sid = kw.get("song_id") or kw.get("source_id")
        return f"spotlight:song_{sid}" if sid else None

    if kind == "evergreen":
        slug = kw.get("target_keyword_slug") or kw.get("slug")
        if not slug and kw.get("target_keyword"):
            slug = slugify(kw["target_keyword"])
        return f"evergreen:{slug}" if slug else None

    if kind in ("anniversary", "album-anniversary"):
        ent = kw.get("entity_slug") or kw.get("slug")
        if not ent and kw.get("source_type") and kw.get("source_id"):
            ent = f"{kw['source_type']}_{kw['source_id']}"
        year = kw.get("year")
        if not ent:
            return None
        return f"{kind}:{ent}" + (f"_{year}" if year else "")

    if kind == "news":
        title = kw.get("title")
        if title:
            return f"news:{_event_fingerprint(title)}"
        url = kw.get("url")
        return f"news:{slugify(url)}" if url else None

    return None


def is_duplicate(
    db: Session,
    content_key: str | None,
    *,
    recency_days: int = DEFAULT_RECENCY_DAYS,
    exclude_proposal_id: int | None = None,
) -> bool:
    """True si ya hay una propuesta viva o un post publicado reciente con esa
    huella. `content_key` None → nunca es duplicado (sin huella, sin red)."""
    if not content_key:
        return False

    from datetime import datetime, timedelta, timezone

    prop_q = (
        db.query(ContentProposal.id)
        .filter(ContentProposal.content_key == content_key)
        .filter(ContentProposal.status.in_(LIVE_PROPOSAL_STATES))
    )
    if exclude_proposal_id is not None:
        prop_q = prop_q.filter(ContentProposal.id != exclude_proposal_id)
    if db.query(prop_q.exists()).scalar():
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(days=recency_days)
    post_exists = (
        db.query(Post.id)
        .filter(Post.content_key == content_key)
        .filter(Post.status == "published")
        .filter(Post.published_at >= cutoff)
        .exists()
    )
    return bool(db.query(post_exists).scalar())
