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
from scripts.seo.common import MODEL, apply_catalog_check, log, upsert_seo_content
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
    "uses la raya larga.\n"
    "NOMBRA SIEMPRE LAS ENTIDADES (regla dura): cuando menciones una persona, "
    "banda, proyecto, disco, canción o lugar, da su NOMBRE concreto si consta en "
    "el material. JAMÁS te quedes en lo genérico ('su hijo', 'una banda', 'un "
    "disco', 'su grupo') cuando el nombre está disponible (mal: 'su hijo tiene una "
    "banda'; bien: 'su hijo Aarón Romero', y si el material da el nombre del grupo, "
    "cítalo). Nombrar con precisión informa mejor al lector y enriquece las conexiones.\n"
    "CONEXIÓN CON EL SUJETO (regla dura): TODO el artículo gira sobre el sujeto. "
    "Cada sección y CADA párrafo debe conectar EXPLÍCITAMENTE con él; si mencionas "
    "otra canción, disco, persona o lugar, explica su RELACIÓN con el sujeto. "
    "JAMÁS metas un párrafo que no se conecte con el sujeto (p.ej. en una página "
    "de un lugar, no te pongas a hablar de un disco sin atarlo a ese lugar).\n"
    "CONEXIONES: cuando un bloque [CANCIÓN CONECTADA] o [ENTIDADES RELACIONADAS] "
    "indique el MOTIVO de la conexión, EXPLÓTALO: relaciona explícitamente al "
    "sujeto con esa canción/persona/lugar citando ese motivo (es una conexión "
    "verificada del grafo). En cambio, un bloque [AFINIDAD SEMÁNTICA] NO es una "
    "conexión confirmada: úsalo solo si el resto del material la respalda; nunca "
    "afirmes una relación factual basándote únicamente en una afinidad.\n"
    "REGLAS DE CITA (CRÍTICAS, un fan jamás falla en esto): el material mezcla "
    "LETRAS de canciones, TRANSCRIPCIONES de directo (con ruido y palabras "
    "cortadas) y ENTREVISTAS. (1) Distingue SIEMPRE una letra de canción de una "
    "declaración: JAMÁS presentes un verso como algo que Robe 'dijo', 'compartió' "
    "o 'declaró en una entrevista'. Si usas una letra, di de qué CANCIÓN es y "
    "cítala exacta y completa, o no la uses. (2) NUNCA inventes la fuente de una "
    "cita: solo atribuye una frase a un medio/entrevista (La Gaceta, Carne Cruda…) "
    "si esa frase aparece DENTRO del bloque de ESE medio; jamás cojas una frase de "
    "un bloque y le pongas la fuente de otro. (3) No cites texto garbleado de "
    "transcripciones. (4) Usa fechas y datos EXACTOS cuando estén en el material "
    "(el día concreto, no solo el mes)."
)


def _coverage_hint(entity_type: str) -> str:
    """Qué DEBE cubrir el artículo según el tipo (evita páginas escuetas/genéricas)."""
    if entity_type == "person":
        return (
            "COBERTURA OBLIGATORIA: biografía y carrera (orígenes, trayectoria, bandas, "
            "instrumentos, anécdotas) y su papel/etapa en el universo de Extremoduro/Robe. "
            "OBLIGATORIO incluir QUÉ HACE ACTUALMENTE: si el material (p.ej. el [CONTEXTO "
            "ENCICLOPÉDICO]) menciona una banda o proyecto actual, NÓMBRALO explícitamente; una "
            "biografía de un músico sin su actividad actual está INCOMPLETA. Si es un colaborador "
            "o figura EXTERNA al núcleo, dedica la mayor parte a SU propia vida, carrera y "
            "discografía (sus grupos y discos célebres, anécdotas), no solo a su relación con Robe."
        )
    if entity_type in ("theme", "concept"):
        return (
            "COBERTURA OBLIGATORIA: qué significa este tema/concepto en la obra. ES OBLIGATORIO "
            "CITAR TEXTUALMENTE entre 2 y 5 VERSOS del bloque [VERSOS donde aparece...], los más "
            "significativos (no los triviales), entre comillas e indicando la canción. Una página "
            "de un tema/concepto SIN versos citados es un FALLO. Explica cómo Robe trabaja la idea."
        )
    if entity_type == "place":
        return (
            "COBERTURA OBLIGATORIA: la relación REAL del lugar con Robe/Extremoduro y su obra "
            "(canciones, hechos, biografía), citando lo concreto. Cada párrafo conecta con el lugar."
        )
    if entity_type == "band":
        return "COBERTURA: la banda (historia, miembros, discos célebres) y su vínculo con Robe/Extremoduro."
    if entity_type == "album":
        return "COBERTURA: el disco (contexto, grabación, sonido, canciones clave) y su lugar en la trayectoria."
    if entity_type == "song":
        return "COBERTURA: significado de la letra (citando versos), la música y su contexto en el disco."
    return ""


