"""Genera contenido SEO editorial para páginas de taxonomía: temas, lugares
y conceptos del universo Robe/Extremoduro.

A diferencia de artist/album/song, las taxonomías solo tenían una
`description` corta de seed. Este script genera un `seo_content` con
`entity_type` ∈ {theme, place, concept}, longitud **proporcional** al número
de canciones asociadas:
  - ≤2 canciones  → 300-500 palabras
  - 3-6 canciones → 600-900 palabras
  - 7+ canciones  → 1000-1400 palabras

Uso:
    python -m scripts.seo.generate_taxonomy_content --kind place --slug plasencia
    python -m scripts.seo.generate_taxonomy_content --kind theme --all --force
    python -m scripts.seo.generate_taxonomy_content --all --force   (las 3 kinds)
"""
from __future__ import annotations

import argparse

from openai import OpenAI

from app.config import get_settings
from app.db.models import Concept, Place, SeoContent, Song, Theme
from app.services.voice import build_system_prompt
from scripts.research.common import get_session, log
from scripts.seo.common import call_llm, tone_quotes_for, upsert_seo_content

SITE_URL = "https://entreinteriores.com"

# kind → (Model, ruta del hub)
KIND_MAP = {
    "theme": (Theme, "temas"),
    "place": (Place, "lugares"),
    "concept": (Concept, "conceptos"),
}

KIND_LABEL = {
    "theme": "tema",
    "place": "lugar",
    "concept": "concepto",
}


def _length_spec(n_songs: int) -> tuple[str, int]:
    """Devuelve (descripción de longitud, min_chars aceptable) según nº de
    canciones asociadas. El min_chars es un suelo generoso: preferimos
    aceptar contenido honesto y conciso a rechazarlo por no estirar."""
    if n_songs <= 2:
        return "entre 300 y 500 palabras", 600
    if n_songs <= 6:
        return "entre 500 y 800 palabras", 1100
    return "entre 800 y 1200 palabras", 1700


def _song_context(db, songs: list[Song]) -> str:
    """Bloque con las canciones donde aparece la taxonomía, para que el LLM
    tenga material real. Incluye un extracto del seo_content si existe."""
    lines: list[str] = []
    for s in songs:
        al = s.album
        ar = al.artist if al else None
        head = f"- «{s.title}»"
        if al and ar:
            head += f" ({ar.name}, {al.title}, {al.year})"
        lines.append(head)
    return "\n".join(lines) if lines else "(sin canciones asociadas)"


def _headings_for_kind(kind: str, name: str) -> str:
    """Plantilla de H2 por tipología. Cada kind cuenta una historia distinta."""
    if kind == "theme":
        return f"""\
## La evolución poética de «{name}»
## Canciones donde el tema se hace herida
## Por qué nos sigue quemando por dentro"""
    if kind == "concept":
        return f"""\
## El símbolo de «{name}» en la obra de Robe
## Canciones clave donde el motivo se hace herida
## El viaje interpretativo: por qué conecta"""
    # place
    return f"""\
## Historia real de «{name}»
## El hito que lo conecta con la banda
## Referencias en canciones y crónicas"""


def _build_system_prompt(kind: str, row):
    """System prompt (voz) por tipología. Ver app/services/voice.py.
    - theme   → 2ª persona cómplice, sin citas de tono, sin subject.
    - concept → 1ª persona megafan con citas de tono, sin subject.
    - place   → 3ª persona cálida, el lugar es el subject (tiene historia propia).
    """
    if kind == "theme":
        return build_system_prompt(family="seo", persona="segunda_complice")
    if kind == "concept":
        return build_system_prompt(
            family="seo",
            persona="primera_admirador",
            tone_quotes=tone_quotes_for(seed=row.slug),
        )
    # place
    return build_system_prompt(
        family="seo", persona="tercera_calida", subject=row.name
    )


