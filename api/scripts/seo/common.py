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
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

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
from app.services.voice import build_system_prompt

MODEL = "gpt-4o"
# Voz por defecto del sitio. Los generadores con voz propia (persona/grupo/lugar/
# tema, etc.) pasan su `system_prompt` a call_llm. Ver app/services/voice.py.
SYSTEM_PROMPT = build_system_prompt(family="seo")


def _data_dir_candidates() -> list[str]:
    """Rutas posibles del dir data/ (contenedor `/app/data` y repo local)."""
    here = os.path.dirname(os.path.abspath(__file__))  # .../api/scripts/seo
    return [
        "/app/data",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data")),  # repo/data
        os.path.normpath(os.path.join(here, "..", "..", "data")),
    ]


@lru_cache(maxsize=1)
def _load_robe_quotes() -> tuple[dict[str, Any], ...]:
    """Citas VERIFICADAS de Robe desde data/robe_quotes.yaml (cacheado)."""
    if yaml is None:
        return ()
    for d in _data_dir_candidates():
        path = os.path.join(d, "robe_quotes.yaml")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                return tuple(
                    q for q in (data.get("quotes") or [])
                    if isinstance(q, dict) and q.get("verified") and q.get("text")
                )
            except Exception:  # noqa: BLE001
                return ()
    return ()


def tone_quotes_for(
    tags: list[str] | None = None, *, k: int = 3, seed: str = ""
) -> list[str]:
    """Hasta k citas de Robe para calibrar el tono (piezas en 1ª persona).

    Con `tags` prioriza las que solapan temáticamente; sin tags, rota de forma
    DETERMINISTA por `seed` (sin azar, para que la regeneración sea reproducible).
    """
    quotes = list(_load_robe_quotes())
    if not quotes:
        return []
    tagset = {t.lower() for t in (tags or [])}
    if tagset:
        def _score(q: dict) -> int:
            return len(tagset & {t.lower() for t in (q.get("tags") or [])})
        quotes.sort(key=lambda q: (-_score(q), q.get("text", "")))
        return [q["text"] for q in quotes[:k]]
    quotes.sort(key=lambda q: q.get("text", ""))
    offset = (sum(ord(c) for c in seed) % len(quotes)) if seed else 0
    rotated = quotes[offset:] + quotes[:offset]
    return [q["text"] for q in rotated[:k]]


_VERIFY_SYS = (
    "Eres un verificador de hechos ESTRICTO de Entre Interiores. Te doy el "
    "MATERIAL (datos verificados, fuentes y consenso fan que se usaron) y un "
    "ARTÍCULO. Devuelve el artículo corregido eliminando o suavizando TODA "
    "afirmación FACTUAL concreta —fechas, años, premios ('Medalla de Oro de "
    "Bellas Artes 2024'), cifras, títulos de canciones/discos, formaciones, "
    "lugares, colaboraciones, eventos— que NO aparezca o no se deduzca "
    "CLARAMENTE del material. Reglas: (1) si un dato no consta en el material, "
    "quítalo o reescribe la frase sin él (mejor sin el dato que uno inventado); "
    "(2) NO añadas información nueva; (3) CONSERVA el estilo, la voz, la opinión, "
    "los encabezados H2/H3 y los enlaces markdown tal cual: solo tocas los "
    "hechos no respaldados; (4) no acortes por acortar. Devuelve SOLO JSON: "
    "{\"body_md\": \"<artículo corregido>\"}."
)


def _verify_body(client: OpenAI, body_md: str, material: str) -> str:
    """Verificación factual del cuerpo contra el material usado. Quita lo no
    respaldado (anti-alucinación). Si falla, devuelve el original."""
    if not body_md.strip():
        return body_md
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _VERIFY_SYS},
                {"role": "user", "content":
                    f"MATERIAL (única fuente de verdad):\n\"\"\"{material[:9000]}\"\"\"\n\n"
                    f"ARTÍCULO:\n\"\"\"{body_md}\"\"\""},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=4000,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        verified = (data.get("body_md") or "").strip()
        return verified if len(verified) > 1000 else body_md
    except Exception as e:  # noqa: BLE001
        log(f"  verificación factual falló ({e}); cuerpo sin verificar", "warn")
        return body_md


def apply_catalog_check(db: Session, body_md: str) -> str:
    """Corrige in-place errores de catálogo (canción↔álbum↔año) contra la BD,
    de forma determinista y quirúrgica (no reescribe). Para generadores que NO
    pasan por `call_llm` (deep/flagship). Best-effort: ante fallo, devuelve el
    cuerpo intacto."""
    if not body_md:
        return body_md
    try:
        from app.services.fact_check import check_body, correct_body
        rep = check_body(db, body_md, use_web=False)
        if not rep.autofixes:
            return body_md
        fixed, skipped = correct_body(db, body_md, rep)
        n = len(rep.autofixes) - len(skipped)
        if n:
            log(f"  fact-check catálogo: {n} hecho(s) corregido(s) contra BD")
        return fixed
    except Exception as e:  # noqa: BLE001
        log(f"  fact-check catálogo falló ({e}); cuerpo sin tocar", "warn")
        return body_md


