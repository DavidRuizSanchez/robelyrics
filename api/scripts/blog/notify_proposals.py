"""Email semanal al admin con el banco de propuestas editoriales.

Lista TODAS las propuestas en estado `proposed`, agrupadas:
  - ACTUALIDAD: noticias, efemérides de Robe, aniversarios de discos.
  - REPOSITORIO: evergreens y spotlights (fondo de armario).

No lleva botones de acción: el admin programa desde la pestaña
/biblioteca/admin/calendario (tope 2/semana). El email es un aviso +
enlace al calendario.

Cron: lunes, después del scraper.

Uso:
    python -m scripts.blog.notify_proposals
    python -m scripts.blog.notify_proposals --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os

from app.db.models import ContentProposal
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ACTUALIDAD_KINDS = ("news", "anniversary", "album-anniversary")
KIND_LABEL = {
    "news": "Noticia",
    "anniversary": "Efeméride de Robe",
    "album-anniversary": "Aniversario de disco",
    "spotlight": "Análisis de canción",
    "evergreen": "Tema de fondo",
}


def _render(actualidad: list, repositorio: list, admin_url: str) -> tuple[str, str]:
    def _item_html(p: ContentProposal) -> str:
        angle = (
            f'<p style="font-family:Georgia,serif;font-style:italic;font-size:13px;'
            f'color:rgba(237,228,211,0.65);margin:4px 0 0;line-height:1.5;">{p.angle}</p>'
            if p.angle else ""
        )
        return (
            f'<li style="margin:0 0 14px;padding:12px 14px;'
            f'background:rgba(237,228,211,0.03);border-left:3px solid #a83a3a;">'
            f'<p style="font-family:\'Courier New\',monospace;font-size:9px;'
            f'letter-spacing:2px;text-transform:uppercase;color:rgba(237,228,211,0.5);'
            f'margin:0 0 4px;">{KIND_LABEL.get(p.kind, p.kind)}</p>'
            f'<p style="font-family:Georgia,serif;font-size:16px;color:#ede4d3;'
            f'margin:0;font-weight:bold;">{p.title}</p>{angle}</li>'
        )

    def _section(titulo: str, items: list) -> str:
        if not items:
            return ""
        lis = "".join(_item_html(p) for p in items)
        return (
            f'<p style="font-family:\'Courier New\',monospace;font-size:11px;'
            f'letter-spacing:3px;text-transform:uppercase;color:#a83a3a;'
            f'margin:24px 0 10px;">{titulo} ({len(items)})</p>'
            f'<ul style="list-style:none;padding:0;margin:0;">{lis}</ul>'
        )

    n = len(actualidad) + len(repositorio)
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  <div style="max-width:640px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#a83a3a;margin:0 0 12px;">
      entre interiores · banco de propuestas
    </p>
    <h1 style="font-family:Georgia,serif;font-size:25px;color:#ede4d3;margin:0 0 8px;line-height:1.2;">
      {n} propuesta{'s' if n != 1 else ''} esperando en el banco
    </h1>
    <p style="font-family:Georgia,serif;font-style:italic;color:rgba(237,228,211,0.6);font-size:14px;margin:0 0 8px;line-height:1.6;">
      Entra al calendario y programa las que quieras. Máximo 2 por semana.
      Lo que no programes se queda en el banco para más adelante.
    </p>
    {_section("Actualidad", actualidad)}
    {_section("Repositorio de fondo", repositorio)}
    <div style="margin:32px 0 0;padding:18px 0 0;border-top:1px solid rgba(237,228,211,0.08);text-align:center;">
      <a href="{admin_url}" style="display:inline-block;padding:14px 28px;border:1px solid #a83a3a;color:#a83a3a;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        abrir el calendario
      </a>
    </div>
  </div>
</body>
</html>"""

    text_lines = [f"{n} propuestas en el banco editorial.", ""]
    for label, items in (("ACTUALIDAD", actualidad), ("REPOSITORIO", repositorio)):
        if not items:
            continue
        text_lines.append(f"== {label} ({len(items)}) ==")
        for p in items:
            text_lines.append(f"· [{KIND_LABEL.get(p.kind, p.kind)}] {p.title}")
        text_lines.append("")
    text_lines.append(f"Programar en: {admin_url}")
    return html, "\n".join(text_lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        proposed = (
            db.query(ContentProposal)
            .filter(ContentProposal.status == "proposed")
            .order_by(ContentProposal.created_at.desc())
            .all()
        )
        actualidad = [p for p in proposed if p.kind in ACTUALIDAD_KINDS]
        repositorio = [p for p in proposed if p.kind not in ACTUALIDAD_KINDS]
        logger.info(
            "Propuestas en banco: %d actualidad, %d repositorio",
            len(actualidad), len(repositorio),
        )

        if not proposed:
            logger.info("Banco vacío, no se envía email")
            return

        site = os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")
        admin_url = f"{site}/biblioteca/admin/calendario"
        html, text = _render(actualidad, repositorio, admin_url)

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
                subject=f"📋 {len(proposed)} propuestas en el banco editorial",
                html=html,
                text=text,
            )
            logger.info("Email de propuestas enviado a %s", admin_email)
        except EmailError as e:
            logger.error("Fallo al enviar email: %s", e)


if __name__ == "__main__":
    main()
