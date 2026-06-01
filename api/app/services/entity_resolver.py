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


# --------------------------------------------------------------------------- #
# Autolinker de corpus: enlazado interno automático contra TODO el catálogo
# (álbumes, canciones, personas, artistas, taxonomías), no solo las entidades
# que marcó el LLM. Conservador y con límite de enlaces por pieza.
# --------------------------------------------------------------------------- #
# Single-word con menos de N letras: demasiado genérico para autoenlazar.
_AUTOLINK_MIN_LEN = 5
# Afinidad de tipo: cuán "enlazable de valor" es el destino. Sirve para dos
# cosas: desempatar colisiones de nombre (se queda el de más peso) y ponderar
# la relevancia del destino (contenido > taxonomía incidental).
_TYPE_WEIGHT = {
    "album": 7, "song": 6, "artist": 5, "person": 4,
    "place": 3, "theme": 2, "concept": 1,
}

# Fronteras de palabra que tratan el subrayado de Markdown (_cursiva_) como
# límite, no como letra: `\w` incluye '_', así que un título en cursiva
# (`_Agila_`) no se matcheaba. `[^\W_]` = alfanumérico SIN guion bajo.
_LB = r"(?<![\[`/]|[^\W_])"                       # antes: no link/code/letra
_LA = r"(?![^\[\n]{0,200}?\])(?![^\W_]|`)"        # no dentro de link + después


def _mention_re(name: str) -> "re.Pattern[str]":
    return re.compile(_LB + re.escape(name) + _LA, re.IGNORECASE)


def _safe_link_first(body_md: str, name: str, url: str) -> tuple[str, int]:
    """Enlaza la PRIMERA ocurrencia de `name` (fuera de links/code existentes)."""
    return _mention_re(name).subn(
        lambda m: f"[{m.group(0)}]({url})", body_md, count=1
    )


def build_corpus_index(
    db: Session, *, site_url: str | None = None
) -> list[dict[str, Any]]:
    """Índice de entidades enlazables del corpus: [{name, norm, url, type}]."""
    base = (site_url or SITE_URL_DEFAULT).rstrip("/")
    # Dedup por nombre normalizado: si dos entidades comparten nombre (p.ej.
    # el artista «Robe Iniesta» y la persona homónima), se queda la de más
    # peso de tipo para no enlazar el mismo texto a dos páginas distintas.
    by_norm: dict[str, dict[str, Any]] = {}

    def add(name: str | None, url: str, type_: str) -> None:
        if not name:
            return
        norm = _normalize(name)
        # Single-word demasiado corto → fuera (evita falsos positivos).
        if " " not in norm and len(norm) < _AUTOLINK_MIN_LEN:
            return
        cur = by_norm.get(norm)
        if cur and _TYPE_WEIGHT.get(cur["type"], 0) >= _TYPE_WEIGHT.get(type_, 0):
            return
        by_norm[norm] = {"name": name.strip(), "norm": norm, "url": url, "type": type_}

    for a in db.query(Artist).all():
        add(a.name, f"{base}/{a.slug}", "artist")
    for al in db.query(Album).all():
        if al.artist:
            add(al.title, f"{base}/{al.artist.slug}/{al.slug}", "album")
    for s in db.query(Song).all():
        if s.album and s.album.artist:
            add(s.title, f"{base}/{s.album.artist.slug}/{s.album.slug}/{s.slug}", "song")
    for p in db.query(Person).all():
        add(p.full_name, f"{base}/personas/{p.slug}", "person")
        if p.stage_name and p.stage_name != p.full_name:
            add(p.stage_name, f"{base}/personas/{p.slug}", "person")
    for pl in db.query(Place).all():
        add(pl.name, f"{base}/lugares/{pl.slug}", "place")
    for th in db.query(Theme).all():
        add(th.name, f"{base}/temas/{th.slug}", "theme")
    for c in db.query(Concept).all():
        add(c.name, f"{base}/conceptos/{c.slug}", "concept")
    return list(by_norm.values())


def autolink_corpus(
    body_md: str,
    index: list[dict[str, Any]],
    *,
    max_links: int = 4,
    exclude_url: str | None = None,
    exclude_slug: str | None = None,
) -> str:
    """Enlaza hasta `max_links` menciones a entidades del corpus, eligiendo las
    más relevantes.

    Selección (cuando hay más candidatos que `max_links`):
      1. Relevancia anchor↔destino: el anchor más específico gana (coincidencia
         exacta del título + nº de palabras + longitud).
      2. Desempate origen↔destino: cuán central es la entidad en el texto
         (frecuencia de mención) y el peso del tipo de destino.
    Conservador: primera ocurrencia por entidad, respeta links/código ya
    presentes, no enlaza la propia página (`exclude_url`).
    """
    if not body_md or not index:
        return body_md

    # Enlaces ya presentes: no duplicamos destino y contamos los que apuntan al
    # corpus contra el tope (idempotente: re-ejecutar no acumula enlaces).
    existing_urls = set(re.findall(r"\]\((\S+?)\)", body_md))
    index_urls = {e["url"] for e in index}
    budget = max_links - len(existing_urls & index_urls)
    if budget <= 0:
        return body_md

    # 1) Candidatos realmente mencionados (y enlazables) en el cuerpo.
    cand: list[dict[str, Any]] = []
    seen_urls: set[str] = set(existing_urls)
    for ent in index:
        url = ent["url"]
        if url == exclude_url or url in seen_urls:
            continue
        # No auto-enlazar la propia página (su seo_content).
        if exclude_slug and url.rstrip("/").endswith("/" + exclude_slug):
            continue
        hits = _mention_re(ent["name"]).findall(body_md)
        if not hits:
            continue
        seen_urls.add(url)
        # Relevancia: todas las menciones son coincidencia EXACTA del nombre
        # (relevancia anchor↔destino uniforme y máxima), así que la selección
        # la decide la relevancia origen↔destino:
        #   - frecuencia: cuán central es la entidad en el texto (peso alto),
        #   - afinidad de tipo: contenido (disco/canción/artista) > taxonomía
        #     incidental (un lugar nombrado de pasada),
        #   - longitud: especificidad del anchor como último desempate.
        score = (
            len(hits) * 30
            + _TYPE_WEIGHT.get(ent["type"], 0) * 10
            + len(ent["norm"]) * 0.5
        )
        cand.append({**ent, "score": score})

    if not cand:
        return body_md

    cand.sort(key=lambda c: c["score"], reverse=True)

    # 3) Enlazar los mejores hasta agotar el presupuesto (1ª ocurrencia c/u).
    for c in cand[:budget]:
        body_md, _ = _safe_link_first(body_md, c["name"], c["url"])
    return body_md
