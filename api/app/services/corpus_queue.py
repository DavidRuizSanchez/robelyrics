"""La cola de ingesta de YouTube, vista y decidida desde el panel.

Hasta el 24-10-2026 la cola no tenía pantalla: un vídeo detectado solo se
aprobaba con el botón del correo, y si el correo se perdía se quedaba en
`detected` para siempre (el teaser #50 esperó 11 días). Aquí están las mismas
decisiones que en el correo, una a una, más reintentar lo que falló y retirar
lo que ya entró.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import InterpretationSource, SongInterpretation, YouTubeIngestQueue

# Donde puede estar vectorizada una fuente. El embed es semanal, así que lo
# recién entrado puede no tener puntos todavía: borrar cero no es un error.
COLECCIONES = ("interpretations_v1", "robe_voice_v1")

ESTADOS = ("detected", "approved", "processing", "done", "failed", "retired")
# Lo que se enseña de cada estado. Lo terminado ocupa mucho y decide poco.
LIMITES = {"detected": 300, "approved": 100, "processing": 50, "failed": 100,
           "done": 30, "retired": 30}

_ACCIONES = {
    # acción → (estados de los que se puede salir, estado al que se llega)
    "aprobar": (("detected",), "approved"),
    "descartar": (("detected", "failed"), "retired"),
    "reintentar": (("failed",), "approved"),
    "retirar": (("done",), "retired"),
}


class AccionNoValida(ValueError):
    pass


def _fila(r: YouTubeIngestQueue) -> dict:
    return {
        "id": r.id, "video_id": r.video_id, "url": r.url, "title": r.title,
        "channel": r.channel, "kind": r.kind, "target": r.target, "status": r.status,
        "nivel": r.nivel, "voces": r.voces or [], "motivos": r.motivos or [],
        "descubierto_por": r.descubierto_por, "duration_s": r.duration_s,
        "error": r.error, "attempts": r.attempts,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "done_at": r.done_at.isoformat() if r.done_at else None,
    }


def listar(db: Session) -> dict:
    """Recuento exacto por estado (COUNT) y las filas de cada estado, con tope."""
    cuenta = {e: 0 for e in ESTADOS}
    for estado, n in (db.query(YouTubeIngestQueue.status, func.count(YouTubeIngestQueue.id))
                      .group_by(YouTubeIngestQueue.status).all()):
        cuenta[estado] = int(n)
    filas = {}
    for estado in ESTADOS:
        orden = (YouTubeIngestQueue.done_at.desc() if estado == "done"
                 else YouTubeIngestQueue.created_at.desc())
        q = db.query(YouTubeIngestQueue).filter(YouTubeIngestQueue.status == estado)
        if estado == "detected":
            # Primero lo que más pesa: A, B, C y lo antiguo sin nivel al final.
            nivel = func.coalesce(YouTubeIngestQueue.nivel, "Z")
            q = q.order_by(nivel, YouTubeIngestQueue.created_at.asc())
        else:
            q = q.order_by(orden)
        filas[estado] = [_fila(r) for r in q.limit(LIMITES[estado]).all()]
    return {"cuenta": cuenta, "filas": filas}


def _retirar_fuente(db: Session, r: YouTubeIngestQueue, qdrant) -> dict:
    """Saca del corpus lo que entró por este vídeo: la fuente, sus tramos
    (CASCADE) y sus puntos en Qdrant. El consenso destilado que ya la citara no
    se reescribe aquí: se avisa, porque re-destilar es otra decisión."""
    fuente = (db.query(InterpretationSource)
              .filter(InterpretationSource.kind == r.kind, InterpretationSource.url == r.url)
              .one_or_none())
    if fuente is None:
        return {"fuente": None, "puntos_borrados": False, "consensos_que_la_citan": []}
    if qdrant is None:
        from app.services.qdrant_client import get_qdrant
        qdrant = get_qdrant()
    from qdrant_client.http.models import FieldCondition, Filter, FilterSelector, MatchValue

    filtro = Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=fuente.id))])
    for coleccion in COLECCIONES:
        if qdrant.collection_exists(coleccion):
            qdrant.delete(collection_name=coleccion,
                          points_selector=FilterSelector(filter=filtro), wait=True)
    citan = [si.song_id for si in db.query(SongInterpretation).all()
             if fuente.id in (si.source_ids or [])]
    fuente_id = fuente.id
    db.delete(fuente)
    return {"fuente": fuente_id, "puntos_borrados": True, "consensos_que_la_citan": citan}


def decidir(db: Session, item_id: int, accion: str, qdrant=None) -> dict:
    if accion not in _ACCIONES:
        raise AccionNoValida(f"acción desconocida: {accion}")
    desde, hasta = _ACCIONES[accion]
    r = db.get(YouTubeIngestQueue, item_id)
    if r is None:
        raise LookupError(item_id)
    if r.status not in desde:
        raise AccionNoValida(f"no se puede {accion} un vídeo en estado «{r.status}»")
    retirada = _retirar_fuente(db, r, qdrant) if accion == "retirar" else None
    r.status = hasta
    if hasta == "approved":
        r.approved_at = datetime.now(UTC)
    if accion == "reintentar":
        r.attempts = 0
        r.error = None
    db.commit()
    fila = _fila(r)
    if retirada is not None:
        fila["retirada"] = retirada
    return fila
