"""Generación del borrador editorial de una propuesta.

Antes esta lógica vivía dentro de `scripts/blog/materialize_proposals.py` y solo
corría al publicar. Ahora se invoca **al aprobar** una propuesta: genera el
cuerpo (RAG), elige la foto, sanea y enlaza, y deja todo guardado en la propia
`ContentProposal` (body_md, excerpt, meta, hero, entities). Así "aprobadas"
contiene borradores ya revisables, y `materialize_proposals` solo copia el
borrador al `Post` y lo publica el día programado.

Idempotente por estado: si la propuesta ya tiene `body_md`, `generate_body`
no se vuelve a llamar (las noticias ya traen cuerpo del scraper); el
post-procesado (hero + saneado + enlazado) se aplica una vez al construir el
borrador.
"""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    ContentProposal,
    Person,
    Place,
    SeoContent,
    Song,
    Theme,
)
from app.services.content_generator import (
    generate_album_anniversary,
    generate_anniversary,
    generate_evergreen_topic,
    generate_seo_article,
    generate_song_spotlight,
)
from scripts.blog.context_builder import (
    album_context,
    artist_context,
    song_context,
    taxonomy_context,
)

logger = logging.getLogger(__name__)

ROBE = "Robe Iniesta"


def _deep_body(
    db, *, entity_type: str, entity, framing: str, coverage: str = "",
    extra_material: str = "", tier: str = "standard", serp_guidance: str = "",
    tipo_pieza: str | None = None,
) -> dict | None:
    """Genera un cuerpo con el MOTOR PROFUNDO (mismo que las páginas de entidad y
    las noticias): dossier RAG del corpus + outline adaptativo + sección a sección
    con anti-redundancia (`prior`) + verificación factual + pulido. Devuelve el
    dict editorial o None si no hay material para algo digno (lo decide el rigor
    aguas abajo). Sustituye al one-shot genérico que producía relleno.

    `extra_material`: material adicional REAL (p.ej. investigación web dirigida) que
    se suma al dossier del corpus. La verificación por sección sigue actuando: solo
    sobrevive lo que el material (corpus + extra) respalde (anti-invención)."""
    try:
        from openai import OpenAI

        from app.services import source_guard
        from app.services.deep_research import gather_entity_dossier
        from app.services.news_research import _news_meta
        from app.services.text_sanitizer import strip_ai_tells
        from scripts.seo.generate_deep import (
            _coverage_hint,
            _material_afirmable,
            _outline,
            _polish,
            _verify_section,
            _write_section,
        )

        dossier = gather_entity_dossier(db, entity_type, entity)
        material = dossier.material or ""
        if extra_material.strip():
            material = f"{material}\n\nINVESTIGACIÓN WEB (material real adicional):\n{extra_material}"
        subject = dossier.subject
        cov = coverage or _coverage_hint(entity_type)
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        # Lo que el listón pide y los hechos duros no traen se BUSCA en el corpus por
        # consulta antes de escribir (la grabación, el sonido): pedirlo sin material
        # le enseña al redactor a esquivar o a inventar. Lo encontrado entra como
        # material; lo afirmable, también para el verificador.
        busqueda, busqueda_afirmable = (_buscar_lo_que_falta(db, client, tipo_pieza, dossier,
                                                             subject)
                                        if tipo_pieza else ("", {}))
        con_material = set(busqueda_afirmable)
        if busqueda:
            material = f"{material}\n\n{busqueda}"
        fichas = _fichas_propias(db, entity_type, entity) if tipo_pieza else ""
        letras = _letras_del_disco(db, entity_type, entity) if tipo_pieza else ""
        if letras:
            fichas = f"{fichas}\n\n----\n\n{letras}" if fichas else letras
        if fichas:
            material = f"{fichas}\n\n----\n\n{material}"
        # El encargo sale del MISMO listón que leen el foco y el juez, y solo pide lo
        # que los hechos duros o la búsqueda traen (`piece_checklist`).
        from app.services.piece_checklist import liston
        lst = liston(tipo_pieza, dossier.hard_facts, con_material) if tipo_pieza else None
        if lst and lst.encargo():
            framing = f"{framing} {lst.encargo()}"
        correcciones = _CORRECCIONES.get()
        if correcciones:
            framing = (f"{framing} El editor jefe rechazó la versión anterior por esto; "
                       "corrígelo SIN inventar (lo que no esté en los DATOS DUROS ni en el "
                       f"material, no lo menciones): {correcciones}")
        hard = f"{framing}\nDATOS DUROS (úsalos, son verídicos):\n{dossier.hard_facts}"
        if serp_guidance.strip():
            hard += f"\n\n{serp_guidance.strip()}"

        outline = _outline(client, subject, "", hard, material, cov, tier=tier)
        if not outline:
            return None
        headings = [s["heading"] for s in outline]
        TRAZA.clear()
        # Lo que se puede AFIRMAR: hechos duros + lo propio + lo ajeno corroborado, igual
        # que las fichas (`generate_deep`). El escritor sigue viendo todo el material
        # para saber de qué hablar. Con el material entero, el aniversario de
        # «Destrozares» salía apoyado en «Mondo Sonoro destacó…» (La voz es nuestra).
        if lst is not None:
            # Piezas con listón (aniversario de disco). Medido el 18-11-2026 sobre una
            # canción, una evergreen y una efeméride: aplicado a todo, empeoraba la canción
            # (34 → 18, «la letra no aclara…»), así que el resto sigue verificando como
            # antes, pero con los hechos duros DELANTE (sin ellos se comía la fecha).
            afirmable = _material_afirmable(client, dossier, [subject, *headings[:4]], db=db)
            if busqueda_afirmable:
                afirmable += "\n\n" + "\n\n".join(busqueda_afirmable.values())
            if fichas:
                afirmable = f"{afirmable}\n\n----\n\n{fichas}"
        else:
            afirmable = f"{dossier.hard_facts}\n\n{material}"
        if extra_material.strip() and lst is not None:
            afirmable += f"\n\nINVESTIGACIÓN WEB (material real adicional):\n{extra_material}"
        parts: list[str] = []
        prior = ""
        for s in outline:
            sec = _write_section(client, subject, s, headings, hard, material, "",
                                 prior=prior, coverage=cov, tier=tier)
            # Los hechos duros DELANTE: el verificador quita lo que no esté en su
            # material, y sin ellos se llevaba la fecha de publicación que el propio
            # encargo daba (aniversario de «Destrozares», 18-11-2026). Delante porque
            # corta a 90.000 caracteres y ese dossier pasaba de 95.000.
            antes = sec
            sec = _verify_section(client, sec, afirmable)
            TRAZA.append({"heading": s.get("heading"), "antes": antes, "despues": sec})
            if sec.strip():
                parts.append(sec.strip())
                prior = "\n\n".join(parts)
        body = "\n\n".join(parts)
        if len(body.strip()) < 300:
            return None
        body = _polish(client, subject, body) or body
        body = strip_ai_tells(body) or body
        # Las mismas limpiezas deterministas que las fichas: frases que nombran a un
        # medio o analista, eco del encargo («el material disponible no especifica») y
        # confesiones de no saber. `_polish` reescribe sin verificar: van después.
        _quitadas: list[str] = []
        if lst is not None:
            body, _quitadas = source_guard.limpiar(body, source_guard.nombres_de_fuentes(db))
        body, _confesiones = source_guard.quitar_confesiones(body)
        if _quitadas or _confesiones:
            logger.info("[draft] limpieza: %d frase(s) de fuentes/metatexto, %d confesión(es)",
                        len(_quitadas), len(_confesiones))
        if len(body.strip()) < 300:
            return None
        meta = _news_meta(subject, body)
        return {
            "title": (meta.get("title") or subject)[:240],
            "excerpt": meta.get("excerpt") or "",
            "body_md": body,
            "meta_title": meta.get("meta_title") or "",
            "meta_description": meta.get("meta_description") or "",
            "entities": [],
        }
    except Exception as exc:  # noqa: BLE001 — degradar al generador clásico
        logger.warning("[draft] motor profundo falló (%s): %s", entity_type, exc)
        return None


