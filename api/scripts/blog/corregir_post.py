"""Corrige un post publicado que afirmaba lo que su fuente no dice.

Nació con el post #65 («Flores Amarillas 2027», 12-10-2026), publicado con un
cartel inventado. El `PUT /admin/posts` del panel cambia el texto, pero no guarda
copia ni revalida la web, y no comprueba nada. Este script sí:

  1. Lee la versión corregida de un JSON (title, excerpt, body_md, meta_title,
     meta_description y, opcional, hero) y las fuentes re-descargadas.
  2. La pasa por `source_grounding` contra esas fuentes, por `source_guard` y por
     `lyric_guard`. Si algo bloquea, no aplica nada.
  3. Guarda la versión anterior en `content_revisions` (se puede deshacer).
  4. Aplica, re-aloja el hero en Cloudinary y revalida /blog y la URL del post.

Uso:
    python -m scripts.blog.corregir_post --post-id 65 --version v.json --fuentes f.json
    python -m scripts.blog.corregir_post ... --apply
    python -m scripts.blog.corregir_post ... --apply --descartar-propuesta 533

`--fuentes`: JSON con una lista de {"url", "text"} (lo que devuelve
`article_extract.fetch_article`), más un `extra` opcional con texto transcrito
(p.ej. un cartel oficial que solo existe como imagen).
"""
from __future__ import annotations

import argparse
import difflib
import json
import logging
import sys

from app.db.models import ContentProposal, ContentRevision, Post
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CAMPOS = ("title", "excerpt", "body_md", "meta_title", "meta_description")


def _texto_fuentes(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as fh:
        datos = json.load(fh)
    if isinstance(datos, dict):
        partes = [x.get("text") or "" for x in datos.get("fuentes", [])]
        partes.append(datos.get("extra") or "")
    else:
        partes = [x.get("text") or "" for x in datos]
    return "\n\n".join(p for p in partes if p.strip())


def comprobar(db, version: dict, fuente: str) -> list[str]:
    """Motivos por los que la versión nueva NO se puede aplicar (vacío = limpia)."""
    from app.services import source_grounding
    from app.services.lyric_guard import check_lyrics
    from app.services.source_guard import fuentes_nombradas, nombres_de_fuentes

    body = version["body_md"]
    motivos: list[str] = []
    v = source_grounding.revisar(body, fuente, casa=source_grounding.nombres_de_casa(db))
    if not v.ok:
        motivos.append(v.motivo(10))
    nombradas = fuentes_nombradas(body, nombres_de_fuentes(db))
    if nombradas:
        motivos.append("nombra fuentes externas: " + " · ".join(f for f, _ in nombradas[:3]))
    letras = check_lyrics(db, body)
    if letras.blocking:
        motivos.append("cita versos que no existen: "
                       + "; ".join(x.quote[:60] for x in letras.blocking))
    return motivos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--post-id", type=int, required=True)
    ap.add_argument("--version", required=True, help="JSON con la versión corregida")
    ap.add_argument("--fuentes", required=True, help="JSON con las fuentes re-descargadas")
    ap.add_argument("--apply", action="store_true", help="sin esto, solo enseña el cambio")
    ap.add_argument("--descartar-propuesta", type=int, default=None,
                    help="propuesta que queda fundida en este post (pasa a discarded)")
    ap.add_argument("--motivo", default="corrección de veracidad: afirmaba lo que su fuente no dice")
    args = ap.parse_args()

    db = SessionLocal()
    post = db.get(Post, args.post_id)
    if not post:
        logger.error("no existe el post %s", args.post_id)
        return 1
    with open(args.version, encoding="utf-8") as fh:
        version = json.load(fh)
    fuente = _texto_fuentes(args.fuentes)

    motivos = comprobar(db, version, fuente)
    for campo in CAMPOS:
        if campo in version and version[campo] != getattr(post, campo):
            print(f"\n=== {campo} ===")
            antes = (getattr(post, campo) or "").splitlines()
            despues = (version[campo] or "").splitlines()
            print("\n".join(difflib.unified_diff(antes, despues, "antes", "después", lineterm="")))
    if version.get("hero"):
        print(f"\n=== hero ===\n{post.hero_image_source_url} → {version['hero'].get('source')}")
    if motivos:
        print("\n✗ NO se puede aplicar:\n- " + "\n- ".join(motivos))
        return 2
    print("\n✓ La versión nueva pasa source_grounding, source_guard y lyric_guard.")
    if not args.apply:
        print("(dry-run: no se ha tocado nada; añade --apply)")
        return 0

    path = f"/blog/{post.slug}"
    db.add(ContentRevision(
        target_kind="post", target_id=post.id, path=path, body_md=post.body_md or "",
        meta_title=post.meta_title, meta_description=post.meta_description, h1=post.title,
        reason=args.motivo,
    ))
    for campo in CAMPOS:
        if campo in version:
            setattr(post, campo, version[campo])

    hero = version.get("hero")
    if hero:
        from app.services.blog_hero import _rehost_to_cloudinary
        from app.services.hero_io import apply_hero

        alojada = _rehost_to_cloudinary(hero["source"])
        if not alojada:
            db.rollback()
            logger.error("no se pudo re-alojar el hero (%s): no se aplica nada", hero["source"])
            return 3
        apply_hero(post, {**hero, "url": alojada})

    if args.descartar_propuesta:
        prop = db.get(ContentProposal, args.descartar_propuesta)
        if prop and prop.status not in ("used", "discarded"):
            prop.status = "discarded"
            logger.info("propuesta #%s → discarded (fundida en el post #%s)", prop.id, post.id)
    db.commit()

    from app.services.publishing import revalidate_paths
    revalidate_paths(["/blog", path], tags=["posts"])
    logger.info("✓ post #%s corregido y revalidado: %s", post.id, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
