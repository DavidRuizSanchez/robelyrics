"""Resuelve cualquier URL interna del sitio contra la BD. Fuente única.

## Por qué existe

`/extremoduro/pedra/ama-ama-ama-y-ensancha-el-alma-en-directo` devolvía **200**.
La canción es de «Iros todos a tomar por culo», pero la página resolvía la canción
solo por su slug y pintaba el disco a partir del segmento de la URL: salía un
Frankenstein con el artículo de una canción y el tracklist, el prev/next y el
JSON-LD de OTRO disco. Cualquier combinación de artista/disco colaba.

Esas URLs no eran teóricas: las inventaba el LLM al enlazar dentro de los artículos.
`scripts/seo/fix_internal_links_manual.py` las desenlazaba a mano una a una.

Aquí vive la respuesta a "¿a qué apunta esta ruta?", y la contestan igual:

  - el endpoint público (para servir 404/redirect en vez de un Frankenstein),
  - `guard_internal_links` (antes de guardar un cuerpo generado),
  - `scripts/seo/audit_urls.py` (barrido de lo ya publicado),
  - los tests.

Una sola implementación: si la resolución cambia, cambia para todos a la vez.

## Cómo está montado

La lógica se escribe contra el protocolo `Catalog`, con dos implementaciones:

  - `DbCatalog(db)`  — consultas dirigidas y memoizadas. Es lo que usa la API:
    resolver una ruta son 2-3 SELECT por índice único, no cargar el catálogo.
  - `MemoryCatalog(...)` — el mismo protocolo desde listas en memoria, para los
    tests (sin Postgres, sin fixtures, sin red).

## La regla que no se negocia

Una ruta **nunca** se resuelve por un slug suelto. `songs.slug` solo es único
DENTRO de su álbum (`uq_songs_album_slug`) y `albums.slug` dentro de su artista
(`uq_albums_artist_slug`); consultarlos como si fueran únicos globales y rematar
con `.first()` es devolver una fila al azar. Cuando hay ambigüedad de verdad,
esto responde `not_found` — nunca adivina.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Dominio propio: el LLM a veces escribe la URL absoluta en vez de la ruta.
SITE_HOSTS = ("entreinteriores.com", "www.entreinteriores.com")

# Secciones de catálogo fuera del árbol /artista/disco/canción. La clave es el
# primer segmento de la URL; el valor, el `entity_type` de `seo_content`.
SECTIONS: dict[str, str] = {
    "personas": "person",
    "grupos": "band",
    "sellos": "band",
    "temas": "theme",
    "lugares": "place",
    "conceptos": "concept",
    "libros": "book",
    "blog": "post",
}

# Rutas estáticas de la app: existen siempre y no las valida nadie contra la BD.
STATIC_PATHS: frozenset[str] = frozenset({
    "", "/", "/blog", "/buscar", "/discografia", "/libros", "/temas", "/lugares",
    "/conceptos", "/personas", "/grupos", "/sellos", "/legal", "/sobre",
    "/registro", "/login", "/logout", "/newsletter", "/olvide-password",
    "/reset-password", "/verificar-email", "/biblioteca",
})

# Enlaces markdown `](/ruta)` y HTML `<a href="/ruta">`.
_MD_LINK_RE = re.compile(r"\]\((\S+?)\)")
_HREF_RE = re.compile(r"""<a\s[^>]*href=["']([^"']+)["']""", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Resultado
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Resolution:
    """A qué apunta una ruta.

    `canonical_path` SIEMPRE sale de la BD, nunca de la ruta que se preguntó: es
    justo la confusión que causó el bug original.
    """

    status: str                      # ok | redirect | not_found | not_catalog
    canonical_path: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    # exact | unpublished | typo_slug | cross_album | wrong_artist | ambiguous |
    # ghost_artist | ghost_album | ghost_song | ghost_entity | static | external
    reason: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.status in ("ok", "not_catalog")


# --------------------------------------------------------------------------- #
# El catálogo, como protocolo
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SongRow:
    id: int
    slug: str
    title: str
    album_slug: str
    artist_slug: str
    published: bool = True


class Catalog(Protocol):
    def artist_id(self, artist_slug: str) -> int | None: ...
    def album_slugs(self, artist_slug: str) -> list[str]: ...
    def album(self, artist_slug: str, album_slug: str) -> tuple[int, bool] | None: ...
    def song_slugs(self, artist_slug: str, album_slug: str) -> list[str]: ...
    def song(self, artist_slug: str, album_slug: str, song_slug: str) -> SongRow | None: ...
    def songs_by_slug(self, song_slug: str, artist_slug: str | None = None) -> list[SongRow]: ...
    def albums_by_slug(self, album_slug: str) -> list[tuple[int, str, bool]]: ...
    def section_entity(self, section: str, slug: str) -> tuple[int, bool] | None: ...
    def canonical_path(self, entity_type: str, entity_id: int) -> str | None: ...


# --------------------------------------------------------------------------- #
# Versiones en directo (se movieron desde routers/public.py: las necesitan los
# dos, y duplicar el criterio de "esto es un directo" es pedir que diverjan)
# --------------------------------------------------------------------------- #
def is_live_version(slug: str, title: str) -> bool:
    """True si la canción es una versión 'en directo'."""
    s = (slug or "").lower()
    t = (title or "").lower()
    return s.endswith("-en-directo") or "(en directo)" in t or "[en directo]" in t


def base_slug(slug: str) -> str:
    """El slug sin el sufijo `-en-directo`, para emparejar versiones."""
    if (slug or "").lower().endswith("-en-directo"):
        return slug[: -len("-en-directo")]
    return slug


# --------------------------------------------------------------------------- #
# Resolución tolerante de slug (mismo criterio que web/lib/slug-resolver.ts)
# --------------------------------------------------------------------------- #
def _unico(candidatos: list[str]) -> str | None:
    return candidatos[0] if len(candidatos) == 1 else None


def _tolerante(pedido: str, slugs: list[str]) -> str | None:
    """Prefijo, prefijo inverso, sufijo y normalizado. Solo si es inequívoco."""
    def norm(s: str) -> str:
        return s.replace("-", "").lower()

    return (
        _unico([s for s in slugs if s.startswith(f"{pedido}-")])
        or _unico([s for s in slugs if pedido.startswith(f"{s}-")])
        # Sufijo: «despues-de-la-catarsis» ← «primer-movimiento-despues-de-la-catarsis».
        or _unico([s for s in slugs if s.endswith(f"-{pedido}")])
        or _unico([s for s in slugs if pedido.endswith(f"-{s}")])
        or _unico([s for s in slugs if norm(s) == norm(pedido)])
    )


def resolve_slug(pedido: str, slugs: list[str]) -> str | None:
    """Slug parecido, solo si es INEQUÍVOCO. Con dos candidatos, ninguno.

    Los tres casos que `fix_internal_links_manual.py` tuvo que arreglar a mano
    salían de aquí, así que el criterio se amplió para cubrirlos sin dejar de
    exigir un ganador único:

      - por sufijo: `despues-de-la-catarsis` → `primer-movimiento-despues-de-la-catarsis`
      - ignorando el `-en-directo`: `bri-bri-bli-bli-en-directo` →
        `bri-bri-bli-bli-en-el-mas-sucio-rincon-de-mi-negro-corazon-en-directo`
      - por parecido: `abre-el-pecho-y-registra` → `abreme-el-pecho-y-registra`

    El parecido es el último recurso y el más goloso, así que exige listón alto
    (0.86) Y ventaja clara sobre el segundo: si dos slugs se parecen lo mismo,
    no hay respuesta y se devuelve None.
    """
    if not pedido or not slugs:
        return None
    if pedido in slugs:
        return pedido

    directo = _tolerante(pedido, slugs)
    if directo:
        return directo

    # Mismo criterio ignorando el sufijo de directo, prefiriendo candidatos de
    # la misma naturaleza (un directo se parea con un directo).
    base = base_slug(pedido)
    if base != pedido:
        mismos = [s for s in slugs if base_slug(s) != s] or slugs
        emparejado = _tolerante(base, [base_slug(s) for s in mismos])
        if emparejado:
            reales = [s for s in mismos if base_slug(s) == emparejado]
            if len(reales) == 1:
                return reales[0]

    from difflib import SequenceMatcher

    puntuados = sorted(
        ((SequenceMatcher(None, pedido, s).ratio(), s) for s in slugs),
        reverse=True,
    )
    mejor, segundo = puntuados[0], (puntuados[1] if len(puntuados) > 1 else (0.0, ""))
    if mejor[0] >= 0.86 and mejor[0] - segundo[0] >= 0.06:
        return mejor[1]
    return None


def _preferir_estudio(filas: list[SongRow]) -> SongRow | None:
    """Con varias canciones homónimas, la de estudio manda sobre el directo.

    Solo desempata si queda UNA. Si hay dos de estudio con el mismo slug en
    discos distintos, no hay respuesta correcta y se devuelve None: mejor un
    404 honesto que servir la ficha de otro disco.
    """
    if len(filas) == 1:
        return filas[0]
    estudio = [f for f in filas if not is_live_version(f.slug, f.title)]
    if len(estudio) == 1:
        return estudio[0]
    return None


# --------------------------------------------------------------------------- #
# Normalización de rutas
# --------------------------------------------------------------------------- #
def normalize_path(url: str) -> str | None:
    """Deja la ruta limpia, o None si la URL no es del sitio.

    Quita ancla y query, y admite la URL absoluta a nuestro dominio (el LLM la
    escribe a veces): `https://entreinteriores.com/temas/x` → `/temas/x`.
    """
    if not url:
        return None
    u = url.strip()
    if u.startswith("//"):
        return None
    if "://" in u:
        for host in SITE_HOSTS:
            for esquema in ("https://", "http://"):
                if u.lower().startswith(f"{esquema}{host}"):
                    u = u[len(f"{esquema}{host}"):] or "/"
                    break
            else:
                continue
            break
        else:
            return None            # dominio ajeno
    if not u.startswith("/"):
        return None                # relativo, mailto:, tel:, #ancla…
    u = u.split("#")[0].split("?")[0]
    if len(u) > 1:
        u = u.rstrip("/")
    return u or "/"


def extract_internal_links(body_md: str) -> list[str]:
    """Rutas internas citadas en un cuerpo, en orden y sin repetir.

    Coge el markdown `](/ruta)` y también el `<a href>` embebido: algunos
    cuerpos llevan HTML y mirar solo el markdown dejaba enlaces sin auditar.
    """
    if not body_md:
        return []
    crudas = _MD_LINK_RE.findall(body_md) + _HREF_RE.findall(body_md)
    salida: list[str] = []
    vistas: set[str] = set()
    for cruda in crudas:
        ruta = normalize_path(cruda)
        if ruta and ruta not in vistas:
            vistas.add(ruta)
            salida.append(ruta)
    return salida


# --------------------------------------------------------------------------- #
# Resolución
# --------------------------------------------------------------------------- #
def resolve_album(cat: Catalog, artist_slug: str, album_slug: str) -> Resolution:
    """Resuelve /artista/disco."""
    if cat.artist_id(artist_slug) is None:
        # El artista no existe: quizá el disco sí, bajo otro artista.
        candidatos = cat.albums_by_slug(album_slug)
        if len(candidatos) == 1:
            _id, real_artist, publicado = candidatos[0]
            return Resolution(
                "redirect", f"/{real_artist}/{album_slug}", "album", _id,
                "wrong_artist" if publicado else "unpublished",
            )
        return Resolution("not_found", reason="ghost_artist")

    encontrado = cat.album(artist_slug, album_slug)
    if encontrado is not None:
        _id, publicado = encontrado
        return Resolution(
            "ok", f"/{artist_slug}/{album_slug}", "album", _id,
            "exact" if publicado else "unpublished",
        )

    # Igual que en las canciones: lo exacto manda sobre lo parecido. ¿Existe ese
    # disco tal cual, bajo otro artista? (`/robe/la-ley-innata`)
    candidatos = cat.albums_by_slug(album_slug)
    if len(candidatos) == 1:
        _id, real_artist, _pub = candidatos[0]
        return Resolution(
            "redirect", f"/{real_artist}/{album_slug}", "album", _id, "wrong_artist",
        )
    if len(candidatos) > 1:
        return Resolution("not_found", reason="ambiguous")

    # No existe en ninguna parte: solo entonces, ¿un typo dentro del artista?
    parecido = resolve_slug(album_slug, cat.album_slugs(artist_slug))
    if parecido:
        encontrado = cat.album(artist_slug, parecido)
        if encontrado is not None:
            _id, _pub = encontrado
            return Resolution(
                "redirect", f"/{artist_slug}/{parecido}", "album", _id, "typo_slug",
            )
    return Resolution("not_found", reason="ghost_album")


def resolve_song(
    cat: Catalog, artist_slug: str, album_slug: str, song_slug: str
) -> Resolution:
    """Resuelve /artista/disco/canción.

    El orden manda, y es **lo exacto antes que lo parecido**: una canción que
    existe tal cual en otro disco es mejor respuesta que una que se parece en
    el disco pedido. Al revés, `/extremoduro/pedra/ama-...-en-directo` se
    quedaba atascado en «Pedrá existe, luego la canción es un fantasma» y no
    llegaba nunca a encontrar la canción de verdad.
    """
    # 1. Camino bueno: los tres segmentos casan.
    fila = cat.song(artist_slug, album_slug, song_slug)
    if fila is not None:
        return Resolution(
            "ok", _song_path(fila), "song", fila.id,
            "exact" if fila.published else "unpublished",
        )

    artista_ok = cat.artist_id(artist_slug) is not None

    # 2. La canción existe TAL CUAL en otro disco del mismo artista. ES EL CASO
    #    PEDRÁ, y da igual que el disco de la URL exista o no.
    if artista_ok:
        dentro = cat.songs_by_slug(song_slug, artist_slug)
        fila = _preferir_estudio(dentro)
        if fila is not None:
            return Resolution(
                "redirect", _song_path(fila), "song", fila.id, "cross_album",
            )
        if dentro:
            return Resolution("not_found", reason="ambiguous")

    # 3. Existe tal cual, pero bajo otro artista.
    todas = cat.songs_by_slug(song_slug)
    fila = _preferir_estudio(todas)
    if fila is not None:
        return Resolution(
            "redirect", _song_path(fila), "song", fila.id,
            "wrong_artist" if artista_ok else "cross_album",
        )
    if todas:
        return Resolution("not_found", reason="ambiguous")

    # 4. No existe en ningún sitio: solo entonces se acepta un parecido, y solo
    #    dentro del disco pedido (si es real).
    if artista_ok and cat.album(artist_slug, album_slug) is not None:
        parecido = resolve_slug(song_slug, cat.song_slugs(artist_slug, album_slug))
        if parecido:
            fila = cat.song(artist_slug, album_slug, parecido)
            if fila is not None:
                return Resolution(
                    "redirect", _song_path(fila), "song", fila.id, "typo_slug",
                )

    return Resolution("not_found", reason="ghost_song")


def _song_path(fila: SongRow) -> str:
    return f"/{fila.artist_slug}/{fila.album_slug}/{fila.slug}"


def resolve_path(cat: Catalog, path: str) -> Resolution:
    """Resuelve cualquier ruta interna del sitio.

    `not_catalog` = ruta estática o ajena: válida, pero no hay nada que validar.
    """
    ruta = normalize_path(path)
    if ruta is None:
        return Resolution("not_catalog", reason="external")
    if ruta in STATIC_PATHS:
        return Resolution("not_catalog", canonical_path=ruta, reason="static")

    partes = [p for p in ruta.strip("/").split("/") if p]
    if not partes:
        return Resolution("not_catalog", canonical_path="/", reason="static")

    # Secciones fuera del árbol del catálogo (/personas/x, /temas/x, /blog/x…).
    # Antes se daban por buenas sin mirar, así que un /personas/inexistente era
    # invisible para la auditoría.
    seccion = SECTIONS.get(partes[0])
    if seccion is not None:
        if len(partes) != 2:
            return Resolution("not_catalog", canonical_path=ruta, reason="static")
        encontrado = cat.section_entity(partes[0], partes[1])
        if encontrado is None and partes[0] in ("grupos", "sellos"):
            # Grupos y sellos comparten tabla (`bands.kind`) pero cada uno tiene
            # su prefijo. El LLM enlaza los sellos como si fueran grupos, y esos
            # enlaces dan 404: Avispa, Warner o El Dromedario Records viven en
            # /sellos, no en /grupos. Como se sabe dónde están de verdad, se
            # propone el destino en vez de dejarlo como fantasma sin arreglo.
            hermano = "sellos" if partes[0] == "grupos" else "grupos"
            otro = cat.section_entity(hermano, partes[1])
            if otro is not None:
                return Resolution(
                    "redirect", f"/{hermano}/{partes[1]}", "band", otro[0],
                    "wrong_section",
                )
        if encontrado is None:
            return Resolution("not_found", reason="ghost_entity")
        _id, publicado = encontrado
        return Resolution(
            "ok", ruta, seccion, _id, "exact" if publicado else "unpublished",
        )

    if partes[0] == "biblioteca":
        return Resolution("not_catalog", canonical_path=ruta, reason="static")

    if len(partes) == 1:
        _id = cat.artist_id(partes[0])
        if _id is None:
            return Resolution("not_found", reason="ghost_artist")
        return Resolution("ok", f"/{partes[0]}", "artist", _id, "exact")

    if len(partes) == 2:
        return resolve_album(cat, partes[0], partes[1])

    if len(partes) == 3:
        return resolve_song(cat, partes[0], partes[1], partes[2])

    # Más de tres segmentos no es ninguna ruta del sitio. Antes se daba por
    # buena; ahora se reporta, que es como se ven los enlaces inventados.
    return Resolution("not_found", reason="ghost_entity")


# --------------------------------------------------------------------------- #
# Catálogo contra la BD
# --------------------------------------------------------------------------- #
class DbCatalog:
    """Catálogo servido por consultas dirigidas y memoizadas.

    Memoiza por instancia: en una request se resuelve una ruta (2-3 SELECT por
    índice único) y en el barrido se reaprovecha entre los miles de enlaces de
    un mismo cuerpo. No se cachea entre peticiones a propósito: una ficha nueva
    tiene que verse al momento.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._memo: dict[tuple, object] = {}

    def _cache(self, clave: tuple, calcular):
        if clave not in self._memo:
            self._memo[clave] = calcular()
        return self._memo[clave]

    # -- artistas / discos / canciones -------------------------------------- #
    def artist_id(self, artist_slug: str) -> int | None:
        from app.db.models import Artist

        return self._cache(("artist", artist_slug), lambda: self.db.execute(
            select(Artist.id).where(Artist.slug == artist_slug)
        ).scalar_one_or_none())

    def album_slugs(self, artist_slug: str) -> list[str]:
        from app.db.models import Album, Artist

        return self._cache(("album_slugs", artist_slug), lambda: [
            r[0] for r in self.db.execute(
                select(Album.slug).join(Artist).where(Artist.slug == artist_slug)
            ).all()
        ])

    def album(self, artist_slug: str, album_slug: str) -> tuple[int, bool] | None:
        from app.db.models import Album, Artist

        def calcular():
            fila = self.db.execute(
                select(Album.id).join(Artist).where(
                    Artist.slug == artist_slug, Album.slug == album_slug,
                )
            ).first()
            return (fila[0], self._publicado("album", fila[0])) if fila else None

        return self._cache(("album", artist_slug, album_slug), calcular)

    def albums_by_slug(self, album_slug: str) -> list[tuple[int, str, bool]]:
        from app.db.models import Album, Artist

        return self._cache(("albums_by_slug", album_slug), lambda: [
            (r[0], r[1], self._publicado("album", r[0]))
            for r in self.db.execute(
                select(Album.id, Artist.slug).join(Artist)
                .where(Album.slug == album_slug).order_by(Album.id)
            ).all()
        ])

    def song_slugs(self, artist_slug: str, album_slug: str) -> list[str]:
        from app.db.models import Album, Artist, Song

        return self._cache(("song_slugs", artist_slug, album_slug), lambda: [
            r[0] for r in self.db.execute(
                select(Song.slug).join(Album).join(Artist).where(
                    Artist.slug == artist_slug, Album.slug == album_slug,
                )
            ).all()
        ])

    def song(
        self, artist_slug: str, album_slug: str, song_slug: str
    ) -> SongRow | None:
        from app.db.models import Album, Artist, Song

        def calcular():
            fila = self.db.execute(
                select(Song.id, Song.slug, Song.title).join(Album).join(Artist)
                .where(
                    Artist.slug == artist_slug,
                    Album.slug == album_slug,
                    Song.slug == song_slug,
                )
            ).first()
            if not fila:
                return None
            return SongRow(
                id=fila[0], slug=fila[1], title=fila[2], album_slug=album_slug,
                artist_slug=artist_slug, published=self._publicado("song", fila[0]),
            )

        return self._cache(("song", artist_slug, album_slug, song_slug), calcular)

    def songs_by_slug(
        self, song_slug: str, artist_slug: str | None = None
    ) -> list[SongRow]:
        from app.db.models import Album, Artist, Song

        def calcular():
            q = (
                select(Song.id, Song.slug, Song.title, Album.slug, Artist.slug)
                .join(Album, Song.album_id == Album.id)
                .join(Artist, Album.artist_id == Artist.id)
                .where(Song.slug == song_slug)
            )
            if artist_slug is not None:
                q = q.where(Artist.slug == artist_slug)
            return [
                SongRow(
                    id=r[0], slug=r[1], title=r[2], album_slug=r[3], artist_slug=r[4],
                    published=self._publicado("song", r[0]),
                )
                for r in self.db.execute(q.order_by(Song.id)).all()
            ]

        return self._cache(("songs_by_slug", song_slug, artist_slug), calcular)

    # -- secciones ----------------------------------------------------------- #
    def section_entity(self, section: str, slug: str) -> tuple[int, bool] | None:
        def calcular():
            from app.db.models import (
                Band,
                Book,
                Concept,
                Person,
                Place,
                Post,
                Theme,
            )

            if section == "blog":
                fila = self.db.execute(
                    select(Post.id, Post.status).where(Post.slug == slug)
                ).first()
                return (fila[0], fila[1] == "published") if fila else None

            if section in ("grupos", "sellos"):
                esperado = "label" if section == "sellos" else "band"
                fila = self.db.execute(
                    select(Band.id, Band.kind).where(Band.slug == slug)
                ).first()
                if not fila:
                    return None
                # Un sello enlazado como /grupos/x no está en su sitio: el
                # frontend sirve cada kind bajo su prefijo.
                if (fila[1] or "band") != esperado:
                    return None
                return fila[0], self._publicado("band", fila[0])

            modelo = {
                "personas": Person, "temas": Theme, "lugares": Place,
                "conceptos": Concept, "libros": Book,
            }[section]
            fila = self.db.execute(
                select(modelo.id).where(modelo.slug == slug)
            ).first()
            if not fila:
                return None
            return fila[0], self._publicado(SECTIONS[section], fila[0])

        return self._cache(("section", section, slug), calcular)

    # -- publicación y canónica ---------------------------------------------- #
    def _publicado(self, entity_type: str, entity_id: int) -> bool:
        """¿Tiene ficha SEO publicada? Sin ella la página pública da 404.

        Las taxonomías y los libros se sirven aunque no tengan ficha, así que
        para ellas esto siempre es True.
        """
        if entity_type in ("theme", "place", "concept", "book"):
            return True

        from app.db.models import SeoContent

        def calcular():
            return self.db.execute(
                select(SeoContent.published).where(
                    SeoContent.entity_type == entity_type,
                    SeoContent.entity_id == entity_id,
                )
            ).scalar_one_or_none() is True

        return self._cache(("pub", entity_type, entity_id), calcular)

    def canonical_path(self, entity_type: str, entity_id: int) -> str | None:
        """La ruta pública de una entidad, siempre derivada de la BD."""
        from app.db.models import (
            Album,
            Artist,
            Band,
            Book,
            Concept,
            Person,
            Place,
            Post,
            Song,
            Theme,
        )

        def calcular():
            if entity_type == "artist":
                s = self.db.get(Artist, entity_id)
                return f"/{s.slug}" if s else None
            if entity_type == "album":
                a = self.db.get(Album, entity_id)
                return f"/{a.artist.slug}/{a.slug}" if a else None
            if entity_type == "song":
                s = self.db.get(Song, entity_id)
                return f"/{s.album.artist.slug}/{s.album.slug}/{s.slug}" if s else None
            if entity_type == "band":
                b = self.db.get(Band, entity_id)
                if not b:
                    return None
                return f"/{'sellos' if b.kind == 'label' else 'grupos'}/{b.slug}"
            prefijos = {
                "person": ("personas", Person), "theme": ("temas", Theme),
                "place": ("lugares", Place), "concept": ("conceptos", Concept),
                "book": ("libros", Book), "post": ("blog", Post),
            }
            if entity_type not in prefijos:
                return None
            prefijo, modelo = prefijos[entity_type]
            fila = self.db.get(modelo, entity_id)
            return f"/{prefijo}/{fila.slug}" if fila else None

        return self._cache(("canon", entity_type, entity_id), calcular)


