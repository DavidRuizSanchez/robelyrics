"""Email semanal al admin con las propuestas evergreen de Instagram.

Lista las publicaciones en estado `proposed` (frases, efemérides, anécdotas,
citas), agrupadas por tipo, con enlace al panel para aprobarlas/descartarlas en
bloque. No publica nada: solo avisa.

Cron: lunes, después de `prepare_evergreen`.

Uso:
    python -m scripts.instagram.notify_evergreen
    python -m scripts.instagram.notify_evergreen --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os

from sqlalchemy import select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TYPE_LABEL = {
    "quote": "Frases de canciones",
    "ephemeris": "Efemérides y aniversarios",
    "anecdote": "Anécdotas y hechos",
    "robe_quote": "Citas de Robe",
}
TYPE_ORDER = ["quote", "ephemeris", "anecdote", "robe_quote"]


def _render(grupos: dict[str, list[InstagramQueueItem]], admin_url: str) -> tuple[str, str]:
    total = sum(len(v) for v in grupos.values())
    secciones_html: list[str] = []
    text_lines = [f"Propuestas evergreen de Instagram: {total}", ""]

    for tipo in TYPE_ORDER:
        items = grupos.get(tipo) or []
        if not items:
            continue
        label = TYPE_LABEL.get(tipo, tipo)
        text_lines.append(f"== {label} ({len(items)}) ==")
        filas = []
        for it in items:
            text_lines.append(f"  · {it.title}")
            sub = (it.summary or "").strip()
            sub_html = (
                f'<div style="font-family:Georgia,serif;font-style:italic;font-size:12px;'
                f'color:rgba(237,228,211,0.6);margin-top:2px;">{sub[:140]}</div>'
                if sub else ""
            )
            filas.append(
                f'<li style="margin:0 0 10px;padding:0;list-style:none;">'
                f'<span style="font-family:Georgia,serif;font-size:15px;color:#ede4d3;">'
                f'{it.title}</span>{sub_html}</li>'
            )
        text_lines.append("")
        secciones_html.append(
            f'<h2 style="font-family:\'Courier New\',monospace;font-size:11px;'
            f'letter-spacing:3px;text-transform:uppercase;color:#a83a3a;'
            f'margin:24px 0 10px;">{label} · {len(items)}</h2>'
            f'<ul style="margin:0;padding:0;">{"".join(filas)}</ul>'
        )

    html = (
        f'<div style="background:#0d0b0a;padding:32px 24px;max-width:600px;margin:0 auto;">'
        f'<p style="font-family:\'Courier New\',monospace;font-size:10px;letter-spacing:3px;'
        f'text-transform:uppercase;color:rgba(237,228,211,0.5);margin:0 0 4px;">'
        f'Entre Interiores · Instagram</p>'
        f'<h1 style="font-family:Georgia,serif;font-size:24px;color:#ede4d3;margin:0 0 16px;">'
        f'{total} propuestas evergreen esperando tu visto bueno</h1>'
        f'<p style="font-family:Georgia,serif;font-size:14px;color:rgba(237,228,211,0.75);'
        f'line-height:1.6;margin:0 0 8px;">Material intemporal sacado del corpus '
        f'(letras, efemérides, hechos verificados y citas de Robe). Aprueba en bloque '
        f'las que te gusten desde el panel; el resto se descartan.</p>'
        f'{"".join(secciones_html)}'
        f'<p style="margin:28px 0 0;"><a href="{admin_url}" '
        f'style="display:inline-block;background:#a83a3a;color:#0d0b0a;'
        f'font-family:\'Courier New\',monospace;font-size:12px;letter-spacing:2px;'
        f'text-transform:uppercase;text-decoration:none;padding:12px 22px;">'
        f'Revisar y aprobar →</a></p>'
        f'</div>'
    )
    text_lines.append(f"Aprobar en: {admin_url}")
    return html, "\n".join(text_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        rows = db.execute(
            select(InstagramQueueItem)
            .where(InstagramQueueItem.status == "proposed")
            .order_by(InstagramQueueItem.content_type, InstagramQueueItem.created_at.desc())
        ).scalars().all()

        grupos: dict[str, list] = {}
        for it in rows:
            grupos.setdefault(it.content_type, []).append(it)

        logger.info("Propuestas evergreen pendientes: %d", len(rows))
        if not rows:
            logger.info("Nada que notificar.")
            return

        site = os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")
        admin_url = f"{site}/biblioteca/admin/instagram"
        html, text = _render(grupos, admin_url)

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
                subject=f"📸 {len(rows)} propuestas para Instagram (evergreen)",
                html=html,
                text=text,
            )
            logger.info("Email evergreen enviado a %s", admin_email)
        except EmailError as e:
            logger.error("Fallo al enviar email: %s", e)


if __name__ == "__main__":
    main()
