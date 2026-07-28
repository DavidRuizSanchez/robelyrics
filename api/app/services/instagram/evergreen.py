"""Generadores de contenido evergreen para Instagram, anclados al corpus.

A diferencia de las noticias (actualidad efímera), el evergreen es material
intemporal del universo Extremoduro/Robe que SIEMPRE se puede publicar:

  - `quote`      → frases de canciones (verso como contenido principal).
  - `ephemeris`  → aniversarios de discos y cumpleaños de miembros.
  - `anecdote`   → anécdotas y hechos verificados del corpus (De Profundis).
  - `robe_quote` → citas verificadas de Robe (data/robe_quotes.yaml).

Cada generador devuelve una lista de "candidatos" (dicts). NO generan imagen ni
caption: solo proponen el tema. El cron los encola como `proposed` y el admin
los aprueba en el panel; al aprobar, `publisher.prepare` construye imagen+caption.

REGLA DE ORO: todo sale del corpus real. Nunca se inventa un verso, un dato ni
una cita. Por eso cada candidato lleva una fuente y un `content_key` estable
para no repetirse entre semanas.
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
from datetime import date

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, InstagramQueueItem, Line, Person, Song
from app.services.instagram import config

logger = logging.getLogger(__name__)

EVERGREEN_TYPES = ("quote", "ephemeris", "anecdote", "robe_quote", "product")

# Horizonte para generar efemérides con fecha fija (`publish_on`): se proponen
# con antelación y SOLO se publican su día exacto, así que la ventana es amplia.
ANNIVERSARY_HORIZON_DAYS = 120

# Personas que son REFERENCIAS culturales citadas en las letras (no gente del
# universo Extremoduro): no se generan posts de su cumpleaños en la cuenta.
REFERENCE_SLUGS = {"manolete", "camaron", "frank-zappa", "freddie-mercury"}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _data_path(filename: str) -> str | None:
    """Resuelve un fichero de data/ tanto en contenedor (/app/data) como local."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        f"/app/data/{filename}",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", filename)),
        os.path.normpath(os.path.join(here, "..", "..", "..", "..", "data", filename)),
    ):
        if os.path.exists(p):
            return p
    return None


def used_content_keys(db: Session) -> set[str]:
    """`content_key`s ya presentes en la cola (cualquier estado): no se repiten.
    Si el admin descartó algo, tampoco se vuelve a proponer (respeta su decisión)."""
    return set(
        db.execute(
            select(InstagramQueueItem.content_key).where(
                InstagramQueueItem.content_key.is_not(None)
            )
        ).scalars().all()
    )


def _es_verso_decente(text: str) -> bool:
    """Heurística para descartar líneas que no funcionan como frase suelta:
    marcadores de sección, gritos en mayúsculas, fragmentos demasiado cortos."""
    t = (text or "").strip()
    if len(t) < 32 or len(t) > 120:
        return False
    if " " not in t:                      # una sola palabra
        return False
    if t == t.upper():                    # ESTRIBILLO EN MAYÚSCULAS
        return False
    if t[0] in "([" or t.startswith("..."):
        return False
    # Frases que acaban en conjunción/preposición quedan "colgando".
    ultima = t.rstrip(".,;:").split()[-1].lower()
    if ultima in {"y", "o", "que", "de", "la", "el", "con", "en", "a", "su", "un"}:
        return False
    return True


# --------------------------------------------------------------------------- #
# Generadores
# --------------------------------------------------------------------------- #
def gen_quotes(db: Session, count: int, used: set[str]) -> list[dict]:
    """Frases de canciones: el verso ES el contenido. Origen: tabla `lines`."""
    rows = db.execute(
        select(
            Line.id, Line.text,
            Song.title, Album.title, Album.year, Artist.name,
        )
        .join(Song, Line.song_id == Song.id)
        .join(Album, Song.album_id == Album.id)
        .join(Artist, Album.artist_id == Artist.id)
        .where(func.length(Line.text) >= 32, func.length(Line.text) <= 120)
        .order_by(func.random())
        .limit(count * 8)
    ).all()

    out: list[dict] = []
    for line_id, text, song_t, album_t, year, artist in rows:
        key = f"quote:line_{line_id}"
        if key in used or not _es_verso_decente(text):
            continue
        out.append({
            "content_type": "quote",
            "content_key": key,
            "title": text.strip(),
            "category": "Música",
            # El álbum en el summary deja que album_cover lo use de fondo.
            "summary": f"«{song_t}» · {artist} · {album_t} ({year})",
            "source_name": "Entre Interiores · Letras",
            "source_url": None,
        })
        used.add(key)
        if len(out) >= count:
            break
    return out


