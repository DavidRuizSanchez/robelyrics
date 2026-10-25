"""Correo «Corpus de la semana»: lo que entró, lo que espera tu clic y si se ha secado.

Fase 5 del plan del corpus. Entre el 29-07 y el 23-10-2026 no entró ni un vídeo y
nadie lo supo: el detector decía «0 nuevos» en un log que nadie lee. Este correo
existe para que eso no vuelva a pasar en silencio, y para que lo que entra solo
(o casi) esté a la vista con un botón de retirar.

Lleva:
  - lo que entró en los últimos 7 días, con su nivel, por qué y «Retirar»;
  - lo que bajó de nivel tras el juez de la transcripción;
  - lo que espera decisión, con «Aprobar» uno a uno, y lo que lleva más de 7 días;
  - el gasto de Whisper del mes y el ritmo de la semana;
  - SEQUÍA: si en 14 días no ha entrado ni cambiado ninguna fuente.

Solo se manda si hay novedad (firma en `notification_digests`) o sequía: una
semana sin nada nuevo y con el corpus creciendo no merece correo.

Uso:
    python -m scripts.notify_corpus --dry-run
    python -m scripts.notify_corpus
"""
from __future__ import annotations

import argparse
import hashlib
import html
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import InterpretationSource, NotificationDigest, YouTubeIngestQueue
from app.db.session import SessionLocal
from app.services import corpus_ritmo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_KIND = "corpus_semana"
DIAS_SEMANA = 7
DIAS_SEQUIA = 14
ESPERA_LARGA_DIAS = 7
REMINDER_DAYS = 14
_MAX_FILAS = 40