# --------------------------------------------------------------------------- #
# Catálogo en memoria (tests)
# --------------------------------------------------------------------------- #
@dataclass
class MemoryCatalog:
    """El mismo protocolo desde listas. Para probar sin Postgres."""

    artists: dict[str, int] = field(default_factory=dict)
    albums: list[tuple[int, str, str, bool]] = field(default_factory=list)
    songs: list[SongRow] = field(default_factory=list)
    sections: dict[tuple[str, str], tuple[int, bool]] = field(default_factory=dict)

    def artist_id(self, artist_slug):
        return self.artists.get(artist_slug)

    def album_slugs(self, artist_slug):
        return [s for _i, s, a, _p in self.albums if a == artist_slug]

    def album(self, artist_slug, album_slug):
        for _id, slug, art, pub in self.albums:
            if slug == album_slug and art == artist_slug:
                return _id, pub
        return None

    def albums_by_slug(self, album_slug):
        return [(i, a, p) for i, s, a, p in self.albums if s == album_slug]

    def song_slugs(self, artist_slug, album_slug):
        return [
            s.slug for s in self.songs
            if s.artist_slug == artist_slug and s.album_slug == album_slug
        ]

    def song(self, artist_slug, album_slug, song_slug):
        for s in self.songs:
            if (s.artist_slug, s.album_slug, s.slug) == (
                artist_slug, album_slug, song_slug
            ):
                return s
        return None

    def songs_by_slug(self, song_slug, artist_slug=None):
        return [
            s for s in self.songs
            if s.slug == song_slug
            and (artist_slug is None or s.artist_slug == artist_slug)
        ]

    def section_entity(self, section, slug):
        return self.sections.get((section, slug))

    def canonical_path(self, entity_type, entity_id):
        if entity_type == "song":
            for s in self.songs:
                if s.id == entity_id:
                    return _song_path(s)
        if entity_type == "album":
            for _id, slug, art, _p in self.albums:
                if _id == entity_id:
                    return f"/{art}/{slug}"
        return None


