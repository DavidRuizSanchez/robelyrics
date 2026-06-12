"""Motor de keyword research del blog: long-tail anclado al corpus.

Reemplaza las 6 semillas fijas genéricas de `generate_proposals` por un research
que parte del CORPUS real (personas, grupos, lugares, temas, conceptos, hechos)
para descubrir consultas long-tail sobre el universo Robe/Extremoduro, las valida
con DataForSEO (+ GSC real si está disponible) y las agrupa en ideas de artículo.

Claves frente a la versión anterior:
  - Semillas ricas del corpus, no head-terms genéricos.
  - **Memoria**: deduplica contra las KW ya publicadas (`Post.target_keyword_slug`)
    y contra las propuestas ya en el banco → no repite lo de cada semana.
  - **Long-tail**: marca las consultas long-tail (≥4 palabras o volumen bajo).
  - **Señal GSC** opcional (consultas reales): `data/gsc_queries.json` si existe.

Credenciales DataForSEO: env `DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field

from openai import OpenAI
from sqlalchemy.orm import Session

from app.db.models import (
    Album, Band, Concept, ContentProposal, Person, Place, Post, Song, Theme,
)
from app.services.seo_research import KeywordData, keyword_suggestions, search_volume

logger = logging.getLogger(__name__)

# Una consulta es long-tail si tiene muchas palabras o poco volumen (nicho).
LONGTAIL_MIN_WORDS = 4
LONGTAIL_MAX_VOLUME = 150

# Referencias culturales citadas en letras (no gente del universo): sus seeds
# traían demanda ajena (Frank Zappa, Freddie Mercury...). Fuera del research.
REFERENCE_SLUGS = {"manolete", "camaron", "frank-zappa", "freddie-mercury"}

# Desambiguación de nombres artísticos cortos (igual que generate_proposals).
PERSON_SEED_OVERRIDES = {
    "robe-iniesta": "robe iniesta",
    "inaki-uoho-anton": "iñaki uoho antón extremoduro",
    "salo": "salo batería extremoduro",
    "miguel-colino": "miguel colino extremoduro",
    "jose-ignacio-cantera": "iñaki cantera extremoduro",
    "kutxi-romero": "kutxi romero marea",
    "fito-cabrales": "fito cabrales",
    "manolo-kabezabolo": "manolo kabezabolo",
    "rosendo-mercado": "rosendo mercado",
}

# Semillas transversales del universo (no apuntan a una página-hub concreta:
# son ángulos de blog — biografía, listas, contexto, legado, historia).
TRANSVERSAL_SEEDS = [
    "robe iniesta biografia",
    "robe iniesta vida",
    "historia de extremoduro",
    "mejores canciones de extremoduro",
    "extremoduro discografia",
    "rock transgresivo extremoduro",
    "extremoduro y robe diferencias",
    "robe iniesta frases",
    "extremoduro letras significado",
    "robe iniesta libros",
]


def kw_slug(s: str) -> str:
    """Normaliza una keyword a un slug estable para dedup/índice."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", "-", s.strip())[:160]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_longtail(keyword: str, volume: int) -> bool:
    return len(_norm(keyword).split()) >= LONGTAIL_MIN_WORDS or (0 < volume <= LONGTAIL_MAX_VOLUME)


