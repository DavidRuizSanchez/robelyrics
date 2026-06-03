"""Genera contenido SEO para un disco completo.

Estructura:
  1. Intro (~150): qué disco es, año, lugar en la discografía.
  2. Contexto histórico (~400): situación de la banda, contexto musical y
     social, sello, productor.
  3. Composición y grabación (~300): cómo y dónde se grabó, anécdotas.
  4. Tracklist comentado (~600): repaso disco a disco con 1-2 frases por canción.
  5. Recepción crítica y comercial (~300): críticas, ventas, premios, giras.
  6. Legado (~250): lugar del álbum en la obra del artista, cobertura posterior.

Total ~2000 palabras.

Ejecución:
  docker compose exec api python -m scripts.seo.generate_album_content --album-slug agila
"""
from __future__ import annotations

import argparse

from openai import OpenAI

from app.config import get_settings
from app.db.models import Album
from app.services.voice import build_system_prompt
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_distilled_for_album,
    fetch_sources_for_album,
    format_distilled_block,
    format_sources_block,
    tone_quotes_for,
    upsert_seo_content,
)


def build_user_prompt(album: Album, sources: list[dict], distilled: list[dict] | None = None) -> str:
    artist = album.artist
    tracks = sorted(album.songs, key=lambda s: (s.track_number or 999, s.id))
    track_text = "\n".join(
        f"- {s.track_number or '?'}. {s.title}"
        for s in tracks
    )

    return f"""\
Escribe un artículo SEO de aproximadamente 2000 palabras sobre el disco
"{album.title}" ({album.year}) de {artist.name}.

DATOS:
- Año: {album.year}
- Tipo: {album.kind}
- Tracklist:
{track_text}

FUENTES EXTERNAS:
{format_sources_block(sources)}

{format_distilled_block(distilled)}

ESTRUCTURA OBLIGATORIA (encabezados H2, en este orden):

## El disco de un vistazo
~150 palabras: qué es, año, lugar en la discografía de {artist.name},
qué lo hace particular.

## Contexto emocional y época de la grabación
~400 palabras: lo que pasaba en {artist.name} en {album.year}, el momento
emocional y vital, contexto musical español de la época, sello y producción
si lo sabes.

## Estilo sonoro: guitarras, arreglos y arquitectura
~350 palabras: cómo suena el disco (guitarras, arreglos, producción y
arquitectura del conjunto). Solo lo que conste; no inventes datos técnicos.

## Canción a canción
~600 palabras: repaso por las canciones del tracklist con 1-2 frases por
cada una. NO copies letras, describe el tema y el tono. Menciona los
títulos en texto plano — el sistema los linkifica automáticamente a sus
páginas locales.

## Formación de estudio: quién grabó qué
~250 palabras: quién toca qué en este disco, productor e ingenieros si
constan. SOLO si consta en las fuentes; si no, omite la sección o acórtala.
NO inventes quién tocó, ni roles, ni nombres.

## Ediciones, maquetas y rarezas
~250 palabras: ediciones, reediciones, maquetas, tomas alternativas, caras B
o rarezas documentadas. SOLO si consta en las fuentes; si no, omite la
sección o acórtala. NO inventes maquetas, fechas ni ediciones.

IMPORTANTE:
- NO escribas markdown de link a mano ni uses placeholders entre
  corchetes ([Título], <slug>, etc.). Si no tienes el dato exacto,
  omite la frase.
- NO inventes datos.

Devuelve JSON con `body_md`, `meta_title` (≤60 chars con título disco +
artista), `meta_description` (≤160 chars resumiendo el álbum),
`entities` (según system prompt).
"""


def generate_for_album(client: OpenAI, db, album_slug: str, *, force: bool) -> bool:
    album = db.query(Album).filter(Album.slug == album_slug).first()
    if not album:
        log(f"álbum '{album_slug}' no encontrado", "err")
        return False
    sources = fetch_sources_for_album(db, album.id)
    distilled = fetch_distilled_for_album(db, album.id)
    log(f"generando álbum: {album.artist.name} · {album.title} "
        f"({len(sources)} fuentes, {len(distilled)} destilados)")

    prompt = build_user_prompt(album, sources, distilled)
    # Voz: megafan punki en 1ª persona; el disco de Robe/Extremoduro es el
    # protagonista, así que sin subject. Ver app/services/voice.py.
    system_prompt = build_system_prompt(
        family="seo",
        persona="primera_admirador",
        tone_quotes=tone_quotes_for(seed=album.slug),
    )
    try:
        out = call_llm(client, prompt, system_prompt=system_prompt)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    if not body_md or len(body_md) < 800:
        log(f"  artículo demasiado corto ({len(body_md)} chars)", "warn")
        return False

    schema = {
        "@context": "https://schema.org",
        "@type": "MusicAlbum",
        "name": album.title,
        "byArtist": {"@type": "MusicGroup", "name": album.artist.name},
        "datePublished": str(album.year),
        "albumProductionType": "StudioAlbum" if album.kind == "studio" else album.kind,
        "url": f"https://entreinteriores.com/{album.artist.slug}/{album.slug}",
        "image": album.cover_url and f"https://entreinteriores.com{album.cover_url}",
    }

    upsert_seo_content(
        db,
        entity_type="album",
        entity_id=album.id,
        slug=album.slug,
        body_md=body_md,
        meta_title=out.get("meta_title"),
        meta_description=out.get("meta_description"),
        schema_jsonld=schema,
        entities=out.get("entities") or [],
        sources=sources,
        force=force,
    )
    db.commit()
    log(f"  ✓ {album.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--album-slug", help="slug del álbum a generar")
    parser.add_argument("--all", action="store_true", help="genera todos los álbumes")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.all and not args.album_slug:
        parser.error("Indica --album-slug X o --all")

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        if args.all:
            from app.db.models import Album as _Album
            slugs = [s for (s,) in db.query(_Album.slug).order_by(_Album.id).all()]
            log(f"=== {len(slugs)} álbumes ===")
            for slug in slugs:
                generate_for_album(client, db, slug, force=args.force)
        else:
            generate_for_album(client, db, args.album_slug, force=args.force)


if __name__ == "__main__":
    main()
