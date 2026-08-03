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
    Album, AlbumTrack, Artist, Band, BandMembership, Concept, Person, Place,
    Song, Theme,
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


# Etiqueta de procedencia por fichero de referencia. Antes TODO se citaba como
# «[De Profundis]», así que datos de Wikipedia acababan atribuidos a un libro que
# no los dice: una cita falsa es tan grave como un dato inventado. Los ficheros
# nuevos pueden declarar su fuente con `<!-- fuente: ... -->` en la cabecera.
_REF_LABELS = {
    "deprofundis_facts": "De Profundis",
    "viaje_intimo_novela": "El viaje íntimo de la locura",
    "wikipedia_giras_facts": "Wikipedia",
    "robe_solo_y_entorno": "research web",
}


def _reference_label(stem: str, text: str) -> str:
    m = re.search(r"<!--\s*fuente:\s*(.+?)\s*-->", text[:500], re.IGNORECASE)
    if m:
        return m.group(1)
    return _REF_LABELS.get(stem, stem.replace("_", " "))


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
        label = _reference_label(md.stem, text)
        for line in text.splitlines():
            nline = _norm(line)
            if len(line.strip()) > 40 and any(k in nline for k in keys):
                out.append(f"[{label}] {line.strip().lstrip('-* ')}")
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
        if entity.release_date:
            facts.append(f"Fecha de publicación: {entity.release_date.isoformat()}.")

        # El tracklist REAL. Sin esto el motor escribía sobre un disco cuyo
        # contenido no conocía, que es justo la puerta por la que se cuelan
        # canciones inventadas.
        if entity.kind in ("studio", "ep"):
            titulos = db.execute(
                select(Song.title).where(Song.album_id == entity.id)
                .order_by(Song.track_number)
            ).scalars().all()
            if titulos:
                facts.append(
                    f"Tracklist ({len(titulos)} cortes): "
                    + "; ".join(f"{i}. {t}" for i, t in enumerate(titulos, 1)) + "."
                )
        else:
            # Directos, recopilatorios y singles no tienen filas `Song` propias:
            # su tracklist es referencial y apunta a la grabación original.
            filas = db.execute(
                select(AlbumTrack, Song, Album)
                .outerjoin(Song, AlbumTrack.song_id == Song.id)
                .outerjoin(Album, Song.album_id == Album.id)
                .where(AlbumTrack.album_id == entity.id)
                .order_by(AlbumTrack.disc, AlbumTrack.position)
            ).all()
            if filas:
                partes = []
                for tr, song, alb in filas:
                    origen = f" [de «{alb.title}», {alb.year}]" if alb else ""
                    partes.append(f"{tr.position}. {tr.title_as_released}{origen}")
                facts.append(
                    f"Tracklist ({len(filas)} cortes), con el disco de origen de "
                    f"cada tema: " + "; ".join(partes) + "."
                )
                rerec = [tr for tr, _, _ in filas if tr.is_rerecording]
                if rerec:
                    facts.append(
                        f"{len(rerec)} de estos cortes son REGRABACIONES hechas "
                        "para este disco, no las tomas originales: "
                        + ", ".join(f"«{t.title_as_released}»" for t in rerec[:10]) + "."
                    )
                facts.append(
                    "Este disco no aporta canciones nuevas al catálogo: sus temas "
                    "ya existen en los discos de origen citados arriba."
                    if not rerec else
                    "Los temas ya existían; lo que aporta este disco son versiones "
                    "distintas de ellos."
                )
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

    allowed: set[str] = set()
    n_sources = 0
    # Buckets por prioridad (lo más fuerte primero; al capar, cae lo más débil).
    b_lyrics: list[str] = []
    b_deprof: list[str] = []
    b_graph: list[str] = []
    b_connsrc: list[str] = []
    b_voice: list[str] = []
    b_namesrc: list[str] = []
    b_semantic: list[str] = []
    b_affinity: list[str] = []

    def _source_head(kind: str, title: str, ext: str) -> str:
        """Cabecera etiquetada de una fuente (marca transcripciones como no-declaración)."""
        if "transcript" in kind or kind in ("youtube", "directo", "concierto"):
            return (f"[TRANSCRIPCIÓN de audio/vídeo · {title}] (contiene LETRAS de canciones "
                    "cantadas y ruido de transcripción; NO es una entrevista: prohibido citar "
                    "esto como algo que Robe 'dijo' o 'declaró', y prohibido asignarle fuente de prensa)")
        return f"[{kind} · {title}]" + (f" — FUENTE: {ext}" if ext else "")

    # 0) Para canciones, la LETRA es el material primario (etiquetada como letra).
    if entity_type == "song":
        letra = (getattr(entity, "lyrics_clean", None) or "").strip()
        if letra:
            b_lyrics.append(
                f"[LETRA de la canción «{subject}» (es la LETRA de la canción, "
                f"NO una declaración de Robe)]\n{letra[:3500]}"
            )
        # Créditos de autoría (verificados por consenso): CRÍTICO para no atribuir
        # mal el texto. P.ej. «Ama, ama y ensancha el alma» es un poema de Manolo
        # Chinato musicado por Robe, no una letra escrita por Robe.
        try:
            from app.db.models import SongCredit as _SC
            _credits = db.query(_SC).filter(_SC.song_id == entity.id).all()
        except Exception:
            _credits = []
        if _credits:
            _lines = "; ".join(f"{c.credit_role.replace('_', ' ')}: {c.credited_name}" for c in _credits)
            b_lyrics.append(
                f"[CRÉDITOS de «{subject}» (DATO CANÓNICO, respétalo al pie de la letra): "
                f"{_lines}. Si el texto NO es de Robe (poema_original/adaptación de otro autor), "
                f"NUNCA digas que Robe escribió la letra: di que Robe le puso música al poema de "
                f"ese autor, y nómbralo.]"
            )

    # 1) Hechos verificados de De Profundis y demás referencias.
    for fact in _reference_facts(names)[:40]:
        b_deprof.append(fact)

    # 1b) Contexto enciclopédico (Wikipedia) para persona/grupo: apoyo, NO citable
    #     como fuente ni como declaración.
    if entity_type in ("person", "band"):
        bio = (getattr(entity, "bio_long", None) or "").strip()
        if bio:
            b_deprof.append(
                "[CONTEXTO ENCICLOPÉDICO (Wikipedia; apoyo de fondo, no es una "
                f"declaración ni una fuente citable)]\n{bio[:1500]}"
            )

    # qvec compartido para retrieval semántico (voz de Robe + afinidad).
    qvec = None
    try:
        from app.services.embeddings import get_embedder
        qvec = get_embedder().embed_one(f"{subject}. {hard[:300]}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[deep] embedder falló: %s", exc)

    # 2) GRAFO CONECTADO: canciones/personas/bandas relacionadas por aristas REALES
    #    (datos curados → verificadas por construcción), con el MOTIVO de la conexión.
    connected_song_ids: list[int] = []
    try:
        from app.services.graph import gather_connected
        from scripts.seo.common import fetch_distilled_for_song, format_distilled_block
        conn = gather_connected(db, entity_type, entity)
        for cs in conn.songs:
            connected_song_ids.append(cs.song_id)
            head = (f"[CANCIÓN CONECTADA · «{cs.title}»"
                    + (f" ({cs.album}, {cs.year})" if cs.album else "")
                    + f" — conecta con {subject} porque {cs.why}]")
            distilled = fetch_distilled_for_song(db, cs.song_id)
            body = format_distilled_block(distilled) if distilled else ""
            b_graph.append(f"{head}\n{body}".strip())
        n_sources += len(conn.songs)
        rel = [f"{subject} → {b['label']} ({b['why']})" for b in conn.bands[:6]]
        rel += [f"{p['label']} ({p['why']})" for p in conn.people[:10]]
        if rel:
            b_graph.append("[ENTIDADES RELACIONADAS (del grafo, conexiones verificadas)]\n" + "; ".join(rel))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[deep] grafo conectado falló: %s", exc)

    # 2b) Fuentes ancladas a las canciones conectadas (referenced_song_ids && ids).
    if connected_song_ids:
        try:
            from sqlalchemy import Integer as SAInteger
            from sqlalchemy import cast
            from sqlalchemy.dialects.postgresql import ARRAY
            from app.db.models import InterpretationSource as _IS
            srcs = db.execute(
                select(_IS)
                .where(_IS.referenced_song_ids.op("&&")(cast(connected_song_ids, ARRAY(SAInteger))))
                .where(_IS.kind != "genius_annotation")
            ).scalars().all()
            seen_url: set[str] = set()
            for r in srcs[:20]:
                if r.url in seen_url:
                    continue
                seen_url.add(r.url)
                snip = (r.content_clean or "").strip()[:_PER_SOURCE]
                if len(snip) < 120:
                    continue
                ext = r.url if (r.url and r.url.startswith("http") and "entreinteriores.com" not in r.url) else ""
                b_connsrc.append(f"{_source_head(r.kind or 'fuente', r.title or '', ext)}\n{snip}")
                if ext:
                    allowed.add(ext)
                n_sources += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] fuentes conectadas falló: %s", exc)

    # 2c) VERSOS reales donde aparece el tema/lugar/concepto (Line ILIKE), para que
    #     el contenido cite los versos relevantes textualmente.
    b_verses: list[str] = []
    if entity_type in ("theme", "place", "concept"):
        try:
            import re as _re
            from sqlalchemy import or_ as _or
            from app.db.models import Line as _Line
            from app.db.models import Song as _Song
            words = {subject} | {
                w for w in _re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]", " ", subject).split()
                if len(w) > 3
            }
            rows = db.execute(
                select(_Line.text, _Song.title)
                .join(_Song, _Line.song_id == _Song.id)
                .where(_or(*[_Line.text.ilike(f"%{t}%") for t in words]))
                .limit(30)
            ).all()
            seen: set[str] = set()
            verses: list[str] = []
            for txt, title in rows:
                key = (txt or "").strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                verses.append(f"· «{title}»: {txt.strip()}")
            if verses:
                b_verses.append(
                    f"[VERSOS donde aparece «{subject}» (cítalos TEXTUALMENTE cuando sean "
                    "relevantes; elige los que mejor capturan la idea, no los triviales)]\n"
                    + "\n".join(verses[:18])
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] versos falló: %s", exc)

    # 3) Voz de Robe sobre el tema (k adaptativo).
    if qvec is not None:
        try:
            from app.services.retrieval import search_robe_voice
            voice_k = 8 if entity_type in ("person", "theme", "concept", "artist") else 4
            for v in search_robe_voice(qvec, k=voice_k):
                b_voice.append(f"[ENTREVISTA/CITA · {v['titulo']}] {v['fragmento']}")
                n_sources += 1
                if v.get("url") and v["url"].startswith("http") and "entreinteriores.com" not in v["url"]:
                    allowed.add(v["url"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] robe_voice falló: %s", exc)

    # 4) Fuentes que mencionan a la entidad por nombre (lo que el match por canción no ve).
    for s in fetch_sources_for_entity(db, names, limit=24):
        snippet = (s.get("content") or "").strip()[:_PER_SOURCE]
        if len(snippet) < 120:
            continue
        url = (s.get("url") or "").strip()
        ext = url if (url.startswith("http") and "entreinteriores.com" not in url) else ""
        b_namesrc.append(f"{_source_head(s.get('kind') or 'fuente', s.get('title') or '', ext)}\n{snippet}")
        if ext:
            allowed.add(ext)
        n_sources += 1

    # 4b) Corpus por SIGNIFICADO. El paso 4 exige que la fuente NOMBRE a la entidad;
    #     esto trae lo que habla del asunto sin nombrarlo, y sobre todo desatasca las
    #     fuentes que no están ligadas a ninguna canción (más de la mitad del corpus),
    #     que hasta ahora estaban vectorizadas y no salían por ningún camino.
    if qvec is not None:
        try:
            from app.services.retrieval import search_interpretations_passages
            ya_vistas = {b.split("\n", 1)[0] for b in b_namesrc}
            for p in search_interpretations_passages(db, qvec, k=6):
                frag = (p.get("fragmento") or "").strip()[:_PER_SOURCE]
                if len(frag) < 120:
                    continue
                url = (p.get("url") or "").strip()
                ext = url if (url.startswith("http") and "entreinteriores.com" not in url) else ""
                head = _source_head(p.get("kind") or "fuente", p.get("title") or "", ext)
                if head in ya_vistas:  # ya vino por nombre en el paso 4
                    continue
                b_semantic.append(f"{head}\n{frag}")
                if ext:
                    allowed.add(ext)
                n_sources += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] corpus semántico falló: %s", exc)

    # 5) Afinidad semántica: canciones cercanas SIN arista real. NO se afirman como
    #    conexión factual (la Fase 4.5 las verifica); van con disclaimer explícito.
    if qvec is not None:
        try:
            from app.services.retrieval import (
                search_interpretations_for_song_ids,
                search_lyrics_full_for_song_ids,
            )
            from scripts.seo.common import fetch_distilled_for_song, format_distilled_block
            from app.db.models import Song as _Song
            aff: dict[int, float] = {}
            for sid, sc in search_interpretations_for_song_ids(qvec, k=8).items():
                aff[sid] = max(aff.get(sid, 0.0), sc)
            for sid, sc in search_lyrics_full_for_song_ids(qvec, k=8).items():
                aff[sid] = max(aff.get(sid, 0.0), sc)
            already = set(connected_song_ids)
            for sid, _sc in sorted(aff.items(), key=lambda x: -x[1])[:6]:
                if sid in already:
                    continue
                s = db.get(_Song, sid)
                if not s:
                    continue
                distilled = fetch_distilled_for_song(db, sid)
                body = format_distilled_block(distilled) if distilled else ""
                head = (f"[AFINIDAD SEMÁNTICA · «{s.title}»] (vecindad temática detectada por el "
                        "buscador; NO afirmes una conexión factual directa con el sujeto salvo que "
                        "el material la respalde)")
                b_affinity.append(f"{head}\n{body}".strip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] afinidad semántica falló: %s", exc)

    # 6) Enriquecimiento VERIFICADO para entidades flacas: si hay poco material
    #    conectado, se confirma externamente (Wikipedia/Google) el vínculo con el
    #    universo y se añade con fuente. SOLO se incorpora lo confirmado.
    b_verified: list[str] = []
    # Para PERSONAS: contexto web (Wikipedia/Google) sobre su carrera y proyectos
    # actuales → nombra entidades que el corpus no tiene (bandas, proyectos, etc.).
    if entity_type == "person":
        try:
            from app.services.web_verify import web_context
            ctx = web_context(
                f"{subject} músico banda proyecto actual discografía",
                wiki_titles=[subject],
            )
            if ctx:
                b_verified.append(
                    "[CONTEXTO WEB EXTERNO sobre la persona (Wikipedia/Google; NOMBRA las "
                    "entidades reales que aquí aparezcan —bandas, proyectos, colaboradores—, "
                    "pero NO inventes lo que no conste aquí)]\n" + ctx
                )
                n_sources += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] web_context persona falló: %s", exc)

    richness = len(b_graph) + len(b_connsrc) + len(b_namesrc) + len(b_voice) + len(b_semantic)
    if entity_type in ("place", "theme", "concept", "person", "band") and richness < 5:
        try:
            from app.services.web_verify import verify_connection
            res = verify_connection(
                subject, "Roberto Iniesta Extremoduro",
                hint="vínculo con el universo de Robe/Extremoduro",
            )
            if res.get("confirmed"):
                src = res.get("source") or "fuente externa"
                # El TEXTO de evidencia real (Wikipedia/prensa) ancla los datos; si
                # no viene, al menos la frase resumida confirmada.
                grounded = res.get("evidence_text") or res.get("evidence") or ""
                if grounded:
                    b_verified.append(
                        "[CONTEXTO VERIFICADO EXTERNAMENTE (Wikipedia/prensa, fuente citable; "
                        f"confirmado en {src}; usa SOLO lo que aquí conste, no añadas datos de "
                        f"memoria)]\n{grounded}"
                    )
                    n_sources += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[deep] verificación externa falló: %s", exc)

    # Orden de prioridad (lo más débil al final → es lo primero que cae al capar).
    blocks = (b_lyrics + b_deprof + b_verified + b_verses + b_graph + b_connsrc + b_voice
              + b_namesrc + b_semantic + b_affinity)

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
