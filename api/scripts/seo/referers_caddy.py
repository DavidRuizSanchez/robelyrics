"""Visitas reales por origen, sacadas del log de acceso de Caddy.

El log lo cuenta todo, también a quien rechaza las cookies (GA4 no lo ve), pero hay
que limpiarlo antes de contar nada. Corre en la Mac sobre un extracto del server:

    ssh robelyrics 'docker exec caddy sh -c "(zcat /data/access-entreinteriores-*.gz; \
        cat /data/access-entreinteriores.log) | grep -F \\"Sec-Fetch-Dest\\\\\\":[\\\\\\"document\\""' \
        > /tmp/x/documentos.jsonl
    python3 -I api/scripts/seo/referers_caddy.py /tmp/x/documentos.jsonl --desde 2026-09-29 --hasta 2026-10-28

Qué se descarta, y por qué:
- **Prefetch de Chrome** (`Sec-Purpose: prefetch…`). Desde la SERP, Chrome precarga los
  primeros resultados a través del proxy de Google (IPs `2001:4860:7…`). Nadie ha hecho
  clic. Medido el 29-10-2026: eran 2.282 de 3.243 «visitas» de Google, y sin este filtro
  el primer informe de redes triplicó el tráfico de buscadores.
- Bots por User-Agent, respuestas ≥ 400 y peticiones que no son de documento (las de RSC
  de Next llevan `Sec-Fetch-Dest: empty`, son navegación interna).
- Referers internos (entreinteriores.com).

«Búsqueda Google» excluye la app de Gmail, Gemini y la propia Search Console, que llevan
dominio de Google y no son búsqueda: así es como cuadra con los clics de GSC.
Las fechas son UTC; GSC corta el día en hora del Pacífico.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

BOT = re.compile(r"bot|crawl|spider|slurp|facebookexternalhit|preview|curl|python|headless|monitor",
                 re.I)
PROPIOS = ("entreinteriores.com", "www.entreinteriores.com")

SOCIAL = {
    "instagram": ("instagram.com",),
    "facebook": ("facebook.com", "fb.com"),
    "x/twitter": ("t.co", "twitter.com", "x.com"),
    "threads": ("threads.net", "threads.com"),
    "whatsapp": ("whatsapp.com", "wa.me"),
    "telegram": ("t.me", "telegram.org"),
    "reddit": ("reddit.com",),
    "youtube": ("youtube.com",),
    "pinterest": ("pinterest.com", "pinterest.es"),
    "bluesky": ("bsky.app",),
    "tiktok": ("tiktok.com",),
    "linkedin": ("linkedin.com", "lnkd.in"),
}
GOOGLE_NO_BUSQUEDA = ("com.google.android.gm", "gemini.google.com", "search.google.com",
                      "mail.google.com")


def _es(host: str, dominios: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in dominios)


def canal(host: str) -> str:
    host = host.removeprefix("www.")
    for nombre, dominios in SOCIAL.items():
        if _es(host, dominios):
            return f"red · {nombre}"
    if re.search(r"(^|\.)google\.", host) or host == "com.google.android.googlequicksearchbox":
        return "otros google · " + host if host in GOOGLE_NO_BUSQUEDA else "búsqueda · google"
    if re.search(r"bing\.com|duckduckgo|yahoo\.|ecosia|yandex|search\.brave|startpage|qwant|baidu",
                 host):
        return "búsqueda · otros"
    if re.search(r"chatgpt|openai|perplexity|copilot|claude\.ai", host):
        return "asistentes IA"
    return "referral · " + host


def contar(ruta: str, desde: datetime, hasta: datetime) -> tuple[collections.Counter, dict, dict]:
    visitas: collections.Counter = collections.Counter()
    paginas: dict = collections.defaultdict(collections.Counter)
    descartes: collections.Counter = collections.Counter()
    with open(ruta, encoding="utf-8") as fh:
        filas = [json.loads(linea) for linea in fh]
    for f in filas:
        if not (desde.timestamp() <= f["ts"] < hasta.timestamp()):
            continue
        h = f["request"].get("headers", {})
        if "document" not in (h.get("Sec-Fetch-Dest") or [""])[0]:
            descartes["no documento"] += 1
            continue
        if "prefetch" in (h.get("Sec-Purpose") or h.get("Purpose") or [""])[0]:
            descartes["prefetch"] += 1
            continue
        if BOT.search((h.get("User-Agent") or [""])[0]):
            descartes["bot"] += 1
            continue
        if f.get("status", 200) >= 400:
            descartes["status ≥ 400"] += 1
            continue
        host = urlparse((h.get("Referer") or [""])[0]).hostname or ""
        if not host:
            descartes["sin referer (directo, apps)"] += 1
            continue
        if host in PROPIOS:
            descartes["referer interno"] += 1
            continue
        c = canal(host)
        visitas[c] += 1
        paginas[c][f["request"]["uri"].split("?")[0]] += 1
    return visitas, paginas, descartes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("extracto", help="JSONL del log de Caddy (solo documentos)")
    ap.add_argument("--desde", required=True, help="YYYY-MM-DD (UTC, incluido)")
    ap.add_argument("--hasta", required=True, help="YYYY-MM-DD (UTC, incluido)")
    ap.add_argument("--paginas", type=int, default=0, help="páginas de entrada por canal")
    args = ap.parse_args()

    desde = datetime.fromisoformat(args.desde).replace(tzinfo=UTC)
    hasta = datetime.fromisoformat(args.hasta).replace(tzinfo=UTC) + timedelta(days=1)
    visitas, paginas, descartes = contar(args.extracto, desde, hasta)

    print(f"Caddy · {args.desde} → {args.hasta} (UTC)")
    for c, n in visitas.most_common():
        print(f"  {c:50} {n:6}")
    print("Descartado:", dict(descartes))
    if args.paginas:
        for c in visitas:
            if not c.startswith("referral"):
                print(f"\n{c}:", paginas[c].most_common(args.paginas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
