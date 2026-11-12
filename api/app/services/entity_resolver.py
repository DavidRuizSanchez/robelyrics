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

import json
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Concept, Person, Place, Song, Theme
from app.services.link_policy import (
    DENTRO_DE_ANCHOR,
    HUBS,
    MAX_BODY_LINKS,
    MAX_HUBS_POR_PAGINA,
    PESO_TIPO,
    PREFIJOS,
    ContextoEnlazado,
    artista_de,
    fold,
    presupuesto,
    relevancia,
    rutas_del_cuerpo,
)

SITE_URL_DEFAULT = "https://entreinteriores.com"

# Snapshot de link juice interno (lo escribe scripts/seo/link_stats.py). El
# autolinker lo usa para potenciar las páginas más débiles. {path: inbound}.
_LINK_STATS_PATH = Path("/app/data/internal_link_stats.json")
_link_stats_cache: dict[str, int] | None = None
_anchor_stats_cache: dict[str, dict[str, int]] | None = None


def load_link_stats() -> dict[str, int]:
    """Carga (cacheado) el snapshot de enlaces internos. {} si no existe.

    El snapshot trae además `__anchors__` ({path: {anchor: n}}), que se separa
    aquí para que `link_stats.get(path, 0)` siga devolviendo un entero."""
    global _link_stats_cache, _anchor_stats_cache
    if _link_stats_cache is None:
        try:
            raw = json.loads(_LINK_STATS_PATH.read_text())
        except Exception:  # noqa: BLE001 — ausente o ilegible
            raw = {}
        _anchor_stats_cache = raw.pop("__anchors__", None) or {}
        _link_stats_cache = {k: v for k, v in raw.items() if isinstance(v, int)}
    return _link_stats_cache


def _url_path(url: str) -> str:
    """Ruta comparable de un enlace (ver `link_policy.norm_path`)."""
    from app.services.link_policy import norm_path

    return norm_path(url) or url


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
        # Solo personas con ficha publicada: sin ella no existen para el público
        # y su @id apuntaría a un 404 (person_visibility).
        from app.services.person_visibility import persona_publicada
        q = db.query(Person).filter(
            (Person.slug == slug_hint) if slug_hint else (Person.full_name.ilike(name)),
            persona_publicada(),
        )
        person = q.first()
        if person is None and slug_hint is None:
            # fuzzy por stage_name o full_name normalizado
            for p in db.query(Person).filter(persona_publicada()).all():
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
        from app.services.url_resolver import is_live_version

        def _desempatar(cands: list) -> object | None:
            """Con homónimas, manda la de estudio. Si sigue el empate, ninguna:
            el `.first()` de antes elegía por orden de PK, o sea a cara o cruz."""
            if len(cands) == 1:
                return cands[0]
            estudio = [c for c in cands if not is_live_version(c.slug, c.title)]
            return estudio[0] if len(estudio) == 1 else None

        song = None
        if slug_hint:
            song = _desempatar(
                db.query(Song).filter(Song.slug == slug_hint).order_by(Song.id).all()
            )
        if song is None:
            song = _desempatar([
                s for s in db.query(Song).order_by(Song.id).all()
                if _normalize(s.title) == norm_name
            ])
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
            + r"(?!" + DENTRO_DE_ANCHOR + r")"
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
_TYPE_WEIGHT = PESO_TIPO  # una sola tabla: link_policy

# Fronteras de palabra que tratan el subrayado de Markdown (_cursiva_) como
# límite, no como letra: `\w` incluye '_', así que un título en cursiva
# (`_Agila_`) no se matcheaba. `[^\W_]` = alfanumérico SIN guion bajo.
_LB = r"(?<![\[`/]|[^\W_])"                       # antes: no link/code/letra
_LA = r"(?!" + DENTRO_DE_ANCHOR + r")(?![^\W_]|`)"  # no dentro de link + después


def _mention_re(name: str) -> "re.Pattern[str]":
    return re.compile(_LB + re.escape(name) + _LA, re.IGNORECASE)


