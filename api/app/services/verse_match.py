"""¿Esta búsqueda cita un verso? Entonces es de la ficha de su canción.

Caso real (26-10-2026): «soy evaristo el rey de la baraja» iba a /temas/religion
porque Google enseña hoy esa página (150 + 137 impresiones), cuando es un verso
de «Jesucristo García». Nadie buscaba versos: `kw_attribute.dueno` solo casa
títulos.

Determinista y sin red. Una búsqueda cita un verso si contiene al menos
`MIN_PALABRAS` palabras SEGUIDAS de una línea de la letra (o de dos líneas
consecutivas), con al menos `MIN_CONTENIDO` palabras de contenido: «que no me da»
está en media discografía y no dice nada. Y solo decide si el verso es de UNA
composición; las versiones (regrabación de 1994, directo de 1997) son la misma.

Medido sobre las 2.526 consultas de GSC (2026-07-31..2026-10-23): casan 203, y los
falsos positivos eran TÍTULOS de disco que también son un verso («tú en tu casa,
nosotros en la hoguera» → La Hoguera). Por eso quien lo usa mira antes el título
(`content_placement.repartir`). La cita tiene que cubrir además la mitad del
contenido de la búsqueda, para no decidir por un trozo de cuatro palabras.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services import seo_style
from app.services.kw_normalize import kw_norm, strip_title_suffix
from app.services.lyric_guard import normalize

MIN_PALABRAS = 4
MIN_CONTENIDO = 2
MIN_COBERTURA = 0.5
# Lo que acompaña a un verso en una búsqueda y no es parte de él.
_ACOMPANAN = {"significado", "significa", "quien", "trata", "extremoduro", "robe",
              "roberto", "iniesta", "songtext", "cancion", "letra"}


@dataclass(frozen=True)
class Composicion:
    clave: str                 # título sin sufijo, normalizado
    titulo: str
    song_ids: tuple[int, ...]  # original y más antigua primero; luego regrabaciones y directos
    textos: tuple[str, ...]    # líneas normalizadas, y cada par consecutivo unido


@dataclass(frozen=True)
class Verso:
    clave: str
    titulo: str
    song_ids: tuple[int, ...]
    cita: str                  # las palabras de la búsqueda que están en la letra


def _clave(titulo: str) -> str:
    return kw_norm(strip_title_suffix(titulo or ""))


def cargar(db) -> list[Composicion]:
    """Las composiciones con su letra. Una lectura de `lines`; cachear por análisis."""
    from sqlalchemy import select

    from app.db.models import Album, Line, Song
    from app.services.versiones import es_original, version_original

    filas = db.execute(
        select(Song.id, Line.text).join(Line, Line.song_id == Song.id)
        .order_by(Song.id, Line.line_index)
    ).all()
    lineas: dict[int, list[str]] = {}
    for sid, texto in filas:
        n = normalize(texto or "")
        if n:
            lineas.setdefault(sid, []).append(n)

    grupos: dict[str, dict] = {}
    for song in db.query(Song).filter(Song.id.in_(list(lineas))).all():
        original = version_original(db, song)
        k = _clave(original.title)
        g = grupos.setdefault(k, {"titulo": strip_title_suffix(original.title),
                                  "ids": [], "textos": []})
        album = db.get(Album, song.album_id) if song.album_id else None
        g["ids"].append((not es_original(song, album), (album.year if album else None) or 9999,
                         song.id))
        ls = lineas[song.id]
        g["textos"] += ls + [f"{a} {b}" for a, b in zip(ls, ls[1:], strict=False)]
    return [Composicion(k, g["titulo"], tuple(i for *_, i in sorted(g["ids"])),
                        tuple(dict.fromkeys(g["textos"])))
            for k, g in grupos.items()]


def _contenido(palabras: list[str]) -> int:
    """Palabras distintas que dicen algo. Se exigen 4 letras porque «no», «me» o
    «da» no están en ninguna lista de vacías y «y que no me» casaba como verso."""
    return len({t for t in seo_style.content_tokens(" ".join(palabras)) if len(t) >= 4})


def verso_de(keyword: str, composiciones: list[Composicion]) -> Verso | None:
    """El verso que cita la búsqueda, si es de UNA sola composición."""
    palabras = normalize(keyword).split()
    if len(palabras) < MIN_PALABRAS:
        return None
    propio = {t for t in seo_style.content_tokens(keyword) if t not in _ACOMPANAN}
    # Ventanas de la más larga a la más corta: la cita más larga es la que manda.
    for largo in range(len(palabras), MIN_PALABRAS - 1, -1):
        hits: dict[str, tuple[Composicion, str]] = {}
        for i in range(len(palabras) - largo + 1):
            ventana = palabras[i:i + largo]
            if _contenido(ventana) < MIN_CONTENIDO:
                continue
            cubierto = propio & set(seo_style.content_tokens(" ".join(ventana)))
            if propio and len(cubierto) / len(propio) < MIN_COBERTURA:
                continue
            frase = f" {' '.join(ventana)} "
            for c in composiciones:
                if c.clave not in hits and any(frase in f" {t} " for t in c.textos):
                    hits[c.clave] = (c, frase.strip())
        if len(hits) == 1:
            c, cita = next(iter(hits.values()))
            return Verso(c.clave, c.titulo, c.song_ids, cita)
        if len(hits) > 1:
            return None      # el mismo verso en dos canciones: no decide
    return None
