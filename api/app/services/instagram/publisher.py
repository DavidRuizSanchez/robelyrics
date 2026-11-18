"""Orquestador de publicación en Instagram.

prepare:  tema → comentario editorial + verso de Robe + imagen → caption +
          fichero de imagen (sin publicar todavía).
publish:  sube la imagen a Cloudinary → publica vía Graph API → registra el
          resultado en `instagram_queue`.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    InstagramQueueItem,
    InstagramQueueMedia,
    Line,
    NewsItem,
    Person,
    Post,
    Song,
    VideoClip,
)
from app.services.instagram import material as material_ig
from app.services.instagram import (
    album_cover,
    captions,
    carousel,
    cloudinary_upload,
    community,
    config,
    editorial,
    errors,
    graph_api,
    imaging,
    photo_finder,
    robe_quote,
    tone,
    video,
)
from app.services import news_entities
from app.services.instagram import gate_final, identity_photo, newsroom
from app.services.instagram.evergreen import EVERGREEN_TYPES

logger = logging.getLogger(__name__)

BLOG_BASE_URL = f"{config.SITE_URL}/blog"
ROBE_PERSON_SLUG = "robe-iniesta"


class SinMaterial(RuntimeError):
    """No hay artículo que leer, así que no hay post: esto SÍ es un no definitivo.

    Distinta de `MaterialPendiente`, que significa «espera un poco». Aquí no se
    espera nada: el medio bloquea la descarga, o hay paywall, o el enlace de
    Google News no se resuelve. Escribir igualmente significa escribir con el
    titular, que es exactamente como se publicó un homónimo famoso por el sujeto
    real de la noticia y una afinidad que ninguna fuente decía.

    `topics.select` ya filtra por esto, pero el alta MANUAL desde el panel no
    pasa por ahí: sin esta guarda, seguiría siendo un bypass completo.
    """


class MaterialPendiente(RuntimeError):
    """El material aún no está, pero viene en camino: no es un fallo.

    Un clip lo baja el daemon de la Mac y tarda unos minutos. Si el goteo llega
    al post en ese hueco, el post NO está roto — solo hay que esperar. Tratarlo
    como fallo lo dejaba muerto para siempre por haber llegado nueve minutos
    antes que su vídeo.
    """


class TextoRetenido(RuntimeError):
    """El texto no se puede publicar y no hay respaldo honesto: lo mira una persona.

    No es un fallo de publicación. No se marca `failed` a propósito: el
    cortacircuitos (`publicacion_bloqueada`) cuenta los `failed` recientes de
    items distintos como señal de que Meta nos bloquea, y tres textos retenidos
    seguidos pararían la cola entera acusando a Meta de algo que no ha hecho.
    """


def _catalogo_del_clip(
    db: Session, clip: VideoClip, item: InstagramQueueItem
) -> tuple[set[str], set[str]]:
    """(títulos que el texto PUEDE citar, todos los títulos del catálogo).

    Lo que puede citar es la canción del clip y su disco. La canción sale de
    `video_clips.song_id` o, si no está, de la línea «Canción:» que dejó el
    selector en las notas internas.
    """
    song = db.get(Song, clip.song_id) if clip.song_id else None
    if song is None:
        for linea in (item.notas_internas or item.summary or "").splitlines():
            clave, _, valor = linea.partition(":")
            if clave.strip().lower() in ("canción", "cancion") and valor.strip():
                song = db.execute(
                    select(Song).where(func.lower(Song.title) == valor.strip().lower())
                ).scalars().first()
                break
    permitidos: set[str] = set()
    if song is not None:
        permitidos.add(song.title)
        if song.album is not None:
            permitidos.add(song.album.title)
    catalogo = set(db.execute(select(Song.title)).scalars().all())
    catalogo |= set(db.execute(select(Album.title)).scalars().all())
    return permitidos, catalogo


def _contexto_clip(db: Session, item: InstagramQueueItem) -> dict | None:
    """Lo que el gate necesita saber de un clip para comprobar que el texto habla
    de ESE clip: quién toca, qué canción es y de qué disco, y qué títulos tiene
    el catálogo (para saber si una cita entre comillas es un título)."""
    clip = db.execute(
        select(VideoClip).where(VideoClip.queue_item_id == item.id)
    ).scalars().first()
    if clip is None:
        return None
    permitidos, catalogo = _catalogo_del_clip(db, clip, item)
    return {
        "interprete": gate_final.interprete_del_video(
            clip.video_title or "", clip.channel_title or ""
        ),
        "titulos_permitidos": permitidos,
        "titulos_catalogo": catalogo,
        "rotulo": "\n".join(x for x in (clip.overlay, clip.subtitle) if x),
    }


def contexto_formacion(db: Session) -> tuple[list, list]:
    """Quién estuvo en cada grupo y cuándo (`band_memberships`) y el año de cada disco,
    en la forma que espera `gate_final.formacion_falsa`."""
    from app.db.models import Artist, BandMembership, Person

    pertenencias = []
    filas = db.execute(
        select(BandMembership, Person, Artist)
        .join(Person, BandMembership.person_id == Person.id)
        .join(Artist, BandMembership.artist_id == Artist.id)
    ).all()
    for m, persona, artista in filas:
        anios = gate_final.era_a_anios(m.era, actual=bool(m.is_current))
        if anios is None:
            continue
        nombres = []
        for n in (persona.full_name, persona.stage_name):
            plano = gate_final._plano(n or "").lower().strip()
            # Un alias corto («Mon», «Uge») casa con cualquier cosa: solo nombres de
            # dos palabras o de cuatro letras o más.
            if plano and (" " in plano or len(plano) >= 4) and plano not in nombres:
                nombres.append(plano)
        if nombres:
            pertenencias.append(gate_final.Pertenencia(
                tuple(nombres), artista.slug, anios[0], anios[1]))
    invitados = _invitados_por_disco(db)
    discos = [
        gate_final.Disco(gate_final._plano(a.title).lower(), art.slug, a.year,
                         invitados.get((art.slug, a.slug), frozenset()))
        for a, art in db.execute(select(Album, Artist).join(Artist, Album.artist_id == Artist.id)).all()
        if a.year
    ]
    return pertenencias, discos


def _invitados_por_disco(db: Session) -> dict[tuple[str, str], frozenset]:
    """(artista, disco) → nombres planos de quien tocó sin ser miembro, de
    `data/formacion_invitados.yaml` (cada entrada lleva su fuente)."""
    from pathlib import Path

    import yaml

    from app.db.models import Person

    for ruta in (Path("/app/data/formacion_invitados.yaml"),
                 Path(__file__).resolve().parents[4] / "data" / "formacion_invitados.yaml"):
        if ruta.exists():
            datos = yaml.safe_load(ruta.read_text()) or {}
            break
    else:
        return {}
    out: dict[tuple[str, str], frozenset] = {}
    for e in datos.get("invitados") or []:
        nombres = set()
        for slug in e.get("personas") or []:
            p = db.execute(select(Person).where(Person.slug == slug)).scalars().first()
            for n in ((p.full_name, p.stage_name) if p else ()):
                if n:
                    nombres.add(gate_final._plano(n).lower().strip())
        out[(e["artista"], e["disco"])] = frozenset(nombres)
    return out


def revisar_gate(db: Session, item: InstagramQueueItem) -> gate_final.VeredictoGate:
    """El gate final sobre lo que ESTE item va a publicar.

    Falla CERRADO: si no se puede comprobar un clip (la BD no responde, falta el
    catálogo), el veredicto es «no», nunca «sin comprobar, adelante».
    """
    try:
        ctx = _contexto_clip(db, item) if item.content_type == "clip" else None
        formacion = contexto_formacion(db)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[gate] no se pudo leer el contexto de %s: %s", item.id, exc)
        return gate_final.VeredictoGate(
            bloqueos=[f"no se pudo comprobar contra el catálogo y la formación: {exc}"[:300]]
        )
    return gate_final.revisar(
        caption=item.caption or "",
        rotulo=(ctx or {}).get("rotulo", ""),
        clip=ctx,
        formacion=formacion,
    )


def _retener(db: Session, item: InstagramQueueItem, motivo: str) -> InstagramQueueItem:
    """Saca el item de la cola hasta que lo mire una persona. Ver `TextoRetenido`."""
    item.needs_human = True
    item.error = f"Retenido antes de publicar: {motivo}"[:2000]
    db.commit()
    logger.warning("[IG] item %s retenido: %s", item.id, motivo)
    return item


_MADRID = ZoneInfo("Europe/Madrid")
_CONTADOR = re.compile(r"Día (\d+) sin Robe")


def fecha_de_publicacion(item: InstagramQueueItem, hoy: date | None = None) -> date:
    """El día en que saldrá el post, en Madrid: el fijado, o hoy si va al goteo.

    `hoy` existe para que quien ya fijó el día (`_dia_de_salida`, los tests) no
    mezcle dos relojes: sin él, el test del contador solo pasaba el 09-11-2026.
    """
    if item.publish_at is not None:
        cuando = item.publish_at
        if cuando.tzinfo is None:
            cuando = cuando.replace(tzinfo=timezone.utc)
        return cuando.astimezone(_MADRID).date()
    if item.publish_on is not None:
        return item.publish_on
    return hoy or datetime.now(_MADRID).date()


def contador_desfasado(item: InstagramQueueItem, hoy: date | None = None) -> bool:
    """¿El «Día N sin Robe» del post no es el de HOY?

    El texto y las imágenes se preparan días (o meses) antes de salir, y el
    contador se quedaba con el número del día de preparar: 94 de 140 publicados
    en 60 días salieron con el día equivocado (medido el 09-11-2026).
    """
    m = _CONTADOR.search(item.caption or "")
    if not m:
        return False
    return int(m.group(1)) != config.dias_sin_robe(_dia_de_salida(item, hoy))


def _dia_de_salida(item: InstagramQueueItem, hoy: date | None = None) -> date:
    """Hoy, salvo que esté fijado para más adelante (un ensayo en seco de un post
    programado no tiene que rehacerlo para el día de hoy)."""
    hoy = hoy or datetime.now(_MADRID).date()
    return max(hoy, fecha_de_publicacion(item, hoy))


def _poner_al_dia_el_contador(db: Session, item: InstagramQueueItem) -> None:
    """Deja el contador con el número de hoy antes de publicar.

    En las imágenes nuestras el número va QUEMADO (cabecera y última tarjeta),
    así que se vacían y `publish` las vuelve a preparar, gate incluido. Lo que no
    se puede rehacer (vídeo, piezas subidas a mano, capturas) solo lleva el
    número en el caption, y ahí basta con cambiarlo.
    """
    hoy = config.dias_sin_robe(_dia_de_salida(item))
    if item.media_type in ("IMAGE", "CAROUSEL") and not item.media_locked:
        db.query(InstagramQueueMedia).filter(InstagramQueueMedia.item_id == item.id).delete()
        item.caption = None
        item.image_url = None
        item.image_path = None
        db.commit()
        db.refresh(item)
        logger.info("[IG] item %s: contador desfasado, se rehace entero", item.id)
        return
    item.caption = _CONTADOR.sub(f"Día {hoy} sin Robe", item.caption or "")
    db.commit()
    logger.info("[IG] item %s: contador del caption puesto al día (%s)", item.id, hoy)


def _topic_from_item(db: Session, item: InstagramQueueItem) -> dict:
    """Construye el dict de tema que consumen editorial / imaging / captions."""
    topic = {
        # El contador «Día N sin Robe» se calcula con el día en que SALE.
        "fecha_publicacion": fecha_de_publicacion(item),
        "title": item.title,
        "category": item.category or "Actualidad",
        # El `summary` de un clip nunca llega al redactor ni al caption: lo
        # interno vive en `notas_internas`, y si quedara algo en `summary` (un
        # item anterior a la migración) se trata como interno también.
        "summary": "" if item.content_type == "clip" else (item.summary or ""),
        "source": item.source_name or "",
        "url": item.source_url or "",
        # Semilla estable de la rotación de moldes del caption: re-preparar un
        # item no debe cambiarle el texto por sorpresa.
        "content_key": item.content_key or "",
    }
    if item.blog_post_id:
        post = db.get(Post, item.blog_post_id)
        if post is not None:
            topic["category"] = "Blog"
            topic["url"] = f"{BLOG_BASE_URL}/{post.slug}"
            topic["image_hint"] = post.hero_image_url or ""
            if not topic["summary"]:
                topic["summary"] = post.excerpt or ""
            # El artículo entero, en prosa, para quien necesite material de
            # verdad. Al carrusel solo le llegaba el `excerpt` —una frase— y
            # `carousel.plan` pide dos, así que un post de blog nunca podía ser
            # carrusel: se caía a foto única sin decir por qué.
            from app.services.instagram.carousel import prosa

            topic["caption_body"] = prosa(post.body_md or "")

    # El ARTÍCULO de la noticia. Se recupera aquí y no se arrastra desde
    # `topics.select` porque `prepare` se llama también al re-preparar desde el
    # panel, cuando de aquel tema ya no queda nada: el único hilo es
    # `news_item_id`. Sin esto, los temas se elegían CON material y luego se
    # descartaban por no tenerlo — y solo se ve corriendo el pipeline entero.
    if item.news_item_id:
        noticia = db.get(NewsItem, item.news_item_id)
        if noticia is not None:
            topic["material"] = noticia.body_text or ""
            topic["url_medio"] = noticia.body_url or noticia.url
            if not topic["url"]:
                topic["url"] = topic["url_medio"]
    return topic


def _sin_desambiguador(song: str, album: str) -> str:
    """«Emparedado (Rock Transgresivo)» → «Emparedado».

    Los dos discos gemelos («Rock transgresivo» y «Tú en tu casa, nosotros en la
    hoguera») comparten canciones, y en el catálogo se desambiguan poniendo el
    disco entre paréntesis. Eso es interno: en un caption el nombre de la canción
    es el de la canción, y el disco ya va aparte.

    Solo se recorta si el paréntesis coincide con el título del álbum — así no se
    toca ningún título que lleve paréntesis de verdad.
    """
    s, a = (song or "").strip(), (album or "").strip()
    if not s.endswith(")") or "(" not in s or not a:
        return s
    base, _, dentro = s.rpartition("(")
    if dentro.rstrip(")").strip().casefold() == a.casefold():
        return base.strip()
    return s


def _hero_es_arte(db: Session, item: InstagramQueueItem) -> bool:
    """¿El hero del post del blog es arte propio (IA)? Lo dice su `alt`, que
    `blog_hero` escribe así para el arte generado."""
    if not item.blog_post_id:
        return False
    post = db.get(Post, item.blog_post_id)
    return bool(post and (post.hero_image_alt or "").startswith("Ilustración editorial"))


def _cancion_de_item(db: Session, item: InstagramQueueItem) -> int | None:
    """La canción de la que va el post, si se SABE (nunca adivinada del texto).

    Un verso (`quote:line_<id>`) es de la canción de esa línea; un clip o una
    ficha de canción del blog, lo que diga `robe_quote.cancion_del_post`.
    """
    key = item.content_key or ""
    if key.startswith("quote:line_"):
        try:
            line = db.get(Line, int(key.rsplit("_", 1)[1]))
        except (IndexError, ValueError):
            line = None
        return line.song_id if line is not None else None
    sid, _ = robe_quote.cancion_del_post(db, item)
    return sid


def _corpus_context(db: Session, item: InstagramQueueItem) -> dict:
    """Datos ESTRUCTURADOS del corpus para rellenar los moldes del caption.

    El `summary` de un evergreen viene ya formateado («canción» · artista · disco
    (año)), y parsearlo sería frágil. Aquí se vuelve a la fuente: el
    `content_key` identifica la fila exacta de la que salió el candidato, así que
    se releen los campos de BD. Si algo no está, se omite la clave y el molde que
    la necesite queda descartado — nunca se rellena con un valor plausible.

    NOTA: no se expone autoría. Robe es el letrista de casi todo, pero no de todo
    («Ama, ama y ensancha el alma» es un poema de Manolo Chinato), y un molde que
    afirmara "esto lo escribió Robe" mentiría en esos casos.
    """
    key = item.content_key or ""
    ctx: dict = {}

    if key.startswith("quote:line_"):
        try:
            line_id = int(key.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return ctx
        row = db.execute(
            select(Song.title, Album.title, Album.year, Artist.name)
            .select_from(Line)
            .join(Song, Line.song_id == Song.id)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
            .where(Line.id == line_id)
        ).first()
        if row:
            ctx["song"], ctx["album"], ctx["year"], ctx["artist"] = row
            ctx["song"] = _sin_desambiguador(ctx["song"], ctx["album"])

    elif key.startswith("ephemeris:album_"):
        slug = key[len("ephemeris:album_"):].rsplit("_", 1)[0]
        row = db.execute(
            select(Album.title, Album.year, Artist.name)
            .join(Artist, Album.artist_id == Artist.id)
            .where(Album.slug == slug)
        ).first()
        if row:
            ctx["album"], ctx["year"], ctx["artist"] = row

    elif key.startswith("ephemeris:birth_"):
        slug = key[len("ephemeris:birth_"):].rsplit("_", 1)[0]
        person = db.execute(
            select(Person).where(Person.slug == slug)
        ).scalar_one_or_none()
        if person is not None:
            ctx["person"] = person.stage_name or person.full_name
            ctx["is_memorial"] = person.death_date is not None

    return ctx


def _clean_credit(raw: str) -> str:
    """Pasa una atribución en markdown (pensada para la web) a texto plano apto
    para el caption de Instagram: sin markdown, sin enlaces y sin raya larga."""
    txt = (raw or "").strip()
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)   # [texto](url) -> texto
    txt = txt.replace("*", "").replace("_", "")
    txt = re.sub(r"\s*[—–]\s*", " · ", txt)              # raya larga -> punto medio
    txt = re.sub(r"^\s*foto:\s*", "", txt, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", txt).strip(" ·")


def _apply_person_photo(
    db: Session, item: InstagramQueueItem, topic: dict
) -> None:
    """Para una efeméride de persona, usa la foto curada de su ficha en la web.

    El `content_key` de los cumpleaños/aniversarios natales es
    `ephemeris:birth_<slug>_<año>`. Si la persona tiene `image_url`, se reusa esa
    misma imagen (la que ya sale en /personas/<slug>): garantiza que la cara es
    la correcta (sin homónimos) y respeta su atribución CC.
    """
    key = item.content_key or ""
    prefix = "ephemeris:birth_"
    if key.startswith(prefix):
        slug = key[len(prefix):].rsplit("_", 1)[0]
    elif item.content_type == "robe_quote":
        # Una cita de Robe es de Robe: su foto acreditada de ficha no sugiere
        # ninguna identidad que no sea la suya. Antes estas salían con arte IA.
        slug = ROBE_PERSON_SLUG
    else:
        return
    if not slug:
        return
    person = db.execute(
        select(Person).where(Person.slug == slug)
    ).scalar_one_or_none()
    if person is None or not person.image_url:
        return
    url = person.image_url
    if url.startswith("/"):
        url = config.SITE_URL + url
    topic["image_hint"] = url
    topic["image_kind"] = "photo"
    topic["image_origin"] = "ficha"
    attribution = _clean_credit(person.image_attribution or "")
    if attribution:
        lic = (person.image_license or "").strip()
        if lic and lic.lower() not in attribution.lower():
            attribution += f" · {lic}"
        topic["image_credit"] = attribution
    logger.info("[IG] efeméride de %s → foto de ficha %s", slug, url[:60])



# Avisos que se ENSEÑAN en el panel pero no retienen el post. Desde el 09-11-2026
# `needs_human` saca el item de la cola (antes era solo una etiqueta), así que
# cualquier aviso retenía: una noticia ilustrada con arte propio se quedaba
# esperando un clic, y la decisión de David es que la IA, como último recurso,
# salga sin aprobación. Los demás avisos (un verso dudoso, una foto sin
# comprobar, un año sin verificar, la muerte de Robe) siguen pidiendo persona.
AVISOS_INFORMATIVOS = (
    "El texto se reescribió",
    "Sin foto acreditada de",
    "una slide repite",
    "Las slides no pasaron las guardas: el post va con el texto de siempre",
)


def es_aviso_informativo(aviso: str) -> bool:
    return any((aviso or "").startswith(p) for p in AVISOS_INFORMATIVOS)


def _guardar_evidencia(db, item, topic: dict, entidades: list) -> None:
    """Deja por escrito de dónde salió cada cosa de este post.

    Sin esto, el panel solo podía decir «imagen ✓», y con eso delante no había
    forma de cazar que la foto era de otra persona sin reconocer la cara. Es
    best-effort: si falla, el post sigue —pero se loguea, que un `except: pass`
    mudo es como muere una guarda sin que nadie se entere.
    """
    from app.db.models import InstagramPostEvidence

    try:
        fila = db.execute(
            select(InstagramPostEvidence).where(
                InstagramPostEvidence.item_id == item.id
            )
        ).scalar_one_or_none()
        if fila is None:
            fila = InstagramPostEvidence(item_id=item.id)
            db.add(fila)

        material = topic.get("material") or ""
        fila.material_url = topic.get("url_medio") or topic.get("url")
        fila.material_status = "ok" if material else "sin_material"
        fila.material_chars = len(material)

        fila.entities = [
            {
                "surface": e.mention.surface,
                "kind": e.mention.kind,
                "role": e.mention.role,
                "status": e.status,
                "label": e.label,
                "description": e.description,
                "qid": e.qid,
                "context": e.mention.context,
                "reason": e.reason,
                "candidates": e.candidates,
            }
            for e in entidades
        ]
        sujeto = news_entities.sujeto(entidades)
        if sujeto is not None:
            fila.subject_label = sujeto.label
            fila.subject_qid = sujeto.qid
            fila.subject_description = sujeto.description

        foto = topic.get("foto")
        if foto is not None:
            fila.photo_source = foto.source
            fila.photo_verdict = foto.verdict
            fila.photo_reason = foto.reason
            fila.photo_query = foto.query
            fila.photo_page_url = foto.page_url
            fila.photo_site = foto.site
            fila.photo_evidence = list(foto.evidence or [])
        elif topic.get("image_origin") == "portada":
            # Antes caía en el `else` y una portada se registraba como arte
            # propio: inflaba el recuento de IA del panel.
            fila.photo_source = "portada"
            fila.photo_verdict = "accredited"
            fila.photo_reason = "Portada oficial del disco del que va el post."
        else:
            fila.photo_source = identity_photo.ARTE_PROPIO
            fila.photo_verdict = "own_art"
            fila.photo_reason = "Sin foto acreditada: no afirma la identidad de nadie."

        fila.claims = topic.get("claims") or []
        fila.avisos = topic.get("avisos") or []
        item.needs_human = any(not es_aviso_informativo(a) for a in fila.avisos)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[evidencia] no se pudo guardar la del item %s: %s", item.id, exc)
        db.rollback()


def _redactar_con_corpus(db: Session, topic: dict, *, extra: str = "") -> None:
    """Escribe el comentario y las slides de un post de material propio.

    Evergreen y blog no pasaban por ningún redactor: su texto salía del corpus
    verificado y las slides eran un troceo del resumen. El texto de partida
    SIGUE siendo intocable (un verso es de quien lo escribió), pero lo que se
    cuenta alrededor ahora lo escribe alguien, con el corpus delante.

    Si no hay material, no se llama al modelo: el post sale exactamente como
    salía. La regla no era «no usar IA», era «no inventar».
    """
    if topic.get("content_type") == "clip":
        topic["texto_base"] = (topic.get("title") or "").strip()
    else:
        topic["texto_base"] = (
            topic.get("caption_body") or topic.get("summary") or topic.get("title") or ""
        ).strip()
    mat = material_ig.reunir(db, topic)
    if extra:
        # Material que no sale del corpus: los datos del clip de directo (qué
        # momento es, qué canción, de qué concierto). Va DELANTE porque es de lo
        # que trata el post.
        mat.prompt = f"{extra}\n\n----\n\n{mat.prompt}".strip("\n- ")
        mat.verificable = f"{extra}\n\n{mat.verificable}".strip()
    if not mat:
        logger.info(
            "[prepare] sin material de casa para «%s»: se deja el texto tal cual",
            (topic.get("title") or "")[:60],
        )
        return
    topic["material_corpus"] = mat.prompt
    # El material contra el que se ancla incluye el texto de partida: el verso o
    # la efeméride son un hecho del post tanto como lo que dice el corpus.
    material = f"{topic['texto_base']}\n\n{mat.prompt}"
    try:
        avisos = newsroom.escribir(db, topic, [], material=material, verificar_rel=False)
    except newsroom.TextoNoPublicable as exc:
        if topic.get("content_type") == "clip":
            # Un clip NO tiene «texto de siempre»: su texto de partida eran las
            # notas del selector, y publicarlas es justo lo que pasó en el #487.
            raise TextoRetenido(f"el texto del clip no pasa las guardas: {exc}") from exc
        # Un evergreen no se tira por esto: su texto ya era publicable antes de
        # que existiera el redactor. Se queda sin slides escritas y sigue.
        logger.warning("[prepare] redacción descartada: %s", exc)
        topic["caption_body"] = topic["texto_base"]
        topic.pop("slides", None)
        topic.pop("cierre", None)
        # Y la pregunta del intento descartado, que si no se queda puesta en el
        # topic y acaba en el caption: sería texto que NO pasó el gate saliendo
        # publicado, justo lo que se está arreglando. Sin ella, `captions` cae a
        # la plantilla anclada, que es lo que había antes de todo esto.
        topic.pop("pregunta", None)
        topic.setdefault("avisos", []).append(
            "Las slides no pasaron las guardas: el post va con el texto de siempre."
        )
        return
    topic["avisos"] = list(topic.get("avisos") or []) + avisos


def _contexto_de_directo(db: Session, item: InstagramQueueItem, topic: dict) -> None:
    """Qué se ve en el clip, para que el texto hable de ESO.

    El momento y la canción los dejó escritos `propose_clips` en las
    `notas_internas` del item (es lo que también se enseña en el correo de aprobación). La fecha
    y el sitio salen del catálogo de conciertos, nunca de la transcripción: la
    de un directo está garbleada y solo sirve para ELEGIR el tramo.

    Si no hay nada de esto —un clip dado de alta a mano, por ejemplo— no se
    inventa: el post sale como salía.
    """
    resumen = (item.notas_internas or item.summary or "")
    datos: dict[str, str] = {}
    for linea in resumen.splitlines():
        if ":" in linea:
            clave, valor = linea.split(":", 1)
            datos[clave.strip().lower()] = valor.strip()

    cancion = datos.get("canción") or datos.get("cancion")
    if cancion:
        fila = db.execute(
            select(Song.title, Album.title, Album.year, Artist.name)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
            .where(func.lower(Song.title) == cancion.lower())
        ).first()
        if fila:
            topic["corpus"] = {"song": fila[0], "album": fila[1],
                               "year": fila[2], "artist": fila[3]}

    partes = []
    clip = db.execute(
        select(VideoClip).where(VideoClip.queue_item_id == item.id)
    ).scalars().first()
    interprete = (
        gate_final.interprete_del_video(clip.video_title or "", clip.channel_title or "")
        if clip else None
    )
    if interprete:
        # Quién toca lo dice el vídeo, no el autor de la canción: el #504 decía
        # «Extremoduro la tocó en Vigo» en un concierto de Robe de 2024.
        partes.append(
            f"Quién toca en este concierto: {interprete} (lo dice el propio vídeo). "
            f"Atribuye el directo a {interprete} y a nadie más."
        )
    if datos.get("momento"):
        partes.append(f"Lo que se ve en el clip: {datos['momento']}"
                      + (f" de «{cancion}»" if cancion else ""))
    verso = datos.get("verso (de nuestra letra)")
    if verso:
        partes.append(f"El verso que suena, según NUESTRA letra: «{verso}»")
    if datos.get("concierto"):
        partes.append(f"El concierto: {datos['concierto']}")
    if partes:
        partes.append(
            "REGLA: lo que se afirme sale de estos datos y de la letra de la "
            "base de datos, NUNCA de la transcripción del directo, que está "
            "llena de erratas. Si aquí no consta la fecha o el sitio, NO se "
            "mencionan."
        )
        topic["material_directo"] = "\n".join(partes)


def prepare(db: Session, item: InstagramQueueItem) -> InstagramQueueItem:
    """Genera imagen y caption para un item de la cola (sin publicar)."""
    topic = _topic_from_item(db, item)
    is_blog = item.content_type == "blog" or topic.get("category") == "Blog"
    is_evergreen = item.content_type in EVERGREEN_TYPES

    # Contexto para los moldes del caption: de qué tipo es y qué datos reales del
    # corpus hay detrás. Sin esto, `captions` solo tendría texto ya formateado.
    topic["content_type"] = item.content_type
    topic["corpus"] = _corpus_context(db, item)

    # El tono (sobrio vs neutral) gobierna CTA, emoji y prompt editorial.
    topic["tone"] = tone.classify(
        topic.get("title", ""), topic.get("summary", "")
    )

    if is_evergreen:
        # Evergreen: el contenido (verso/efeméride/anécdota/cita) ya es final y
        # sale del corpus verificado. NO se reescribe con IA (anti-alucinación)
        # ni se busca foto de prensa. Imagen, por prioridad:
        #   1) Portada del disco si el texto lo menciona (versos, efeméride de
        #      disco): el arte del propio disco al que pertenece.
        #   2) Efeméride de una PERSONA (cumpleaños/aniversario natal): SU foto
        #      curada de la ficha de la web (misma imagen, sin homónimos).
        #   3) Si no, arte temático (IA) afín a la categoría.
        cover = album_cover.find(db, topic, song_id=_cancion_de_item(db, item))
        if cover:
            topic["image_hint"] = cover["url"]
            topic["image_kind"] = "cover"
            topic["image_origin"] = "portada"
        else:
            _apply_person_photo(db, item, topic)
        # El contenido se basta solo: sin verso ornamental (evita duplicarlo en
        # los posts de frase, donde el verso YA es el titular).
        topic["verse"] = {}
        # El texto del evergreen (el verso, la efeméride, la cita) es DEFINITIVO
        # y ajeno: no se reescribe. Lo que sí se escribe ahora es lo de
        # alrededor —el comentario y las slides—, y solo si hay material de casa
        # que lo respalde. Sin material, el post sale como salía: eso es lo que
        # protegía la regla de «en evergreen no se llama al LLM», y se mantiene.
        _redactar_con_corpus(db, topic)
    else:
        # El verso 🎵: SOLO si el post va de una canción concreta, y de ESA
        # canción (`robe_quote.cancion_del_post`). Se elige AQUÍ, antes de
        # escribir, para que las guardas lo vean (`newsroom.texto_publicado`):
        # hasta el 09-10-2026 se añadía después de ellas y nadie lo revisaba.
        sid, preferido = robe_quote.cancion_del_post(db, item)
        topic["verse"] = robe_quote.verso_de_cancion(db, sid, preferido) if sid else {}

        # Las noticias se reescriben con voz editorial propia (sin citar al
        # medio); los posts del blog ya traen su texto y su imagen destacada.
        if is_blog:
            # El cuerpo del post no se toca (lo escribió el motor profundo), pero
            # sus slides también las escribe alguien ahora.
            _redactar_con_corpus(db, topic)
            # Sin hero, o con un hero de arte propio, el post salía con IA aunque
            # su título nombrara un disco: medido el 09-11-2026, 6 de los 15
            # posts de blog del mes («La Gira 2002 de Yo, minoría absoluta»,
            # «Robando perchas del hotel (2012)»…). En IG una portada sí puede
            # repetirse, así que va por delante del arte.
            if not topic.get("image_hint") or _hero_es_arte(db, item):
                cover = album_cover.find(db, topic, song_id=_cancion_de_item(db, item))
                if cover:
                    topic["image_hint"] = cover["url"]
                    topic["image_kind"] = "cover"
                    topic["image_origin"] = "portada"
            if topic.get("image_hint") and not topic.get("image_origin"):
                topic["image_origin"] = "hero_blog"
        # SOLO las noticias AJENAS. Dos formas de equivocarse aquí, y las dos
        # han pasado:
        #
        #   - Un clip de vídeo no tiene «cuerpo del artículo» —su material es
        #     el propio vídeo— y con `not is_blog` a secas se le exigía
        #     igualmente: desde que existe la guarda de «sin material no hay
        #     post», CUALQUIER clip aprobado fallaba al prepararse. `product`
        #     no lo sufría de casualidad, porque está en EVERGREEN_TYPES.
        #   - Y al arreglarlo mirando solo el `content_type` se rompió el caso
        #     contrario: un post NUESTRO encolado como `news`. El material de
        #     esos está en la BD (`blog_post_id`), no en una descarga, así que
        #     pedirles un artículo ajeno es pedirles algo que nunca van a
        #     tener. Medido el 23-09-2026: 18 de los 20 items que vienen del
        #     blog están encolados con `content_type='news'`, y desde la
        #     guarda ninguno podía salir. `is_blog` ya lo sabe unas líneas más
        #     arriba —de ahí que sus slides sí se escriban—; lo que faltaba era
        #     que esta condición se enterara.
        if item.content_type == "news" and not is_blog:
            material = (topic.get("material") or "").strip()
            if not material:
                from app.services.article_extract import PASTE_HINT
                raise SinMaterial(
                    f"No hay cuerpo del artículo para «{topic.get('title', '')[:60]}»: "
                    f"sin material no se escribe. Si el medio lo bloquea, {PASTE_HINT}."
                )
            # Antes de escribir: saber de quién se habla. Lo que no se
            # identifica no se nombra (`newsroom`, regla dura).
            entidades = newsroom.resolver_entidades(db, topic)
            # Y qué sabemos NOSOTROS del tema. El artículo cuenta lo que ha
            # pasado; el corpus es lo que hace que el post sea de esta cuenta y
            # no del medio: la canción, la letra, lo que dijo Robe.
            mat = material_ig.reunir(db, topic, entidades=entidades)
            topic["material_corpus"] = mat.prompt
            # Anclarse vale con todo el material (una anotación citada es un
            # apoyo legítimo); AFIRMAR una relación nueva, solo con el artículo
            # y nuestras propias fichas.
            avisos = newsroom.escribir(
                db, topic, entidades,
                material=f"{material}\n\n{mat.verificable}".strip(),
                material_verificable=f"{material}\n\n{mat.verificable}".strip(),
            )
            topic["avisos"] = avisos
            # Fuente de imagen por prioridad:
            #   1) Portada del disco si el tema trata sobre uno de la discografía.
            #   2) Foto CC del protagonista real (Wikimedia/Openverse) por entidad.
            #   3) (en imaging) arte IA temático como último recurso.
            cover = album_cover.find(db, topic)
            if cover:
                topic["image_hint"] = cover["url"]
                topic["image_kind"] = "cover"
                topic["image_origin"] = "portada"
            else:
                # Créditos de las fotos recientes: para no repetir imagen.
                recent_credits = {
                    m.group(1).strip()
                    for c in db.execute(
                        select(InstagramQueueItem.caption)
                        .where(
                            InstagramQueueItem.caption.is_not(None),
                            InstagramQueueItem.id != item.id,
                        )
                        .order_by(InstagramQueueItem.id.desc())
                        .limit(12)
                    ).scalars().all()
                    if c and (m := re.search(r"📷\s*(.+)", c))
                }
                # La foto la busca la ENTIDAD resuelta, no una frase que el
                # modelo adivina del titular. `photo_finder.find` se queda para
                # el evergreen y el blog; aquí no se usa porque elegía uno de los
                # quince primeros de Google por hash, sin mirar nada.
                sujeto = news_entities.sujeto(entidades)
                foto = (
                    identity_photo.find_for_entity(
                        sujeto, topic, exclude=recent_credits
                    )
                    if sujeto is not None
                    else None
                )
                if foto:
                    topic["image_hint"] = foto.url
                    topic["image_hint_thumb"] = foto.thumb
                    topic["image_credit"] = foto.credit
                    topic["image_kind"] = "photo"
                    topic["image_origin"] = f"foto:{foto.source}"
                    topic["foto"] = foto
                    if foto.needs_human:
                        topic.setdefault("avisos", []).append(
                            "La foto no se ha podido comprobar con visión: revísala."
                        )
                elif sujeto is not None:
                    # Nada acreditado: arte propio. Se dice, porque una foto que
                    # no aparece se nota menos que una foto equivocada, y aun así
                    # conviene que alguien sepa por qué.
                    topic.setdefault("avisos", []).append(
                        f"Sin foto acreditada de «{sujeto.label or sujeto.mention.surface}»: "
                        f"va arte propio."
                    )


    # Formato: carrusel si el tema da para ello, foto única en cualquier otro
    # caso (que sigue siendo el camino por defecto). `carousel.plan` devuelve
    # None cuando no hay material verificado suficiente.
    if item.media_type == "PRODUCT":
        return _prepare_product(db, item, topic)

    if item.media_type in ("REELS", "CLIP"):
        # CLIP: fragmento de otro canal, con su sonido. Es lo que un verso
        # animado no puede dar (los reels propios van mudos a propósito).
        clip = db.execute(
            select(VideoClip).where(
                VideoClip.queue_item_id == item.id,
                VideoClip.status.in_(("ready", "published")),
            )
        ).scalars().first()

        if item.media_type == "CLIP" and not (clip and clip.url_cdn):
            # ¿Está el vídeo en camino o no hay ninguno? No es lo mismo: el
            # daemon de la Mac tarda sus minutos en bajarlo, y durante ese rato
            # el post no está roto, solo no está listo todavía.
            enCamino = db.execute(
                select(VideoClip).where(
                    VideoClip.queue_item_id == item.id,
                    VideoClip.status.in_(("requested", "downloading")),
                )
            ).scalars().first()
            if enCamino is not None:
                raise MaterialPendiente(
                    f"el clip #{enCamino.id} aún se está bajando "
                    f"({enCamino.status}); se reintentará solo"
                )
            raise RuntimeError(
                "este post es de formato «clip externo» pero no tiene ninguno "
                "enlazado. Pide el clip abajo, en «clips de vídeo», y pulsa "
                "«usar en un post»."
            )

        if clip and clip.url_cdn:
            _sync_media(db, item, [], [], kind="video")
            item.media.append(
                InstagramQueueMedia(
                    position=0, kind="video", role="clip",
                    url=clip.url_cdn,
                    cloudinary_public_id=clip.cloudinary_public_id,
                    duration_s=clip.duration_s,
                )
            )
            # El crédito del canal viaja también en el caption, no solo quemado
            # en el vídeo.
            topic["image_credit"] = clip.atribucion
            # Y de qué momento va el post. Sin esto el caption de un clip de
            # concierto hablaba del vídeo entero: «Robe en tal sitio», sin decir
            # que lo que se ve es el estribillo de una canción concreta.
            _contexto_de_directo(db, item, topic)
            # Y que el texto lo escriba alguien, con ese material delante. Antes
            # el caption de un clip salía solo de moldes, así que hablaba del
            # vídeo en general y nunca del momento que se ve.
            if topic.get("material_directo"):
                topic["texto_base"] = topic.get("title") or ""
                _redactar_con_corpus(db, topic, extra=topic["material_directo"])
            item.image_path = None      # el material vive en Cloudinary
            item.media_type = "CLIP"
            item.image_origin = "video"
            item.caption = captions.build(db, topic)
            item.status = "prepared"
            item.error = None
            db.commit()
            logger.info("[IG] item %s usará el clip #%s (%s)",
                        item.id, clip.id, clip.channel_title)
            return item

        # Sin clip asignado: verso animado propio.
        ruta = video.render_verse_reel(topic, slot=item.slot or 1)
        specs, paths, used_hero = [{"layout": "reel"}], [ruta], False
        _sync_media(db, item, paths, specs, kind="video")
        item.image_origin = "reel_propio"
        item.image_path = ruta
        item.caption = captions.build(db, topic)
        item.status = "prepared"
        item.error = None
        db.commit()
        return item

    # El formato lo decide `item.media_type`, que fija el repartidor de formatos
    # (`scheduling.repartir_formatos`) o el admin desde el panel. Antes se
    # forzaba carrusel siempre que se pudiera, y el resultado fue que 26 de los
    # 28 posts de la cola quedaron en carrusel: un feed monótono.
    quiere_carrusel = item.media_type == "CAROUSEL" or (
        config.CAROUSEL_ENABLED and item.media_type == "IMAGE" and not item.media_locked
        and not item.media
    )
    specs = carousel.plan(topic, item.content_type) if quiere_carrusel else None
    if not specs and item.media_type == "CAROUSEL" and item.media_locked:
        # Lo eligió una PERSONA en el panel: no se le cambia el formato a su
        # espalda. Antes se caía al `else`, que reescribe `media_type = "IMAGE"`,
        # y desde fuera parecía que el selector no funcionaba: elegías carrusel,
        # re-preparabas y volvía a foto sin una palabra.
        raise RuntimeError(
            "no hay material para un carrusel de este tema: hacen falta al menos "
            "dos frases de desarrollo y solo se ha encontrado una. Alarga el "
            "resumen del post o déjalo en foto única."
        )
    if specs:
        paths, used_hero = carousel.render(topic, specs, slot=item.slot or 1)
        item.media_type = "CAROUSEL"
    else:
        path, used_hero = imaging.generate(topic, slot=item.slot or 1)
        paths, specs = [path], [{"layout": "cover"}]
        item.media_type = "IMAGE"

    # Solo se acredita la foto si finalmente se usó una imagen real con
    # licencia; si la generación cayó al fondo IA, no hay crédito que poner.
    if not used_hero:
        topic.pop("image_credit", None)
    # Lo que se usó DE VERDAD: si la foto no se pudo bajar, `imaging` cae a arte
    # propio y eso es lo que sale publicado.
    item.image_origin = (topic.get("image_origin") or "foto") if used_hero else "ia"

    _sync_media(db, item, paths, specs)
    item.image_path = paths[0]      # espejo de la diapositiva 0
    item.caption = captions.build(db, topic)
    item.status = "prepared"
    item.error = None
    db.commit()

    # Lo último: dejar por escrito de dónde salió cada cosa, para que el panel
    # pueda enseñarlo y no haya que reconocer una cara para cazar un fallo.
    if topic.get("entidades"):
        _guardar_evidencia(db, item, topic, topic["entidades"])
    return item


def _prepare_product(
    db: Session, item: InstagramQueueItem, topic: dict
) -> InstagramQueueItem:
    """Prepara un post que enseña una funcionalidad de la web.

    El TEMA del post es la consulta concreta («¿Qué es la libertad para Robe?»),
    no la funcionalidad en abstracto: viene ya en el título desde que se creó, y
    aquí no se toca. Antes se machacaba con el título de la ficha, así que los
    cuatro posts de producto se llamaban todos igual.

    La pieza se compone consultando la API de VERDAD (pregunta real al
    consultorio, versos reales del buscador). Si la consulta falla, se lanza:
    un post que dice enseñar una funcionalidad tiene que enseñarla.
    """
    from app.services.instagram import product_shots, product_topics

    # content_key = "product:<funcionalidad>:<consulta>" (la consulta es lo que se
    # pregunta de verdad, y es el TEMA del post).
    ref = (item.content_key or "").removeprefix("product:").strip()
    slug, _, consulta_id = ref.partition(":")
    if not slug:
        raise RuntimeError(
            "este post de «la web» no dice qué funcionalidad enseña. Créalo desde "
            "«✦ enseñar la web», que le pone el tema."
        )

    ficha = product_shots.ficha(slug)
    if not ficha:
        raise RuntimeError(f"«{slug}» no está en data/instagram_product.yaml")

    consulta = product_topics.consulta_de(db, slug, consulta_id)
    ruta = product_shots.componer(db, slug, consulta)
    if not ruta:
        # Antes se cogía «la primera pieza que hubiera», y como el slug no se
        # reasignaba salía el título del karaoke sobre la foto del consultorio:
        # un post que promete una cosa y enseña otra. Mejor fallar y que se vea.
        raise RuntimeError(
            f"no se pudo componer la pieza de «{slug}» con «{consulta}» "
            "(¿falla el consultorio o el buscador?)"
        )

    topic["content_type"] = "product"
    topic["detalle"] = ficha.get("detalle", "")
    topic["cta"] = ficha.get("cta", "")
    topic["consulta"] = consulta
    # El título del post manda; el de la ficha es solo el nombre de la sección.
    topic["title"] = topic["headline"] = item.title
    topic["seccion"] = ficha.get("title") or slug
    if not (item.summary or "").strip() and ficha.get("claim"):
        item.summary = ficha["claim"]
    topic["summary"] = item.summary or ficha.get("claim", "")

    _sync_media(db, item, [ruta], [{"layout": "product"}])
    item.image_path = ruta
    item.image_origin = "producto"
    item.caption = captions.build(db, topic)
    item.status = "prepared"
    item.error = None
    db.commit()
    logger.info("[IG] item %s: «%s» sobre «%s»", item.id, consulta, slug)
    return item


def _sync_media(
    db: Session, item: InstagramQueueItem, paths: list[str], specs: list[dict],
    kind: str = "image",
) -> None:
    """Reescribe las filas de media del item con las rutas recién generadas."""
    item.media.clear()          # delete-orphan limpia las anteriores
    db.flush()
    for i, ruta in enumerate(paths):
        rol = (specs[i].get("layout") if i < len(specs) else None) or "body"
        item.media.append(
            InstagramQueueMedia(position=i, kind=kind, role=rol, local_path=ruta)
        )


def _media_lista(item: InstagramQueueItem) -> bool:
    """¿Están TODAS las piezas en disco?

    `IMAGES_DIR` vive en /tmp y es efímero. Con una sola imagen daba igual
    (se regeneraba), pero con un carrusel puede sobrevivir un subconjunto y
    publicarse mutilado o con las diapositivas desordenadas. Si falta una, se
    regenera el carrusel entero.
    """
    if not item.media:
        # `image_url` cuenta igual que el fichero: los items antiguos (previos a
        # la tabla de media) tienen su imagen en Cloudinary, y `/tmp` se vacía en
        # cada reinicio. Sin esto, repescar un post viejo regeneraba la imagen
        # con IA teniéndola ya subida.
        return bool(item.image_url) or bool(
            item.image_path and os.path.exists(item.image_path)
        )
    # Una pieza vale si está en disco O ya subida: los clips de terceros los baja
    # el daemon de la Mac y llegan directamente a Cloudinary, sin pasar por el
    # /tmp del servidor.
    return all(
        (m.local_path and os.path.exists(m.local_path)) or m.url
        for m in item.media
    )


def _marcar_fallo(
    db: Session,
    item: InstagramQueueItem,
    motivo,
    *,
    quema_intento: bool | None = None,
) -> InstagramQueueItem:
    """Deja el item en `failed` con su motivo, gastando o no un intento.

    Solo gastan intento los fallos ATRIBUIBLES AL ITEM (su material, su caption,
    lo que Meta diga de él). Cuando lo que está caído es la conexión con Meta el
    fallo es global —le pasaría igual a cualquier post— y quemarle un intento a
    este condenaría a la cola entera por algo que no es suyo. Mismo criterio que
    la cola de ingesta de YouTube, donde un 502 masivo durante un rebuild no
    consume reintentos.

    Con `quema_intento=None` (lo normal) lo decide `errors.quema_intento` leyendo
    el código que trae Meta. Se sigue admitiendo el booleano explícito para los
    casos en que el llamador ya sabe de quién es la culpa. Esa distinción existía
    en el docstring desde julio pero NO en el camino que importaba: el fallo al
    publicar la hacía siempre a ciegas, y por eso la cuenta restringida de agosto
    se llevó por delante 47 posts.
    """
    item.status = "failed"
    item.error = str(motivo)[:2000]
    item.error_code = getattr(motivo, "etiqueta", None)
    item.last_attempt_at = datetime.now(timezone.utc)
    if quema_intento is None:
        quema_intento = errors.quema_intento(motivo)
    if quema_intento:
        item.attempts = (item.attempts or 0) + 1
    db.commit()
    return item


def publicacion_bloqueada(db: Session) -> tuple[bool, str | None, datetime | None]:
    """¿Nos está bloqueando Meta ahora mismo? Devuelve (bloqueado, motivo, desde).

    El estado no se guarda en ningún sitio: se DEDUCE de los fallos recientes de
    la propia cola. Así caduca solo —no hay flag que alguien tenga que acordarse
    de apagar, que es de donde salen los "llevamos tres semanas sin publicar"— y
    además queda auditable: se ve qué items y qué código lo abrieron.

    Abre por dos caminos:
      - un `error_code` que sabemos global (25/2207050, 190, cuota...);
      - una RACHA de `GLOBAL_STREAK` items DISTINTOS fallando en la ventana,
        aunque no reconozcamos el código. Esto es lo que hace asumible que un
        código desconocido gaste intento: un global nuevo se caza igual.
    """
    desde = datetime.now(timezone.utc) - timedelta(hours=config.BLOCK_WINDOW_H)
    recientes = db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status == "failed",
            InstagramQueueItem.last_attempt_at.is_not(None),
            InstagramQueueItem.last_attempt_at >= desde,
        )
        .order_by(InstagramQueueItem.last_attempt_at.desc())
    ).scalars().all()
    if not recientes:
        return False, None, None

    for it in recientes:
        if it.error_code and errors.es_global(_error_de(it)):
            return True, (
                f"Meta está bloqueando la publicación: {it.error_code} · "
                f"{it.error or 'sin detalle'}"
            )[:300], _utc(it.last_attempt_at)

    if len({it.id for it in recientes}) >= config.GLOBAL_STREAK:
        # El motivo se devuelve YA redactado, y dice lo que se sabe y no más.
        # Cuando todos los fallos traen el MISMO código y ese código no es de
        # los globales, acusar a Meta de bloquear la cuenta manda a quien lee el
        # correo a desbloquear en instagram.com algo que no está bloqueado —
        # pasó el 13-sep-2026 con un 9004/2207052 (Meta no conseguía bajar las
        # imágenes de Cloudinary), y la cuenta estaba perfectamente.
        codigos = {it.error_code for it in recientes if it.error_code}
        n = len({it.id for it in recientes})
        if len(codigos) == 1:
            codigo = next(iter(codigos))
            return True, (
                f"{n} posts distintos han fallado con el mismo código "
                f"{codigo} en las últimas {config.BLOCK_WINDOW_H} h: "
                f"{recientes[0].error or 'sin detalle'}"
            )[:300], _utc(recientes[-1].last_attempt_at)
        return (
            True,
            f"Meta está bloqueando la publicación: {n} posts distintos han "
            f"fallado en las últimas {config.BLOCK_WINDOW_H} h: la caída no es "
            f"de ninguno de ellos",
            _utc(recientes[-1].last_attempt_at),
        )
    return False, None, None


def _error_de(item: InstagramQueueItem) -> errors.MetaError:
    """Rehidrata el MetaError de un item ya guardado, para reclasificarlo."""
    code, _, subcode = (item.error_code or "").partition("/")
    return errors.MetaError(
        mensaje=item.error or "",
        code=int(code) if code.lstrip("-").isdigit() else None,
        subcode=int(subcode) if subcode.isdigit() else None,
    )


def _utc(dt: datetime | None) -> datetime | None:
    """SQLite devuelve datetimes sin tzinfo; Postgres con ella."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def publish(
    db: Session,
    item: InstagramQueueItem,
    dry_run: bool = False,
    force: bool = False,
) -> InstagramQueueItem:
    """Publica un item ya preparado (lo prepara si hace falta).

    `force` se salta el cortacircuitos: lo usa el botón del panel, porque un
    humano que le da a publicar tiene que poder ver el error real de Meta (y de
    paso ese intento sirve de sondeo).
    """
    if contador_desfasado(item):
        _poner_al_dia_el_contador(db, item)

    if not _media_lista(item):
        # Preparar puede fallar por motivos legítimos (un post de clip sin clip
        # enlazado, un carrusel sin material). Eso NO puede tumbar el cron: sin
        # este `except`, la excepción subía hasta `publish_next` y además el item
        # se quedaba `pending`, así que `next_pending` lo volvía a elegir cada
        # 15 minutos y la cola entera se quedaba atascada detrás de él.
        try:
            prepare(db, item)
        except MaterialPendiente as esperando:
            # Se queda como está y se reintenta en la siguiente pasada del cron.
            db.rollback()
            logger.info("[IG] item %s todavía no: %s", item.id, esperando)
            return item
        except (TextoRetenido, newsroom.TextoNoPublicable) as retenido:
            # El texto no se sostiene: no es una avería ni un fallo de Meta. Con
            # `_marcar_fallo` quedaría `failed`, gastaría intento y contaría para
            # la racha del cortacircuitos, que acusaría a Meta en falso.
            db.rollback()
            return _retener(db, item, str(retenido))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.error("[IG] item %s no se pudo preparar: %s", item.id, exc)
            return _marcar_fallo(db, item, f"al preparar: {exc}")

    # La última puerta: TODO lo que va a ver la gente, ya montado. Va antes del
    # dry-run para que el ensayo diga lo mismo que diría la publicación real.
    veredicto = revisar_gate(db, item)
    if not veredicto.ok:
        return _retener(db, item, veredicto.motivo)

    if dry_run:
        item.status = "prepared"
        db.commit()
        logger.info("[DRY-RUN] item %s listo (no se publica).", item.id)
        return item

    # Verificar token Y que la cuenta sea alcanzable (no solo el scope).
    ok, msg, _ = graph_api.connection_is_healthy()
    if not ok:
        logger.error("[IG] conexión no saludable para publicar: %s", msg)
        # Fallo global, no de este post: no le quema un intento (ver `_marcar_fallo`).
        return _marcar_fallo(db, item, msg, quema_intento=False)

    # Si Meta nos está bloqueando, parar AQUÍ: subir a Cloudinary y crear
    # containers para que los rechace todos cuesta dinero y no arregla nada. En
    # agosto de 2026 el cron hizo eso cada 15 minutos durante once días.
    if not force:
        bloqueado, motivo_bloqueo, _ = publicacion_bloqueada(db)
        if bloqueado:
            logger.warning("[IG] publicación bloqueada por Meta: %s", motivo_bloqueo)
            # No es culpa de este post: no le quema intento.
            return _marcar_fallo(
                db, item, f"publicación bloqueada: {motivo_bloqueo}",
                quema_intento=False,
            )

    # Subir a Cloudinary (la Graph API exige URLs públicas). Se hace commit de
    # las URLs ANTES de llamar a Meta: si la publicación falla, reintentar no
    # tiene que volver a subir nada.
    piezas = sorted(item.media, key=lambda m: m.position) or []
    try:
        if piezas:
            for m in piezas:
                if m.url:
                    # Ya está en el CDN: o se subió en un intento anterior, o nunca
                    # pasó por aquí. Los clips de terceros son lo segundo — los baja
                    # el daemon de la Mac y llegan directos a Cloudinary sin tocar el
                    # /tmp del servidor, así que su `local_path` está vacío a
                    # propósito. `_media_lista` los da por buenos por eso mismo;
                    # aquí faltaba la misma comprobación y se llamaba a
                    # `upload_video(None)` → «expected str, bytes or os.PathLike
                    # object, not NoneType» y el post moría sin llegar a Meta.
                    continue
                if m.kind == "video":
                    subido = cloudinary_upload.upload_video(m.local_path)
                    m.url = subido["url"]
                    m.cloudinary_public_id = subido["public_id"]
                    m.duration_s = subido.get("duration")
                else:
                    m.url = cloudinary_upload.upload(m.local_path)
        elif not item.image_url:  # item antiguo, anterior a la tabla de media
            # Mismo criterio que el `continue` de arriba: si ya está en el CDN no
            # se vuelve a subir. Sin el `elif`, un item viejo repescado llamaba a
            # `upload(None)` —su `/tmp` hacía días que no existía— y moría por un
            # fichero que no le hacía ninguna falta.
            item.image_url = cloudinary_upload.upload(item.image_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("[IG] subida a Cloudinary falló: %s", exc)
        return _marcar_fallo(db, item, f"Cloudinary: {exc}")
    if piezas:
        item.image_url = piezas[0].url      # espejo de la diapositiva 0
    db.commit()

    urls = [m.url for m in piezas if m.url] or [item.image_url]
    if item.media_type in ("REELS", "CLIP"):
        # CLIP va aquí con REELS porque las dos cosas son un VÍDEO: en Instagram
        # el clip de otro canal se publica como reel igual que el verso animado.
        # Faltaba, y caía al `else` → `post_photo` con una URL de .mp4, así que
        # ningún clip podía publicarse.
        #
        # Meta tarda minutos en procesar un vídeo: el polling largo solo es
        # viable desde el cron, nunca dentro de una petición del panel.
        media_id, result_msg = graph_api.post_reel(urls[0], item.caption or "")
    elif item.media_type == "CAROUSEL" and len(urls) >= graph_api.MIN_CAROUSEL_ITEMS:
        media_id, result_msg = graph_api.post_carousel(urls, item.caption or "")
    else:
        media_id, result_msg = graph_api.post_photo(urls[0], item.caption or "")
    if media_id:
        item.status = "published"
        item.ig_media_id = media_id
        item.published_at = datetime.now(timezone.utc)
        item.error = None
        item.error_code = None
        item.attempts = 0
        logger.info("[IG] ✅ item %s publicado · media_id=%s", item.id, media_id)
        # Si el post salió de un clip de terceros, se cierra su ficha: así el
        # registro de procedencia sabe en qué publicación acabó y la retirada
        # puede borrar el post correcto.
        clip = db.execute(
            select(VideoClip).where(VideoClip.queue_item_id == item.id)
        ).scalars().first()
        if clip is not None:
            clip.status = "published"
            clip.ig_media_id = media_id
            clip.published_at = item.published_at
            db.commit()

        # Arranca el hilo con la pregunta del caption, como hacen las cuentas
        # del nicho con mejor engagement. Best-effort: si falla, el post ya está
        # publicado y no se toca.
        try:
            ok, detalle = community.comentar_post(media_id, item.caption or "")
            if not ok:
                logger.info("[IG] sin autocomentario en %s: %s", item.id, detalle)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IG] autocomentario falló en %s: %s", item.id, exc)
    else:
        logger.error("[IG] ❌ item %s falló: %s", item.id, result_msg)
        return _marcar_fallo(db, item, result_msg or "Meta no devolvió media_id")
    db.commit()
    return item