def _safe_link_first(body_md: str, name: str, url: str) -> tuple[str, int]:
    """Enlaza la PRIMERA ocurrencia de `name` fuera de links/code existentes y
    NUNCA dentro de un encabezado (regla: no enlazar headings)."""
    for m in _mention_re(name).finditer(body_md):
        line_start = body_md.rfind("\n", 0, m.start()) + 1
        nl = body_md.find("\n", m.start())
        line = body_md[line_start: nl if nl != -1 else len(body_md)]
        if line.lstrip().startswith("#"):
            continue  # es un heading: saltar
        return (
            body_md[:m.start()] + f"[{m.group(0)}]({url})" + body_md[m.end():],
            1,
        )
    return body_md, 0


_TITLE_SUFFIX_RE = re.compile(r"\s*[(\[].*$")


def _clean_title(title: str | None) -> str | None:
    """Quita el sufijo entre paréntesis/corchetes de los títulos del corpus.

    Las canciones se guardan como «Título (Álbum)» o «Título [En Directo]»;
    para que el autolinker las reconozca al citarse por su nombre limpio
    («Jesucristo García»), añadimos ese alias al índice.
    """
    if not title:
        return None
    cleaned = _TITLE_SUFFIX_RE.sub("", title).strip()
    return cleaned or None


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
            url = f"{base}/{al.artist.slug}/{al.slug}"
            add(al.title, url, "album")
            add(_clean_title(al.title), url, "album")
    for s in db.query(Song).all():
        if s.album and s.album.artist:
            url = f"{base}/{s.album.artist.slug}/{s.album.slug}/{s.slug}"
            add(s.title, url, "song")
            # Alias sin el sufijo de álbum/directo: «Jesucristo García
            # (Rock Transgresivo)» también enlaza al citarse «Jesucristo García».
            add(_clean_title(s.title), url, "song")
    # Sin ficha publicada no se enlaza: el enlace daría 404 (person_visibility).
    from app.services.person_visibility import persona_publicada
    for p in db.query(Person).filter(persona_publicada()).all():
        purl = f"{base}/personas/{p.slug}"
        add(p.full_name, purl, "person")
        if p.stage_name and p.stage_name != p.full_name:
            add(p.stage_name, purl, "person")
            # Alias «apodo + primer apellido»: el texto suele escribir «Fito
            # Cabrales» aunque la ficha sea nombre «Adolfo Cabrales Mato» +
            # apodo «Fito». El primer apellido es el 2º token del nombre.
            toks = (p.full_name or "").split()
            if len(toks) >= 2:
                add(f"{p.stage_name} {toks[1]}", purl, "person")
    for pl in db.query(Place).all():
        add(pl.name, f"{base}/lugares/{pl.slug}", "place")
    for th in db.query(Theme).all():
        add(th.name, f"{base}/temas/{th.slug}", "theme")
    for c in db.query(Concept).all():
        add(c.name, f"{base}/conceptos/{c.slug}", "concept")
    # Grupos/sellos afines (sección /grupos). Import perezoso para no acoplar
    # el resolver a un modelo que llegó después.
    try:
        from app.db.models import Band  # noqa: PLC0415
        for b in db.query(Band).all():
            # Los sellos viven en /sellos/: indexarlos en /grupos/ hacía que el
            # guard los reescribiera y el autolinker no reconociera su enlace.
            seccion = "sellos" if b.kind == "label" else "grupos"
            add(b.name, f"{base}/{seccion}/{b.slug}", "band")
    except Exception:  # noqa: BLE001
        pass
    # Hubs (páginas índice en código): solo variantes de varias palabras.
    for path, hub in HUBS.items():
        for variante in hub["variantes"]:
            add(variante, f"{base}{path}", "hub")
    return list(by_norm.values())


def load_anchor_stats() -> dict[str, dict[str, int]]:
    """Anchors entrantes por destino ({path: {anchor_plegado: n}}), del mismo
    snapshot que `load_link_stats` (clave `__anchors__`). {} si no hay."""
    load_link_stats()
    return _anchor_stats_cache or {}


# Tipos cuyo nombre es propio: solo casa si la mención lleva alguna mayúscula
# («rock transgresivo» es el estilo, no el disco; «pasión», la palabra, no el
# sello). Medido en el ensayo de prod del 11-11-2026: 26 de 240 enlaces nuevos.
_NOMBRE_PROPIO = frozenset({"album", "song", "artist", "person", "band", "place"})


