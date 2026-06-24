"""Consultorio "Pregúntale al viento": Q&A que responde COMO Robe.

Pipeline:
  1. moderar la pregunta (omni-moderation-latest).
  2. clasificar pragmática (dato exacto) vs filosófica (RAG) + entidades + tags.
  3. PRAGMÁTICA → lookup EXACTO en BD (Album/Person/Song/Book); el LLM solo lo
     redacta con su voz, sin alterar el dato.
  4. FILOSÓFICA → grounding desde robe_voice_v1 (lo que dijo Robe) + versos (chunks_v1).
  5. answer_as_robe: gpt-4o con voice.build_system_prompt(family="consultorio").

Anti-invención: si no hay base, grounded=False y Robe esquiva con su estilo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import or_
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db.models import Album, Artist, Book, Person, Song
from app.services.embeddings import get_embedder
from app.services.qdrant_client import get_qdrant
from app.services.robe_quotes import tone_quotes
from app.services.robe_style import speech_style
from app.services.text_sanitizer import strip_ai_tells
from app.services.voice import build_system_prompt

ROBE_VOICE_COLLECTION = "robe_voice_v1"
CHUNKS_COLLECTION = "chunks_v1"
CLASSIFY_MODEL = "gpt-4o-mini"
ANSWER_MODEL = "gpt-4o"

_MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key)


def _fmt_date(d) -> str | None:
    if not d:
        return None
    try:
        return f"{d.day} de {_MESES[d.month]} de {d.year}"
    except Exception:  # noqa: BLE001
        return str(d)


# --------------------------------------------------------------------------- #
# Moderación
# --------------------------------------------------------------------------- #
def is_flagged(client: OpenAI, question: str) -> bool:
    try:
        resp = client.moderations.create(model="omni-moderation-latest", input=question)
        return bool(resp.results[0].flagged)
    except Exception:  # noqa: BLE001
        return False  # ante fallo de moderación, no bloqueamos (el prompt ya es digno)


# --------------------------------------------------------------------------- #
# Clasificación
# --------------------------------------------------------------------------- #
_CLASSIFY_SCHEMA = {
    "name": "classify",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {"type": "string", "enum": ["pragmatic", "philosophical"]},
            "entities": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "entities", "tags"],
    },
}

_CLASSIFY_SYS = (
    "Clasificas una pregunta dirigida a Robe Iniesta (Extremoduro). "
    "'pragmatic' = pide un DATO objetivo (año de un disco, fecha de nacimiento o "
    "muerte, formación, duración, datos de catálogo). 'philosophical' = pide su "
    "opinión, su visión o un concepto (amor, rabia, libertad, política, muerte...). "
    "Extrae en 'entities' los nombres propios mencionados (discos, personas, "
    "canciones, libros) tal cual aparecen. En 'tags' pon 1-4 temas en minúscula "
    "(p.ej. libertad, fama, censura, amor, muerte, composicion)."
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=15),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
)
def classify_question(client: OpenAI, question: str) -> dict:
    resp = client.chat.completions.create(
        model=CLASSIFY_MODEL,
        messages=[
            {"role": "system", "content": _CLASSIFY_SYS},
            {"role": "user", "content": question},
        ],
        response_format={"type": "json_schema", "json_schema": _CLASSIFY_SCHEMA},
        temperature=0,
    )
    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        data = {}
    return {
        "kind": data.get("kind", "philosophical"),
        "entities": [e for e in (data.get("entities") or []) if e][:6],
        "tags": [t for t in (data.get("tags") or []) if t][:4],
    }


# --------------------------------------------------------------------------- #
# Lookup pragmático (dato EXACTO desde la BD)
# --------------------------------------------------------------------------- #
def lookup_facts(db: Session, entities: list[str]) -> list[str]:
    facts: list[str] = []
    for name in entities:
        like = f"%{name.strip()}%"
        if len(name.strip()) < 3:
            continue
        for alb in db.query(Album).filter(Album.title.ilike(like)).limit(3).all():
            artist = db.get(Artist, alb.artist_id)
            who = artist.name if artist else "Extremoduro/Robe"
            when = _fmt_date(alb.release_date) or (str(alb.year) if alb.year else None)
            if when:
                facts.append(f'"{alb.title}" ({who}) se publicó en {when}.')
        for p in (
            db.query(Person)
            .filter(or_(Person.full_name.ilike(like), Person.stage_name.ilike(like)))
            .limit(3)
            .all()
        ):
            nm = p.stage_name or p.full_name
            b = _fmt_date(p.birth_date)
            d = _fmt_date(p.death_date)
            if b:
                facts.append(f"{nm} nació el {b}" + (f", en {p.birth_place}." if p.birth_place else "."))
            if d:
                facts.append(f"{nm} falleció el {d}.")
        for s in db.query(Song).filter(Song.title.ilike(like)).limit(3).all():
            alb = db.get(Album, s.album_id)
            if alb and alb.year:
                facts.append(f'La canción "{s.title}" salió en "{alb.title}" ({alb.year}).')
            if s.duration_sec:
                facts.append(f'"{s.title}" dura {s.duration_sec // 60}:{s.duration_sec % 60:02d}.')
        for bk in db.query(Book).filter(Book.title.ilike(like)).limit(2).all():
            if bk.year:
                facts.append(f'El libro "{bk.title}" es de {bk.year}.')
    # dedup preservando orden
    seen: set[str] = set()
    uniq = []
    for f in facts:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq[:8]


# --------------------------------------------------------------------------- #
# Retrieval de grounding (filosófico)
# --------------------------------------------------------------------------- #
@dataclass
class Passage:
    tipo: str
    titulo: str
    fragmento: str
    ref: str | None = None
    author_is_robe: bool = True


def _voice_passages(query_vec: list[float], only_robe: bool, k: int) -> list[Passage]:
    qdrant = get_qdrant()
    flt = Filter(
        must=[FieldCondition(key="author_is_robe", match=MatchValue(value=only_robe))]
    )
    try:
        resp = qdrant.query_points(
            collection_name=ROBE_VOICE_COLLECTION,
            query=query_vec,
            limit=k,
            query_filter=flt,
            score_threshold=0.33,
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[Passage] = []
    for r in resp.points:
        p = r.payload or {}
        frag = (p.get("fragmento") or "").strip()
        if not frag:
            continue
        out.append(
            Passage(
                tipo=p.get("tipo") or "entrevista",
                titulo=p.get("titulo") or "Robe Iniesta",
                fragmento=frag[:600],
                ref=p.get("url"),
                author_is_robe=bool(p.get("author_is_robe")),
            )
        )
    return out


def _lyric_passages(db: Session, query_vec: list[float], k: int) -> list[Passage]:
    qdrant = get_qdrant()
    try:
        resp = qdrant.query_points(
            collection_name=CHUNKS_COLLECTION, query=query_vec, limit=k, score_threshold=0.33
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[Passage] = []
    for r in resp.points:
        p = r.payload or {}
        txt = (p.get("text") or "").strip()
        if not txt:
            continue
        # recortar a pocas líneas (regla <4 versos)
        lines = [ln for ln in txt.splitlines() if ln.strip()][:3]
        title = p.get("song_title") or "una canción"
        slug = p.get("song_slug")
        artist = p.get("artist_slug")
        album = p.get("album_slug")
        ref = f"/{artist}/{album}/{slug}" if (artist and album and slug) else None
        out.append(
            Passage(tipo="letra", titulo=title, fragmento="\n".join(lines), ref=ref)
        )
    return out


def retrieve_grounding(db: Session, query: str) -> list[Passage]:
    qvec = get_embedder().embed_one(query)
    passages = _voice_passages(qvec, only_robe=True, k=10)
    passages += _voice_passages(qvec, only_robe=False, k=2)
    passages += _lyric_passages(db, qvec, k=3)
    return passages


# --------------------------------------------------------------------------- #
# Generación de la respuesta
# --------------------------------------------------------------------------- #
_ANSWER_SCHEMA = {
    "name": "robe_answer",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tipo": {"type": "string"},
                        "titulo": {"type": "string"},
                        "ref": {"type": ["string", "null"]},
                    },
                    "required": ["tipo", "titulo", "ref"],
                },
            },
            "grounded": {"type": "boolean"},
        },
        "required": ["answer", "citations", "grounded"],
    },
}


def _build_user_prompt(question: str, facts: list[str], passages: list[Passage]) -> str:
    parts = [f"PREGUNTA: {question}\n"]
    if facts:
        parts.append("DATOS EXACTOS (verídicos, NO los cambies, dilos con tu voz):")
        parts += [f"- {f}" for f in facts]
        parts.append("")
    if passages:
        parts.append(
            "PASAJES (tu materia prima: de aquí sacas tus ideas y tu tono. "
            "CONCEPTÚALO con tus palabras, NO copies los versos ni los encadenes; "
            "lo marcado como CONTEXTO no eres tú):"
        )
        for i, p in enumerate(passages, 1):
            etiqueta = {
                "robe_quote": "algo que dijiste",
                "robe_interview": "entrevista tuya",
                "robe_prose": "texto tuyo",
                "letra": "verso tuyo (para tu tono e ideas, NO para copiarlo)",
                "about_robe": "CONTEXTO de terceros (no eres tú)",
            }.get(p.tipo, p.tipo)
            parts.append(f"[{i}] ({etiqueta} · {p.titulo}) {p.fragmento}")
        parts.append("")
    if not facts and not passages:
        parts.append(
            "NO HAY PASAJES NI DATOS sobre esto. No te inventes una postura: "
            "esquívalo con tu estilo y pon grounded=false."
        )
    return "\n".join(parts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
)
def _call_answer(client: OpenAI, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=ANSWER_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": _ANSWER_SCHEMA},
        temperature=0.8,
    )
    return resp.choices[0].message.content or "{}"


def answer_as_robe(
    client: OpenAI, question: str, facts: list[str], passages: list[Passage], tags: list[str]
) -> dict:
    system = build_system_prompt(
        family="consultorio",
        persona="robe_primera",
        tone_quotes=tone_quotes(tags, k=4),
        style_guide=speech_style(),
    )
    user = _build_user_prompt(question, facts, passages)
    try:
        raw = _call_answer(client, system, user)
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {
            "answer": "Hoy el viento no me trae nada de eso. Pregúntame otra cosa, anda.",
            "citations": [],
            "grounded": False,
        }
    answer = strip_ai_tells(data.get("answer") or "") or ""
    cites = []
    for c in data.get("citations") or []:
        if isinstance(c, dict) and c.get("titulo"):
            cites.append({"tipo": c.get("tipo") or "", "titulo": c["titulo"], "ref": c.get("ref")})
    return {"answer": answer, "citations": cites, "grounded": bool(data.get("grounded"))}


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #
@dataclass
class ConsultResult:
    question: str
    answer: str
    citations: list = field(default_factory=list)
    grounded: bool = False
    kind: str = "philosophical"
    flagged: bool = False


def ask(db: Session, question: str) -> ConsultResult:
    client = _client()
    if is_flagged(client, question):
        return ConsultResult(
            question=question,
            answer="Por ahí no paso. Pregúntame de las canciones, de la vida, de lo que quieras de verdad.",
            grounded=False,
            kind="philosophical",
            flagged=True,
        )
    cls = classify_question(client, question)
    facts: list[str] = []
    passages: list[Passage] = []
    if cls["kind"] == "pragmatic":
        facts = lookup_facts(db, cls["entities"])
        # si no hay dato, intentamos también algo de grounding por si acaso
        if not facts:
            passages = retrieve_grounding(db, question)
    else:
        passages = retrieve_grounding(db, question)
    result = answer_as_robe(client, question, facts, passages, cls["tags"])
    answer = result["answer"]
    # Red de seguridad anti-alucinación: corrige errores de catálogo (canción↔
    # álbum↔año) en la respuesta contra la BD. Determinista, no reescribe.
    try:
        from app.services.fact_check import check_body, correct_body
        rep = check_body(db, answer, use_web=False)
        if rep.autofixes:
            answer, _ = correct_body(db, answer, rep)
    except Exception:  # noqa: BLE001 — best-effort, nunca rompe la respuesta
        pass
    return ConsultResult(
        question=question,
        answer=answer,
        citations=result["citations"],
        grounded=result["grounded"],
        kind=cls["kind"],
        flagged=False,
    )
