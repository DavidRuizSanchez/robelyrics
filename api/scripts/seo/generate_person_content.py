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
from scripts.research.common import get_session, log
from scripts.seo.common import call_llm, upsert_seo_content


SITE_URL = "https://entreinteriores.com"


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


def _build_prompt(person: Person, memberships: list[BandMembership]) -> str:
    summary = _person_summary(person, memberships)
    band_list = ", ".join(m.artist.name for m in memberships) or "(sin memberships en el corpus)"
    bio = person.bio_short or "(sin biografía corta documentada)"
    primary_band = memberships[0].artist.name if memberships else None

    # Plantilla de secciones: sustituye los placeholders por el nombre real
    # de la banda principal ANTES de mandar al LLM. Si no hay banda
    # principal, omite esa sección y usa "Trayectoria" genérico.
    if primary_band:
        section_trayectoria = (
            "### Primeros años\n"
            f"### Etapa con {primary_band}\n"
            "### Otras colaboraciones y proyectos\n"
            "### Etapa actual o cierre (si fallecido, despedida)\n"
        )
    else:
        section_trayectoria = (
            "### Primeros años\n"
            "### Trayectoria principal\n"
            "### Otras colaboraciones y proyectos\n"
            "### Etapa actual o cierre (si fallecido, despedida)\n"
        )

    return f"""\
Escribe un artículo SEO de 1800-2400 palabras sobre {person.full_name}.

DATOS VERIFICADOS:
{summary}

BIOGRAFÍA CORTA (puedes parafrasear pero no copiar):
{bio}

BANDAS EN NUESTRO SITIO (no es texto fijo; úsalo como info):
{band_list}

ESTRUCTURA OBLIGATORIA (encabezados H2):

## Quién es {person.full_name}
~300 palabras: presentación, contexto, qué lugar ocupa en el rock español.

## Trayectoria
~800 palabras con H3 según las etapas significativas reales. Usa los
encabezados H3 EXACTOS de abajo (sustitutos ya hechos, no cambies ni
añadas corchetes):
{section_trayectoria}

## Estilo y aportación
~400 palabras: qué hace distintivo a esta persona musicalmente, qué rol
desempeña en grupo (compositor, líder de directo, etc.).

## Discos y canciones donde aparece
~400 palabras: repaso de los álbumes y canciones donde participa, una o
dos frases por disco. Menciona los títulos en texto plano — el sistema
los enlazará automáticamente a sus páginas locales.

## Legado e impacto
~200 palabras: huella en la escena, artistas influidos.

IMPORTANTE:
- NO uses placeholders entre corchetes en el texto final ("[banda
  principal]", "[título]", "<algo>"). Si no tienes el dato, omite la
  frase o redondea ("una de sus bandas más conocidas").
- NO INVENTES datos. Si no conoces fecha, productor, etc., omítelo.
- NO escribas links markdown a mano. El sistema linkifica los nombres
  detectados como entidades automáticamente.

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

    log(f"generando persona: {person.full_name} ({len(memberships)} memberships)")
    prompt = _build_prompt(person, memberships)
    try:
        out = call_llm(client, prompt)
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
