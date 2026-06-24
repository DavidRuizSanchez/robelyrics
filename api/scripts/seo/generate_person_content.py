"""Genera contenido SEO para páginas de Persona (miembros, líderes amigos).

Inserta en `seo_content` con entity_type='person'. Estructura ~2500 palabras
con secciones que aprovechan los datos de `band_memberships` para conectar
con las páginas existentes de los Artists.

Schema.org Person con memberOf hacia MusicGroup (Extremoduro/Robe) y
sameAs hacia Wikipedia + Wikidata. El @id canónico se usa luego desde el
helper de Next.js para que el @graph del sitio se interconecte.

Uso:
    python -m scripts.seo.generate_person_content --slug robe-iniesta
    python -m scripts.seo.generate_person_content --all
    python -m scripts.seo.generate_person_content --all --force
"""
from __future__ import annotations

import argparse

from openai import OpenAI
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Album, Artist, BandMembership, Person
from app.services.voice import build_system_prompt
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_sources_for_entity,
    format_sources_block,
    upsert_seo_content,
)


SITE_URL = "https://entreinteriores.com"

# REFERENCIAS CULTURALES: personas CITADAS en las letras de Robe/Extremoduro
# (toreros, músicos ajenos al universo, iconos), NO músicos de la banda ni de su
# círculo. Su ficha NO debe usar la estructura de músico ("entrada en la banda",
# "química con Robe"), que es absurda para un torero o un músico extranjero. Para
# ellas se usa una estructura propia centrada en CÓMO las cita Robe.
# Añade aquí futuras referencias culturales que aparezcan en las letras.
REFERENCE_SLUGS = {"manolete", "camaron", "frank-zappa", "freddie-mercury"}


def _display_name(person: Person) -> str:
    """Nombre con el que nos referimos a la persona en el texto."""
    if person.stage_name and person.stage_name != person.full_name:
        return person.stage_name
    return person.full_name


def _tense_guidance(person: Person) -> str:
    """Instrucción de TIEMPO VERBAL según conste o no el fallecimiento. Evita el
    error de escribir 'fue un músico' de alguien que sigue vivo (no consta
    muerto) y, a la vez, el de hablar en presente de un fallecido."""
    if person.death_date:
        return (
            f"ESTADO: consta FALLECIDO el {person.death_date.isoformat()}. "
            "Habla de su vida y su obra en pasado, con respeto y sin morbo."
        )
    return (
        "ESTADO: NO consta su fallecimiento. Refiérete a la persona en PRESENTE "
        "('es músico', 'toca', 'sigue en activo'). Usa el pasado SOLO para "
        "etapas concretas ya cerradas (p.ej. 'fue bajista de X entre 1990 y "
        "1993'). PROHIBIDO escribir 'fue un músico' o tratarlo como difunto: no "
        "consta que haya muerto."
    )


def _wikidata_refs_block(person: Person) -> str:
    """Datos estructurados de Wikidata (hoy ignorados por el generador). Son la
    munición concreta contra la vaguedad: bandas, obras, instrumentos, oficios."""
    lines: list[str] = []
    if person.other_bands:
        lines.append("Otras bandas/proyectos (Wikidata): "
                     + ", ".join(b["name"] for b in person.other_bands))
    if person.notable_works:
        lines.append("Obras destacadas: "
                     + ", ".join(w["name"] for w in person.notable_works))
    if getattr(person, "instruments", None):
        lines.append("Instrumentos: "
                     + ", ".join(i["name"] for i in person.instruments))
    if person.occupations:
        lines.append("Oficios: " + ", ".join(o["name"] for o in person.occupations))
    return "\n".join(lines) or "(sin datos estructurados de Wikidata)"


def _names_for_search(person: Person) -> list[str]:
    out = [person.full_name]
    if person.stage_name and person.stage_name != person.full_name:
        out.append(person.stage_name)
    return out


def _person_summary(person: Person, memberships: list[BandMembership]) -> str:
    parts = []
    if person.stage_name and person.stage_name != person.full_name:
        parts.append(f"{person.full_name} (conocido como {person.stage_name})")
    else:
        parts.append(person.full_name)
    if person.birth_date:
        parts.append(f"nacido el {person.birth_date.isoformat()}")
    if person.birth_place:
        parts.append(f"en {person.birth_place}")
    if person.death_date:
        parts.append(f"fallecido el {person.death_date.isoformat()}")
    if memberships:
        roles = ", ".join(
            f"{m.role} de {m.artist.name} ({m.era or 'era sin documentar'})"
            for m in memberships
        )
        parts.append(roles)
    return ". ".join(parts) + "."


