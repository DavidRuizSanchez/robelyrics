"""Calcula los patrones de publicación del JSON de `benchmark_accounts`.

Todo lo que sale de aquí es aritmética sobre datos reales de la Graph API:
formato usado, cadencia, longitud y forma del caption, hashtags, hora de
publicación y engagement. Nada es estimado — el dato que la API no devuelve
(p.ej. `like_count` en cuentas que ocultan los likes) se cuenta como `n/d` y se
excluye de las medianas, diciendo de cuántos posts se trata.

Uso:
    python -m scripts.instagram.analyze_benchmark
    python -m scripts.instagram.analyze_benchmark --in /tmp/ig_benchmark.json \
        --out-dir /tmp/ig_patterns --top 25
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime
from statistics import median

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

HASHTAG_RE = re.compile(r"#\w+", re.UNICODE)
MENTION_RE = re.compile(r"@[\w.]+", re.UNICODE)
# Rangos de emoji más comunes. Es una aproximación declarada, no un conteo
# exhaustivo de todo el estándar Unicode.
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _med(values: list[float]) -> float | None:
    return round(median(values), 2) if values else None


def _parse_ts(ts: str | None) -> datetime | None:
    """'2026-05-01T12:34:56+0000' → datetime. La Graph API entrega UTC."""
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def _post_metrics(post: dict, followers: int | None) -> dict:
    caption = post.get("caption") or ""
    hashtags = HASHTAG_RE.findall(caption)
    likes = post.get("like_count")
    comments = post.get("comments_count")
    engagement = (likes + comments) if isinstance(likes, int) and isinstance(comments, int) else None
    lines = [ln for ln in caption.split("\n")]
    return {
        "media_type": post.get("media_type") or "n/d",
        "product_type": post.get("media_product_type") or "n/d",
        "ts": _parse_ts(post.get("timestamp")),
        "permalink": post.get("permalink"),
        "chars": len(caption),
        "words": len(caption.split()),
        "lines": len([ln for ln in lines if ln.strip()]),
        "has_caption": bool(caption.strip()),
        "hook": (lines[0].strip() if lines else "")[:180],
        "n_hashtags": len(hashtags),
        "hashtags": [h.lower() for h in hashtags],
        "n_mentions": len(MENTION_RE.findall(caption)),
        "n_emoji": len(EMOJI_RE.findall(caption)),
        "likes": likes,
        "comments": comments,
        "views": post.get("view_count"),
        "engagement": engagement,
        "er": round(engagement / followers * 100, 3)
        if engagement is not None and isinstance(followers, int) and followers > 0
        else None,
    }


def analyze_account(res: dict) -> dict:
    prof = res.get("profile") or {}
    followers = prof.get("followers_count")
    posts = [_post_metrics(p, followers) for p in res.get("media") or []]
    stamps = sorted(p["ts"] for p in posts if p["ts"])

    # Cadencia real: posts leídos / semanas que abarca la muestra.
    per_week = None
    if len(stamps) >= 2:
        dias = (stamps[-1] - stamps[0]).days
        if dias > 0:
            per_week = round(len(posts) / (dias / 7), 2)

    with_eng = [p for p in posts if p["engagement"] is not None]
    er_por_formato: dict[str, float | None] = {}
    for fmt in {p["media_type"] for p in posts}:
        vals = [p["er"] for p in with_eng if p["media_type"] == fmt and p["er"] is not None]
        er_por_formato[fmt] = _med(vals)

    return {
        "username": res["username"],
        "followers": followers,
        "media_count_total": prof.get("media_count"),
        "biography": prof.get("biography"),
        "posts_analizados": len(posts),
        "muestra_desde": stamps[0].date().isoformat() if stamps else None,
        "muestra_hasta": stamps[-1].date().isoformat() if stamps else None,
        "posts_por_semana": per_week,
        "formatos": dict(Counter(p["media_type"] for p in posts).most_common()),
        "product_types": dict(Counter(p["product_type"] for p in posts).most_common()),
        "caption_chars_mediana": _med([p["chars"] for p in posts]),
        "caption_palabras_mediana": _med([p["words"] for p in posts]),
        "caption_lineas_mediana": _med([p["lines"] for p in posts]),
        "posts_sin_caption": sum(1 for p in posts if not p["has_caption"]),
        "hashtags_mediana": _med([p["n_hashtags"] for p in posts]),
        "menciones_mediana": _med([p["n_mentions"] for p in posts]),
        "emojis_mediana": _med([p["n_emoji"] for p in posts]),
        "likes_mediana": _med([p["likes"] for p in posts if isinstance(p["likes"], int)]),
        "comentarios_mediana": _med([p["comments"] for p in posts if isinstance(p["comments"], int)]),
        "er_mediana_pct": _med([p["er"] for p in posts if p["er"] is not None]),
        "er_por_formato_pct": er_por_formato,
        "posts_sin_metricas": len(posts) - len(with_eng),
        "hashtags_top": Counter(h for p in posts for h in p["hashtags"]).most_common(15),
        "horas_utc": dict(Counter(p["ts"].hour for p in posts if p["ts"]).most_common()),
        "dias_semana": dict(Counter(DIAS[p["ts"].weekday()] for p in posts if p["ts"]).most_common()),
        "_posts": posts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="src", default="/tmp/ig_benchmark.json")
    parser.add_argument("--out-dir", default="/tmp/ig_patterns")
    parser.add_argument("--top", type=int, default=25, help="Posts top por ER a volcar.")
    args = parser.parse_args()

    with open(args.src, encoding="utf-8") as fh:
        payload = json.load(fh)
    ok = [r for r in payload["results"] if r.get("ok")]
    fallidas = [r for r in payload["results"] if not r.get("ok")]
    if not ok:
        raise SystemExit("Ninguna cuenta legible en el JSON: no hay nada que analizar.")

    os.makedirs(args.out_dir, exist_ok=True)
    cuentas = [analyze_account(r) for r in ok]

    # --- CSV por cuenta -----------------------------------------------------
    cols = [k for k in cuentas[0] if not k.startswith("_")]
    csv_path = os.path.join(args.out_dir, "cuentas.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for c in cuentas:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                        for k, v in c.items() if k in cols})

    # --- CSV post a post ----------------------------------------------------
    posts_path = os.path.join(args.out_dir, "posts.csv")
    pcols = ["username", "ts", "media_type", "product_type", "chars", "words", "lines",
             "n_hashtags", "n_mentions", "n_emoji", "likes", "comments", "views",
             "engagement", "er", "hook", "permalink"]
    todos: list[dict] = []
    for c in cuentas:
        for p in c["_posts"]:
            row = {**p, "username": c["username"]}
            row["ts"] = p["ts"].isoformat() if p["ts"] else None
            todos.append(row)
    with open(posts_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=pcols, extrasaction="ignore")
        w.writeheader()
        w.writerows(todos)

    # --- Top posts por engagement relativo (lectura cualitativa) ------------
    top = sorted([p for p in todos if p["er"] is not None], key=lambda p: p["er"], reverse=True)
    top_path = os.path.join(args.out_dir, "top_posts.json")
    with open(top_path, "w", encoding="utf-8") as fh:
        json.dump(top[: args.top], fh, ensure_ascii=False, indent=2, default=str)

    # --- Resumen en consola -------------------------------------------------
    fmt_global = Counter(p["media_type"] for p in todos)
    total = sum(fmt_global.values())
    logger.info("=" * 68)
    logger.info("PATRONES · %d cuentas leídas de %d · %d publicaciones",
                len(ok), payload["accounts_requested"], len(todos))
    if fallidas:
        logger.info("Cuentas NO legibles (%d): %s", len(fallidas),
                    ", ".join(f'{r["username"]} ({r["error"]})' for r in fallidas))
    logger.info("-" * 68)
    logger.info("Formato (global): %s", ", ".join(
        f"{k} {v} ({v / total * 100:.0f}%)" for k, v in fmt_global.most_common()))
    logger.info("Caption mediana global: %s caracteres · %s palabras · %s hashtags",
                _med([p["chars"] for p in todos]),
                _med([p["words"] for p in todos]),
                _med([p["n_hashtags"] for p in todos]))
    sin_metricas = sum(c["posts_sin_metricas"] for c in cuentas)
    if sin_metricas:
        logger.info("Posts sin likes/comentarios visibles (n/d, fuera de medianas): %d", sin_metricas)
    logger.info("-" * 68)
    for c in sorted(cuentas, key=lambda c: c["followers"] or 0, reverse=True):
        logger.info(
            "%-24s %8s seg · %5s posts · %s/sem · cap %s car · %s ht · ER %s%%",
            c["username"], c["followers"] if c["followers"] is not None else "n/d",
            c["posts_analizados"], c["posts_por_semana"] or "n/d",
            c["caption_chars_mediana"], c["hashtags_mediana"],
            c["er_mediana_pct"] if c["er_mediana_pct"] is not None else "n/d",
        )
    logger.info("=" * 68)
    logger.info("Salida: %s · %s · %s", csv_path, posts_path, top_path)


if __name__ == "__main__":
    main()
