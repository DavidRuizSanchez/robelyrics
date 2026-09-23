"""Propone clips solos: elige el vídeo, elige el tramo y los encola.

Los CONCIERTOS van primero, que es de lo que se quieren los clips: un estribillo
con el público cantando, Robe hablando desde el escenario, un solo. Las
entrevistas quedan detrás, como respaldo cuando no hay material de directo, y
con la guarda de que hable el entrevistado y no quien le entrevista.

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


def _titulo_post(asset, candidato=None) -> str:
    """De qué va el post, dicho con datos duros.

    En un directo eso es EL MOMENTO más dónde y cuándo pasó: «El estribillo de
    "Standby" — Barcelona, 08-10-2022». Nada sale de la transcripción, que en un
    concierto está garbleada: el nombre de la canción viene de casar con la
    letra de la BD, y la fecha y el sitio, del catálogo.

    Sin fecha ni lugar se dice solo el momento (decisión de David): antes un
    hueco que un dato inventado.
    """
    es_directo = getattr(asset, "kind", "") == "live_fan"
    if candidato is not None and es_directo and getattr(candidato, "cancion", None):
        etiqueta = {
            "estribillo": "El estribillo de",
            "arranque": "Arranca",
            "solo": "El solo de",
            "canto": "En directo,",
        }.get(candidato.tipo, "En directo,")
        base = f'{etiqueta} «{candidato.cancion}»'
    elif candidato is not None and es_directo and candidato.tipo == "habla":
        # Solo en un directo se habla DESDE EL ESCENARIO. En una entrevista,
        # «habla» es el tipo por defecto del candidato y decir eso sería mentir
        # sobre dónde se grabó.
        base = "Robe, desde el escenario"
    else:
        base = (asset.title or "").strip()
        base = _RUIDO.sub("", base).strip(" ·-—|")
        if not base:
            base = "En directo"
        if asset.channel_title and asset.channel_title.lower() not in base.lower():
            base = f"{base} ({asset.channel_title})"

    donde_cuando = _cuando_y_donde(asset)
    if donde_cuando and candidato is not None and candidato.cancion:
        base = f"{base} — {donde_cuando}"
    # El título del POST es texto nuestro, así que le aplica la regla dura del
    # nombre. El título original del vídeo se queda intacto donde toca —en
    # `video_assets` y en la procedencia del clip—: eso es una cita, no se
    # reescribe.
    from app.services.text_sanitizer import enforce_name_policy

    return (enforce_name_policy(base) or base)[:300]


def _cuando_y_donde(asset) -> str:
    """«Barcelona, 08-10-2022», o "" si no consta. Nunca se rellena a ojo."""
    partes = []
    if asset.event_place:
        partes.append(asset.event_place)
    if asset.event_date:
        partes.append(asset.event_date.strftime("%d-%m-%Y"))
    elif asset.title:
        from app.services.instagram import concierto_meta as cm

        ev = cm.extraer(asset.title, "")
        if ev.anio:
            partes.append(str(ev.anio))
    return ", ".join(partes)


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
    ap.add_argument("--solo-directos", action="store_true",
                    help="no completa con entrevistas aunque falte cupo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--forzar", action="store_true",
                    help="propone aunque la cola esté llena (para probar el "
                         "circuito; no publica nada igualmente)")
    args = ap.parse_args()

    with SessionLocal() as db:
        sitio = _hay_sitio(db)
        if args.forzar and sitio <= 0:
            # La propuesta no publica: espera un clic. Saltarse el freno solo
            # adelanta trabajo del daemon, no vuelca nada al feed.
            logger.info("Cola llena, pero se fuerza: la propuesta espera tu clic.")
            sitio = args.limit
        if sitio <= 0 and not args.dry_run:
            logger.info("La cola está llena (umbral %d): no se proponen clips.",
                        config.BACKLOG_THRESHOLD)
            return
        cupo = min(args.limit, sitio or args.limit)

        # Primero los conciertos, que es de lo que se quieren los clips. Las
        # entrevistas solo completan si el directo no da para el cupo.
        candidatos = clip_picker.elegir_directo(db, limite=cupo)
        logger.info("Momentos de directo: %d", len(candidatos))
        if len(candidatos) < cupo and not args.solo_directos:
            faltan = cupo - len(candidatos)
            de_entrevistas = clip_picker.elegir(db, tema=args.tema, limite=faltan)
            if de_entrevistas:
                logger.info("Se completan %d con entrevistas", len(de_entrevistas))
            candidatos += de_entrevistas
        if not candidatos:
            logger.info("Ningún tramo pasa el listón. No es una avería: sin "
                        "material bueno, no hay clip.")
            return

        for c in candidatos:
            # El finalista de una entrevista pasa por el juez: las señales
            # deterministas dejaron escapar al locutor de la SER una vez.
            if c.asset.kind != "live_fan":
                del_sujeto, motivo = clip_picker.habla_el_protagonista(c.texto)
                if not del_sujeto:
                    logger.info("Descartado (%s): %s", motivo, c.resumen())
                    continue
            sensible = video_clips.canal_sensible(c.asset.channel_title or "")
            logger.info("Candidato: %s", c.resumen())
            logger.info("   título: %s", _titulo_post(c.asset, c))
            logger.info("   texto:  %s…", c.texto[:120])
            if sensible:
                logger.info("   ojo: canal de medio profesional («%s»)", sensible)
            if args.dry_run:
                continue

            clip = video_clips.solicitar(
                db, c.asset.url, c.start_s, c.end_s,
                subtitle=_titulo_post(c.asset, c),
                requested_by="auto",
                estado_item="proposed",
                needs_human=True,
            )
            item = db.get(InstagramQueueItem, clip.queue_item_id)
            if item is not None:
                # Por qué se eligió: viaja al correo y al panel. Sin esto, la
                # elección sería una caja negra y no se podría calibrar.
                partes = [f"Tramo {c.start_s:.0f}-{c.end_s:.0f}s de «{c.asset.title}»"]
                if c.tipo:
                    partes.append(f"Momento: {c.tipo}")
                if c.cancion:
                    partes.append(f"Canción: {c.cancion}")
                if c.verso:
                    # El verso de la BD, no lo que transcribió Whisper.
                    partes.append(f"Verso (de nuestra letra): {c.verso}")
                donde = _cuando_y_donde(c.asset)
                if donde:
                    partes.append(f"Concierto: {donde} (fuente: {c.asset.event_source or 'catálogo'})")
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
