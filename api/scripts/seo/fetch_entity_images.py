"""Imágenes ilustrativas para entidades que no tienen (Artist, Place, Theme,
Concept), cumpliendo el estándar (imagen + atribución).

- CONCRETAS (Artist, Place): foto CC real vía Wikidata P18 → Wikimedia
  (reutiliza photo_finder._wikidata_photo). Hot-link a upload.wikimedia.org.
- ABSTRACTAS (Theme, Concept): arte IA con la estética «Entre Interiores»
  (pollinations.ai, flux), subido a Cloudinary.

Idempotente: salta las que ya tienen image_url (salvo --force).

Uso:
  python -m scripts.seo.fetch_entity_images --types artist,place
  python -m scripts.seo.fetch_entity_images --types concept --sample 4
  python -m scripts.seo.fetch_entity_images --types theme,concept
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import tempfile
from urllib.parse import quote

import httpx
from sqlalchemy import update

from app.db.models import Artist, Band, Concept, Person, Place, Theme
from app.db.session import SessionLocal
from app.services import wikimedia
from app.services.instagram import cloudinary_upload, photo_finder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CONCRETE = {"artist": Artist, "place": Place, "band": Band}
_ABSTRACT = {"theme": Theme, "concept": Concept}
# Todos los modelos con campo image_url (para el re-alojado a Cloudinary).
_ALL_MODELS = {"artist": Artist, "place": Place, "person": Person,
               "theme": Theme, "concept": Concept, "band": Band}


def _rehost_to_cloudinary(url: str) -> str | None:
    """Descarga una imagen externa y la re-aloja en Cloudinary. Devuelve la
    URL nueva, o None si falla. Evita martillear Wikimedia (429) desde el
    optimizador de Next: el sitio sirve siempre desde Cloudinary."""
    if not url or "res.cloudinary.com" in url:
        return None
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True,
                          headers={"User-Agent": wikimedia.USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("  descarga falló (%s): %s", url[:60], exc)
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        return cloudinary_upload.upload(tmp.name, folder="entreinteriores-art")
    except Exception as exc:  # noqa: BLE001
        logger.warning("  Cloudinary falló: %s", exc)
        return None
    finally:
        os.unlink(tmp.name)


def _rehost(db, types: list[str]) -> None:
    """Re-aloja a Cloudinary las imágenes externas (Wikimedia) de las entidades
    indicadas, conservando la atribución."""
    from sqlalchemy import update
    for t in types:
        model = _ALL_MODELS.get(t)
        if model is None:
            continue
        rows = [e for e in db.query(model).order_by(model.slug).all()
                if e.image_url and "res.cloudinary.com" not in e.image_url]
        logger.info("[rehost %s] %d imágenes externas a re-alojar", t, len(rows))
        for e in rows:
            new = _rehost_to_cloudinary(e.image_url)
            if new:
                db.execute(update(model).where(model.id == e.id).values(image_url=new))
                logger.info("  ✓ %s «%s» -> Cloudinary", t, getattr(e, "name", e.slug))
        db.commit()


def _concrete_image(name: str, *, aliases: list[str] | None = None) -> dict | None:
    """Foto CC real de ESTA entidad: Wikidata P18 y, si falla, búsqueda en Commons.

    Dos guardas que antes no había y que son el origen de los fallos repetidos:

      - **Acreditación**: buscar por nombre devuelve lo que sea (una foto de las
        fiestas de San Isidro, un homónimo argentino, tocino ucraniano para «Salo»).
        Solo se acepta la foto si la procedencia de Commons dice que es esta entidad
        (`image_guard.verify_provenance`). Si no lo dice, se queda sin foto.
      - **Alojamiento**: la URL se re-aloja SIEMPRE en Cloudinary antes de guardarla.
        Un hot-link a Wikimedia se rompe solo en cuanto Commons devuelve 429, y
        limpiarlo después con `--rehost` es una carrera que siempre se pierde.
    """
    from app.services import image_guard

    candidatos: list[dict] = []
    foto = photo_finder._wikidata_photo(name)
    if foto:
        candidatos.append({"url": foto["url"], "credit": foto["credit"],
                           "license": "CC", "source": foto.get("source")})
    wi = wikimedia.search_image(name)
    if wi:
        candidatos.append({
            "url": wi.thumb_url,
            "credit": f"{wi.author or 'Autor desconocido'} · Wikimedia Commons "
                      f"({wi.license_short or 'CC'})",
            "license": wi.license_short or "CC",
            "source": wi.source_page_url,
        })

    for img in candidatos:
        verdict = image_guard.verify_provenance(
            entity_name=name, aliases=aliases, image_url=img["url"],
            source_url=img.get("source"), attribution=img.get("credit"),
            license_=img.get("license"),
        )
        if not verdict.publishable:
            logger.info("  ✗ descartada para «%s»: %s", name, verdict.reason)
            continue
        origen = img["url"]
        hosted = _rehost_to_cloudinary(origen) if image_guard.must_rehost(origen) else origen
        if not hosted:
            logger.warning("  ✗ «%s»: no se pudo re-alojar la foto; no se guarda un hot-link", name)
            continue
        img["url"] = hosted
        img.setdefault("source", origen)
        img["source"] = img.get("source") or origen
        return img
    return None


def _ai_art_url(
    name: str, description: str, seed: int, texture: bool = False,
    ai_prompt: str | None = None,
) -> str | None:
    """Genera arte IA temático y lo sube a Cloudinary. Devuelve la URL.

    `texture=True` pide textura abstracta pura (sin escena ni sujeto
    figurativo): es lo que menos texto basura provoca en Flux, para los
    conceptos en los que el modo figurativo se empeña en meter letras.

    `ai_prompt` permite controlar el sujeto a mano (p.ej. «un dromedario» o
    «una banda de rock tocando en directo»): se le añade la paleta del
    proyecto y los guardas anti-texto.
    """
    desc = (description or "").strip().replace("\n", " ")[:140]
    if ai_prompt:
        prompt = (
            f"{ai_prompt}. deep crimson and charcoal black palette, expressive "
            "painterly digital art, cinematic moody lighting, film grain texture, "
            "no typography, no lettering, no words, no watermark, no caption"
        )
    elif texture:
        prompt = (
            f"pure abstract expressionist texture evoking the idea of {name}, "
            "crimson red and charcoal black, palette knife strokes, dripping "
            "paint, layered grunge texture, film grain, "
            "no figures, no objects, no scene, no horizon, "
            "no typography, no lettering, no words, no watermark"
        )
    else:
        prompt = (
            f"evocative symbolic painting of {name}. {desc} "
            "deep crimson and charcoal black palette, expressive brushwork, "
            "painterly digital art, cinematic moody lighting, film grain texture, "
            "clean wordless composition, untitled, unsigned, "
            "no typography, no lettering, no watermark, no caption, no people"
        )
    url = (
        f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        f"?width=1200&height=900&seed={seed}&model=flux&nologo=true"
    )
    try:
        with httpx.Client(timeout=150.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("  pollinations falló para «%s»: %s", name, exc)
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        return cloudinary_upload.upload(tmp.name, folder="entreinteriores-art")
    except Exception as exc:  # noqa: BLE001
        logger.warning("  Cloudinary falló para «%s»: %s", name, exc)
        return None
    finally:
        os.unlink(tmp.name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--types", default="artist,place,theme,concept",
                    help="Coma-separado: artist,place,theme,concept")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--sample", type=int, default=0,
                    help="Solo procesa N entidades (para revisión).")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--slugs", default="",
                    help="Coma-separado: solo estos slugs (para regenerar puntual).")
    ap.add_argument("--seed-salt", type=int, default=0,
                    help="Desplaza la semilla del arte IA (para regenerar distinto).")
    ap.add_argument("--texture", action="store_true",
                    help="Arte abstracto puro (sin figura): evita el texto de Flux.")
    ap.add_argument("--rehost", action="store_true",
                    help="Re-aloja a Cloudinary las imágenes externas (Wikimedia).")
    ap.add_argument("--ai-art", action="store_true",
                    help="Fuerza arte IA para los --slugs dados (cualquier tipo).")
    ap.add_argument("--ai-prompt", default="",
                    help="Sujeto del arte IA (con --ai-art), p.ej. «un dromedario».")
    args = ap.parse_args()
    types = [t.strip() for t in args.types.split(",") if t.strip()]
    only_slugs = {s.strip() for s in args.slugs.split(",") if s.strip()}

    with SessionLocal() as db:
        if args.rehost:
            _rehost(db, types)
            return
        if args.ai_art:
            if not only_slugs:
                logger.warning("--ai-art requiere --slugs")
                return
            for t in types:
                model = _ALL_MODELS.get(t)
                if model is None:
                    continue
                for e in db.query(model).filter(model.slug.in_(only_slugs)).all():
                    seed = (int(hashlib.md5(e.slug.encode()).hexdigest(), 16)
                            + args.seed_salt) % 1_000_000
                    url = _ai_art_url(e.name, "", seed,
                                      ai_prompt=args.ai_prompt or e.name)
                    if not url:
                        continue
                    db.execute(update(model).where(model.id == e.id).values(
                        image_url=url,
                        image_attribution="Arte generado por IA · Entre Interiores",
                        image_license="propio",
                        image_source_url=None,
                    ))
                    logger.info("  ✓ ai-art %s «%s» → %s", t, e.name, url)
                db.commit()
            return
        for t in types:
            model = _CONCRETE.get(t) or _ABSTRACT.get(t)
            if model is None:
                logger.warning("tipo desconocido: %s", t)
                continue
            rows = db.query(model).order_by(model.slug).all()
            if only_slugs:
                rows = [e for e in rows if e.slug in only_slugs]
            todo = [e for e in rows if args.force or not e.image_url or only_slugs]
            if args.sample:
                todo = todo[: args.sample]
            elif args.limit:
                todo = todo[: args.limit]
            logger.info("[%s] %d a procesar (de %d)", t, len(todo), len(rows))

            for e in todo:
                if t in _CONCRETE:
                    # Una persona se acredita por su nombre artístico o por el de
                    # pila (Commons etiqueta a unos por uno y a otros por el otro).
                    aliases = [a for a in (getattr(e, "stage_name", None),
                                           getattr(e, "full_name", None)) if a]
                    nombre = getattr(e, "name", None) or (aliases[0] if aliases else e.slug)
                    img = _concrete_image(nombre, aliases=aliases)
                    if not img:
                        logger.info("  %s «%s»: sin foto CC acreditada", t, getattr(e, "name", e.slug))
                        continue
                    db.execute(update(model).where(model.id == e.id).values(
                        image_url=img["url"],
                        image_attribution=img["credit"],
                        image_license=img.get("license"),
                        image_source_url=img.get("source"),
                    ))
                    logger.info("  ✓ %s «%s» → %s", t, e.name, img["credit"])
                else:
                    seed = (
                        int(hashlib.md5(e.slug.encode()).hexdigest(), 16)
                        + args.seed_salt
                    ) % 1_000_000
                    url = _ai_art_url(e.name, e.description or "", seed, texture=args.texture)
                    if not url:
                        continue
                    db.execute(update(model).where(model.id == e.id).values(
                        image_url=url,
                        image_attribution="Arte generado por IA · Entre Interiores",
                        image_license="propio",
                        image_source_url=None,
                    ))
                    logger.info("  ✓ %s «%s» → %s", t, e.name, url)
            db.commit()


if __name__ == "__main__":
    main()
