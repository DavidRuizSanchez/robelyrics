"""Motor de Consenso de Verificación (MCV).

Generaliza lo que `web_verify` + `fact_check` hacían de UNA sola fuente a un
**consenso multi-fuente ponderado con confianza**. Es la pieza que decide qué se
auto-corrige y qué (poco) llega a revisión humana.

Filosofía (feedback de fans, ver plan del vuelco editorial): la verdad de base
del site tenía agujeros (letras mal transcritas, autoría sin modelar, disco/año
de Genius). En vez de mandar todo a un humano, contrastamos cada dato contra
VARIAS fuentes externas; si hay consenso claro de que algo está mal Y con qué
corregirlo, se corrige solo, registrando la traza (auditable y reversible). El
humano solo arbitra el residuo ambiguo.

Este módulo aporta las piezas GENÉRICAS y testables:
  - Tiering de autoridad de fuente (peso en el voto).
  - Dataclasses de veredicto enriquecido (confidence + sources).
  - Política de decisión (auto-aplicar vs revisión humana) — función pura.
  - Adjudicador LLM (reutiliza el juez barato de news_research).
  - Persistencia en VerificationRecord.

Los verificadores por eje (scripts/verify/lyrics_consensus.py,
authorship_consensus.py, catalog_consensus.py) RECOLECTAN la evidencia concreta
(LRCLIB, Wikipedia, anotaciones de Genius, blogs del corpus...) y llaman a
`adjudicate()` + `decide()` de aquí.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Tiering de fuentes: cuánta autoridad tiene cada fuente en el voto.
#   T1 = puede GOBERNAR una auto-corrección (autoritativa).
#   T2 = corroboración fuerte.
#   T3 = señal débil: corrobora, nunca decide sola, nunca se publica.
# La clave es el `source_kind` que pasa el verificador (no el dominio crudo).
# --------------------------------------------------------------------------- #
Tier = Literal[1, 2, 3]

_SOURCE_TIER: dict[str, Tier] = {
    # --- T1 ---
    "wikipedia": 1,
    "wikidata": 1,
    "musicbrainz": 1,
    "genius_annotation_verified": 1,
    "robe_voice": 1,            # palabras del propio Robe (entrevistas)
    "respuestas_del_robe": 1,   # hilo Mediavida donde Robe confirma/niega
    "curated": 1,               # datos ya curados del repo (bands/books/reference)
    "booklet": 1,               # libreto/edición física
    "discography_yaml": 1,
    # --- T2 ---
    "blog_especializado": 2,
    "lrclib": 2,
    "letras_com": 2,
    "vagalume": 2,
    "genius": 2,                # letra de Genius (fuente actual)
    "google_serp": 2,
    "book": 2,
    "thesis": 2,
    "fan_feedback": 2,          # corrección reportada por un fan de confianza
                                # (arbitra empates, pero NUNCA se aplica sola:
                                #  requiere corroboración externa, ver
                                #  decide_fan_correction)
    # --- T3 ---
    "genius_annotation": 3,     # anotación sin verificar
    "forum": 3,
    "youtube_transcript": 3,
    "youtube_comment": 3,
    "reddit": 3,                # solo señal interna, NUNCA publicada (policy)
    "unknown": 3,
}

# Peso numérico por tier (para el score de confianza agregado). Calibrado para
# que 1×T1 o 2×T2 sin contradicción superen el umbral de auto-aplicación.
_TIER_WEIGHT: dict[Tier, float] = {1: 1.0, 2: 0.6, 3: 0.25}

# Umbral de confianza mínimo para auto-aplicar.
AUTO_APPLY_MIN_CONFIDENCE = 0.7

Stance = Literal["supports", "contradicts", "neutral"]
Verdict = Literal["confirmed", "corrected", "conflict", "not_found"]
Action = Literal["auto_apply", "needs_human", "confirm_noop", "skip"]


def source_tier(source_kind: str) -> Tier:
    """Tier de autoridad de un `source_kind`. Desconocido → T3 (conservador)."""
    return _SOURCE_TIER.get((source_kind or "").strip().lower(), 3)


@dataclass
class SourceRef:
    """Una fuente que participa en el voto de consenso."""

    name: str                      # nombre legible ("Wikipedia · Extrechinato y tú")
    source_kind: str               # clave de _SOURCE_TIER
    stance: Stance = "neutral"     # respalda / contradice / neutral respecto a `value`
    value: str | None = None       # el valor que ESTA fuente afirma (letra, autor, año)
    url: str | None = None
    quote: str | None = None       # cita breve que lo respalda

    @property
    def tier(self) -> Tier:
        return source_tier(self.source_kind)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_kind": self.source_kind,
            "tier": self.tier,
            "stance": self.stance,
            "value": self.value,
            "url": self.url,
            "quote": self.quote,
        }


@dataclass
class ConsensusResult:
    """Resultado del consenso sobre un claim."""

    verdict: Verdict
    confidence: float                          # 0-1 agregado
    current_value: str | None = None           # lo que hay hoy en BD
    correct_value: str | None = None           # el valor propuesto (si corrected)
    sources: list[SourceRef] = field(default_factory=list)
    rationale: str = ""

    # -- votos por tier (solo fuentes que RESPALDAN el correct_value) --
    # El `stance` ya lo fijó el adjudicador/evaluador con su propio criterio de
    # equivalencia (p.ej. tolerante a puntuación en letras); aquí se respeta.
    def _supporters(self) -> list[SourceRef]:
        return [s for s in self.sources if s.stance == "supports"]

    def _contradictors_t1(self) -> list[SourceRef]:
        """Fuentes T1 que CONTRADICEN el valor propuesto (bloquean auto-aplicar)."""
        return [s for s in self.sources if s.stance == "contradicts" and s.tier == 1]

    def supporter_tiers(self) -> list[Tier]:
        return sorted(s.tier for s in self._supporters())


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


# --------------------------------------------------------------------------- #
# Política de decisión (FUNCIÓN PURA — el corazón, testable sin red).
# --------------------------------------------------------------------------- #
def decide(result: ConsensusResult, *, high_risk: bool = False) -> Action:
    """Decide qué hacer con un veredicto de consenso.

    - `confirmed`  → confirm_noop (lo de BD ya es correcto).
    - `corrected`  → auto_apply si hay respaldo suficiente y confianza alta y
                     ninguna T1 lo contradice y NO es alto riesgo; si no, needs_human.
    - `conflict`   → needs_human (fuentes fiables se contradicen).
    - `not_found`  → skip (sin cobertura externa; no tocamos nada, no molestamos
                     al humano salvo que venga de una errata explícita).

    Respaldo suficiente = ≥1 fuente T1 respalda, o ≥2 T2 respaldan.
    """
    if result.verdict == "confirmed":
        return "confirm_noop"
    if result.verdict == "not_found":
        return "skip"
    if result.verdict == "conflict":
        return "needs_human"

    # verdict == "corrected"
    if not result.correct_value:
        return "needs_human"
    if result._contradictors_t1():
        return "needs_human"
    if result.confidence < AUTO_APPLY_MIN_CONFIDENCE:
        return "needs_human"
    if high_risk:
        return "needs_human"

    tiers = result.supporter_tiers()
    n_t1 = sum(1 for t in tiers if t == 1)
    n_t2 = sum(1 for t in tiers if t == 2)
    if n_t1 >= 1 or n_t2 >= 2:
        return "auto_apply"
    return "needs_human"


def evaluate_hypothesis(
    *,
    hypothesis: str,
    current_value: str | None,
    sources: list[SourceRef],
    matcher=None,
) -> ConsensusResult:
    """Evalúa una HIPÓTESIS concreta (p.ej. el valor que reporta un fan) contra
    las fuentes, de forma DETERMINISTA (sin LLM). Marca cada fuente como
    supports/contradicts según su valor case con la hipótesis, y calcula la
    confianza agregada. Verdict: 'corrected' si la hipótesis difiere del valor
    actual y hay respaldo; 'confirmed' si la hipótesis == valor actual.

    `matcher(a, b) -> bool` opcional: predicado de equivalencia entre valores.
    Por defecto, igualdad normalizada exacta (sensible a cambios de palabra como
    'llega'/'lleva'; los verificadores de letra pasan un matcher por tokens que
    tolera puntuación y conectores pero NO cambios de palabra).
    """
    def _matches(a: str | None, b: str | None) -> bool:
        if a is None or b is None:
            return False
        if matcher is not None:
            return bool(matcher(a, b))
        return _norm(a) == _norm(b)

    for s in sources:
        if s.value is None:
            s.stance = "neutral"
        elif _matches(s.value, hypothesis):
            s.stance = "supports"
        else:
            s.stance = "contradicts"

    supports_any = any(s.stance == "supports" for s in sources)
    same_as_current = _matches(hypothesis, current_value)
    if same_as_current:
        verdict: Verdict = "confirmed"
    elif supports_any:
        verdict = "corrected"
    else:
        verdict = "not_found"

    confidence = aggregate_confidence(sources, hypothesis) if verdict in ("confirmed", "corrected") else 0.0
    return ConsensusResult(
        verdict=verdict,
        confidence=confidence,
        current_value=current_value,
        correct_value=hypothesis if verdict == "corrected" else None,
        sources=sources,
        rationale="Evaluación determinista de la hipótesis contra las fuentes.",
    )


def decide_fan_correction(result: ConsensusResult, fan_value: str) -> Action:
    """Política para una corrección reportada por un FAN de confianza.

    Filosofía del vuelco: la palabra de un superfan que lee cada post arbitra los
    empates que las fuentes abiertas no resuelven (caso real "llega/lleva": LRCLIB
    dice lleva, letras.com dice llega). PERO nunca se aplica una corrección de fan
    SIN corroboración externa (regla de integridad de datos).

    - auto_apply si: el valor ganador coincide con lo que dijo la fan Y AL MENOS
      UNA fuente independiente (no-fan) lo corrobora Y ninguna T1 lo contradice.
    - needs_human si: nadie corrobora a la fan, o una T1 la contradice, o el
      ganador no es su valor.
    """
    winner = result.correct_value if result.verdict == "corrected" else result.current_value
    if _norm(winner) != _norm(fan_value):
        return "needs_human"
    if result._contradictors_t1():
        return "needs_human"
    # ¿hay corroboración EXTERNA (fuente no-fan que respalde el valor de la fan)?
    external_support = [
        s for s in result._supporters() if s.source_kind != "fan_feedback"
    ]
    if external_support:
        return "auto_apply"
    return "needs_human"


def aggregate_confidence(sources: list[SourceRef], target: str | None) -> float:
    """Confianza agregada 0-1 a partir del respaldo ponderado por tier menos la
    contradicción ponderada. Función pura (testable)."""
    support = 0.0
    against = 0.0
    for s in sources:
        w = _TIER_WEIGHT[s.tier]
        if s.stance == "supports":
            support += w
        elif s.stance == "contradicts":
            against += w
    if support <= 0:
        return 0.0
    # Una fuente que contradice cuenta a la mitad (un disidente aislado no debe
    # tumbar un respaldo sólido, pero sí rebajar la confianza). Calibrado para:
    # 1×T1 sin contra → 0.77; 2×T2 → 0.80; 1×T2 solo → 0.67 (<0.7, va a humano).
    raw = support / (support + 0.5 * against + 0.3)
    return round(min(1.0, raw), 3)


# --------------------------------------------------------------------------- #
# Adjudicador LLM: dado un claim + candidatos con sus fuentes, decide.
# Reutiliza el juez barato (gpt-4o-mini) de news_research.
# --------------------------------------------------------------------------- #
_ADJUDICATE_SYS = (
    "Eres un adjudicador de consenso riguroso para un archivo sobre Robe y "
    "Extremoduro. Te doy una PREGUNTA, el VALOR ACTUAL que tenemos, y EVIDENCIA "
    "de varias fuentes (cada una con su fiabilidad T1/T2/T3, donde T1 es la más "
    "fiable). Decide y responde SOLO JSON:\n"
    '{"verdict": "confirmed|corrected|conflict|not_found", '
    '"correct_value": "<el valor correcto, o null>", '
    '"rationale": "<por qué, en una frase>"}.\n'
    "- confirmed: la evidencia respalda el VALOR ACTUAL.\n"
    "- corrected: la evidencia indica claramente OTRO valor (ponlo en correct_value).\n"
    "- conflict: fuentes fiables (T1/T2) se contradicen entre sí sin ganador claro.\n"
    "- not_found: la evidencia no cubre el tema o es insuficiente.\n"
    "Pondera por fiabilidad: una T1 pesa más que varias T3. Ante la duda entre "
    "corrected y not_found, elige not_found. NO inventes valores que no estén en "
    "la evidencia."
)


def adjudicate(
    *,
    question: str,
    current_value: str | None,
    sources: list[SourceRef],
) -> ConsensusResult:
    """Llama al adjudicador LLM y devuelve un ConsensusResult con confianza y
    fuentes. La confianza final se recalcula de forma determinista a partir del
    tiering (no se fía del número que diga el LLM)."""
    from app.services.news_research import _json

    if not sources:
        return ConsensusResult(
            verdict="not_found", confidence=0.0, current_value=current_value,
            sources=[], rationale="Sin evidencia recolectada.",
        )

    evidence_block = "\n".join(
        f"[T{s.tier} · {s.name}] afirma: {s.value or '(sin valor explícito)'}"
        + (f" — \"{s.quote}\"" if s.quote else "")
        for s in sources
    )
    out = _json(
        _ADJUDICATE_SYS,
        f"PREGUNTA: {question}\nVALOR ACTUAL: {current_value or '(ninguno)'}\n\n"
        f"EVIDENCIA:\n{evidence_block[:6000]}",
        max_tokens=300,
        temperature=0.1,
    )
    verdict = out.get("verdict")
    if verdict not in ("confirmed", "corrected", "conflict", "not_found"):
        verdict = "not_found"
    correct_value = out.get("correct_value") or None

    # Marcar stance de cada fuente respecto al valor ganador (para el score).
    target = correct_value if verdict == "corrected" else current_value
    for s in sources:
        if s.value is None:
            continue
        if _norm(s.value) == _norm(target):
            s.stance = "supports"
        elif verdict in ("corrected", "conflict"):
            s.stance = "contradicts"

    confidence = aggregate_confidence(sources, target) if verdict in ("confirmed", "corrected") else 0.0
    return ConsensusResult(
        verdict=verdict,
        confidence=confidence,
        current_value=current_value,
        correct_value=correct_value,
        sources=sources,
        rationale=(out.get("rationale") or "")[:400],
    )


# --------------------------------------------------------------------------- #
# Persistencia en VerificationRecord (traza auditable).
# --------------------------------------------------------------------------- #
def errata_exists(db, *, target_type: str, target_id: int | None, field: str | None = None) -> bool:
    """¿Ya hay una errata ABIERTA (pending/needs_human) para este target? Evita que
    el barrido nocturno cree duplicados del mismo caso en cada pasada."""
    from sqlalchemy import select

    from app.db.models import ErrataReport

    q = select(ErrataReport.id).where(
        ErrataReport.target_type == target_type,
        ErrataReport.status.in_(("pending", "needs_human")),
    )
    if target_id is not None:
        q = q.where(ErrataReport.target_id == target_id)
    if field:
        q = q.where(ErrataReport.field == field)
    return db.execute(q).first() is not None


def record_verification(
    db,
    *,
    claim_kind: str,
    claim_key: str,
    result: ConsensusResult,
    song_id: int | None = None,
    applied: bool = False,
):
    """Upsert de la traza de una verificación. `db` es una Session sync
    (los scripts de verify corren en sync, como el resto de scripts.*)."""
    from sqlalchemy import select

    from app.db.models import VerificationRecord

    rec = db.execute(
        select(VerificationRecord).where(
            VerificationRecord.claim_kind == claim_kind,
            VerificationRecord.claim_key == claim_key,
        )
    ).scalar_one_or_none()
    if rec is None:
        rec = VerificationRecord(claim_kind=claim_kind, claim_key=claim_key)
        db.add(rec)
    rec.song_id = song_id
    rec.old_value = result.current_value
    rec.new_value = result.correct_value
    rec.verdict = result.verdict
    rec.confidence = result.confidence
    rec.sources = [s.to_dict() for s in result.sources]
    rec.auto_applied = applied
    rec.checked_at = datetime.now(timezone.utc)
    return rec
