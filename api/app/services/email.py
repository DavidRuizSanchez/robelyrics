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


def _site_url() -> str:
    """URL pública absoluta del site, usada para que los emails enlacen a
    imágenes y rutas accesibles desde cualquier cliente de email."""
    import os
    return os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")


def _email_logo_header() -> str:
    """Bloque HTML con el logo bomba de Entre Interiores (Robe en bote,
    ballenas, sol y nube, mecha encendida) centrado, listo para inyectar al
    inicio del <body> de los emails. Usa una URL absoluta para que Gmail y
    otros clientes lo carguen.

    Nota: en local con SITE_URL=http://localhost:..., Gmail/clientes externos
    no podrán descargar la imagen. En prod (entreinteriores.com) sí.
    """
    base = _site_url()
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto 24px;">
  <tr>
    <td align="center">
      <a href="{base}" style="text-decoration:none;display:inline-block;">
        <img src="{base}/logo-bomba-light-256.png"
             width="128" height="128"
             alt="Entre Interiores · Robe en bote, ballenas, sol y nube"
             style="display:block;border:0;outline:none;width:128px;height:128px;" />
      </a>
    </td>
  </tr>
</table>"""


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
  {_email_logo_header()}
  <div style="max-width:520px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 12px;">
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
      <a href="{verify_url}" style="display:inline-block;padding:14px 28px;border:1px solid #e85050;color:#e85050;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
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
  {_email_logo_header()}
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


def render_newsletter_confirm_email(confirm_url: str) -> tuple[str, str]:
    """Email de doble opt-in: la persona se suscribió a la newsletter y debe
    confirmar pinchando el link. Sin confirmar, no recibe nada más."""
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  {_email_logo_header()}
  <div style="max-width:520px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 12px;">
      entre interiores
    </p>
    <h1 style="font-family:Georgia,serif;font-size:28px;color:#ede4d3;margin:0 0 16px;">
      Confirma tu suscripción
    </h1>
    <p style="font-style:italic;line-height:1.6;color:rgba(237,228,211,0.7);font-size:16px;margin:0 0 24px;">
      Te has apuntado a recibir las entradas de <em>De manera urgente</em>, el
      diario de Entre Interiores. Confirma que quieres que te lleguen los avisos
      pulsando aquí abajo — sin esto, no enviaremos nada.
    </p>
    <p style="margin:32px 0;text-align:center;">
      <a href="{confirm_url}" style="display:inline-block;padding:14px 28px;border:1px solid #e85050;color:#e85050;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        confirmar suscripción
      </a>
    </p>
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:1px;color:rgba(237,228,211,0.4);margin:24px 0 0;line-height:1.6;">
      Si no fuiste tú quien se apuntó, ignora este email — no se hará nada con tu
      dirección. Sin tu confirmación tu email no entra en la lista.
    </p>
  </div>
</body>
</html>"""
    text = (
        "Confirma tu suscripción a Entre Interiores · De manera urgente.\n\n"
        f"Pulsa este enlace para activar la suscripción:\n{confirm_url}\n\n"
        "Si no fuiste tú quien se apuntó, ignora este email."
    )
    return html, text


