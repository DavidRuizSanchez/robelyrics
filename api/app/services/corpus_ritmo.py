"""Ritmo y gasto de la ingesta del corpus: qué se transcribe, en qué orden y cuánto cuesta.

Objetivo de David (23-10-2026): entre 10 y 20 fuentes nuevas por semana, con un
tope de 15 $ al mes en Whisper, y los subtítulos de YouTube (gratis) antes que
Whisper. La búsqueda trae más de lo que cabe, y la pasada de histórico de golpe
quemaría el mes en un día: el tope semanal es lo que reparte.

El gasto NO se apunta en ningún contador: se deduce de la propia cola (lo que
está en `done` con `via='whisper'` este mes, por su duración). Así no hay un
número que pueda desincronizarse del trabajo hecho, y si el daemon muere a
medias no se cobra nada que no se haya hecho.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models import YouTubeIngestQueue

WHISPER_USD_POR_MIN = 0.006      # precio de whisper-1 (OpenAI)
PRESUPUESTO_MES_USD = 15.0
MAX_DONE_SEMANA = 20
# Un A con subtítulos AUTOMÁTICOS y corto pasa por Whisper aunque haya
# subtítulos: la atribución de voz pide calidad, y 20 min son 0,12 $.
WHISPER_EN_A_HASTA_S = 20 * 60
# Sin duración conocida (un audio suelto de pódcast, una fila vieja) se supone la
# de un programa largo: suponer cero es dejar pasar cualquier cosa.
PEOR_CASO_SIN_DURACION_S = 2 * 60 * 60

# A antes que B antes que C. Lo que no tiene nivel (canales vigilados,
# inventario) va con C: es como estaba antes de los niveles.
ORDEN_NIVEL = case((YouTubeIngestQueue.nivel == "A", 0), (YouTubeIngestQueue.nivel == "B", 1),
                   else_=2)


def _inicio_de_mes(ahora: datetime) -> datetime:
    return ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def minutos_whisper_mes(db: Session, ahora: datetime | None = None) -> float:
    ahora = ahora or datetime.now(UTC)
    seg = (db.query(func.coalesce(func.sum(YouTubeIngestQueue.duration_s), 0.0))
           .filter(YouTubeIngestQueue.status == "done", YouTubeIngestQueue.via == "whisper",
                   YouTubeIngestQueue.done_at >= _inicio_de_mes(ahora))
           .scalar())
    return float(seg or 0.0) / 60.0


def whisper_sin_duracion_mes(db: Session, ahora: datetime | None = None) -> int:
    """Lo transcrito con Whisper este mes sin duración apuntada: el gasto no lo
    cuenta, así que con alguno el gasto es una cota inferior."""
    ahora = ahora or datetime.now(UTC)
    return (db.query(func.count(YouTubeIngestQueue.id))
            .filter(YouTubeIngestQueue.status == "done", YouTubeIngestQueue.via == "whisper",
                    YouTubeIngestQueue.duration_s.is_(None),
                    YouTubeIngestQueue.done_at >= _inicio_de_mes(ahora))
            .scalar()) or 0


def gasto_mes_usd(db: Session, ahora: datetime | None = None) -> float:
    return round(minutos_whisper_mes(db, ahora) * WHISPER_USD_POR_MIN, 2)


def minutos_whisper_restantes(db: Session, ahora: datetime | None = None) -> float:
    return max(0.0, PRESUPUESTO_MES_USD / WHISPER_USD_POR_MIN - minutos_whisper_mes(db, ahora))


def hechos_semana(db: Session, ahora: datetime | None = None) -> int:
    ahora = ahora or datetime.now(UTC)
    return (db.query(func.count(YouTubeIngestQueue.id))
            .filter(YouTubeIngestQueue.status == "done",
                    YouTubeIngestQueue.done_at >= ahora - timedelta(days=7))
            .scalar()) or 0


def hueco_semana(db: Session, ahora: datetime | None = None) -> int:
    return max(0, MAX_DONE_SEMANA - hechos_semana(db, ahora))


def whisper_permitido(duracion_s: float | None, restantes_min: float) -> bool:
    """Si cabe en lo que queda del mes. Sin duración conocida, se supone el peor caso."""
    if restantes_min <= 0:
        return False
    return (duracion_s or PEOR_CASO_SIN_DURACION_S) / 60.0 <= restantes_min


def resumen(db: Session, ahora: datetime | None = None) -> dict:
    """Lo que enseñan el panel y el correo semanal."""
    return {
        "gasto_mes_usd": gasto_mes_usd(db, ahora),
        "presupuesto_mes_usd": PRESUPUESTO_MES_USD,
        "minutos_whisper_mes": round(minutos_whisper_mes(db, ahora), 1),
        "whisper_sin_duracion": whisper_sin_duracion_mes(db, ahora),
        "hechos_semana": hechos_semana(db, ahora),
        "max_semana": MAX_DONE_SEMANA,
    }
