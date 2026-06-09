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
    "Eres un fan de toda la vida de Extremoduro, Robe y el punk-rock que escribe "
    "para Entre Interiores. Te conoces la obra al dedillo y escribes con pasión, "
    "calle y criterio, en tercera persona, sin reverencia hueca ni misticismo. "
    "REGLA DE ORO: cada frase aporta un DATO, una historia o una idea CONCRETA del "
    "material. Prohibido el relleno y las vaguedades de relleno tipo 'pudo haber', "
    "'sin duda', 'resonó en la comunidad', 'dejó una huella imborrable', 'marcó un "
    "antes y un después', 'a lo largo de su trayectoria', 'en resumen', 'en última "
    "instancia'. Si no hay material para algo, NO lo rellenas: mejor corto y con "
    "chicha que largo y vacío. NUNCA inventas (ni vivencias en primera persona). "
    "NUNCA repites una frase, un dato ni el mismo encuadre dos veces (no vuelvas a "
    "presentar al sujeto en cada sección). Robe falleció en diciembre de 2025. "
    "Refiérete a él como 'Robe' (o 'Roberto Iniesta'), NUNCA 'Robe Iniesta'. No "
    "uses la raya larga."
)


def _section_cap(material: str) -> int:
    """Nº máximo de secciones proporcional al material real (anti-paja)."""
    n = len(material or "")
    if n < 2500:
        return 3
    if n < 6000:
        return 4
    if n < 20000:
        return 6
    return 8


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
    cap = _section_cap(material)
    user = f"""\
Planifica el mejor artículo y MÁS VERAZ de internet sobre {subject}.
{kw_block}
DATOS DUROS:
{hard}

MATERIAL DEL CORPUS (única fuente de hechos):
\"\"\"{material[:80000]}\"\"\"

Propón ENTRE 2 Y {cap} secciones H2, SOLO las que el material real permita llenar
con sustancia (datos, historias, hechos concretos). Si hay poco material, propón
MENOS secciones y más densas: NO inventes secciones de relleno ni temas sin
soporte. Cada sección debe cubrir algo DISTINTO (sin solaparse con las demás).
Devuelve JSON {{"sections":[{{"heading":"<H2 concreto>","covers":"<qué cubre, distinto>"}}]}}.
"""
    data = _chat(client, user, max_tokens=1200)
    secs = data.get("sections") if isinstance(data, dict) else None
    return [s for s in (secs or []) if s.get("heading")][:cap]


def _write_section(client: OpenAI, subject: str, section: dict, headings: list[str],
                   hard: str, material: str, kw_block: str, prior: str = "") -> str:
    # Longitud proporcional al material: poco material → secciones cortas y densas.
    words = "120-220" if len(material) < 3000 else "180-380"
    prior_block = ""
    if prior.strip():
        prior_block = (
            "YA ESCRITO en secciones anteriores (el lector ya lo ha leído; NO lo "
            "repitas, ni los datos ni el encuadre, ni vuelvas a presentar al "
            f"sujeto):\n\"\"\"{prior[-4000:]}\"\"\"\n\n"
        )
    user = f"""\
Escribe la sección "{section['heading']}" del artículo sobre {subject}.
Cubre (y SOLO esto): {section.get('covers', '')}
{kw_block}
Otras secciones del artículo (no invadas su tema): {', '.join(headings)}

DATOS DUROS:
{hard}

MATERIAL (única fuente de hechos; parafrasea, NO inventes nada que no esté aquí):
\"\"\"{material}\"\"\"

{prior_block}INSTRUCCIONES:
- Empieza con "## {section['heading']}".
- {words} palabras. SOLO sustancia: fechas, lugares, nombres, anécdotas y hechos
  reales del material. Cero relleno, cero vaguedades, cero frases de transición huecas.
- NO re-presentes al sujeto ni repitas datos/frases ya escritos arriba.
- Si el material concreto para esta sección es escaso, escribe POCO (incluso 2-3
  frases) pero real; NUNCA rellenes para alargar.
- Si el material trae 1-2 CITAS textuales de Robe, inclúyelas entrecomilladas y
  ATRIBUIDAS a su fuente. Nunca inventes una cita.
- NO escribas enlaces internos (el sistema los añade). Nunca enlaces en el encabezado.
- Solo esta sección. Devuelve JSON {{"body_md":"<markdown>"}}.
"""
    data = _chat(client, user, max_tokens=1800)
    body = data.get("body_md", "") if isinstance(data, dict) else ""
    return strip_ai_tells(body) or body


