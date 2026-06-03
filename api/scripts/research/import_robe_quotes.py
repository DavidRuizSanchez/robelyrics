"""Importa las citas VERIFICADAS de Robe (data/robe_quotes.yaml) como
InterpretationSource (kind="robe_quote") para alimentar el corpus de voz del
consultorio "Pregúntale al viento".

Solo entran las citas con `verified: true` (literal contrastado). Las paráfrasis
(verified:false) NO se importan: el consultorio jamás debe presentar como
palabras de Robe algo que no dijo textualmente.

Idempotente por (kind, url): si la cita no trae url, se usa una sintética
estable derivada del hash del texto ("robequote://<hash>").

Ejecución:
    docker compose exec api python -m scripts.research.import_robe_quotes
"""
from __future__ import annotations

import hashlib

import yaml

from scripts.research.common import DATA_DIR, get_session, log, upsert_source


def _synthetic_url(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"robequote://{h}"


def main() -> None:
    path = DATA_DIR / "robe_quotes.yaml"
    if not path.exists():
        log(f"{path} no encontrado", "err")
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    quotes = data.get("quotes") or []

    imported = skipped = 0
    with get_session() as db:
        for q in quotes:
            text = (q.get("text") or "").strip()
            if not text or not q.get("verified"):
                skipped += 1
                continue
            url = q.get("url") or _synthetic_url(text)
            upsert_source(
                db,
                kind="robe_quote",
                url=url,
                title=q.get("source") or "Cita de Robe Iniesta",
                author="Robe Iniesta",
                published_at=None,
                content_raw=text,
                content_clean=text,
                quality_score=0.95,
                for_seo_only=False,
            )
            imported += 1
            log(f"  + {text[:60]}…", "ok")
    log(f"Citas de Robe importadas: {imported} · saltadas (no verificadas): {skipped}", "ok")


if __name__ == "__main__":
    main()
