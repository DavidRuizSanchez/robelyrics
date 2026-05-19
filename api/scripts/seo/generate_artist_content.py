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
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_sources_for_artist,
    format_sources_block,
    upsert_seo_content,
)


def build_user_prompt(artist: Artist, albums: list[Album], sources: list[dict]) -> str:
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

ESTRUCTURA OBLIGATORIA (encabezados H2):

## Quién es {artist.name}
~300 palabras: presentación general, formación si es banda, qué lugar ocupa
en la música española.

## Trayectoria
~1200 palabras divididos en H3 por etapas:
### Inicios y primeros años
### Consolidación y discos clave
### Etapa de madurez / solitario / cambios de formación
### Cierre / etapa final / fallecimiento (si aplica)

## Estilo, temáticas y lenguaje
~500 palabras: rasgos literarios distintivos, registros, influencias, lenguaje.

## Discografía comentada
~600 palabras: repaso disco a disco con 1-2 frases por álbum. Para cada disco,
enlaza `[Título](/{artist.slug}/<slug>)`.

## Legado e influencia
~300 palabras: impacto en la escena rock española, artistas influidos.

## Hechos biográficos relevantes
~100 palabras: solo datos públicos y verificados; obviar lo no documentado.

Devuelve JSON con `body_md`, `meta_title` (≤60 chars), `meta_description`
(≤160 chars).
"""


def generate_for_artist(client: OpenAI, db, artist_slug: str, *, force: bool) -> bool:
    artist = db.query(Artist).filter(Artist.slug == artist_slug).first()
    if not artist:
        log(f"artista '{artist_slug}' no encontrado", "err")
        return False
    albums = list(artist.albums)
    sources = fetch_sources_for_artist(db, artist.id)
    log(f"generando artista: {artist.name} ({len(albums)} discos · {len(sources)} fuentes top)")

    prompt = build_user_prompt(artist, albums, sources)
    try:
        out = call_llm(client, prompt)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    if not body_md or len(body_md) < 1500:
        log(f"  artículo demasiado corto ({len(body_md)} chars)", "warn")
        return False

    schema_type = "MusicGroup" if " " not in artist.name or artist.name.lower().startswith(
        ("extremoduro",)
    ) else "Person"
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
        force=force,
    )
    db.commit()
    log(f"  ✓ {artist.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-slug", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        generate_for_artist(client, db, args.artist_slug, force=args.force)


if __name__ == "__main__":
    main()