def _section_cap(material: str, tier: str = "standard") -> int:
    """Nº máximo de secciones proporcional al material real (anti-paja). El `tier`
    de engagement sube el techo: los temas que un fan quiere leer a fondo admiten
    MÁS secciones (siempre que el material real las sostenga; el anti-relleno sigue)."""
    n = len(material or "")
    base = 3 if n < 2500 else 4 if n < 6000 else 6 if n < 20000 else 8
    bump = {"premium": 2, "flagship": 4, "cornerstone": 6}.get(tier, 0)
    return min(base + bump, 14)


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


def _outline(client: OpenAI, subject: str, kw_block: str, hard: str, material: str,
             coverage: str = "", tier: str = "standard") -> list[dict]:
    cap = _section_cap(material, tier)
    user = f"""\
Planifica el mejor artículo y MÁS VERAZ de internet sobre {subject}.
{kw_block}
{coverage}
DATOS DUROS:
{hard}

MATERIAL DEL CORPUS (única fuente de hechos):
\"\"\"{material[:80000]}\"\"\"

Propón ENTRE 2 Y {cap} secciones H2, SOLO las que el material real permita llenar
con sustancia (datos, historias, hechos concretos). Si hay poco material, propón
MENOS secciones y más densas: NO inventes secciones de relleno ni temas sin soporte.
Cada sección debe cubrir algo DISTINTO y tratar SOBRE {subject}.
ENCABEZADOS: específicos y con sentido sobre {subject}; NADA de títulos forzados,
genéricos o sin coherencia semántica (mal: «El Rock Transgresivo: Un Género
Extremadura»). Todo el esquema debe girar en torno a {subject}.
Devuelve JSON {{"sections":[{{"heading":"<H2 concreto sobre {subject}>","covers":"<qué cubre, distinto>"}}]}}.
"""
    data = _chat(client, user, max_tokens=1200)
    secs = data.get("sections") if isinstance(data, dict) else None
    return [s for s in (secs or []) if s.get("heading")][:cap]


def _write_section(client: OpenAI, subject: str, section: dict, headings: list[str],
                   hard: str, material: str, kw_block: str, prior: str = "",
                   coverage: str = "", tier: str = "standard") -> str:
    # Longitud proporcional al material Y al tier: los temas premium/flagship
    # admiten secciones más largas (hay más material real que las sostiene).
    scarce = len(material) < 3000
    if tier == "cornerstone":
        words = "320-560" if scarce else "420-720"
    elif tier == "flagship":
        words = "260-460" if scarce else "340-620"
    elif tier == "premium":
        words = "200-360" if scarce else "260-480"
    else:
        words = "120-220" if scarce else "180-380"
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

{coverage}
{prior_block}INSTRUCCIONES:
- Empieza con "## {section['heading']}".
- {words} palabras. SOLO sustancia: fechas, lugares, nombres, anécdotas y hechos
  reales del material. Cero relleno, cero vaguedades, cero frases de transición huecas.
- CONECTA todo con {subject}: cada frase trata sobre {subject}; si mencionas otra
  canción/disco/persona/lugar, explica su relación con {subject}. No te vayas por las ramas.
- NO re-presentes al sujeto ni repitas datos/frases ya escritos arriba.
- Si el material concreto para esta sección es escaso, escribe POCO (incluso 2-3
  frases) pero real; NUNCA rellenes para alargar.
- Si el material trae 1-2 CITAS textuales de Robe, inclúyelas entrecomilladas y
  ATRIBUIDAS a su fuente. Nunca inventes una cita.
