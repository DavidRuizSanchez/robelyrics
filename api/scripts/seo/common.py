"""Helpers comunes para los scripts de generación SEO.

Reglas legales/editoriales que TODOS los prompts deben respetar:
  - NO recitar más de 4 líneas seguidas de letra original (cita LPI 32).
  - NO copiar bloques textuales de fuentes; siempre parafrasear.
  - Tono editorial cercano y riguroso, tercera persona.
  - Spanish neutral (no jerga regional excesiva).
  - NO usar Genius como fuente directa (CC-BY-NC en privada, ya excluido por
    `for_seo_only=True` o `kind=genius_annotation` en el filtro).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    InterpretationSource,
    SeoContent,
    Song,
)
from scripts.research.common import log

MODEL = "gpt-4o"
SYSTEM_PROMPT = """\
Eres un redactor editorial musical especializado en rock español, con tono \
cercano y riguroso. Escribes para un sitio fan no oficial de Extremoduro y \
Robe. Tu trabajo es producir artículos ricos en contexto y atractivos para \
SEO, sobre artistas, discos y canciones concretas.

Reglas estrictas que NO puedes romper:
1. NUNCA recites más de 4 líneas seguidas de letra original. Puedes mencionar \
   versos sueltos como cita corta entre comillas, pero el grueso del análisis \
   debe ser tuyo, no transcripción.
2. NUNCA copies frases textuales de las fuentes que se te aporten. Para todo \
   tipo de afirmación, parafrasea con tus propias palabras.
3. Escribe en tercera persona, no incluyas opiniones personales del tipo \
   "yo creo" o "personalmente".
4. NO inventes datos: si no sabes una fecha, una composición o un detalle \
   técnico, omítelo o señálalo como "no documentado".
5. Tono editorial culto pero accesible. Evita la jerga de fan club ("el rey \
   de Extremadura", "la voz de la calle", "rey del rock transgresivo"). \
   Prefiere descripciones específicas.
6. SEO: usa el título de la entidad y términos relacionados con naturalidad, \
   sin keyword-stuffing. Estructura el artículo con encabezados H2 y H3 en \
   markdown.
7. Cita explícita en markdown: cuando uses información concreta de una \
   fuente externa (no tu conocimiento general), referénciala con el formato \
   [Fuente: Mondo Sonoro 2021] al final de la frase.

MARCAS DE IA — PROHIBIDO ABSOLUTO (si rompes una, el texto se descarta):
8. PROHIBIDO el carácter raya/em-dash "—" y el guion largo "–". No los uses \
   NUNCA. Para incisos usa comas, paréntesis o puntos. Para guiones usa el \
   guion corto normal "-" solo en palabras compuestas.
9. PROHIBIDA la estructura tipo IA: nada de intro-desarrollo-conclusión \
   explícita. Nada de encabezados genéricos ("Introducción", "Contexto", \
   "Conclusión", "Resumen"). Los H2/H3 deben ser concretos y con sustantivos \
   del tema, no abstracciones.
10. PROHIBIDAS las frases meta sobre la propia escritura: "en este artículo", \
   "como veremos", "es importante destacar", "cabe mencionar", "en resumen", \
   "vale la pena", "en conclusión", "para terminar", "a continuación".
11. PROHIBIDOS los adjetivos vacíos de relleno: "icónico", "legendario", \
   "magistral", "imprescindible", "inolvidable", "espectacular", "único".
12. Empieza por una imagen concreta, un dato o una escena, NO por una frase \
   de definición genérica.

Devuelves SIEMPRE un objeto JSON con la estructura:
{
  "body_md": "<artículo en markdown completo>",
  "meta_title": "<≤60 caracteres>",
  "meta_description": "<≤160 caracteres>",
  "entities": [<lista — ver bloque ENTIDADES MENCIONADAS abajo>]
}

ENTIDADES MENCIONADAS — array `entities` obligatorio
Identifica TODAS las entidades nombradas en el texto y añádelas. Sirve para
construir schema.org `mentions` y enlazar el knowledge graph del sitio:

- Personas (músicos, miembros, productores, autores, periodistas).
- Bandas, grupos, proyectos musicales.
- Discos (MusicAlbum), canciones (MusicComposition).
- Lugares (ciudades, pueblos, regiones, salas, festivales).
- Organizaciones, sellos discográficos, medios.
- Programas (TVSeries, RadioSeries).

Formato por entidad:
  {
    "type": "Person" | "MusicGroup" | "MusicAlbum" | "MusicComposition" |
            "Place" | "TVSeries" | "RadioSeries" | "Organization" |
            "CreativeWork",
    "name": "<nombre canónico>",
    "wikidata_id": "<Q-ID si lo conoces, sino null>",
    "slug_hint": "<slug en kebab-case del corpus si crees que está,
                    sino null. Ej.: 'extremoduro', 'robe', 'agila',
                    'cipotecastico', 'robe-iniesta', 'inaki-uoho-anton',
                    'plasencia'>"
  }

Si la entidad es Robe, Extremoduro, un disco del catálogo, una canción o
un miembro conocido, rellena slug_hint para enlazar a la página local.
NO incluyas entidades genéricas o muy abstractas ("rock", "música",
"España", "España entera"). Solo entidades concretas y nombradas que un
lector pueda buscar.
"""


def call_llm(client: OpenAI, user_prompt: str) -> dict[str, Any]:
    """Invoca GPT-4o con structured output JSON. Lanza ValueError si JSON inválido."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.5,
        max_tokens=4000,
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("LLM devolvió contenido vacío")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido del LLM: {e}; raw={content[:200]}") from e


