"""Monitor de cambios del sitio: una foto por URL y qué cambió desde la anterior.

Petición de David (26-10-2026): saber cuándo cambia el title, la description,
los headings, el contenido, el meta robots, el canonical o el status de cualquier
página, con correo y panel propio. El motor reescribe páginas solo (fusiones,
relinker, erratas) y nada comparaba lo publicado de un día para otro.

Este módulo es puro salvo `snapshot`, que hace una petición HTTP al propio sitio:
`parse` saca los campos de un HTML y `diff` compara dos fotos. Lo que se guarda y
lo que se avisa lo decide `scripts/seo/monitor_cambios.py`.

Tres decisiones para que el correo no se llene de falsos cambios:

- Los bloques que dependen de OTRAS páginas (posts relacionados, menciones,
  vídeos) llevan `data-monitor="ignore"` en su componente y no cuentan.
- En los LISTADOS (portada, hubs, /blog) el contenido es el H1 y la intro: que
  entre un post nuevo en /blog no es un cambio de /blog.
- Hay campos que avisan siempre (status, robots, canonical, title, description,
  H1) y campos de contenido. Un deploy no explica ninguno de los dos: si cambia
  un title el día de un deploy, es inesperado.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

SITE = "https://entreinteriores.com"
# Sube cuando cambia CÓMO se lee una página. Una foto de otra versión no se compara:
# se vuelve a fotografiar. Sin esto, mejorar el parser (26-10-2026: el texto pasó a
# ir por bloques) daba «contenido cambiado» en todas las páginas a la vez.
VERSION_PARSER = 2
USER_AGENT = "EntreInteriores-Monitor/1.0 (+https://entreinteriores.com)"
MAX_REDIRECTS = 5

# Páginas que listan otras: su contenido cambia cada vez que se publica algo.
LISTADOS = frozenset({
    "/", "/blog", "/discografia", "/discografia/extremoduro", "/discografia/robe",
    "/temas", "/lugares", "/conceptos", "/personas", "/grupos", "/sellos", "/libros",
    "/estudios",
})

# Severidad de cada campo. «critico» va con asunto propio en el correo.
ESTRUCTURALES = ("title", "description", "canonical", "h1", "robots", "x_robots",
                 "hreflang")
CONTENIDO = ("headings", "contenido", "enlaces", "jsonld", "og")
LENTO_FACTOR = 3.0
LENTO_MIN_MS = 1500


@dataclass
class Cambio:
    campo: str
    antes: str | None
    despues: str | None
    severidad: str                       # critico | estructural | contenido | aviso
    detalle: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# HTML → campos
# --------------------------------------------------------------------------- #
def _texto(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _bloques(el) -> str:
    """El texto con un salto por bloque: si no, el H1 y el H2 se pegaban a la primera
    frase y el diff del panel enseñaba «Interludio La letra Dejo las ventanas…»."""
    lineas = (re.sub(r"\s+", " ", t).strip() for t in el.get_text("\n").split("\n"))
    return "\n".join(t for t in lineas if t)


def _path(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url)
    return ("/" + p.path.strip("/")) if p.path else "/"


def parse(html: str, *, path: str, headers: dict | None = None) -> dict:
    """Los campos que se vigilan de una página. Determinista: el mismo HTML da lo mismo."""
    soup = BeautifulSoup(html or "", "html.parser")
    head = soup.head or soup

    def meta(**attrs) -> str | None:
        el = head.find("meta", attrs=attrs)
        return (el.get("content") or "").strip() if el else None

    canonical = head.find("link", rel="canonical")
    jsonld: set[str] = set()
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        nodos = data.get("@graph", [data]) if isinstance(data, dict) else data
        for n in nodos if isinstance(nodos, list) else []:
            t = n.get("@type") if isinstance(n, dict) else None
            jsonld.update(t if isinstance(t, list) else [t] if t else [])

    main = soup.find("main") or soup.body or soup
    for basura in main.find_all(["script", "style", "noscript", "template"]):
        basura.decompose()
    for ignorar in main.select('[data-monitor="ignore"]'):
        ignorar.decompose()

    headings = [f"{h.name}: {_texto(h)}" for h in main.find_all(re.compile(r"^h[1-6]$"))]
    h1 = next((h.split(": ", 1)[1] for h in headings if h.startswith("h1: ")), None)
    if path in LISTADOS:
        primer_p = main.find("p")
        contenido = " · ".join(x for x in (h1, _texto(primer_p) if primer_p else "") if x)
        enlaces: list[str] = []
    else:
        contenido = _bloques(main)
        enlaces = sorted({_path(a["href"]) for a in main.find_all("a", href=True)
                          if a["href"].startswith("/") and not a["href"].startswith("//")})
    imgs_sin_alt = sum(1 for i in main.find_all("img") if not (i.get("alt") or "").strip())
    h = {k.lower(): v for k, v in (headers or {}).items()}
    return {
        "v": VERSION_PARSER,
        "title": _texto(head.title) if head.title else None,
        "description": meta(name="description"),
        "robots": meta(name="robots"),
        "x_robots": h.get("x-robots-tag"),
        "canonical": canonical.get("href") if canonical else None,
        "h1": h1,
        "headings": headings,
        "hreflang": sorted(f"{link.get('hreflang')}={link.get('href')}"
                           for link in head.find_all("link", rel="alternate")
                           if link.get("hreflang")),
        "og": {k: meta(property=f"og:{k}") for k in ("title", "description", "image")},
        "jsonld": sorted(jsonld),
        "enlaces": enlaces,
        "palabras": len(contenido.split()),
        "imgs_sin_alt": imgs_sin_alt,
        "contenido": contenido,
        "contenido_hash": hashlib.sha256(contenido.encode()).hexdigest()[:32],
    }


# --------------------------------------------------------------------------- #
# Petición
# --------------------------------------------------------------------------- #
@dataclass
class Foto:
    path: str
    status: int
    final_url: str
    cadena: list[list]          # [[status, url], ...] de cada redirección
    ms: int
    bytes: int
    campos: dict


def snapshot(client, path: str, *, base: str = SITE) -> Foto:
    """Pide la URL siguiendo las redirecciones a mano, para guardar la cadena."""
    url = urljoin(base, path)
    cadena: list[list] = []
    t0 = time.monotonic()
    for _ in range(MAX_REDIRECTS + 1):
        resp = client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
            cadena.append([resp.status_code, url])
            url = urljoin(url, resp.headers["location"])
            continue
        break
    ms = int((time.monotonic() - t0) * 1000)
    html = resp.text if "html" in resp.headers.get("content-type", "") else ""
    return Foto(path=path, status=resp.status_code, final_url=url, cadena=cadena, ms=ms,
                bytes=len(resp.content), campos=parse(html, path=path, headers=resp.headers))


# --------------------------------------------------------------------------- #
# Foto vs foto
# --------------------------------------------------------------------------- #
def _noindex(valor: str | None) -> bool:
    return "noindex" in (valor or "").lower()


def _como_texto(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    return str(v)


def _frases(texto: str) -> list[str]:
    return [f.strip() for bloque in (texto or "").split("\n")
            for f in re.split(r"(?<=[.!?…])\s+", bloque) if f.strip()]


def _detalle_contenido(antes: str, despues: str, tope: int = 12) -> dict:
    """Qué frases entran y salen: el diff que se enseña, no el texto entero."""
    a, b = _frases(antes), _frases(despues)
    salen, entran = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            salen += a[i1:i2]
        if op in ("insert", "replace"):
            entran += b[j1:j2]
    return {"salen": salen[:tope], "entran": entran[:tope],
            "n_salen": len(salen), "n_entran": len(entran)}


def diff(antes: dict, despues: dict, *, path: str) -> list[Cambio]:
    """Lo que cambió entre dos fotos de la MISMA URL.

    `antes`/`despues` llevan `status`, `final_url`, `cadena`, `ms` y `campos`, que
    es lo que se guarda en `page_snapshots`.
    """
    out: list[Cambio] = []
    if antes["status"] != despues["status"]:
        critico = despues["status"] != 200 or antes["status"] != 200
        out.append(Cambio("status", str(antes["status"]), str(despues["status"]),
                          "critico" if critico else "estructural"))
    if _path(antes["final_url"]) != _path(despues["final_url"]):
        out.append(Cambio("redireccion", antes["final_url"], despues["final_url"], "critico",
                          {"cadena_antes": antes["cadena"], "cadena_despues": despues["cadena"]}))
    if despues["status"] != 200:
        return out      # una página caída no tiene title que comparar

    ca, cd = antes["campos"], despues["campos"]
    for campo in ESTRUCTURALES + CONTENIDO:
        va, vd = ca.get(campo), cd.get(campo)
        if campo == "contenido":
            if ca.get("contenido_hash") == cd.get("contenido_hash"):
                continue
            out.append(Cambio("contenido", va, vd, "contenido",
                              _detalle_contenido(va or "", vd or "")))
            continue
        if va == vd:
            continue
        sev = "estructural" if campo in ESTRUCTURALES else "contenido"
        if campo in ("robots", "x_robots") and _noindex(vd) and not _noindex(va):
            sev = "critico"
        if campo == "canonical" and vd and _path(vd) != path:
            sev = "critico"          # apunta a OTRA página
        detalle = {}
        if isinstance(va, list) and isinstance(vd, list):
            detalle = {"salen": [x for x in va if x not in vd],
                       "entran": [x for x in vd if x not in va]}
        out.append(Cambio(campo, _como_texto(va), _como_texto(vd), sev, detalle))

    if cd.get("imgs_sin_alt", 0) > ca.get("imgs_sin_alt", 0):
        out.append(Cambio("imgs_sin_alt", str(ca.get("imgs_sin_alt", 0)),
                          str(cd["imgs_sin_alt"]), "aviso"))
    ms_a, ms_d = antes.get("ms") or 0, despues.get("ms") or 0
    if ms_a and ms_d >= LENTO_MIN_MS and ms_d >= LENTO_FACTOR * ms_a:
        out.append(Cambio("tiempo", f"{ms_a} ms", f"{ms_d} ms", "aviso"))
    return out
