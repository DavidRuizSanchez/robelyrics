"""Genera contenido SEO para páginas de Grupo/Sello (sección /grupos).

Inserta en `seo_content` con entity_type='band'. Espejo de
generate_person_content: artículo editorial con la regla "nunca inventar".
Modo low-data honesto cuando apenas hay datos (p.ej. The Flying Rebollos).

KW objetivo: el nombre del grupo + su relación con Extremoduro/Robe (intención
informacional "<grupo> banda / <grupo> y Extremoduro"). No canibaliza páginas
existentes: cada grupo es una entidad nueva sin URL previa en el corpus.

Schema.org MusicGroup (band) / Organization (label) con sameAs hacia
Wikipedia + Wikidata y @id canónico para el knowledge graph.

Uso:
    python -m scripts.seo.generate_band_content --slug marea
    python -m scripts.seo.generate_band_content --all
    python -m scripts.seo.generate_band_content --all --force
"""
from __future__ import annotations

import argparse

from openai import OpenAI
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Band
from app.services.voice import build_system_prompt
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_sources_for_entity,
    format_sources_block,
    upsert_seo_content,
)


SITE_URL = "https://entreinteriores.com"


def _band_summary(band: Band) -> str:
    parts = [band.name]
    kind_es = "sello discográfico" if band.kind == "label" else "grupo de música"
    parts.append(f"({kind_es})")
    if band.founded_year:
        parts.append(f"fundado en {band.founded_year}")
    if band.dissolved_year:
        parts.append(f"disuelto en {band.dissolved_year}")
    if band.related_note:
        parts.append("vínculo con el universo Robe/Extremoduro: "
                     + " ".join(band.related_note.split()))
    return ". ".join(parts) + "."


def _bond_heading(band: Band) -> tuple[str, str]:
    """Devuelve (encabezado_H2, instrucción) para la sección del lazo con
    Extremoduro, ramificado según band.relation_type."""
    if band.relation_type == "family":
        return (
            "## El lazo de sangre con el universo de Robe",
            "el vínculo de familia: este grupo nace de las costillas de "
            "Extremoduro (músicos, proyectos paralelos, sangre compartida del "
            "círculo de Robe). Cuéntalo como lo que es, familia del universo "
            "Extremoduro. Nombra en texto plano a la gente del entorno (Robe, "
            "Uoho, Fito…) para que se enlacen. No inventes colaboraciones que "
            "no consten.",
        )
    if band.relation_type == "friend":
        return (
            "## La trinchera compartida con Extremoduro",
            "el vínculo de escena: carretera, escenarios y festivales "
            "compartidos, respeto mutuo entre iguales del rock estatal. No es "
            "familia, son compañeros de trinchera. Nombra en texto plano a la "
            "gente del entorno (Robe, Fito, Rosendo, Kutxi…) para que se "
            "enlacen. No inventes colaboraciones que no consten.",
        )
    return (
        "## Relación con Extremoduro y Robe",
        "el vínculo documentado con el universo de Robe (escena compartida, "
        "gente en común, escenarios, carretera). Nombra en texto plano a las "
        "personas del entorno (Robe, Fito, Rosendo, Kutxi…) para que se "
        "enlacen. No inventes colaboraciones que no consten.",
    )