def upsert_seo_content(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    slug: str,
    body_md: str,
    meta_title: str | None,
    meta_description: str | None,
    schema_jsonld: dict | None,
    entities: list | None = None,
    force: bool = False,
) -> int:
    """Inserta o actualiza la fila correspondiente. Si ya existe y --force,
    sobrescribe body_md y reset reviewed_at + published. Si no force, falla."""
    # Saneado anti marcas de IA (em-dash, etc.) — red de seguridad por si el
    # LLM ignoró el SYSTEM_PROMPT.
    from app.services.text_sanitizer import strip_ai_tells
    body_md = strip_ai_tells(body_md) or body_md
    meta_title = strip_ai_tells(meta_title)
    meta_description = strip_ai_tells(meta_description)
    if not force:
        # Comprueba que no existe ya para evitar pisar revisión humana
        existing = (
            db.query(SeoContent)
            .filter(
                SeoContent.entity_type == entity_type,
                SeoContent.entity_id == entity_id,
            )
            .first()
        )
        if existing:
            log(
                f"  ya existe seo_content para {entity_type}/{slug} "
                f"(id={existing.id}, published={existing.published}); usa --force",
                "warn",
            )
            return existing.id

    ents = entities or []
    # Linkifica el body_md con las entidades resueltas: primera mención de
    # cada una se convierte en `[name](url)` apuntando a la página local
    # (si está en corpus) o a Wikidata. Idempotente y limitado a una
    # sustitución por entity para evitar overlinking.
    if ents and body_md:
        from app.services.entity_resolver import linkify_body_md, resolve_entities
        resolved = resolve_entities(db, ents)
        if resolved:
            body_md = linkify_body_md(body_md, resolved)

    stmt = (
        pg_insert(SeoContent)
        .values(
            entity_type=entity_type,
            entity_id=entity_id,
            slug=slug,
            body_md=body_md,
            meta_title=meta_title,
            meta_description=meta_description,
            schema_jsonld=schema_jsonld,
            entities=ents,
            generated_at=datetime.now(timezone.utc),
            generated_by=MODEL,
            reviewed_at=None,
            published=False,
        )
        .on_conflict_do_update(
            constraint="uq_seo_content_entity",
            set_={
                "slug": slug,
                "body_md": body_md,
                "meta_title": meta_title,
                "meta_description": meta_description,
                "schema_jsonld": schema_jsonld,
                "entities": ents,
                "generated_at": datetime.now(timezone.utc),
                "generated_by": MODEL,
                "reviewed_at": None,
                "published": False,
            },
        )
        .returning(SeoContent.id)
    )
    return int(db.execute(stmt).scalar_one())


def fetch_sources_for_song(db: Session, song_id: int) -> list[dict[str, Any]]:
    """Devuelve las fuentes (no-Genius) que mencionan a la canción, incluyendo
    las marcadas for_seo_only. Cada source en formato lite para el prompt."""
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(InterpretationSource.referenced_song_ids.any(song_id))
            .where(InterpretationSource.kind != "genius_annotation")
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:3000],  # truncamos por tokens
        }
        for r in rows
    ]


def fetch_sources_for_album(db: Session, album_id: int) -> list[dict[str, Any]]:
    """Fuentes que mencionan cualquier canción del álbum."""
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy import Integer as SAInteger, cast

    song_ids = [
        sid for (sid,) in db.execute(
            select(Song.id).where(Song.album_id == album_id)
        ).all()
    ]
    if not song_ids:
        return []
    # ARRAY overlap operator (&&) en Postgres
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(
                InterpretationSource.referenced_song_ids.op("&&")(
                    cast(song_ids, ARRAY(SAInteger))
                )
            )
            .where(InterpretationSource.kind != "genius_annotation")
        )
        .scalars()
        .all()
    )
    # dedup por url para evitar repetidos cuando una fuente menciona varias canciones
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.url in seen:
            continue
        seen.add(r.url)
        out.append({
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:3000],
        })
    return out


def fetch_sources_for_artist(db: Session, artist_id: int) -> list[dict[str, Any]]:
    """Top fuentes que mencionan al artista (todas sus canciones). Limitado a 20
    para no inundar el prompt — priorizamos `for_seo_only` (prensa profesional)."""
    song_ids = [
        sid for (sid,) in db.execute(
            select(Song.id)
            .join(Album, Song.album_id == Album.id)
            .where(Album.artist_id == artist_id)
        ).all()
    ]
    if not song_ids:
        return []
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy import Integer as SAInteger, cast
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(
                InterpretationSource.referenced_song_ids.op("&&")(
                    cast(song_ids, ARRAY(SAInteger))
                )
            )
            .where(InterpretationSource.kind != "genius_annotation")
            .order_by(InterpretationSource.for_seo_only.desc(), InterpretationSource.id)
            .limit(20)
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:2000],
        }
        for r in rows
    ]


def format_sources_block(sources: list[dict[str, Any]]) -> str:
    """Bloque legible para el prompt con las fuentes consultadas."""
    if not sources:
        return "(Sin fuentes externas adicionales — usa solo conocimiento general.)"
    blocks = []
    for i, s in enumerate(sources, 1):
        author = f" · {s['author']}" if s["author"] else ""
        head = f"FUENTE {i} [{s['kind']}{author}]: {s['title']}"
        blocks.append(f"{head}\n{s['content']}")
    return "\n\n---\n\n".join(blocks)
