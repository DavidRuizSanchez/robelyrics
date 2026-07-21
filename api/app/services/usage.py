"""Registro de uso de features (F2.4).

Guarda en BD el TEXTO de las consultas del buscador/completar/mood (para saber qué
busca la gente y qué huecos de contenido revela). El ratio agregado de uso va aparte
a GA4 (eventos, sin PII). Nunca lanza: un fallo de logging no puede tumbar la feature.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_feature_query(db, feature: str, query: str, *, n_results: int | None = None, user_id: int | None = None) -> None:
    if not query:
        return
    try:
        from app.db.models import FeatureQuery

        db.add(FeatureQuery(
            feature=feature, query=query.strip()[:500],
            n_results=n_results, user_id=user_id,
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 — nunca romper la feature por el log
        logger.warning("[usage] no se pudo registrar '%s': %s", feature, exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
