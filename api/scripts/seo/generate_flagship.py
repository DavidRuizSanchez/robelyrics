"""Generador EXHAUSTIVO de las 2 páginas estrella: Robe y Extremoduro.

A diferencia de `generate_artist_content` (estructura fija, top-20 fuentes),
aquí se mina el corpus rico (entrevistas, libros, episodios "Historia de
Extremoduro", consenso destilado, citas) + los DATOS DUROS de la ficha
(nacimiento/muerte/lugar) para escribir el artículo más completo posible:
largo, con headings ADAPTADOS al contenido y al storytelling (sin plantilla),
enlazado internamente y pasado por verificación factual.

Uso:
  python -m scripts.seo.generate_flagship --entity robe
  python -m scripts.seo.generate_flagship --entity extremoduro [--publish]
"""
from __future__ import annotations

import argparse
import json
import os

from openai import OpenAI
from sqlalchemy import select

from app.db.models import Album, Artist, InterpretationSource, Person
from app.db.session import SessionLocal
from scripts.seo.common import (
    MODEL,
    _verify_body,
    fetch_distilled_for_artist,
    format_distilled_block,
    log,
    upsert_seo_content,
)
from app.services.entity_resolver import (
    autolink_corpus,
    build_corpus_index,
    load_link_stats,
)
from app.services.text_sanitizer import strip_ai_tells

# Cap de material por fuente y total (gpt-4o: 128k contexto; dejamos sitio a la
# salida larga). Priorizamos densidad de hechos, no transcripciones de directo.
_PER_SOURCE = 3500
_TOTAL_CAP = 115_000
# Orden de prioridad de kinds por densidad de hechos.
_KIND_PRIORITY = [
    "about_robe", "robe_interview", "libro", "press", "prensa",
    "blog", "robe_quote", "forum", "genius_annotation", "youtube_transcript",
]


def _hard_facts(db) -> str:
    facts = []
    robe = db.execute(
        select(Person).where(Person.full_name.ilike("%iniesta%"))
    ).scalars().first()
    if robe:
        facts.append(
            f"Robe Iniesta (nombre real {robe.full_name}). "
            f"Nacimiento: {robe.birth_date} en {robe.birth_place}. "
            f"Fallecimiento: {robe.death_date}."
        )
    for a in db.execute(select(Artist)).scalars():
        albums = db.execute(
            select(Album).where(Album.artist_id == a.id).order_by(Album.year)
        ).scalars().all()
        disc = ", ".join(f"{al.title} ({al.year})" for al in albums)
        facts.append(f"{a.name} (actividad {a.active_years}). Discografía: {disc}.")
    return "\n".join(facts)


def _gather_material(db) -> str:
    """Material rico del corpus, priorizando densidad de hechos. Episodios
    'Historia de Extremoduro' de Juancares primero entre los youtube."""
    rows = db.execute(
        select(
            InterpretationSource.kind,
            InterpretationSource.title,
            InterpretationSource.content_clean,
        ).where(InterpretationSource.content_clean.is_not(None))
    ).all()

    def sort_key(r):
        kind = r[0]
        prio = _KIND_PRIORITY.index(kind) if kind in _KIND_PRIORITY else 99
        title = (r[1] or "").upper()
        # Dentro de youtube_transcript, los episodios "HISTORIA"/"CAPÍTULO"
        # (narrativos, ricos en hechos) van antes que las grabaciones de directo.
        narr = 0 if ("HISTORIA DE EXTREMODURO" in title or "CAPÍTULO" in title
                     or "ENTREVISTA" in title) else 1
        return (prio, narr, -(len(r[2] or "")))

    rows = sorted(rows, key=sort_key)
    chunks, total = [], 0
    for kind, title, content in rows:
        snippet = (content or "").strip()[:_PER_SOURCE]
        if len(snippet) < 200:
            continue
        block = f"[{kind}] {title or ''}\n{snippet}"
        if total + len(block) > _TOTAL_CAP:
            break
        chunks.append(block)
        total += len(block)
    log(f"material curado: {len(chunks)} fuentes · {total//1000}k chars")
    return "\n\n----\n\n".join(chunks)


_FLAGSHIP_SYS = (
    "Eres el autor de Entre Interiores. Vas a escribir LA página de referencia "
    "sobre {subject}: el artículo más completo y mejor contado que existe en "
    "internet. Voz de fan que lleva media vida con estas canciones, en primera "
    "persona admiradora, pero SIN inventar presencia en eventos ('yo estaba'...) "
    "y SIN inventar datos. Robe FALLECIÓ: enmárcalo en pasado. No uses la raya "
    "larga."
)


