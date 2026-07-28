"""Descarga el feed público de cuentas de Instagram de referencia.

Lee una lista de usernames y, para cada uno, pide a la Graph API su perfil y
sus últimas publicaciones (`business_discovery`). Vuelca un JSON crudo que
luego mastica `analyze_benchmark`.

No inventa nada: la cuenta que no se pueda leer (personal, inexistente, con
restricción de edad) queda registrada con el error literal de la API, y el
resumen final dice cuántas entraron y cuántas no.

Uso:
    python -m scripts.instagram.benchmark_accounts
    python -m scripts.instagram.benchmark_accounts --usernames cuenta1,cuenta2
    python -m scripts.instagram.benchmark_accounts --accounts /app/data/mis_cuentas.txt \
        --max-posts 100 --out /tmp/ig_benchmark.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

from app.services.instagram import benchmark

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# httpx loguea la URL COMPLETA de cada petición, y la Graph API lleva el
# `access_token` en la query string: a nivel INFO el token acababa impreso en
# claro en el log del cron. Se silencia a WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)

DEFAULT_ACCOUNTS = "/app/data/instagram_benchmark_accounts.txt"
DEFAULT_OUT = "/tmp/ig_benchmark.json"


def _read_accounts(path: str) -> list[str]:
    """Un username por línea. Se ignoran vacías y comentarios con '#'."""
    if not os.path.exists(path):
        raise SystemExit(f"No existe el fichero de cuentas: {path}")
    out: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line:
                out.extend(p for p in line.split(",") if p.strip())
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", default=DEFAULT_ACCOUNTS)
    parser.add_argument("--usernames", default=None, help="Lista separada por comas.")
    parser.add_argument("--max-posts", type=int, default=100)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    raw = args.usernames.split(",") if args.usernames else _read_accounts(args.accounts)
    usernames = list(dict.fromkeys(benchmark._clean_username(u) for u in raw if u.strip()))
    if not usernames:
        raise SystemExit("Lista de cuentas vacía.")

    logger.info("Benchmark IG · %d cuentas · hasta %d posts each", len(usernames), args.max_posts)

    results: list[dict] = []
    for i, user in enumerate(usernames, 1):
        res = benchmark.discover(user, media_limit=args.page_size, max_posts=args.max_posts)
        if res["ok"]:
            prof = res["profile"] or {}
            logger.info(
                "  [%d/%d] %-24s OK · %s seguidores · %d posts leídos%s",
                i, len(usernames), user,
                f'{prof.get("followers_count", "n/d"):,}'.replace(",", ".")
                if isinstance(prof.get("followers_count"), int) else "n/d",
                len(res["media"]),
                " (truncado)" if res["truncated"] else "",
            )
        else:
            logger.warning("  [%d/%d] %-24s NO LEÍDA · %s", i, len(usernames), user, res["error"])
        results.append(res)
        time.sleep(1.0)  # cortesía con el rate limit de la Graph API

    ok = [r for r in results if r["ok"]]
    payload = {
        "accounts_requested": len(usernames),
        "accounts_ok": len(ok),
        "accounts_failed": len(results) - len(ok),
        "posts_total": sum(len(r["media"]) for r in ok),
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Listo: %d/%d cuentas leídas, %d publicaciones. → %s",
        len(ok), len(usernames), payload["posts_total"], args.out,
    )
    if payload["accounts_failed"]:
        logger.warning(
            "%d cuentas NO se pudieron leer (ver 'error' en el JSON). "
            "Casi siempre: no son Business/Creator.",
            payload["accounts_failed"],
        )


if __name__ == "__main__":
    main()
