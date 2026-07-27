"""Hero image ÚNICO por post — nunca se repite una imagen entre posts.

Estrategia (decisión de producto): primero una imagen REAL de la entidad
protagonista aún NO usada por otro post/propuesta; si todas están ya usadas, se
genera arte editorial ÚNICO con gpt-image-1 (estilo "Entre Interiores", granate
sobre negro) y se sube a Cloudinary. Siempre se devuelve un ALT descriptivo de la
imagen real (no del título del post) para accesibilidad + SEO.

Regla dura del proyecto: JAMÁS dos posts con la misma foto.
"""
from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import zlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.hero_image import pick_hero_image

logger = logging.getLogger(__name__)


def used_hero_urls(db: Session) -> set[str]:
    """URLs de imagen hero ya empleadas por cualquier Post o ContentProposal."""
    from app.db.models import ContentProposal, Post

    urls: set[str] = set()
    for (u,) in db.execute(select(Post.hero_image_url).where(Post.hero_image_url.isnot(None))):
        urls.add(u)
    for (u,) in db.execute(
        select(ContentProposal.hero_image_url).where(ContentProposal.hero_image_url.isnot(None))
    ):
        urls.add(u)
    return urls


def _seed(subject: str) -> int:
    """Semilla estable (sin aleatoriedad) para variar el estilo del arte IA."""
    return zlib.crc32((subject or "entre interiores").encode("utf-8"))