- VERSOS: si citas un verso de una canción entre comillas, cópialo LITERAL del
  bloque [LETRA] del material y atribúyelo a esa canción. Si el verso NO está en
  el material, NO lo entrecomilles: parafraséalo o descríbelo. JAMÁS inventes un
  verso ni lo atribuyas a una canción de la que no tienes la letra delante.
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
    # Linter léxico determinista (Eje E): detecta muletillas y palabras
    # distintivas sobre-usadas (el "encapsula ×6" del feedback de la fan) y se
    # las nombra al pulidor para que las quite de forma DIRIGIDA. La entidad del
    # artículo puede repetirse sin penalizar.
    from app.services.text_sanitizer import lexical_repetition_report
    rep = lexical_repetition_report(body, allowed={subject.lower()})
    lexical_task = ""
    if rep.has_problems:
        bits = []
        if rep.overused:
            bits.append(
                "no repitas estas palabras (varíalas con sinónimos o reescribe): "
                + ", ".join(f'"{w}" (aparece {n} veces)' for w, n in rep.overused)
            )
        if rep.burned:
            bits.append(
                "elimina estas muletillas de relleno y di lo concreto en su lugar: "
                + ", ".join(f'"{p}"' for p in rep.burned)
            )
        lexical_task = "3) VARIEDAD LÉXICA: " + "; ".join(bits) + ".\n"
    user = (
        f"Pule este artículo sobre {subject} para que lo firme un fan exigente. "
        "TAREAS, sin añadir NADA nuevo ni inventar:\n"
        "1) Elimina TODA repetición: si una frase, un dato o un encuadre (p.ej. "
        "volver a presentar al sujeto) aparece en más de una sección, deja solo la "
        "primera vez y borra las demás.\n"
        "2) Elimina TODO relleno y vaguedad sin información ('pudo haber', 'resonó', "
        "'dejó huella', 'en resumen', 'a lo largo de', frases de transición huecas).\n"
        + lexical_task +
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
        "voz, el encabezado H2 y los enlaces.\n"
        "VIGILA EN ESPECIAL (errores graves de credibilidad):\n"
        "- CITAS FALSAS: si la sección atribuye una frase a una entrevista o medio "
        "(p.ej. 'en una entrevista con La Gaceta dijo…') y esa frase NO aparece "
        "literalmente dentro del bloque de ESE medio en el material, elimínala o "
        "quita la atribución. Jamás vale mezclar una frase de un bloque con la "
        "fuente de otro.\n"
        "- LETRAS COMO DECLARACIONES: si la sección presenta un verso de una canción "
        "(o texto de un bloque [TRANSCRIPCIÓN]) como algo que Robe 'dijo'/'declaró', "
        "elimínalo (una letra cantada no es una declaración).\n"
        "- VERSOS INVENTADOS: si la sección entrecomilla un verso y lo atribuye a una "
        "canción, y ese verso NO aparece LITERAL en el bloque [LETRA] de esa canción "
        "dentro del material, es una invención: quita las comillas y parafrasea, o "
        "elimina la frase. Un verso citado SIEMPRE debe existir en la letra real.\n"
        "- Texto garbleado de transcripciones: quítalo.\n\n"
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

    coverage = _coverage_hint(entity_type)
    log(f"generando DEEP: {entity_type}/{dossier.subject}")
    outline = _outline(client, dossier.subject, kw_block, dossier.hard_facts, dossier.material, coverage)
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
                             prior="\n\n".join(parts), coverage=coverage)
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

    # Red de seguridad anti-alucinación: corrige errores de catálogo (canción↔
    # álbum↔año) contra la BD antes de persistir. Determinista, no reescribe.
    body = apply_catalog_check(db, body)

    # Gate de RIGOR editorial: una página genérica/floja no se publica. Si se puede
    # tensar, se tensa; si es flojo sin remedio, queda BORRADOR (no se publica).
    try:
        from app.services.editorial_review import review as editorial_review
        v = editorial_review(body, kind=entity_type, subject=dossier.subject)
        if v.verdict == "revise" and v.tightened_body_md:
            body = v.tightened_body_md
            log(f"  rigor: tensado (score {v.score})")
        elif v.verdict == "reject":
            publish = False
            log(f"  rigor RECHAZA (score {v.score}): {'; '.join(v.reasons)} → queda BORRADOR")
    except Exception as exc:  # noqa: BLE001
        log(f"  rigor falló: {exc}", "warn")

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
