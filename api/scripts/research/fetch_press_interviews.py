"""Busca entrevistas en texto a las voces de casa y las pasa al corpus (Fase 4.2).

El agregador de noticias solo ve lo de los últimos días. Las entrevistas a Uoho,
a Cantera o a Leiva hablando de Robe que salieron hace años en HOY, en El País o
en Mariskal Rock no llegan por ningún feed. Aquí se buscan en Google (DataForSEO),
unas pocas voces por semana que van rotando, y solo se descarga lo que viene de
un medio de `data/corpus_media.yaml`: lo demás ni se abre.

La extracción es `article_extract.fetch_article`: si un medio bloquea la descarga
se queda fuera, sin disfrazar el User-Agent. La clasificación y el modo sombra
son los de `corpus_prensa` (un A en modo sombra entra como fondo).

Uso:
    python -m scripts.research.fetch_press_interviews --dry-run
    python -m scripts.research.fetch_press_interviews --voces 6
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime

from app.config import get_settings
from app.db.models import InterpretationSource
from app.services.article_extract import fetch_article
from app.services.corpus_prensa import clasificar_texto, guardar, medio_de
from app.services.corpus_trust import ROBE, MediosCorpus, cargar_voces
from app.services.news_research import web_research
from scripts.research.common import get_session, log

VOCES_POR_SEMANA = 6
RESULTADOS = 8
MAX_CHARS = 60000      # una entrevista larga; el tope de 8.000 de las noticias la cortaría


def consultas(voces, semana: int, n: int) -> list[str]:
    """Las voces de esta semana, rotando. Robe va todas las semanas."""
    otras = sorted((v for v in voces if v.slug != ROBE.slug), key=lambda v: v.slug)
    if not otras:
        return ["entrevista Robe Iniesta"]
    ini = (semana * n) % len(otras)
    turno = [otras[(ini + i) % len(otras)] for i in range(min(n, len(otras)))]
    return ["entrevista Robe Iniesta"] + [f"entrevista {v.nombre} Extremoduro Robe" for v in turno]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--voces", type=int, default=VOCES_POR_SEMANA)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    auto = get_settings().corpus_auto_entry
    semana = datetime.now(UTC).isocalendar().week
    with get_session() as db:
        voces, medios = cargar_voces(db), MediosCorpus.desde_yaml()
        conocidas = {u for (u,) in db.query(InterpretationSource.url).all()}
        vistos: set[str] = set()
        cuenta = {"A": 0, "B": 0, "fuera": 0, "sin_medio": 0, "ya": 0, "no_baja": 0}
        for q in consultas(voces, semana, args.voces):
            for r in web_research(q, n=RESULTADOS):
                url = r.get("url") or ""
                if not url or url in vistos:
                    continue
                vistos.add(url)
                if url in conocidas:
                    cuenta["ya"] += 1
                    continue
                if not medio_de(url, medios):
                    cuenta["sin_medio"] += 1
                    continue
                art = fetch_article(url, max_chars=MAX_CHARS, resolve_google=False)
                if not art.ok:
                    cuenta["no_baja"] += 1
                    log(f"  no se baja ({art.status}): {url}", "warn")
                    continue
                v = clasificar_texto(r.get("title") or "", art.text or "", url, voces, medios)
                cuenta[v.nivel] += 1
                log(f"  {v.nivel} [{v.medio}] {(r.get('title') or '')[:70]} · {v.motivo}")
                if not args.dry_run:
                    guardar(db, v, titulo=r.get("title") or url, texto=art.text or "",
                            url=url, auto_entry=auto)
        if args.dry_run:
            db.rollback()
    log("entrevistas en texto: " + " · ".join(f"{k} {n}" for k, n in cuenta.items())
        + (" (dry-run)" if args.dry_run else ""), "ok")


if __name__ == "__main__":
    main()