def call_llm(
    client: OpenAI, user_prompt: str, *, system_prompt: str | None = None,
    verify: bool = True, db: Session | None = None,
) -> dict[str, Any]:
    """Invoca GPT-4o con structured output JSON. Lanza ValueError si JSON inválido.

    system_prompt: override de la voz por defecto. Las fichas de persona/grupo
    pasan uno con foco de sujeto (ver app.services.voice.build_system_prompt).
    verify: si True (por defecto), pasa el body_md por una verificación factual
    contra el material del prompt (caza fabricaciones tipo 'Medalla de Oro 2024').
    db: si se pasa, añade ADEMÁS la verificación canónica contra BD (corrige
    canción↔álbum↔año contra el catálogo real, determinista). Retrocompatible:
    sin db, comportamiento idéntico al de antes.
    """
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.65,  # algo más de expresividad para que asome la voz de fan
        max_tokens=4000,
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("LLM devolvió contenido vacío")
    try:
        out = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido del LLM: {e}; raw={content[:200]}") from e
    if verify and isinstance(out.get("body_md"), str):
        body = out["body_md"]
        # Verdad dura del catálogo (canción↔álbum↔año) cuando hay sesión. Barato
        # y determinista (use_web=False); no añade latencia de red.
        if db is not None:
            try:
                from app.services.fact_check import check_body, correct_body
                rep = check_body(db, body, material=user_prompt, use_web=False)
                if rep.autofixes:
                    body = correct_body(db, body, rep, material=user_prompt)
            except Exception as e:  # noqa: BLE001
                log(f"  verificación canónica BD falló ({e}); sigo con material", "warn")
        out["body_md"] = _verify_body(client, body, user_prompt)
    return out


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
    sources: list[dict] | None = None,
    force: bool = False,
) -> int:
    """Inserta o actualiza la fila correspondiente. Si ya existe y --force,
    sobrescribe body_md y reset reviewed_at + published. Si no force, falla."""
    # Saneado anti marcas de IA (em-dash, etc.) — red de seguridad por si el
    # LLM ignoró el SYSTEM_PROMPT.
    from app.services.text_sanitizer import (
        enforce_name_policy,
        normalize_headings,
        strip_ai_tells,
    )
    body_md = strip_ai_tells(body_md) or body_md
    body_md = normalize_headings(body_md) or body_md
    meta_title = strip_ai_tells(meta_title)
    meta_description = strip_ai_tells(meta_description)
    # El schema_jsonld NO pasa por strip_ai_tells (es un dict) y era el hueco por el
    # que se colaba "Robe Iniesta". Se sanea el JSON serializado antes de escribir.
    if schema_jsonld:
        import json as _json
        _raw = _json.dumps(schema_jsonld, ensure_ascii=False)
        _clean = enforce_name_policy(_raw)
        if _clean != _raw:
            schema_jsonld = _json.loads(_clean)
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
    # Enlazado interno automático: enlaza hasta 4 menciones a entidades del
    # corpus (las más relevantes) a su página local. No enlaza la propia
    # página de este seo_content.
    if body_md:
        from app.services.entity_resolver import (
            autolink_corpus,
            autolink_sources,
            build_corpus_index,
            load_link_stats,
        )
        body_md = autolink_corpus(
            body_md, build_corpus_index(db), max_links=4,
            exclude_slug=slug, link_stats=load_link_stats(),
        )
        # Enlazado externo a medios citados: si una fuente (Mondo Sonoro, Efe
        # Eme…) se nombra en el cuerpo, enlaza el medio a su url de origen.
        if sources:
            body_md = autolink_sources(body_md, sources)

    update_set = {
        "slug": slug,
        "body_md": body_md,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "schema_jsonld": schema_jsonld,
        "entities": ents,
        "generated_at": datetime.now(timezone.utc),
        "generated_by": MODEL,
    }
    # Por defecto, regenerar una ficha la vuelve a borrador (revisión humana).
    # Con SEO_KEEP_PUBLISHED=1 se PRESERVA el estado publicado al regenerar
    # (para el rewrite masivo de lo ya publicado: no tumba las páginas y el
    # contenido nuevo ya va verificado por call_llm).
    if os.environ.get("SEO_KEEP_PUBLISHED") != "1":
        update_set["reviewed_at"] = None
        update_set["published"] = False
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
            set_=update_set,
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
            "url": r.url or "",
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
            "url": r.url or "",
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
            "url": r.url or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:2000],
        }
        for r in rows
    ]