def _write(client: OpenAI, subject: str, angle: str, hard: str, material: str) -> dict:
    user = f"""\
Escribe el artículo DEFINITIVO sobre {subject}. {angle}

OBJETIVO: que no quede ninguna duda sobre su vida (pública y privada), su obra,
relaciones, miedos, logros e influencias. Cuenta los DETALLES que casi nadie
cuenta (salen del MATERIAL del corpus de abajo). Cuanto más completo, mejor:
extiéndete todo lo que el material dé de sí (apunta a 2500-4500 palabras).

DATOS DUROS (inclúyelos sí o sí, son básicos y faltaban):
{hard}

MATERIAL DEL CORPUS (tu única fuente de hechos; parafrasea, no copies; cruza y
ordena la información; NO inventes nada que no esté aquí o en los datos duros):
\"\"\"
{material}
\"\"\"

CÓMO ESCRIBIRLO:
- Headings (H2/H3) ADAPTADOS al contenido y al storytelling: NO sigas una
  plantilla fija. Que la estructura nazca de lo que hay que contar (orígenes y
  Plasencia, el nombre, la calle, las adicciones, el método de componer, cada
  etapa de la obra, el crowdfunding, las relaciones y colaboraciones, los
  miedos, los logros, las influencias, el final y el legado... lo que el
  material pida), ordenado de forma lógica y atractiva.
- Concreto y con fondo: fechas, lugares, nombres, anécdotas reales del material.
  Nada de relleno ni frases-humo.
- Enlaza de forma natural cuando nombres discos/canciones/personas del universo
  (markdown a entreinteriores.com); el sistema añadirá más enlaces después.
- SEO natural, sin keyword-stuffing.

Devuelve JSON: body_md (markdown, sin H1), meta_title (≤60, entidad al inicio,
3ª persona), meta_description (≤155), entities (lista de nombres propios del
universo citados para el knowledge graph).
"""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _FLAGSHIP_SYS.format(subject=subject)},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.6,
        max_tokens=16000,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    for f in ("body_md", "meta_title", "meta_description"):
        if isinstance(data.get(f), str):
            data[f] = strip_ai_tells(data[f])
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity", required=True, choices=["robe", "extremoduro"])
    ap.add_argument("--publish", action="store_true", help="publica al terminar")
    args = ap.parse_args()

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with SessionLocal() as db:
        artist = db.execute(
            select(Artist).where(Artist.slug == args.entity)
        ).scalars().first()
        if not artist:
            log(f"artista '{args.entity}' no encontrado", "err")
            return

        subject = "Robe Iniesta" if args.entity == "robe" else "Extremoduro"
        angle = (
            "Su vida completa (Plasencia, la calle, las adicciones, su forma de "
            "ser), toda su obra con Extremoduro y en solitario, sus relaciones y "
            "su legado."
            if args.entity == "robe" else
            "La historia completa de la banda: del rock transgresivo casero a la "
            "madurez sinfónica, formaciones, cada disco y gira, y su huella."
        )
        hard = _hard_facts(db)
        material = _gather_material(db)
        distilled = format_distilled_block(fetch_distilled_for_artist(db, artist.id))
        material = f"{material}\n\n---- CONSENSO DESTILADO ----\n{distilled}"

        log(f"generando FLAGSHIP: {subject}")
        out = _write(client, subject, angle, hard, material)
        body = out.get("body_md") or ""
        if len(body) < 3000:
            log(f"  cuerpo corto ({len(body)} chars); revisar", "warn")

        # Verificación factual contra el material (hard + corpus).
        body = _verify_body(client, body, f"{hard}\n\n{material}")
        # Enlazado interno del knowledge graph.
        body = autolink_corpus(
            body, build_corpus_index(db), max_links=10,
            exclude_slug=artist.slug, link_stats=load_link_stats(),
        )
        log(f"  ✓ {subject}: {len(body)} chars")

        ents = out.get("entities") if isinstance(out.get("entities"), list) else []
        schema = {
            "@context": "https://schema.org",
            "@type": "Person" if args.entity == "robe" else "MusicGroup",
            "name": subject,
            "url": f"https://entreinteriores.com/{artist.slug}",
        }
        upsert_seo_content(
            db, entity_type="artist", entity_id=artist.id, slug=artist.slug,
            body_md=body, meta_title=(out.get("meta_title") or "")[:60],
            meta_description=(out.get("meta_description") or "")[:155],
            schema_jsonld=schema, entities=ents, force=True,
        )
        if args.publish:
            from sqlalchemy import update
            from app.db.models import SeoContent
            db.execute(
                update(SeoContent).where(
                    SeoContent.entity_type == "artist",
                    SeoContent.entity_id == artist.id,
                ).values(published=True)
            )
            db.commit()
            log("  publicado", "ok")


if __name__ == "__main__":
    main()
