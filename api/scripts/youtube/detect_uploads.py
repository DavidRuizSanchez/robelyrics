"""Detección de vídeos nuevos para ingerir al corpus (canales + entrevistas).

Corre en el SERVER (cron cada 3 días). NO descarga ni transcribe nada (la IP del
datacenter dispara el antibot de YouTube): solo DETECTA y AVISA.

  1. Lista los uploads de cada canal con `ingest: true` en data/sources.yaml
     (YouTube Data API) → target=corpus.
  2. Siembra las entrevistas de Robe de data/robe_interviews.yaml (medium=video)
     → target=robe_voice, kind=robe_interview|about_robe según author_is_robe.
  3. Deduplica contra lo ya encolado y lo ya ingerido (interpretation_sources).
  4. Inserta los nuevos como `detected` en youtube_ingest_queue.
  5. Si hay novedades, manda al admin un email con un CTA firmado de 1 click que
     marca el batch como `approved`. A partir de ahí, el daemon local de la Mac
     (IP residencial) los transcribe y empuja a prod.

Un canal puede no ser monotemático. @juancaraes lo es (`relevance: all`), pero
@tesonica sube sobre todo metal y solo una parte va de Extremoduro, así que lleva
`relevance: catalog` y pasa por `app.services.youtube_relevance`: se encola lo que
menciona a Robe/Extremoduro o un título del catálogo. El MOTIVO de cada match va
en el email, que es donde se aprueba de verdad.

Uso:
    python -m scripts.youtube.detect_uploads
    python -m scripts.youtube.detect_uploads --dry-run        # no inserta, no envía
    python -m scripts.youtube.detect_uploads --limit 5        # tope de uploads (smoke)
    python -m scripts.youtube.detect_uploads --only-channel @tesonica
    python -m scripts.youtube.detect_uploads --skip-channel @juancaraes
    python -m scripts.youtube.detect_uploads --no-interviews  # solo canales
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
from app.services.youtube_relevance import build_vocab, is_relevant
from scripts.research.common import DATA_DIR, get_session, load_sources_yaml
from scripts.research.fetch_youtube import (
    get_uploads_playlist,
    list_videos,
    parse_iso,
    resolve_channel_id,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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


def _ingest_channels() -> list[dict]:
    """Canales de data/sources.yaml marcados con `ingest: true`."""
    entries = load_sources_yaml().get("youtube") or []
    return [e for e in entries if isinstance(e, dict) and e.get("ingest")]


def _handle_of(cfg: dict) -> str:
    """Handle sin la arroba (lo que espera resolve_channel_id)."""
    return (cfg.get("handle") or cfg.get("name") or "").lstrip("@")


def _channel_candidates(cfg: dict, limit: int | None, vocab) -> list[dict]:
    """Uploads de un canal → filas target=corpus, filtradas según `relevance`.

    El dict lleva una clave `reasons` que NO es columna del modelo: la consume el
    email y `main` la retira antes de construir la fila.
    """
    handle = _handle_of(cfg)
    settings = get_settings()
    if not settings.youtube_api_key:
        logger.warning("YOUTUBE_API_KEY no configurada: salto @%s", handle)
        return []
    with httpx.Client(timeout=30) as c:
        cid = resolve_channel_id(c, settings.youtube_api_key, handle)
        if not cid:
            logger.warning("canal @%s no resuelto", handle)
            return []
        pl = get_uploads_playlist(c, settings.youtube_api_key, cid)
        if not pl:
            return []
        videos = list_videos(c, settings.youtube_api_key, pl, limit=limit)

    filtra = (cfg.get("relevance") or "all") != "all"
    use_desc = bool(cfg.get("match_description"))
    author = cfg.get("ingest_author") or cfg.get("name") or handle

    out = []
    for v in videos:
        reasons: list[str] = []
        if filtra:
            ok, reasons = is_relevant(
                v.get("title"), v.get("description"),
                vocab=vocab, use_description=use_desc,
            )
            if not ok:
                continue
        out.append({
            "video_id": v["video_id"],
            "url": f"https://www.youtube.com/watch?v={v['video_id']}",
            "title": v.get("title"),
            "channel": handle,
            "target": "corpus",
            "kind": "youtube_transcript",
            "author": author,
            "published_at": parse_iso(v.get("published_at")),
            "reasons": reasons,
        })
    logger.info(
        "@%s: %d uploads · %d relevantes%s",
        handle, len(videos), len(out), "" if filtra else " (sin filtro)",
    )
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
            "reasons": ["inventario robe_interviews.yaml"],
        })
    return out


def _send_email(
    new_rows: list[YouTubeIngestQueue], reasons_by_vid: dict[str, list[str]] | None = None
) -> None:
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

    reasons_by_vid = reasons_by_vid or {}
    voice = [r for r in new_rows if r.target == "robe_voice"]
    # El corpus se agrupa por canal: con varios canales barriéndose, saber de quién
    # es cada vídeo es lo que permite decidir si aprobarlo.
    corpus_by_channel: dict[str, list[YouTubeIngestQueue]] = {}
    for r in new_rows:
        if r.target == "corpus":
            corpus_by_channel.setdefault(r.channel or "?", []).append(r)

    def _why(r: YouTubeIngestQueue) -> str:
        """Motivo del match, en pequeño y bajo el título."""
        rs = reasons_by_vid.get(r.video_id) or []
        if not rs:
            return ""
        txt = " · ".join(rs[:2])
        return (
            f'<div style="font-family:\'Courier New\',monospace;font-size:10px;'
            f'color:rgba(237,228,211,0.45);margin:2px 0 0;">{txt}</div>'
        )

    def _section(titulo: str, rows: list[YouTubeIngestQueue]) -> str:
        if not rows:
            return ""
        lis = "".join(
            f'<li style="margin:0 0 8px;font-family:Georgia,serif;font-size:15px;'
            f'color:#ede4d3;">{(r.title or r.video_id)}{_why(r)}</li>'
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
    {"".join(_section(f"@{ch} (corpus)", rows) for ch, rows in sorted(corpus_by_channel.items()))}
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
    secciones = [(f"@{ch}", rows) for ch, rows in sorted(corpus_by_channel.items())]
    secciones.append(("ENTREVISTAS DE ROBE", voice))
    for label, rows in secciones:
        if not rows:
            continue
        text_lines.append(f"== {label} ({len(rows)}) ==")
        for r in rows:
            text_lines.append(f"· {(r.title or r.video_id)}")
            rs = reasons_by_vid.get(r.video_id) or []
            if rs:
                text_lines.append(f"    ↳ {' · '.join(rs[:2])}")
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
    ap.add_argument("--limit", type=int, default=None, help="Tope de uploads por canal.")
    ap.add_argument("--only-channel", default=None, help="Solo este handle (p.ej. @tesonica).")
    ap.add_argument("--skip-channel", action="append", default=[], help="Excluir handle (repetible).")
    ap.add_argument("--no-channels", action="store_true", help="Solo entrevistas yaml.")
    ap.add_argument("--no-interviews", action="store_true", help="Solo canales.")
    # Alias históricos: el cron y la documentación vieja los usan.
    ap.add_argument("--no-juancares", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    skip = {h.lstrip("@") for h in args.skip_channel}
    if args.no_juancares:
        skip.add("juancaraes")
    only = args.only_channel.lstrip("@") if args.only_channel else None

    candidates: list[dict] = []
    if not args.no_channels:
        channels = [
            cfg for cfg in _ingest_channels()
            if _handle_of(cfg) not in skip and (only is None or _handle_of(cfg) == only)
        ]
        if not channels:
            logger.warning("ningún canal con ingest: true que barrer")
        # El vocabulario del filtro se deriva de la BD una sola vez por pasada.
        needs_vocab = any((cfg.get("relevance") or "all") != "all" for cfg in channels)
        vocab = None
        if needs_vocab:
            with get_session() as db:
                vocab = build_vocab(db)
            logger.info(
                "vocabulario de relevancia: %d títulos distintivos · %d cortos",
                len(vocab.distinctive), len(vocab.short),
            )
        for cfg in channels:
            candidates += _channel_candidates(cfg, args.limit, vocab)
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
                logger.info(
                    "  + [%s/%s · @%s] %s",
                    c["target"], c["kind"], c.get("channel") or "?",
                    (c["title"] or c["video_id"]),
                )
                for r in (c.get("reasons") or [])[:3]:
                    logger.info("        ↳ %s", r)
            return

        # `reasons` es contexto para el email, no una columna del modelo.
        reasons_by_vid = {c["video_id"]: (c.get("reasons") or []) for c in fresh}
        new_rows = [
            YouTubeIngestQueue(
                status="detected", **{k: v for k, v in c.items() if k != "reasons"}
            )
            for c in fresh
        ]
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
        _send_email(rows, reasons_by_vid)


if __name__ == "__main__":
    main()