# --------------------------------------------------------------------------- #
# Atajos contra la BD (lo que consume la API)
# --------------------------------------------------------------------------- #
def resolve_path_db(db: Session, path: str) -> Resolution:
    return resolve_path(DbCatalog(db), path)


def resolve_song_db(
    db: Session, artist_slug: str, album_slug: str, song_slug: str
) -> Resolution:
    return resolve_song(DbCatalog(db), artist_slug, album_slug, song_slug)


def resolve_album_db(db: Session, artist_slug: str, album_slug: str) -> Resolution:
    return resolve_album(DbCatalog(db), artist_slug, album_slug)


def canonical_path_for(db: Session, entity_type: str, entity_id: int) -> str | None:
    return DbCatalog(db).canonical_path(entity_type, entity_id)


# --------------------------------------------------------------------------- #
# Guard de escritura
# --------------------------------------------------------------------------- #
@dataclass
class LinkGuardResult:
    body_md: str
    fixed: list[tuple[str, str]] = field(default_factory=list)   # (roto, canónico)
    unlinked: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.fixed or self.unlinked)

    def summary(self) -> str:
        trozos = []
        if self.fixed:
            trozos.append(
                "corregidos " + ", ".join(f"{a}→{b}" for a, b in self.fixed[:5])
            )
        if self.unlinked:
            trozos.append("desenlazados " + ", ".join(self.unlinked[:5]))
        return "; ".join(trozos) or "sin cambios"