def _publicable():
    """Condición SQL de «a este item todavía le toca salir».

    Además de lo que espera turno (`pending`/`prepared`), incluye lo que falló
    pero conserva intentos. Antes un `failed` era terminal de hecho: los dos
    selectores de la cola filtraban por pending/prepared, así que un tropiezo
    transitorio —el CDN, un timeout de Meta— borraba el post del calendario para
    siempre y en silencio. Nadie se enteraba hasta echar de menos la publicación.

    Y le conserva los intentos DE VERDAD: reintentar exige que hayan pasado
    `RETRY_COOLDOWN_H`. El cron dispara cada 15 min y el guard de cadencia solo
    frena tras un éxito, así que con todo fallando reintentaba 96 veces al día
    y los 3 intentos se gastaban en 45 minutos — mucho antes de que la alerta
    diaria pudiera avisar de nada.
    """
    limite = datetime.now(timezone.utc) - timedelta(hours=config.RETRY_COOLDOWN_H)
    # Lo que pide que lo mire una persona NO sale solo. Antes `needs_human` era
    # solo una etiqueta del panel y el goteo lo publicaba igual; ahora es lo que
    # usa el gate final para retener, y si el selector no lo saltara elegiría el
    # mismo item cada 15 minutos y pararía la cola entera detrás de él.
    return and_(
        InstagramQueueItem.needs_human.is_(False),
        or_(
            InstagramQueueItem.status.in_(("pending", "prepared")),
            and_(
                InstagramQueueItem.status == "failed",
                InstagramQueueItem.attempts < config.MAX_PUBLISH_ATTEMPTS,
                or_(
                    InstagramQueueItem.last_attempt_at.is_(None),
                    InstagramQueueItem.last_attempt_at <= limite,
                ),
            ),
        ),
    )


