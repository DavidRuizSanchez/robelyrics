"""Servicio de envío de emails. Dos backends:

  1. SMTP genérico (compatible con Gmail vía app-password). Es la opción
     recomendada para uso personal, sin necesidad de dominio. Si SMTP_HOST,
     SMTP_USER y SMTP_PASSWORD están configurados, se usa este.

  2. Resend (preferido en producción con dominio verificado). Si solo está
     RESEND_API_KEY, se usa éste.

Si ninguno está configurado, las funciones loguean por stderr en lugar de
enviar — útil para desarrollo sin claves.
"""
from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage

import httpx

from app.config import get_settings

RESEND_API_URL = "https://api.resend.com/emails"


class EmailError(Exception):
    pass


def send_email(to: str, subject: str, html: str, text: str | None = None) -> str | None:
    """Envía un email. Devuelve un identificador (Message-ID o id de Resend),
    o None si solo se logueó en stderr.

    Selecciona backend según configuración: SMTP > Resend > log.
    """
    settings = get_settings()

    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        return _send_smtp(settings, to, subject, html, text)

    if settings.resend_api_key:
        return _send_resend(settings, to, subject, html, text)

    print(
        f"[email:dev] sin SMTP_* ni RESEND_API_KEY; loggeando · to={to} subject={subject!r}",
        file=sys.stderr,
    )
    print(f"[email:dev] body html → {html[:300]}...", file=sys.stderr)
    return None


def _send_smtp(settings, to: str, subject: str, html: str, text: str | None) -> str:
    msg = EmailMessage()
    from_addr = settings.smtp_from or settings.smtp_user
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{from_addr}>"
    msg["To"] = to
    msg.set_content(text or "Confirma tu email visitando el enlace.")
    msg.add_alternative(html, subtype="html")

    try:
        # Gmail (587) y la mayoría de proveedores: STARTTLS.
        # Para puerto 465 (SMTPS) usaríamos SMTP_SSL — no contemplado de momento
        # porque app-password de Gmail funciona perfectamente con 587.
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"smtp error: {type(e).__name__}: {e}") from e

    return msg["Message-ID"] or "smtp-sent"


def _send_resend(settings, to: str, subject: str, html: str, text: str | None) -> str:
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

    return r.json().get("id", "resend-sent")


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


def render_reset_password_email(reset_url: str) -> tuple[str, str]:
    """Devuelve (html, text) para el email de reseteo de contraseña.
    TTL más corto (30 min) y advertencia explícita ante ignorar."""
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  <div style="max-width:520px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 12px;">
      entre interiores
    </p>
    <h1 style="font-family:Georgia,serif;font-size:28px;color:#ede4d3;margin:0 0 16px;">
      Restablecer contraseña
    </h1>
    <p style="font-style:italic;line-height:1.6;color:rgba(237,228,211,0.7);font-size:16px;margin:0 0 24px;">
      Hemos recibido una petición para restablecer tu contraseña.
      Pulsa el botón para elegir una nueva. El enlace caduca en 30&nbsp;minutos.
    </p>
    <p style="margin:32px 0;text-align:center;">
      <a href="{reset_url}" style="display:inline-block;padding:14px 28px;border:1px solid #e85050;color:#e85050;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        elegir nueva contraseña
      </a>
    </p>
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:1px;color:rgba(237,228,211,0.4);margin:24px 0 0;line-height:1.6;">
      Si no solicitaste esto, ignora este email — tu contraseña sigue intacta.
      Si recibes muchos avisos como éste sin haberlos pedido, contáctanos.
    </p>
  </div>
</body>
</html>"""
    text = (
        "Restablecer contraseña en Entre Interiores.\n\n"
        f"Pulsa el siguiente enlace (caduca en 30 min):\n{reset_url}\n\n"
        "Si no solicitaste esto, ignora este mensaje — tu contraseña sigue intacta."
    )
    return html, text