def _inicio_de_frase(body_md: str, pos: int) -> bool:
    antes = body_md[:pos].rstrip(" \t*_\"«“(¿¡")
    return not antes or antes[-1] in ".!?:\n" or antes.endswith(("- ", "-"))


def _ocurrencias(body_md: str, nombres: list[str], prefijos: tuple[str, ...],
                 tipo: str = "") -> list[tuple[int, int, str]]:
    """Menciones enlazables (fuera de enlaces, código y encabezados): el nombre
    solo y, si ya está escrito delante, el nombre con su prefijo («el disco
    *Agila*»). No inventa texto: solo elige qué trozo existente es el anchor.

    Mayúsculas: un nombre propio exige alguna mayúscula en la mención, y un tema
    escrito con mayúscula a mitad de frase es parte de otro nombre («Calle
    Esperanza»), así que no cuenta."""
    out: list[tuple[int, int, str]] = []
    pref = "|".join(re.escape(x) for x in sorted(prefijos, key=len, reverse=True))
    for nombre in nombres:
        patrones = [re.compile(_LB + "(?P<n>" + re.escape(nombre) + ")" + _LA, re.IGNORECASE)]
        if pref:
            patrones.append(re.compile(
                _LB + rf"(?:{pref})\s+(?P<em>[*_]{{0,2}})(?P<n>" + re.escape(nombre) + r")(?P=em)" + _LA,
                re.IGNORECASE,
            ))
        for pat in patrones:
            for m in pat.finditer(body_md):
                ini = body_md.rfind("\n", 0, m.start()) + 1
                if body_md[ini:m.start()].lstrip().startswith("#"):
                    continue  # nunca dentro de un encabezado
                n = m.group("n")
                if tipo in _NOMBRE_PROPIO and not any(c.isupper() for c in n):
                    continue
                if tipo == "theme" and n[:1].isupper() and not _inicio_de_frase(body_md, m.start("n")):
                    continue
                out.append((m.start(), m.end(), m.group(0)))
    return sorted(set(out))


def autolink_corpus(
    body_md: str,
    index: list[dict[str, Any]],
    *,
    max_links: int = MAX_BODY_LINKS,
    exclude_url: str | None = None,
    exclude_slug: str | None = None,
    link_stats: dict[str, int] | None = None,
    weak_k: float = 60.0,
    contexto: ContextoEnlazado | None = None,
    ya_en_pagina: Iterable[str] = (),
    anchor_stats: dict[str, dict[str, int]] | None = None,
) -> str:
    """Enlaza menciones a entidades del corpus según `link_policy`.

    - Tope: `MAX_BODY_LINKS` (3) rutas internas distintas en el cuerpo, contando
      las que ya hay y las de `ya_en_pagina` (el resto de la página, para quien
      enlaza por secciones). Un `max_links` mayor se recorta a ese tope.
    - No enlaza lo que ya enlaza la plantilla (`contexto.plantilla`), ni la propia
      página, ni un destino ya enlazado.
    - Taxonomías solo con relación en el grafo (`contexto.admite`). Sin contexto,
      ninguna.
    - Hubs: como mucho uno, el del artista de la página, sin impulso de débil.
    - Anchor: entre los alias y las ampliaciones ya escritas, el menos usado.

    Selección por relevancia: frecuencia de mención, peso del tipo, longitud del
    nombre y, a igualdad, impulso a las páginas que reciben menos enlaces.
    """
    if not body_md or not index:
        return body_md
    ctx = contexto or ContextoEnlazado()
    tope = min(max_links, MAX_BODY_LINKS)
    ya = {p for p in (_url_path(u) for u in ya_en_pagina) if p.startswith("/")}
    budget = presupuesto(body_md, ctx.plantilla, ya, tope)
    if budget <= 0:
        return body_md

    vistos = set(rutas_del_cuerpo(body_md)) | ya | set(ctx.plantilla) | set(ctx.migas)
    if ctx.origen:
        vistos.add(ctx.origen)
    exclude_path = _url_path(exclude_url) if exclude_url else None
    artista_pagina = artista_de(ctx.origen)
    hubs_puestos = sum(1 for p in set(rutas_del_cuerpo(body_md)) | ya if p in HUBS)

    # Agrupa los alias por destino (el índice tiene una entrada por nombre).
    grupos: dict[str, dict[str, Any]] = {}
    for ent in index:
        path = _url_path(ent["url"])
        g = grupos.setdefault(path, {"url": ent["url"], "type": ent["type"], "names": []})
        g["names"].append(ent["name"])

    cand: list[dict[str, Any]] = []
    for path, g in grupos.items():
        if path in vistos or path == exclude_path:
            continue
        if exclude_slug and path.endswith("/" + exclude_slug):
            continue
        if not ctx.admite(path):
            continue
        es_hub = g["type"] == "hub"
        if es_hub:
            hub_artista = HUBS.get(path, {}).get("artista")
            if hubs_puestos >= MAX_HUBS_POR_PAGINA:
                continue
            if hub_artista and artista_pagina and hub_artista != artista_pagina:
                continue
        hits = sum(len(_mention_re(n).findall(body_md)) for n in g["names"])
        if not hits:
            continue
        score = relevancia(hits, g["type"], max(len(_normalize(n)) for n in g["names"]))
        if link_stats is not None and not es_hub:
            score += weak_k / (1 + link_stats.get(path, 0))
        cand.append({**g, "path": path, "score": score, "hub": es_hub})

    cand.sort(key=lambda c: c["score"], reverse=True)
    anchors = anchor_stats or {}
    puestos = 0
    for c in cand:
        if puestos >= budget:
            break
        if c["hub"] and hubs_puestos >= MAX_HUBS_POR_PAGINA:
            continue
        occ = _ocurrencias(body_md, c["names"], PREFIJOS.get(c["type"], ()), c["type"])
        if not occ:
            continue
        usados = anchors.get(c["path"], {})
        ini, fin, texto = min(occ, key=lambda o: (usados.get(fold(o[2]), 0), o[0]))
        body_md = body_md[:ini] + f"[{texto}]({c['url']})" + body_md[fin:]
        puestos += 1
        hubs_puestos += c["hub"]
    return body_md