# --------------------------------------------------------------------------- #
# Semillas desde el corpus
# --------------------------------------------------------------------------- #
def build_seeds(db: Session) -> list[str]:
    """Semillas ancladas al corpus: transversales + entidades reales."""
    seeds = list(TRANSVERSAL_SEEDS)
    for p in db.query(Person).all():
        if p.slug in REFERENCE_SLUGS:
            continue
        seeds.append(PERSON_SEED_OVERRIDES.get(p.slug) or p.full_name)
    for b in db.query(Band).all():
        seeds.append(b.name if b.kind == "label" else f"{b.name} grupo")
    for t in db.query(Theme).all():
        seeds.append(f"extremoduro {t.name}")
    for pl in db.query(Place).all():
        seeds.append(f"{pl.name} extremoduro")
    for c in db.query(Concept).all():
        seeds.append(f"extremoduro {c.name}")
    # dedup conservando orden
    seen: set[str] = set()
    out: list[str] = []
    for s in seeds:
        k = _norm(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _covered_tokens(db: Session) -> set[str]:
    """Títulos de canción/disco normalizados: una KW que los contenga ya la capta
    su página-hub (no es ángulo de blog)."""
    tokens: set[str] = set()
    for (title,) in db.query(Song.title).all():
        n = _norm(title)
        if len(n) >= 6:
            tokens.add(n)
    for (title,) in db.query(Album.title).all():
        n = _norm(title)
        if len(n) >= 6:
            tokens.add(n)
    return tokens


def _published_kw_slugs(db: Session) -> set[str]:
    """KW ya publicadas (memoria anti-repetición entre semanas)."""
    slugs: set[str] = set()
    for (s,) in db.query(Post.target_keyword_slug).filter(
        Post.target_keyword_slug.isnot(None)
    ).all():
        if s:
            slugs.add(s)
    for (s,) in db.query(ContentProposal.target_keyword_slug).filter(
        ContentProposal.target_keyword_slug.isnot(None)
    ).all():
        if s:
            slugs.add(s)
    return slugs


def _gsc_queries() -> list[KeywordData]:
    """Consultas reales de GSC si hay un cache versionado (data/gsc_queries.json).
    Formato esperado: [{"query": str, "clicks": int, "impressions": int,
    "position": float}]. Se priorizan posiciones 5-20 (oportunidad). Degrada a []
    si el fichero no existe (GSC aún no cableado al backend)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/app/data/gsc_queries.json",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", "gsc_queries.json")),
    ):
        if os.path.exists(p):
            try:
                rows = json.load(open(p, encoding="utf-8"))
            except (ValueError, OSError) as exc:
                logger.warning("gsc_queries.json ilegible: %s", exc)
                return []
            out: list[KeywordData] = []
            for r in rows:
                q = (r.get("query") or "").strip()
                if not q:
                    continue
                pos = r.get("position") or 0
                # Oportunidad: lo que ya aparece pero no en el top (5-20).
                vol = int(r.get("impressions") or 0)
                out.append(KeywordData(keyword=q, volume=vol, cpc=None, competition=pos))
            logger.info("[gsc] %d consultas reales cargadas del cache", len(out))
            return out
    return []


# --------------------------------------------------------------------------- #
# Pool de keywords
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    keyword: str
    volume: int
    signal: str  # corpus|dataforseo|gsc
    longtail: bool = field(default=False)


def research_pool(db: Session, *, per_seed: int = 60, min_volume: int = 20) -> list[Candidate]:
    """Recolecta el pool de candidatas: DataForSEO por semilla + GSC real, dedup
    y filtra lo cubierto por páginas-hub y lo ya publicado."""
    seeds = build_seeds(db)
    covered = _covered_tokens(db)
    published = _published_kw_slugs(db)
    logger.info("Keyword research: %d semillas del corpus", len(seeds))

    pool: dict[str, Candidate] = {}

    def _consider(keyword: str, volume: int, signal: str) -> None:
        nk = _norm(keyword)
        slug = kw_slug(keyword)
        if not nk or nk in pool or slug in published:
            return
        if any(tok in nk for tok in covered):  # ya lo capta una página-hub
            return
        pool[nk] = Candidate(
            keyword=keyword, volume=volume, signal=signal,
            longtail=_is_longtail(keyword, volume),
        )

    for seed in seeds:
        for kw in keyword_suggestions(seed, limit=per_seed, min_volume=min_volume):
            _consider(kw.keyword, kw.volume, "dataforseo")

    for g in _gsc_queries():
        _consider(g.keyword, g.volume, "gsc")

    out = sorted(pool.values(), key=lambda c: (-int(c.longtail), -c.volume))
    n_lt = sum(1 for c in out if c.longtail)
    logger.info("Pool: %d candidatas (%d long-tail, %.0f%%)",
                len(out), n_lt, 100 * n_lt / max(1, len(out)))
    return out


# --------------------------------------------------------------------------- #
# Clustering en ideas de artículo
# --------------------------------------------------------------------------- #
CLUSTER_SYSTEM = """\
Eres estratega de contenidos SEO de un sitio editorial sobre Robe Iniesta y
Extremoduro. A partir de una lista de keywords reales con su volumen de búsqueda,
propones IDEAS DE ARTÍCULO de blog.

Reglas:
- Cada idea agrupa keywords afines que comparten intención de búsqueda.
- PRIORIZA las consultas LONG-TAIL (específicas, de varias palabras): son el 80%
  del objetivo. Evita head-terms genéricos.
- NO propongas artículos sobre UNA canción, UN disco, UNA persona o UNA taxonomía
  concreta: esas páginas ya existen en el sitio (serían canibalización). Busca
  ángulos TRANSVERSALES: listas, biografía, contexto histórico, comparativas,
  el legado, anécdotas, las relaciones entre personas/grupos, hechos del universo.
- Título editorial y atractivo, no un keyword pelado. Sin em-dash «—».
- El ángulo: una frase con el enfoque del artículo.
- Tono: neutral, cercano, admiración a Robe sin reverencia mística.

Devuelve JSON: {"topics": [{"title": str, "angle": str,
"target_keyword": str, "secondary_keywords": [str, ...]}]}.
target_keyword = la keyword principal (la más representativa del artículo).
Propón TANTAS ideas como te permita el material (hasta 40). Sin límite artificial.
"""


def cluster_topics(client: OpenAI, pool: list[Candidate], *, max_topics: int = 40) -> list[dict]:
    if not pool:
        return []
    kw_lines = "\n".join(
        f"- {c.keyword} ({c.volume}/mes{', long-tail' if c.longtail else ''})"
        for c in pool[:260]
    )
    user = (
        "Keywords reales con volumen de búsqueda mensual en España "
        "(las long-tail marcadas):\n\n"
        f"{kw_lines}\n\nAgrúpalas en ideas de artículo según las reglas."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": CLUSTER_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
        max_tokens=4000,
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        logger.error("LLM clustering devolvió JSON inválido")
        return []
    return (data.get("topics") or [])[:max_topics]


def build_proposal_rows(
    client: OpenAI, db: Session, *, slug_int
) -> list[dict]:
    """Devuelve las filas de ContentProposal (kind='evergreen') listas para
    insertar, con target_keyword + metadatos. `slug_int` = hash estable de título
    para la UNIQUE (kind, source_type, source_id)."""
    pool = research_pool(db)
    by_norm = {_norm(c.keyword): c for c in pool}
    topics = cluster_topics(client, pool)
    logger.info("El LLM agrupó en %d ideas de artículo", len(topics))

    published = _published_kw_slugs(db)
    rows: list[dict] = []
    for topic in topics:
        title = (topic.get("title") or "").strip()
        primary = (topic.get("target_keyword") or "").strip()
        if not title or not primary:
            continue
        pslug = kw_slug(primary)
        if pslug in published:
            continue  # memoria: no repetir KW ya usada
        published.add(pslug)

        # Ensambla keywords (primary + secundarias) con volumen/señal del pool.
        all_kw = [primary] + [k for k in (topic.get("secondary_keywords") or []) if k]
        kw_objs, total_vol, longtail_any, signal = [], 0, False, "corpus"
        for kw in all_kw:
            c = by_norm.get(_norm(kw))
            vol = c.volume if c else 0
            total_vol += vol
            longtail_any = longtail_any or _is_longtail(kw, vol)
            if c:
                signal = c.signal
            kw_objs.append({"keyword": kw, "volume": vol, "cpc": None, "competition": None})

        prim = by_norm.get(_norm(primary))
        rows.append({
            "kind": "evergreen",
            "source_type": "seo",
            "source_id": slug_int(title),
            "title": title[:240],
            "angle": (topic.get("angle") or "")[:1000],
            "keywords": kw_objs,
            "target_keyword": primary[:160],
            "target_keyword_slug": pslug,
            "search_volume": (prim.volume if prim else 0),
            "is_longtail": _is_longtail(primary, prim.volume if prim else 0) or longtail_any,
            "signal_source": (prim.signal if prim else signal),
            "content_key": f"evergreen:{pslug}" if pslug else None,
        })
    return rows