def _build_low_data_label_prompt(band: Band) -> str:
    """Low-data para SELLOS (kind='label'). Un sello no tiene 'componentes' ni
    'líder': tiene línea editorial y catálogo de artistas. Estructura propia."""
    summary = _band_summary(band)
    bond_heading, bond_instr = _bond_heading(band)
    return f"""\
Escribe un artículo editorial de 600 a 900 palabras sobre {band.name},
SELLO DISCOGRÁFICO, en relación con el universo de Extremoduro y Robe Iniesta.

DATOS VERIFICADOS (lo ÚNICO que consta con certeza):
{summary}

ESTE SELLO ESTÁ POCO DOCUMENTADO. No hay una historia pública sólida. Por eso:
- NO inventes fechas de fundación, fundadores, artistas, discos ni declaraciones.
- Si un dato no consta, NO lo escribas. No rellenes con conjeturas.
- El valor no es una historia completa (no la hay): es situar con rigor a
  {band.name} como sello en el contexto del rock afín a Extremoduro. Mejor corto
  y veraz que largo y especulativo.

ESTRUCTURA (encabezados H2 concretos, con sustantivos del tema):

## Qué es {band.name}
~150 palabras: qué sello es, cuándo se funda si consta, su línea editorial y qué
lugar ocupa en la industria del rock estatal.

## Catálogo y artistas
~120 palabras: qué artistas o discos publica o publicó, nómbralos en texto plano
SOLO si constan con seguridad (el sistema enlaza solo). Si el catálogo no está
documentado, dilo con honestidad. NUNCA hables de "componentes" ni "integrantes":
un sello edita a artistas, no los tiene de plantilla. NO inventes nombres.

{bond_heading}
~300 palabras: {bond_instr}

## Lo documentado y lo que queda en penumbra
~150 palabras: reconoce con honestidad qué se sabe y qué no.

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final.
- NO escribas links markdown a mano. El sistema linkifica solo.
- Menciona "Extremoduro" y "Robe" en texto plano cuando aplique (se enlazan solos).

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_low_data_prompt(band: Band) -> str:
    # Los sellos tienen estructura propia (catálogo/artistas, no componentes).
    if band.kind == "label":
        return _build_low_data_label_prompt(band)
    summary = _band_summary(band)
    bond_heading, bond_instr = _bond_heading(band)
    return f"""\
Escribe un artículo editorial de 600 a 900 palabras sobre {band.name},
en relación con el universo de Extremoduro y Robe Iniesta.

DATOS VERIFICADOS (lo ÚNICO que consta con certeza):
{summary}

ESTE GRUPO ESTÁ POCO DOCUMENTADO. No hay una biografía pública sólida. Por eso:
- NO inventes fechas, formación, discos, anécdotas ni declaraciones.
- Si un dato no consta, NO lo escribas. No rellenes con conjeturas.
- El valor no es una biografía completa (no la hay): es situar con rigor a
  {band.name} en el contexto del rock afín a Extremoduro y dar contexto útil a
  quien lo busca. Mejor corto y veraz que largo y especulativo.

ESTRUCTURA (encabezados H2 concretos, con sustantivos del tema):

## Quién es {band.name}
~150 palabras: qué es, qué lugar ocupa en la escena del rock estatal.

## Componentes
~120 palabras: nombra a los integrantes que CONSTEN con seguridad y su
instrumento/rol, en texto plano (el sistema enlaza solo). Si la formación no
está documentada, dilo con honestidad y nombra solo a quien conste (al menos
el líder). NO inventes nombres.

{bond_heading}
~300 palabras: {bond_instr}