def _build_reference_prompt(person: Person, sources: list[dict] | None = None) -> str:
    """Prompt para REFERENCIAS CULTURALES (personas citadas en las letras, NO
    músicos del universo). El protagonista del texto es la CONEXIÓN con Robe, no
    una biografía completa: quién es la figura (breve y veraz), cómo y dónde la
    cita Robe/Extremoduro, y por qué resuena en su universo.
    """
    name = _display_name(person)
    summary = _person_summary(person, [])
    bio = (person.bio_long or person.bio_short or "(sin biografía documentada)")[:6000]
    refs = _wikidata_refs_block(person)
    fan_block = format_sources_block(sources or [])
    kw = person.full_name
    if person.stage_name and person.stage_name != person.full_name:
        kw += f" / {person.stage_name}"

    return f"""\
Escribe un artículo editorial de 700 a 1000 palabras sobre {name} como REFERENCIA
CULTURAL citada en la obra de Robe Iniesta y Extremoduro. {name} NO es músico de
Extremoduro ni de su banda: es una figura a la que Robe alude en sus letras. El
PROTAGONISTA del texto es la CONEXIÓN con Robe/Extremoduro, no una biografía
completa de {name}.

DATOS VERIFICADOS:
{summary}

{_tense_guidance(person)}

FICHA DE WIKIPEDIA (fuente de datos CONCRETOS sobre {name}; parafrasea, no copies;
úsala para situar quién es en su campo —flamenco, rock, toreo…—):
{bio}

DATOS ESTRUCTURADOS (Wikidata) — nómbralos explícitamente, no los resumas:
{refs}

QUÉ DICEN LAS FUENTES (libros, entrevistas, prensa, fan-content; aquí está la
munición sobre CÓMO y DÓNDE cita Robe a {name} —canción, verso, contexto—;
úsalo, contrasta, no copies literal):
{fan_block}

KW OBJETIVO: «{kw}». Colócala al INICIO del meta_title, en la meta_description y
en el primer párrafo, con naturalidad. KWs secundarias: Robe, Extremoduro y las
canciones donde aparece la figura.

ESTRUCTURA OBLIGATORIA (encabezados H2 concretos, EN ESTE ORDEN):

## Quién fue/es {name}
~150 palabras: quién es en su campo (flamenco, rock, toreo…), breve y veraz.
Tiempo verbal según el ESTADO indicado arriba (si consta fallecido, en pasado;
si no, en presente). Solo lo que conste; nada de relleno biográfico.

## {name} en la obra de Robe
~400 palabras: CÓMO y DÓNDE lo cita Robe/Extremoduro. ¿En qué canción aparece?
¿En qué verso o contexto? ¿Qué significa esa mención? Apóyate en las fuentes de
arriba. Si el detalle (canción concreta, verso) NO consta en los datos o las
fuentes, DILO con honestidad; NO inventes en qué tema aparece ni qué dice el
verso. Mejor reconocer la penumbra que fabricar una cita.

## Por qué resuena en el universo Extremoduro
~250 palabras: la afinidad estética y vital. Qué representa esa figura para Robe
(autenticidad, tragedia, libertad, oficio…), por qué encaja en su imaginario.
Conjetura razonada SÍ, pero sin atribuir a Robe declaraciones que no consten.

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final.
- NO INVENTES datos: ni canciones, ni versos, ni declaraciones de Robe.
- NO escribas links markdown a mano. El sistema linkifica los nombres detectados.

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_low_data_prompt(
    person: Person, memberships: list[BandMembership], primary_band: str | None
) -> str:
    """Prompt para figuras POCO DOCUMENTADAS (miembros históricos sin
    biografía ni artículo de Wikipedia). Forzar 2000 palabras sobre alguien
    de quien casi no hay datos lleva al LLM a inventar. Aquí se pide un
    artículo más corto y centrado en CONTEXTO real (la etapa de la banda),
    no en una biografía personal que no existe.
    """
    summary = _person_summary(person, memberships)
    name = _display_name(person)
    band = primary_band or "su banda"
    return f"""\
Escribe un artículo editorial de 700 a 1000 palabras sobre {name}.

DATOS VERIFICADOS (lo ÚNICO que consta con certeza):
{summary}

{_tense_guidance(person)}

ESTA PERSONA ESTÁ POCO DOCUMENTADA. No hay biografía pública detallada suya.
Por eso:
- NO inventes fecha ni lugar de nacimiento, anécdotas, declaraciones, otros
  grupos, vida personal ni nada que no esté en los datos verificados.