def _gather(db, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(UTC)
    semana = ahora - timedelta(days=DIAS_SEMANA)
    entraron = (db.query(YouTubeIngestQueue)
                .filter(YouTubeIngestQueue.status == "done", YouTubeIngestQueue.done_at >= semana)
                .order_by(corpus_ritmo.ORDEN_NIVEL, YouTubeIngestQueue.done_at.desc()).all())
    pendientes = (db.query(YouTubeIngestQueue)
                  .filter(YouTubeIngestQueue.status == "detected")
                  .order_by(corpus_ritmo.ORDEN_NIVEL, YouTubeIngestQueue.created_at.asc()).all())
    por_kind = dict(db.execute(
        select(InterpretationSource.kind, func.count(InterpretationSource.id))
        .where(InterpretationSource.fetched_at >= ahora - timedelta(days=DIAS_SEQUIA))
        .group_by(InterpretationSource.kind)).all())
    return {
        "ahora": ahora,
        "entraron": entraron,
        "bajaron": [r for r in entraron if any("baja de A" in m for m in (r.motivos or []))],
        "pendientes": pendientes,
        "esperan_mucho": (db.query(YouTubeIngestQueue)
                          .filter(YouTubeIngestQueue.status == "detected",
                                  YouTubeIngestQueue.created_at
                                  <= ahora - timedelta(days=ESPERA_LARGA_DIAS)).all()),
        "nuevas_por_kind": {k: int(n) for k, n in por_kind.items()},
        "ritmo": corpus_ritmo.resumen(db, ahora),
    }


def sequia(data: dict) -> bool:
    return sum(data["nuevas_por_kind"].values()) == 0


def _signature(data: dict) -> str:
    partes = ["e:" + ",".join(str(r.id) for r in sorted(data["entraron"], key=lambda r: r.id)),
              "p:" + ",".join(str(r.id) for r in sorted(data["pendientes"], key=lambda r: r.id)),
              f"s:{int(sequia(data))}"]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()[:64]


def _should_send(db, data: dict, firma: str) -> tuple[bool, str]:
    if not (data["entraron"] or data["pendientes"] or sequia(data)):
        return False, "ni entró nada ni hay nada pendiente"
    last = db.execute(select(NotificationDigest).where(NotificationDigest.kind == _KIND)
                      .order_by(NotificationDigest.sent_at.desc()).limit(1)).scalar_one_or_none()
    if last is None:
        return True, "primer correo"
    if last.signature != firma:
        return True, "hay novedades"
    enviado = last.sent_at if last.sent_at.tzinfo else last.sent_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - enviado >= timedelta(days=REMINDER_DAYS):
        return True, "recordatorio"
    return False, "lo mismo que el último correo"


def _motivo(r: YouTubeIngestQueue) -> str:
    """El último motivo cuenta lo que pasó al final (el juez va después del título)."""
    ms = r.motivos or []
    return html.escape(" · ".join(ms[-2:]) if ms else "")


def _build_html(data: dict, site: str) -> str:
    from app.services.auth import create_corpus_retire_token, create_youtube_ingest_token

    st = "font-family:'Courier New',monospace;font-size:11px;letter-spacing:2px;color:#a83a3a"
    p = ["<div style=\"font-family:Georgia,serif;max-width:680px\">",
         "<h2>Entre Interiores · el corpus esta semana</h2>"]
    r = data["ritmo"]
    p.append(f"<p>Han entrado <b>{r['hechos_semana']}</b> fuentes de vídeo en 7 días "
             f"(tope {r['max_semana']}). Whisper este mes: <b>{r['gasto_mes_usd']:.2f} $</b> de "
             f"{r['presupuesto_mes_usd']:.0f} $ ({r['minutos_whisper_mes']} min).</p>")
    if sequia(data):
        p.append(f"<p style='color:#a83a3a'><b>⚠️ Sequía:</b> en {DIAS_SEQUIA} días no ha entrado "
                 "ni cambiado ninguna fuente del corpus. Mira el log de <code>detect_uploads</code> "
                 "y el daemon de la Mac.</p>")
    elif data["nuevas_por_kind"]:
        partes = ", ".join(f"{k} {n}" for k, n in sorted(data["nuevas_por_kind"].items()))
        p.append(f"<p style='color:#666;font-size:13px'>Fuentes nuevas o cambiadas en "
                 f"{DIAS_SEQUIA} días: {html.escape(partes)}.</p>")

    if data["entraron"]:
        p.append(f"<h3>Entró en los últimos {DIAS_SEMANA} días ({len(data['entraron'])})</h3><ul>")
        for q in data["entraron"][:_MAX_FILAS]:
            url = f"{site}/api/public/corpus-retire?token={create_corpus_retire_token(q.id)}"
            p.append(f"<li><a href='{q.url}'>{html.escape(q.title or q.video_id)}</a> "
                     f"<span style='color:#888'>· {q.nivel or '—'} · {q.kind} · {q.via or '—'}</span>"
                     f" <a href='{url}' style=\"{st}\">retirar</a>"
                     f"<br><span style='color:#888;font-size:12px'>{_motivo(q)}</span></li>")
        p.append("</ul>")
    if data["bajaron"]:
        p.append(f"<p style='color:#666;font-size:13px'>De esos, {len(data['bajaron'])} bajaron de "
                 "A a fondo porque el juez de la transcripción no vio hablar a quien decía el "
                 "título.</p>")

    if data["pendientes"]:
        p.append(f"<h3>Esperan tu decisión ({len(data['pendientes'])})</h3><ul>")
        mucho = {q.id for q in data["esperan_mucho"]}
        for q in data["pendientes"][:_MAX_FILAS]:
            url = f"{site}/api/public/youtube-ingest?token={create_youtube_ingest_token([q.id])}"
            aviso = (f" <b style='color:#a83a3a'>(más de {ESPERA_LARGA_DIAS} días)</b>"
                     if q.id in mucho else "")
            p.append(f"<li><a href='{q.url}'>{html.escape(q.title or q.video_id)}</a> "
                     f"<span style='color:#888'>· {q.nivel or '—'} · {html.escape(q.channel or '')}"
                     f"</span>{aviso} <a href='{url}' style=\"{st}\">aprobar</a>"
                     f"<br><span style='color:#888;font-size:12px'>{_motivo(q)}</span></li>")
        p.append("</ul>")
    p.append(f"<p><a href='{site}/biblioteca/admin/corpus'>→ La cola en el panel</a></p></div>")
    return "\n".join(p)


def main() -> None:
    ap = argparse.ArgumentParser(description="Correo semanal del corpus.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="manda aunque no haya novedades")
    args = ap.parse_args()

    settings = get_settings()
    to = settings.admin_email
    if not to:
        logger.warning("Sin ADMIN_EMAIL configurado; no se envía.")
        return
    db = SessionLocal()
    try:
        data = _gather(db)
        firma = _signature(data)
        enviar, motivo = _should_send(db, data, firma)
        logger.info("entraron %d · pendientes %d · sequía %s · %s", len(data["entraron"]),
                    len(data["pendientes"]), sequia(data), motivo)
        if not enviar and not args.force:
            return
        asunto = (f"[Entre Interiores] ⚠️ el corpus lleva {DIAS_SEQUIA} días sin crecer"
                  if sequia(data) else
                  f"[Entre Interiores] Corpus: {len(data['entraron'])} entraron · "
                  f"{len(data['pendientes'])} por decidir")
        cuerpo = _build_html(data, settings.site_url.rstrip("/"))
        if args.dry_run:
            logger.info("(dry-run) enviaría a %s: %s\n%s", to, asunto, cuerpo[:1500])
            return
        from app.services.email import send_email

        mid = send_email(to, asunto, cuerpo)
        db.add(NotificationDigest(kind=_KIND, signature=firma, sent_at=datetime.now(UTC)))
        db.commit()
        logger.info("Correo del corpus enviado a %s (id=%s)", to, mid)
    finally:
        db.close()


if __name__ == "__main__":
    main()
