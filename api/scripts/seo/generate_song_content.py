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
from app.services.voice import build_system_prompt
from scripts.research.common import get_session, log
from scripts.seo.common import (
    call_llm,
    fetch_distilled_for_song,
    fetch_sources_for_song,
    format_distilled_block,
    format_sources_block,
    tone_quotes_for,
    upsert_seo_content,
)


def build_user_prompt(
    song: Song,
    album: Album,
    artist: Artist,
    sources: list[dict],
    siblings: list[Song],
    distilled: dict | None = None,
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

{format_distilled_block(distilled)}

ESTRUCTURA OBLIGATORIA del artículo (encabezados H2/H3, en este orden):

## La canción de un vistazo
~150 palabras: qué es, dónde encaja en la discografía de {artist.name},
qué la diferencia de otras del mismo disco.

## El origen creativo y las musas
~300 palabras: año, momento de la banda, lo que se sabe sobre la composición,
qué disparó la canción y de dónde sale. Si no sabes algo concreto, dilo en
general sin inventar.

## Hermenéutica y análisis lírico
~400 palabras (la sección más importante, ve hondo): de qué trata la letra,
tono, registros literarios, qué le pasa a quien la escucha. Usa el CONSENSO FAN
DESTILADO de arriba como FUNDAMENTO interpretativo (intégralo con tu voz, no lo
cites ni lo copies). Aquí es donde más vale tu mirada de fan: por qué esta
canción importa. Puedes citar versos sueltos entre comillas (máximo 4 líneas
seguidas), nunca bloques.

### La psicología del dolor y el permiso para sentir
~150 palabras dentro del análisis: qué herida toca la canción y por qué nos da
permiso para sentirla. Apóyate en el consenso fan, no inventes.

## Arquitectura musical
~200 palabras: tempo aproximado, estructura (estrofas, estribillos, puentes),
instrumentación y arreglos si la fuente los menciona. No inventes datos técnicos.

## Directos, variaciones de letra y grabaciones de culto
~300 palabras: presencia en directos, variaciones de letra entre versiones,
bootlegs o grabaciones de culto, recopilatorios, referencias en críticas
posteriores. SOLO si constan en las fuentes; no inventes bootlegs ni cambios de
letra. Cierra mencionando, si encaja, 1-2 canciones del MISMO DISCO por su
título en texto plano. El sistema linkifica automáticamente los títulos a sus
páginas locales — NO escribas markdown de link a mano ni uses placeholders
entre corchetes ni `<algo>`.

NO INVENTES datos. Si no sabes algo concreto, omítelo.
NO uses placeholders del tipo [título], <slug>, etc.

Devuelve JSON con `body_md` (artículo completo en markdown), `meta_title`
(≤60 chars, con el nombre de la canción al inicio), `meta_description`
(≤160 chars, ángulo concreto) y `entities` (según system prompt).
"""


def generate_for_song(client: OpenAI, db, song_slug: str, *, force: bool) -> bool:
    song = db.query(Song).filter(Song.slug == song_slug).first()
    if not song:
        log(f"canción '{song_slug}' no encontrada", "err")
        return False
    album = song.album
    artist = album.artist
    sources = fetch_sources_for_song(db, song.id)
    distilled = fetch_distilled_for_song(db, song.id)
    siblings = [s for s in album.songs]

    log(f"generando: {artist.name} · {album.title} · {song.title} "
        f"({len(sources)} fuentes, destilado={'sí' if distilled else 'no'})")
    prompt = build_user_prompt(song, album, artist, sources, siblings, distilled)
    # Voz: megafan punki en 1ª persona; la canción de Robe/Extremoduro es el
    # protagonista, así que sin subject. Ver app/services/voice.py.
    system_prompt = build_system_prompt(
        family="seo",
        persona="primera_admirador",
        tone_quotes=tone_quotes_for(seed=song.slug),
    )
    try:
        out = call_llm(client, prompt, system_prompt=system_prompt)
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
        sources=sources,
        force=force,
    )
    db.commit()
    log(f"  ✓ {song.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-slug", help="solo una canción concreta")
    parser.add_argument("--album-slug", help="todas las canciones de un álbum")
    parser.add_argument("--all", action="store_true", help="todas las canciones del catálogo")
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
        elif args.all:
            slugs = [s for (s,) in db.query(Song.slug).order_by(Song.id).all()]
        else:
            log("debes pasar --song-slug, --album-slug o --all", "err")
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
