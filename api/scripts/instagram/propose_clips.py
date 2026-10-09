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
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import clip_picker, config, video_clips

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("clips")

# Dos por pasada y a diario: sale 1 vídeo al día y de cada dos propuestas se
# descarta alguna (a 09-10-2026: 4 publicados, 6 retirados). El freno es
# `VIDEO_BUFFER`, no el atasco de los carruseles: el vídeo va por su carril.
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

    # Dónde y cuándo va en CUALQUIER momento de directo, no solo en los que
    # tienen canción: «Robe, desde el escenario» sin decir de qué concierto es
    # deja fuera justo el dato que se buscaba.
    donde_cuando = _cuando_y_donde(asset)
    if donde_cuando and es_directo:
        base = f"{base} — {donde_cuando}"
    # El título del POST es texto nuestro, así que le aplica la regla dura del
    # nombre. El título original del vídeo se queda intacto donde toca —en
    # `video_assets` y en la procedencia del clip—: eso es una cita, no se
    # reescribe.
    from app.services.text_sanitizer import enforce_name_policy

    return (enforce_name_policy(base) or base)[:300]


def _rotulo_del_clip(candidato) -> str:
    """El texto que se QUEMA en el vídeo, que no es el título del post.

    El título es descriptivo y largo, para el panel y el caption; el rótulo son
    dos líneas cortas, porque en el vídeo caben unos 32 caracteres por línea.
    """
    from app.services.instagram import rotulo

    asset = candidato.asset
    cuando = None
    if asset.event_date:
        # La fecha larga («9 de octubre de 1999») solo donde ocupa línea propia,
        # que es el clip de Robe hablando. En los demás la línea ya lleva la
        # canción y el sitio, así que basta el año o se encoge tanto que no se
        # lee: el hueco son 1044 px medidos, no una estimación.
        cuando = (
            rotulo.fecha_larga(asset.event_date)
            if candidato.tipo == "habla"
            else str(asset.event_date.year)
        )
    elif asset.title:
        from app.services.instagram import concierto_meta as cm

        ev = cm.extraer(asset.title, "")
        cuando = str(ev.anio) if ev.anio else None

    return rotulo.componer(
        tipo=candidato.tipo,
        cancion=candidato.cancion,
        verso=candidato.verso,
        lugar=asset.event_place,
        cuando=cuando,
        # La clave del clip: el mismo tramo da siempre el mismo rótulo.
        clave=f"{asset.youtube_id}:{int(candidato.start_s)}",
    )


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


def _proponer_canciones(db, cupo: int, dry_run: bool) -> int:
    """Clips de UNA canción, cortados en su estribillo (09-10-2026). Van primero.

    Criterio de David: un clip es una canción y su estribillo, y el texto es el
    de esa canción. El vídeo ya dice qué canción es (`live_song`, catalogado por
    `buscar_canciones_directo`), así que aquí no se transcribe nada: el tramo
    nace por localizar y el daemon lo fija escuchando el audio. Si no oye el
    estribillo de esa canción, no hay clip (y no llega al correo).

    Una canción por propuesta y nunca una que ya tenga clip vivo o publicado.
    """
    from datetime import timedelta

    from app.db.models import Song, VideoAsset, VideoClip
    from app.services.instagram import rotulo
    from app.services.instagram.robe_quote import _clean_song_title, _estribillo
    from app.services.versiones import version_original

    hace = datetime.now(UTC) - timedelta(days=120)
    usadas = {sid for (sid,) in db.execute(
        select(VideoClip.song_id).where(
            VideoClip.song_id.is_not(None),
            (VideoClip.status.in_(("requested", "downloading", "ready", "published")))
            | (VideoClip.created_at >= hace),
        )).all()}
    videos_fallidos = {v for (v,) in db.execute(
        select(VideoClip.video_id).where(VideoClip.status == "failed")).all()}
    assets = db.execute(
        select(VideoAsset).where(VideoAsset.kind == "live_song",
                                 VideoAsset.vetado.is_(False),
                                 VideoAsset.song_id.is_not(None))
        .order_by(VideoAsset.event_date.is_(None), VideoAsset.id)
    ).scalars().all()

    hechas = 0
    for asset in assets:
        if hechas >= cupo:
            break
        if asset.song_id in usadas or asset.youtube_id in videos_fallidos:
            continue
        song = version_original(db, db.get(Song, asset.song_id))
        letra = [(ln.text or "").strip() for ln in song.lines if (ln.text or "").strip()]
        i = _estribillo(letra)
        if i is None:
            continue   # sin estribillo identificado en la letra no hay qué buscar
        # Sin la coletilla con la que el catálogo distingue los discos gemelos:
        # «Emparedado (Rock Transgresivo)» → «Emparedado».
        from app.services.instagram.publisher import _sin_desambiguador

        cancion = _sin_desambiguador(_clean_song_title(song.title),
                                     song.album.title if song.album else "")
        donde = _cuando_y_donde(asset)
        titulo = f"El estribillo de «{cancion}»" + (f" — {donde}" if donde else "")
        cuando = str(asset.event_date.year) if asset.event_date else None
        logger.info("Canción: %s · %s · %s", cancion, asset.youtube_id, asset.title)
        usadas.add(asset.song_id)
        hechas += 1
        if dry_run:
            continue
        clip = video_clips.solicitar(
            db, asset.url, 0.0, 30.0,   # provisional: lo fija el daemon al oírlo
            subtitle=titulo,
            overlay=rotulo.componer(tipo="estribillo", cancion=cancion, verso=letra[i],
                                    lugar=asset.event_place, cuando=cuando,
                                    clave=f"{asset.youtube_id}:estribillo"),
            requested_by="auto", estado_item="proposed", needs_human=True,
            song_id=song.id, buscar_estribillo=True,
        )
        item = db.get(InstagramQueueItem, clip.queue_item_id)
        if item is not None:
            partes = [f"Vídeo de una canción: «{asset.title}»",
                      "Momento: estribillo (se localiza escuchando el audio)",
                      f"Canción: {song.title}",
                      f"Verso (de nuestra letra): {letra[i]}"]
            if donde:
                partes.append(f"Concierto: {donde} (fuente: {asset.event_source or 'título'})")
            if asset.channel_title:
                partes.append(f"Canal: {asset.channel_title}")
            item.summary = "\n".join(partes)
            db.commit()
    return hechas


def _hay_sitio(db) -> int:
    """Cuántas propuestas caben. Los clips van por su carril (1 al día, encima
    del goteo), así que el tope es de VÍDEO —`VIDEO_BUFFER`, una semana— y no
    el umbral de atasco de los carruseles, que ya no les afecta."""
    vivos = db.execute(
        select(InstagramQueueItem).where(
            InstagramQueueItem.status.in_(("proposed", "pending", "prepared")),
            InstagramQueueItem.media_type.in_(config.VIDEO_MEDIA_TYPES),
        )
    ).scalars().all()
    return max(0, config.VIDEO_BUFFER - len(vivos))


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
            logger.info("Ya esperan %d vídeos (tope %d): no se proponen más.",
                        config.VIDEO_BUFFER, config.VIDEO_BUFFER)
            return
        cupo = min(args.limit, sitio or args.limit)

        # Primero, directos de UNA canción cortados en su estribillo.
        cupo -= _proponer_canciones(db, cupo, args.dry_run)
        if cupo <= 0:
            return

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
                overlay=_rotulo_del_clip(c),
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
