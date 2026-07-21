"""Tests del Motor de Consenso de Verificación (MCV) — funciones puras.

Blindan la POLÍTICA de decisión (qué se auto-corrige vs qué va al humano) y el
tiering de fuentes, que son el corazón del vuelco editorial. No tocan red ni BD:
el adjudicador LLM y la persistencia se prueban aparte con mocks/integración.
"""
from __future__ import annotations

from app.services import consensus as c
from app.services.consensus import ConsensusResult, SourceRef, decide


def _src(kind, value, stance="supports", name=None):
    return SourceRef(name=name or kind, source_kind=kind, value=value, stance=stance)


# --- Tiering ---------------------------------------------------------------- #
def test_tiering_conocido_y_desconocido():
    assert c.source_tier("wikipedia") == 1
    assert c.source_tier("lrclib") == 2
    assert c.source_tier("reddit") == 3
    assert c.source_tier("loquesea") == 3  # desconocido → conservador T3


# --- Política: corrección con respaldo T1 se auto-aplica -------------------- #
def test_una_t1_respalda_correccion_auto_aplica():
    r = ConsensusResult(
        verdict="corrected", confidence=0.8,
        current_value="llega", correct_value="lleva",
        sources=[_src("wikipedia", "lleva"), _src("lrclib", "lleva")],
    )
    assert decide(r) == "auto_apply"


# --- Política: dos T2 respaldan → auto-aplica ------------------------------- #
def test_dos_t2_respaldan_auto_aplica():
    r = ConsensusResult(
        verdict="corrected", confidence=0.75,
        current_value="llega", correct_value="lleva",
        sources=[_src("lrclib", "lleva"), _src("letras_com", "lleva")],
    )
    assert decide(r) == "auto_apply"


# --- Política: una sola T2 NO basta → humano ------------------------------- #
def test_una_sola_t2_no_basta():
    r = ConsensusResult(
        verdict="corrected", confidence=0.75,
        current_value="llega", correct_value="lleva",
        sources=[_src("lrclib", "lleva")],
    )
    assert decide(r) == "needs_human"


# --- Política: una T1 que CONTRADICE bloquea la auto-corrección ------------- #
def test_t1_contradictoria_bloquea():
    r = ConsensusResult(
        verdict="corrected", confidence=0.9,
        current_value="llega", correct_value="lleva",
        sources=[
            _src("lrclib", "lleva"),
            _src("letras_com", "lleva"),
            _src("wikipedia", "llega", stance="contradicts"),
        ],
    )
    assert decide(r) == "needs_human"


# --- Política: confianza baja → humano ------------------------------------- #
def test_confianza_baja_va_a_humano():
    r = ConsensusResult(
        verdict="corrected", confidence=0.4,
        current_value="llega", correct_value="lleva",
        sources=[_src("wikipedia", "lleva")],
    )
    assert decide(r) == "needs_human"


# --- Política: alto riesgo (re-atribución) siempre a humano ---------------- #
def test_alto_riesgo_siempre_humano():
    r = ConsensusResult(
        verdict="corrected", confidence=0.95,
        current_value="Robe", correct_value="Manolo Chinato",
        sources=[_src("wikipedia", "Manolo Chinato"), _src("curated", "Manolo Chinato")],
    )
    assert decide(r, high_risk=True) == "needs_human"


# --- Política: confirmado / conflicto / no-encontrado ---------------------- #
def test_confirmado_conflicto_nofound():
    assert decide(ConsensusResult(verdict="confirmed", confidence=0.9)) == "confirm_noop"
    assert decide(ConsensusResult(verdict="conflict", confidence=0.0)) == "needs_human"
    assert decide(ConsensusResult(verdict="not_found", confidence=0.0)) == "skip"


# --- Corrección de fan: exige corroboración EXTERNA ------------------------ #
def test_fan_corregida_con_corroboracion_externa_se_aplica():
    # caso real "llega/lleva": fan dice lleva, LRCLIB corrobora, letras.com no.
    sources = [
        _src("fan_feedback", "lleva"),
        _src("lrclib", "lleva"),
        _src("letras_com", "llega"),
    ]
    r = c.evaluate_hypothesis(hypothesis="lleva", current_value="llega", sources=sources)
    assert r.verdict == "corrected"
    assert c.decide_fan_correction(r, "lleva") == "auto_apply"


def test_fan_sin_corroboracion_va_a_humano():
    # solo el fan lo dice; nadie externo lo corrobora → no se aplica.
    sources = [
        _src("fan_feedback", "lleva"),
        _src("lrclib", "llega"),
        _src("letras_com", "llega"),
    ]
    r = c.evaluate_hypothesis(hypothesis="lleva", current_value="llega", sources=sources)
    assert c.decide_fan_correction(r, "lleva") == "needs_human"


def test_fan_contradicha_por_t1_va_a_humano():
    sources = [
        _src("fan_feedback", "lleva"),
        _src("lrclib", "lleva"),
        _src("wikipedia", "llega", stance="contradicts"),
    ]
    r = c.evaluate_hypothesis(hypothesis="lleva", current_value="llega", sources=sources)
    # wikipedia (T1) contradice → bloquea
    assert c.decide_fan_correction(r, "lleva") == "needs_human"


def test_hipotesis_igual_al_actual_es_confirmada():
    r = c.evaluate_hypothesis(
        hypothesis="llega", current_value="llega",
        sources=[_src("lrclib", "llega")],
    )
    assert r.verdict == "confirmed"


# --- Confianza agregada: T1 pesa más que T3 -------------------------------- #
def test_confianza_agregada_pondera_tier():
    solo_t3 = c.aggregate_confidence([_src("reddit", "x")], "x")
    una_t1 = c.aggregate_confidence([_src("wikipedia", "x")], "x")
    assert una_t1 > solo_t3
    # contradicción resta
    con_contra = c.aggregate_confidence(
        [_src("wikipedia", "x"), _src("forum", "y", stance="contradicts")], "x"
    )
    assert con_contra < una_t1
