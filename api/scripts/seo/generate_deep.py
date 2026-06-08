"""Motor de contenido RAG PROFUNDO por entidad (generaliza el patrón flagship).

A diferencia de los generadores fijos (`generate_person/band/taxonomy_content`),
aquí se investiga TODO el corpus de la entidad (`deep_research.gather_entity_dossier`:
voz de Robe + fuentes por nombre + De Profundis + relaciones) y se escribe con
outline ADAPTATIVO + sección a sección + verificación factual. Opcionalmente
KW-aware: si se pasa --target-keyword, gobierna meta y headings.

Por defecto guarda como BORRADOR (published=False). Con SEO_KEEP_PUBLISHED=1
preserva el estado publicado anterior (refresh en sitio).

Uso:
  python -m scripts.seo.generate_deep --entity-type person --slug inaki-milindris
  python -m scripts.seo.generate_deep --entity-type band --slug marea --target-keyword "marea grupo"
"""
from __future__ import annotations

import argparse
import json
import os

from openai import OpenAI
from sqlalchemy import select, update

from app.db.models import (
    Album, Artist, Band, Concept, Person, Place, SeoContent, Song, Theme,
)
from app.db.session import SessionLocal
from app.services.deep_research import gather_entity_dossier
from app.services.entity_resolver import (
    autolink_corpus, build_corpus_index, load_link_stats,
)
from app.services.text_sanitizer import strip_ai_tells
from scripts.seo.common import MODEL, log, upsert_seo_content
from scripts.seo.generate_flagship import _sanitize_links

_MODELS = {
    "person": Person, "band": Band, "theme": Theme, "place": Place,
    "concept": Concept, "artist": Artist, "album": Album, "song": Song,
}

# Voz editorial en TERCERA persona (no la voz fan del flagship): rigurosa,
# cercana, sin inventar. Robe FALLECIÓ → pasado.
_SYS = (
    "Eres el autor de Entre Interiores, un sitio editorial sobre el universo de "
    "Robe Iniesta y Extremoduro. Escribes en tercera persona, con rigor y "
    "cercanía, sin reverencia mística y SIN inventar datos: si algo no está en "
    "el material, no lo afirmas. Robe falleció en diciembre de 2025: enmárcalo "
    "en pasado. No uses la raya larga."
)


def _chat(client: OpenAI, user: str, *, max_tokens: int, temp: float = 0.5) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": user}],
        temperature=temp, max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


def _outline(client: OpenAI, subject: str, kw_block: str, hard: str, material: str) -> list[dict]:
    user = f"""\
Planifica el artículo MÁS COMPLETO y veraz de internet sobre {subject}.
{kw_block}
DATOS DUROS:
{hard}

MATERIAL DEL CORPUS (única fuente de hechos):
\"\"\"{material[:80000]}\"\"\"

Propón un esquema de 5 a 10 secciones H2 ADAPTADAS a lo que de verdad hay que
contar sobre {subject} (quién es, su papel/etapa, su aportación, anécdotas y
hechos reales del material, su huella). Si hay material de valor que no encaja
en ninguna sección "SEO" pero es interesante, créale su propia sección.
Devuelve JSON {{"sections":[{{"heading":"<H2 concreto>","covers":"<qué cubre>"}}]}}.
"""
    data = _chat(client, user, max_tokens=1200)
    secs = data.get("sections") if isinstance(data, dict) else None
    return [s for s in (secs or []) if s.get("heading")][:10]


def _write_section(client: OpenAI, subject: str, section: dict, headings: list[str],
                   hard: str, material: str, kw_block: str) -> str:
    user = f"""\
Escribe la sección "{section['heading']}" del artículo definitivo sobre {subject}.
Cubre: {section.get('covers', '')}
{kw_block}
Las otras secciones (no repitas su contenido): {', '.join(headings)}

DATOS DUROS:
{hard}

MATERIAL (única fuente de hechos; parafrasea, NO inventes nada que no esté aquí):
\"\"\"{material}\"\"\"

INSTRUCCIONES:
- Empieza con "## {section['heading']}".
- 180-450 palabras, concreto: fechas, lugares, nombres y anécdotas reales del material.
- Si el material trae 1-2 CITAS textuales de Robe, inclúyelas entrecomilladas y
  ATRIBUIDAS a su fuente. Nunca inventes una cita.
- NO escribas enlaces internos (el sistema los añade). Nunca enlaces en el encabezado.
- Solo esta sección. Devuelve JSON {{"body_md":"<markdown>"}}.
"""
    data = _chat(client, user, max_tokens=1800)
    body = data.get("body_md", "") if isinstance(data, dict) else ""
    return strip_ai_tells(body) or body