def _next_anniversary_date(md: tuple[int, int], hoy: date) -> date | None:
    """Fecha del próximo aniversario de (mes, día), o None si no es válida
    (p.ej. 29-feb en año no bisiesto)."""
    mes, dia = md
    try:
        este = date(hoy.year, mes, dia)
    except ValueError:
        return None
    if este < hoy:
        try:
            este = date(hoy.year + 1, mes, dia)
        except ValueError:
            return None
    return este


def gen_ephemerides(db: Session, count: int, used: set[str]) -> list[dict]:
    """Aniversarios de discos (por fecha de lanzamiento) y cumpleaños de
    miembros vivos en el horizonte próximo. Cada uno lleva `publish_on` = su
    fecha exacta: SOLO se publica ese día (no gotea). Devuelve TODOS los que
    caen en la ventana (no se recorta a `count`: cada uno es de su día)."""
    hoy = date.today()
    out: list[dict] = []

    # 1) Aniversarios de disco con fecha exacta → publish_on = el aniversario.
    albums = db.execute(
        select(Album, Artist.name).join(Artist).where(Album.kind == "studio")
    ).all()
    for album, artist in albums:
        if not album.release_date:
            continue
        aniv = _next_anniversary_date(
            (album.release_date.month, album.release_date.day), hoy
        )
        if aniv is None or (aniv - hoy).days > ANNIVERSARY_HORIZON_DAYS:
            continue
        n = aniv.year - album.year
        if n <= 0:
            continue
        key = f"ephemeris:album_{album.slug}_{aniv.year}"
        if key in used:
            continue
        out.append({
            "content_type": "ephemeris",
            "content_key": key,
            "publish_on": aniv,
            "title": f"Hace {n} años: «{album.title}»",
            "category": "Efemérides",
            "summary": (
                f"Un día como hoy de {album.year}, {artist} publicaba "
                f"«{album.title}»."
            ),
            "source_name": "Entre Interiores · Efemérides",
            "source_url": None,
        })
        used.add(key)

    # 2) Aniversario de nacimiento de miembros → publish_on = el día.
    #    El enfoque cambia según esté VIVO o FALLECIDO:
    #      - vivo:      felicitación alegre ("Cumpleaños de X").
    #      - fallecido: homenaje nostálgico. El texto memorial ("le recordamos,
    #        en su memoria") activa el tono SOBRIO en tone.classify → sin emoji
    #        de fuego y con CTA respetuoso.
    persons = db.execute(
        select(Person).where(Person.birth_date.is_not(None))
    ).scalars().all()
    for p in persons:
        if p.slug in REFERENCE_SLUGS:
            continue
        aniv = _next_anniversary_date((p.birth_date.month, p.birth_date.day), hoy)
        if aniv is None or (aniv - hoy).days > ANNIVERSARY_HORIZON_DAYS:
            continue
        nombre = p.stage_name or p.full_name
        edad = aniv.year - p.birth_date.year
        key = f"ephemeris:birth_{p.slug}_{aniv.year}"
        if key in used:
            continue
        bio = (p.bio_short or "").strip()
        if p.death_date is None:
            title = f"Cumpleaños de {nombre}"
            summary = f"Un día como hoy nació {nombre}, que cumple {edad} años. {bio}".strip()
        else:
            title = f"Un día como hoy nació {nombre}"
            summary = (
                f"Hoy {nombre} habría cumplido {edad} años. {bio} "
                "Le recordamos, en su memoria."
            ).strip()
        out.append({
            "content_type": "ephemeris",
            "content_key": key,
            "publish_on": aniv,
            "title": title,
            "category": "Efemérides",
            "summary": summary,
            "source_name": "Entre Interiores · Efemérides",
            "source_url": None,
        })
        used.add(key)

    out.sort(key=lambda c: c["publish_on"])
    return out


def gen_anecdotes(db: Session, count: int, used: set[str]) -> list[dict]:
    """Anécdotas y hechos verificados del corpus (data/instagram_anecdotes.yaml)."""
    path = _data_path("instagram_anecdotes.yaml")
    if not path:
        logger.warning("[evergreen] instagram_anecdotes.yaml no encontrado")
        return []
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    items = list(data.get("anecdotes") or [])
    random.shuffle(items)

    out: list[dict] = []
    for a in items:
        slug = (a.get("slug") or "").strip()
        text = (a.get("text") or "").strip()
        title = (a.get("title") or "").strip()
        if not slug or not text or not title:
            continue
        key = f"anecdote:{slug}"
        if key in used:
            continue
        out.append({
            "content_type": "anecdote",
            "content_key": key,
            "title": title,
            "category": "Curiosidades",
            "summary": text,
            "source_name": a.get("source") or "Entre Interiores",
            "source_url": None,
        })
        used.add(key)
        if len(out) >= count:
            break
    return out