- Si un dato no consta, NO lo escribas. No rellenes con conjeturas.
- El protagonista es {name}, no Robe ni la banda: el grupo es el contexto, pero
  céntrate en situar a ESTA persona con rigor. Mejor corto y veraz que largo y
  especulativo.

ESTRUCTURA OBLIGATORIA (encabezados H2 concretos, con sustantivos del tema):

## Quién es {name}
~200 palabras: quién es, su rol e instrumento exactos, la etapa en que estuvo en
{band} y qué lugar ocupa. (Si consta fallecido, en pasado; si no, en presente.)

## Su paso por {band}
~300 palabras: qué hizo concretamente en el grupo, en qué periodo, los cambios
de formación alrededor de su entrada y su salida. Céntrate en SU papel, no en la
historia general de la banda.

## Los discos y el sonido de su etapa
~200 palabras: en qué discos participó o qué preparaba {band} mientras estuvo, y
cómo sonaba su aportación. Menciona títulos de discos en texto plano.

## Lo documentado y lo que queda en penumbra
~150 palabras: reconoce con honestidad qué se sabe y qué no de esta figura.

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final.
- NO escribas links markdown a mano. El sistema linkifica solo.

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_prompt(
    person: Person, memberships: list[BandMembership], sources: list[dict] | None = None
) -> str:
    # REFERENCIAS CULTURALES: rama propia ANTES de la decisión low-data/rico. Una
    # figura citada en las letras (torero, músico ajeno) no tiene "entrada en la
    # banda" ni "química con Robe"; su ficha gira en torno a CÓMO la cita Robe.
    if person.slug in REFERENCE_SLUGS:
        return _build_reference_prompt(person, sources)

    summary = _person_summary(person, memberships)
    band_list = ", ".join(m.artist.name for m in memberships) or "(sin memberships en el corpus)"
    # bio_long = artículo completo de Wikipedia (datos concretos). Es la clave
    # contra la vaguedad. Cae a bio_short si no hay.
    bio = (person.bio_long or person.bio_short or "(sin biografía documentada)")[:9000]
    refs = _wikidata_refs_block(person)
    fan_block = format_sources_block(sources or [])
    primary_band = memberships[0].artist.name if memberships else None
    kw = person.full_name
    if person.stage_name and person.stage_name != person.full_name:
        kw += f" / {person.stage_name}"
    if primary_band:
        kw += f" ({primary_band})"

    # Figuras poco documentadas: sin biografía (ni corta ni larga), sin artículo
    # de Wikipedia Y sin fuentes que las mencionen. Si hay fuentes curadas
    # (reference_sources, prensa, fan-content), usamos el prompt rico que SÍ las
    # aprovecha; solo cuando no hay NADA caemos al prompt honesto y corto.
    if not person.bio_short and not person.bio_long and not person.wikipedia_url \
            and not sources:
        return _build_low_data_prompt(person, memberships, primary_band)

    name = _display_name(person)
    band = primary_band or "su banda"

    return f"""\
Escribe un artículo de 1500-2200 palabras sobre {name}{(', músico de ' + primary_band) if primary_band else ''}.

DATOS VERIFICADOS:
{summary}

{_tense_guidance(person)}

FICHA DE WIKIPEDIA (fuente principal de datos CONCRETOS; parafrasea, no copies;
extrae de aquí nombres de bandas, discos, años, instrumentos, hechos):
{bio}

DATOS ESTRUCTURADOS (Wikidata) — nómbralos explícitamente, no los resumas como
"varias bandas":
{refs}

QUÉ DICEN LAS FUENTES (libros, entrevistas, prensa, fan-content que mencionan a
{name}; úsalo para datos, matices y anécdotas; contrasta, no copies literal):
{fan_block}

BANDAS EN NUESTRO SITIO (se enlazan a su página local; menciónalas por nombre):
{band_list}

KW OBJETIVO: «{kw}». Colócala al INICIO del meta_title, en la meta_description y
en el primer párrafo, con naturalidad. KWs secundarias: sus instrumentos y los
nombres concretos de sus bandas y discos.

FOCO: el protagonista es {name}, no Robe. Robe y {band} son el contexto que
explica por qué importa, pero el centro del texto es ÉL/ELLA: su valía propia.

ESTRUCTURA OBLIGATORIA (H2 concretos, en este orden):

## Quién es {name}
~250 palabras: quién es, qué instrumento toca y qué papel cumple, de dónde sale y
por qué merece ficha propia. Tiempo verbal según el ESTADO indicado arriba.

## Orígenes e influencias
~350 palabras: de dónde viene como músico, primeras bandas o formación, qué le
marca. Solo lo que conste; si no hay datos de infancia/formación, dilo honesto y
corto, NO inventes.

## La entrada en {band} y la química con Robe
~450 palabras: cómo se cruzó su camino con {band} (audición, llamada o
recomendación si consta), en qué periodo y cómo encaja con Robe y el resto.
Céntrate en SU papel, no en la historia general de la banda.

## Aportación al sonido: estilo, equipo y discos
~450 palabras: qué aporta al sonido (estilo de ejecución, instrumento, equipo o
guitarras si consta) y en qué discos y canciones grabó, con TÍTULO + AÑO + su rol
concreto. Nombra, no generalices ("varios discos" está prohibido).

## Proyectos paralelos y carrera propia
~300 palabras: otras bandas o proyectos suyos (antes, durante o después), con
nombres y años. Si sigue en activo, dilo en PRESENTE y con qué proyecto. Cierra
situando su huella concreta, sin frases de relleno.

IMPORTANTE:
- NO uses placeholders entre corchetes. Si no tienes un dato, omite la frase.
- NO INVENTES datos. Si no consta fecha, instrumento, productor, etc., omítelo.
- NO escribas links markdown a mano. El sistema linkifica los nombres detectados.

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_schema(person: Person, memberships: list[BandMembership]) -> dict:
    same_as = []
    if person.wikipedia_url:
        same_as.append(person.wikipedia_url)
    if person.wikidata_id:
        same_as.append(f"https://www.wikidata.org/wiki/{person.wikidata_id}")

    member_of = [
        {
            "@type": "MusicGroup",
            "@id": f"{SITE_URL}/{m.artist.slug}#musicgroup",
            "name": m.artist.name,
            "url": f"{SITE_URL}/{m.artist.slug}",
        }
        for m in memberships
    ]

    schema: dict = {
        "@context": "https://schema.org",
        "@type": "Person",
        "@id": f"{SITE_URL}/personas/{person.slug}#person",
        "name": person.full_name,
        "url": f"{SITE_URL}/personas/{person.slug}",
    }
    if person.stage_name and person.stage_name != person.full_name:
        schema["alternateName"] = person.stage_name
    if person.birth_date:
        schema["birthDate"] = person.birth_date.isoformat()
    if person.death_date:
        schema["deathDate"] = person.death_date.isoformat()
    if person.birth_place:
        schema["birthPlace"] = {"@type": "Place", "name": person.birth_place}
    if person.image_url:
        schema["image"] = person.image_url
    if same_as:
        schema["sameAs"] = same_as
    if member_of:
        schema["memberOf"] = member_of
    return schema


def generate_for_person(client: OpenAI, db, person_slug: str, *, force: bool) -> bool:
    person = db.execute(
        select(Person).where(Person.slug == person_slug)
    ).scalar_one_or_none()
    if person is None:
        log(f"persona '{person_slug}' no encontrada", "err")
        return False

    memberships = list(person.memberships)
    # Carga los artists eager para no caer en lazy fuera de session
    for m in memberships:
        _ = m.artist  # noqa

    sources = fetch_sources_for_entity(db, _names_for_search(person))
    log(f"generando persona: {person.full_name} "
        f"({len(memberships)} memberships, bio_long={'sí' if person.bio_long else 'no'}, "
        f"{len(sources)} fuentes)")
    prompt = _build_prompt(person, memberships, sources)
    # Voz propia: 3ª persona cálida y cómplice, con el músico como protagonista
    # (no Robe). Ver app/services/voice.py.
    system_prompt = build_system_prompt(
        family="seo", persona="tercera_calida", subject=_display_name(person)
    )
    try:
        out = call_llm(client, prompt, system_prompt=system_prompt, db=db)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    if not body_md or len(body_md) < 1000:
        log(f"  artículo demasiado corto ({len(body_md)} chars)", "warn")
        return False

    schema = _build_schema(person, memberships)
    upsert_seo_content(
        db,
        entity_type="person",
        entity_id=person.id,
        slug=person.slug,
        body_md=body_md,
        meta_title=out.get("meta_title"),
        meta_description=out.get("meta_description"),
        schema_jsonld=schema,
        entities=out.get("entities") or [],
        sources=sources,
        force=force,
    )
    db.commit()
    log(f"  ✓ {person.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.slug and not args.all:
        parser.error("Indica --slug X o --all")

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        if args.slug:
            generate_for_person(client, db, args.slug, force=args.force)
            return
        all_slugs = [
            s for (s,) in db.execute(select(Person.slug).order_by(Person.id)).all()
        ]
        for slug in all_slugs:
            generate_for_person(client, db, slug, force=args.force)


if __name__ == "__main__":
    main()