def _polish(client: OpenAI, subject: str, body: str) -> str:
    """Pase final anti-repetición y anti-paja sobre el artículo completo."""
    if len(body.strip()) < 200:
        return body
    user = (
        f"Pule este artículo sobre {subject} para que lo firme un fan exigente. "
        "DOS tareas, sin añadir NADA nuevo ni inventar:\n"
        "1) Elimina TODA repetición: si una frase, un dato o un encuadre (p.ej. "
        "volver a presentar al sujeto) aparece en más de una sección, deja solo la "
        "primera vez y borra las demás.\n"
        "2) Elimina TODO relleno y vaguedad sin información ('pudo haber', 'resonó', "
        "'dejó huella', 'en resumen', 'a lo largo de', frases de transición huecas).\n"
        "Si tras quitar la paja una sección se queda sin sustancia, redúcela a lo "
        "que aporte de verdad o elimínala entera (encabezado incluido). Conserva los "
        "encabezados '## ' que sobrevivan, los enlaces markdown y las citas. Mejor "
        "corto y con chicha que largo y vacío. Devuelve JSON {\"body_md\":\"...\"}.\n\n"
        f"ARTÍCULO:\n\"\"\"{body}\"\"\""
    )
    data = _chat(client, user, max_tokens=4000, temp=0.2)
    v = (data.get("body_md") or "").strip() if isinstance(data, dict) else ""
    return v if len(v) > 200 else body


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


def generate_for_entity(
    db,
    client: OpenAI,
    entity_type: str,
    entity,
    *,
    target_keyword: str | None = None,
    secondary: list[str] | None = None,
    publish: bool = False,
    corpus_index=None,
    link_stats=None,
) -> bool:
    """Genera contenido deep-RAG para UNA entidad y hace upsert + persiste KW/outline.

    Reutilizable por el orquestador del backfill: acepta `corpus_index` y
    `link_stats` ya construidos (se construyen una vez para todo el lote) para no
    rehacerlos por entidad. Devuelve True si guardó, False si abortó (outline vacío).
    El estado publicado lo gobierna `SEO_KEEP_PUBLISHED` en `upsert_seo_content`;
    `publish=True` lo fuerza a publicado además.
    """
    secondary = secondary or []
    dossier = gather_entity_dossier(db, entity_type, entity)
    if len(dossier.material) < 400:
        log(f"corpus escaso para {entity.slug} ({len(dossier.material)} chars); "
            "la página será honesta y corta", "warn")

    kw_block = ""
    if target_keyword:
        kw_block = (
            f"KEYWORD OBJETIVO: «{target_keyword}» (úsala con naturalidad "
            "en el título y algún H2). "
            + (f"SECUNDARIAS: {', '.join(secondary)}. " if secondary else "")
            + "Construye los headings teniéndolas en cuenta, pero NO fuerces ni "
            "rellenes: prima el conocimiento real del corpus.\n"
        )

    log(f"generando DEEP: {entity_type}/{dossier.subject}")
    outline = _outline(client, dossier.subject, kw_block, dossier.hard_facts, dossier.material)
    if not outline:
        log("el outline salió vacío; abortando", "err")
        return False
    headings = [s["heading"] for s in outline]
    full = f"{dossier.hard_facts}\n\n{dossier.material}"
    parts: list[str] = []
    for s in outline:
        # `prior` = lo ya escrito → cada sección evita repetir datos/encuadre.
        sec = _write_section(client, dossier.subject, s, headings,
                             dossier.hard_facts, dossier.material, kw_block,
                             prior="\n\n".join(parts))
        sec = _verify_section(client, sec, full)
        if sec.strip():
            parts.append(sec.strip())
        log(f"  · {s['heading']} ({len(sec)} chars)")

    body = "\n\n".join(parts)
    # Pase final anti-repetición/anti-paja sobre el artículo completo.
    before = len(body)
    body = _polish(client, dossier.subject, body)
    log(f"  pulido: {before} → {len(body)} chars")
    body = _sanitize_links(body, dossier.allowed_urls)
    body = autolink_corpus(
        body, corpus_index if corpus_index is not None else build_corpus_index(db),
        max_links=8, exclude_slug=entity.slug,
        link_stats=link_stats if link_stats is not None else load_link_stats(),
    )
    log(f"  ensamblado: {len(body)} chars")

    meta = _meta(client, dossier.subject, target_keyword, body)
    schema = {
        "@context": "https://schema.org",
        "@type": {"person": "Person", "band": "MusicGroup", "place": "Place"}.get(
            entity_type, "Thing"),
        "name": dossier.subject,
    }
    upsert_seo_content(
        db, entity_type=entity_type, entity_id=entity.id, slug=entity.slug,
        body_md=body, meta_title=(meta.get("meta_title") or "")[:60],
        meta_description=(meta.get("meta_description") or "")[:155],
        schema_jsonld=schema, entities=[], force=True,
    )
    # Persiste KW objetivo + outline + cobertura (campos del motor profundo).
    db.execute(
        update(SeoContent)
        .where(SeoContent.entity_type == entity_type, SeoContent.entity_id == entity.id)
        .values(
            target_keyword=target_keyword,
            secondary_keywords=[{"keyword": k} for k in secondary],
            outline=outline,
            sources_count=dossier.sources_count,
            **({"published": True} if publish else {}),
        )
    )
    db.commit()
    keep = os.environ.get("SEO_KEEP_PUBLISHED") == "1"
    estado = "publicado" if (publish or keep) else "borrador"
    log(f"  guardado ({estado}) · {dossier.sources_count} fuentes del corpus", "ok")
    return True


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
        secondary = [s.strip() for s in (args.secondary or "").split(";") if s.strip()]
        generate_for_entity(
            db, client, args.entity_type, entity,
            target_keyword=args.target_keyword, secondary=secondary,
            publish=args.publish,
        )


if __name__ == "__main__":
    main()