## Lo documentado y lo que queda en penumbra
~150 palabras: reconoce con honestidad qué se sabe y qué no.

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final.
- NO escribas links markdown a mano. El sistema linkifica solo.
- Menciona "Extremoduro" y "Robe" en texto plano cuando aplique (se enlazan solos).

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_label_prompt(band: Band, sources: list[dict] | None = None) -> str:
    """Prompt rico para SELLOS (kind='label'). Estructura propia de sello
    (línea editorial + catálogo/artistas), nunca la de grupo ('componentes')."""
    summary = _band_summary(band)
    bio = (band.bio_long or band.bio_short or "(sin biografía documentada)")[:9000]
    artists_hint = ""
    if band.members:
        names = [m.get("name") if isinstance(m, dict) else str(m) for m in band.members]
        artists_hint = "ARTISTAS/DISCOS CONOCIDOS (Wikidata/curado, nómbralos): " + ", ".join(
            n for n in names if n)
    fan_block = format_sources_block(sources or [])
    bond_heading, bond_instr = _bond_heading(band)
    return f"""\
Escribe un artículo SEO de 1400-2000 palabras sobre {band.name}, SELLO
DISCOGRÁFICO del entorno del rock español, en relación con el universo de
Extremoduro y Robe Iniesta.

DATOS VERIFICADOS:
{summary}

FICHA DE WIKIPEDIA (tu fuente principal de datos CONCRETOS; parafrasea, extrae
fundación, fundadores, artistas, discos, años, hechos; no copies literal):
{bio}

{artists_hint}

QUÉ DICEN LAS FUENTES (fan-content / prensa que mencionan al sello; matices y
hechos, contrasta, no copies literal):
{fan_block}

KW OBJETIVO: «{band.name}». Al inicio del meta_title, en la meta_description y
en el primer párrafo. KWs secundarias: sus artistas, sus discos, Extremoduro.

ESTRUCTURA OBLIGATORIA (encabezados H2, EN ESTE ORDEN):

## Qué es {band.name}
~250 palabras: qué sello es, cuándo y por quién se funda si consta, su línea
editorial y qué lugar ocupa en la industria del rock estatal.

## Catálogo y artistas
~350 palabras: qué artistas y discos publica o publicó. Nómbralos en texto plano
(sin links markdown; el sistema enlaza solo a quien tenga ficha). NUNCA hables de
"componentes" ni "integrantes": un sello edita a artistas, no los tiene de
plantilla. NO inventes nombres ni fichajes: si no tienes certeza, no lo incluyas.

## Historia y trayectoria
~450 palabras con H3 según las etapas reales (fundación, crecimiento, hitos,
cierre o continuidad). Menciona los discos publicados en texto plano. NO inventes
fechas ni lanzamientos.

{bond_heading}
~400 palabras: {bond_instr}

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final.
- NO INVENTES datos. Si no conoces una fecha, un artista o un disco, omítelo.
- NO escribas links markdown a mano. El sistema linkifica las entidades.

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_prompt(band: Band, sources: list[dict] | None = None) -> str:
    summary = _band_summary(band)
    bio = (band.bio_long or band.bio_short or "(sin biografía documentada)")[:9000]
    members_hint = ""
    if band.members:
        names = [m.get("name") if isinstance(m, dict) else str(m) for m in band.members]
        members_hint = "MIEMBROS CONOCIDOS (Wikidata/curado, nómbralos): " + ", ".join(
            n for n in names if n)
    fan_block = format_sources_block(sources or [])

    # Grupos poco documentados (sin bio y sin Wikipedia): prompt aparte para
    # no forzar invención. (El low-data ya ramifica internamente por kind.)
    if not band.bio_short and not band.bio_long and not band.wikipedia_url:
        return _build_low_data_prompt(band)

    # SELLOS (kind='label'): estructura propia de sello, no de grupo.
    if band.kind == "label":
        return _build_label_prompt(band, sources)

    kind_es = "sello discográfico" if band.kind == "label" else "grupo de rock"
    bond_heading, bond_instr = _bond_heading(band)
    return f"""\
Escribe un artículo SEO de 1400-2000 palabras sobre {band.name}, {kind_es}
del entorno del rock español, en relación con el universo de Extremoduro y
Robe Iniesta.

DATOS VERIFICADOS:
{summary}

FICHA DE WIKIPEDIA (tu fuente principal de datos CONCRETOS; parafrasea, extrae
miembros, discos, años, hechos; no copies literal):
{bio}

{members_hint}

QUÉ DICEN LAS FUENTES (fan-content / prensa que mencionan al grupo; matices y
hechos, contrasta, no copies literal):
{fan_block}

KW OBJETIVO: «{band.name}». Al inicio del meta_title, en la meta_description y
en el primer párrafo. KWs secundarias: sus discos, sus integrantes, Extremoduro.

ESTRUCTURA OBLIGATORIA (encabezados H2, EN ESTE ORDEN):

## Quién es {band.name}
~250 palabras: presentación, origen, qué lugar ocupa en el rock español.

