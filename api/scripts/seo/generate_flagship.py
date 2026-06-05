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
import re

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
            InterpretationSource.url,
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
    allowed_urls: set[str] = set()
    for kind, title, content, url in rows:
        snippet = (content or "").strip()[:_PER_SOURCE]
        if len(snippet) < 200:
            continue
        u = (url or "").strip()
        # Solo URLs EXTERNAS reales (noticia/vídeo) son enlazables: las internas
        # y sintéticas (entreinteriores.com/_ref/...) NO son páginas y romperían.
        ext = u if (u.startswith("http") and "entreinteriores.com" not in u) else ""
        head = f"[{kind}] {title or ''}" + (f" — FUENTE: {ext}" if ext else "")
        block = f"{head}\n{snippet}"
        if total + len(block) > _TOTAL_CAP:
            break
        chunks.append(block)
        total += len(block)
        if ext:
            allowed_urls.add(ext)
    log(f"material curado: {len(chunks)} fuentes · {total//1000}k chars · "
        f"{len(allowed_urls)} URLs enlazables")
    return "\n\n----\n\n".join(chunks), allowed_urls


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
- NO escribas tú enlaces internos (a entreinteriores.com): solo nombra los
  discos/canciones/personas; el sistema los enlazará. Y NUNCA enlaces dentro del
  encabezado.
- Para un HECHO IMPORTANTE (un homenaje, un evento, un disco señalado) SÍ puedes
  enlazar a una FUENTE EXTERNA que lo cubra (noticia o vídeo), usando ÚNICAMENTE
  las URLs que aparecen tras 'FUENTE:' en el material. No inventes URLs.
- INTERCALAR VÍDEO: si esta sección cubre un momento MUY relevante con un vídeo
  de YouTube asociado en el material (un directo histórico, el homenaje, un
  videoclip clave), intercálalo poniendo su URL de YouTube SOLA en su propia
  línea (sin corchetes ni texto), usando ÚNICAMENTE una URL de YouTube que
  aparezca tras 'FUENTE:' en el material. Como mucho 1 vídeo, y solo si de
  verdad aporta. Si no hay nada muy relevante, no metas vídeo.
- Solo esta sección, sin intro ni cierre del artículo entero.
Devuelve JSON {{"body_md": "<la sección en markdown>"}}.
"""
    data = _chat(client, _FLAGSHIP_SYS.format(subject=subject), user, max_tokens=2500)
    body = data.get("body_md", "") if isinstance(data, dict) else ""
    return strip_ai_tells(body) or body


def _verify_section(client: OpenAI, section_md: str, material: str) -> str:
    """Verifica UNA sección contra el material completo (cabe sin truncar el
    JSON, a diferencia de verificar las 24k de golpe)."""
    if not section_md.strip():
        return section_md
    try:
        data = _chat(
            client,
            "Verificador de hechos ESTRICTO. Devuelve la sección corregida "
            "quitando o suavizando TODA afirmación factual (fechas, años, "
            "premios, cifras, títulos, formaciones, lugares, colaboraciones, "
            "citas, eventos) que NO conste en el MATERIAL. No inventes ni "
            "añadas. Conserva voz, encabezado y enlaces markdown. JSON "
            "{\"body_md\": \"<sección corregida>\"}.",
            f"MATERIAL:\n\"\"\"{material[:95000]}\"\"\"\n\nSECCIÓN:\n\"\"\"{section_md}\"\"\"",
            max_tokens=2500, temp=0.1,
        )
        v = (data.get("body_md") or "").strip() if isinstance(data, dict) else ""
        return v if len(v) > 120 else section_md
    except Exception as e:  # noqa: BLE001
        log(f"    verify sección falló ({e}); sin verificar", "warn")
        return section_md


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _sanitize_links(body: str, allowed_ext: set[str]) -> str:
    """Limpia enlaces: (1) NUNCA en headings; (2) quita los internos escritos por
    el LLM (el autolink reañade solo los reales en el cuerpo); (3) externos SOLO
    si están en el material (evita rotos/inventados)."""
    # Limpia restos de cabeceras del material que el LLM pueda haber copiado.
    body = re.sub(r"\s*[—-]?\s*FUENTE:\s*\S+", "", body)
    out = []
    for line in body.split("\n"):
        if line.lstrip().startswith("#"):
            out.append(_LINK_RE.sub(r"\1", line))  # headings sin enlaces
            continue
        # Línea que es SOLO una URL = vídeo intercalado: se conserva únicamente
        # si es un YouTube real del material (si no, se descarta para no embeber
        # un vídeo inventado/equivocado).
        bare = line.strip()
        if re.fullmatch(r"https?://\S+", bare):
            is_yt = "youtube.com" in bare or "youtu.be" in bare
            out.append(line if (is_yt and bare in allowed_ext) else "")
            continue

        def repl(m):
            text, url = m.group(1), m.group(2).strip()
            if url.startswith("/") or "entreinteriores.com" in url:
                return text  # interno: lo añade autolink_corpus si procede
            if url.startswith("http"):
                return m.group(0) if url in allowed_ext else text
            return text

        out.append(_LINK_RE.sub(repl, line))
    return "\n".join(out)


def _faq(client: OpenAI, subject: str, material: str) -> str:
    """Sección de Preguntas frecuentes (factuales y no factuales), basada solo
    en el material y verificada. SIN enlaces ni vídeos: la pregunta es un H3 y
    la respuesta un párrafo."""
    user = f"""\
