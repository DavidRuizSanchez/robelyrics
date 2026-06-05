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


def _chat(client: OpenAI, system: str, user: str, *, max_tokens: int,
          temp: float = 0.6, jsonmode: bool = True) -> dict | str:
    kw = {"response_format": {"type": "json_object"}} if jsonmode else {}
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temp, max_tokens=max_tokens, **kw,
    )
    raw = resp.choices[0].message.content or ("{}" if jsonmode else "")
    return json.loads(raw) if jsonmode else raw


def _outline(client: OpenAI, subject: str, angle: str, hard: str, material: str) -> list[dict]:
    """Esquema ADAPTATIVO: 9-14 secciones nacidas del contenido y del
    storytelling, no de una plantilla."""
    user = f"""\
Vas a planificar el artículo MÁS COMPLETO de internet sobre {subject}. {angle}

DATOS DUROS:
{hard}

MATERIAL DEL CORPUS (lo único que existe como fuente de hechos):
\"\"\"{material[:90000]}\"\"\"

Propón un esquema de 9 a 14 secciones H2 ADAPTADAS a lo que de verdad hay que
contar (orígenes/Plasencia, el nombre, la calle y las adicciones, cómo componía,
cada etapa de la obra, crowdfunding, relaciones y colaboraciones, miedos,
logros, influencias que recibió y que dejó, el final y el legado... lo que el
material pida), ordenadas con lógica narrativa. NO uses una plantilla genérica.
Devuelve JSON {{"sections": [{{"heading": "<título H2 concreto y atractivo>",
"covers": "<qué hechos/anécdotas del material cubre, en una frase>"}}]}}.
"""
    data = _chat(client, _FLAGSHIP_SYS.format(subject=subject), user, max_tokens=1500)
    secs = data.get("sections") if isinstance(data, dict) else None
    return [s for s in (secs or []) if s.get("heading")][:14]


def _write_section(client: OpenAI, subject: str, section: dict,
                   all_headings: list[str], hard: str, material: str) -> str:
    """Escribe UNA sección en profundidad, con citas textuales atribuidas."""
    user = f"""\
Escribe la sección "{section['heading']}" del artículo definitivo sobre {subject}.
Cubre: {section.get('covers', '')}

El artículo completo tiene estas secciones (para que NO repitas lo de otras):
{chr(10).join('- ' + h for h in all_headings)}

DATOS DUROS:
{hard}

MATERIAL DEL CORPUS (única fuente de hechos; parafrasea, NO inventes nada que no
esté aquí):
\"\"\"{material}\"\"\"

INSTRUCCIONES:
- Empieza con el encabezado markdown "## {section['heading']}".
- En profundidad y concreto: 250-550 palabras, con fechas, lugares, nombres y
  ANÉCDOTAS reales del material. Nada de relleno.
- INCLUYE, si el material las tiene, 1-3 CITAS TEXTUALES de Robe entre comillas,
  ATRIBUIDAS a su fuente (p.ej. "como contó en una entrevista" o el medio/libro
  que aparezca en el bloque del material). NUNCA inventes una cita.
- Enlaza de forma natural discos/canciones/personas del universo (markdown a
  entreinteriores.com).
- Solo esta sección, sin intro ni cierre del artículo entero.
Devuelve JSON {{"body_md": "<la sección en markdown>"}}.
"""
    data = _chat(client, _FLAGSHIP_SYS.format(subject=subject), user, max_tokens=2500)
    body = data.get("body_md", "") if isinstance(data, dict) else ""
    return strip_ai_tells(body) or body


def _meta(client: OpenAI, subject: str, body: str) -> dict:
    data = _chat(
        client, "Generas metadatos SEO. JSON.",
        f"Para este artículo sobre {subject}, devuelve JSON con meta_title "
        f"(≤60 chars, '{subject}' al inicio, 3ª persona, sin Entre Interiores) y "
        f"meta_description (≤155 chars, una frase con el ángulo). Artículo:\n"
        f"{body[:2000]}",
        max_tokens=300,
    )
    return data if isinstance(data, dict) else {}


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
        outline = _outline(client, subject, angle, hard, material)
        log(f"  esquema: {len(outline)} secciones")
        headings = [s["heading"] for s in outline]
        parts = []
        for s in outline:
            sec = _write_section(client, subject, s, headings, hard, material)
            if sec.strip():
                parts.append(sec.strip())
            log(f"  · {s['heading']} ({len(sec)} chars)")
        body = "\n\n".join(parts)
        log(f"  borrador ensamblado: {len(body)} chars")
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

        meta = _meta(client, subject, body)
        schema = {
            "@context": "https://schema.org",
            "@type": "Person" if args.entity == "robe" else "MusicGroup",
            "name": subject,
            "url": f"https://entreinteriores.com/{artist.slug}",
        }
        upsert_seo_content(
            db, entity_type="artist", entity_id=artist.id, slug=artist.slug,
            body_md=body, meta_title=(meta.get("meta_title") or "")[:60],
            meta_description=(meta.get("meta_description") or "")[:155],
            schema_jsonld=schema, entities=[], force=True,
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
