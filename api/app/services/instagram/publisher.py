"""Orquestador de publicación en Instagram.

prepare:  tema → comentario editorial + verso de Robe + imagen → caption +
          fichero de imagen (sin publicar todavía).
publish:  sube la imagen a Cloudinary → publica vía Graph API → registra el
          resultado en `instagram_queue`.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    InstagramQueueItem,
    InstagramQueueMedia,
    Line,
    Person,
    Post,
    Song,
)
from app.services.instagram import (
    album_cover,
    captions,
    carousel,
    cloudinary_upload,
    config,
    editorial,
    graph_api,
    imaging,
    photo_finder,
    robe_quote,
    tone,
)
from app.services.instagram.evergreen import EVERGREEN_TYPES

logger = logging.getLogger(__name__)

BLOG_BASE_URL = f"{config.SITE_URL}/blog"


def _topic_from_item(db: Session, item: InstagramQueueItem) -> dict:
    """Construye el dict de tema que consumen editorial / imaging / captions."""
    topic = {
        "title": item.title,
        "category": item.category or "Actualidad",
        "summary": item.summary or "",
        "source": item.source_name or "",
        "url": item.source_url or "",
        # Semilla estable de la rotación de moldes del caption: re-preparar un
        # item no debe cambiarle el texto por sorpresa.
        "content_key": item.content_key or "",
    }
    if item.blog_post_id:
        post = db.get(Post, item.blog_post_id)
        if post is not None:
            topic["category"] = "Blog"
            topic["url"] = f"{BLOG_BASE_URL}/{post.slug}"
            topic["image_hint"] = post.hero_image_url or ""
            if not topic["summary"]:
                topic["summary"] = post.excerpt or ""
    return topic


def _sin_desambiguador(song: str, album: str) -> str:
    """«Emparedado (Rock Transgresivo)» → «Emparedado».

    Los dos discos gemelos («Rock transgresivo» y «Tú en tu casa, nosotros en la
    hoguera») comparten canciones, y en el catálogo se desambiguan poniendo el
    disco entre paréntesis. Eso es interno: en un caption el nombre de la canción
    es el de la canción, y el disco ya va aparte.

    Solo se recorta si el paréntesis coincide con el título del álbum — así no se
    toca ningún título que lleve paréntesis de verdad.
    """
    s, a = (song or "").strip(), (album or "").strip()
    if not s.endswith(")") or "(" not in s or not a:
        return s
    base, _, dentro = s.rpartition("(")
    if dentro.rstrip(")").strip().casefold() == a.casefold():
        return base.strip()
    return s


def _corpus_context(db: Session, item: InstagramQueueItem) -> dict:
    """Datos ESTRUCTURADOS del corpus para rellenar los moldes del caption.

    El `summary` de un evergreen viene ya formateado («canción» · artista · disco
    (año)), y parsearlo sería frágil. Aquí se vuelve a la fuente: el
    `content_key` identifica la fila exacta de la que salió el candidato, así que
    se releen los campos de BD. Si algo no está, se omite la clave y el molde que
    la necesite queda descartado — nunca se rellena con un valor plausible.

    NOTA: no se expone autoría. Robe es el letrista de casi todo, pero no de todo
    («Ama, ama y ensancha el alma» es un poema de Manolo Chinato), y un molde que
    afirmara "esto lo escribió Robe" mentiría en esos casos.
    """
    key = item.content_key or ""
    ctx: dict = {}

    if key.startswith("quote:line_"):
        try:
            line_id = int(key.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return ctx
        row = db.execute(
            select(Song.title, Album.title, Album.year, Artist.name)
            .select_from(Line)
            .join(Song, Line.song_id == Song.id)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
            .where(Line.id == line_id)
        ).first()
        if row:
            ctx["song"], ctx["album"], ctx["year"], ctx["artist"] = row
            ctx["song"] = _sin_desambiguador(ctx["song"], ctx["album"])

    elif key.startswith("ephemeris:album_"):
        slug = key[len("ephemeris:album_"):].rsplit("_", 1)[0]
        row = db.execute(
            select(Album.title, Album.year, Artist.name)
            .join(Artist, Album.artist_id == Artist.id)
            .where(Album.slug == slug)
        ).first()
        if row:
            ctx["album"], ctx["year"], ctx["artist"] = row

    elif key.startswith("ephemeris:birth_"):
        slug = key[len("ephemeris:birth_"):].rsplit("_", 1)[0]
        person = db.execute(
            select(Person).where(Person.slug == slug)
        ).scalar_one_or_none()
        if person is not None:
            ctx["person"] = person.stage_name or person.full_name
            ctx["is_memorial"] = person.death_date is not None

    return ctx


def _clean_credit(raw: str) -> str:
    """Pasa una atribución en markdown (pensada para la web) a texto plano apto
    para el caption de Instagram: sin markdown, sin enlaces y sin raya larga."""
    txt = (raw or "").strip()
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)   # [texto](url) -> texto
    txt = txt.replace("*", "").replace("_", "")
    txt = re.sub(r"\s*[—–]\s*", " · ", txt)              # raya larga -> punto medio
    txt = re.sub(r"^\s*foto:\s*", "", txt, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", txt).strip(" ·")


def _apply_person_photo(
    db: Session, item: InstagramQueueItem, topic: dict
) -> None:
    """Para una efeméride de persona, usa la foto curada de su ficha en la web.

    El `content_key` de los cumpleaños/aniversarios natales es
    `ephemeris:birth_<slug>_<año>`. Si la persona tiene `image_url`, se reusa esa
    misma imagen (la que ya sale en /personas/<slug>): garantiza que la cara es
    la correcta (sin homónimos) y respeta su atribución CC.
    """
    key = item.content_key or ""
    prefix = "ephemeris:birth_"
    if not key.startswith(prefix):
        return
    slug = key[len(prefix):].rsplit("_", 1)[0]
    if not slug:
        return
    person = db.execute(
        select(Person).where(Person.slug == slug)
    ).scalar_one_or_none()
    if person is None or not person.image_url:
        return
    url = person.image_url
    if url.startswith("/"):
        url = config.SITE_URL + url
    topic["image_hint"] = url
    topic["image_kind"] = "photo"
    attribution = _clean_credit(person.image_attribution or "")
    if attribution:
        lic = (person.image_license or "").strip()
        if lic and lic.lower() not in attribution.lower():
            attribution += f" · {lic}"
        topic["image_credit"] = attribution
    logger.info("[IG] efeméride de %s → foto de ficha %s", slug, url[:60])


def prepare(db: Session, item: InstagramQueueItem) -> InstagramQueueItem:
    """Genera imagen y caption para un item de la cola (sin publicar)."""
    topic = _topic_from_item(db, item)
    is_blog = item.content_type == "blog" or topic.get("category") == "Blog"
    is_evergreen = item.content_type in EVERGREEN_TYPES

    # Contexto para los moldes del caption: de qué tipo es y qué datos reales del
    # corpus hay detrás. Sin esto, `captions` solo tendría texto ya formateado.
    topic["content_type"] = item.content_type
    topic["corpus"] = _corpus_context(db, item)

    # El tono (sobrio vs neutral) gobierna CTA, emoji y prompt editorial.
    topic["tone"] = tone.classify(
        topic.get("title", ""), topic.get("summary", "")
    )

    if is_evergreen:
        # Evergreen: el contenido (verso/efeméride/anécdota/cita) ya es final y
        # sale del corpus verificado. NO se reescribe con IA (anti-alucinación)
        # ni se busca foto de prensa. Imagen, por prioridad:
        #   1) Portada del disco si el texto lo menciona (versos, efeméride de
        #      disco): el arte del propio disco al que pertenece.
        #   2) Efeméride de una PERSONA (cumpleaños/aniversario natal): SU foto
        #      curada de la ficha de la web (misma imagen, sin homónimos).
        #   3) Si no, arte temático (IA) afín a la categoría.
        cover = album_cover.find(db, topic)
        if cover:
            topic["image_hint"] = cover["url"]
            topic["image_kind"] = "cover"
        else:
            _apply_person_photo(db, item, topic)
        # El contenido se basta solo: sin verso ornamental (evita duplicarlo en
        # los posts de frase, donde el verso YA es el titular).
        topic["verse"] = {}
    else:
        # Las noticias se reescriben con voz editorial propia (sin citar al
        # medio); los posts del blog ya traen su texto y su imagen destacada.
        if not is_blog:
            editorial.enrich(topic)
            # Fuente de imagen por prioridad:
            #   1) Portada del disco si el tema trata sobre uno de la discografía.
            #   2) Foto CC del protagonista real (Wikimedia/Openverse) por entidad.
            #   3) (en imaging) arte IA temático como último recurso.
            cover = album_cover.find(db, topic)
            if cover:
                topic["image_hint"] = cover["url"]
                topic["image_kind"] = "cover"
            else:
                # Créditos de las fotos recientes: para no repetir imagen.
                recent_credits = {
                    m.group(1).strip()
                    for c in db.execute(
                        select(InstagramQueueItem.caption)
                        .where(
                            InstagramQueueItem.caption.is_not(None),
                            InstagramQueueItem.id != item.id,
                        )
                        .order_by(InstagramQueueItem.id.desc())
                        .limit(12)
                    ).scalars().all()
                    if c and (m := re.search(r"📷\s*(.+)", c))
                }
                foto = photo_finder.find(topic, exclude=recent_credits)
                if foto:
                    topic["image_hint"] = foto["url"]
                    topic["image_hint_thumb"] = foto.get("thumb") or ""
                    topic["image_credit"] = foto.get("credit") or ""
                    topic["image_kind"] = "photo"

        # Verso afín al tema (se reutiliza en imagen y caption, así coinciden).
        # Se excluyen los versos usados en los últimos posts para no repetirlos.
        _t = topic.get("headline") or topic.get("title") or ""
        _b = topic.get("caption_body") or topic.get("summary") or ""
        recent_caps = db.execute(
            select(InstagramQueueItem.caption)
            .where(InstagramQueueItem.caption.is_not(None), InstagramQueueItem.id != item.id)
            .order_by(InstagramQueueItem.id.desc())
            .limit(6)
        ).scalars().all()
        recent_verses = {
            m.group(1)
            for c in recent_caps
            if (m := re.search(r"«([^»]+)»", c or ""))
        }
        topic["verse"] = robe_quote.find_verse(
            db, f"{_t}. {_b}", exclude_lines=recent_verses
        ) or {}

    # Formato: carrusel si el tema da para ello, foto única en cualquier otro
    # caso (que sigue siendo el camino por defecto). `carousel.plan` devuelve
    # None cuando no hay material verificado suficiente.
    quiere_carrusel = config.CAROUSEL_ENABLED or item.media_type == "CAROUSEL"
    specs = carousel.plan(topic, item.content_type) if quiere_carrusel else None
    if specs:
        paths, used_hero = carousel.render(topic, specs, slot=item.slot or 1)
        item.media_type = "CAROUSEL"
    else:
        path, used_hero = imaging.generate(topic, slot=item.slot or 1)
        paths, specs = [path], [{"layout": "cover"}]
        item.media_type = "IMAGE"

    # Solo se acredita la foto si finalmente se usó una imagen real con
    # licencia; si la generación cayó al fondo IA, no hay crédito que poner.
    if not used_hero:
        topic.pop("image_credit", None)

    _sync_media(db, item, paths, specs)
    item.image_path = paths[0]      # espejo de la diapositiva 0
    item.caption = captions.build(db, topic)
    item.status = "prepared"
    item.error = None
    db.commit()
    return item


def _sync_media(
    db: Session, item: InstagramQueueItem, paths: list[str], specs: list[dict]
) -> None:
    """Reescribe las filas de media del item con las rutas recién generadas."""
    item.media.clear()          # delete-orphan limpia las anteriores
    db.flush()
    for i, ruta in enumerate(paths):
        rol = (specs[i].get("layout") if i < len(specs) else None) or "body"
        item.media.append(
            InstagramQueueMedia(position=i, kind="image", role=rol, local_path=ruta)
        )


def _media_lista(item: InstagramQueueItem) -> bool:
    """¿Están TODAS las piezas en disco?

    `IMAGES_DIR` vive en /tmp y es efímero. Con una sola imagen daba igual
    (se regeneraba), pero con un carrusel puede sobrevivir un subconjunto y
    publicarse mutilado o con las diapositivas desordenadas. Si falta una, se
    regenera el carrusel entero.
    """
    if not item.media:
        return bool(item.image_path and os.path.exists(item.image_path))
    return all(m.local_path and os.path.exists(m.local_path) for m in item.media)


def publish(
    db: Session, item: InstagramQueueItem, dry_run: bool = False
) -> InstagramQueueItem:
    """Publica un item ya preparado (lo prepara si hace falta)."""
    if not _media_lista(item):
        prepare(db, item)

    if dry_run:
        item.status = "prepared"
        db.commit()
        logger.info("[DRY-RUN] item %s listo (no se publica).", item.id)
        return item

    # Verificar token Y que la cuenta sea alcanzable (no solo el scope).
    ok, msg, _ = graph_api.connection_is_healthy()
    if not ok:
        item.status = "failed"
        item.error = msg
        db.commit()
        logger.error("[IG] conexión no saludable para publicar: %s", msg)
        return item

    # Subir a Cloudinary (la Graph API exige URLs públicas). Se hace commit de
    # las URLs ANTES de llamar a Meta: si la publicación falla, reintentar no
    # tiene que volver a subir nada.
    piezas = sorted(item.media, key=lambda m: m.position) or []
    try:
        if piezas:
            for m in piezas:
                m.url = cloudinary_upload.upload(m.local_path)
        else:  # item antiguo, anterior a la tabla de media
            item.image_url = cloudinary_upload.upload(item.image_path)
    except Exception as exc:  # noqa: BLE001
        item.status = "failed"
        item.error = f"Cloudinary: {exc}"
        db.commit()
        logger.error("[IG] subida a Cloudinary falló: %s", exc)
        return item
    if piezas:
        item.image_url = piezas[0].url      # espejo de la diapositiva 0
    db.commit()

    urls = [m.url for m in piezas if m.url] or [item.image_url]
    if item.media_type == "CAROUSEL" and len(urls) >= graph_api.MIN_CAROUSEL_ITEMS:
        media_id, result_msg = graph_api.post_carousel(urls, item.caption or "")
    else:
        media_id, result_msg = graph_api.post_photo(urls[0], item.caption or "")
    if media_id:
        item.status = "published"
        item.ig_media_id = media_id
        item.published_at = datetime.now(timezone.utc)
        item.error = None
        logger.info("[IG] ✅ item %s publicado · media_id=%s", item.id, media_id)
    else:
        item.status = "failed"
        item.error = result_msg
        logger.error("[IG] ❌ item %s falló: %s", item.id, result_msg)
    db.commit()
    return item


def next_pending(db: Session) -> InstagramQueueItem | None:
    """Siguiente item del GOTEO: orden manual (`position`) primero; luego slot
    (blog primero), día y antigüedad. Excluye el contenido con momento fijado
    (`publish_on` de efeméride o `publish_at` programado a mano): ese no gotea,
    sale a su hora vía `due_pinned`."""
    return db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status.in_(("pending", "prepared")),
            InstagramQueueItem.publish_on.is_(None),
            InstagramQueueItem.publish_at.is_(None),
        )
        .order_by(
            InstagramQueueItem.position,
            InstagramQueueItem.slot,
            InstagramQueueItem.day,
            InstagramQueueItem.created_at,
        )
        .limit(1)
    ).scalar_one_or_none()


def due_pinned(db: Session) -> list[InstagramQueueItem]:
    """Items con momento fijado que YA toca publicar, al margen del cuentagotas.

    Dos formas de fijar el momento, y las dos vencen aquí:
      - `publish_on` (efeméride): su día exacto, sin hora.
      - `publish_at`  (programado a mano en el panel): fecha y hora concretas;
        vence cuando ese instante ya pasó, así que un post programado para una
        hora en la que el cron no corría sale en la pasada siguiente en vez de
        perderse.
    """
    today = date.today()
    ahora = datetime.now(timezone.utc)
    return db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status.in_(("pending", "prepared")),
            or_(
                InstagramQueueItem.publish_on == today,
                InstagramQueueItem.publish_at <= ahora,
            ),
        )
        .order_by(InstagramQueueItem.position, InstagramQueueItem.created_at)
    ).scalars().all()
