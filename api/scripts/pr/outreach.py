"""Outreach del estudio: manda desde hola@ por Brevo y lee las respuestas por IMAP.

Corre en el HOST, no en docker (la clave nunca entra en un contenedor ni en la imagen):

    python3 -I api/scripts/pr/outreach.py list
    python3 -I api/scripts/pr/outreach.py preview 1
    python3 -I api/scripts/pr/outreach.py send 1 --yes
    python3 -I api/scripts/pr/outreach.py replies
    python3 -I api/scripts/pr/outreach.py followups

Credenciales en ~/.config/correo-personal/credenciales.env, que solo se usan desde
RobeLyrics y Privado (hook `proteger-correo-personal.py`). Solo librería estándar.

Reglas que el script hace cumplir, no solo documenta:
  · Cada `send` es UN destinatario y exige `--yes`: la aprobación es uno a uno, en el
    chat, y nunca hay un «mandar todos».
  · No se manda dos veces: si «Mandado (fecha)» tiene valor, se niega.
  · Solo texto plano: sin HTML, Brevo no reescribe los enlaces con su seguimiento y el
    periodista copia la URL limpia (que es el backlink que se busca).
  · La lectura es de SOLO LECTURA (`EXAMINE`): no marca nada como leído ni lo mueve.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import email
import email.header
import email.utils
import imaplib
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CSV_PATH = REPO / "data" / "estudio" / "outreach.csv"
CREDENCIALES = Path.home() / ".config" / "correo-personal" / "credenciales.env"

REMITENTE = {"name": "David Ruiz · Entre Interiores", "email": "hola@entreinteriores.com"}
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
EXTRA = ["ID", "Brevo messageId", "Última comprobación"]
DIAS_INSISTENCIA = 7


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def leer() -> tuple[list[str], list[dict]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as fh:
        r = csv.DictReader(fh)
        cols = list(r.fieldnames or [])
        filas = list(r)
    cambiado = False
    for c in EXTRA:
        if c not in cols:
            cols = ([c] if c == "ID" else []) + cols + ([] if c == "ID" else [c])
            cambiado = True
    for i, f in enumerate(filas, 1):
        if not f.get("ID"):
            f["ID"] = str(i)
            cambiado = True
        for c in EXTRA:
            f.setdefault(c, "")
    if cambiado:
        escribir(cols, filas)
    return cols, filas


def escribir(cols: list[str], filas: list[dict]) -> None:
    tmp = CSV_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(filas)
    tmp.replace(CSV_PATH)


def fila(filas: list[dict], ident: str) -> dict:
    for f in filas:
        if f["ID"] == ident:
            return f
    sys.exit(f"no hay fila con ID {ident}")


# --------------------------------------------------------------------------- #
# Credenciales
# --------------------------------------------------------------------------- #
def credencial(nombre: str) -> str:
    if not CREDENCIALES.exists():
        sys.exit(f"falta {CREDENCIALES}")
    for linea in CREDENCIALES.read_text(encoding="utf-8").splitlines():
        if linea.strip().startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        if k.strip() == nombre and v.strip():
            return v.strip()
    sys.exit(f"{nombre} está vacío en {CREDENCIALES}")


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #
def cmd_list(_args) -> int:
    _, filas = leer()
    for f in filas:
        estado = f"mandado {f['Mandado (fecha)']}" if f["Mandado (fecha)"] else "pendiente"
        if f.get("Respuesta"):
            estado += " · respondió"
        print(f"{f['ID']:>3}  {f['Bloque'][:16]:<16} {f['Medio'][:34]:<34} {f['Email'][:34]:<34} {estado}")
    return 0


def _comprobar_enviable(f: dict) -> str | None:
    if f["Mandado (fecha)"]:
        return f"ya se mandó el {f['Mandado (fecha)']}"
    if "@" not in f["Email"] or f["Email"].lower().startswith("n/d"):
        return f"sin email válido: «{f['Email']}»"
    if not f["Asunto"].strip() or not f["Cuerpo"].strip():
        return "asunto o cuerpo vacío"
    return None


def cmd_preview(args) -> int:
    _, filas = leer()
    f = fila(filas, args.id)
    print(f"De:      {REMITENTE['name']} <{REMITENTE['email']}>")
    print(f"Para:    {f['Persona']} <{f['Email']}>")
    print(f"BCC:     {REMITENTE['email']}")
    print(f"Asunto:  {f['Asunto']}")
    print("-" * 72)
    print(f["Cuerpo"])
    print("-" * 72)
    motivo = _comprobar_enviable(f)
    print(f"NO SE PUEDE MANDAR: {motivo}" if motivo else "listo para mandar con: send "
          f"{f['ID']} --yes")
    return 0


def cmd_send(args) -> int:
    if not args.yes:
        sys.exit("falta --yes: cada envío necesita el OK explícito de David")
    cols, filas = leer()
    f = fila(filas, args.id)
    motivo = _comprobar_enviable(f)
    if motivo:
        sys.exit(f"no se manda: {motivo}")

    nombre = f["Persona"] if f["Persona"] and not f["Persona"].startswith("Redacción") else None
    destino = {"email": f["Email"], **({"name": nombre} if nombre else {})}
    payload = {
        "sender": REMITENTE,
        "to": [destino],
        "bcc": [{"email": REMITENTE["email"]}],
        "replyTo": REMITENTE,
        "subject": f["Asunto"],
        "textContent": f["Cuerpo"],
        "tags": ["outreach-estudio-repertorio"],
    }
    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": credencial("BREVO_API_KEY"),
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            cuerpo = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Brevo respondió {e.code}: {e.read().decode('utf-8', 'replace')}")

    f["Mandado (fecha)"] = date.today().isoformat()
    f["Brevo messageId"] = cuerpo.get("messageId", "")
    escribir(cols, filas)
    print(f"mandado a {f['Email']} · messageId {f['Brevo messageId']}")
    return 0


def _decodificar(valor: str | None) -> str:
    if not valor:
        return ""
    partes = email.header.decode_header(valor)
    return "".join(
        (t.decode(c or "utf-8", "replace") if isinstance(t, bytes) else t) for t, c in partes
    )


def _extracto(msg: email.message.Message) -> str:
    for parte in msg.walk():
        if parte.get_content_type() == "text/plain" and not parte.get_filename():
            carga = parte.get_payload(decode=True) or b""
            texto = carga.decode(parte.get_content_charset() or "utf-8", "replace")
            lineas = [ln for ln in texto.splitlines() if ln.strip() and not ln.startswith(">")]
            return " ".join(lineas)[:400]
    return ""


def cmd_replies(args) -> int:
    _, filas = leer()
    por_dominio: dict[str, dict] = {}
    for f in filas:
        if "@" in f["Email"]:
            por_dominio[f["Email"].split("@", 1)[1].lower()] = f

    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(credencial("GMAIL_USER"), credencial("GMAIL_APP_PASSWORD"))
    try:
        # La carpeta «Todos» cambia de nombre con el idioma de Gmail («[Gmail]/All Mail»,
        # «[Gmail]/Todos»…): se busca por su atributo \All, no por el nombre.
        _, carpetas = imap.list()
        todos = next(
            (c.decode().rsplit(' "/" ', 1)[-1] for c in carpetas or [] if b"\\All" in c),
            None,
        )
        if not todos:
            sys.exit("no encuentro la carpeta de todos los mensajes (atributo \\All)")
        # readonly=True manda EXAMINE: nada cambia de estado en el buzón.
        typ, _ = imap.select(todos, readonly=True)
        if typ != "OK":
            sys.exit(f"no se pudo abrir {todos}")
        consulta = (f"to:hola@entreinteriores.com -from:hola@entreinteriores.com "
                    f"newer_than:{args.dias}d")
        typ, data = imap.search(None, "X-GM-RAW", f'"{consulta}"')
        ids = data[0].split() if typ == "OK" and data and data[0] else []
        print(f"{len(ids)} correos a hola@ en los últimos {args.dias} días\n")
        for num in ids[-args.max:]:
            # BODY.PEEK no marca como leído.
            typ, partes = imap.fetch(num, "(BODY.PEEK[])")
            if typ != "OK" or not partes or not isinstance(partes[0], tuple):
                continue
            msg = email.message_from_bytes(partes[0][1])
            remitente = email.utils.parseaddr(msg.get("From", ""))[1].lower()
            dominio = remitente.split("@", 1)[-1]
            f = por_dominio.get(dominio)
            print(f"— {msg.get('Date', '')}")
            print(f"  De: {_decodificar(msg.get('From'))}")
            print(f"  Asunto: {_decodificar(msg.get('Subject'))}")
            print(f"  Fila: {f['ID'] + ' · ' + f['Medio'] if f else '(no casa con ningún medio)'}")
            print(f"  {_extracto(msg)}\n")
    finally:
        with contextlib.suppress(Exception):
            imap.logout()
    return 0


def cmd_followups(_args) -> int:
    _, filas = leer()
    hoy = date.today()
    hay = False
    for f in filas:
        if not f["Mandado (fecha)"] or f.get("Respuesta"):
            continue
        enviado = datetime.strptime(f["Mandado (fecha)"], "%Y-%m-%d").date()
        if hoy - enviado < timedelta(days=DIAS_INSISTENCIA):
            continue
        hay = True
        print(f"{f['ID']:>3}  {f['Medio']} <{f['Email']}> · mandado el {f['Mandado (fecha)']} "
              f"({(hoy - enviado).days} días, sin respuesta)")
    if not hay:
        print(f"nada que insistir (umbral: {DIAS_INSISTENCIA} días sin respuesta)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("preview")
    p.add_argument("id")
    p.set_defaults(fn=cmd_preview)
    s = sub.add_parser("send")
    s.add_argument("id")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_send)
    r = sub.add_parser("replies")
    r.add_argument("--dias", type=int, default=60)
    r.add_argument("--max", type=int, default=30)
    r.set_defaults(fn=cmd_replies)
    sub.add_parser("followups").set_defaults(fn=cmd_followups)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
