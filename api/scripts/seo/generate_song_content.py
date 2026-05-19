"""Genera contenido SEO para una canción individual.

Estructura del artículo:
  1. Intro (~150 palabras): qué es la canción, dónde encaja en la discografía.
  2. Contexto (~300): cuándo se compuso, qué pasaba en la banda, declaraciones.
  3. Análisis temático (~400): de qué habla, tono, lugar en la obra.
  4. Análisis musical (~200): tempo, estructura, instrumentación si lo sabemos.
  5. Recepción y legado (~300): cómo se recibió, recopilatorios, versiones live.

Salida: insert en seo_content con published=False, reviewed_at=None.

Ejecución:
  docker compose exec api python -m scripts.seo.generate_song_content --song-slug asco
  docker compose exec api python -m scripts.seo.generate_song_content --album-slug agila
  docker compose exec api python -m scripts.seo.generate_song_content --album-slug agila --force
"""
from __future__ import annotations

import argparse

from openai import OpenAI

from app.config import get_settings
from app.db.models import Album, Artist, Song
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_sources_for_song,
    format_sources_block,
    upsert_seo_content,
)


def build_user_prompt(
    song: Song,
    album: Album,
    artist: Artist,
    sources: list[dict],
    siblings: list[Song],
) -> str:
    sib_text = "\n".join(
        f"- {s.track_number or '?'}. {s.title}" for s in siblings if s.id != song.id
    ) or "(sin tracklist)"

    lyrics_clean = song.lyrics_clean or song.lyrics_raw or ""
    lyrics_for_context = lyrics_clean[:4000]  # bloque solo para que el LLM entienda el tema

    return f"""\
Escribe un artículo SEO de aproximadamente 1500 palabras sobre la canción
"{song.title}" del disco "{album.title}" ({album.year}) de {artist.name}.

DATOS:
- Pista: {song.track_number or '?'} de {len(siblings)}
- Año del disco: {album.year}
- Tipo de disco: {album.kind}

LETRA (solo para tu comprensión, NO LA REPRODUZCAS COMPLETA):
---
{lyrics_for_context}
---

OTRAS CANCIONES DEL MISMO DISCO (para internal linking sugerido):
{sib_text}

FUENTES EXTERNAS:
{format_sources_block(sources)}

ESTRUCTURA OBLIGATORIA del artículo (encabezados H2):

## La canción de un vistazo
~150 palabras: qué es, dónde encaja en la discografía de {artist.name},
qué la diferencia de otras del mismo disco.

## Contexto de creación
~300 palabras: año, momento de la banda, lo que se sabe sobre la composición.
Si no sabes algo concreto, dilo en general sin inventar.

## Tema y lectura interpretativa
~400 palabras: de qué trata la letra, tono, registros literarios. Puedes citar
versos sueltos entre comillas (máximo 4 líneas seguidas), nunca bloques.

## Forma musical
~200 palabras: tempo aproximado, estructura (estrofas, estribillos, puentes),
instrumentación si la fuente la menciona. No inventes datos técnicos.

## Recepción y legado
~300 palabras: cómo se recibió, presencia en directos, recopilatorios,
referencias en críticas posteriores.

## Para seguir escuchando
~50 palabras + lista de 2-3 canciones del MISMO DISCO con los enlaces
internos sugeridos en formato:
[Otra canción](/{artist.slug}/{album.slug}/<otra-slug>)

Devuelve JSON con `body_md` (artículo completo en markdown), `meta_title`
(≤60 chars, incluye nombre de canción + artista) y `meta_description`
(≤160 chars, frase atractiva con la temática principal).
"""


def generate_for_song(client: OpenAI, db, song_slug: str, *, force: bool) -> bool:
    song = db.query(Song).filter(Song.slug == song_slug).first()
    if not song:
        log(f"canción '{song_slug}' no encontrada", "err")
        return False
    album = song.album
    artist = album.artist
    sources = fetch_sources_for_song(db, song.id)
    siblings = [s for s in album.songs]

    log(f"generando: {artist.name} · {album.title} · {song.title} ({len(sources)} fuentes)")
    prompt = build_user_prompt(song, album, artist, sources, siblings)
    try:
        out = call_llm(client, prompt)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    meta_title = out.get("meta_title")
    meta_description = out.get("meta_description")

    if not body_md or len(body_md) < 500:
        log(f"  artículo demasiado corto ({len(body_md)} chars), saltando", "warn")
        return False

    schema = {
        "@context": "https://schema.org",
        "@type": "MusicComposition",
        "name": song.title,
        "composer": {"@type": "MusicGroup", "name": artist.name},
        "inAlbum": {
            "@type": "MusicAlbum",
            "name": album.title,
            "datePublished": str(album.year),
        },
        "url": f"https://entreinteriores.com/{artist.slug}/{album.slug}/{song.slug}",
    }

    upsert_seo_content(
        db,
        entity_type="song",
        entity_id=song.id,
        slug=song.slug,
        body_md=body_md,
        meta_title=meta_title,
        meta_description=meta_description,
        schema_jsonld=schema,
        entities=out.get("entities") or [],
        force=force,
    )
    db.commit()
    log(f"  ✓ {song.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-slug", help="solo una canción concreta")
    parser.add_argument("--album-slug", help="todas las canciones de un álbum")
    parser.add_argument("--force", action="store_true", help="sobrescribe filas existentes")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        slugs: list[str] = []
        if args.song_slug:
            slugs = [args.song_slug]
        elif args.album_slug:
            album = db.query(Album).filter(Album.slug == args.album_slug).first()
            if not album:
                log(f"álbum '{args.album_slug}' no encontrado", "err")
                return
            slugs = [s.slug for s in album.songs]
        else:
            log("debes pasar --song-slug o --album-slug", "err")
            return

    log(f"canciones a generar: {len(slugs)}")
    n_ok = 0
    for slug in slugs:
        with get_session() as db:
            if generate_for_song(client, db, slug, force=args.force):
                n_ok += 1
    log(f"generadas: {n_ok}/{len(slugs)}", "ok")


if __name__ == "__main__":
    main()