# --------------------------------------------------------------------------- #
# Autolinker de FUENTES externas: cuando el contenido cita un medio (p.ej.
# «Mondo Sonoro destacó…»), enlaza el nombre del medio a la URL de la fuente
# (InterpretationSource.url). Enlace EXTERNO — el frontend lo marca con
# rel="nofollow noopener" target="_blank" (ver web/components/MarkdownArticle.tsx).
# Mismo patrón conservador que `autolink_corpus`: primera ocurrencia, respeta
# links/código existentes, idempotente, tope `max_links`.
# --------------------------------------------------------------------------- #
# Dominio → nombre visible del medio. La clave es el dominio registrable sin
# `www.` ni subdominios. Si el dominio no está aquí y `author` no parece nombre
# de medio fiable, NO se enlaza (mejor no enlazar que enlazar mal).
#
# Mondo Sonoro, Efe Eme y Rockdelux están FUERA a propósito (02-08-2026): son la
# «prensa comercial vetada» de CLAUDE.md, en «Decisiones que NO hay que reabrir»,
# y este mapa los estaba enlazando activamente — el código contradecía la
# política declarada. Se pueden seguir CITANDO como fuente en el texto (77 fichas
# lo hacen y el veto se escribió para el corpus de fan-content, no para las
# citas), pero no se les manda enlace.
_MEDIA_VETADOS = {"mondosonoro.com", "efeeme.com", "rockdelux.com"}

_MEDIA_BY_DOMAIN: dict[str, str] = {
    "rocksesion.com": "RockSesión",
    "elpais.com": "El País",
    "mariskalrock.com": "MariskalRock",
    "jenesaispop.com": "Jenesaispop",
    "publico.es": "Público",
    "elmundo.es": "El Mundo",
    "abc.es": "ABC",
    "lavanguardia.com": "La Vanguardia",
    "eldiario.es": "elDiario.es",
    "rtve.es": "RTVE",
    "cadenaser.com": "Cadena SER",
    "elconfidencial.com": "El Confidencial",
    "infolibre.es": "infoLibre",
    "ondacero.es": "Onda Cero",
    "20minutos.es": "20minutos",
    "europapress.es": "Europa Press",
    "ruta66.es": "Ruta 66",
    "popular1.com": "Popular 1",
    "lasexta.com": "laSexta",
    "huffingtonpost.es": "El HuffPost",
    "huffingtonpost.com": "El HuffPost",
    "muzikalia.com": "Muzikalia",
    "indienauta.com": "Indienauta",
    "binaural.es": "Binaural",
    "hipersonica.com": "Hipersónica",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "spotify.com": "Spotify",
    "bandcamp.com": "Bandcamp",
    "wikipedia.org": "Wikipedia",
}

