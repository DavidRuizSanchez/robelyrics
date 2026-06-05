"""Importa transcripciones de entrevistas (data/robe_interview_transcripts.json)
como InterpretationSource, para el corpus de voz del consultorio.

El JSON se genera transcribiendo las entrevistas DESDE UNA IP RESIDENCIAL
(scripts.transcribe_with_whisper --source-mode), porque YouTube bloquea la
descarga de subtítulos/audio desde IPs de datacenter (servidor). Así no usamos
hacks de cookies/evasión: transcribimos donde se puede y versionamos el texto.

Cada entrada: {kind (robe_interview|about_robe), url, title, author,
content_clean, quality_score}. Idempotente por (kind, url).

Ejecución:
    docker compose exec api python -m scripts.research.import_interview_transcripts
"""
from __future__ import annotations

import argparse
import json

from scripts.research.common import DATA_DIR, clean_text, get_session, log, upsert_source


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--path",
        default=None,
        help="Ruta del JSON a importar (por defecto data/robe_interview_transcripts.json).",
    )
    args = ap.parse_args()
    path = DATA_DIR / args.path if args.path else DATA_DIR / "robe_interview_transcripts.json"
    if not path.exists():
        log(f"{path} no encontrado", "err")
        return
    rows = json.loads(path.read_text(encoding="utf-8")) or []
    n = 0
    with get_session() as db:
        for r in rows:
            content = (r.get("content_clean") or "").strip()
            if not r.get("kind") or not r.get("url") or len(content) < 200:
                continue
            upsert_source(
                db,
                kind=r["kind"],
                url=r["url"],
                title=r.get("title"),
                author=r.get("author"),
                published_at=None,
                content_raw=content,
                content_clean=clean_text(content),
                quality_score=r.get("quality_score") or (0.8 if r["kind"] == "robe_interview" else 0.5),
                for_seo_only=False,
            )
            n += 1
            log(f"  + [{r['kind']}] {(r.get('title') or '')[:55]}", "ok")
    log(f"Transcripciones importadas: {n}", "ok")


if __name__ == "__main__":
    main()
