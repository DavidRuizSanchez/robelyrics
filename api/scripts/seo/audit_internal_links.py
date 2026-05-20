"""Audita enlaces internos en seo_content.body_md.

Detecta enlaces tipo /artist[/album[/song]] en el markdown editorial que apuntan
a slugs que no existen en la BD. Causa los 404 internos detectados en el crawl.

Estrategia:
1. Para cada SeoContent publicado, parsea el markdown buscando enlaces internos.
2. Resuelve cada enlace contra la BD (artist/album/song).
3. Si el slug exacto no existe, intenta el resolver tolerante de Next.js
   (prefijo único, inverso, normalizado).
4. Reporta los broken con sugerencia y, opcionalmente, los corrige con --apply.

Uso:
    docker compose exec api python -m scripts.seo.audit_internal_links
    docker compose exec api python -m scripts.seo.audit_internal_links --apply
"""
from __future__ import annotations

import argparse
import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, SeoContent, Song
from app.db.session import SessionLocal

LINK_RE = re.compile(r"\]\((/[^)\s]+)\)")


def resolve_slug(pedido: str, slugs: list[str]) -> str | None:
    """Misma lógica que web/lib/slug-resolver.ts."""
    norm = lambda s: s.replace("-", "").lower()
    pre = [s for s in slugs if s.startswith(f"{pedido}-")]
    if len(pre) == 1:
        return pre[0]
    inv = [s for s in slugs if pedido.startswith(f"{s}-")]
    if len(inv) == 1:
        return inv[0]
    p = norm(pedido)
    n = [s for s in slugs if norm(s) == p]
    if len(n) == 1:
        return n[0]
    return None


def check_url(
    db: Session,
    url: str,
    artist_slugs: set[str],
) -> tuple[bool, str | None]:
    """Devuelve (es_valido, sugerencia_canonica_si_aplica)."""
    parts = url.strip("/").split("/")
    if not parts or parts[0] not in artist_slugs:
        return True, None  # no es una URL de catálogo, ignoramos
    artist_slug = parts[0]

    if len(parts) == 1:
        return True, None  # /artist es siempre válido

    if len(parts) == 2:
        album_slug = parts[1]
        rows = db.execute(
            select(Album.slug).join(Artist).where(Artist.slug == artist_slug)
        ).all()
        slugs = [r[0] for r in rows]
        if album_slug in slugs:
            return True, None
        match = resolve_slug(album_slug, slugs)
        if match:
            return False, f"/{artist_slug}/{match}"
        return False, None

    if len(parts) == 3:
        album_slug, song_slug = parts[1], parts[2]
        rows = db.execute(
            select(Song.slug)
            .join(Album)
            .join(Artist)
            .where(Artist.slug == artist_slug, Album.slug == album_slug)
        ).all()
        slugs = [r[0] for r in rows]
        if song_slug in slugs:
            return True, None
        # Antes de proponer corrección del song, validar que el album existe
        album_exists = db.execute(
            select(Album.id)
            .join(Artist)
            .where(Artist.slug == artist_slug, Album.slug == album_slug)
        ).first()
        if not album_exists:
            # Quizá el problema está en el slug del álbum
            return False, None
        match = resolve_slug(song_slug, slugs)
        if match:
            return False, f"/{artist_slug}/{album_slug}/{match}"
        return False, None

    return True, None  # URL más larga, ignoramos


def audit(apply_fixes: bool) -> None:
    with SessionLocal() as db:
        artist_slugs = {r[0] for r in db.execute(select(Artist.slug)).all()}

        contents = db.execute(
            select(SeoContent).where(SeoContent.published.is_(True))
        ).scalars().all()

        broken_total = 0
        fixable_total = 0
        applied_total = 0
        rows_with_issues: list[tuple[SeoContent, list[tuple[str, str | None]]]] = []

        for sc in contents:
            body = sc.body_md or ""
            links = LINK_RE.findall(body)
            issues: list[tuple[str, str | None]] = []
            new_body = body
            for raw_url in links:
                url = raw_url.split("#")[0].split("?")[0]
                ok, suggestion = check_url(db, url, artist_slugs)
                if not ok:
                    issues.append((url, suggestion))
                    broken_total += 1
                    if suggestion:
                        fixable_total += 1
                        if apply_fixes:
                            new_body = new_body.replace(f"]({raw_url})", f"]({suggestion})")

            if issues:
                rows_with_issues.append((sc, issues))
                if apply_fixes and new_body != body:
                    sc.body_md = new_body
                    applied_total += 1

        if apply_fixes:
            db.commit()

        # Report
        print(f"\nSeoContent publicados auditados: {len(contents)}")
        print(f"Enlaces rotos detectados: {broken_total}")
        print(f"Con corrección automática posible: {fixable_total}")
        print(f"Sin sugerencia (requieren intervención manual): {broken_total - fixable_total}")
        if apply_fixes:
            print(f"SeoContent actualizados: {applied_total}")
        else:
            print("\n(dry-run: usa --apply para aplicar las correcciones)\n")

        if rows_with_issues:
            print("\n=== Detalle por SeoContent ===")
            for sc, issues in rows_with_issues:
                print(f"\n[{sc.entity_type}#{sc.entity_id}] slug={sc.slug}")
                for url, suggestion in issues:
                    arrow = f" → {suggestion}" if suggestion else " (sin sugerencia)"
                    print(f"  - {url}{arrow}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplica correcciones en BD (sin --apply solo reporta).",
    )
    args = parser.parse_args()
    audit(apply_fixes=args.apply)


if __name__ == "__main__":
    main()
