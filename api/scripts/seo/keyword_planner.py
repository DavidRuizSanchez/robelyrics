"""Planificador de keywords por ENTIDAD para el backfill deep-RAG.

Para cada entidad (persona, grupo, lugar, tema, concepto, canción, disco) genera
candidatas de keyword ancladas a SU nombre + el universo (extremoduro/robe), las
valida con volumen real de DataForSEO (España/ES, en lote) y devuelve:

  - keyword PRIMARIA: SIEMPRE contiene el nombre distintivo de la entidad
    (anti-canibalización: dos páginas nunca compiten por la misma primaria).
  - keywords SECUNDARIAS: variantes, rol e intención (letra/significado…), las de
    más volumen, sin repetir la primaria.

Reglas de honestidad (web pública, no afirmar lo que no es):
  - Persona MIEMBRO real de Extremoduro/Robe → primaria «<nombre> extremoduro».
  - Persona EXTERNA (colaborador/referencia citada: Zappa, Manolete, Camarón…) →
    primaria = su propio nombre; la conexión solo aparece como secundaria.

Si DataForSEO no responde, degrada a la primaria canónica sin volúmenes. No
inventa nada: las candidatas se derivan de datos del modelo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Artist, BandMembership, Person
from app.services.seo_research import KeywordData, search_volume

_CORE_ARTISTS = {"extremoduro", "robe", "robe-iniesta"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _clean(s: str) -> str:
    """Saca paréntesis y símbolos no admitidos por DataForSEO; deja letras
    (con acentos/ñ), números, espacios y guiones."""
    s = re.sub(r"\([^)]*\)", " ", s or "")
    s = re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _marca(artist_name: str) -> str:
    """Nombre del artista tal como se usa EN KEYWORDS.

    `Artist.name` guarda «Robe Iniesta», que el proyecto prohíbe escribir en
    contenido (regla dura, con enforcement en el ORM y en `strip_ai_tells`).
    Meterlo en el `target_keyword` obligaba al motor a pelearse con su propio
    guard. Y además es peor keyword: medido con Ahrefs, «mayeutica robe» tiene
    1.100 búsquedas/mes y «robe iniesta mayeutica» solo 70.
    """
    a = (artist_name or "").strip()
    if _norm(a) in ("robe iniesta", "roberto iniesta", "roberto iniesta ojea"):
        return "Robe"
    return a


def _dedup_clean(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in seq:
        s = _clean(raw)
        k = _norm(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


@dataclass
class EntityKW:
    core: str                                  # token distintivo que la primaria debe contener
    preferred: str                             # primaria canónica de reserva (sin volumen)
    primary_pool: list[str] = field(default_factory=list)  # candidatas elegibles como primaria
    candidates: list[str] = field(default_factory=list)    # todas (para secundarias)


def _is_core_member(db: Session, person_id: int) -> bool:
    slugs = db.execute(
        select(Artist.slug)
        .join(BandMembership, BandMembership.artist_id == Artist.id)
        .where(BandMembership.person_id == person_id)
    ).scalars().all()
    return any(s in _CORE_ARTISTS for s in slugs)


def _person_role(db: Session, person_id: int) -> str | None:
    m = db.execute(
        select(BandMembership).where(BandMembership.person_id == person_id)
    ).scalars().first()
    return _clean(m.role) if (m and m.role) else None


def candidates_for(db: Session, entity_type: str, entity) -> EntityKW:
    """Deriva token distintivo + pool de primaria + candidatas para la entidad."""
    if entity_type == "person":
        display = _clean(entity.stage_name or entity.full_name or "")
        full = _clean(entity.full_name or "")
        core_member = _is_core_member(db, entity.id)
        role = _person_role(db, entity.id)
        instr = ""
        if isinstance(entity.instruments, list) and entity.instruments:
            first = entity.instruments[0]
            instr = _clean(first.get("name") if isinstance(first, dict) else str(first))

        # Primaria SIEMPRE marca-cualificada (nunca el nombre pelado: esquiva
        # homónimos tipo Aitor Ariño=balonmano / Manolete=torero / Leiva=solista).
        # DataForSEO elige entre la forma «… extremoduro» y «… robe» por volumen.
        primary_pool = [f"{display} extremoduro", f"{display} robe"]
        cands = [f"{display} extremoduro", f"{display} robe", display]
        if full and _norm(full) != _norm(display):
            cands.append(full)
        if core_member and role:
            cands += [f"{role} de extremoduro", f"{display} {role}"]
        if core_member and instr:
            cands.append(f"{display} {instr}")
        preferred = f"{display} extremoduro"
        return EntityKW(core=display, preferred=preferred,
                        primary_pool=_dedup_clean(primary_pool), candidates=_dedup_clean(cands))

    if entity_type == "band":
        name = _clean(entity.name or "")
        is_label = getattr(entity, "kind", "") == "label"
        if is_label:
            pool = [f"{name} sello", f"{name} discográfica"]
            cands = [f"{name} sello", f"{name} discográfica", f"{name} extremoduro", name]
            pref = f"{name} sello"
        else:
            pool = [f"{name} grupo", f"{name} banda"]
            cands = [f"{name} grupo", f"{name} banda", f"{name} extremoduro", name]
            pref = f"{name} grupo"
        return EntityKW(core=name, preferred=pref,
                        primary_pool=_dedup_clean(pool), candidates=_dedup_clean(cands))

    if entity_type == "place":
        name = _clean(entity.name or "")
        pool = [f"{name} extremoduro", f"{name} robe"]
        cands = [f"{name} extremoduro", f"{name} robe", f"{name} canción", name]
        return EntityKW(core=name, preferred=f"{name} extremoduro",
                        primary_pool=_dedup_clean(pool), candidates=_dedup_clean(cands))

    if entity_type in ("theme", "concept"):
        name = _clean(entity.name or "")
        pool = [f"{name} extremoduro", f"{name} significado"]
        cands = [f"{name} extremoduro", f"{name} significado", f"{name} robe", name]
        return EntityKW(core=name, preferred=f"{name} extremoduro",
                        primary_pool=_dedup_clean(pool), candidates=_dedup_clean(cands))

    if entity_type == "song":
        title = _clean(entity.title or "")
        artist = ""
        al = getattr(entity, "album", None)
        if al and getattr(al, "artist", None):
            artist = _clean(al.artist.name)
        # La marca del pool es la del artista REAL, no «extremoduro» a pelo.
        # Estaba hardcodeado y afectaba a los 5 discos de Robe (34 canciones):
        # se les proponía «X extremoduro» como primaria cuando su artista es
        # Robe, y `artist` solo entraba como candidata secundaria.
        marca = _marca(artist) or "extremoduro"
        pool = [f"{title} letra", f"{title} significado", f"{title} {marca}"]
        cands = [f"{title} letra", f"{title} significado", f"{title} {marca}", title]
        if artist and artist.lower() != marca.lower():
            cands.append(f"{title} {artist}")
        return EntityKW(core=title, preferred=f"{title} letra",
                        primary_pool=_dedup_clean(pool), candidates=_dedup_clean(cands))

    if entity_type == "album":
        title = _clean(entity.title or "")
        artist = _clean(entity.artist.name) if getattr(entity, "artist", None) else ""
        marca = _marca(artist) or "extremoduro"
        pool = [f"{title} {marca}", f"{title} disco"]
        cands = [f"{title} {marca}", f"{title} disco", title]
        # Intenciones que el research y GSC confirman y que este pool ignoraba:
        # «agila contraportada» está en posición 8,0 y «agila significado» en 22.
        cands += [f"{title} significado", f"{title} portada", f"{title} canciones"]
        return EntityKW(core=title, preferred=f"{title} {marca}",
                        primary_pool=_dedup_clean(pool), candidates=_dedup_clean(cands))

    name = _clean(getattr(entity, "name", None) or getattr(entity, "title", "") or "")
    return EntityKW(core=name, preferred=f"{name} extremoduro",
                    primary_pool=_dedup_clean([f"{name} extremoduro", name]),
                    candidates=_dedup_clean([f"{name} extremoduro", name]))


def plan(ekw: EntityKW, volumes: dict[str, KeywordData], *, n_secondary: int = 3) -> tuple[str, list[str]]:
    """Elige (primaria, [secundarias]). La primaria sale SOLO del `primary_pool`
    (regla de honestidad); dentro del pool gana la de más volumen, y si ninguna
    tiene volumen, la canónica `preferred`."""
    def vol(kw: str) -> int:
        kd = volumes.get(_norm(kw))
        return kd.volume if kd else 0

    pool = ekw.primary_pool or [ekw.preferred]
    pool_sorted = sorted(pool, key=vol, reverse=True)
    primary = pool_sorted[0] if (pool_sorted and vol(pool_sorted[0]) > 0) else ekw.preferred

    rest = [c for c in ekw.candidates if _norm(c) != _norm(primary)]
    secondary = sorted(rest, key=vol, reverse=True)[:n_secondary]
    return primary, secondary


def plan_for_worklist(
    db: Session, items: list[tuple[str, object]]
) -> dict[int, tuple[str, list[str], int]]:
    """Para [(entity_type, entity)], consulta DataForSEO en lotes y devuelve
    {id(entity): (primaria, [secundarias], volumen_primaria)}."""
    ekws: dict[int, EntityKW] = {}
    all_kw: list[str] = []
    for et, ent in items:
        ek = candidates_for(db, et, ent)
        ekws[id(ent)] = ek
        all_kw += ek.candidates

    volumes: dict[str, KeywordData] = {}
    uniq = _dedup_clean(all_kw)
    for i in range(0, len(uniq), 700):
        try:
            volumes.update(search_volume(uniq[i : i + 700]))
        except Exception:  # noqa: BLE001 — degradar a sin-volumen
            pass

    out: dict[int, tuple[str, list[str], int]] = {}
    for et, ent in items:
        ek = ekws[id(ent)]
        primary, secondary = plan(ek, volumes)
        pv = volumes.get(_norm(primary))
        out[id(ent)] = (primary, secondary, pv.volume if pv else 0)
    return out
