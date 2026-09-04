"""Re-autoriza el token OAuth de Google (Search Console + Analytics).

    PYTHONPATH=api python3 -m scripts.seo.gsc_reauth

Abre el navegador, pide consentimiento y reescribe
`~/.config/entreinteriores/gsc-token.json` conservando `client_id`,
`client_secret` y `scopes` del token anterior. Corre SOLO en la Mac: ese token da
acceso a varias propiedades personales y no debe vivir en el server (ver
`infra/local/gsc_weekly.sh`).

Por qué hace falta un script: el `refresh_token` **caduca**. Si la app de OAuth
sigue en modo *Testing* en Google Cloud Console, Google revoca los refresh tokens
a los **7 días** — medido el 03-08-2026, con un token emitido el 22-07 que devolvía
`invalid_grant: Token has been expired or revoked`. Mientras estuvo revocado, el
job semanal escribía `"pages": {}` y se lo rsynceaba a prod.

Para que deje de caducar hay que publicar la app (OAuth consent screen →
*Publish app*). En modo *In production* el refresh_token no expira por tiempo.
"""
from __future__ import annotations

import json
import secrets
import socket
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

TOKEN_PATH = Path.home() / ".config" / "entreinteriores" / "gsc-token.json"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES_DEFAULT = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

_recibido: dict[str, str] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _recibido.update({k: v[0] for k, v in q.items()})
        ok = "code" in _recibido
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            ("<h2>Listo, vuelve a la terminal.</h2>" if ok
             else f"<h2>Error: {_recibido.get('error', 'sin code')}</h2>").encode("utf-8")
        )

    def log_message(self, *a: object) -> None:  # silencio
        return


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    if not TOKEN_PATH.exists():
        print(f"No hay token previo en {TOKEN_PATH}: no puedo sacar client_id/secret.",
              file=sys.stderr)
        print("Descarga el JSON de credenciales OAuth (tipo 'Desktop app') de Google "
              "Cloud Console y déjalo ahí con las claves client_id y client_secret.",
              file=sys.stderr)
        return 1

    viejo = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    client_id, client_secret = viejo.get("client_id"), viejo.get("client_secret")
    if not (client_id and client_secret):
        print("El token previo no tiene client_id/client_secret.", file=sys.stderr)
        return 1
    scopes = viejo.get("scopes") or SCOPES_DEFAULT

    puerto = _puerto_libre()
    redirect_uri = f"http://localhost:{puerto}"
    state = secrets.token_urlsafe(16)
    url = f"{AUTH_URI}?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",       # obligatorio: sin él Google no reemite refresh_token
        "state": state,
    })

    print("Abriendo el navegador para autorizar…")
    print(f"Si no se abre solo, pega esta URL:\n\n{url}\n")
    webbrowser.open(url)

    servidor = HTTPServer(("127.0.0.1", puerto), _Handler)
    servidor.handle_request()
    servidor.server_close()

    if _recibido.get("state") != state:
        print("El `state` no coincide: abortando por seguridad.", file=sys.stderr)
        return 1
    code = _recibido.get("code")
    if not code:
        print(f"Google no devolvió código: {_recibido.get('error', 'motivo desconocido')}",
              file=sys.stderr)
        return 1

    r = httpx.post(TOKEN_URI, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }, timeout=30)
    if r.status_code != 200:
        print(f"Intercambio de código fallido: HTTP {r.status_code}\n{r.text[:400]}",
              file=sys.stderr)
        return 1
    tok = r.json()
    if not tok.get("refresh_token"):
        print("Google no ha devuelto refresh_token. Revoca el acceso de la app en "
              "https://myaccount.google.com/permissions y vuelve a correr esto.",
              file=sys.stderr)
        return 1

    TOKEN_PATH.write_text(json.dumps({
        "token": tok.get("access_token"),
        "refresh_token": tok["refresh_token"],
        "token_uri": TOKEN_URI,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    print(f"\nToken reescrito en {TOKEN_PATH}")
    print("Compruébalo con:\n"
          "  PYTHONPATH=api python3 -m scripts.seo.gsc_fetch_page_queries --weeks 12 "
          "--out data/gsc_page_queries.json")
    print("\nY publica la app en Google Cloud Console (OAuth consent screen → "
          "Publish app) o volverá a caducar en 7 días.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
