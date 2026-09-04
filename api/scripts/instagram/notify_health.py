"""Aviso al admin cuando Instagram deja de publicar.

El 24-ago-2026 Meta restringió la cuenta y la publicación se paró. Nadie se
enteró hasta el 4 de septiembre, once días después, porque NADA vigilaba esto:
`publish_next` termina con `sys.exit(1)` cuando falla, pero ese código lo
recogía el cron y lo tiraba a un log de 8 MB que no lee nadie.

Va aparte del digest de las 09:15 (`scripts.notify_review`) a propósito: aquel
corta en seco si no hay erratas ni posts por revisar, así que una caída de IG en
una semana tranquila habría quedado silenciada — exactamente el fallo que esto
viene a cerrar. Lo que sí se reutiliza es su maquinaria: `send_email` y la firma
anti-spam en `notification_digests`.

Cuatro motivos para sonar, de más grave a menos:
  1. Meta nos está bloqueando ahora mismo (cortacircuitos abierto).
  2. Llevamos ALERT_STALE_H sin publicar TENIENDO material. Este es el detector
     que no depende de reconocer ningún código: cubre el cron muerto, docker
     caído, Cloudinary y cualquier bug futuro.
  3. Hay posts que agotaron sus intentos y ya no volverán solos.
  4. La cola está vacía (leve: no es una avería, es que falta material).

Silencio por defecto. La firma lleva la sequía por TRAMOS (2/4/7/14/30 días), no
en horas: si no cambia nada no hay correo diario, pero al empeorar vuelve a sonar.

Uso:
  python -m scripts.instagram.notify_health
  python -m scripts.instagram.notify_health --dry-run
  python -m scripts.instagram.notify_health --force
"""
from __future__ import annotations

import argparse
import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import InstagramQueueItem, NotificationDigest
from app.db.session import SessionLocal
from app.services.instagram import config, publisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SITE = "https://entreinteriores.com"
_KIND = "instagram_health"

# Cada cuánto se repite un aviso que no ha cambiado. Más corto que el del digest
# editorial (14 días): esto es una avería, no una tarea que pueda esperar.
REMINDER_DAYS = 3

# Tramos de sequía para la firma. Sin ellos el correo saldría cada día (las horas
# cambian siempre); con ellos suena al entrar en cada escalón.
TRAMOS_DIAS = (2, 4, 7, 14, 30)


def _tramo(dias: float) -> int:
    """El escalón de sequía en el que estamos."""
    escalon = 0
    for t in TRAMOS_DIAS:
        if dias >= t:
            escalon = t
    return escalon


def _gather(db) -> dict:
    ahora = datetime.now(UTC)
    bloqueado, motivo, desde = publisher.publicacion_bloqueada(db)

    ultimo = db.execute(
        select(func.max(InstagramQueueItem.published_at)).where(
            InstagramQueueItem.status == "published"
        )
    ).scalar_one_or_none()
    if ultimo is not None and ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=UTC)
    if ultimo is None:
        # Nunca se publicó nada: el suelo es el item más antiguo de la cola, o
        # ahora mismo si la cola está vacía. Sin esto, una instalación nueva no
        # avisaría jamás porque `horas_sin_publicar` sería infinito o nulo.
        ultimo = db.execute(
            select(func.min(InstagramQueueItem.created_at))
        ).scalar_one_or_none()
        if ultimo is not None and ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=UTC)
    horas = (ahora - ultimo).total_seconds() / 3600 if ultimo else 0.0

    publicables = db.execute(
        select(func.count(InstagramQueueItem.id)).where(publisher._publicable())
    ).scalar_one()

    condenados = db.execute(
        select(func.count(InstagramQueueItem.id)).where(
            InstagramQueueItem.status == "failed",
            InstagramQueueItem.attempts >= config.MAX_PUBLISH_ATTEMPTS,
        )
    ).scalar_one()

    codigos = db.execute(
        select(InstagramQueueItem.error_code, func.count(InstagramQueueItem.id))
        .where(
            InstagramQueueItem.status == "failed",
            InstagramQueueItem.error_code.is_not(None),
        )
        .group_by(InstagramQueueItem.error_code)
        .order_by(func.count(InstagramQueueItem.id).desc())
        .limit(5)
    ).all()

    return {
        "bloqueado": bloqueado,
        "motivo": motivo,
        "desde": desde,
        "ultimo": ultimo,
        "horas_sin_publicar": horas,
        "publicables": int(publicables),
        "condenados": int(condenados),
        "codigos": [(c or "-", int(n)) for c, n in codigos],
    }


def _problemas(data: dict) -> list[str]:
    """Qué está mal, en cristiano. Vacío = todo bien y no hay correo."""
    fuera = []
    if data["bloqueado"]:
        fuera.append(f"Meta está bloqueando la publicación: {data['motivo']}")
    if (
        data["horas_sin_publicar"] >= config.ALERT_STALE_H
        and data["publicables"] > 0
    ):
        fuera.append(
            f"{data['horas_sin_publicar'] / 24:.1f} días sin publicar teniendo "
            f"{data['publicables']} post(s) listos"
        )
    if data["condenados"]:
        fuera.append(
            f"{data['condenados']} post(s) agotaron sus intentos y ya no vuelven solos"
        )
    if data["publicables"] == 0 and not data["bloqueado"]:
        fuera.append("la cola está vacía: no hay nada que publicar")
    return fuera


