"""Dossier del corpus por entidad para el motor de contenido RAG profundo.

Hoy los generadores SEO (persona/grupo/lugar/tema...) hacen un RAG superficial:
buscan fuentes por nombre y poco más. Aquí se ENSAMBLA todo el conocimiento del
corpus sobre una entidad, combinando:

  - Datos duros de la entidad (campos del modelo + relaciones).
  - Retrieval semántico de la VOZ DE ROBE (robe_voice_v1) sobre el tema.
  - Fuentes que la mencionan por nombre (fan-content, prensa, entrevistas,
    transcripciones de Juancares) vía ILIKE — captura menciones que el match por
    canción no ve (p.ej. las 63 menciones de "Setién" en Juancares).
  - Hechos verificados de data/reference/*.md filtrados a la entidad.

Devuelve `material` (texto para el prompt), `hard_facts`, `allowed_urls` (URLs
externas reales enlazables) y `sources_count` (cobertura).
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Album, Artist, Band, BandMembership, Concept, Person, Place, Song, Theme,
)
from scripts.seo.common import (
    fetch_sources_for_entity, format_sources_block,
)

logger = logging.getLogger(__name__)

_PER_SOURCE = 2800
_TOTAL_CAP = 100_000


@dataclass
class Dossier:
    subject: str
    names: list[str]
    hard_facts: str
    material: str
    allowed_urls: set[str] = field(default_factory=set)
    sources_count: int = 0


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


def _reference_facts(names: list[str]) -> list[str]:
    """Párrafos/líneas de data/reference/*.md que mencionan a la entidad."""
    here = Path(__file__).resolve()
    candidates = [
        Path("/app/data/reference"),
        here.parents[3] / "data" / "reference",
        here.parents[2] / "data" / "reference",
    ]
    ref_dir = next((p for p in candidates if p.exists()), None)
    if not ref_dir:
        return []
    keys = [_norm(n) for n in names if len(n) >= 5]
    out: list[str] = []
    for md in sorted(ref_dir.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            nline = _norm(line)
            if len(line.strip()) > 40 and any(k in nline for k in keys):
                out.append(f"[De Profundis] {line.strip().lstrip('-* ')}")
    return out


def entity_names(db: Session, entity_type: str, entity) -> tuple[str, list[str]]:
    """Nombre canónico + alias para buscar la entidad en el corpus."""
    if entity_type == "person":
        subject = entity.stage_name or entity.full_name
        names = [n for n in {entity.full_name, entity.stage_name} if n]
    elif entity_type == "band":
        subject = entity.name
        names = [entity.name]
    elif entity_type in ("theme", "place", "concept"):
        subject = entity.name
        names = [entity.name]
    elif entity_type == "artist":
        subject = entity.name
        names = [entity.name]
    elif entity_type == "album":
        subject = entity.title
        names = [entity.title]
    elif entity_type == "song":
        subject = entity.title
        names = [entity.title]
    else:
        subject = getattr(entity, "name", "") or getattr(entity, "title", "")
        names = [subject]
    return subject, [n for n in names if n]


def _hard_facts(db: Session, entity_type: str, entity, subject: str) -> str:
    facts: list[str] = []
    if entity_type == "person":
        bits = [f"{subject} (nombre real {entity.full_name})."]
        if entity.birth_date:
            bits.append(f"Nacimiento: {entity.birth_date}"
                        + (f" en {entity.birth_place}" if entity.birth_place else "") + ".")
        if entity.death_date:
            bits.append(f"Fallecimiento: {entity.death_date}.")
        if entity.instruments:
            ins = ", ".join(i.get("name", "") for i in entity.instruments if i.get("name"))
            if ins:
                bits.append(f"Instrumentos: {ins}.")
        # Membresías (rol/era en bandas del universo).
        rows = db.execute(
            select(BandMembership, Artist)
            .join(Artist, BandMembership.artist_id == Artist.id)
            .where(BandMembership.person_id == entity.id)
        ).all()
        for m, art in rows:
            era = f" ({m.era})" if m.era else ""
            facts.append(f"{subject} fue {m.role or 'miembro'} de {art.name}{era}.")
        facts.insert(0, " ".join(bits))
        if entity.bio_short:
            facts.append(entity.bio_short.strip())
    elif entity_type == "band":
        bits = [f"{subject} ({entity.kind})."]
        if entity.founded_year:
            bits.append(f"Fundación: {entity.founded_year}.")
        if entity.dissolved_year:
            bits.append(f"Disolución: {entity.dissolved_year}.")
        if entity.related_note:
            bits.append(entity.related_note)
        facts.append(" ".join(bits))
        if entity.bio_short:
            facts.append(entity.bio_short.strip())
    elif entity_type == "album":
        art = db.get(Artist, entity.artist_id)
        facts.append(f"«{entity.title}» ({art.name if art else ''}, {entity.year}), tipo {entity.kind}.")
    elif entity_type == "song":
        al = getattr(entity, "album", None)
        art = getattr(al, "artist", None) if al else None
        facts.append(
            f"«{entity.title}» es una canción de {art.name if art else 'Extremoduro'}"
            + (f", del disco «{al.title}» ({al.year})" if al else "") + "."
        )
        themes = [t.name for t in (getattr(entity, "themes", None) or []) if getattr(t, "name", None)]
        if themes:
            facts.append(f"Temas que toca: {', '.join(themes[:8])}.")
        places = [p.name for p in (getattr(entity, "places", None) or []) if getattr(p, "name", None)]
        if places:
            facts.append(f"Lugares mencionados: {', '.join(places[:8])}.")
    elif entity_type in ("theme", "place", "concept"):
        if entity.description:
            facts.append(entity.description.strip()[:1200])
    elif entity_type == "artist":
        albums = db.execute(
            select(Album).where(Album.artist_id == entity.id).order_by(Album.year)
        ).scalars().all()
        disc = ", ".join(f"{a.title} ({a.year})" for a in albums)
        facts.append(f"{subject} (actividad {entity.active_years}). Discografía: {disc}.")
    return "\n".join(facts)


def gather_entity_dossier(db: Session, entity_type: str, entity) -> Dossier:
    """Ensambla TODO el corpus relevante sobre la entidad."""
    subject, names = entity_names(db, entity_type, entity)
    hard = _hard_facts(db, entity_type, entity, subject)

    blocks: list[str] = []
    allowed: set[str] = set()
    n_sources = 0

    # 0) Para canciones, la LETRA es el material primario del análisis (si no,
    #    el motor inventa el análisis musical). Se marca como letra, no declaración.
    if entity_type == "song":
        letra = (getattr(entity, "lyrics_clean", None) or "").strip()
        if letra:
            blocks.append(
                f"[LETRA de la canción «{subject}» (es la LETRA de la canción, "
                f"NO una declaración de Robe)]\n{letra[:3500]}"
            )

    # 1) Hechos verificados de De Profundis y demás referencias.
    for fact in _reference_facts(names)[:40]:
        blocks.append(fact)

    # 2) Voz de Robe sobre el tema (retrieval semántico).
    try:
        from app.services.embeddings import get_embedder
        from app.services.retrieval import search_robe_voice
        qvec = get_embedder().embed_one(f"{subject}. {hard[:300]}")
        for v in search_robe_voice(qvec, k=4):
            blocks.append(f"[ENTREVISTA/CITA · {v['titulo']}] {v['fragmento']}")
            n_sources += 1
            if v.get("url") and v["url"].startswith("http") and "entreinteriores.com" not in v["url"]:
                allowed.add(v["url"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[deep] robe_voice falló: %s", exc)

    # 3) Fuentes que mencionan a la entidad por nombre (fan-content, prensa,
    #    transcripciones). Esto trae lo que el match por canción no ve.
    sources = fetch_sources_for_entity(db, names, limit=24)
    n_sources += len(sources)
    for s in sources:
        snippet = (s.get("content") or "").strip()[:_PER_SOURCE]
        if len(snippet) < 120:
            continue
        url = (s.get("url") or "").strip()
        ext = url if (url.startswith("http") and "entreinteriores.com" not in url) else ""
        kind = s.get("kind") or "fuente"
        is_transcript = "transcript" in kind or kind in ("youtube", "directo", "concierto")
        if is_transcript:
            # Las transcripciones de audio/vídeo mezclan LETRAS cantadas con
            # charla y traen ruido (palabras cortadas). NO son declaraciones.
            head = (
                f"[TRANSCRIPCIÓN de audio/vídeo · {s.get('title') or ''}] "
                "(contiene LETRAS de canciones cantadas y ruido de transcripción; "
                "NO es una entrevista: prohibido citar esto como algo que Robe "
                "'dijo' o 'declaró', y prohibido asignarle una fuente de prensa)"
            )
        else:
            head = f"[{kind} · {s.get('title') or ''}]" + (f" — FUENTE: {ext}" if ext else "")
        blocks.append(f"{head}\n{snippet}")
        if ext:
            allowed.add(ext)

    # Capa al contexto.
    material, total = [], 0
    for b in blocks:
        if total + len(b) > _TOTAL_CAP:
            break
        material.append(b)
        total += len(b)

    logger.info(
        "[deep] dossier %s/%s: %d bloques · %dk chars · %d fuentes · %d URLs",
        entity_type, subject, len(material), total // 1000, n_sources, len(allowed),
    )
    return Dossier(
        subject=subject, names=names, hard_facts=hard,
        material="\n\n----\n\n".join(material),
        allowed_urls=allowed, sources_count=n_sources,
    )