def _patron_ruta(ruta: str) -> str:
    """Todas las formas en que un cuerpo puede escribir la MISMA ruta.

    El LLM enlaza indistintamente `/grupos/pasion` y
    `https://entreinteriores.com/grupos/pasion`, con o sin barra final. El
    extractor las normaliza todas a la ruta, así que el reescritor tiene que
    reconocerlas todas: buscando solo la forma relativa, los enlaces absolutos
    se detectaban pero no se arreglaban («0 cambios» con 14 hallazgos).
    """
    hosts = "|".join(re.escape(h) for h in SITE_HOSTS)
    return rf"(?:https?://(?:{hosts}))?{re.escape(ruta)}/?"


def _desenlazar(body: str, ruta: str) -> str:
    """`[texto](ruta)` → `texto`. El texto se queda; solo cae el enlace."""
    md = re.compile(
        r"\[([^\]]*)\]\(" + _patron_ruta(ruta) + r"(?:[#?][^)\s]*)?\)"
    )
    body = md.sub(r"\1", body)
    # Y el mismo enlace escrito en HTML, que también viaja en algunos cuerpos.
    html = re.compile(
        r"<a\s[^>]*href=[\"']" + _patron_ruta(ruta)
        + r"(?:[#?][^\"']*)?[\"'][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    return html.sub(r"\1", body)


def _reenlazar(body: str, ruta: str, canonica: str) -> str:
    """Reemplaza TODAS las apariciones de la ruta rota por la buena.

    El destino se escribe siempre como ruta relativa, aunque el original fuera
    absoluto: los enlaces internos del sitio no tienen por qué llevar el dominio.
    """
    md = re.compile(
        r"\]\(" + _patron_ruta(ruta) + r"((?:[#?][^)\s]*)?)\)"
    )
    body = md.sub(lambda m: f"]({canonica}{m.group(1)})", body)
    html = re.compile(
        r"(<a\s[^>]*href=[\"'])" + _patron_ruta(ruta) + r"((?:[#?][^\"']*)?[\"'])",
        re.IGNORECASE,
    )
    return html.sub(lambda m: f"{m.group(1)}{canonica}{m.group(2)}", body)


def guard_internal_links(db: Session, body_md: str) -> LinkGuardResult:
    """Valida cada enlace interno del cuerpo contra la BD antes de guardarlo.

    Este es el eslabón que faltaba: `fact_check`, `focus_check`, `lyric_guard` y
    `editorial_review` revisan el TEXTO; ninguno miraba una URL, y por eso los
    enlaces inventados por el LLM llegaban publicados.

    Lo que tiene ruta real se reescribe a la buena; el fantasma se desenlaza
    conservando el texto (borrar la frase sería peor que quitarle el enlace).
    Determinista, sin red y sin LLM. **Nunca lanza**: ante cualquier fallo
    devuelve el cuerpo intacto, que una generación de dos minutos no se puede
    caer por un enlace.
    """
    if not body_md:
        return LinkGuardResult(body_md=body_md or "")
    try:
        cat = DbCatalog(db)
        salida = LinkGuardResult(body_md=body_md)
        for ruta in extract_internal_links(body_md):
            res = resolve_path(cat, ruta)
            if res.is_ok:
                continue
            if res.status == "redirect" and res.canonical_path:
                salida.body_md = _reenlazar(salida.body_md, ruta, res.canonical_path)
                salida.fixed.append((ruta, res.canonical_path))
            else:
                salida.body_md = _desenlazar(salida.body_md, ruta)
                salida.unlinked.append(ruta)
        if salida.changed:
            logger.info("[links] %s", salida.summary())
        return salida
    except Exception as exc:  # noqa: BLE001
        logger.warning("[links] guard no pudo correr, cuerpo intacto: %s", exc)
        return LinkGuardResult(body_md=body_md)
