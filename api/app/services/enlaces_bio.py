"""La página de enlaces de la bio de Instagram (`/enlaces`).

Instagram solo deja un puñado de enlaces en la bio y ninguno en los pies, así que
cada «link en la bio» manda a la gente a buscar. Esta página enseña los últimos
posts publicados, con su imagen, y cada uno lleva a la página de la web de la que
habla: el artículo, la canción del verso o del clip, el disco de la efeméride, la
ficha de la persona o el registro, si el post enseña una función de la web.

Solo sale lo que tiene destino PROPIO y PUBLICADO. Un post sin página nuestra (una
noticia ajena sin artículo, una anécdota) no se enseña: un enlace que no lleva a
ningún sitio es peor que no ponerlo. El destino se deriva de la BD con las mismas
reglas que el resto de la web (`url_resolver`), nunca se guarda a mano.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    InstagramQueueItem,
    Line,
    Person,
    Post,
    VideoClip,
)
from app.services import url_resolver

REGISTRO = "/registro"

# Lo que pone el botón de cada tipo de destino.
ETIQUETA = {
    "post": "Leer el artículo",
    "song": "La canción",
    "album": "El disco",
    "person": "Su ficha",
    "registro": "Pruébalo gratis",
}


@dataclass(frozen=True)
class Enlace:
    id: int
    titulo: str
    imagen: str | None
    destino: str
    etiqueta: str
    tipo: str
    publicado: datetime | None


def miniatura(url: str | None, lado: int = 480) -> str | None:
    """Miniatura cuadrada de Cloudinary; de un vídeo, su primer fotograma.

    Las piezas de IG van en 4:5 y los clips en 9:16: en una cuadrícula se recortan
    al centro, igual que en el perfil de Instagram. Lo que no es de Cloudinary
    se devuelve tal cual.
    """
    if not url or "res.cloudinary.com" not in url or "/upload/" not in url:
        return url
    ajuste = f"c_fill,g_auto,w_{lado},h_{lado},f_auto,q_auto"
    if "/video/upload/" in url:
        url = re.sub(r"\.(mp4|mov|webm)(\?.*)?$", ".jpg", url)
        ajuste = "so_1," + ajuste
    return url.replace("/upload/", f"/upload/{ajuste}/", 1)


def _imagen(item: InstagramQueueItem) -> str | None:
    medios = sorted(item.media or [], key=lambda m: m.position)
    if medios:
        primero = medios[0]
        if primero.kind == "video":
            return miniatura(primero.cover_url or primero.url)
        return miniatura(primero.url)
    return miniatura(item.image_url)


def _titulo(item: InstagramQueueItem) -> str:
    # La raya larga no se escribe en la web (`voice.py`): los títulos de los clips
    # la traen de la procedencia («Robe, desde el escenario — Vigo, …»).
    return re.sub(r"\s+[—–]\s+", " · ", (item.title or "").strip())


def destino(db: Session, cat: url_resolver.DbCatalog, item: InstagramQueueItem
            ) -> tuple[str, str] | None:
    """(ruta, tipo) de la página de la que habla el post, o None si no tiene."""
    clave = item.content_key or ""

    def entidad(tipo: str, ident: int | None) -> tuple[str, str] | None:
        if not ident:
            return None
        if tipo != "post" and not cat._publicado(tipo, ident):
            return None
        ruta = cat.canonical_path(tipo, ident)
        return (ruta, tipo) if ruta else None

    if item.blog_post_id:
        post = db.get(Post, item.blog_post_id)
        if post and post.status == "published":
            return entidad("post", post.id)
        return None

    if item.content_type == "product":
        return REGISTRO, "registro"

    if item.content_type == "quote" and clave.startswith("quote:line_"):
        try:
            linea = db.get(Line, int(clave.removeprefix("quote:line_")))
        except ValueError:
            return None
        return entidad("song", linea.song_id if linea else None)

    if item.content_type == "clip":
        song_id = db.execute(
            select(VideoClip.song_id).where(VideoClip.queue_item_id == item.id)
        ).scalars().first()
        return entidad("song", song_id)

    if item.content_type == "ephemeris":
        # ephemeris:<album|round|birth>_<slug>_<año>
        m = re.fullmatch(r"ephemeris:(album|round|birth)_(.+)_\d{4}", clave)
        if not m:
            return None
        clase, slug = m.groups()
        if clase == "birth":
            ids = db.execute(select(Person.id).where(Person.slug == slug)).scalars().all()
            return entidad("person", ids[0]) if len(ids) == 1 else None
        # Un slug de disco que exista en los dos artistas no se adivina.
        ids = db.execute(select(Album.id).where(Album.slug == slug)).scalars().all()
        return entidad("album", ids[0]) if len(ids) == 1 else None

    return None


def ultimos(db: Session, limite: int = 24, ventana: int = 120) -> list[Enlace]:
    """Los `limite` posts publicados más recientes que llevan a una página nuestra.

    Recorre como mucho los `ventana` últimos publicados: si de ahí no salen
    bastantes, la página enseña menos, no posts de hace meses.
    """
    cat = url_resolver.DbCatalog(db)
    items = db.execute(
        select(InstagramQueueItem)
        .where(InstagramQueueItem.status == "published",
               InstagramQueueItem.published_at.is_not(None))
        .order_by(InstagramQueueItem.published_at.desc())
        .limit(ventana)
    ).scalars().all()

    enlaces: list[Enlace] = []
    for item in items:
        hallado = destino(db, cat, item)
        if not hallado:
            continue
        ruta, tipo = hallado
        enlaces.append(Enlace(
            id=item.id, titulo=_titulo(item), imagen=_imagen(item), destino=ruta,
            etiqueta=ETIQUETA[tipo], tipo=tipo, publicado=item.published_at,
        ))
        if len(enlaces) >= limite:
            break
    return enlaces