def fetch_sources_for_entity(
    db: Session, names: list[str], *, limit: int = 12
) -> list[dict[str, Any]]:
    """Fan-content/prensa que MENCIONA a una persona/grupo por su nombre.

    Hasta ahora las fuentes solo se ligaban a canciones (referenced_song_ids);
    esto permite traer lo que foros/prensa dicen de una PERSONA o GRUPO (p.ej.
    el papel de Uoho en la ruptura). Busca por ILIKE en content_clean (con el
    índice trigram si existe), priorizando prensa (for_seo_only)."""
    from sqlalchemy import or_
    clean = [
        n.strip() for n in names
        if n and (len(n.strip()) >= 6 or " " in n.strip())  # evita tokens cortos ambiguos
    ]
    if not clean:
        return []
    conds = [InterpretationSource.content_clean.ilike(f"%{n}%") for n in clean]
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(InterpretationSource.kind != "genius_annotation")
            .where(or_(*conds))
            .order_by(InterpretationSource.for_seo_only.desc(), InterpretationSource.id)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "url": r.url or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:2500],
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


# --------------------------------------------------------------------------- #
# Conocimiento fan DESTILADO (SongInterpretation.payload). Mismo criterio de
# confianza que reranker.fetch_song_context (high/medium). Esto es lo que da
# PROFUNDIDAD y alma al contenido: el consenso de lo que los fans entienden de
# cada canción, ya destilado y con citación. Antes solo lo usaba la búsqueda
# privada; ahora también la generación de contenido público.
# --------------------------------------------------------------------------- #
def fetch_distilled_for_song(db: Session, song_id: int) -> dict[str, Any] | None:
    from app.db.models import SongInterpretation
    interp = (
        db.query(SongInterpretation)
        .filter(SongInterpretation.song_id == song_id)
        .first()
    )
    if not interp or interp.confidence not in ("high", "medium"):
        return None
    p = interp.payload or {}
    if not (p.get("fan_consensus") or p.get("themes") or p.get("key_metaphors")):
        return None
    return {
        "themes": p.get("themes") or [],
        "key_metaphors": p.get("key_metaphors") or [],
        "fan_consensus": p.get("fan_consensus") or "",
        "confidence": interp.confidence,
    }


def fetch_distilled_for_album(db: Session, album_id: int, *, limit: int = 14) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Song.id, Song.title).where(Song.album_id == album_id).order_by(Song.track_number)
    ).all()
    out: list[dict[str, Any]] = []
    for sid, title in rows:
        d = fetch_distilled_for_song(db, sid)
        if d:
            out.append({"song": title, **d})
        if len(out) >= limit:
            break
    return out


def fetch_distilled_for_artist(db: Session, artist_id: int, *, limit: int = 14) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Song.id, Song.title)
        .join(Album, Song.album_id == Album.id)
        .where(Album.artist_id == artist_id)
    ).all()
    out: list[dict[str, Any]] = []
    for sid, title in rows:
        d = fetch_distilled_for_song(db, sid)
        if d and d.get("fan_consensus"):
            out.append({"song": title, **d})
        if len(out) >= limit:
            break
    return out


def format_distilled_block(distilled: dict[str, Any] | list[dict[str, Any]] | None) -> str:
    """Bloque para el prompt con el consenso fan destilado.

    Acepta un dict (canción) o una lista de dicts (álbum/artista). Etiquetado
    para que el LLM lo use como FUNDAMENTO interpretativo, no como texto a
    recitar.
    """
    if not distilled:
        return ""
    items = [distilled] if isinstance(distilled, dict) else distilled
    if not items:
        return ""
    header = (
        "CONSENSO FAN DESTILADO (lo que la comunidad de fans entiende de estas "
        "canciones, ya destilado y consensuado). Úsalo como FUNDAMENTO y GOBIERNO "
        "de tu lectura interpretativa: tu interpretación debe nacer de aquí (o de "
        "los versos y lo que dijo Robe), no de tópico literario. Intégralo y "
        "parafraséalo con tu voz; NO lo copies textual ni lo recites como si fuera "
        "la letra. REGLA CLAVE: si aquí NO hay consenso sobre un verso (o es "
        "escaso), NO inventes una lectura honda ni la disfraces de metáfora; sé "
        "descriptivo y honesto ('a mí me suena a...', o cuéntalo literal), o elige "
        "otro ángulo con más fundamento. Y NO llames 'metáfora' a lo que es una "
        "afirmación directa (una crítica social explícita es literal, no figurada)."
    )
    blocks: list[str] = []
    for d in items:
        lines: list[str] = []
        if d.get("song"):
            lines.append(f"· {d['song']}")
        if d.get("themes"):
            lines.append("  Temas: " + ", ".join(str(t) for t in d["themes"][:6]))
        for m in (d.get("key_metaphors") or [])[:4]:
            if isinstance(m, dict) and m.get("phrase"):
                meaning = m.get("meaning") or ""
                lines.append(f"  Metáfora: «{m['phrase']}» -> {meaning}")
        if d.get("fan_consensus"):
            lines.append("  " + d["fan_consensus"])
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return header + "\n" + "\n\n".join(blocks)