Genera la sección final de PREGUNTAS FRECUENTES sobre {subject}.
6-9 preguntas que la gente se hace de verdad: unas FACTUALES (fechas, lugares,
discos, datos básicos) y otras NO factuales (por qué importa, qué lo hacía
único, su forma de ser). Respuestas BREVES (1-3 frases), concretas y basadas
SOLO en el MATERIAL; no inventes nada.
FORMATO: cada pregunta es un encabezado H3 ("### ¿pregunta?") y la respuesta va
debajo como un párrafo normal. NINGÚN enlace ni vídeo en toda la sección.

MATERIAL:
\"\"\"{material[:90000]}\"\"\"

Devuelve JSON {{"body_md": "## Preguntas frecuentes\\n\\n### ¿pregunta?\\n\\nrespuesta\\n\\n### ¿pregunta?\\n\\nrespuesta..."}}.
"""
    data = _chat(client, _FLAGSHIP_SYS.format(subject=subject), user,
                 max_tokens=2200, temp=0.4)
    body = data.get("body_md", "") if isinstance(data, dict) else ""
    body = _verify_section(client, body, material)
    body = strip_ai_tells(body) or body
    # Sin NINGUNA referencia en la FAQ: quita enlaces markdown y URLs sueltas.
    body = _LINK_RE.sub(r"\1", body)
    body = re.sub(r"(?m)^\s*https?://\S+\s*$", "", body)
    return body


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
        material, allowed_urls = _gather_material(db)
        distilled = format_distilled_block(fetch_distilled_for_artist(db, artist.id))
        material = f"{material}\n\n---- CONSENSO DESTILADO ----\n{distilled}"

        log(f"generando FLAGSHIP: {subject}")
        outline = _outline(client, subject, angle, hard, material)
        log(f"  esquema: {len(outline)} secciones")
        headings = [s["heading"] for s in outline]
        parts = []
        full_material = f"{hard}\n\n{material}"
        for s in outline:
            sec = _write_section(client, subject, s, headings, hard, material)
            sec = _verify_section(client, sec, full_material)  # anti-alucinación
            if sec.strip():
                parts.append(sec.strip())
            log(f"  · {s['heading']} ({len(sec)} chars)")
        # Sección de Preguntas frecuentes al final.
        faq = _faq(client, subject, material)
        if faq.strip():
            parts.append(faq.strip())
            log("  · Preguntas frecuentes añadida")
        body = "\n\n".join(parts)
        log(f"  ensamblado y verificado: {len(body)} chars")
        if len(body) < 3000:
            log(f"  cuerpo corto ({len(body)} chars); revisar", "warn")

        # Limpieza de enlaces: sin enlaces en headings, internos fuera (los pone
        # el autolink), externos solo del material. Luego enlazado interno.
        body = _sanitize_links(body, allowed_urls)
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
        db.commit()  # upsert_seo_content NO commitea; el caller debe hacerlo.
        log("  guardado (borrador)", "ok")
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
