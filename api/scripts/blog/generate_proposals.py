"""Genera propuestas editoriales SEO-driven en el banco `content_proposals`.

A diferencia de la versión anterior (que proponía taxonomías internas sin
demanda), este generador parte de KEYWORD RESEARCH real:

  1. Semillas del universo (Robe, Extremoduro, discos, personas, amigos).
  2. DataForSEO `keyword_suggestions` por semilla → pool de keywords con
     volumen de búsqueda real.
  3. Se descartan las keywords que ya cubre una página existente (canción
     o disco concreto): esa demanda ya la capta el catálogo.
  4. Un LLM agrupa las keywords restantes en IDEAS DE ARTÍCULO, cada una
     con título, ángulo y keywords objetivo.
  5. Cada idea entra al banco como propuesta `kind='evergreen'` con sus
     keywords + volumen adjuntos.

Además genera las efemérides de actualidad (aniversarios de discos
próximos, cumpleaños/muerte de Robe) como antes.

Uso:
    python -m scripts.blog.generate_proposals
    python -m scripts.blog.generate_proposals --dry-run
    python -m scripts.blog.generate_proposals --no-research   (solo efemérides)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import unicodedata
from datetime import date

from openai import OpenAI
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db.models import Album, Artist, ContentProposal, Person, Song
from app.db.session import SessionLocal
from app.services.seo_research import KeywordData, keyword_suggestions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROBE_BIRTH = (5, 16)
ROBE_DEATH = (12, 10)

# Semillas fijas del universo (además de discos/personas que se cargan de DB).
FIXED_SEEDS = [
    "robe iniesta",
    "extremoduro",
    "robe cantante",
    "marea grupo",
    "platero y tú",
    "rock urbano español",
]

CLUSTER_SYSTEM = """\
Eres estratega de contenidos SEO de un sitio editorial sobre Robe Iniesta
y Extremoduro. Tu trabajo: a partir de una lista de keywords reales con su
volumen de búsqueda mensual, proponer IDEAS DE ARTÍCULO de blog.

Reglas:
- Cada idea agrupa keywords afines que comparten intención de búsqueda.
- NO propongas artículos sobre una canción o disco concreto: esas páginas
  ya existen en el sitio. Busca ángulos transversales: listas, biografía,
  contexto, comparativas, el legado, las personas, los grupos afines.
- Prioriza ideas con mayor volumen de búsqueda agregado.
- Título editorial y atractivo, no un keyword pelado. Sin em-dash «—».
- El ángulo: una frase explicando el enfoque del artículo.
- Tono del sitio: neutral, cercano, respeto y admiración a Robe sin
  reverencia mística.

Devuelve JSON: {"topics": [{"title": str, "angle": str,
"target_keywords": [str, ...]}]}. Máximo 18 topics.
"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _slug_int(text: str) -> int:
    """Hash determinista y estable de un texto → int para la UNIQUE de
    (kind, source_type, source_id). Evita duplicar la misma idea."""
    h = 0
    for ch in _norm(text):
        h = (h * 31 + ord(ch)) % 2_000_000_000
    return h or 1


def _days_until(today: date, month: int, day: int) -> int:
    this_year = date(today.year, month, day)
    target = this_year if this_year >= today else date(today.year + 1, month, day)
    return (target - today).days