def _lo_que_caduca_primero():
    """La actualidad sale antes que lo evergreen. Es lo único que no espera.

    El 13-sep-2026 se repescaron 16 versos y anécdotas que un bloqueo de Meta
    condenó en agosto. Al ir al final de la cola ocupaban siete días de
    calendario, y como `prepare_daily` encola cada noticia nueva detrás de todo
    (`max(position) + 1`), la actualidad de esa semana habría salido con doce
    días encima: publicarla así engaña sobre cuándo pasó, que es justo por lo
    que `recover_failed` descarta las noticias viejas en vez de repescarlas.

    Al revés no se pierde nada: un verso no caduca, espera.

    No sirve ordenar por `slot` —que es lo que el ORDER BY declaraba y no
    cumplía, porque `position` es única por item y nunca llega a desempatar—:
    el slot lo asigna `prepare_daily` por hueco del día, no por tipo, y en prod
    había `news` repartidas entre los slots 0, 1 y 2.

    Dentro de cada grupo sigue mandando `position`, así que el reordenado a mano
    del panel se respeta. Para adelantar algo por encima de todo está
    programarlo con `publish_at`, que sale por `due_pinned` al margen del goteo.
    """
    return case(
        (InstagramQueueItem.content_type.in_(config.TIPOS_DE_ACTUALIDAD), 0),
        else_=1,
    )


