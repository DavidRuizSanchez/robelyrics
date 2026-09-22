"""Propone clips de vídeo solos: elige el vídeo, elige el tramo y los encola.

Era lo único del camino de clips que seguía siendo manual. Todo lo demás ya
funcionaba: `video_clips.solicitar` crea el clip y su publicación, el daemon de
la Mac lo baja y lo monta en 9:16 con la atribución quemada, y `retire` lo
retira en un paso.

Lo que NO hace esto: publicar. Cada propuesta nace en `proposed`, que está
fuera del goteo (`next_pending` solo mira `pending`/`prepared`), y espera el
clic de una persona desde el correo que manda `notify_clips` con el vídeo YA
MONTADO. Es lo que pidió David: validar sobre el clip creado, no sobre una idea.

El título del post sale de la PROCEDENCIA (el vídeo y su canal), nunca de
resumir el tramo: lo que dice la transcripción sirve para elegirlo, no para
afirmarlo — las automáticas traen erratas y Whisper escribe «Robben y Niesta».

Uso:
    python -m scripts.instagram.propose_clips --dry-run
    python -m scripts.instagram.propose_clips --limit 2
"""
from __future__ import annotations

import argparse
import logging
import re

from sqlalchemy import select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import clip_picker, config, video_clips

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("clips")

# Pocos y espaciados: la cola es compartida y pasar de `BACKLOG_THRESHOLD`
# dispara el modo atasco, que acelera el goteo de TODO lo demás.
POR_PASADA = 2
# Los títulos de YouTube vienen con ruido de canal («| LA RESISTENCIA #LaRe»).
_RUIDO = re.compile(r"\s*[|#\-–—]\s*[^|#]{0,40}$")


def _titulo_post(asset) -> str:
    """De qué va el post, dicho con datos duros: qué vídeo y de quién.

    No resume el tramo a propósito. Quien aprueba ve el clip montado y puede
    cambiarlo desde el panel si quiere afinar.
    """
    base = (asset.title or "").strip()
    base = _RUIDO.sub("", base).strip(" ·-—|")
    if not base:
        base = "Entrevista a Robe"
    if asset.channel_title and asset.channel_title.lower() not in base.lower():
        base = f"{base} ({asset.channel_title})"
    # El título del POST es texto nuestro, así que le aplica la regla dura del
    # nombre. El título original del vídeo se queda intacto donde toca —en
    # `video_assets` y en la procedencia del clip—: eso es una cita, no se
    # reescribe.
    from app.services.text_sanitizer import enforce_name_policy

    return (enforce_name_policy(base) or base)[:300]


def _hay_sitio(db) -> int:
    """Cuántas propuestas caben sin volcar la cola."""
    vivos = db.execute(
        select(InstagramQueueItem).where(
            InstagramQueueItem.status.in_(("proposed", "pending", "prepared"))
        )
    ).scalars().all()
    return max(0, config.BACKLOG_THRESHOLD - len(vivos))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=POR_PASADA)
    ap.add_argument("--tema", default="", help="sesga la elección hacia un tema")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        sitio = _hay_sitio(db)
        if sitio <= 0 and not args.dry_run:
            logger.info("La cola está llena (umbral %d): no se proponen clips.",
                        config.BACKLOG_THRESHOLD)
            return
        cupo = min(args.limit, sitio or args.limit)

        candidatos = clip_picker.elegir(db, tema=args.tema, limite=cupo)
        if not candidatos:
            logger.info("Ningún tramo pasa el listón. No es una avería: sin "
                        "material bueno, no hay clip.")
            return

        for c in candidatos:
            sensible = video_clips.canal_sensible(c.asset.channel_title or "")
            logger.info("Candidato: %s", c.resumen())
            logger.info("   título: %s", _titulo_post(c.asset))
            logger.info("   texto:  %s…", c.texto[:120])
            if sensible:
                logger.info("   ojo: canal de medio profesional («%s»)", sensible)
            if args.dry_run:
                continue

            clip = video_clips.solicitar(
                db, c.asset.url, c.start_s, c.end_s,
                subtitle=_titulo_post(c.asset),
                requested_by="auto",
                estado_item="proposed",
                needs_human=True,
            )
            item = db.get(InstagramQueueItem, clip.queue_item_id)
            if item is not None:
                # Por qué se eligió: viaja al correo y al panel. Sin esto, la
                # elección sería una caja negra y no se podría calibrar.
                partes = [f"Tramo {c.start_s:.0f}-{c.end_s:.0f}s de «{c.asset.title}»"]
                if c.asset.channel_title:
                    partes.append(f"Canal: {c.asset.channel_title}")
                partes.append(f"Corte: {c.frontera}")
                if c.motivos:
                    partes.append("Motivos: " + "; ".join(c.motivos))
                if sensible:
                    partes.append(f"AVISO: medio profesional («{sensible}»)")
                partes.append(f"Transcripción del tramo: {c.texto[:600]}")
                item.summary = "\n".join(partes)
                db.commit()
            logger.info("   → clip #%s, post #%s (esperando tu visto bueno)",
                        clip.id, clip.queue_item_id)

        if args.dry_run:
            logger.info("[dry-run] no se ha encolado nada")


if __name__ == "__main__":
    main()
