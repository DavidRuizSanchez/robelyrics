"""Política de enlazado interno: una sola fuente de verdad.

Hasta el 11-11-2026 cada camino comparaba los enlaces a su manera
(`entity_resolver._url_path`, `relink_existing._path`, `link_stats._to_path`) y
el autolinker comparaba las URLs EN CRUDO: el índice del corpus las da absolutas
(`https://entreinteriores.com/...`) y `url_resolver._reenlazar` las reescribe
relativas (`/sellos/...`). El autolinker no veía el enlace que ya existía, no lo
contaba en el tope y enlazaba la siguiente mención. Así `/personas/alen-ayerdi`
llegó a enlazar 6 veces a El Dromedario Records: uno más por pasada del cron.

Reglas de David (11-11-2026), medidas en `data/seo_plan_autoridad/MEDICIONES_FASE1.md`:

1. **1 enlace por destino y página.** El cuerpo no repite un destino de la
   plantilla. La garantía final va AL SERVIR (`web/lib/enlazado.ts`), porque la
   plantilla es dinámica; aquí la plantilla se pasa al autolinker como exclusión
   para que no gaste su presupuesto en enlaces que luego se pintan como texto.
2. **Como mucho `MAX_BODY_LINKS` (3) enlaces contextuales en el cuerpo.** Cuentan
   todas las rutas internas distintas del cuerpo salvo las que ya cubre la
   plantilla (esas se pintan como texto). Sustituye los 4/6/8/10/2 que tenía
   cada llamador.
3. **Relación, solo para temas y conceptos** (los lugares no: ver `_EXIGEN_RELACION`).
   Medido: el 100 % de lo que caía por esta regla en otros destinos eran enlaces
   que el propio texto respalda (Albert Pla → Extremoduro, Barricada → El
   Drogas); en taxonomías, casi todo era una palabra común («lucha»,
   «libertad») en una canción que no trata de eso. Las aristas `mentions` NO
   cuentan: saldrían de la propia mención y la regla sería circular.
4. **Anchors variados.** Además de los alias del índice, vale ampliar la mención
   con las palabras que YA la preceden en el texto («el disco *Agila*»). Entre
   las variantes presentes se elige la menos usada para ese destino
   (`internal_link_stats.json`, clave `__anchors__`). No se reescribe ninguna
   frase.

Hubs (`/discografia/*`, `/personas`): solo variantes de varias palabras, como
mucho uno por página, solo el del artista de la página y sin el impulso de
"página débil" (con 2 entrantes tendría ventaja fija).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

SITE_HOSTS = ("entreinteriores.com", "www.entreinteriores.com")
SITE = "https://entreinteriores.com"

MAX_BODY_LINKS = 3
MAX_HUBS_POR_PAGINA = 1

_ABSOLUTA = re.compile(r"^(?:https?:)?//([^/?#]+)(.*)$", re.IGNORECASE)
_NO_NAVEGABLE = ("mailto:", "tel:", "javascript:", "#")
_TAXONOMIA = frozenset({"temas", "conceptos", "lugares"})
# Solo temas y conceptos exigen relación (David, 11-11-2026): ahí el ruido son
# palabras comunes («lucha», «libertad»). Un lugar es nombre propio (exige
# mayúscula) y el grafo no sabe dónde nació o se formó nadie: la regla quitaba
# 37 enlaces que el texto respalda (Robe → Plasencia, Marea → Pamplona).
_EXIGEN_RELACION = frozenset({"temas", "conceptos"})
_ARISTAS_QUE_NO_RELACIONAN = frozenset({"mentions"})
_ARTISTAS = frozenset({"robe", "extremoduro"})

# Enlace markdown inline (no imágenes). Admite título: [x](url "título").
ENLACE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def norm_path(url: str | None) -> str | None:
    """Ruta interna comparable (`/a/b`, sin dominio, query, fragmento ni barra
    final), o `None` si el enlace no es interno.

    Dos enlaces apuntan a la misma página si y solo si dan la misma ruta aquí.
    """
    u = (url or "").strip()
    if not u or u.lower().startswith(_NO_NAVEGABLE):
        return None
    m = _ABSOLUTA.match(u)
    if m:
        host = m.group(1).lower().split(":", 1)[0]
        if host not in SITE_HOSTS:
            return None
        u = m.group(2)
    elif not u.startswith("/"):
        return None
    u = re.split(r"[?#]", u, maxsplit=1)[0]
    return "/" + u.strip("/")


def rutas_del_cuerpo(md: str | None) -> list[str]:
    """Rutas internas enlazadas en el cuerpo, en orden de aparición."""
    return [p for p in (norm_path(u) for _, u in ENLACE.findall(md or "")) if p]


def es_taxonomia(path: str) -> bool:
    partes = path.strip("/").split("/")
    return len(partes) == 2 and partes[0] in _TAXONOMIA


def exige_relacion(path: str) -> bool:
    partes = path.strip("/").split("/")
    return len(partes) == 2 and partes[0] in _EXIGEN_RELACION


def artista_de(path: str | None) -> str | None:
    """`robe` / `extremoduro` si la ruta es de su árbol, o None."""
    if not path:
        return None
    primera = path.strip("/").split("/", 1)[0]
    if primera in _ARTISTAS:
        return primera
    if primera == "discografia":
        resto = path.strip("/").split("/")
        return resto[1] if len(resto) > 1 and resto[1] in _ARTISTAS else None
    return None


def fold(s: str) -> str:
    """Minúsculas sin acentos ni marcas de énfasis: clave para contar anchors."""
    s = unicodedata.normalize("NFD", s.replace("*", "").replace("_", " "))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------- #
# Hubs: páginas índice que viven en código. Variantes de VARIAS palabras.
# --------------------------------------------------------------------------- #
HUBS: dict[str, dict] = {
    "/discografia/extremoduro": {
        "artista": "extremoduro",
        "variantes": ["discografía de Extremoduro", "discografía completa de Extremoduro",
                      "discos de Extremoduro", "álbumes de Extremoduro"],
    },
    "/discografia/robe": {
        "artista": "robe",
        "variantes": ["discografía de Robe", "discografía en solitario de Robe",
                      "discos de Robe", "discos en solitario de Robe", "álbumes de Robe"],
    },
    "/personas": {
        "artista": None,
        "variantes": ["miembros de Extremoduro", "integrantes de Extremoduro",
                      "músicos de Extremoduro", "formación de Extremoduro"],
    },
}

# Palabras que pueden preceder a la mención y formar parte del anchor. Solo se
# usan si YA están en el texto: no se reescribe nada.
PREFIJOS: dict[str, tuple[str, ...]] = {
    "album": ("el disco", "su disco", "el álbum", "su álbum", "el directo", "el recopilatorio"),
    "song": ("la canción", "su canción", "el tema", "el corte"),
    "band": ("el grupo", "la banda", "el sello", "la discográfica"),
    "artist": ("el grupo", "la banda"),
    "person": ("el guitarrista", "el bajista", "el batería", "el baterista",
               "el cantante", "el productor", "el poeta", "el músico"),
    "place": ("la ciudad de", "el pueblo de", "la localidad de"),
    "theme": (),
    "concept": (),
    "hub": (),
}


# --------------------------------------------------------------------------- #
# Contexto de una página: su ruta, lo que enlaza su plantilla y el grafo.
# --------------------------------------------------------------------------- #
@dataclass
class Relaciones:
    """Grafo no dirigido sobre rutas públicas, sin aristas `mentions`."""

    adj: dict[str, set[str]] = field(default_factory=dict)

    def relacionados(self, a: str | None, b: str) -> bool:
        if not a:
            return False
        va, vb = self.adj.get(a), self.adj.get(b)
        if not va or vb is None:
            return False
        return b in va or bool(va & vb)


@dataclass
class ContextoEnlazado:
    origen: str | None = None
    plantilla: frozenset[str] = frozenset()
    relaciones: Relaciones | None = None

    @property
    def migas(self) -> frozenset[str]:
        """Lo que enlazan las migas de pan: cada ruta madre de la página
        (`/extremoduro/agila/so-payaso` → `/extremoduro`, `/extremoduro/agila`).
        El autolinker no rellena con ellas: una canción ya enlaza su artista y su
        disco arriba (asesor, 11-11-2026: 24 de 236 enlaces nuevos iban ahí).
        No cuentan como plantilla en el recorte: el enlace del cuerpo se ve."""
        if not self.origen:
            return frozenset()
        partes = self.origen.strip("/").split("/")
        return frozenset("/" + "/".join(partes[:i]) for i in range(1, len(partes)))

    def admite(self, destino: str) -> bool:
        """Regla 3: un tema o un concepto exige relación en el grafo."""
        if not exige_relacion(destino):
            return True
        return self.relaciones is not None and self.relaciones.relacionados(self.origen, destino)


def rutas_de_nodos(db) -> dict[tuple[str, int], str]:
    """(tipo, id) → ruta pública, para todo el catálogo."""
    from app.db.models import Album, Artist, Band, Concept, Person, Place, Song, Theme

    artistas = {a.id: a.slug for a in db.query(Artist).all()}
    discos = {a.id: (artistas.get(a.artist_id), a.slug) for a in db.query(Album).all()}
    out: dict[tuple[str, int], str] = {}
    for aid, slug in artistas.items():
        out[("artist", aid)] = f"/{slug}"
    for alid, (art, slug) in discos.items():
        if art:
            out[("album", alid)] = f"/{art}/{slug}"
    for s in db.query(Song).all():
        art, alb = discos.get(s.album_id, (None, None))
        if art and alb:
            out[("song", s.id)] = f"/{art}/{alb}/{s.slug}"
    for p in db.query(Person).all():
        out[("person", p.id)] = f"/personas/{p.slug}"
    for b in db.query(Band).all():
        out[("band", b.id)] = f"/{'sellos' if b.kind == 'label' else 'grupos'}/{b.slug}"
    for t in db.query(Theme).all():
        out[("theme", t.id)] = f"/temas/{t.slug}"
    for p in db.query(Place).all():
        out[("place", p.id)] = f"/lugares/{p.slug}"
    for c in db.query(Concept).all():
        out[("concept", c.id)] = f"/conceptos/{c.slug}"
    return out


def cargar_relaciones(db, rutas: dict[tuple[str, int], str] | None = None) -> Relaciones:
    from app.db.models import EntityEdge

    rutas = rutas if rutas is not None else rutas_de_nodos(db)
    adj: dict[str, set[str]] = {}
    for e in db.query(EntityEdge).all():
        if e.edge_type in _ARISTAS_QUE_NO_RELACIONAN:
            continue
        a, b = rutas.get((e.src_type, e.src_id)), rutas.get((e.dst_type, e.dst_id))
        if a and b and a != b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return Relaciones(adj)


def plantilla_de(db, entity_type: str, entity_id: int,
                 rutas: dict[tuple[str, int], str]) -> frozenset[str]:
    """Rutas que enlaza la plantilla pública de esa ficha (espejo de las páginas
    de `web/app`). Si no se acierta del todo no pasa nada grave: la garantía
    final la da `MarkdownArticle` al servir."""
    from app.db.models import (
        Album,
        AlbumTrack,
        BandMembership,
        Song,
        SongConcept,
        SongCredit,
        SongPlace,
        SongTheme,
    )

    from app.services.person_visibility import ids_publicadas

    out: set[str] = set()
    publicadas = ids_publicadas(db)

    def r(tipo: str, i: int | None) -> None:
        # Una persona sin ficha publicada se nombra pero no se enlaza.
        if tipo == "person" and i not in publicadas:
            return
        p = rutas.get((tipo, i)) if i else None
        if p:
            out.add(p)

    if entity_type == "song":
        s = db.get(Song, entity_id)
        if s is None:
            return frozenset()
        r("album", s.album_id)
        for (sid,) in db.query(Song.id).filter(Song.album_id == s.album_id, Song.id != s.id):
            r("song", sid)
        for modelo, col, tipo in ((SongTheme, "theme_id", "theme"), (SongPlace, "place_id", "place"),
                                  (SongConcept, "concept_id", "concept")):
            for row in db.query(modelo).filter(modelo.song_id == s.id):
                r(tipo, getattr(row, col))
        for c in db.query(SongCredit).filter(SongCredit.song_id == s.id):
            r("person", c.person_id)
    elif entity_type == "album":
        al = db.get(Album, entity_id)
        if al is None:
            return frozenset()
        r("artist", al.artist_id)
        # Bloque «Discografía completa» de la ficha de disco (web/app/[artist]/[album]).
        if rutas.get(("artist", al.artist_id)):
            out.add("/discografia" + rutas[("artist", al.artist_id)])
        for (sid,) in db.query(Song.id).filter(Song.album_id == al.id):
            r("song", sid)
        for t in db.query(AlbumTrack).filter(AlbumTrack.album_id == al.id):
            r("song", t.song_id)
        # «Más discos»: los 6 más cercanos en el orden cronológico (MoreFromArtist).
        hermanos = (db.query(Album).filter(Album.artist_id == al.artist_id)
                    .order_by(Album.year, Album.id).all())
        idx = next((i for i, x in enumerate(hermanos) if x.id == al.id), None)
        if idx is not None:
            otros = sorted((x for x in hermanos if x.id != al.id),
                           key=lambda x: abs(hermanos.index(x) - idx))
            for x in otros[:6]:
                r("album", x.id)
    elif entity_type in ("theme", "place", "concept"):
        # El MISMO filtro que la API (`_detail_taxonomy`): solo canciones con
        # ficha publicada y, si hay estudio y directo, la de estudio.
        from app.db.models import Concept, Place, Theme
        from app.routers.public import _dedupe_studio_vs_live, _published_songs

        tax = db.get({"theme": Theme, "place": Place, "concept": Concept}[entity_type], entity_id)
        if tax is not None:
            for s in _dedupe_studio_vs_live(_published_songs(db, tax.songs)):
                r("song", s.id)
    elif entity_type == "person":
        for m in db.query(BandMembership).filter(BandMembership.person_id == entity_id):
            r("artist", m.artist_id)
    elif entity_type == "artist":
        if rutas.get(("artist", entity_id)):
            out.add("/discografia" + rutas[("artist", entity_id)])
        for (alid,) in db.query(Album.id).filter(Album.artist_id == entity_id):
            r("album", alid)
        for m in db.query(BandMembership).filter(BandMembership.artist_id == entity_id):
            r("person", m.person_id)
    return frozenset(out)


def contexto_de(db, entity_type: str | None, entity_id: int | None, *,
                rutas: dict[tuple[str, int], str] | None = None,
                relaciones: Relaciones | None = None) -> ContextoEnlazado:
    """Contexto de una ficha de `seo_content`. Nunca lanza: ante un fallo,
    contexto vacío (sin plantilla y sin relaciones: no enlaza taxonomías)."""
    try:
        rutas = rutas if rutas is not None else rutas_de_nodos(db)
        relaciones = relaciones if relaciones is not None else cargar_relaciones(db, rutas)
        if not entity_type or entity_id is None:
            return ContextoEnlazado(relaciones=relaciones)
        return ContextoEnlazado(
            origen=rutas.get((entity_type, entity_id)),
            plantilla=plantilla_de(db, entity_type, entity_id, rutas),
            relaciones=relaciones,
        )
    except Exception:  # noqa: BLE001
        return ContextoEnlazado()


def contexto_post(slug: str, relaciones: Relaciones | None = None) -> ContextoEnlazado:
    """Un post no es un nodo del grafo: sin relación, no enlaza taxonomías."""
    return ContextoEnlazado(origen=f"/blog/{slug}", relaciones=relaciones)


def presupuesto(md: str | None, plantilla: Iterable[str] = (),
                ya_en_pagina: Iterable[str] = (), maximo: int = MAX_BODY_LINKS) -> int:
    """Enlaces contextuales que caben todavía. Lo que ya cubre la plantilla no
    cuenta: se pinta como texto."""
    cubiertos = set(plantilla)
    propios = (set(rutas_del_cuerpo(md)) | set(ya_en_pagina)) - cubiertos
    return maximo - len(propios)


# --------------------------------------------------------------------------- #
# Relevancia y recorte: el MISMO criterio para el autolinker y la limpieza.
# --------------------------------------------------------------------------- #
# Peso del tipo de destino: contenido (disco/canción/artista) > taxonomía.
PESO_TIPO = {
    "album": 7, "song": 6, "artist": 5, "person": 4, "band": 4,
    "place": 3, "hub": 3, "otro": 3, "theme": 2, "concept": 1,
}


def relevancia(menciones: int, tipo: str, longitud_nombre: int) -> float:
    """Cuán central es el destino en el texto: frecuencia de mención, peso del
    tipo y especificidad del nombre (último desempate)."""
    return menciones * 30 + PESO_TIPO.get(tipo, 3) * 10 + longitud_nombre * 0.5


def solo_cambian_enlaces(antes: str, despues: str, *, permite_nuevos: bool = False) -> bool:
    """Invariante de la limpieza: el texto sin enlaces es idéntico byte a byte,
    los enlaces de después son un subconjunto de los de antes (salvo los
    internos nuevos del relleno, si `permite_nuevos`) y externos e imágenes no
    se tocan."""
    if ENLACE.sub(r"\1", antes) != ENLACE.sub(r"\1", despues):
        return False
    from collections import Counter

    a, d = Counter(ENLACE.findall(antes)), Counter(ENLACE.findall(despues))
    nuevos = d - a
    if nuevos and not (permite_nuevos and all(norm_path(u) for _, u in nuevos)):
        return False
    externos = lambda c: Counter({k: v for k, v in c.items() if norm_path(k[1]) is None})  # noqa: E731
    imagenes = re.compile(r"!\[[^\]]*\]\([^)]*\)")
    return externos(a) == externos(d) and imagenes.findall(antes) == imagenes.findall(despues)


@dataclass
class Recorte:
    md: str
    quitados: list[tuple[str, str, str]]  # (anchor, ruta, motivo)

    @property
    def cambia(self) -> bool:
        return bool(self.quitados)


IMPULSO_DEBIL = 60.0  # mismo `weak_k` que el autolinker


def recortar(md: str, ctx: ContextoEnlazado, *, tipo_de: dict[str, str] | None = None,
             nombres_de: dict[str, list[str]] | None = None,
             link_stats: dict[str, int] | None = None,
             maximo: int = MAX_BODY_LINKS) -> Recorte:
    """Aplica las reglas a un cuerpo ya publicado quitando ENLACES (el texto se
    queda). Motivos: `repetido` (se queda el primero), `propia` (la página a sí
    misma), `sin_relacion` (tema o concepto sin arista) y `tope` (pasa de 3: se quedan
    los de más relevancia, con impulso a los destinos que reciben menos enlaces,
    como en el autolinker).

    Lo que ya enlaza la plantilla NO se quita (asesor, 11-11-2026): al servir se
    pinta como texto (`web/lib/enlazado.ts`) y borrarlo ataría el cuerpo a una
    plantilla que cambia. Tampoco cuenta para el tope."""
    tipo_de, nombres_de, link_stats = tipo_de or {}, nombres_de or {}, link_stats or {}
    plano = ENLACE.sub(r"\1", md)
    vistos: set[str] = set()
    quitar: dict[int, str] = {}
    candidatos: list[tuple[re.Match, str]] = []
    for m in ENLACE.finditer(md):
        p = norm_path(m.group(2))
        if not p:
            continue
        if p in ctx.plantilla:
            pass  # se pinta como texto al servir; ni se quita ni cuenta
        elif p in vistos:
            quitar[m.start()] = "repetido"
        elif ctx.origen and p == ctx.origen:
            quitar[m.start()] = "propia"
        elif not ctx.admite(p):
            quitar[m.start()] = "sin_relacion"
        else:
            candidatos.append((m, p))
        vistos.add(p)
    if len(candidatos) > maximo:
        def puntos(item: tuple[re.Match, str]) -> tuple[float, int]:
            m, p = item
            nombres = set(nombres_de.get(p, [])) | {re.sub(r"[*_]", "", m.group(1))}
            menciones = sum(len(re.findall(rf"(?<!\w){re.escape(n)}(?!\w)", plano, re.I))
                            for n in nombres if n)
            largo = max(len(fold(n)) for n in nombres)
            tipo = tipo_de.get(p, "otro")
            puntos = relevancia(menciones, tipo, largo)
            if tipo != "hub":
                puntos += IMPULSO_DEBIL / (1 + link_stats.get(p, 0))
            return (-puntos, m.start())
        for m, _ in sorted(candidatos, key=puntos)[maximo:]:
            quitar[m.start()] = "tope"
    out, quitados, cursor = [], [], 0
    for m in ENLACE.finditer(md):
        if m.start() in quitar:
            out.append(md[cursor:m.start()] + m.group(1))
            cursor = m.end()
            quitados.append((m.group(1), norm_path(m.group(2)) or m.group(2), quitar[m.start()]))
    out.append(md[cursor:])
    return Recorte("".join(out), quitados)
