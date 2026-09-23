"""De qué concierto es un vídeo: cuándo fue, dónde, y si de verdad son ellos.

Tres preguntas, tres respuestas que pueden ser «no lo sé», y eso es un
resultado legítimo: el post entonces habla del momento y no menciona la fecha
ni el sitio. Antes un hueco que un dato inventado.

La materia prima es el TÍTULO y la DESCRIPCIÓN del vídeo. Los canales de
archivo las escriben bien («Extremoduro - Directo Pub El Barco, Palma de
Mallorca 17/4/1993»), y hasta ahora el proyecto descargaba la descripción en
`fetch_youtube.list_videos` y la tiraba sin guardarla.

La fecha se valida con `news_research._date_mentioned`, que es la guarda que ya
usa el blog: solo vale si aparece LITERALMENTE en el texto.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

# Lo que NO son ellos aunque el título diga «Extremoduro». La web está llena de
# bandas tributo —Pedrá, Milongas Extremas, Deltó— y publicar una como si fuera
# Extremoduro es el mismo fallo de identidad que confundir a dos personas: por
# eso el descarte es duro y no una penalización de score.
logger = logging.getLogger(__name__)

_TRIBUTO = re.compile(
    r"\b(tributo|homenaje|tribute|cover|covers|versi[oó]n de|versiones de|"
    r"karaoke|remake|banda tributo|rinde homenaje|a la manera de)\b", re.I
)

# Cosas que salen buscando «concierto» y no lo son. Sin esto entraron al
# catálogo una rueda de prensa de la gira de Mayéutica, la venta de entradas de
# Mérida y un americano reaccionando a un directo de 2002.
_NO_ES_CONCIERTO = re.compile(
    r"\b(rueda de prensa|presentaci[oó]n de la gira|venta de entradas|"
    r"reacciona|reacci[oó]n|reaction|reacting|an[aá]lisis|comentando|"
    r"entrevista|documental|trailer|tr[aá]iler|making of|así se hizo|"
    r"unboxing|review|rese[nñ]a|noticias|programa completo)\b", re.I
)


# Salas que el proyecto ya documenta (data/reference/deprofundis_facts.md, línea
# de «Salas:»), más los recintos que aparecen en las giras de
# data/reference/wikipedia_giras_facts.md. No se inventa ninguna: si un sitio no
# está aquí ni es una ciudad conocida, no se afirma.
SALAS = (
    "Canciller", "Sukursal", "La Riviera", "La Cubierta de Leganés", "La Cubierta",
    "Las Ventas", "Palacio de los Deportes", "Palacio de Deportes",
    "Pabellón de Deportes del Real Madrid", "Teatro Romano de Mérida",
    "Palau de la Música", "WiZink", "Vistalegre", "Sala Vértigo", "Sala Jácara",
    "Plaza Mayor", "Festimad", "Viña Rock", "Azkena", "Rock in Rio",
    "Monumental", "Pub El Barco", "Sala Arena", "Sala But", "Razzmatazz",
)

# Ciudades. Es geografía, no un dato del proyecto: aquí no hay nada que
# inventar. Sirven para completar «sala + ciudad» o para quedarse solo con la
# ciudad cuando el título no da la sala.
CIUDADES = (
    "Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza", "Bilbao", "Málaga",
    "Murcia", "Palma de Mallorca", "Palma", "Las Palmas", "Alicante", "Córdoba",
    "Valladolid", "Vigo", "Gijón", "Granada", "Vitoria", "La Coruña", "A Coruña",
    "Pamplona", "Santander", "Salamanca", "Badajoz", "Cáceres", "Plasencia",
    "Mérida", "Logroño", "Albacete", "Burgos", "Santiago de Compostela",
    "Cádiz", "Huelva", "Jaén", "Almería", "León", "Lugo", "Ourense", "Oviedo",
    "Pontevedra", "Segovia", "Soria", "Tarragona", "Teruel", "Toledo", "Zamora",
    "Leganés", "Alcalá de Henares", "Móstoles", "Getafe", "Barakaldo", "Berriz",
    "Muxika", "El Piornal", "Ciempozuelos", "Azuaga", "Béjar",
)

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy (y con año de dos cifras no: demasiado ambiguo)
_RE_DMY = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
# yyyy/mm/dd, yyyy-mm-dd, yyyy.mm.dd
_RE_YMD = re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b")
# 17 de abril de 1993
_RE_TEXTO = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})\b", re.I
)
_RE_ANIO = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")

# Años en los que estos dos tocaron. Fuera de ahí, un número de cuatro cifras en
# un título no es el año del concierto (es un contador de visitas, una calidad
# de vídeo o cualquier otra cosa).
ANIO_MIN, ANIO_MAX = 1987, 2026


@dataclass
class Evento:
    """Cuándo y dónde fue, con la procedencia de cada dato."""

    fecha: date | None = None
    anio: int | None = None
    lugar: str | None = None
    fuente: str | None = None          # titulo | descripcion

    @property
    def tiene_algo(self) -> bool:
        return bool(self.fecha or self.anio or self.lugar)

    def como_texto(self) -> str:
        """Cómo se nombra en un post. "" si no hay nada que decir."""
        partes = []
        if self.lugar:
            partes.append(self.lugar)
        if self.fecha:
            partes.append(self.fecha.strftime("%d-%m-%Y"))
        elif self.anio:
            partes.append(str(self.anio))
        return ", ".join(partes)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def es_tributo(titulo: str, descripcion: str = "") -> str | None:
    """Si esto no son ellos, devuelve la palabra que lo delata."""
    m = _TRIBUTO.search(f"{titulo}\n{descripcion}")
    return m.group(0) if m else None


def no_es_concierto(titulo: str, descripcion: str = "") -> str | None:
    """Si esto no es un bolo aunque lo parezca, devuelve qué lo delata."""
    m = _NO_ES_CONCIERTO.search(f"{titulo}\n{descripcion}")
    return m.group(0) if m else None


def _fecha_en(texto: str) -> date | None:
    """La primera fecha COMPLETA que aparezca, o None. Nunca una inventada."""
    for m in _RE_DMY.finditer(texto):
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ANIO_MIN <= a <= ANIO_MAX and 1 <= mes <= 12 and 1 <= d <= 31:
            try:
                return date(a, mes, d)
            except ValueError:
                continue
    for m in _RE_YMD.finditer(texto):
        a, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ANIO_MIN <= a <= ANIO_MAX and 1 <= mes <= 12 and 1 <= d <= 31:
            try:
                return date(a, mes, d)
            except ValueError:
                continue
    for m in _RE_TEXTO.finditer(texto):
        mes = _MESES.get(_norm(m.group(2)))
        a, d = int(m.group(3)), int(m.group(1))
        if mes and ANIO_MIN <= a <= ANIO_MAX:
            try:
                return date(a, mes, d)
            except ValueError:
                continue
    return None


def _anio_en(texto: str) -> int | None:
    for m in _RE_ANIO.finditer(texto):
        a = int(m.group(1))
        if ANIO_MIN <= a <= ANIO_MAX:
            return a
    return None


def _lugar_en(texto: str) -> str | None:
    """Sala y/o ciudad, solo de las que el proyecto ya conoce."""
    plano = _norm(texto)
    sala = next((s for s in SALAS if _norm(s) in plano), None)
    ciudad = next((c for c in CIUDADES if _norm(c) in plano), None)
    if sala and ciudad and _norm(ciudad) not in _norm(sala):
        return f"{sala}, {ciudad}"
    return sala or ciudad


def extraer(titulo: str, descripcion: str = "") -> Evento:
    """Cuándo y dónde, mirando primero el título (que es lo más fiable).

    El título lo escribe quien sube el vídeo para que se entienda de un vistazo;
    la descripción suele traer de todo (enlaces, tracklists, avisos de copyright)
    y por eso va después y solo si el título no dio nada.
    """
    ev = Evento()
    # El año que declara el TÍTULO manda sobre la descripción. Medido: un vídeo
    # titulado «sala Vértigo 1993» tenía en su descripción «12-09-2016», que es
    # cuándo lo subieron, y el post habría fechado el concierto veintitrés años
    # tarde. Si los dos no coinciden, la descripción no se usa para la fecha.
    anio_titulo = _anio_en(titulo or "")

    for texto, fuente in ((titulo or "", "titulo"), (descripcion or "", "descripcion")):
        if not texto.strip():
            continue
        if ev.fecha is None:
            candidata = _fecha_en(texto)
            if (candidata and fuente == "descripcion" and anio_titulo
                    and candidata.year != anio_titulo):
                logger.debug("fecha %s descartada: el título dice %s",
                             candidata, anio_titulo)
                candidata = None
            ev.fecha = candidata
            if ev.fecha:
                ev.fuente = ev.fuente or fuente
        if ev.anio is None:
            ev.anio = (ev.fecha.year if ev.fecha else None) or _anio_en(texto)
            if ev.anio and not ev.fuente:
                ev.fuente = fuente
        if ev.lugar is None:
            ev.lugar = _lugar_en(texto)
            if ev.lugar and not ev.fuente:
                ev.fuente = fuente
    # Coherencia: si hay fecha, el año es el suyo y no otro que ande por el texto.
    if ev.fecha:
        ev.anio = ev.fecha.year
    return ev