def _ai_hero(subject: str, seed: int, alt_label: str = "") -> dict | None:
    """Arte editorial ÚNICO con gpt-image-1 subido a Cloudinary. None si no hay
    API key o falla (el caller degrada a sin-imagen, nunca a una repetida).

    `alt_label`: texto legible (título del post) para el ALT; si no se da, cae al
    subject. El prompt de imagen usa el subject (tema) tal cual."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    path = None
    try:
        from app.services.instagram import cloudinary_upload, imaging

        img = imaging._ai_background(subject or "Robe y Extremoduro", seed)
        img = imaging._treat(img, has_photo=False)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            path = fh.name
        img.convert("RGB").save(path, "JPEG", quality=90)
        url = cloudinary_upload.upload(path, folder="entreinteriores-blog")
        label = (alt_label or subject or "").strip()
        return {
            "url": url, "attribution": None, "license": None, "source": None,
            "alt": f"Ilustración editorial de Entre Interiores para «{label}»",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("arte IA de hero falló (%s): %s", subject, exc)
        return None
    finally:
        if path and os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(path)


# Dominios cuyas URLs de imagen NO son heros fiables: widgets/crawlers de redes y
# CDNs que hotlinkean con 403 o devuelven HTML en vez de la imagen. Un hero roto en
# una página pública es peor que un arte IA figurativo — se vetan.
_BAD_IMAGE_HOSTS = (
    "lookaside.instagram.com", "instagram.com", "cdninstagram.com", "fbcdn.net",
    "facebook.com", "fbsbx.com", "twimg.com", "pbs.twimg.com", "tiktokcdn.com",
    "scontent", "pinimg.com",
)


def _rehost_to_cloudinary(url: str) -> str | None:
    """Descarga una foto web y la RE-SUBE a Cloudinary (folder del blog), devolviendo
    la URL `res.cloudinary.com`. Necesario porque Next.js solo optimiza imágenes de
    dominios en `remotePatterns` (wikimedia/cloudinary): una URL externa de un medio,
    aunque cargue con 200, da 400 en `/_next/image` y se ve ROTA. Re-alojarla en
    Cloudinary la hace siempre renderizable y estable (sin hotlink frágil). None si
    la descarga/subida falla."""
    import contextlib
    import tempfile

    path = None
    try:
        from app.services.instagram import cloudinary_upload, imaging
        img = imaging._fetch_image(url)  # valida que es imagen de verdad
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            path = fh.name
        img.convert("RGB").save(path, "JPEG", quality=88)
        return cloudinary_upload.upload(path, folder="entreinteriores-blog")
    except Exception as exc:  # noqa: BLE001
        logger.info("hero: re-host a Cloudinary falló (%s): %s", url[:60], exc)
        return None
    finally:
        if path and os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(path)


def _web_photo_hero(
    entities: list[dict] | None, subject: str, alt_label: str, used: set[str]
) -> dict | None:
    """Foto REAL del sujeto por búsqueda web (mismo motor que Instagram:
    Google Images vía DataForSEO + respaldo Wikimedia/Openverse CC). La foto web se
    RE-ALOJA en Cloudinary para que Next la renderice (los dominios de medios no
    están en `remotePatterns` → se verían rotas). Deduplicada por URL. None si no
    hay ninguna usable → el caller cae al arte IA figurativo (nunca a un hero roto).

    Prioriza fotos originales relacionadas con el tema del post antes de caer al
    arte IA. Ancla la query al universo Robe/Extremoduro para evitar homónimos."""
    try:
        from app.services.instagram import photo_finder

        label = _protagonist_label(entities) or (alt_label or subject or "").strip()
        if not label:
            return None
        topic = {
            "title": alt_label or subject,
            # Query desambiguada del sujeto (photo_finder ya reancla a la banda si
            # no encuentra algo relevante).
            "image_search": f"{label} Extremoduro Robe Iniesta",
            "image_query": label,
        }
        chosen = photo_finder.find(topic, exclude=used)
        if not chosen:
            return None
        # Prueba la imagen full y, si no, el thumbnail. Vetos de dominio inestable;
        # las locales sirven tal cual, las externas se re-alojan en Cloudinary.
        for url in (chosen.get("url"), chosen.get("thumb")):
            if not url or url in used:
                continue
            if any(h in url.lower() for h in _BAD_IMAGE_HOSTS):
                continue
            hosted = url if url.startswith("/") else _rehost_to_cloudinary(url)
            if not hosted or hosted in used:
                continue
            credit = (chosen.get("credit") or "").strip()
            return {
                "url": hosted,
                "attribution": credit or None,
                "license": None,
                "source": url,
                "alt": f"Fotografía relacionada con «{(alt_label or subject or label).strip()}»",
            }
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("foto web de hero falló (%s): %s", subject, exc)
        return None


def _protagonist_label(entities: list[dict] | None) -> str:
    """Etiqueta legible de la entidad protagonista del post (la primera con label)."""
    for e in entities or []:
        lbl = (e.get("label") or e.get("name") or "").strip()
        if lbl:
            return lbl
    return ""


def build_unique_hero(
    db: Session,
    entities: list[dict] | None,
    subject: str,
    *,
    allow_ai: bool = True,
    used: set[str] | None = None,
    alt_label: str = "",
) -> dict | None:
    """Devuelve {url, alt, attribution, license, source} ÚNICO para el post, o None.

    1) Imagen REAL de la entidad no usada aún (dedup duro).
    2) Foto REAL del sujeto por búsqueda web (Google Images/Wikimedia), deduplicada.
    3) Si no hay foto libre → arte editorial IA figurativo único (si `allow_ai`).

    `alt_label`: título legible del post para el ALT del arte IA (mejor que el
    slug de keyword). El `subject` (tema) alimenta el prompt de imagen.
    """
    from app.services import hero_guard

    used = used if used is not None else used_hero_urls(db)
    subj = subject or alt_label
    # 1) Imagen curada de la entidad protagonista, GATED por relevancia: una foto
    #    correcta de otra entidad (p.ej. Robe en un post de Rosendo) se rechaza.
    img = pick_hero_image(db, entities, used=used, subject=subj)
    if img and hero_guard.verify_hero(img, subject=subj, entities=entities).ok:
        return img
    # 2) Foto real por web del sujeto, también GATED (fuente no fiable → visión).
    web = _web_photo_hero(entities, subject, alt_label, used)
    if web and hero_guard.verify_hero(web, subject=subj, entities=entities).ok:
        return web
    # 3) Arte editorial IA propio: on-topic por construcción (se genera DEL sujeto),
    #    así una foto web irrelevante NUNCA gana; se degrada a arte propio.
    if allow_ai:
        ai = _ai_hero(subject, _seed(subject), alt_label=alt_label)
        if ai and ai["url"] not in used:
            return ai
    return None
