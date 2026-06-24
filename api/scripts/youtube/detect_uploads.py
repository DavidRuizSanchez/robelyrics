"""Detección de vídeos nuevos para ingerir al corpus (Juancares + entrevistas).

Corre en el SERVER (cron cada 3 días). NO descarga ni transcribe nada (la IP del
datacenter dispara el antibot de YouTube): solo DETECTA y AVISA.

  1. Lista los uploads de @juancaraes (YouTube Data API) → target=corpus.
  2. Siembra las entrevistas de Robe de data/robe_interviews.yaml (medium=video)
     → target=robe_voice, kind=robe_interview|about_robe según author_is_robe.
  3. Deduplica contra lo ya encolado y lo ya ingerido (interpretation_sources).
  4. Inserta los nuevos como `detected` en youtube_ingest_queue.
  5. Si hay novedades, manda al admin un email con un CTA firmado de 1 click que
     marca el batch como `approved`. A partir de ahí, el daemon local de la Mac
     (IP residencial) los transcribe y empuja a prod.

Uso:
    python -m scripts.youtube.detect_uploads
    python -m scripts.youtube.detect_uploads --dry-run        # no inserta, no envía
    python -m scripts.youtube.detect_uploads --limit 5        # tope de uploads (smoke)
    python -m scripts.youtube.detect_uploads --no-juancares   # solo entrevistas yaml
"""
from __future__ import annotations

import argparse
import logging
import os
import re

import httpx
import yaml

from app.config import get_settings
from app.db.models import InterpretationSource, YouTubeIngestQueue
from scripts.research.common import DATA_DIR, get_session
from scripts.research.fetch_youtube import (
    get_uploads_playlist,
    list_videos,
    parse_iso,
    resolve_channel_id,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

HANDLE = "juancaraes"
JUANCARES_AUTHOR = "Juancares"
# kinds que viven en el corpus por video_id (para dedup contra lo ya ingerido).
INGESTED_KINDS = ("youtube_transcript", "robe_interview", "about_robe")

_VID_RE = re.compile(
    r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{6,})"
)


def video_id_from_url(url: str | None) -> str | None:
    m = _VID_RE.search(url or "")
    return m.group(1) if m else None


def _already_ingested_ids(db) -> set[str]:
    rows = (
        db.query(InterpretationSource.url)
        .filter(InterpretationSource.kind.in_(INGESTED_KINDS))
        .all()
    )
    return {vid for (u,) in rows if (vid := video_id_from_url(u))}


def _queued_ids(db) -> set[str]:
    """video_ids ya en la cola (cualquier estado): no re-detectar."""
    rows = db.query(YouTubeIngestQueue.video_id).all()
    return {vid for (vid,) in rows}


def _juancares_candidates(limit: int | None) -> list[dict]:
    """Uploads de @juancaraes → filas target=corpus."""
    settings = get_settings()
    if not settings.youtube_api_key:
        logger.warning("YOUTUBE_API_KEY no configurada: salto Juancares")
        return []
    with httpx.Client(timeout=30) as c:
        cid = resolve_channel_id(c, settings.youtube_api_key, HANDLE)
        if not cid:
            logger.warning("canal @%s no resuelto", HANDLE)
            return []
        pl = get_uploads_playlist(c, settings.youtube_api_key, cid)
        if not pl:
            return []
        videos = list_videos(c, settings.youtube_api_key, pl, limit=limit)
    out = []
    for v in videos:
        out.append({
            "video_id": v["video_id"],
            "url": f"https://www.youtube.com/watch?v={v['video_id']}",
            "title": v.get("title"),
            "channel": HANDLE,
            "target": "corpus",
            "kind": "youtube_transcript",
            "author": JUANCARES_AUTHOR,
            "published_at": parse_iso(v.get("published_at")),
        })
    return out


def _robe_interview_candidates() -> list[dict]:
    """Entrevistas de robe_interviews.yaml (solo medium=video) → target=robe_voice."""
    path = DATA_DIR / "robe_interviews.yaml"
    if not path.exists():
        logger.warning("%s no encontrado: salto entrevistas", path)
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for entry in data.get("interviews", []):
        if entry.get("medium") != "video":
            continue  # los medium=text se ingieren aparte (fetch de artículo)
        vid = video_id_from_url(entry.get("url"))
        if not vid:
            continue
        is_robe = bool(entry.get("author_is_robe"))
        out.append({
            "video_id": vid,
            "url": entry["url"],
            "title": entry.get("title"),
            "channel": entry.get("author"),
            "target": "robe_voice",
            "kind": "robe_interview" if is_robe else "about_robe",
            "author": entry.get("author"),
            "published_at": None,
        })
    return out