def gen_robe_quotes(db: Session, count: int, used: set[str]) -> list[dict]:
    """Citas verificadas de Robe (data/robe_quotes.yaml, verified: true)."""
    path = _data_path("robe_quotes.yaml")
    if not path:
        logger.warning("[evergreen] robe_quotes.yaml no encontrado")
        return []
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    quotes = [
        q for q in (data.get("quotes") or [])
        if q.get("verified") and (q.get("text") or "").strip()
    ]
    random.shuffle(quotes)

    out: list[dict] = []
    for q in quotes:
        text = q["text"].strip()
        key = f"robe_quote:{hashlib.md5(text.encode()).hexdigest()[:12]}"
        if key in used:
            continue
        out.append({
            "content_type": "robe_quote",
            "content_key": key,
            "title": text,
            "category": "Cultura",
            "summary": f"— Robe. {q.get('source') or ''}".strip(),
            "source_name": q.get("source") or "Robe",
            "source_url": q.get("url") or None,
        })
        used.add(key)
        if len(out) >= count:
            break
    return out


def gen_product(db: Session, count: int, used: set[str]) -> list[dict]:
    """Posts que ENSEÑAN la web (data/instagram_product.yaml).

    Casi todo lo bueno del sitio vive tras el login, así que estos posts son el
    gancho de registro: el CTA manda a /registro, no a la ruta privada (que
    rebotaría al login y dejaría al visitante en la puerta).

    Si falta la captura, se salta la funcionalidad: un post que promete enseñar
    algo y no lo enseña no vale para nada.
    """
    path = _data_path("instagram_product.yaml")
    if not path:
        logger.warning("[evergreen] instagram_product.yaml no encontrado")
        return []
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    items = list(data.get("funcionalidades") or [])
    random.shuffle(items)

    shots_dir = _data_path("product_shots") or ""
    out: list[dict] = []
    for f in items:
        slug = (f.get("slug") or "").strip()
        if not slug:
            continue
        key = f"product:{slug}"
        if key in used:
            continue
        # La pieza puede venir de dos sitios: generada con datos reales por
        # `product_shots.generar()` (lo normal) o una captura de pantalla puesta
        # a mano en data/product_shots/ (para lo que no se puede recomponer,
        # como el karaoke, donde lo que se vende es la interacción).
        captura = ""
        generada = os.path.join(
            config.IMAGES_DIR, "product", (f.get("generada") or "")
        )
        if f.get("generada") and os.path.exists(generada):
            captura = generada
        else:
            estatica = os.path.join(shots_dir, f.get("captura") or "")
            if shots_dir and f.get("captura") and os.path.exists(estatica):
                captura = estatica
        if not captura:
            logger.info("[evergreen] sin pieza para %s, se salta", slug)
            continue
        out.append({
            "content_type": "product",
            "content_key": key,
            "title": f.get("title") or slug,
            "category": "Cultura",
            "summary": (f.get("claim") or "").strip(),
            "detalle": (f.get("detalle") or "").strip(),
            "image_hint": captura,
            "image_kind": "photo",
            "cta": f.get("cta") or "",
            "source_name": "Entre Interiores",
            "source_url": None,
        })
        used.add(key)
        if len(out) >= count:
            break
    return out


# Reparto por defecto del lote semanal (tipo → cuántos proponer).
DEFAULT_MIX = {
    "quote": 6,
    "ephemeris": 4,
    "anecdote": 4,
    "robe_quote": 3,
    # Cuota corta a propósito: como mucho 1 de cada 6 publicaciones enseña la
    # web. Más que eso convierte la cuenta en un folleto.
    "product": 2,
}

_GENERATORS = {
    "quote": gen_quotes,
    "ephemeris": gen_ephemerides,
    "anecdote": gen_anecdotes,
    "robe_quote": gen_robe_quotes,
    "product": gen_product,
}


def generate_batch(db: Session, mix: dict[str, int] | None = None) -> list[dict]:
    """Genera un lote de candidatos evergreen repartido por tipo, deduplicado
    contra todo lo que ya pasó por la cola."""
    mix = mix or DEFAULT_MIX
    used = used_content_keys(db)
    batch: list[dict] = []
    for tipo, n in mix.items():
        gen = _GENERATORS.get(tipo)
        if not gen or n <= 0:
            continue
        try:
            candidatos = gen(db, n, used)
        except Exception as exc:  # noqa: BLE001
            logger.error("[evergreen] generador %s falló: %s", tipo, exc)
            candidatos = []
        logger.info("[evergreen] %s: %d candidatos", tipo, len(candidatos))
        batch.extend(candidatos)
    return batch