def _insert(db, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = (
        pg_insert(ContentProposal)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_content_proposals_kind_source")
        .returning(ContentProposal.id)
    )
    return len(db.execute(stmt).fetchall())


# --------------------------------------------------------------------------- #
# Keyword research
# --------------------------------------------------------------------------- #
def _collect_seeds(db) -> list[str]:
    seeds = list(FIXED_SEEDS)
    for (title,) in db.query(Album.title).all():
        seeds.append(f"{title} extremoduro")
    for p in db.query(Person).all():
        seeds.append(p.stage_name or p.full_name)
    # dedup conservando orden
    seen: set[str] = set()
    out: list[str] = []
    for s in seeds:
        k = _norm(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _covered_tokens(db) -> set[str]:
    """Conjunto de títulos de canción normalizados — una keyword que los
    contenga ya está cubierta por la página de esa canción."""
    tokens: set[str] = set()
    for (title,) in db.query(Song.title).all():
        n = _norm(title)
        if len(n) >= 5:  # evita títulos de 1-2 letras demasiado genéricos
            tokens.add(n)
    return tokens


def _research_pool(seeds: list[str], covered: set[str]) -> list[KeywordData]:
    """Recolecta keywords de todas las semillas, dedup y filtra lo cubierto."""
    pool: dict[str, KeywordData] = {}
    for seed in seeds:
        kws = keyword_suggestions(seed, limit=60, min_volume=40)
        logger.info("  semilla %r → %d keywords", seed, len(kws))
        for kw in kws:
            nk = _norm(kw.keyword)
            if not nk or nk in pool:
                continue
            # descartar si la keyword contiene el título de una canción
            if any(tok in nk for tok in covered):
                continue
            pool[nk] = kw
    return sorted(pool.values(), key=lambda k: -k.volume)


def _cluster(client: OpenAI, pool: list[KeywordData]) -> list[dict]:
    """Pide al LLM agrupar el pool de keywords en ideas de artículo."""
    if not pool:
        return []
    kw_lines = "\n".join(f"- {k.keyword} ({k.volume}/mes)" for k in pool[:180])
    user = (
        "Keywords reales con volumen de búsqueda mensual en España:\n\n"
        f"{kw_lines}\n\n"
        "Agrúpalas en ideas de artículo según las reglas del sistema."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": CLUSTER_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
        max_tokens=3000,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("LLM clustering devolvió JSON inválido")
        return []
    return data.get("topics") or []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-research", action="store_true",
        help="salta DataForSEO + LLM, solo genera efemérides",
    )
    parser.add_argument("--anniversary-window", type=int, default=90)
    args = parser.parse_args()

    today = date.today()
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    with SessionLocal() as db:
        actualidad: list[dict] = []
        seo_rows: list[dict] = []

        # --- Aniversarios de discos próximos ---
        for album, artist in (
            db.query(Album, Artist).join(Artist, Album.artist_id == Artist.id)
            .filter(Album.release_date.isnot(None)).all()
        ):
            rd = album.release_date
            if _days_until(today, rd.month, rd.day) > args.anniversary_window:
                continue
            anniv = date(
                today.year if date(today.year, rd.month, rd.day) >= today
                else today.year + 1, rd.month, rd.day,
            )
            years = anniv.year - rd.year
            actualidad.append({
                "kind": "album-anniversary",
                "source_type": "album",
                "source_id": album.id,
                "title": f"{years}º aniversario de {album.title}",
                "angle": (
                    f"El {anniv.isoformat()} se cumplen {years} años del "
                    f"lanzamiento de {album.title} ({artist.name}, {rd.year})."
                ),
            })

        # --- Efemérides de Robe ---
        for label, (m, d), src in (
            ("cumpleaños", ROBE_BIRTH, "robe-birth"),
            ("aniversario de la muerte", ROBE_DEATH, "robe-death"),
        ):
            if _days_until(today, m, d) <= args.anniversary_window:
                actualidad.append({
                    "kind": "anniversary",
                    "source_type": src,
                    "source_id": 0,
                    "title": f"Robe Iniesta · {label}",
                    "angle": (
                        f"Se acerca el {label} de Robe Iniesta ({d:02d}/{m:02d}). "
                        "Homenaje editorial actualizado."
                    ),
                })

        # --- Propuestas SEO-driven ---
        if not args.no_research and client is not None:
            seeds = _collect_seeds(db)
            covered = _covered_tokens(db)
            logger.info("Keyword research: %d semillas...", len(seeds))
            pool = _research_pool(seeds, covered)
            logger.info("Pool de keywords (filtrado): %d", len(pool))
            vol_by_kw = {_norm(k.keyword): k for k in pool}
            topics = _cluster(client, pool)
            logger.info("El LLM agrupó en %d ideas de artículo", len(topics))
            for topic in topics:
                title = (topic.get("title") or "").strip()
                if not title:
                    continue
                target = topic.get("target_keywords") or []
                kw_objs = []
                for kw in target:
                    kd = vol_by_kw.get(_norm(kw))
                    if kd:
                        kw_objs.append(kd.as_dict())
                    else:
                        kw_objs.append({"keyword": kw, "volume": 0,
                                        "cpc": None, "competition": None})
                seo_rows.append({
                    "kind": "evergreen",
                    "source_type": "seo",
                    "source_id": _slug_int(title),
                    "title": title[:240],
                    "angle": (topic.get("angle") or "")[:1000],
                    "keywords": kw_objs,
                })
        elif not args.no_research:
            logger.warning("OPENAI_API_KEY no configurada, salto research SEO")

        logger.info(
            "Candidatas: %d actualidad, %d SEO-driven", len(actualidad), len(seo_rows)
        )

        if args.dry_run:
            print("--- ACTUALIDAD ---")
            for r in actualidad:
                print(f"  [{r['kind']}] {r['title']}")
            print("--- SEO-DRIVEN ---")
            for r in seo_rows:
                vol = sum(k["volume"] for k in r.get("keywords", []))
                print(f"  {r['title']}  ({vol}/mes agregado)")
                for k in r.get("keywords", [])[:5]:
                    print(f"      · {k['keyword']} ({k['volume']})")
            return

        n_act = _insert(db, actualidad)
        n_seo = _insert(db, seo_rows)
        db.commit()
        logger.info(
            "Propuestas NUEVAS: %d actualidad + %d SEO-driven = %d",
            n_act, n_seo, n_act + n_seo,
        )


if __name__ == "__main__":
    main()