def _verify_section(client: OpenAI, section_md: str, material: str) -> str:
    """Verifica una sección contra el material: quita afirmaciones no respaldadas."""
    if not section_md.strip():
        return section_md
    user = (
        "Verificador de hechos ESTRICTO. Devuelve JSON {\"body_md\": \"...\"} con la "
        "sección corregida, quitando o suavizando TODA afirmación factual (fechas, "
        "premios, cifras, títulos, formaciones, lugares, colaboraciones, citas, "
        "eventos) que NO conste en el MATERIAL. No inventes ni añadas. Conserva la "
        "voz, el encabezado H2 y los enlaces.\n\n"
        f"MATERIAL:\n\"\"\"{material[:90000]}\"\"\"\n\nSECCIÓN:\n\"\"\"{section_md}\"\"\""
    )
    data = _chat(client, user, max_tokens=1800, temp=0.1)
    v = (data.get("body_md") or "").strip() if isinstance(data, dict) else ""
    return v if len(v) > 100 else section_md


def _meta(client: OpenAI, subject: str, target_kw: str | None, body: str) -> dict:
    kw = f" La keyword objetivo es '{target_kw}', colócala al inicio del título." if target_kw else ""
    return _chat(
        client,
        f"Para este artículo sobre {subject}, devuelve JSON con meta_title "
        f"(<=60 chars, '{subject}' al inicio, 3a persona){kw} y meta_description "
        f"(<=155 chars, una frase con el ángulo).\n\n{body[:1800]}",
        max_tokens=250,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity-type", required=True, choices=list(_MODELS))
    ap.add_argument("--slug", required=True)
    ap.add_argument("--target-keyword", default=None)
    ap.add_argument("--secondary", default=None, help="KW secundarias separadas por ;")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    model = _MODELS[args.entity_type]
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with SessionLocal() as db:
        entity = db.execute(select(model).where(model.slug == args.slug)).scalars().first()
        if not entity:
            log(f"{args.entity_type} '{args.slug}' no encontrado", "err")
            return

        dossier = gather_entity_dossier(db, args.entity_type, entity)
        if len(dossier.material) < 400:
            log(f"corpus escaso para {args.slug} ({len(dossier.material)} chars); "
                "la página será honesta y corta", "warn")

        secondary = [s.strip() for s in (args.secondary or "").split(";") if s.strip()]
        kw_block = ""
        if args.target_keyword:
            kw_block = (
                f"KEYWORD OBJETIVO: «{args.target_keyword}» (úsala con naturalidad "
                "en el título y algún H2). "
                + (f"SECUNDARIAS: {', '.join(secondary)}. " if secondary else "")
                + "Construye los headings teniéndolas en cuenta, pero NO fuerces ni "
                "rellenes: prima el conocimiento real del corpus.\n"
            )

        log(f"generando DEEP: {args.entity_type}/{dossier.subject}")
        outline = _outline(client, dossier.subject, kw_block, dossier.hard_facts, dossier.material)
        if not outline:
            log("el outline salió vacío; abortando", "err")
            return
        headings = [s["heading"] for s in outline]
        full = f"{dossier.hard_facts}\n\n{dossier.material}"
        parts: list[str] = []
        for s in outline:
            sec = _write_section(client, dossier.subject, s, headings,
                                 dossier.hard_facts, dossier.material, kw_block)
            sec = _verify_section(client, sec, full)
            if sec.strip():
                parts.append(sec.strip())
            log(f"  · {s['heading']} ({len(sec)} chars)")

        body = "\n\n".join(parts)
        body = _sanitize_links(body, dossier.allowed_urls)
        body = autolink_corpus(
            body, build_corpus_index(db), max_links=8,
            exclude_slug=entity.slug, link_stats=load_link_stats(),
        )
        log(f"  ensamblado: {len(body)} chars")

        meta = _meta(client, dossier.subject, args.target_keyword, body)
        schema = {
            "@context": "https://schema.org",
            "@type": {"person": "Person", "band": "MusicGroup", "place": "Place"}.get(
                args.entity_type, "Thing"),
            "name": dossier.subject,
        }
        upsert_seo_content(
            db, entity_type=args.entity_type, entity_id=entity.id, slug=entity.slug,
            body_md=body, meta_title=(meta.get("meta_title") or "")[:60],
            meta_description=(meta.get("meta_description") or "")[:155],
            schema_jsonld=schema, entities=[], force=True,
        )
        # Persiste KW objetivo + outline + cobertura (campos del motor profundo).
        db.execute(
            update(SeoContent)
            .where(SeoContent.entity_type == args.entity_type, SeoContent.entity_id == entity.id)
            .values(
                target_keyword=args.target_keyword,
                secondary_keywords=[{"keyword": k} for k in secondary],
                outline=outline,
                sources_count=dossier.sources_count,
                **({"published": True} if args.publish else {}),
            )
        )
        db.commit()
        log(f"  guardado ({'publicado' if args.publish else 'borrador'}) · "
            f"{dossier.sources_count} fuentes del corpus", "ok")


if __name__ == "__main__":
    main()