# Hint de que un `author` es un medio (no una persona): contiene una de estas
# palabras o termina en uno de estos sufijos típicos de cabecera.
_MEDIA_AUTHOR_HINT = re.compile(
    r"\b(magazine|revista|diario|radio|tv|televisi[oó]n|prensa|"
    r"redacci[oó]n|agencia|news|press|media|rock|son(?:oro|ido))\b",
    re.IGNORECASE,
)


def _domain_of(url: str) -> str | None:
    """Dominio registrable de una url (sin esquema, sin `www.`, sin path)."""
    if not url:
        return None
    m = re.match(r"\s*(?:https?:)?//", url)
    rest = url[m.end():] if m else url
    host = re.split(r"[/?#]", rest, 1)[0].strip().lower()
    host = host.split("@")[-1].split(":")[0]  # quita user:pass@ y :puerto
    if not host or "." not in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    # Dominio registrable: últimos 2 labels (o 3 para .co.uk, .com.es…).
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "gob", "gov"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _media_name_for_source(src: dict[str, Any]) -> str | None:
    """Nombre de medio visible y FIABLE para una fuente, o None si no se puede
    derivar con confianza (en cuyo caso NO se enlaza)."""
    url = (src.get("url") or "").strip()
    if not url:
        return None
    domain = _domain_of(url)
    if domain and domain in _MEDIA_BY_DOMAIN:
        return _MEDIA_BY_DOMAIN[domain]
    # Fallback: usar `author` solo si parece nombre de medio (no persona) y es
    # razonablemente específico (evita single-word genérico tipo «Blog»).
    author = (src.get("author") or "").strip()
    if author and len(author) >= _AUTOLINK_MIN_LEN and _MEDIA_AUTHOR_HINT.search(author):
        return author
    return None


def autolink_sources(
    body_md: str,
    sources: list[dict[str, Any]],
    *,
    max_links: int = 4,
) -> str:
    """Enlaza menciones a MEDIOS citados en el cuerpo a la url de su fuente.

    `sources`: dicts como los de fetch_sources_* (con 'kind','title','author',
    'url'). Para cada fuente con url se deriva un nombre de medio visible
    (mapa dominio→nombre, o `author` si parece cabecera); si no se puede
    derivar con fiabilidad, esa fuente NO se enlaza.

    Conservador como `autolink_corpus`: enlaza la PRIMERA ocurrencia (case-
    insensitive, con fronteras de palabra) de cada nombre, no enlaza dentro de
    links/código ya presentes, es idempotente y respeta el tope `max_links`.
    """
    if not body_md or not sources:
        return body_md

    # Presupuesto: descuenta enlaces a estas urls ya presentes (idempotencia).
    existing_urls = set(re.findall(r"\]\((\S+?)\)", body_md))
    source_urls = {(s.get("url") or "").strip() for s in sources if s.get("url")}
    budget = max_links - len(existing_urls & source_urls)
    if budget <= 0:
        return body_md

    # Dedup por nombre de medio (si varias fuentes son del mismo medio, se
    # queda la primera) y por url ya enlazada.
    seen_names: set[str] = set()
    seen_urls: set[str] = set(existing_urls)
    linked = 0
    for src in sources:
        if linked >= budget:
            break
        url = (src.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        name = _media_name_for_source(src)
        if not name:
            continue
        nkey = _normalize(name)
        if nkey in seen_names:
            continue
        new_body, n = _safe_link_first(body_md, name, url)
        if n > 0:
            body_md = new_body
            seen_names.add(nkey)
            seen_urls.add(url)
            linked += 1
    return body_md