def _filtro_video(video: bool | None) -> list:
    if video is None:
        return []
    es_video = InstagramQueueItem.media_type.in_(config.VIDEO_MEDIA_TYPES)
    return [es_video] if video else [or_(~es_video, InstagramQueueItem.media_type.is_(None))]


def next_pending(db: Session, *, video: bool | None = None) -> InstagramQueueItem | None:
    """Siguiente item del GOTEO: primero lo que caduca (noticias y blog), y
    dentro de cada grupo el orden manual (`position`), slot, día y antigüedad.
    Excluye el contenido con momento fijado (`publish_on` de efeméride o
    `publish_at` programado a mano): ese no gotea, sale a su hora vía
    `due_pinned`.

    `video`: None = todo (panel); False = solo el goteo de carruseles; True =
    solo el carril de vídeo (`config.VIDEO_MEDIA_TYPES`)."""
    # Un post de clip cuyo vídeo aún se está bajando NO cuenta como pendiente:
    # si contara, el goteo lo elegiría cada 15 minutos —siempre es el mismo, va
    # por `position`— y toda la cola se quedaría parada detrás esperándolo.
    clip_listo = (
        select(VideoClip.id)
        .where(
            VideoClip.queue_item_id == InstagramQueueItem.id,
            VideoClip.status.in_(("ready", "published")),
        )
        .exists()
    )
    return db.execute(
        select(InstagramQueueItem)
        .where(
            _publicable(),
            InstagramQueueItem.publish_on.is_(None),
            InstagramQueueItem.publish_at.is_(None),
            or_(InstagramQueueItem.media_type != "CLIP", clip_listo),
            *_filtro_video(video),
        )
        .order_by(
            _lo_que_caduca_primero(),
            InstagramQueueItem.position,
            InstagramQueueItem.slot,
            InstagramQueueItem.day,
            InstagramQueueItem.created_at,
        )
        .limit(1)
    ).scalar_one_or_none()


