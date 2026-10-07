"""Enlaza el post viejo de conciertos con el estudio del repertorio. Idempotente.

    python -m scripts.blog.link_estudio_post_conciertos            # dry-run
    python -m scripts.blog.link_estudio_post_conciertos --apply

`el-fenomeno-insuperable-de-los-conciertos-de-extremoduro-y-robe` cuenta que La
ley innata se tocaba entera abriendo con «Dulce introducción al caos». El estudio
tiene el dato que lo sostiene: en los 107 conciertos de 2008-2014 sonó en el
96,3 % (`data/estudio/SOURCES.md`, tabla del índice corregido). Se añade UNA
frase con UN enlace, a la sección exacta.

Cirugía, no regeneración: si la frase ancla no está tal cual, no toca nada. El
cuerpo nuevo pasa por `guard_internal_links`, que tiene que dejar el enlace vivo
(`ESTUDIO_SLUGS`); si lo desenlazara, aborta.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.publishing import _revalidate_next
from app.services.url_resolver import guard_internal_links

SLUG = "el-fenomeno-insuperable-de-los-conciertos-de-extremoduro-y-robe"
ANCLA = "obligando al público a escuchar la obra entera como una sinfonía."
ENLACE = "/estudios/repertorio-en-directo-extremoduro-robe#extremoduro-vs-robe"
FRASE = (
    " Y aquel arranque se volvió fijo: en los conciertos documentados de 2008 a 2014, "
    "«Dulce introducción al caos» sonó en el 96,3 %, según "
    f"[el estudio del repertorio en directo]({ENLACE})."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        post = db.execute(select(Post).where(Post.slug == SLUG)).scalar_one_or_none()
        if post is None:
            print(f"no existe el post {SLUG}", file=sys.stderr)
            return 1
        if ENLACE.split("#")[0] in post.body_md:
            print("ya enlaza al estudio: nada que hacer")
            return 0
        if post.body_md.count(ANCLA) != 1:
            print(f"la frase ancla aparece {post.body_md.count(ANCLA)} veces: no se toca",
                  file=sys.stderr)
            return 1

        nuevo = post.body_md.replace(ANCLA, ANCLA + FRASE)
        guard = guard_internal_links(db, nuevo)
        if ENLACE.split("#")[0] not in guard.body_md:
            print(f"la guarda desenlazó el estudio: {guard.unlinked}", file=sys.stderr)
            return 1

        i = guard.body_md.find(ANCLA)
        print("ANTES:", post.body_md[i - 120:i + len(ANCLA)])
        print("DESPUÉS:", guard.body_md[i - 120:i + len(ANCLA) + len(FRASE) + 10])
        if not args.apply:
            print("\n(dry-run; repetir con --apply)")
            return 0

        post.body_md = guard.body_md
        db.commit()
        _revalidate_next(SLUG)
        print(f"aplicado y revalidado /blog/{SLUG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
