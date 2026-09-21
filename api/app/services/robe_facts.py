"""Lo que el sitio da por cierto sobre Robe, en un solo sitio.

Existe porque el dato más importante de esta web —que Robe murió— estaba escrito
a mano en cuatro constantes distintas y en media docena de prompts con seis
redacciones diferentes, y aun así un artículo publicado podía recorrer toda la
trayectoria de Extremoduro sin mencionarlo. Cuando un hecho vive en siete copias,
ninguna manda: basta con que una se quede vieja para que el sitio se contradiga.

Dos reglas que este módulo hace cumplir por construcción:

1. **La discografía NO se escribe aquí.** Sale de la BD (`discography`), así que
   un disco nuevo aparece solo y nadie tiene que acordarse de añadirlo. Si la
   consulta falla, se devuelve lista vacía: antes un hueco que un dato inventado.

2. **La causa de la muerte no se afirma.** El día del fallecimiento el comunicado
   de su agencia no dio detalles médicos, y nadie los ha confirmado después. Lo
   documentado es el antecedente: en noviembre de 2024 canceló conciertos tras un
   tromboembolismo pulmonar. Por eso no hay ninguna constante que diga «murió de»,
   y sí uno que dice que no se hizo pública.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# --------------------------------------------------------------------------- #
# Hechos
# --------------------------------------------------------------------------- #
BIRTH_DATE = date(1962, 5, 16)
BIRTH_PLACE = "Plasencia"
DEATH_DATE = date(2025, 12, 10)
DEATH_AGE = 63

# La causa NO se hizo pública. `None` a propósito: quien quiera escribirla no
# tiene de dónde sacarla.
DEATH_CAUSE_PUBLIC: str | None = None
DEATH_CAUSE_NOTE = "la causa no se hizo pública"
DEATH_ANTECEDENT = (
    "en noviembre de 2024 canceló conciertos de urgencia tras ser diagnosticado "
    "de un tromboembolismo pulmonar"
)

EXTREMODURO_DISSOLUTION_DATE = date(2019, 12, 18)
EXTREMODURO_DEBUT = ("Tú en tu casa, nosotros en la hoguera", 1990)
EXTREMODURO_LAST_ALBUM = ("Para todos los públicos", 2013)

# Un medio al que enlazar cuando se cuente el fallecimiento.
DEATH_SOURCE = {
    "name": "elDiario.es",
    "date": "2025-12-10",
    "url": ("https://www.eldiario.es/cultura/"
            "muere-robe-iniesta-lider-extremoduro-63-anos_1_12832622.html"),
}

# Reconocimientos póstumos, con fecha. Sin fecha no entran.
POSTHUMOUS = (
    "Medalla de Oro al Mérito en las Bellas Artes (concedida en 2024, entregada "
    "el 27 de mayo de 2026)",
    "Hijo Predilecto de Plasencia (aprobado por unanimidad el 8 de abril de 2026)",
    "festival «Primeras Flores Amarillas» en Plasencia, el 16 de mayo de 2026",
)

# La persona y el artista son dos entidades distintas en la BD, y cada una tenía
# la mitad de los datos: la persona sabía cuándo murió pero no qué publicó, y el
# artista al revés. Este mapa es lo que permite cruzarlas.
PERSON_ARTIST_LINKS = {"robe-iniesta": "robe"}
ARTIST_PERSON_LINKS = {v: k for k, v in PERSON_ARTIST_LINKS.items()}

# De quién hablamos cuando aplica la regla de completitud.
PERIMETER_SLUGS = frozenset({"robe-iniesta", "robe", "extremoduro"})


@dataclass(frozen=True)
class Lanzamiento:
    title: str
    year: int | None
    kind: str
    artist_slug: str


def discography(db) -> list[Lanzamiento]:
    """Todo lo publicado por Extremoduro y por Robe, desde la BD.

    Nunca escrita a mano: si mañana sale un disco, entra solo con el catálogo.
    """
    try:
        from sqlalchemy import select

        from app.db.models import Album, Artist

        filas = db.execute(
            select(Album, Artist.slug)
            .join(Artist, Artist.id == Album.artist_id)
            .where(Artist.slug.in_(("extremoduro", "robe")))
            .order_by(Album.year, Album.title)
        ).all()
    except Exception:  # noqa: BLE001 — sin catálogo se calla, no se inventa
        return []
    return [
        Lanzamiento(title=a.title, year=a.year, kind=a.kind or "studio", artist_slug=slug)
        for a, slug in filas
    ]


def latest_release(db) -> Lanzamiento | None:
    """El último lanzamiento conocido. Es el que delata a un texto desactualizado."""
    todo = discography(db)
    return todo[-1] if todo else None


# --------------------------------------------------------------------------- #
# Redacciones canónicas
# --------------------------------------------------------------------------- #
def _fecha_larga(d: date) -> str:
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


DEATH_SENTENCE = (
    f"Robe falleció el {_fecha_larga(DEATH_DATE)}, a los {DEATH_AGE} años"
)


def anchor_prompt(db=None) -> str:
    """El ancla para quien ESCRIBE. Exige, no solo permite.

    La versión anterior solo decía al modelo que hablar de su muerte «es
    correcto, no un fallo». Eso evita que se equivoque de tiempo verbal, pero no
    hace que cuente lo que hay que contar: por eso salió publicado un recorrido
    por toda la trayectoria de Extremoduro que terminaba en 2021, como si nada
    hubiera pasado después.
    """
    ultimo = latest_release(db) if db is not None else None
    cola = (f" El último lanzamiento del catálogo es «{ultimo.title}»"
            f" ({ultimo.year})." if ultimo else "")
    return (
        f"HECHOS QUE NO SE OMITEN: {DEATH_SENTENCE}. Si el texto recorre su "
        f"trayectoria o la de Extremoduro, DEBE decirlo; dejarlo fuera es un "
        f"error grave, no una elección de enfoque. "
        f"{DEATH_CAUSE_NOTE.capitalize()}: no la afirmes ni la insinúes. Lo "
        f"documentado es que {DEATH_ANTECEDENT}. "
        f"Extremoduro anunció su disolución el "
        f"{_fecha_larga(EXTREMODURO_DISSOLUTION_DATE)}. "
        f"Su debut fue «{EXTREMODURO_DEBUT[0]}» ({EXTREMODURO_DEBUT[1]}); "
        f"«Rock Transgresivo» (1994) es la regrabación que lo sustituyó, no el "
        f"debut. Si enumeras discos, usa los del material y llega hasta el "
        f"último.{cola}"
    )


def anchor_for_editor() -> str:
    """El ancla para quien JUZGA. Contexto factual + qué mirar."""
    return (
        f"CONTEXTO FACTUAL (no lo penalices como error): Roberto Iniesta 'Robe', "
        f"líder de Extremoduro, FALLECIÓ el {_fecha_larga(DEATH_DATE)}; un texto "
        f"que hable de él en pasado o mencione su muerte es CORRECTO. Extremoduro "
        f"anunció su disolución el {_fecha_larga(EXTREMODURO_DISSOLUTION_DATE)} y "
        f"Robe siguió en solitario. En cambio, SÍ es un defecto que un texto "
        f"recorra su trayectoria y no mencione que murió, o que enumere su "
        f"discografía dejándose los discos posteriores: dilo en `reasons`."
    )


def must_facts_lines(db=None) -> list[str]:
    """Hechos duros, para inyectar como material junto a los de la entidad."""
    lineas = [
        f"{DEATH_SENTENCE} (nacido el {_fecha_larga(BIRTH_DATE)} en {BIRTH_PLACE}).",
        f"Sobre su muerte, {DEATH_CAUSE_NOTE}; lo documentado es que "
        f"{DEATH_ANTECEDENT}.",
        f"Extremoduro anunció su disolución el "
        f"{_fecha_larga(EXTREMODURO_DISSOLUTION_DATE)}; su último disco de "
        f"estudio fue «{EXTREMODURO_LAST_ALBUM[0]}» ({EXTREMODURO_LAST_ALBUM[1]}).",
        f"El debut de Extremoduro fue «{EXTREMODURO_DEBUT[0]}» "
        f"({EXTREMODURO_DEBUT[1]}); «Rock Transgresivo» (1994) es la regrabación "
        f"que lo sustituyó por los derechos.",
    ]
    discos = discography(db) if db is not None else []
    if discos:
        por_artista: dict[str, list[str]] = {}
        for d in discos:
            por_artista.setdefault(d.artist_slug, []).append(f"{d.title} ({d.year})")
        for slug, titulos in por_artista.items():
            nombre = "Extremoduro" if slug == "extremoduro" else "Robe en solitario"
            lineas.append(f"Discografía completa de {nombre}: {', '.join(titulos)}.")
    return lineas
