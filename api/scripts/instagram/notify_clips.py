"""Correo de los clips propuestos, con el vídeo YA MONTADO y un clic por clip.

Orden deliberado: `propose_clips` encola, el daemon de la Mac baja el tramo y lo
monta, y SOLO ENTONCES se avisa. Así el correo lleva el enlace al vídeo real,
que es lo que pidió David el 22-09-2026: «con mi validación sobre los clips ya
creados». Avisar antes sería pedir que apruebe una idea.

Un botón por clip, nunca un «aprobar todos»: un clip es un vídeo de otra
persona publicado sin pedir permiso, y esas se deciden de una en una. Mismo
criterio que el correo de oportunidades SEO.

Silencio por defecto: si no hay clips montados esperando, no se manda nada.

Uso:
    python -m scripts.instagram.notify_clips --dry-run
    python -m scripts.instagram.notify_clips
"""
from __future__ import annotations

import argparse
import logging
import os

from sqlalchemy import select

from app.db.models import InstagramQueueItem, VideoClip
from app.db.session import SessionLocal
from app.services.auth import create_clip_action_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("clips")

COL_FONDO = "#0d0b0a"
COL_PAPEL = "#ede4d3"
COL_GRANATE = "#a83a3a"


def _pendientes(db) -> list[tuple[VideoClip, InstagramQueueItem]]:
    """Clips montados cuya publicación espera el visto bueno."""
    filas = db.execute(
        select(VideoClip, InstagramQueueItem)
        .join(InstagramQueueItem, VideoClip.queue_item_id == InstagramQueueItem.id)
        .where(
            VideoClip.status == "ready",
            InstagramQueueItem.status == "proposed",
            InstagramQueueItem.content_type == "clip",
        )
        .order_by(VideoClip.id)
    ).all()
    return [(c, i) for c, i in filas]


def _ficha_html(clip: VideoClip, item: InstagramQueueItem, site: str) -> str:
    aprobar = create_clip_action_token(clip.id, "approve")
    rechazar = create_clip_action_token(clip.id, "reject")
    resumen = (item.summary or "").strip()
    aviso = ""
    if "AVISO:" in resumen:
        aviso = (
            f'<p style="font-family:\'Courier New\',monospace;font-size:11px;'
            f'color:{COL_GRANATE};margin:8px 0 0;">⚠ '
            + resumen.split("AVISO:", 1)[1].split("\n")[0].strip()
            + "</p>"
        )
    detalle = "<br>".join(
        linea for linea in resumen.splitlines()
        if not linea.startswith(("Transcripción", "AVISO:"))
    )
    transcripcion = next(
        (linea[len("Transcripción del tramo: "):]
         for linea in resumen.splitlines()
         if linea.startswith("Transcripción del tramo: ")), "",
    )
    return f"""
<div style="border:1px solid rgba(237,228,211,0.12);padding:18px;margin:0 0 20px;">
  <h2 style="font-family:Georgia,serif;font-size:19px;color:{COL_PAPEL};margin:0 0 6px;">
    {item.title}</h2>
  <p style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:2px;
     text-transform:uppercase;color:rgba(237,228,211,0.55);margin:0 0 10px;">
    {clip.start_s:.0f}s – {clip.end_s:.0f}s · {(clip.end_s - clip.start_s):.0f} segundos</p>
  <p style="font-family:Georgia,serif;font-size:13px;color:rgba(237,228,211,0.75);
     line-height:1.6;margin:0 0 10px;">{detalle}</p>
  <p style="font-family:Georgia,serif;font-style:italic;font-size:13px;
     color:rgba(237,228,211,0.6);line-height:1.6;margin:0 0 12px;">
    «{transcripcion[:400]}»</p>
  {aviso}
  <p style="margin:14px 0 0;">
    <a href="{clip.url_cdn}" style="font-family:'Courier New',monospace;font-size:12px;
       color:{COL_PAPEL};text-decoration:underline;">▶ Ver el clip montado</a>
  </p>
  <p style="margin:16px 0 0;">
    <a href="{site}/api/public/clip-action?token={aprobar}"
       style="display:inline-block;background:{COL_GRANATE};color:{COL_FONDO};
       font-family:'Courier New',monospace;font-size:12px;letter-spacing:2px;
       text-transform:uppercase;text-decoration:none;padding:11px 20px;">
       Publicar este</a>
    <a href="{site}/api/public/clip-action?token={rechazar}"
       style="display:inline-block;margin-left:10px;color:rgba(237,228,211,0.6);
       font-family:'Courier New',monospace;font-size:12px;letter-spacing:2px;
       text-transform:uppercase;text-decoration:none;padding:11px 14px;">
       Descartar</a>
  </p>
</div>"""


def _render(pares, site: str) -> tuple[str, str]:
    fichas = "".join(_ficha_html(c, i, site) for c, i in pares)
    n = len(pares)
    html = (
        f'<div style="background:{COL_FONDO};padding:32px 24px;max-width:640px;'
        f'margin:0 auto;">'
        f'<p style="font-family:\'Courier New\',monospace;font-size:10px;'
        f'letter-spacing:3px;text-transform:uppercase;color:rgba(237,228,211,0.5);'
        f'margin:0 0 4px;">Entre Interiores · Clips</p>'
        f'<h1 style="font-family:Georgia,serif;font-size:24px;color:{COL_PAPEL};'
        f'margin:0 0 8px;">{n} clip{"s" if n != 1 else ""} montado'
        f'{"s" if n != 1 else ""}, esperando tu visto bueno</h1>'
        f'<p style="font-family:Georgia,serif;font-size:14px;'
        f'color:rgba(237,228,211,0.75);line-height:1.6;margin:0 0 22px;">'
        f'Los ha elegido el sistema (vídeo y tramo) y ya están montados en 9:16 '
        f'con la atribución quemada. Míralos antes de decidir. Al aprobar, entran '
        f'en la cola y salen cuando les toque, con el resto de publicaciones.</p>'
        f'{fichas}</div>'
    )
    lineas = [f"{n} clips montados esperando tu visto bueno:", ""]
    for c, i in pares:
        lineas += [f"· {i.title}", f"  {c.start_s:.0f}-{c.end_s:.0f}s · {c.url_cdn}", ""]
    return html, "\n".join(lineas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        pares = _pendientes(db)
        if not pares:
            logger.info("No hay clips montados esperando. No se manda nada.")
            return

        site = os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")
        html, text = _render(pares, site)
        if args.dry_run:
            print(text)
            return

        admin_email = os.environ.get("ADMIN_EMAIL")
        if not admin_email:
            logger.warning("ADMIN_EMAIL no configurado, no se envía")
            return
        from app.services.email import EmailError, send_email

        try:
            send_email(
                to=admin_email,
                subject=f"🎬 {len(pares)} clip(s) listos para tu visto bueno",
                html=html,
                text=text,
            )
            logger.info("Email de clips enviado a %s", admin_email)
        except EmailError as e:
            logger.error("Fallo al enviar email: %s", e)


if __name__ == "__main__":
    main()
