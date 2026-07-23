"""Genera contenido SEO para una página de artista (hub principal).

Estructura ~3000 palabras:
  1. Quién es (~300): nombre, formación, qué representa.
  2. Trayectoria por etapas (~1200): orígenes → discos clave → solitario → cierre.
  3. Estilo y temáticas (~500): rasgos distintivos de la obra.
  4. Discografía comentada (~600): listado con 1-2 frases por disco.
  5. Legado e influencia (~300): impacto en la escena española.
  6. Hechos personales relevantes (~100): solo lo público y verificado.

Ejecución:
  docker compose exec api python -m scripts.seo.generate_artist_content --artist-slug extremoduro
"""
from __future__ import annotations

import argparse

from openai import OpenAI

from app.config import get_settings
from app.db.models import Album, Artist
from app.services.voice import build_system_prompt
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_distilled_for_artist,
    fetch_sources_for_artist,
    format_distilled_block,
    format_sources_block,
    tone_quotes_for,
    upsert_seo_content,
)


def build_user_prompt(artist: Artist, albums: list[Album], sources: list[dict],
                      distilled: list[dict] | None = None) -> str:
    disco_text = "\n".join(
        f"- {a.year}. {a.title} ({a.kind})" for a in sorted(albums, key=lambda x: x.year)
    )

    return f"""\
Escribe un artículo SEO de aproximadamente 3000 palabras sobre {artist.name}
({artist.active_years or 'años activos no documentados'}).

DISCOGRAFÍA OFICIAL EN BD:
{disco_text}

FUENTES EXTERNAS PRIORITARIAS:
{format_sources_block(sources)}

{format_distilled_block(distilled)}

ENFOQUE: esto es la página del PROYECTO MUSICAL / la BANDA {artist.name} (su
discografía, formación, sonido y directos), NO una biografía personal. Si {artist.name}
es un proyecto en solitario ligado a una persona (p.ej. «Los Robe» = el proyecto de
Robe tras Extremoduro), la vida privada, la infancia y la biografía del líder viven en
SU ficha de persona (/personas/…): NO las narres aquí; céntrate en el proyecto musical.

ESTRUCTURA OBLIGATORIA (encabezados H2, en este orden):

## {artist.name}: qué es y su lugar en el rock
~350 palabras: qué ES el proyecto/banda, cuándo y cómo se forma, quiénes lo integran,
qué propuesta musical representa y su sitio en el rock español. Nada de infancia del líder.

## La formación y el sonido de la banda
~450 palabras: los músicos que la integran y su papel, la evolución del sonido, los
directos y las giras si constan. Solo lo que conste en las fuentes.

## Discografía comentada, disco a disco
~1000 palabras: repaso disco a disco con 2-3 frases por álbum (año, tono, temas,
qué aporta al arco del proyecto). Menciona cada disco por su título en texto plano —
el sistema linkifica los títulos a sus páginas locales.

## El proceso creativo y la mirada del proyecto
~500 palabras: cómo se compone, la relación letra-música, temas recurrentes y la
mirada del mundo que atraviesa la obra. Solo lo documentado; no inventes método.

## Legado, homenajes y la herencia del proyecto
~450 palabras: impacto en la escena, artistas influidos, homenajes documentados y la
herencia que deja el proyecto. Solo datos públicos y verificados.

IMPORTANTE:
- NO escribas markdown de link a mano ni uses placeholders entre
  corchetes ([Título], <slug>, etc.).
- NO INVENTES datos.

META (para captar búsquedas del PROYECTO, no biográficas): `meta_title` (≤60 chars)
debe incluir «{artist.name}» y un término de proyecto/discografía (p.ej. «discografía»,
«discos», «canciones»); `meta_description` (≤160 chars) resume la banda y su discografía,
sin biografía personal.

Devuelve JSON con `body_md`, `meta_title` (≤60 chars), `meta_description`
(≤160 chars), `entities` (según system prompt).
"""


def generate_for_artist(client: OpenAI, db, artist_slug: str, *, force: bool) -> bool:
    artist = db.query(Artist).filter(Artist.slug == artist_slug).first()
    if not artist:
        log(f"artista '{artist_slug}' no encontrado", "err")
        return False
    albums = list(artist.albums)
    sources = fetch_sources_for_artist(db, artist.id)
    distilled = fetch_distilled_for_artist(db, artist.id)
    log(f"generando artista: {artist.name} ({len(albums)} discos · {len(sources)} fuentes top "
        f"· {len(distilled)} destilados)")

    prompt = build_user_prompt(artist, albums, sources, distilled)
    # Voz: megafan punki en 1ª persona. Robe/Extremoduro ES el protagonista,
    # así que sin subject. Ver app/services/voice.py.
    system_prompt = build_system_prompt(
        family="seo",
        persona="primera_admirador",
        tone_quotes=tone_quotes_for(seed=artist.slug),
    )
    try:
        out = call_llm(client, prompt, system_prompt=system_prompt, db=db)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    if not body_md or len(body_md) < 1500:
        log(f"  artículo demasiado corto ({len(body_md)} chars)", "warn")
        return False

    # La ruta de artista representa un PROYECTO MUSICAL / banda (Extremoduro, Los
    # Robe): siempre MusicGroup. La biografía de la persona vive en /personas/*.
    schema_type = "MusicGroup"
    schema = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": artist.name,
        "url": f"https://entreinteriores.com/{artist.slug}",
        "album": [
            {
                "@type": "MusicAlbum",
                "name": a.title,
                "datePublished": str(a.year),
                "url": f"https://entreinteriores.com/{artist.slug}/{a.slug}",
            }
            for a in albums
        ],
    }

    upsert_seo_content(
        db,
        entity_type="artist",
        entity_id=artist.id,
        slug=artist.slug,
        body_md=body_md,
        meta_title=out.get("meta_title"),
        meta_description=out.get("meta_description"),
        schema_jsonld=schema,
        entities=out.get("entities") or [],
        sources=sources,
        force=force,
    )
    db.commit()
    log(f"  ✓ {artist.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-slug")
    parser.add_argument("--all", action="store_true", help="genera todos los artistas")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.all and not args.artist_slug:
        parser.error("Indica --artist-slug X o --all")

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        if args.all:
            slugs = [s for (s,) in db.query(Artist.slug).order_by(Artist.id).all()]
            log(f"=== {len(slugs)} artistas ===")
            for slug in slugs:
                generate_for_artist(client, db, slug, force=args.force)
        else:
            generate_for_artist(client, db, args.artist_slug, force=args.force)


if __name__ == "__main__":
    main()
