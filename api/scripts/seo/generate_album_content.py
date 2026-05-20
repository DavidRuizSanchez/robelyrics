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
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_sources_for_album,
    format_sources_block,
    upsert_seo_content,
)


def build_user_prompt(album: Album, sources: list[dict]) -> str:
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

ESTRUCTURA OBLIGATORIA (encabezados H2):

## El disco de un vistazo
~150 palabras: qué es, año, lugar en la discografía de {artist.name},
qué lo hace particular.

## Contexto histórico y musical
~400 palabras: lo que pasaba en {artist.name} en {album.year}, contexto
musical español de la época, sello y producción si lo sabes.

## Composición y grabación
~300 palabras: cómo y dónde se grabó si lo aportan las fuentes; anécdotas
documentadas. NO inventes datos técnicos.

## Recorrido por las canciones
~600 palabras: repaso por las canciones del tracklist con 1-2 frases por
cada una. NO copies letras, describe el tema y el tono. Menciona los
títulos en texto plano — el sistema los linkifica automáticamente a sus
páginas locales.

## Recepción crítica y comercial
~300 palabras: cómo lo recibió la prensa especializada (puedes citar Mondo
Sonoro, Efe Eme, Rockdelux si están en las fuentes), ventas, premios, giras
asociadas.

## Legado
~250 palabras: lugar del álbum en la obra de {artist.name}, cobertura
posterior, recopilatorios, regresos en directo.

## Otros discos relacionados
~50 palabras mencionando 1-2 discos cercanos del mismo artista por su
título (texto plano, el sistema los linkifica).

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
    log(f"generando álbum: {album.artist.name} · {album.title} ({len(sources)} fuentes)")

    prompt = build_user_prompt(album, sources)
    try:
        out = call_llm(client, prompt)
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
        force=force,
    )
    db.commit()
    log(f"  ✓ {album.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--album-slug", required=True, help="slug del álbum a generar")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        generate_for_album(client, db, args.album_slug, force=args.force)


if __name__ == "__main__":
    main()