def _send_email(new_rows: list[YouTubeIngestQueue]) -> None:
    from app.services.auth import create_youtube_ingest_token
    from app.services.email import EmailError, send_email

    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        logger.warning("ADMIN_EMAIL no configurado: no se envía email")
        return
    settings = get_settings()
    site = settings.site_url.rstrip("/")
    token = create_youtube_ingest_token([r.id for r in new_rows])
    approve_url = f"{site}/api/public/youtube-ingest?token={token}"

    corpus = [r for r in new_rows if r.target == "corpus"]
    voice = [r for r in new_rows if r.target == "robe_voice"]

    def _section(titulo: str, rows: list[YouTubeIngestQueue]) -> str:
        if not rows:
            return ""
        lis = "".join(
            f'<li style="margin:0 0 8px;font-family:Georgia,serif;font-size:15px;'
            f'color:#ede4d3;">{(r.title or r.video_id)}</li>'
            for r in rows
        )
        return (
            f'<p style="font-family:\'Courier New\',monospace;font-size:11px;'
            f'letter-spacing:3px;text-transform:uppercase;color:#a83a3a;'
            f'margin:24px 0 10px;">{titulo} ({len(rows)})</p>'
            f'<ul style="list-style:none;padding:0;margin:0;">{lis}</ul>'
        )

    n = len(new_rows)
    html = f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  <div style="max-width:640px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#a83a3a;margin:0 0 12px;">
      entre interiores · ingesta de YouTube
    </p>
    <h1 style="font-family:Georgia,serif;font-size:25px;color:#ede4d3;margin:0 0 8px;line-height:1.2;">
      {n} vídeo{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''} para el corpus
    </h1>
    <p style="font-family:Georgia,serif;font-style:italic;color:rgba(237,228,211,0.6);font-size:14px;margin:0 0 8px;line-height:1.6;">
      Con un click los apruebas. Tu Mac los descargará, transcribirá y subirá sola
      (IP residencial). Nada se descarga desde el servidor.
    </p>
    {_section("Juancares (corpus)", corpus)}
    {_section("Entrevistas de Robe (voz)", voice)}
    <div style="margin:32px 0 0;padding:18px 0 0;border-top:1px solid rgba(237,228,211,0.08);text-align:center;">
      <a href="{approve_url}" style="display:inline-block;padding:14px 28px;border:1px solid #a83a3a;color:#a83a3a;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        aprobar e ingerir
      </a>
    </div>
  </div>
</body>
</html>"""
    text_lines = [f"{n} vídeos nuevos para ingerir.", ""]
    for label, rows in (("JUANCARES", corpus), ("ENTREVISTAS DE ROBE", voice)):
        if not rows:
            continue
        text_lines.append(f"== {label} ({len(rows)}) ==")
        text_lines += [f"· {(r.title or r.video_id)}" for r in rows]
        text_lines.append("")
    text_lines.append(f"Aprobar e ingerir: {approve_url}")
    try:
        send_email(
            to=admin_email,
            subject=f"🎬 {n} vídeo{'s' if n != 1 else ''} para ingerir al corpus",
            html=html,
            text="\n".join(text_lines),
        )
        logger.info("Email de detección enviado a %s", admin_email)
    except EmailError as e:
        logger.error("Fallo al enviar email: %s", e)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="No inserta ni envía email.")
    ap.add_argument("--limit", type=int, default=None, help="Tope de uploads Juancares.")
    ap.add_argument("--no-juancares", action="store_true", help="Solo entrevistas yaml.")
    ap.add_argument("--no-interviews", action="store_true", help="Solo Juancares.")
    args = ap.parse_args()

    candidates: list[dict] = []
    if not args.no_juancares:
        candidates += _juancares_candidates(args.limit)
    if not args.no_interviews:
        candidates += _robe_interview_candidates()

    with get_session() as db:
        seen = _queued_ids(db) | _already_ingested_ids(db)
        # Dedup interno del propio lote (un video_id repetido en yaml).
        fresh: list[dict] = []
        batch_seen: set[str] = set()
        for c in candidates:
            vid = c["video_id"]
            if vid in seen or vid in batch_seen:
                continue
            batch_seen.add(vid)
            fresh.append(c)

        logger.info(
            "%d candidatos · %d ya conocidos · %d nuevos",
            len(candidates), len(candidates) - len(fresh), len(fresh),
        )
        if not fresh:
            logger.info("Nada nuevo que ingerir.")
            return
        if args.dry_run:
            for c in fresh:
                logger.info("  + [%s/%s] %s", c["target"], c["kind"], (c["title"] or c["video_id"]))
            return

        new_rows = [YouTubeIngestQueue(status="detected", **c) for c in fresh]
        db.add_all(new_rows)
        db.flush()  # asigna ids antes de firmar el token
        ids = [r.id for r in new_rows]
        db.commit()

    # Recargar para el email (sesión nueva; el commit cerró la anterior).
    with get_session() as db:
        rows = (
            db.query(YouTubeIngestQueue)
            .filter(YouTubeIngestQueue.id.in_(ids))
            .all()
        )
        _send_email(rows)


if __name__ == "__main__":
    main()