def render_newsletter_digest_email(
    posts: list[dict], unsubscribe_url: str, site_url: str
) -> tuple[str, str]:
    """Digest de nuevas entradas del blog. Recibe lista de posts con
    {title, excerpt, url, kind_label, published_at_human}."""
    posts_html = ""
    posts_text_parts: list[str] = []
    for p in posts:
        posts_html += f"""\
<div style="margin:0 0 28px;padding:0 0 24px;border-bottom:1px solid rgba(237,228,211,0.08);">
  <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 8px;">
    {p['kind_label']} · {p['published_at_human']}
  </p>
  <h2 style="font-family:Georgia,serif;font-size:22px;color:#ede4d3;margin:0 0 10px;line-height:1.25;">
    <a href="{p['url']}" style="color:#ede4d3;text-decoration:none;">{p['title']}</a>
  </h2>
  <p style="font-family:Georgia,serif;font-style:italic;font-size:15px;line-height:1.6;color:rgba(237,228,211,0.7);margin:0 0 10px;">
    {p.get('excerpt') or ''}
  </p>
  <p style="margin:8px 0 0;">
    <a href="{p['url']}" style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#e85050;text-decoration:none;border-bottom:1px solid #e85050;">
      leer entrada
    </a>
  </p>
</div>
"""
        posts_text_parts.append(
            f"· {p['title']}\n  {p.get('excerpt') or ''}\n  {p['url']}\n"
        )

    intro = (
        "Una nueva entrada" if len(posts) == 1
        else f"{len(posts)} entradas nuevas"
    )
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  {_email_logo_header()}
  <div style="max-width:580px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 6px;">
      entre interiores · de manera urgente
    </p>
    <h1 style="font-family:Georgia,serif;font-size:24px;color:#ede4d3;margin:0 0 8px;">
      {intro} en el diario
    </h1>
    <p style="font-style:italic;line-height:1.6;color:rgba(237,228,211,0.6);font-size:14px;margin:0 0 32px;">
      Lo último que se ha publicado sobre Robe y Extremoduro en
      Entre Interiores. Tómatelo con calma.
    </p>
    {posts_html}
    <div style="margin:32px 0 0;padding:18px 0 0;border-top:1px solid rgba(237,228,211,0.08);">
      <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:1px;color:rgba(237,228,211,0.4);line-height:1.7;margin:0;">
        Recibes este email porque te suscribiste en
        <a href="{site_url}" style="color:rgba(237,228,211,0.6);">entreinteriores.com</a>.
        Si ya no quieres recibirlos,
        <a href="{unsubscribe_url}" style="color:#e85050;">date de baja aquí</a>
        — sin preguntas.
      </p>
    </div>
  </div>
</body>
</html>"""
    text = (
        f"{intro} en Entre Interiores · De manera urgente.\n\n"
        + "\n".join(posts_text_parts)
        + f"\n--\nDarse de baja: {unsubscribe_url}\n"
        + f"Web: {site_url}\n"
    )
    return html, text


def render_newsletter_invite_email(confirm_url: str) -> tuple[str, str]:
    """Email one-shot a usuarios YA registrados invitándoles a la newsletter.
    A diferencia del confirm normal, este reconoce al destinatario como
    persona que ya está dentro del sitio y pide confirmar la suscripción al
    diario."""
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  {_email_logo_header()}
  <div style="max-width:560px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 12px;">
      entre interiores · de manera urgente
    </p>
    <h1 style="font-family:Georgia,serif;font-size:26px;color:#ede4d3;margin:0 0 16px;line-height:1.2;">
      Hemos abierto un diario en Entre Interiores
    </h1>
    <p style="font-style:italic;line-height:1.7;color:rgba(237,228,211,0.75);font-size:16px;margin:0 0 14px;">
      Como ya tienes cuenta aquí, te aviso de primera mano: hemos abierto
      <strong>De manera urgente</strong>, una sección de noticias y memoria
      sobre Robe y Extremoduro, escrita desde el cariño y a su
      ritmo.
    </p>
    <p style="font-style:italic;line-height:1.7;color:rgba(237,228,211,0.75);font-size:16px;margin:0 0 14px;">
      Si te apetece que te llegue un aviso cuando se publique algo,
      confirma con un clic. Sin spam, baja en cualquier momento.
    </p>
    <p style="margin:32px 0;text-align:center;">
      <a href="{confirm_url}" style="display:inline-block;padding:14px 28px;border:1px solid #e85050;color:#e85050;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        sí, apúntame al diario
      </a>
    </p>
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:1px;color:rgba(237,228,211,0.4);margin:24px 0 0;line-height:1.7;">
      Si no te apetece, no hagas nada y no recibirás más correos sobre
      esto. Tu cuenta sigue intacta. Te escribimos hoy y se acabó.
    </p>
  </div>
</body>
</html>"""
    text = (
        "Hemos abierto un diario en Entre Interiores: De manera urgente.\n\n"
        "Como ya tienes cuenta, te lo aviso por si te apetece recibir un\n"
        "email cada vez que publiquemos algo. Confirma con un clic:\n\n"
        f"{confirm_url}\n\n"
        "Si no te apetece, no hagas nada — no recibirás más correos sobre esto."
    )
    return html, text


