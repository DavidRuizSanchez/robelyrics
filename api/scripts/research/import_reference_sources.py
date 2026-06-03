"""Importa fuentes de autoridad curadas a la tabla InterpretationSource.

Lee `data/reference_sources.yaml` (extractos parafraseados de libros/entrevistas/
institucional) y los inserta/actualiza como filas InterpretationSource. Idempotente
por (kind, url). Detecta canciones mencionadas en el `content` y rellena
`referenced_song_ids` reutilizando `find_referenced_titles`, de modo que las
fuentes queden ligadas a las canciones que nombran (y las recojan los generadores
de canción/disco/artista). Las que mencionan a una persona o grupo por su nombre
las recoge `fetch_sources_for_entity` por ILIKE.

Marcadas `for_seo_only=True` por defecto: alimentan la generación SEO pública pero
NO el destilador fan (no contaminan el corpus de interpretación de la comunidad).

Uso:
    python -m scripts.research.import_reference_sources
    python -m scripts.research.import_reference_sources --dry-run
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import InterpretationSource, Song
from scripts.research.common import find_referenced_titles, get_session, log


def _yaml_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))  # .../api/scripts/research
    candidates = [
        "/app/data/reference_sources.yaml",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", "reference_sources.yaml")),
        os.path.normpath(os.path.join(here, "..", "..", "data", "reference_sources.yaml")),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="no escribe, solo informa")
    args = parser.parse_args()

    path = _yaml_path()
    if not path:
        log("data/reference_sources.yaml no encontrado", "err")
        return
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    sources = data.get("sources") or []
    if not sources:
        log("reference_sources.yaml sin entradas", "warn")
        return

    with get_session() as db:
        all_titles = [(sid, t) for sid, t in db.execute(select(Song.id, Song.title)).all()]
        done = 0
        for s in sources:
            kind = s.get("kind")
            url = s.get("url")
            content = (s.get("content") or "").strip()
            if not (kind and url and content):
                log(f"  entrada inválida (falta kind/url/content): {s.get('title')}", "warn")
                continue
            song_ids = find_referenced_titles(content, all_titles)
            if args.dry_run:
                log(f"[dry] {kind} · {s.get('title')} → {len(song_ids)} canciones ligadas")
                continue
            values = dict(
                kind=kind,
                url=url,
                title=s.get("title"),
                author=s.get("author"),
                content_raw=content,
                content_clean=content,
                referenced_song_ids=song_ids or None,
                quality_score=float(s.get("quality_score", 0.85)),
                for_seo_only=bool(s.get("for_seo_only", True)),
                fetched_at=datetime.now(timezone.utc),
            )
            stmt = (
                pg_insert(InterpretationSource)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_interp_sources_kind_url",
                    set_={
                        "title": values["title"],
                        "author": values["author"],
                        "content_raw": content,
                        "content_clean": content,
                        "referenced_song_ids": song_ids or None,
                        "quality_score": values["quality_score"],
                        "for_seo_only": values["for_seo_only"],
                    },
                )
            )
            db.execute(stmt)
            done += 1
        if not args.dry_run:
            db.commit()
        log(f"reference_sources importadas/actualizadas: {done}", "ok")


if __name__ == "__main__":
    main()