# Motivos del editor jefe en la versión anterior; `_deep_body` los añade al encargo
# cuando `juzgar_borrador` pide una reescritura. ContextVar para no cambiar la firma de
# todos los generadores por kind.
_CORRECCIONES: ContextVar[str] = ContextVar("_CORRECCIONES", default="")
MAX_REESCRITURAS = 2
# Una pieza con listón que tras verificar se queda en menos de esto no tiene material
# afirmable de sobra: reescribirla con los mismos datos da lo mismo (18-11-2026,
# «Bienvenidos al temporal»: 1.598 caracteres y dos reescrituras a ciegas). Se busca
# MÁS material una vez, con consultas amplias, y si sigue corta se retiene diciendo por
# qué. El aniversario de «Destrozares» que pasó tenía 4.054.
MIN_CUERPO_CON_LISTON = 2500
_BUSQUEDA_AMPLIA: ContextVar[bool] = ContextVar("_BUSQUEDA_AMPLIA", default=False)
# Consultas de la búsqueda amplia, para todo lo que el listón pide (también lo que los
# hechos duros ya cubren: el contexto de un dato también es material).
CONSULTAS_AMPLIAS = (
    "historia del disco {t}", "Robe habla de {t} en una entrevista",
    "grabación y conciertos de {t}", "canciones de {t} y su significado",
    "músicos y formación de {t}", "{t} en directo y gira",
)
# Lo que es central para la web (un disco, la efeméride de Robe) y no se tira por una
# tirada del juez en la frontera: va a la lectura de David.
PIEZAS_CENTRALES = frozenset({"album-anniversary", "anniversary"})
UMBRAL_PARA_TU_LECTURA = 55

FICHA_MAX_CHARS = 2500
# Cada sección antes y después del verificador, para diagnosticar qué se quita (la
# prueba de fuego del aniversario de «Destrozares» lo necesitó). Se vacía en cada cuerpo.
TRAZA: list[dict] = []


def _fichas_propias(db, entity_type: str, entity) -> str:
    """Las fichas YA PUBLICADAS de la entidad (y, si es un disco, las de sus canciones)
    como material propio. Medido el 18-11-2026: la ficha de «Destrozares» (6.300
    caracteres) y las de sus 10 canciones no llegaban al redactor del post de su
    aniversario. Criterio de David: se usan sin copiarlas, y el post enlaza a ellas."""
    from app.db.models import SeoContent

    pares: list[tuple[str, int, str]] = []
    if entity_type == "album":
        pares.append(("album", entity.id, entity.title))
        for sid, titulo in db.execute(
                select(Song.id, Song.title).where(Song.album_id == entity.id)
                .order_by(Song.track_number.nulls_last())).all():
            pares.append(("song", sid, titulo))
    elif entity_type == "song":
        pares.append(("song", entity.id, entity.title))
        if getattr(entity, "album_id", None):
            al = db.get(Album, entity.album_id)
            if al:
                pares.append(("album", al.id, al.title))
    bloques = []
    for tipo, ident, titulo in pares:
        f = db.execute(select(SeoContent).where(
            SeoContent.entity_type == tipo, SeoContent.entity_id == ident,
            SeoContent.published.is_(True))).scalar_one_or_none()
        if f and (f.body_md or "").strip():
            bloques.append(
                f"[FICHA PUBLICADA DE ENTRE INTERIORES · {titulo}] (material propio y "
                "verificado: afirma sus datos en nuestra voz, sin decir «la ficha»; "
                "PROHIBIDO copiar sus frases o su estructura: el post cuenta otra historia)\n"
                + f.body_md.strip()[:FICHA_MAX_CHARS])
    return "\n\n----\n\n".join(bloques)


LETRA_MAX_CHARS = 1400