def _build_prompt(kind: str, row, songs: list[Song]) -> str:
    label = KIND_LABEL[kind]
    length_desc, _ = _length_spec(len(songs))
    descr = (row.description or "").strip() or "(sin descripción previa)"
    song_block = _song_context(None, songs)
    headings = _headings_for_kind(kind, row.name)

    geo_hint = ""
    if kind == "place" and (getattr(row, "geo_lat", None) or getattr(row, "geo_lng", None)):
        geo_hint = "Es un lugar geográfico real; sitúalo con precisión.\n"

    place_note = ""
    if kind == "place":
        place_note = (
            "- Respeta que el lugar tiene historia propia al margen de Robe; "
            "no inventes hitos ni conexiones que no consten en las fuentes.\n"
        )

    compare_note = ""
    if kind in ("theme", "concept"):
        compare_note = (
            "- Compara ≥3 canciones cuando las haya, mostrando cómo el "
            f"{label} muta de una a otra.\n"
        )

    return f"""\
Escribe un artículo editorial SEO sobre el {label} «{row.name}» tal como
aparece en el universo de Robe Iniesta y Extremoduro.

DESCRIPCIÓN PREVIA (puedes partir de ella, ampliarla, no copiarla literal):
{descr}

CANCIONES DONDE APARECE ESTE {label.upper()}:
{song_block}
{geo_hint}
LONGITUD: {length_desc}. Ajusta la profundidad al material real: si solo
hay una o dos canciones, sé conciso y honesto, no rellenes de paja.

ENFOQUE:
- Explica qué es «{row.name}» y, sobre todo, QUÉ SIGNIFICA dentro de las
  letras de Robe y Extremoduro: cómo lo trata, qué evoca, por qué reaparece.
- Menciona los títulos de canción en texto plano (el sistema los enlaza
  solo). Igual con discos, artistas, lugares o personas que cites.
- Si es un lugar, conecta lo geográfico/real con lo simbólico en las letras.
{compare_note}{place_note}
ESTRUCTURA OBLIGATORIA (encabezados H2, en este orden; SIN H1, lo pone la
plantilla):

{headings}

Cierra con una frase seca, sin moraleja.

Devuelve JSON con `body_md`, `meta_title` (≤60 chars, con «{row.name}» al
inicio), `meta_description` (≤155 chars) y `entities` (según system prompt).
"""


def _build_schema(kind: str, row) -> dict:
    hub = KIND_MAP[kind][1]
    url = f"{SITE_URL}/{hub}/{row.slug}"
    if kind == "place":
        schema: dict = {
            "@context": "https://schema.org",
            "@type": "Place",
            "name": row.name,
            "url": url,
        }
        if getattr(row, "geo_lat", None) and getattr(row, "geo_lng", None):
            schema["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": float(row.geo_lat),
                "longitude": float(row.geo_lng),
            }
        return schema
    # theme / concept
    return {
        "@context": "https://schema.org",
        "@type": "DefinedTerm",
        "name": row.name,
        "url": url,
        "inDefinedTermSet": f"{SITE_URL}/{hub}",
    }


def generate_for_taxonomy(
    client: OpenAI, db, kind: str, slug: str, *, force: bool
) -> bool:
    model = KIND_MAP[kind][0]
    row = db.query(model).filter(model.slug == slug).first()
    if not row:
        log(f"{kind} '{slug}' no encontrado", "err")
        return False

    songs = list(row.songs)
    log(f"generando {kind}: {row.name} ({len(songs)} canciones)")

    prompt = _build_prompt(kind, row, songs)
    system_prompt = _build_system_prompt(kind, row)
    try:
        out = call_llm(client, prompt, system_prompt=system_prompt)
    except Exception as e:  # noqa: BLE001
        log(f"  LLM error: {e}", "err")
        return False

    body_md = out.get("body_md", "")
    _, min_chars = _length_spec(len(songs))
    if not body_md or len(body_md) < min_chars:
        log(f"  artículo demasiado corto ({len(body_md)} chars, min {min_chars})", "warn")
        return False

    upsert_seo_content(
        db,
        entity_type=kind,
        entity_id=row.id,
        slug=row.slug,
        body_md=body_md,
        meta_title=out.get("meta_title"),
        meta_description=out.get("meta_description"),
        schema_jsonld=_build_schema(kind, row),
        entities=out.get("entities") or [],
        force=force,
    )
    db.commit()
    log(f"  ✓ {kind}/{row.slug} ({len(body_md)} chars)", "ok")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=list(KIND_MAP.keys()))
    parser.add_argument("--slug")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.all and not (args.kind and args.slug):
        parser.error("Indica --kind X --slug Y, o --all (opcionalmente con --kind)")

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    kinds = [args.kind] if args.kind else list(KIND_MAP.keys())

    with get_session() as db:
        if args.slug:
            generate_for_taxonomy(client, db, args.kind, args.slug, force=args.force)
            return
        for kind in kinds:
            model = KIND_MAP[kind][0]
            slugs = [s for (s,) in db.query(model.slug).order_by(model.id).all()]
            log(f"=== {kind}: {len(slugs)} entradas ===")
            for slug in slugs:
                generate_for_taxonomy(client, db, kind, slug, force=args.force)


if __name__ == "__main__":
    main()
