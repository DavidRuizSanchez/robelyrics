"""Resuelve las entidades extraídas por el LLM (`Post.entities`,
`SeoContent.entities`) contra el corpus local + Wikidata.

Cada entidad llega del LLM como:
  {"type": str, "name": str, "wikidata_id": str | None, "slug_hint": str | None}

Tras resolver, el frontend recibe:
  {"type": str, "name": str, "canonical_id": str, "url": str | None,
   "same_as": [wikidata_url, wikipedia_url] | None, "from_corpus": bool}

- Si la entidad matchea un Artist/Album/Song/Person de nuestra DB,
  `canonical_id` y `url` apuntan al hub local (knowledge graph
  interconectado).
- Si no, `canonical_id` apunta a Wikidata si tenemos Q-ID.
- Si tampoco, se devuelve solo el nombre (mejor que omitir).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Concept, Person, Place, Song, Theme

SITE_URL_DEFAULT = "https://entreinteriores.com"


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _resolve_one(
    db: Session, ent: dict[str, Any], site_url: str
) -> dict[str, Any] | None:
    name = (ent.get("name") or "").strip()
    if not name:
        return None
    e_type = (ent.get("type") or "").strip() or "Thing"
    wikidata_id = ent.get("wikidata_id")
    slug_hint = (ent.get("slug_hint") or "").strip() or None
    norm_name = _normalize(name)

    canonical_id: str | None = None
    url: str | None = None
    from_corpus = False

    # --- lookup en corpus por tipo ---
    if e_type in {"Person"}:
        q = db.query(Person).filter(
            (Person.slug == slug_hint) if slug_hint else (Person.full_name.ilike(name))
        )
        person = q.first()
        if person is None and slug_hint is None:
            # fuzzy por stage_name o full_name normalizado
            for p in db.query(Person).all():
                if _normalize(p.stage_name or "") == norm_name or _normalize(p.full_name) == norm_name:
                    person = p
                    break
        if person is not None:
            canonical_id = f"{site_url}/personas/{person.slug}#person"
            url = f"{site_url}/personas/{person.slug}"
            from_corpus = True

    if not from_corpus and e_type in {"MusicGroup", "Organization"}:
        artist = None
        if slug_hint:
            artist = db.query(Artist).filter(Artist.slug == slug_hint).first()
        if artist is None:
            for a in db.query(Artist).all():
                if _normalize(a.name) == norm_name or a.slug == norm_name.replace(" ", "-"):
                    artist = a
                    break
        if artist is not None:
            canonical_id = f"{site_url}/{artist.slug}#musicgroup"
            url = f"{site_url}/{artist.slug}"
            from_corpus = True

    if not from_corpus and e_type in {"MusicAlbum"}:
        album = None
        if slug_hint:
            album = db.query(Album).filter(Album.slug == slug_hint).first()
        if album is None:
            for a in db.query(Album).all():
                if _normalize(a.title) == norm_name:
                    album = a
                    break
        if album is not None:
            artist_slug = album.artist.slug if album.artist else None
            if artist_slug:
                canonical_id = f"{site_url}/{artist_slug}/{album.slug}#musicalbum"
                url = f"{site_url}/{artist_slug}/{album.slug}"
                from_corpus = True

    if not from_corpus and e_type in {"MusicComposition", "MusicRecording"}:
        song = None
        if slug_hint:
            song = db.query(Song).filter(Song.slug == slug_hint).first()
        if song is None:
            for s in db.query(Song).all():
                if _normalize(s.title) == norm_name:
                    song = s
                    break
        if song is not None and song.album and song.album.artist:
            canonical_id = (
                f"{site_url}/{song.album.artist.slug}/{song.album.slug}/{song.slug}#musiccomposition"
            )
            url = f"{site_url}/{song.album.artist.slug}/{song.album.slug}/{song.slug}"
            from_corpus = True

    # Taxonomías locales: Place / Theme / Concept tienen pages en
    # /lugares/{slug}, /temas/{slug}, /conceptos/{slug}.
    if not from_corpus and e_type in {"Place", "TouristAttraction", "City", "AdministrativeArea"}:
        place = None
        if slug_hint:
            place = db.query(Place).filter(Place.slug == slug_hint).first()
        if place is None:
            for pl in db.query(Place).all():
                if _normalize(pl.name) == norm_name or pl.slug == norm_name.replace(" ", "-"):
                    place = pl
                    break
        if place is not None:
            canonical_id = f"{site_url}/lugares/{place.slug}#place"
            url = f"{site_url}/lugares/{place.slug}"
            from_corpus = True

    if not from_corpus and e_type in {"Thing", "DefinedTerm"} and slug_hint:
        # Conceptos genéricos del bestiario (libertad, lucha, etc.)
        concept = db.query(Concept).filter(Concept.slug == slug_hint).first()
        if concept is None:
            for c in db.query(Concept).all():
                if _normalize(c.name) == norm_name:
                    concept = c
                    break
        if concept is not None:
            canonical_id = f"{site_url}/conceptos/{concept.slug}#concept"
            url = f"{site_url}/conceptos/{concept.slug}"
            from_corpus = True

    # --- fallback: Wikidata como @id externo ---
    same_as: list[str] = []
    if wikidata_id and isinstance(wikidata_id, str) and wikidata_id.startswith("Q"):
        wd_url = f"https://www.wikidata.org/wiki/{wikidata_id}"
        same_as.append(wd_url)
        if canonical_id is None:
            canonical_id = wd_url

    return {
        "type": e_type,
        "name": name,
        "canonical_id": canonical_id,
        "url": url,
        "same_as": same_as,
        "from_corpus": from_corpus,
    }


def resolve_entities(
    db: Session, raw_entities: list[dict[str, Any]] | None, *, site_url: str | None = None
) -> list[dict[str, Any]]:
    """Resuelve un array de entidades raw. Devuelve solo las que tienen
    name válido (descarta duplicados por canonical_id o name normalizado)."""
    if not raw_entities:
        return []
    base_url = site_url or SITE_URL_DEFAULT
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ent in raw_entities:
        if not isinstance(ent, dict):
            continue
        resolved = _resolve_one(db, ent, base_url)
        if resolved is None:
            continue
        key = (resolved.get("canonical_id") or "") + "|" + _normalize(resolved["name"])
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


# --------------------------------------------------------------------------- #
# Linkificación de body_md con entidades resueltas
# --------------------------------------------------------------------------- #
def linkify_body_md(
    body_md: str, resolved_entities: list[dict[str, Any]] | None
) -> str:
    """Reemplaza la primera ocurrencia de cada entidad mencionada (con `url`
    no nula) por un link markdown `[name](url)`.

    Reglas:
      - Una sola sustitución por entidad (evita keyword-stuffing).
      - Match con word boundaries, case-insensitive, mantiene la
        capitalización original del texto.
      - No matchea si la palabra ya está dentro de un link `[...](...)` o
        dentro de inline code `` `…` ``.
      - Entidades más largas primero (matchea "Robe Iniesta" antes de
        intentar "Robe", para no romper la primera).
      - Salta entidades cuyo `url` apunta al mismo path que está ya en el
        texto (evita auto-links de la propia página).

    Idempotente: si se llama dos veces sobre el mismo body, no genera
    dobles corchetes (el lookahead protege contra esto).
    """
    if not body_md or not resolved_entities:
        return body_md

    # Solo linkifica las que tengan url. Sortea por longitud de name desc
    # para priorizar matches más específicos.
    candidates = sorted(
        [
            e for e in resolved_entities
            if e.get("url") and e.get("name")
        ],
        key=lambda e: len(e["name"]),
        reverse=True,
    )

    seen_urls: set[str] = set()
    for ent in candidates:
        name = ent["name"]
        url = ent["url"]
        if url in seen_urls:
            continue

        escaped = re.escape(name)
        # Lookbehind: no precedido por '[' (texto de link) ni '`' (code)
        # Lookahead: no seguido por ']' antes del próximo '[' (dentro de link)
        #   ni por '`' (cierre de code inline)
        pattern = re.compile(
            r"(?<![\[`/\w])"
            + escaped
            + r"(?![^\[\n]{0,200}?\])"
            r"(?![\w`])",
            re.IGNORECASE,
        )

        def _replace(match: "re.Match[str]") -> str:
            return f"[{match.group(0)}]({url})"

        new_body, n = pattern.subn(_replace, body_md, count=1)
        if n > 0:
            body_md = new_body
            seen_urls.add(url)
    return body_md
