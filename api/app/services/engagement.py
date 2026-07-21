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

# Engagement muy alto: cornerstone sea cual sea el origen (un tema que de verdad
# arrastra merece la pieza máxima aunque la propuesta se creara como 'seo').
CORNERSTONE_STRONG_SCORE = 65
# Para TEMÁTICAS explícitas (theme/concept) el listón de cornerstone es más bajo:
# su amplitud ya es señal de engagement.
CORNERSTONE_MIN_SCORE = 55


def content_tier(kind: str, score: int, tier: str, source_type: str | None = None) -> str:
    """Política de calidad por tipo de contenido:

    - Noticias: se respeta el tier por engagement (la actualidad manda, no se infla).
    - TODO lo demás (evergreen, spotlight, efemérides, temas): SUELO en `flagship`
      — la calidad profunda es el estándar del blog, no la excepción.
    - Engagement MUY alto (score ≥ 65) o temática (theme/concept) con engagement
      notable (≥ 55): `cornerstone`, la versión más exhaustiva —independientemente
      de cómo se creara la propuesta (seo/evergreen/…).
    El material real sigue gobernando la extensión de cada sección (anti-relleno)."""
    if kind == "news":
        return tier
    s = score or 0
    # theme/concept/album con engagement notable → cornerstone con listón más
    # bajo: su AMPLITUD (temática o de tracklist) ya es señal fuerte de recorrido.
    if s >= CORNERSTONE_STRONG_SCORE or (
        source_type in ("theme", "concept", "album") and s >= CORNERSTONE_MIN_SCORE):
        return TIER_CORNERSTONE
    return TIER_FLAGSHIP


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


def _richness_score(
    graph_degree: int, fan_sources: int, theme_reach: int = 0, amplitude: float = 0.0
) -> float:
    """0..1 según cuánto material fan y conexión de grafo tiene la entidad. Para
    TEMÁTICAS, su AMPLITUD (nº de canciones que tocan el tema) es en sí una señal
    fuerte de engagement: un tema que atraviesa medio cancionero da para una pieza
    cornerstone aunque su volumen de búsqueda directo sea modesto.

    `amplitude` es una señal de amplitud YA NORMALIZADA (0..1) para orígenes cuya
    riqueza no se mide con un simple contador de canciones — hoy, la RIQUEZA DEL
    TRACKLIST de un aniversario de disco (ver `_album_tracklist_reach`)."""
    deg = min(1.0, graph_degree / 18.0)      # ~18 aristas = muy central
    fan = min(1.0, fan_sources / 12.0)        # ~12 fuentes fan = muy rico
    theme = min(1.0, theme_reach / 15.0)      # ~15 canciones = tema muy amplio
    return max(0.5 * deg + 0.5 * fan, theme, max(0.0, min(1.0, amplitude)))


def _media_bonus(related_videos: int) -> float:
    """Pequeño empujón si hay material multimedia (vídeos) que enriquezca la pieza."""
    return min(0.1, related_videos * 0.03)


def score_from_signals(
    *, volume: int | None, graph_degree: int, fan_sources: int,
    related_videos: int = 0, theme_reach: int = 0, amplitude: float = 0.0,
) -> tuple[int, str]:
    """Núcleo PURO (testeable): señales → (score 0-100, tier). El SEO y la riqueza
    de fan pesan por igual; el multimedia es un extra acotado. `amplitude` es una
    señal de amplitud pre-normalizada (0..1), hoy la riqueza del tracklist de un
    aniversario de disco."""
    base = 0.5 * _volume_score(volume) + 0.5 * _richness_score(
        graph_degree, fan_sources, theme_reach, amplitude)
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


def _theme_reach(db, source_type: str | None, source_id: int | None) -> int:
    """Nº de canciones que tocan una temática (theme/concept). Amplitud del tema."""
    if not source_id or source_type not in ("theme", "concept"):
        return 0
    try:
        from app.db.models import Concept, Theme
        obj = db.get(Theme if source_type == "theme" else Concept, source_id)
        return len(obj.songs) if obj and obj.songs else 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("engagement: theme_reach falló: %s", exc)
        return 0