def due_pinned(db: Session, ahora: datetime | None = None) -> list[InstagramQueueItem]:
    """Items con momento fijado que YA toca publicar, al margen del cuentagotas.

    Dos formas de fijar el momento, y las dos vencen aquí:
      - `publish_on` (efeméride): su día exacto, sin hora.
      - `publish_at`  (programado a mano en el panel): fecha y hora concretas;
        vence cuando ese instante ya pasó, así que un post programado para una
        hora en la que el cron no corría sale en la pasada siguiente en vez de
        perderse.

    Lo que falló con intentos de sobra también vence aquí: un post programado no
    puede evaporarse porque el CDN diera un error a su hora exacta.
    """
    from app.services.instagram import scheduling

    ahora = ahora or datetime.now(timezone.utc)
    local = ahora.astimezone(_MADRID)
    # Una efeméride vence en su día, pero no antes de la primera franja: con el
    # día a secas salía a las 00:00 UTC, la 01:00 en Madrid (09-11-2026).
    primera = min(scheduling.slots_diarios(), default=None)
    efemeride_toca = primera is None or local.time() >= primera
    condiciones = [InstagramQueueItem.publish_at <= ahora]
    if efemeride_toca:
        condiciones.append(and_(
            InstagramQueueItem.publish_on == local.date(),
            InstagramQueueItem.publish_at.is_(None),
        ))
    return db.execute(
        select(InstagramQueueItem)
        .where(
            _publicable(),
            or_(*condiciones),
        )
        .order_by(InstagramQueueItem.position, InstagramQueueItem.created_at)
    ).scalars().all()