def _letras_del_disco(db, entity_type: str, entity) -> str:
    """Las letras REALES de las canciones del disco, como material propio. El dossier de
    un disco solo traía un resumen corto por canción, sin versos: el juez pedía «versos
    que sostengan la lectura» y el redactor no tenía ninguno (18-11-2026). Cada verso que
    se cite lo sigue comprobando `lyric_guard` contra la letra."""
    if entity_type != "album":
        return ""
    bloques = []
    for titulo, letra in db.execute(
            select(Song.title, Song.lyrics_clean).where(Song.album_id == entity.id)
            .order_by(Song.track_number.nulls_last())).all():
        if (letra or "").strip():
            bloques.append(f"[LETRA · «{titulo}»] (verso citable LITERAL, nombrando la canción)\n"
                           + letra.strip()[:LETRA_MAX_CHARS])
    return "\n\n----\n\n".join(bloques)


def _buscar_lo_que_falta(db, client, tipo_pieza: str, dossier, subject: str
                         ) -> tuple[str, dict[str, str]]:
    """Material del corpus para cada punto del listón que los hechos duros no cubren.

    Devuelve (bloque para el redactor, {clave_punto: parte afirmable}). Un punto solo
    cuenta como cubierto si sale algo AFIRMABLE: palabras de Robe, testimonio del
    entorno o un dato de terceros corroborado (`corroborar`). El fondo sin corroborar
    orienta al redactor, pero no hace exigible el punto."""
    from app.services.corpus_for_queries import (
        bloque_material,
        corroborar,
        es_entrevista_transcrita,
        material_para_consultas,
        parte_afirmable,
    )
    from app.services.piece_checklist import pendientes

    from app.services.piece_checklist import Punto

    base = (subject or "").split(",")[0].strip()
    bloques, afirmable = [], {}
    puntos = list(pendientes(tipo_pieza, dossier.hard_facts))
    amplia = _BUSQUEDA_AMPLIA.get()
    if amplia:
        # Un punto «contexto» que no exige nada: su material solo engorda lo afirmable.
        puntos.append(Punto("contexto", "contexto del disco", (), CONSULTAS_AMPLIAS))
    for punto in puntos:
        consultas = [c.format(t=base) for c in punto.consultas]
        try:
            pasajes = material_para_consultas(db, consultas, k=8 if amplia else 4,
                                              max_pasajes=10 if amplia else 5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[draft] búsqueda de «%s» falló: %s", punto.clave, exc)
            continue
        if not pasajes:
            continue
        propios = [x for x in pasajes if x.get("kind") in ("robe_interview", "entorno_interview")]
        transcritas = [x for x in pasajes
                       if es_entrevista_transcrita(x.get("kind"), x.get("title"))]
        fondo = "\n\n".join(x["fragmento"] for x in pasajes
                             if x not in propios and x not in transcritas)
        verificados, _ = corroborar(client, fondo, dossier.hard_facts, consultas, db=db)
        bloque = bloque_material([x for x in pasajes if x not in transcritas], verificados)
        if transcritas:
            bloque += ("\n\n====\n\nENTREVISTAS A ROBE TRANSCRITAS (afirma lo que cuenta; "
                       "PROHIBIDO entrecomillar: la transcripción trae erratas):\n\n"
                       + "\n\n----\n\n".join(x["fragmento"] for x in transcritas))
        if not bloque.strip():
            continue
        bloques.append(f"[MATERIAL BUSCADO PARA: {punto.encargo}]\n{bloque}")
        solo = parte_afirmable(bloque)
        propios = propios + transcritas
        if propios or verificados:
            afirmable[punto.clave] = solo
        logger.info("[draft] «%s»: %d pasaje(s), %d propio(s), %d dato(s) corroborado(s)",
                    punto.clave, len(pasajes), len(propios), len(verificados))
    return "\n\n".join(bloques), afirmable


def _primary_keyword(p: ContentProposal) -> str:
    """Keyword principal de la propuesta (la de más volumen), o el target/título."""
    kws = getattr(p, "keywords", None) or []
    if kws:
        try:
            top = max(kws, key=lambda k: (k.get("volume") or 0))
            if top.get("keyword"):
                return top["keyword"]
        except Exception:  # noqa: BLE001
            pass
    return (p.target_keyword or p.title or "").strip()


def _deep_seo_evergreen(
    db, p: ContentProposal, *, tier: str = "standard", serp: str = "",
) -> dict | None:
    """Intenta anclar un evergreen 'seo' a su entidad central y generarlo con el
    motor profundo. Devuelve el dict editorial o None si no hay ancla fiable (→ el
    caller cae al one-shot). El titular/ángulo se pasan como `framing` para no
    perder la intención de búsqueda; el dossier de la entidad aporta la sustancia."""
    try:
        from app.services.blog_anchor import resolve_central_entity
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft: resolver de ancla no disponible: %s", exc)
        return None

    anchor = resolve_central_entity(
        db, primary_keyword=_primary_keyword(p), title=p.title, angle=p.angle
    )
    if not anchor:
        return None

    angle = (p.angle or "").strip()
    framing = (
        f"{p.title}. Pieza a fondo anclada al corpus sobre «{anchor.name}»"
        + (f" — ángulo: {angle}" if angle else "")
        + ". Responde de verdad a lo que busca quien teclea «"
        + _primary_keyword(p)
        + "»: hechos, datos y (si aplica) versos REALES del material [LETRA] "
        "(copiados LITERAL; nunca inventes un verso ni lo atribuyas a una canción "
        "sin tener su letra). Concreto y con sustancia, nada genérico ni de relleno."
    )
    deep = _deep_body(
        db, entity_type=anchor.entity_type, entity=anchor.entity,
        framing=framing, tier=tier, serp_guidance=serp,
    )
    if deep:
        logger.info("draft: evergreen 'seo' #%s anclado a %s/%s (motor profundo)",
                    p.id, anchor.entity_type, anchor.name)
    return deep


def _entidad_catalogo(db, tipo: str, ident: int):
    from app.db.models import Person, Place
    return db.get({"album": Album, "song": Song, "person": Person, "place": Place}[tipo], ident)


def _deep_catalogo(db, p: ContentProposal, cat: tuple[str, str], *, tier: str, serp: str):
    """Idea de catálogo: se escribe CON su entidad (no se adivina por keyword) y con el
    listón de su ángulo. Es una historia para fans: no repite la ficha, la enlaza."""
    tipo, angulo = cat
    entidad = _entidad_catalogo(db, tipo, p.source_id)
    if entidad is None:
        return None
    framing = (
        f"{p.title}. Cuenta {(p.angle or '').split('. Material:')[0].lower()}. Es una historia "
        "para quien ya conoce la obra: no repitas lo que dice la ficha de la entidad, cuenta "
        "otra cosa y apóyate en hechos concretos, versos LITERALES de [LETRA] si citas una "
        "canción y lo que contó Robe (con el medio si es una entrevista escrita). La voz es "
        "nuestra: no nombres medios, blogs ni analistas. Nunca hables del proceso («el "
        "material», «las fuentes»). Nada de loas vacías."
    )
    return _deep_body(db, entity_type=tipo, entity=entidad, framing=framing, tier=tier,
                      serp_guidance=serp,
                      tipo_pieza="album-historia" if (tipo, angulo) == ("album", "historia") else None)


def tipo_pieza_de(p: ContentProposal) -> str:
    """El tipo de pieza para el listón y el juez."""
    from app.services.catalog_ideas import entidad_de
    if entidad_de(p.source_type) == ("album", "historia"):
        return "album-historia"
    return p.kind


def generate_body(db, p: ContentProposal) -> dict | None:
    """Genera el contenido editorial de una propuesta sin body, según kind.
    Devuelve dict con title/excerpt/body_md/meta_title/meta_description/entities
    o None si no se pudo. Los tipos anclados a una entidad real (canción, disco,
    Robe, taxonomía) usan el MOTOR PROFUNDO; si falla, caen al generador clásico.

    El `tier` de engagement (premium/flagship) sube la extensión/profundidad y, para
    esos temas, trae un brief de competencia SERP como guía de cobertura a superar."""
    today = date.today()
    _tier = getattr(p, "quality_tier", None) or "standard"
    _serp = ""
    if _tier in ("premium", "flagship", "cornerstone"):
        try:
            from app.services.serp_brief import build_brief
            _serp = build_brief(p.target_keyword or p.title or "")
        except Exception as exc:  # noqa: BLE001 — el brief es opcional
            logger.warning("draft: brief SERP falló: %s", exc)

    from app.services.catalog_ideas import entidad_de
    cat = entidad_de(p.source_type)
    if cat and p.source_id:
        return _deep_catalogo(db, p, cat, tier=_tier, serp=_serp)

    if p.kind == "spotlight" and p.source_type == "song" and p.source_id:
        song = db.get(Song, p.source_id)
        if not song:
            return None
        # Una propuesta vieja puede apuntar a una fila del directo: se escribe
        # sobre la canción original, con su disco y su año.
        from app.services.versiones import version_original
        song = version_original(db, song)
        album = db.get(Album, song.album_id)
        artist = db.get(Artist, album.artist_id) if album else None
        seo = db.execute(
            select(SeoContent).where(
                SeoContent.entity_type == "song", SeoContent.entity_id == song.id
            )
        ).scalar_one_or_none()
        deep = _deep_body(
            db, entity_type="song", entity=song,
            framing=(
                f"Análisis a fondo de la canción «{song.title}»"
                + (f" del disco «{album.title}»" if album else "")
                + ". CITA versos textuales concretos entre comillas (copiados LITERAL "
                "de la letra real que tienes en el material [LETRA]; nunca inventes un "
                "verso), explica su significado, la música y su contexto. Nada genérico."
            ),
            tier=_tier, serp_guidance=_serp,
        )
        if deep:
            return deep
        try:
            ctx = song_context(db, song.id)
        except Exception:
            ctx = ""
        return generate_song_spotlight(
            song_title=song.title,
            album_title=album.title if album else "",
            artist_name=artist.name if artist else "",
            seo_excerpt=(seo.body_md if seo else None),
            context=ctx,
            today=today,
        )

    if p.kind == "album-anniversary" and p.source_type == "album" and p.source_id:
        album = db.get(Album, p.source_id)
        if not album:
            return None
        artist = db.get(Artist, album.artist_id)
        years = today.year - (
            album.release_date.year if album.release_date else today.year
        )
        track_titles = [
            t for (t,) in db.execute(
                select(Song.title).where(Song.album_id == album.id)
                .order_by(Song.track_number.nulls_last())
            ).all()
        ]
        rel_year = album.release_date.year if album.release_date else album.year
        deep = _deep_body(
            db, entity_type="album", entity=album,
            framing=(
                f"{max(years,1)} años del disco «{album.title}» "
                f"(publicado el {album.release_date.isoformat() if album.release_date else rel_year}). "
                "Nombra cada canción por su TÍTULO (nunca por un verso suelto) y, cuando "
                "comentes una, cita un verso LITERAL de su [LETRA]. La voz es "
                "nuestra: no nombres medios, blogs ni analistas (solo Robe se cita, con su "
                "medio). Nunca hables del proceso: nada de «el material», «las fuentes», "
                "«la reseña» ni «no se especifica»; lo que no sabes, no lo menciones. No "
                "escribas «hoy» ni «este mes»: la fecha de publicación del post puede "
                "moverse. Datos concretos; nada de loas vacías."
            ),
            tier=_tier, serp_guidance=_serp, tipo_pieza="album-anniversary",
        )
        if deep:
            return deep
        try:
            ctx = album_context(db, album.id)
        except Exception:
            ctx = ""
        return generate_album_anniversary(
            album_title=album.title,
            artist_name=artist.name if artist else "",
            years_since=max(years, 1),
            release_year=rel_year,
            track_titles=track_titles,
            context=ctx,
            today=today,
        )

    if p.kind == "anniversary":
        kind = "death" if p.source_type == "robe-death" else "birth"
        if kind == "death":
            years = today.year - 2025
        else:
            years = today.year - 1962
        robe = db.execute(
            select(Artist).where(Artist.slug == "robe")
        ).scalar_one_or_none()
        label = "su muerte (diciembre de 2025)" if kind == "death" else "su nacimiento"
        if robe:
            deep = _deep_body(
                db, entity_type="artist", entity=robe,
                framing=(
                    f"Efeméride: {max(years,1)} años de {label} de Robe. Repasa hechos "
                    "biográficos y de su obra CONCRETOS y datados (discos, canciones, "
                    "momentos), citando lo verídico. Nada de loas genéricas."
                ),
                tier=_tier, serp_guidance=_serp,
            )
            if deep:
                return deep
        try:
            ctx = artist_context(db, robe.id) if robe else ""
        except Exception:
            ctx = ""
        return generate_anniversary(
            kind, person_name=ROBE, years_since=max(years, 1),
            context=ctx, today=today,
        )

    if p.kind == "evergreen":
        if p.source_type == "seo":
            # Los evergreen keyword-driven no tienen entidad asignada, pero casi
            # siempre GIRAN en torno a una (persona, banda/proyecto, Robe, disco,
            # tema…). Si podemos anclarlos a ella con confianza, los generamos con
            # el MOTOR PROFUNDO (adiós one-shot flaco); si no, one-shot clásico.
            deep = _deep_seo_evergreen(db, p, tier=_tier, serp=_serp)
            if deep:
                return deep
            return generate_seo_article(
                title=p.title,
                angle=p.angle,
                keywords=p.keywords or [],
                today=today,
            )
        # Evergreen anclado a una PERSONA/ARTISTA/BANDA (p.ej. "frases icónicas de
        # Robe"): motor profundo sobre esa entidad, con el ángulo del título.
        ent_model = {"artist": Artist, "person": Person, "band": Band}.get(
            p.source_type or ""
        )
        if ent_model and p.source_id:
            ent = db.get(ent_model, p.source_id)
            if ent:
                name = getattr(ent, "name", "") or p.title
                deep = _deep_body(
                    db, entity_type=p.source_type, entity=ent,
                    framing=(
                        f"{p.title}. Pieza a fondo sobre {name}, anclada al corpus: "
                        "hechos y versos REALES (los versos, copiados LITERAL del "
                        "material [LETRA]; nunca inventes un verso ni lo atribuyas a una "
                        "canción sin tener su letra). Concreto y con sustancia, nada genérico."
                    ),
                    tier=_tier, serp_guidance=_serp,
                )
                if deep:
                    return deep

        model = {"theme": Theme, "place": Place, "concept": Concept}.get(
            p.source_type or ""
        )
        if model and p.source_id:
            tax = db.get(model, p.source_id)
            if tax:
                deep = _deep_body(
                    db, entity_type=p.source_type, entity=tax,
                    framing=(
                        f"Tema de fondo: «{tax.name}» en la obra de Robe/Extremoduro. "
                        "CITA versos textuales concretos donde aparece (copiados LITERAL "
                        "del material [LETRA]; nunca inventes un verso ni lo atribuyas a "
                        "una canción sin tener su letra) e ilústralo con canciones y "
                        "hechos reales. Nada de divagación genérica."
                    ),
                    tier=_tier, serp_guidance=_serp,
                )
                if deep:
                    return deep
                try:
                    song_ids = [s.id for s in tax.songs]
                    seo_tax = db.execute(
                        select(SeoContent).where(
                            SeoContent.entity_type == p.source_type,
                            SeoContent.entity_id == tax.id,
                        )
                    ).scalar_one_or_none()
                    ctx = taxonomy_context(
                        db, song_ids, seo_tax.body_md if seo_tax else None
                    )
                except Exception:
                    ctx = ""
                return generate_evergreen_topic(
                    taxonomy_kind=p.source_type,
                    taxonomy_name=tax.name,
                    taxonomy_description=tax.description,
                    song_titles=[s.title for s in tax.songs],
                    context=ctx,
                    today=today,
                )
        return None

    return None


def _post_process(db, body_md: str, entities: list, subject: str = "",
                  title: str = "") -> tuple[str, dict | None]:
    """Aplica hero ÚNICO (foto del sujeto sin repetir, o arte IA) + saneado anti-IA
    + jerarquía de headings + enlazado interno automático. Devuelve (body_md, hero|None)."""
    from app.services.blog_hero import build_unique_hero
    from app.services.entity_resolver import (
        autolink_corpus,
        build_corpus_index,
        load_link_stats,
    )
    from app.services.lyric_guard import complete_verses
    from app.services.text_sanitizer import normalize_headings, strip_ai_tells

    hero = build_unique_hero(db, entities or [], subject, alt_label=title or subject)
    # Lo que admite no saber no informa (source_guard.quitar_confesiones): el
    # 10-11-2026 un borrador traía «El material no detalla el programa…».
    from app.services import source_guard
    body_md, _confesiones = source_guard.quitar_confesiones(body_md)
    body_md, _metatexto = source_guard.quitar_metatexto(body_md)
    # Versos citados SIEMPRE completos: expande cada cita a la línea real del corpus.
    body_md = complete_verses(db, body_md) or body_md
    body_md = strip_ai_tells(body_md) or body_md
    body_md = normalize_headings(body_md) or body_md
    # Embebe vídeos referenciados como enlace markdown (URL desnuda → reproductor).
    from app.services.text_sanitizer import embed_youtube_links
    body_md = embed_youtube_links(body_md) or body_md
    body_md = autolink_corpus(
        body_md, build_corpus_index(db), link_stats=load_link_stats()
    )
    return body_md, hero


def enlazar_ficha_del_disco(body_md: str, titulo: str, ruta: str) -> str:
    """Enlaza la PRIMERA mención del disco a su ficha, si el cuerpo no la enlaza ya.

    Criterio de David (18-11-2026): un post sobre algo con ficha enlaza a la ficha, para
    no canibalizarla. Sin esto, el aniversario de «Destrozares» enlazaba el título del
    disco a la canción homónima: el autoenlazador busca el título largo con sus
    mayúsculas, no lo encontraba en minúscula y ganaba la canción."""
    import re

    if not body_md or not titulo or f"]({ruta})" in body_md:
        return body_md
    corto = titulo.split(",")[0].strip()
    for nombre in dict.fromkeys((titulo, corto)):
        if len(nombre) < 3:
            continue
        # Fuera de un enlace ya hecho y de un heading.
        for m in re.finditer(r"(?<![\w\[])" + re.escape(nombre) + r"(?![\w\]])", body_md, re.I):
            linea_ini = body_md.rfind("\n", 0, m.start()) + 1
            if body_md[linea_ini:linea_ini + 1] == "#":
                continue
            antes = body_md[:m.start()]
            if antes.count("[") > antes.count("]"):
                continue
            return f"{antes}[{m.group(0)}]({ruta}){body_md[m.end():]}"
    return body_md


def _collect_videos(db, p: ContentProposal) -> None:
    """Consolida `p.videos` (lista). En premium/flagship añade vídeos REALES
    relacionados de la entidad (oficial/directo/entrevista) y los embebe en el
    cuerpo; cada uno emite su VideoObject en el schema. Best-effort."""
    videos: list[dict] = []
    seen: set[str] = set()
    if getattr(p, "video", None) and p.video.get("youtube_id"):
        videos.append(p.video)
        seen.add(p.video["youtube_id"])
    tier = getattr(p, "quality_tier", None) or "standard"
    if tier in ("premium", "flagship", "cornerstone"):
        try:
            from sqlalchemy import select

            from app.db.models import RelatedVideo, RelatedVideoEntity
            slugs = [e["slug_hint"] for e in (p.entities or []) if e.get("slug_hint")]
            if slugs:
                limit = {"cornerstone": 4, "flagship": 3}.get(tier, 2)
                rows = db.execute(
                    select(RelatedVideo)
                    .join(RelatedVideoEntity, RelatedVideoEntity.video_id == RelatedVideo.id)
                    .where(RelatedVideoEntity.entity_slug.in_(slugs))
                    .limit(10)
                ).scalars().all()
                added = 0
                for rv in rows:
                    if added >= limit or rv.youtube_id in seen:
                        continue
                    seen.add(rv.youtube_id)
                    added += 1
                    videos.append({
                        "youtube_id": rv.youtube_id, "title": rv.title,
                        "upload_date": rv.upload_date.isoformat() if rv.upload_date else None,
                        "channel": None,
                    })
                    p.body_md = (p.body_md or "").rstrip() + (
                        f"\n\nhttps://www.youtube.com/watch?v={rv.youtube_id}\n"
                    )
                if added:
                    logger.info("draft: %d vídeo(s) relacionado(s) en propuesta %s (%s)",
                                added, p.id, tier)
        except Exception as exc:  # noqa: BLE001 — multimedia es opcional
            logger.warning("draft: vídeos relacionados fallaron: %s", exc)
    if videos:
        p.videos = videos
        if not getattr(p, "video", None):
            p.video = videos[0]


def generate_proposal_draft(db, p: ContentProposal, *, persist: bool = True,
                            juzgar: bool = True) -> bool:
    """Construye el borrador completo de la propuesta y lo guarda en ella
    (body_md + excerpt + meta + hero + entities). Devuelve True si quedó listo.

    Pensado para invocarse al aprobar (en background) y como red de seguridad
    desde el cron `generate_approved_drafts` y desde `materialize_proposals`.

    `persist`: si False, NO hace commit/refresh finales — para regenerar sobre una
    propuesta TRANSITORIA (no persistida) sin chocar con constraints ni dejar filas
    sueltas; el caller lee los campos en memoria (p.ej. regen_entity_post)."""
    # 0. Engagement: score + tier (modula extensión/profundidad/multimedia y activa
    #    el brief de competencia SERP en premium/flagship). Se calcula antes del
    #    cuerpo para que generate_body lo lea.
    if not p.quality_tier:
        try:
            from app.services.engagement import compute_for_proposal, content_tier
            score, tier = compute_for_proposal(db, p)
            p.engagement_score = score
            # Política: no-noticias con SUELO flagship; temáticas de alto engagement
            # → cornerstone. Las noticias mantienen su tier por actualidad.
            p.quality_tier = content_tier(p.kind, score, tier, p.source_type)
            logger.info("draft: propuesta %s → engagement %s (%s)",
                        p.id, p.engagement_score, p.quality_tier)
        except Exception as exc:  # noqa: BLE001
            logger.warning("draft: engagement falló: %s", exc)

    # 1. Cuerpo: el que ya trae (news) o generado por kind. Si una persona pidió
    #    reescribir con una nota (panel), la nota le llega al redactor como corrección.
    if not p.body_md:
        razones = getattr(p, "review_reasons", None)
        nota = razones.get("nota") if isinstance(razones, dict) else None
        token = _CORRECCIONES.set(f"Nota del editor: {nota}") if nota else None
        try:
            payload = generate_body(db, p)
        finally:
            if token is not None:
                _CORRECCIONES.reset(token)
        if payload is None:
            logger.error("draft: no se pudo generar body para propuesta %s", p.id)
            return False
        from app.services.catalog_ideas import entidad_de as _ent
        # Una idea de catálogo conserva SU título: es el ángulo que la separa de la ficha
        # (no canibalizar). El modelo lo cambiaba por uno suyo (asesor, 18-11-2026).
        if _ent(p.source_type) is None:
            p.title = (payload.get("title") or p.title)[:240]
        p.excerpt = payload.get("excerpt")
        p.body_md = payload["body_md"]
        p.meta_title = (p.title[:60] if _ent(p.source_type) else (payload.get("meta_title") or None))
        p.meta_description = (payload.get("meta_description") or None)
        p.entities = payload.get("entities") or []

    # 1a. Si ya tenía vídeo (una reescritura vacía el cuerpo), se vuelve a embeber:
    #     la versión final de «Destrozares» salía con `p.video` y sin el reproductor.
    vid_previo = getattr(p, "video", None)
    if vid_previo and vid_previo.get("youtube_id") and vid_previo["youtube_id"] not in (p.body_md or ""):
        p.body_md = (p.body_md or "").rstrip() + (
            f"\n\nhttps://www.youtube.com/watch?v={vid_previo['youtube_id']}\n")

    # 1b. Best-effort VÍDEO: si la propuesta no trae vídeo (kinds no-news), buscar
    #     uno claramente del tema y embeberlo (URL desnuda → reproductor + VideoObject).
    if not getattr(p, "video", None):
        try:
            from app.services.news_research import find_video
            subject = (p.target_keyword or p.title or "").strip()
            vid = find_video(subject, subject) if subject else None
            if vid:
                p.video = vid
                p.body_md = (p.body_md or "").rstrip() + (
                    f"\n\nhttps://www.youtube.com/watch?v={vid['youtube_id']}\n"
                )
                logger.info("draft: vídeo añadido a propuesta %s", p.id)
        except Exception as exc:  # noqa: BLE001 — el vídeo es opcional
            logger.warning("draft: búsqueda de vídeo falló: %s", exc)

    # 1c. Multimedia enriquecida: consolida la lista `videos` y, en premium/flagship,
    #     añade vídeos REALES relacionados de la entidad (oficial/directo/entrevista).
    _collect_videos(db, p)

    # 2. Post-procesado (hero ÚNICO + saneado + enlazado). El aniversario de un disco
    #    enlaza primero a la ficha del disco (no canibalizarla).
    from app.services.catalog_ideas import entidad_de as _entidad_de
    _cat = _entidad_de(p.source_type)
    if p.source_id and ((p.kind == "album-anniversary" and p.source_type == "album")
                        or (_cat is not None and _cat[0] == "album")):
        album = db.get(Album, p.source_id)
        artista = db.get(Artist, album.artist_id) if album else None
        if album and artista:
            p.body_md = enlazar_ficha_del_disco(p.body_md, album.title,
                                                f"/{artista.slug}/{album.slug}")
    subject = (p.target_keyword or p.title or "").strip()
    body_md, hero = _post_process(db, p.body_md, p.entities or [], subject, title=p.title)
    p.body_md = body_md
    if hero:
        from app.services.hero_io import apply_hero
        apply_hero(p, hero)  # los 5 campos juntos, sin desincronizar
    if p.meta_title:
        p.meta_title = p.meta_title[:60]
    if p.meta_description:
        p.meta_description = p.meta_description[:155]

    # 3. Juicio al preparar: la cascada del día de publicar, ahora y no el día D.
    if juzgar:
        try:
            juzgar_borrador(db, p)
        except Exception as exc:  # noqa: BLE001 — el juicio no tumba el borrador
            logger.warning("draft: el juicio de la propuesta %s falló: %s", p.id, exc)

    if persist:
        db.commit()
        db.refresh(p)
        logger.info("draft listo para propuesta %s (%s)", p.id, p.kind)
    return True


# --------------------------------------------------------------------------- #
# Juicio al preparar (plan del blog, 18-11-2026)
# --------------------------------------------------------------------------- #
def hechos_de_propuesta(db, p: ContentProposal) -> str:
    """Los hechos duros de la entidad de la propuesta, para el juez y el listón."""
    from app.services.catalog_ideas import entidad_de
    from app.services.deep_research import _hard_facts, entity_names

    tipo, entidad = None, None
    cat = entidad_de(p.source_type)
    if cat and p.source_id:
        tipo, entidad = cat[0], _entidad_catalogo(db, cat[0], p.source_id)
    elif p.kind == "album-anniversary" and p.source_type == "album" and p.source_id:
        tipo, entidad = "album", db.get(Album, p.source_id)
    elif p.kind == "spotlight" and p.source_type == "song" and p.source_id:
        tipo, entidad = "song", db.get(Song, p.source_id)
    if entidad is None:
        return ""
    try:
        sujeto, _ = entity_names(db, tipo, entidad)
        return _hard_facts(db, tipo, entidad, sujeto)
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft: hechos duros de la propuesta %s: %s", p.id, exc)
        return ""


def material_propio_de_propuesta(db, p: ContentProposal) -> str:
    """Fichas publicadas y letras de la entidad de la propuesta (lo que el fact-check
    puede dar por bueno sin ir a la web)."""
    from app.services.catalog_ideas import entidad_de

    cat = entidad_de(p.source_type)
    es_disco = (p.kind == "album-anniversary" and p.source_type == "album") or (
        cat is not None and cat[0] == "album")
    if es_disco and p.source_id:
        al = db.get(Album, p.source_id)
        if al:
            return "\n\n".join(x for x in (_fichas_propias(db, "album", al),
                                            _letras_del_disco(db, "album", al)) if x)
    if cat is not None and cat[0] == "song" and p.source_id:
        so = db.get(Song, p.source_id)
        if so:
            return _fichas_propias(db, "song", so) + "\n\n" + (so.lyrics_clean or "")
    if p.kind == "spotlight" and p.source_type == "song" and p.source_id:
        so = db.get(Song, p.source_id)
        if so:
            return _fichas_propias(db, "song", so) + "\n\n" + (so.lyrics_clean or "")
    return ""


def _juzgar(db, p: ContentProposal, hard: str):
    from app.services.blog_gates import cascada_en_seco

    return cascada_en_seco(db, kind=p.kind, subject=(p.target_keyword or p.title or "").strip(),
                           title=p.title or "", body_md=p.body_md or "", hard_facts=hard,
                           tipo_pieza=tipo_pieza_de(p),
                           material_propio=material_propio_de_propuesta(db, p))


def _corta(p: ContentProposal) -> bool:
    """¿Pieza con listón que no llega al mínimo? Solo cuenta el texto, no los vídeos."""
    import re

    from app.services.piece_checklist import LISTAS

    if tipo_pieza_de(p) not in LISTAS:
        return False
    texto = re.sub(r"(?m)^https?://\S+\s*$", "", p.body_md or "")
    return len(texto.strip()) < MIN_CUERPO_CON_LISTON


def juzgar_borrador(db, p: ContentProposal, *, reescribir: bool = True):
    """Pasa la cascada ENTERA en seco sobre el borrador y guarda el veredicto.

    Si no pasa por rigor, foco o voz, se reescribe con los motivos delante, hasta
    `MAX_REESCRITURAS` veces, y se queda la mejor versión. Lo que sigue sin pasar queda
    `retenida` con su motivo: no se programa ni se descarta en silencio (David,
    18-11-2026: que pase, y retener es el último recurso). Las noticias no pasan por
    aquí: su comprobación es contra su artículo, en `materialize_proposals`."""
    if p.kind == "news" or not (p.body_md or "").strip():
        return None
    hard = hechos_de_propuesta(db, p)
    intentos = 1
    corta = _corta(p)
    if corta and reescribir:
        # Antes de juzgar: lo que falta es material, no estilo.
        previo = {k: getattr(p, k) for k in
                  ("title", "excerpt", "body_md", "meta_title", "meta_description", "entities")}
        token = _BUSQUEDA_AMPLIA.set(True)
        try:
            p.body_md = None
            ok = generate_proposal_draft(db, p, persist=False, juzgar=False)
        finally:
            _BUSQUEDA_AMPLIA.reset(token)
        intentos += 1
        antes = len((previo["body_md"] or "").strip())
        if not ok or len((p.body_md or "").strip()) <= antes:
            for k, v in previo.items():
                setattr(p, k, v)
        logger.info("draft: propuesta %s corta (%d car.): búsqueda amplia → %d car.",
                    p.id, antes, len((p.body_md or "").strip()))
        corta = _corta(p)
    juicio = _juzgar(db, p, hard)
    if corta and juicio.pasa:
        # Pasa todos los filtros pero no da para un post: no sale sola.
        from app.services.blog_gates import Juicio
        juicio = Juicio(False, "material", [
            f"se queda en {len((p.body_md or '').strip())} caracteres tras verificar: no hay "
            "material afirmable para más (lo que solo contaban terceros sin corroborar se "
            "quitó)"], juicio.score, juicio.cuerpo)
    while (not corta and not juicio.pasa and reescribir and intentos <= MAX_REESCRITURAS
           and juicio.bloquea in ("rigor", "foco", "fuentes", "completeness")):
        # Solo los motivos de ESTILO van al redactor. Pedirle «falta el sello» sin
        # material nuevo le enseña a esquivar o a inventar (asesor, 18-11-2026): los
        # datos se buscan antes de escribir (`_buscar_lo_que_falta`), no se reclaman aquí.
        estilo = [m for m in juicio.motivos if m not in juicio.faltan_datos]
        if not estilo:
            break
        previo = {k: getattr(p, k) for k in
                  ("title", "excerpt", "body_md", "meta_title", "meta_description", "entities")}
        token = _CORRECCIONES.set("; ".join(estilo)[:1500])
        try:
            p.body_md = None
            ok = generate_proposal_draft(db, p, persist=False, juzgar=False)
        finally:
            _CORRECCIONES.reset(token)
        intentos += 1
        if not ok:
            for k, v in previo.items():
                setattr(p, k, v)
            break
        nuevo = _juzgar(db, p, hard)
        logger.info("draft: propuesta %s reescrita (%d): %s → %s", p.id, intentos - 1,
                    juicio.score, nuevo.score)
        # Se queda la nueva si pasa, o si la frena el MISMO filtro con mejor nota: la
        # nota de dos filtros distintos no se compara.
        if nuevo.pasa or (nuevo.bloquea == juicio.bloquea
                          and (nuevo.score or 0) > (juicio.score or 0)):
            juicio = nuevo
        else:
            for k, v in previo.items():
                setattr(p, k, v)
    if juicio.cuerpo and reescribir:
        # Con el recorte del foco y el tensado del juez. Con `reescribir=False` (el backlog
        # del cron) no se toca el texto: solo se juzga (es lo que se le dijo a David).
        # TAMBIÉN si no pasa: lo que David lee en «para tu lectura» tiene que ser lo que se
        # juzgó. El 18-11-2026 la #417 se juzgó sin las secciones que el foco recortó y se
        # guardó entera, con cinco menciones a Mondo Sonoro que la voz propia habría parado.
        p.body_md = juicio.cuerpo
    # Pieza CENTRAL que solo frena el juez de rigor, y en la frontera: la decide David
    # (18-11-2026: «buscar la recepción y que decidas tú»). Su lectura es el filtro final.
    para_ti = (not juicio.pasa and juicio.bloquea == "rigor" and p.kind in PIEZAS_CENTRALES
               and (juicio.score or 0) >= UMBRAL_PARA_TU_LECTURA)
    p.review_verdict = "pasa" if juicio.pasa else ("para_tu_lectura" if para_ti else "retenida")
    p.review_score = juicio.score
    p.review_reasons = juicio.to_dict()
    p.reviewed_at = datetime.now(UTC)
    p.review_attempts = intentos
    logger.info("draft: propuesta %s %s (score %s, %d intento/s)%s", p.id, p.review_verdict,
                juicio.score, intentos,
                "" if juicio.pasa else f" — {juicio.bloquea}: {'; '.join(juicio.motivos)[:200]}")
    return juicio