def render_admin_review_email(
    posts: list[dict],
    admin_panel_url: str,
) -> tuple[str, str]:
    """Email al admin con la lista de posts pending_review y botones
    aprobar/rechazar directos (one-click, JWT-firmados).

    Cada item en `posts` debe tener: title, kind_label, excerpt (opcional),
    source_name (opcional), source_url (opcional), approve_url, reject_url,
    admin_url (vista detalle).
    """
    site_url = _site_url()

    items_html = ""
    items_text: list[str] = []
    for p in posts:
        excerpt_html = (
            f'<p style="font-family:Georgia,serif;font-style:italic;font-size:13px;'
            f'color:rgba(237,228,211,0.7);margin:8px 0 12px;line-height:1.5;">'
            f'{p["excerpt"]}</p>'
            if p.get("excerpt") else ""
        )
        source_html = ""
        if p.get("source_name") and p.get("source_url"):
            source_html = (
                f'<p style="font-family:\'Courier New\',monospace;font-size:10px;'
                f'color:rgba(237,228,211,0.5);margin:0 0 12px;">Fuente: '
                f'<a href="{p["source_url"]}" style="color:#e85050;text-decoration:none;">'
                f'{p["source_name"]} ↗</a></p>'
            )
        items_html += f"""\
<div style="margin:0 0 24px;padding:18px 18px 16px;background:rgba(237,228,211,0.03);border-left:3px solid #a83a3a;">
  <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(237,228,211,0.5);margin:0 0 6px;">
    {p["kind_label"]}
  </p>
  <p style="font-family:Georgia,serif;font-size:18px;color:#ede4d3;margin:0 0 6px;line-height:1.3;font-weight:bold;">
    {p["title"]}
  </p>
  {excerpt_html}
  {source_html}
  <p style="margin:14px 0 0;">
    <a href="{p["approve_url"]}" style="display:inline-block;padding:10px 18px;margin-right:8px;background:#a83a3a;color:#fff;text-decoration:none;font-family:'Courier New',monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;">
      aprobar
    </a>
    <a href="{p["reject_url"]}" style="display:inline-block;padding:10px 18px;margin-right:8px;border:1px solid rgba(237,228,211,0.3);color:rgba(237,228,211,0.7);text-decoration:none;font-family:'Courier New',monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;">
      rechazar
    </a>
    <a href="{p["admin_url"]}" style="display:inline-block;padding:10px 18px;color:rgba(237,228,211,0.5);text-decoration:none;font-family:'Courier New',monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;">
      ver completo →
    </a>
  </p>
</div>"""
        items_text.append(
            f"· [{p['kind_label']}] {p['title']}\n"
            f"  aprobar: {p['approve_url']}\n"
            f"  rechazar: {p['reject_url']}\n"
            f"  ver: {p['admin_url']}\n"
        )

    n = len(posts)
    headline = (
        "Una entrada para revisar"
        if n == 1
        else f"{n} entradas para revisar"
    )
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  {_email_logo_header()}
  <div style="max-width:620px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#a83a3a;margin:0 0 12px;">
      entre interiores · admin
    </p>
    <h1 style="font-family:Georgia,serif;font-size:26px;color:#ede4d3;margin:0 0 8px;line-height:1.2;">
      {headline}
    </h1>
    <p style="font-family:Georgia,serif;font-style:italic;color:rgba(237,228,211,0.6);font-size:14px;margin:0 0 28px;line-height:1.6;">
      Aprueba con un clic desde aquí, o entra al panel para ver y editar
      antes de publicar. Nada se manda a los suscriptores hasta que apruebes.
    </p>
    {items_html}
    <div style="margin:32px 0 0;padding:18px 0 0;border-top:1px solid rgba(237,228,211,0.08);text-align:center;">
      <a href="{admin_panel_url}" style="font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#a83a3a;text-decoration:none;">
        ver todos los pendientes →
      </a>
    </div>
  </div>
</body>
</html>"""

    text = (
        f"{headline} en Entre Interiores:\n\n"
        + "\n".join(items_text)
        + f"\n\nPanel admin: {admin_panel_url}\n"
        f"Web: {site_url}\n"
    )
    return html, text