def _signature(data: dict) -> str:
    partes = [
        "b:" + (data["motivo"] or "-" if data["bloqueado"] else "-"),
        f"t:{_tramo(data['horas_sin_publicar'] / 24)}",
        f"c:{data['condenados']}",
        f"v:{int(data['publicables'] == 0)}",
    ]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:64]


def _should_send(db, problemas: list[str], signature: str) -> tuple[bool, str]:
    if not problemas:
        return False, "Instagram va bien"
    last = db.execute(
        select(NotificationDigest)
        .where(NotificationDigest.kind == _KIND)
        .order_by(NotificationDigest.sent_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return True, "primer aviso"
    if last.signature != signature:
        return True, "ha cambiado algo"
    sent_at = last.sent_at
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=UTC)
    edad = datetime.now(UTC) - sent_at
    if edad >= timedelta(days=REMINDER_DAYS):
        return True, f"recordatorio ({edad.days} días sin avisar)"
    return False, "lo mismo que el último aviso"


def _build_html(data: dict, problemas: list[str]) -> str:
    fecha = data["ultimo"].strftime("%d-%m-%Y %H:%M UTC") if data["ultimo"] else "nunca"
    p = [
        "<div style='background:#0d0b0a;color:#ede4d3;padding:24px;"
        "font-family:Georgia,serif'>",
        "<h2 style='color:#a83a3a;margin:0 0 16px'>Instagram · algo va mal</h2>",
        "<ul style='line-height:1.7'>",
    ]
    p += [f"<li>{x}</li>" for x in problemas]
    p.append("</ul>")
    p.append(
        f"<p style='color:#9a8f80'>Última publicación: <b>{fecha}</b> · "
        f"en cola: <b>{data['publicables']}</b> · "
        f"sin intentos: <b>{data['condenados']}</b></p>"
    )
    if data["codigos"]:
        filas = "".join(
            f"<tr><td style='padding:2px 12px 2px 0'><code>{c}</code></td>"
            f"<td>{n}</td></tr>"
            for c, n in data["codigos"]
        )
        p.append(
            "<p style='color:#9a8f80'>Códigos de error en la cola:</p>"
            f"<table style='color:#ede4d3'>{filas}</table>"
        )
    if data["bloqueado"] and (data["motivo"] or "").startswith("25/2207050"):
        p.append(
            "<p style='background:#2a1414;padding:12px;border-left:3px solid #a83a3a'>"
            "<b>Esto lo tienes que resolver tú, no se arregla solo.</b><br>"
            "Meta ha restringido la cuenta. Entra en "
            "<a style='color:#a83a3a' href='https://www.instagram.com/'>instagram.com</a> "
            "<b>desde el navegador</b> con @entreinterioresrobe y completa lo que "
            "pida (Estado de la cuenta / verificación de identidad). Mientras tanto "
            "el sistema no gasta nada: ha dejado de subir imágenes y de crear "
            "publicaciones que Meta iba a rechazar.</p>"
        )
    if data["condenados"]:
        p.append(
            "<p style='color:#9a8f80'>Para devolver a la cola lo recuperable y "
            "descartar lo caducado:<br>"
            "<code style='color:#ede4d3'>python -m scripts.instagram.recover_failed "
            "--dry-run</code></p>"
        )
    p.append(
        f"<p><a style='color:#a83a3a' href='{_SITE}/biblioteca/admin/instagram'>"
        "Abrir el panel de Instagram</a></p></div>"
    )
    return "".join(p)


def main() -> None:
    ap = argparse.ArgumentParser(description="Aviso de salud del pipeline de Instagram.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="manda aunque no haya novedad")
    args = ap.parse_args()

    to = get_settings().admin_email
    if not to:
        logger.warning("Sin ADMIN_EMAIL configurado; no se envía.")
        return

    db = SessionLocal()
    try:
        data = _gather(db)
        problemas = _problemas(data)
        signature = _signature(data)
        send, why = _should_send(db, problemas, signature)
        logger.info(
            "IG: %.1f h sin publicar · %d en cola · %d sin intentos · bloqueado=%s",
            data["horas_sin_publicar"], data["publicables"], data["condenados"],
            data["bloqueado"],
        )
        if not send and not args.force:
            logger.info("No se envía aviso: %s.", why)
            return
        if not problemas:
            problemas = ["(sin problemas; enviado con --force)"]

        subject = f"[Entre Interiores] Instagram: {problemas[0][:90]}"
        html = _build_html(data, problemas)
        if args.dry_run:
            logger.info("(dry-run) enviaría a %s (%s): %s", to, why, subject)
            for x in problemas:
                logger.info("  · %s", x)
            return

        from app.services.email import send_email

        mid = send_email(to, subject, html)
        db.add(
            NotificationDigest(
                kind=_KIND, signature=signature,
                sent_at=datetime.now(UTC),
            )
        )
        db.commit()
        logger.info("Aviso enviado a %s (%s, id=%s)", to, why, mid)
    finally:
        db.close()


if __name__ == "__main__":
    main()
