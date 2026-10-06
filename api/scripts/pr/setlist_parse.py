"""Parseo DETERMINISTA de las páginas públicas de estadísticas de setlist.fm.

Por qué a mano y no con un modelo leyendo la página: midiendo las mismas cifras
por dos caminos salieron DISTINTAS. Una búsqueda resumida daba «Ama, ama, ama»
con 140 toques y «Jesucristo García» con 126; la página dice 143 y 130. Para un
entregable público con cada celda trazable, un resumidor no vale: la cifra tiene
que salir del atributo del HTML, que no opina.

Las cifras viven en atributos, no en el texto:
    <td class="songCount" data-stats-sort="143"><span>143</span></td>
y el título en `data-stats-sort` del `td.songName`, que es el título limpio (el
`<span>` interior va envuelto en enlaces de «Play Video» y de estadísticas).

Lo que estas funciones NO hacen, a propósito:
  · No tocan la BD. El dato de setlist.fm no entra en nuestro catálogo.
  · No devuelven su tabla para republicarla, sino lo necesario para calcular
    agregados e índices derivados propios.

AVISO MEDIDO (06-10-2026): los desgloses POR GIRA de setlist.fm no son fiables.
La página de «Agila 96» declara 53 conciertos y su canción más tocada sale con 4
toques; la del setlist promedio avisa de que solo usó 2 de los 53. No construir
series temporales con ellos. Los totales por artista y por disco sí cuadran.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

# <tr class="songRow even"> … <td class="songName" data-stats-sort="TÍTULO">
#   … <td class="songCount" data-stats-sort="143">
_FILA_CANCION = re.compile(r'<tr[^>]*class="songRow[^"]*"[^>]*>(.*?)</tr>', re.S)
_TITULO = re.compile(r'<td[^>]*class="songName"[^>]*data-stats-sort="([^"]*)"')
_TOQUES = re.compile(r'<td[^>]*class="songCount"[^>]*data-stats-sort="(\d+)"')

# La página de discos no lleva `data-stats-sort`: la fila es
# «<td class="countId">1</td> … <span>Deltoya</span> … 465».
_FILA_DISCO = re.compile(r'<tr[^>]*class="(?:even|odd)"[^>]*>(.*?)</tr>', re.S)

# «All setlist songs ( 459 )» — el total de setlists del artista.
_TOTAL = re.compile(r"All setlist songs\s*\(\s*(\d+)\s*\)")

# Años y giras. El contador NO va junto al nombre: va en un SEGUNDO enlace, el
# que apunta al buscador. La estructura real es
#   <a href="..?year=2014"><span>2014</span></a>&nbsp;(<a href="../search?..&year=2014"><span>44</span></a>)
# así que anclar en el primer enlace y buscar «( n )» detrás no casa nada —
# fue el primer intento y devolvió cero filas en las dos páginas.
_ANYO = re.compile(r'href="\.\./search\?artist=[0-9a-f]+&amp;year=(\d{4})"[^>]*>\s*<span>(\d+)</span>')
# La gira se empareja por su ID entre los dos enlaces. El nombre se saca del
# `title` y no del `<span>`, porque el span puede venir recortado con «…».
_GIRA_NOMBRE = re.compile(r'href="[^"]*\?tour=([0-9a-f]+)"\s+title="Show song statistics of the tour ([^"]+)"')
_GIRA_CUENTA = re.compile(r'href="\.\./search\?artist=[0-9a-f]+&amp;tour=([0-9a-f]+)"[^>]*>\s*<span>(\d+)</span>')


def _texto(fragmento: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragmento))).strip()


@dataclass(frozen=True)
class Cancion:
    titulo: str
    toques: int


@dataclass(frozen=True)
class EstadisticasArtista:
    """Lo que da UNA página de estadísticas de artista, sin parámetros."""

    slug: str
    setlists: int | None
    canciones: tuple[Cancion, ...]
    anyos: tuple[tuple[int, int], ...]   # (año, conciertos)
    giras: tuple[tuple[str, int], ...]   # (gira, conciertos)
    #: True si la tabla llegó al tope de filas de la página. OJO: no basta
    #: contar filas. Extremoduro devuelve exactamente 100, que es el tope, y
    #: aun así está COMPLETA — se comprueba porque sus toques suman 3.295, lo
    #: mismo que la página de discos, que no tiene tope. Si faltaran canciones,
    #: cada una con 1+ toque, las dos sumas no podrían coincidir. Para eso está
    #: `cuadra_con_discos()`.
    truncada: bool

    @property
    def toques_totales(self) -> int:
        return sum(c.toques for c in self.canciones)

    @property
    def anyos_completos(self) -> bool:
        """Los bloques «Years on tour» y «Tours» de la página solo traen los
        primeros; el resto está detrás de un «Show all» que es JavaScript.
        Medido en Extremoduro: 8 años visibles suman 317 de 459 setlists, o sea
        que falta el 31%. Publicar «conciertos por año» con esto sería publicar
        una serie con agujeros sin decirlo."""
        if self.setlists is None or not self.anyos:
            return False
        return sum(n for _, n in self.anyos) == self.setlists

    @property
    def giras_completas(self) -> bool:
        if self.setlists is None or not self.giras:
            return False
        return sum(n for _, n in self.giras) == self.setlists

    def cuadra_con_discos(self, discos: tuple[tuple[str, int], ...]) -> bool:
        """Validación cruzada entre dos tablas de páginas distintas. Es la
        prueba de que la extracción no se ha dejado filas por el camino."""
        return self.toques_totales == sum(n for _, n in discos)


TOPE_TABLA = 100


def parse_artista(html_doc: str, slug: str) -> EstadisticasArtista:
    canciones: list[Cancion] = []
    for fila in _FILA_CANCION.findall(html_doc):
        t, n = _TITULO.search(fila), _TOQUES.search(fila)
        if t and n:
            canciones.append(Cancion(html.unescape(t.group(1)).strip(), int(n.group(1))))

    plano = _texto(html_doc)
    total = _TOTAL.search(plano)

    anyos = sorted({(int(m.group(1)), int(m.group(2))) for m in _ANYO.finditer(html_doc)})

    nombres = {gid: html.unescape(nombre).strip() for gid, nombre in _GIRA_NOMBRE.findall(html_doc)}
    cuentas = {gid: int(n) for gid, n in _GIRA_CUENTA.findall(html_doc)}
    giras = sorted(
        (nombres[gid], cuentas[gid]) for gid in nombres.keys() & cuentas.keys()
    )

    return EstadisticasArtista(
        slug=slug,
        setlists=int(total.group(1)) if total else None,
        canciones=tuple(canciones),
        anyos=tuple(anyos),
        giras=tuple(giras),
        truncada=len(canciones) >= TOPE_TABLA,
    )


def parse_discos(html_doc: str) -> tuple[tuple[str, int], ...]:
    """Toques agrupados por disco. Incluye los cajones «Covers» y «Others», que
    NO son discos: se devuelven igual porque son el dato más interesante de la
    página de Robe —«Covers» es su bloque más tocado, y ahí está el legado de
    Extremoduro— y filtrarlos aquí escondería eso."""
    salida: list[tuple[str, int]] = []
    for fila in _FILA_DISCO.findall(html_doc):
        nombre = re.search(r"<span>([^<]+)</span>", fila)
        if not nombre:
            continue
        # La fila es «<posición> <nombre> <toques>»: el contador es el último
        # entero del texto. Cogerlo por posición y no por el primero que
        # aparezca evita quedarse con el número de orden.
        numeros = re.findall(r"\b(\d+)\b", _texto(fila))
        if not numeros:
            continue
        salida.append((html.unescape(nombre.group(1)).strip(), int(numeros[-1])))
    return tuple(salida)