## Componentes
~300 palabras: la formación del grupo. Nombra a sus integrantes con su
instrumento/rol (voz, guitarra, bajo, batería…) en texto plano, sin links
markdown (el sistema enlaza solo a quien tenga ficha). Distingue, si procede,
formación clásica y cambios de alineación. NO inventes nombres ni roles: si no
tienes certeza de un integrante, no lo incluyas; mejor nombrar solo a quienes
constan con seguridad (al menos el líder/vocalista).

## Trayectoria y discografía
~500 palabras con H3 según las etapas reales. Menciona los títulos de discos
en texto plano (sin links markdown). NO inventes discos ni fechas.

## Estilo y sonido
~300 palabras: qué hace distintivo a {band.name} musicalmente.

{bond_heading}
~400 palabras: {bond_instr}

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final.
- NO INVENTES datos. Si no conoces una fecha o un disco, omítelo.
- NO escribas links markdown a mano. El sistema linkifica las entidades.

Devuelve JSON con body_md, meta_title (≤60), meta_description (≤160),
entities (array según el system prompt).
"""


def _build_schema(band: Band) -> dict:
    same_as = []
    if band.wikipedia_url:
        same_as.append(band.wikipedia_url)
    if band.wikidata_id:
        same_as.append(f"https://www.wikidata.org/wiki/{band.wikidata_id}")

    is_label = band.kind == "label"
    schema_type = "Organization" if is_label else "MusicGroup"
    anchor = "organization" if is_label else "musicgroup"
    # Los sellos viven en /sellos; los grupos en /grupos.
    section = "sellos" if is_label else "grupos"
    schema: dict = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "@id": f"{SITE_URL}/{section}/{band.slug}#{anchor}",
        "name": band.name,
        "url": f"{SITE_URL}/{section}/{band.slug}",
    }
    if band.founded_year:
        schema["foundingDate"] = str(band.founded_year)
    if band.dissolved_year:
        schema["dissolutionDate"] = str(band.dissolved_year)
    if band.image_url:
        schema["image"] = band.image_url
    if same_as:
        schema["sameAs"] = same_as
    members = []
    for m in band.members or []:
        if isinstance(m, str):
            members.append({"@type": "Person", "name": m})
        elif isinstance(m, dict) and (m.get("name") or m.get("nombre")):
            members.append({"@type": "Person", "name": m.get("name") or m.get("nombre")})
    if members:
        schema["member"] = members
    return schema


def generate_for_band(client: OpenAI, db, band_slug: str, *, force: bool) -> bool:
    band = db.execute(
        select(Band).where(Band.slug == band_slug)
    ).scalar_one_or_none()
    if band is None:
        log(f"grupo '{band_slug}' no encontrado", "err")
        return False

    sources = fetch_sources_for_entity(db, [band.name])
    log(f"generando grupo: {band.name} (kind={band.kind}, "
        f"bio_long={'sí' if band.bio_long else 'no'}, {len(sources)} fuentes)")
    prompt = _build_prompt(band, sources)
    # Voz propia: 3ª persona cálida y cómplice, con el grupo como protagonista
    # (no Robe). Ver app/services/voice.py.
    system_prompt = build_system_prompt(
        family="seo", persona="tercera_calida", subject=band.name
    )
    try:
        out = call_llm(client, prompt, system_prompt=system_prompt, db=db)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    if not body_md or len(body_md) < 600:
        log(f"  artículo demasiado corto ({len(body_md)} chars)", "warn")
        return False

    schema = _build_schema(band)
    upsert_seo_content(
        db,
        entity_type="band",
        entity_id=band.id,
        slug=band.slug,
        body_md=body_md,
        meta_title=out.get("meta_title"),
        meta_description=out.get("meta_description"),
        schema_jsonld=schema,
        entities=out.get("entities") or [],
        sources=sources,
        force=force,
    )
    db.commit()
    log(f"  ✓ {band.slug} ({len(body_md)} chars)", "ok")
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
            generate_for_band(client, db, args.slug, force=args.force)
            return
        all_slugs = [
            s for (s,) in db.execute(select(Band.slug).order_by(Band.id)).all()
        ]
        for slug in all_slugs:
            generate_for_band(client, db, slug, force=args.force)


if __name__ == "__main__":
    main()
