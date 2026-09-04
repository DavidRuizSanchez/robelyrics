"""Autoprogramación de la cola de Instagram.

Reparte los posts ya aprobados por las próximas semanas, igual que hace el
calendario del blog (`admin_proposals_auto_schedule`), pero con las dos
particularidades de Instagram:

  - Aquí importa la HORA, no solo el día: se reparte en slots horarios.
  - La mezcla se hace por `content_type`, intercalando para que no salgan tres
    versos seguidos.

Respeta el techo semanal derivado del cuentagotas (`config.STEADY_INTERVAL_H`),
así que autoprogramar no puede saltarse la cadencia acordada.

SOBRE LAS HORAS: son una convención, NO un dato de rendimiento. No hay métricas
propias de la cuenta todavía (hacen falta los insights de Meta, que requieren el
permiso `instagram_manage_insights`). Cuando los haya, estos slots deberían
derivarse de la hora real a la que responde la audiencia. Hasta entonces se
declaran configurables por entorno y no se presentan como "las mejores horas".
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem
from app.services.instagram import config

logger = logging.getLogger(__name__)

# La cuenta es española: se programa pensando en hora local y se guarda en UTC.
TZ = ZoneInfo(os.getenv("IG_TIMEZONE", "Europe/Madrid"))

# Slots horarios por día (hora local). Convención, no dato — ver cabecera.
# Formato del env: "13:30,20:30".
_SLOTS_RAW = os.getenv("IG_SLOTS", "13:30,20:30")

# Estados que ocupan sitio en el calendario.
ACTIVOS = ("pending", "prepared")


def slots_diarios() -> list[time]:
    """Horas locales de publicación, ordenadas."""
    out: list[time] = []
    for trozo in _SLOTS_RAW.split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            h, m = trozo.split(":")
            out.append(time(int(h), int(m)))
        except (ValueError, IndexError):
            logger.warning("[IG] slot horario inválido en IG_SLOTS: %r", trozo)
    return sorted(out) or [time(13, 30), time(20, 30)]


def cap_semanal() -> int:
    """Posts por semana que permite el cuentagotas.

    Se deriva de `STEADY_INTERVAL_H` en vez de ser un número aparte: así no
    puede haber dos cadencias distintas contradiciéndose (una en el cron y otra
    en el calendario).
    """
    return max(1, round(24 * 7 / max(config.STEADY_INTERVAL_H, 1)))


def _lunes_de(d: datetime) -> datetime.date:
    local = d.astimezone(TZ)
    return (local - timedelta(days=local.weekday())).date()


def _ocupacion_semanal(db: Session) -> dict:
    """Cuántos posts hay ya comprometidos por semana (lunes local → nº).

    Cuenta lo programado a mano, las efemérides con día fijo y lo ya publicado:
    todo eso ocupa sitio real en el feed.
    """
    conteo: dict = {}
    filas = db.execute(
        select(
            InstagramQueueItem.publish_at,
            InstagramQueueItem.publish_on,
            InstagramQueueItem.published_at,
        ).where(
            InstagramQueueItem.status.in_((*ACTIVOS, "published"))
        )
    ).all()
    for publish_at, publish_on, published_at in filas:
        momento = publish_at or published_at
        if momento is not None:
            lunes = _lunes_de(momento)
        elif publish_on is not None:
            lunes = publish_on - timedelta(days=publish_on.weekday())
        else:
            continue
        conteo[lunes] = conteo.get(lunes, 0) + 1
    return conteo


def _ocupados(db: Session) -> set[datetime]:
    """Instantes ya tomados, para no encajar dos posts en el mismo slot."""
    return {
        p for (p,) in db.execute(
            select(InstagramQueueItem.publish_at).where(
                InstagramQueueItem.publish_at.is_not(None),
                InstagramQueueItem.status.in_((*ACTIVOS, "published")),
            )
        ).all() if p is not None
    }


def _intercalar(items: list[InstagramQueueItem]) -> list[InstagramQueueItem]:
    """Round-robin por `content_type` para que no caigan tres versos seguidos.

    Mismo criterio que el botón «alternar tipos» que ya existe en el panel.
    """
    cubos: dict[str, list[InstagramQueueItem]] = {}
    for it in items:
        cubos.setdefault(it.content_type or "news", []).append(it)
    orden = sorted(cubos.keys())
    salida: list[InstagramQueueItem] = []
    while any(cubos.values()):
        for clave in orden:
            if cubos[clave]:
                salida.append(cubos[clave].pop(0))
    return salida


# Cuota máxima por tipo de contenido, como fracción del feed. Es una decisión
# EDITORIAL: los posts que enseñan la web son el gancho de registro, y pasado
# cierto punto la cuenta deja de ser un cancionero y es un folleto.
CUOTA_POR_TIPO: dict[str, float] = {"product": 0.10}


def cupo_semanal(tipo: str) -> int:
    """Cuántos posts de ese tipo caben por semana. Sin cuota, no hay tope."""
    fraccion = CUOTA_POR_TIPO.get(tipo)
    if fraccion is None:
        return cap_semanal()
    return max(1, round(cap_semanal() * fraccion))


def _ocupacion_por_tipo(db: Session, tipo: str) -> dict:
    """Posts de ese tipo ya comprometidos por semana (lunes local → nº)."""
    conteo: dict = {}
    filas = db.execute(
        select(
            InstagramQueueItem.publish_at,
            InstagramQueueItem.publish_on,
            InstagramQueueItem.published_at,
        ).where(
            InstagramQueueItem.status.in_((*ACTIVOS, "published")),
            InstagramQueueItem.content_type == tipo,
        )
    ).all()
    for publish_at, publish_on, published_at in filas:
        momento = publish_at or published_at
        if momento is not None:
            lunes = _lunes_de(momento)
        elif publish_on is not None:
            lunes = publish_on - timedelta(days=publish_on.weekday())
        else:
            continue
        conteo[lunes] = conteo.get(lunes, 0) + 1
    return conteo


def cupo_libre(db: Session, tipo: str, weeks: int = 4) -> int:
    """Cuántos posts más de ese tipo caben en las próximas semanas.

    Cuenta también los que aún no tienen fecha: si no, pulsar «✦ enseñar la web»
    cuatro veces seguidas metía dieciséis en la cola y luego la programación no
    tenía dónde ponerlos.
    """
    cupo = cupo_semanal(tipo)
    ocupados = sum(_ocupacion_por_tipo(db, tipo).values())
    sin_fecha = db.execute(
        select(func.count()).select_from(InstagramQueueItem).where(
            InstagramQueueItem.status.in_(ACTIVOS),
            InstagramQueueItem.content_type == tipo,
            InstagramQueueItem.publish_at.is_(None),
            InstagramQueueItem.publish_on.is_(None),
        )
    ).scalar() or 0
    return max(0, cupo * max(weeks, 1) - ocupados - sin_fecha)


def candidatos(db: Session) -> list[InstagramQueueItem]:
    """Items aprobados y aún sin momento asignado, en orden de cola."""
    return list(db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status.in_(ACTIVOS),
            InstagramQueueItem.publish_at.is_(None),
            InstagramQueueItem.publish_on.is_(None),
        )
        .order_by(
            InstagramQueueItem.position,
            InstagramQueueItem.slot,
            InstagramQueueItem.day,
            InstagramQueueItem.created_at,
        )
    ).scalars().all())


def plan(
    db: Session, weeks: int = 4, desde: datetime | None = None
) -> tuple[list[tuple[InstagramQueueItem, datetime]], list[dict]]:
    """Calcula (sin escribir nada) qué post va a qué hora.

    Devuelve `(asignaciones, descartes)`. Un descarte lleva su motivo, para que
    el panel pueda decir por qué se quedó algo fuera en vez de perderlo en
    silencio.
    """
    ahora = (desde or datetime.now(timezone.utc)).astimezone(timezone.utc)
    horas = slots_diarios()
    cap = cap_semanal()
    ocupacion = _ocupacion_semanal(db)
    tomados = _ocupados(db)
    # Ocupación por tipo, para los que tienen cuota propia (ver CUOTA_POR_TIPO).
    por_tipo = {t: _ocupacion_por_tipo(db, t) for t in CUOTA_POR_TIPO}

    pendientes = _intercalar(candidatos(db))
    asignaciones: list[tuple[InstagramQueueItem, datetime]] = []
    descartes: list[dict] = []

    # Primer día candidato: hoy (los slots ya pasados se descartan solos).
    dia = ahora.astimezone(TZ).date()
    fin = dia + timedelta(weeks=max(weeks, 1))

    for item in pendientes:
        colocado = False
        d = dia
        tipo = item.content_type or "news"
        cupo_tipo = cupo_semanal(tipo) if tipo in CUOTA_POR_TIPO else None
        while d <= fin:
            lunes = d - timedelta(days=d.weekday())
            if ocupacion.get(lunes, 0) >= cap:
                # Semana llena: salta al lunes siguiente de golpe.
                d = lunes + timedelta(days=7)
                continue
            if cupo_tipo is not None and por_tipo[tipo].get(lunes, 0) >= cupo_tipo:
                # Esta semana ya lleva su cuota de este tipo: a la siguiente.
                d = lunes + timedelta(days=7)
                continue
            for h in horas:
                momento_local = datetime.combine(d, h, tzinfo=TZ)
                momento = momento_local.astimezone(timezone.utc)
                if momento <= ahora or momento in tomados:
                    continue
                asignaciones.append((item, momento))
                tomados.add(momento)
                ocupacion[lunes] = ocupacion.get(lunes, 0) + 1
                if cupo_tipo is not None:
                    por_tipo[tipo][lunes] = por_tipo[tipo].get(lunes, 0) + 1
                colocado = True
                break
            if colocado:
                break
            d += timedelta(days=1)

        if not colocado:
            motivo = f"sin hueco en {weeks} semanas (tope {cap}/semana)"
            if cupo_tipo is not None:
                motivo += f" o cuota de «{tipo}» llena ({cupo_tipo}/semana)"
            descartes.append({
                "id": item.id,
                "title": item.title[:80],
                "reason": motivo,
            })

    return asignaciones, descartes


def apply_plan(
    db: Session, asignaciones: list[tuple[InstagramQueueItem, datetime]]
) -> int:
    """Escribe las fechas calculadas. Devuelve cuántos items se programaron."""
    for item, momento in asignaciones:
        item.publish_at = momento
    db.commit()
    return len(asignaciones)


# --------------------------------------------------------------------------- #
# Reparto de FORMATOS
# --------------------------------------------------------------------------- #
# Mezcla objetivo del feed. Es una decisión EDITORIAL, no un dato: el nicho
# publica un 69% de vídeo, pero nuestro vídeo propio va sin audio (la música
# tiene derechos) y rinde peor que uno con sonido, así que no se copia esa
# proporción a ciegas. Formato del env: "REELS:4,CAROUSEL:3,IMAGE:3".
FORMAT_MIX_RAW = os.getenv("IG_FORMAT_MIX", "REELS:4,CAROUSEL:3,IMAGE:3")

# Formatos que el repartidor PUEDE asignar. Son los tres que valen para cualquier
# tema: una noticia o un verso se cuentan igual de bien en foto, carrusel o reel.
FORMATOS_VALIDOS = ("IMAGE", "CAROUSEL", "REELS")

# Formatos que NO se reparten porque no son una forma de contar un tema: son un
# tema en sí. Un CLIP es un vídeo concreto de un canal concreto y un PRODUCT es
# una consulta concreta a la web; ninguno se puede «asignar» a un post que iba de
# otra cosa. Se excluyen aquí explícitamente y no solo vía `media_locked`, que es
# una marca que se puede quitar desde el panel sin querer.
FORMATOS_PROPIOS = ("CLIP", "PRODUCT")


def mezcla_formatos() -> list[str]:
    """La mezcla desplegada en una lista, p.ej. [REELS, REELS, CAROUSEL, IMAGE…]."""
    salida: list[str] = []
    for trozo in FORMAT_MIX_RAW.split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            fmt, n = trozo.split(":")
            fmt = fmt.strip().upper()
            if fmt in FORMATOS_VALIDOS:
                salida.extend([fmt] * max(int(n), 0))
            else:
                logger.warning("[IG] formato desconocido en IG_FORMAT_MIX: %r", fmt)
        except (ValueError, IndexError):
            logger.warning("[IG] tramo inválido en IG_FORMAT_MIX: %r", trozo)
    return salida or ["REELS", "CAROUSEL", "IMAGE"]


def _sin_repetir_seguidos(secuencia: list[str]) -> list[str]:
    """Reordena para que no caigan dos formatos iguales consecutivos.

    Va tomando siempre el formato que MÁS queda por colocar, evitando el que
    acaba de salir. Si solo queda uno, se acepta la repetición: mejor repetir
    que dejar posts sin formato.
    """
    from collections import Counter

    quedan = Counter(secuencia)
    salida: list[str] = []
    anterior = None
    while sum(quedan.values()):
        candidatos = [f for f in quedan if quedan[f] and f != anterior]
        if not candidatos:                       # solo queda el repetido
            candidatos = [f for f in quedan if quedan[f]]
        elegido = max(candidatos, key=lambda f: quedan[f])
        salida.append(elegido)
        quedan[elegido] -= 1
        anterior = elegido
    return salida


def repartir_formatos(
    db: Session, semilla: int = 0, solo_programados: bool = True
) -> list[dict]:
    """Asigna formato variado a los posts, respetando los fijados a mano.

    Sin esto el feed sale monótono: al activar el carrusel por defecto, 26 de los
    28 posts de la cola pasaron a ser carrusel de golpe.

    `semilla` desplaza el punto de arranque de la mezcla, así que volver a
    repartir con otra semilla da otro orden. Dentro de una misma semilla es
    determinista: repetir la operación no cambia nada.

    Devuelve la lista de cambios [{id, title, antes, ahora}] — los items que ya
    tenían el formato que les tocaba no aparecen.
    """
    q = select(InstagramQueueItem).where(
        InstagramQueueItem.status.in_(ACTIVOS),
        InstagramQueueItem.media_locked.is_(False),
        # Los clips y las piezas de la web tienen formato propio por naturaleza:
        # el repartidor los arrasaba (el botón manda `only_scheduled: false`, así
        # que barre toda la cola activa) y se quedaban sin su vídeo o su pieza.
        InstagramQueueItem.media_type.not_in(FORMATOS_PROPIOS),
    )
    if solo_programados:
        q = q.where(InstagramQueueItem.publish_at.is_not(None))
    items = list(db.execute(
        q.order_by(InstagramQueueItem.publish_at, InstagramQueueItem.position)
    ).scalars().all())
    if not items:
        return []

    base = mezcla_formatos()
    # Se repite la mezcla hasta cubrir todos los items y se desplaza por semilla.
    repeticiones = (len(items) // len(base)) + 1
    secuencia = (base * repeticiones)[:len(items)]
    if semilla:
        corte = semilla % len(secuencia)
        secuencia = secuencia[corte:] + secuencia[:corte]
    secuencia = _sin_repetir_seguidos(secuencia)

    cambios: list[dict] = []
    for item, formato in zip(items, secuencia):
        if item.media_type == formato:
            continue
        cambios.append({
            "id": item.id,
            "title": item.title[:70],
            "antes": item.media_type,
            "ahora": formato,
        })
        item.media_type = formato
        # El formato cambia ⇒ hay que regenerar el material.
        item.status = "pending"
        item.media.clear()
        item.image_path = None
    db.commit()
    return cambios
