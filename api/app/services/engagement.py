"""Score de ENGAGEMENT de fan y tier de calidad del contenido del blog.

Idea: no todos los temas merecen la misma inversión. Un tema que de verdad le
interesa a un fan de Robe/Extremoduro Y tiene recorrido de búsqueda debe salir
MUCHO más extenso, profundo y con más multimedia. El score combina señales REALES
ya disponibles (sin nueva ingesta):

  - Potencial SEO: volumen de búsqueda de la keyword (DataForSEO).
  - Riqueza de fan / centralidad: cuánto fan-content hay sobre la entidad y cómo
    de conectada está en el grafo de conocimiento (grado en entity_edges).
  - Multimedia disponible: vídeos relacionados anclados a la entidad.

El score (0-100) deriva un `tier`:
  - flagship  (>= 65): pieza estrella, extensión y profundidad máximas.
  - premium   (>= 40): por encima del estándar.
  - standard  (< 40): densa pero contenida (mejor corto y con chicha que largo y vacío).

El tier lo LEEN el planificador de secciones y el redactor (generate_deep) para
subir el techo de extensión, y el generador para inyectar MÁS material real
(SERP de competencia + más retrieval) que justifique esa extensión — nunca relleno.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TIER_CORNERSTONE = "cornerstone"  # calidad máxima: temáticas de alto engagement
TIER_FLAGSHIP = "flagship"
TIER_PREMIUM = "premium"
TIER_STANDARD = "standard"

_TIER_ORDER = {"standard": 0, "premium": 1, "flagship": 2, "cornerstone": 3}

# Score a partir del cual una TEMÁTICA (theme/concept) se trata como pieza
# cornerstone (calidad aún mayor que flagship).
CORNERSTONE_MIN_SCORE = 55


def content_tier(kind: str, score: int, tier: str, source_type: str | None = None) -> str:
    """Política de calidad por tipo de contenido:

    - Noticias: se respeta el tier por engagement (la actualidad manda, no se infla).
    - TODO lo demás (evergreen, spotlight, efemérides, temas): SUELO en `flagship`
      — la calidad profunda es el estándar del blog, no la excepción.
    - Temáticas (theme/concept) de alto engagement: `cornerstone`, la versión más
      exhaustiva.
    El material real sigue gobernando la extensión de cada sección (anti-relleno)."""
    if kind == "news":
        return tier
    t = tier if _TIER_ORDER.get(tier, 0) >= _TIER_ORDER[TIER_FLAGSHIP] else TIER_FLAGSHIP
    if source_type in ("theme", "concept") and (score or 0) >= CORNERSTONE_MIN_SCORE:
        t = TIER_CORNERSTONE
    return t


def _volume_score(volume: int | None) -> float:
    """0..1 según el volumen de búsqueda mensual (DataForSEO)."""
    v = volume or 0
    if v >= 500:
        return 1.0
    if v >= 200:
        return 0.8
    if v >= 80:
        return 0.6
    if v >= 30:
        return 0.45
    if v >= 10:
        return 0.3
    return 0.12


def _richness_score(graph_degree: int, fan_sources: int) -> float:
    """0..1 según cuánto material fan y conexión de grafo tiene la entidad."""
    deg = min(1.0, graph_degree / 18.0)      # ~18 aristas = muy central
    fan = min(1.0, fan_sources / 12.0)        # ~12 fuentes fan = muy rico
    return 0.5 * deg + 0.5 * fan


def _media_bonus(related_videos: int) -> float:
    """Pequeño empujón si hay material multimedia (vídeos) que enriquezca la pieza."""
    return min(0.1, related_videos * 0.03)


def score_from_signals(
    *, volume: int | None, graph_degree: int, fan_sources: int, related_videos: int = 0
) -> tuple[int, str]:
    """Núcleo PURO (testeable): señales → (score 0-100, tier). El SEO y la riqueza
    de fan pesan por igual; el multimedia es un extra acotado."""
    base = 0.5 * _volume_score(volume) + 0.5 * _richness_score(graph_degree, fan_sources)
    score = int(round(min(1.0, base + _media_bonus(related_videos)) * 100))
    if score >= 65:
        tier = TIER_FLAGSHIP
    elif score >= 40:
        tier = TIER_PREMIUM
    else:
        tier = TIER_STANDARD
    return score, tier


# --------------------------------------------------------------------------- #
# Recolección de señales desde BD
# --------------------------------------------------------------------------- #
def _entity_signals(db, entities: list[dict] | None) -> tuple[int, int, int]:
    """Devuelve (grado_grafo_máx, nº_fuentes_fan, nº_vídeos_relacionados) para las
    entidades del post. Robusto: si algo falla, devuelve ceros (score cae a SEO)."""
    ents = [e for e in (entities or []) if e.get("slug_hint")]
    if not ents:
        return 0, 0, 0
    slugs = [e["slug_hint"] for e in ents]
    max_degree = fan_sources = related_videos = 0
    try:
        from sqlalchemy import func, or_, select

        from app.db.models import (
            EntityEdge,
            InterpretationSource,
            RelatedVideoEntity,
            Song,
        )

        # Grado en el grafo: nº de aristas salientes de cualquiera de las entidades.
        for slug in slugs:
            deg = db.execute(
                select(func.count()).select_from(EntityEdge).where(EntityEdge.src_slug == slug)
            ).scalar() or 0
            max_degree = max(max_degree, int(deg))

        # Fan-content: fuentes que referencian canciones de las entidades-canción.
        song_ids = [
            sid for (sid,) in db.execute(
                select(Song.id).where(Song.slug.in_(slugs))
            ).all()
        ]
        if song_ids:
            rows = db.execute(
                select(func.count()).select_from(InterpretationSource).where(
                    or_(*[InterpretationSource.referenced_song_ids.any(sid) for sid in song_ids])
                )
            ).scalar()
            fan_sources = int(rows or 0)

        related_videos = int(db.execute(
            select(func.count()).select_from(RelatedVideoEntity).where(
                RelatedVideoEntity.entity_slug.in_(slugs)
            )
        ).scalar() or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("engagement: señales de entidad fallaron: %s", exc)
    return max_degree, fan_sources, related_videos


def compute_for_proposal(db, proposal) -> tuple[int, str]:
    """Calcula (score, tier) de una ContentProposal a partir de sus señales."""
    degree, fan, videos = _entity_signals(db, getattr(proposal, "entities", None))
    return score_from_signals(
        volume=getattr(proposal, "search_volume", None),
        graph_degree=degree, fan_sources=fan, related_videos=videos,
    )
