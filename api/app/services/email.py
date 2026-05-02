"""Wrapper minimal sobre la API REST de Resend.

Resend no requiere SDK: es un POST a https://api.resend.com/emails con auth Bearer.
Si `RESEND_API_KEY` no está configurada (entorno local sin email saliente), las
funciones loguean el contenido por stderr en lugar de enviar — útil para
desarrollo, falla rápido en producción si falta la key.
"""
from __future__ import annotations

import sys

import httpx

from app.config import get_settings

RESEND_API_URL = "https://api.resend.com/emails"


class EmailError(Exception):
    pass


def send_email(to: str, subject: str, html: str, text: str | None = None) -> str | None:
    """Envía un email. Devuelve el ID de Resend, o None si solo se logueó.

    No lanza si la key no está configurada (modo dev). Sí lanza EmailError si
    Resend devuelve error explícito.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        print(
            f"[email:dev] sin RESEND_API_KEY; loggeando · to={to} subject={subject!r}",
            file=sys.stderr,
        )
        print(f"[email:dev] body html → {html[:300]}...", file=sys.stderr)
        return None

    payload = {
        "from": settings.resend_from_email,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as e:
        raise EmailError(f"resend http error: {e}") from e

    if r.status_code >= 400:
        raise EmailError(f"resend {r.status_code}: {r.text[:300]}")

    return r.json().get("id")


def render_verify_email(verify_url: str) -> tuple[str, str]:
    """Devuelve (html, text) para el email de verificación de cuenta nueva."""
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  <div style="max-width:520px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#a83a3a;margin:0 0 12px;">
      entre interiores
    </p>
    <h1 style="font-family:Georgia,serif;font-size:28px;color:#ede4d3;margin:0 0 16px;">
      Confirma tu email
    </h1>
    <p style="font-style:italic;line-height:1.6;color:rgba(237,228,211,0.7);font-size:16px;margin:0 0 24px;">
      Hola, hemos recibido tu solicitud de acceso al cancionero íntimo.
      Confirma tu email pulsando el botón. El enlace caduca en 24&nbsp;horas.
    </p>
    <p style="margin:32px 0;text-align:center;">
      <a href="{verify_url}" style="display:inline-block;padding:14px 28px;border:1px solid #a83a3a;color:#a83a3a;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        verificar email
      </a>
    </p>
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:1px;color:rgba(237,228,211,0.4);margin:24px 0 0;">
      Si no solicitaste esto, ignora este email.
    </p>
  </div>
</body>
</html>"""
    text = (
        "Confirma tu email en Entre Interiores.\n\n"
        f"Pulsa el siguiente enlace (caduca en 24h):\n{verify_url}\n\n"
        "Si no solicitaste esto, ignora este mensaje."
    )
    return html, text