def _album_tracklist_reach(db, source_id: int | None) -> float:
    """Riqueza del TRACKLIST de un disco → amplitud normalizada (0..1). Un
    aniversario de un disco con muchas canciones, bien analizadas y muy conectadas
    en el grafo merece una pieza cornerstone aunque el volumen de su keyword sea
    modesto (mismo espíritu que `_theme_reach` para temáticas).

    Componentes (todos read-only, sin nueva ingesta):
      - tamaño del disco (nº de canciones),
      - cobertura de análisis (canciones con destilado fan) y su profundidad
        (canciones con `confidence='high'`),
      - conexión de grafo agregada del tracklist (aristas salientes de sus canciones),
      - fan-content agregado (fuentes que citan cualquier canción del disco),
      - amplitud temática (temas/conceptos distintos que tocan sus canciones).
    """
    if not source_id:
        return 0.0
    try:
        from sqlalchemy import func, or_, select

        from app.db.models import (
            Album,
            EntityEdge,
            InterpretationSource,
            Song,
            SongConcept,
            SongInterpretation,
            SongTheme,
        )

        album = db.get(Album, source_id)
        if album is None:
            return 0.0
        song_ids = [
            sid for (sid,) in db.execute(
                select(Song.id).where(Song.album_id == album.id)
            ).all()
        ]
        n_songs = len(song_ids)
        if n_songs == 0:
            return 0.0

        # Cobertura + profundidad del análisis fan.
        n_interp = int(db.execute(
            select(func.count()).select_from(SongInterpretation).where(
                SongInterpretation.song_id.in_(song_ids)
            )
        ).scalar() or 0)
        n_high = int(db.execute(
            select(func.count()).select_from(SongInterpretation).where(
                SongInterpretation.song_id.in_(song_ids),
                SongInterpretation.confidence == "high",
            )
        ).scalar() or 0)

        # Grado de grafo agregado del tracklist (aristas salientes de sus canciones).
        total_degree = int(db.execute(
            select(func.count()).select_from(EntityEdge).where(
                EntityEdge.src_type == "song", EntityEdge.src_id.in_(song_ids)
            )
        ).scalar() or 0)

        # Fan-content agregado: fuentes que referencian cualquier canción del disco.
        fan_sources = int(db.execute(
            select(func.count()).select_from(InterpretationSource).where(
                or_(*[InterpretationSource.referenced_song_ids.any(sid) for sid in song_ids])
            )
        ).scalar() or 0) if song_ids else 0

        # Amplitud temática: temas + conceptos distintos que tocan sus canciones.
        n_themes = int(db.execute(
            select(func.count(func.distinct(SongTheme.theme_id))).where(
                SongTheme.song_id.in_(song_ids)
            )
        ).scalar() or 0)
        n_concepts = int(db.execute(
            select(func.count(func.distinct(SongConcept.concept_id))).where(
                SongConcept.song_id.in_(song_ids)
            )
        ).scalar() or 0)

        size = min(1.0, n_songs / 12.0)                    # ~12 tracks = LP completo
        coverage = n_interp / n_songs                       # % con análisis fan
        depth = n_high / n_songs                             # % con análisis sólido
        graph = min(1.0, total_degree / (n_songs * 5.0))    # ~5 aristas/canción = muy conectado
        fan = min(1.0, fan_sources / 25.0)
        themes = min(1.0, (n_themes + n_concepts) / 15.0)
        reach = (0.22 * size + 0.22 * coverage + 0.18 * depth
                 + 0.16 * graph + 0.12 * themes + 0.10 * fan)
        return max(0.0, min(1.0, reach))
    except Exception as exc:  # noqa: BLE001
        logger.warning("engagement: tracklist_reach falló: %s", exc)
        return 0.0


def compute_for_proposal(db, proposal) -> tuple[int, str]:
    """Calcula (score, tier) de una ContentProposal a partir de sus señales."""
    degree, fan, videos = _entity_signals(db, getattr(proposal, "entities", None))
    source_type = getattr(proposal, "source_type", None)
    source_id = getattr(proposal, "source_id", None)
    reach = _theme_reach(db, source_type, source_id)
    # Aniversario de disco: su amplitud es la RIQUEZA DEL TRACKLIST, no un contador
    # de canciones sobre un tema. Se pasa ya normalizada como `amplitude`.
    amplitude = _album_tracklist_reach(db, source_id) if source_type == "album" else 0.0
    return score_from_signals(
        volume=getattr(proposal, "search_volume", None),
        graph_degree=degree, fan_sources=fan, related_videos=videos,
        theme_reach=reach, amplitude=amplitude,
    )
