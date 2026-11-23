"""Una noticia del blog se escribe con su artículo, y lo que no dice no se afirma.

El 12-10-2026 salió publicado «Flores Amarillas 2027: el homenaje a Robe en
Plasencia» con un cartel entero inventado: Fito Cabrales «confirmado», Kutxi
Romero, un grupo tributo llamado «Los Robe». El artículo del que salía la noticia
no nombraba a ni un solo músico. Tres cosas se juntaron:

- el borrador se escribió el 14-09, antes de que existiera `google_news_url`, con
  el titular y el banner de cookies de Google como único «material»;
- el motor PEDÍA el cartel («quién actúa», «actuaciones», y el juez de rigor
  rechazaba un anuncio sin lineup), así que con el material vacío lo rellenó con
  lo que el corpus sí trae: Kutxi y Fito hablando de Robe;
- ningún gate del blog comparaba el cuerpo con el artículo. Los que corrían
  miran si el texto es genérico, si cuadra con la BD o con Google, y los versos.

Este módulo es esa comparación. Es DETERMINISTA en lo que puede serlo (nombres
propios) y solo pregunta a un modelo lo que no se puede ver por texto (una frase
de «contará con actuaciones de…» sin nombres), y lo pregunta CONTRA EL ARTÍCULO,
nunca contra la web: es el criterio medido en Instagram con el caso Guardiola
(`caption_guard._lo_dice_el_articulo`).

Reglas:

1. Un nombre propio del cuerpo tiene que estar en el artículo o ser de casa
   (Robe, Extremoduro, el catálogo, las fichas, los lugares).
2. En una frase que ANUNCIA participación («actuará», «confirmado», «contará
   con», «cartel»…), ser de casa no basta: el nombre tiene que estar en el
   artículo. Kutxi Romero tiene ficha aquí y eso no le pone en el cartel de nadie.
3. Una frase de participación sin nombres va al juez, que tiene que encontrar la
   cita literal en el artículo.

Falla CERRADO: sin artículo no hay veredicto bueno posible.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Normalización
# --------------------------------------------------------------------------- #
def _norm(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def _aparece(nombre: str, texto_norm: str) -> bool:
    """¿Está el nombre en el texto (ya normalizado)? Con fronteras de palabra."""
    n = _norm(nombre)
    if not n:
        return False
    return re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", texto_norm) is not None


# --------------------------------------------------------------------------- #
# Extracción de nombres propios
# --------------------------------------------------------------------------- #
# Palabras que abren frase con mayúscula sin ser un nombre. Solo se descartan
# cuando abren la frase: a media frase, una mayúscula ya es señal de nombre.
_ABREN_FRASE = {
    "a", "al", "ante", "asi", "aun", "ademas", "algunos", "algunas", "antes", "aqui",
    "cada", "como", "con", "cuando", "de", "del", "desde", "despues", "donde", "durante",
    "el", "ella", "ellos", "en", "entre", "es", "esa", "ese", "eso", "esta", "este",
    "esto", "estos", "estas", "fue", "habra", "hace", "hasta", "hay", "la", "las", "le",
    "lo", "los", "mas", "mientras", "muchos", "nada", "ni", "no", "nunca", "o", "otro",
    "otra", "otros", "para", "pero", "por", "porque", "pues", "que", "quien", "se", "segun",
    "ser", "si", "sin", "sobre", "su", "sus", "tambien", "tampoco", "tan", "tanto", "tras",
    "tu", "un", "una", "uno", "unos", "unas", "y", "ya", "todo", "toda", "todos", "todas",
    "hoy", "ayer", "manana", "luego", "entonces", "aunque", "incluso", "solo", "sera",
    "seran", "contara", "tendra", "estara", "mismo", "misma", "dos", "tres",
    "cuatro", "cinco", "primera", "primer", "segunda", "segundo", "nuestra", "nuestro",
    "lejos", "cerca", "ahora", "alli", "aquel", "aquella",
}
# Conectores que pueden ir DENTRO de un nombre: «Junta de Extremadura»,
# «Casa de la Salud». La «y» NO: separa a dos personas.
_CONECTORES = {"de", "del", "la", "las", "los", "el"}
# Lo que se nombra con mayúscula sin ser una afirmación sobre nadie.
_GENERICOS = {
    "espana", "extremadura", "europa", "internet", "instagram", "youtube", "spotify",
    "facebook", "google", "tiktok", "entre interiores", "rock", "dios",
}
_DE_CASA_SIEMPRE = {"robe", "roberto iniesta", "extremoduro", "uoho", "iniesta"}

_PALABRA_MAYUS = re.compile(r"^[A-ZÁÉÍÓÚÑÜ][\wÁÉÍÓÚÑÜáéíóúñü'’\-]*$")
_TOKEN = re.compile(r"[\wÁÉÍÓÚÑÜáéíóúñü'’\-]+|[^\w\s]")
# Terminaciones de verbo en pasado o futuro que no comparten los nombres de pila
# («Participaron», «Asistieron», «Entregó», «Actuará», «Estaban»). Fuera a propósito:
# -an/-en (Juan, Carmen), -ía (María, García) y -é (José).
_VERBO_INICIAL = re.compile(r"(?:aron|ieron|ó|ará|erá|irá|arán|erán|irán|aba|aban|ían)$")


def _texto_plano(body_md: str) -> str:
    """El cuerpo sin markdown: sin encabezados, URLs ni citas entrecomilladas.

    Los encabezados van fuera porque `seo_style` ya persigue el Title Case y un
    «## Actuaciones Destacadas» daría falsos nombres. Lo entrecomillado son
    títulos o versos: de eso se encarga `lyric_guard`.
    """
    lineas = [ln for ln in (body_md or "").splitlines() if not ln.lstrip().startswith("#")]
    t = "\n".join(lineas)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"«[^»]*»|\"[^\"\n]*\"|“[^”]*”", " ", t)
    t = re.sub(r"[*_`>]", " ", t)
    return t


def frases(texto: str) -> list[str]:
    partes = re.split(r"(?<=[.!?…])\s+|\n+", texto or "")
    return [p.strip() for p in partes if p.strip()]


def nombres_en(frase: str, conocido=None) -> list[str]:
    """Nombres propios de una frase: rachas de palabras con mayúscula.

    `conocido(nombre) -> bool` dice si un nombre consta en algún sitio (el artículo, la
    casa, lo propio). Sirve para el verbo que abre la frase pegado a un nombre:
    «Participaron León y representantes…» daba el nombre «Participaron León» y la frase
    se retiraba de una noticia cuyo artículo sí nombra a León (cuadro, 20-11-2026). Si
    el nombre entero no consta y sin su primera palabra sí, la primera palabra era el
    verbo. Solo con terminación de verbo conjugado (`_VERBO_INICIAL`): «Kutxi Romero»
    no se queda en «Romero» porque el artículo nombre a otro Romero. Lo que quede se
    comprueba igual que cualquier nombre.
    """
    tokens = _TOKEN.findall(frase)
    nombres: list[str] = []
    racha: list[str] = []
    inicio_racha = 0

    def cerrar() -> None:
        while racha and _norm(racha[-1]) in _CONECTORES:
            racha.pop()
        if not racha:
            return
        palabras = list(racha)
        # Una sola palabra abriendo la frase no se distingue de un verbo
        # («Participarán 20 grupos…»). Si es un nombre, sale en otra frase.
        if inicio_racha == 0 and len(palabras) == 1:
            return
        if inicio_racha == 0 and _norm(palabras[0]) in _ABREN_FRASE:
            palabras = palabras[1:]
            while palabras and _norm(palabras[0]) in _CONECTORES:
                palabras = palabras[1:]
        elif (inicio_racha == 0 and conocido is not None and len(palabras) > 1
              and _VERBO_INICIAL.search(palabras[0])
              and not conocido(" ".join(palabras)) and conocido(" ".join(palabras[1:]))):
            palabras = palabras[1:]
        if palabras:
            nombres.append(" ".join(palabras))

    for i, tok in enumerate(tokens):
        if _PALABRA_MAYUS.match(tok) and not tok.isdigit():
            if not racha:
                inicio_racha = i
            racha.append(tok)
        elif racha and _norm(tok) in _CONECTORES and i + 1 < len(tokens) and (
            _PALABRA_MAYUS.match(tokens[i + 1]) or _norm(tokens[i + 1]) in _CONECTORES
        ):
            racha.append(tok)
        else:
            cerrar()
            racha = []
    cerrar()
    return nombres


# --------------------------------------------------------------------------- #
# Participación anunciada
# --------------------------------------------------------------------------- #
_PARTICIPACION = re.compile(
    r"\b(actuar(?:a|an|á|án)|actuaci(?:on|ón|ones)\b|confirmad[oa]s?|"
    r"participaci(?:on|ón)|participar(?:a|an|á|án)|contar(?:a|á) con|"
    r"cartel|line-?up|subir(?:a|an|á|án) al escenario|tocar(?:a|an|á|án)|"
    r"invitad[oa]s|estar(?:a|an|á|án) (?:presentes?|en el escenario)|"
    r"interpretar(?:a|an|á|án)|compartieron escenario|programad[oa]s?|"
    r"incluir(?:a|á) (?:guiños|actuaciones|conciertos))\b",
    re.I,
)
# «Aún no se han anunciado los nombres» es lo que se le PIDE al redactor cuando la
# noticia no da cartel: negar un anuncio no afirma nada que haya que respaldar.
# Los nombres que lleve la frase se siguen comprobando igual.
_NIEGA_ANUNCIO = re.compile(
    r"\b(?:no|aún no|aun no|todavía no|todavia no|sin)\b[^.]{0,40}?"
    r"\b(?:se\s+)?(?:ha[n]?\s+)?(?:anunciad|confirmad|desvelad|publicad|conocid|detallad)",
    re.I,
)


# --------------------------------------------------------------------------- #
# Veredicto
# --------------------------------------------------------------------------- #
@dataclass
class Hallazgo:
    tipo: str          # "nombre" | "participacion" | "sin_respaldo"
    nombre: str
    frase: str

    def texto(self) -> str:
        if self.tipo == "nombre":
            return f"«{self.nombre}» no consta en el artículo"
        if self.tipo == "participacion":
            return f"el artículo no dice que «{self.nombre}» participe"
        return f"el artículo no respalda «{self.frase[:120]}»"


@dataclass
class Veredicto:
    bloqueos: list[Hallazgo] = field(default_factory=list)
    sin_articulo: bool = False

    @property
    def ok(self) -> bool:
        return not self.bloqueos and not self.sin_articulo

    def motivo(self, n: int = 4) -> str:
        if self.sin_articulo:
            return "No hay artículo con el que comprobar la noticia (sin material no hay post)."
        vistos: list[str] = []
        for h in self.bloqueos:
            t = h.texto()
            if t not in vistos:
                vistos.append(t)
        extra = f" (+{len(vistos) - n})" if len(vistos) > n else ""
        return "Afirma lo que su artículo no dice: " + "; ".join(vistos[:n]) + extra

    def frases_bloqueadas(self) -> set[str]:
        return {h.frase for h in self.bloqueos}


def _de_casa(nombre_norm: str, casa: set[str]) -> bool:
    if nombre_norm in _DE_CASA_SIEMPRE or nombre_norm in _GENERICOS:
        return True
    return nombre_norm in casa


def _en_fuente(nombre: str, fuente_norm: str) -> bool:
    """El nombre, o el nombre sin su palabra genérica de cabeza, está en la fuente.

    «el Festival Flores Amarillas» cuenta si la fuente dice «Flores Amarillas».
    Pero «Los Robe» NO se reduce a «Robe»: quitar la cabeza solo vale si quedan
    dos palabras o más, que es lo que distingue un nombre de un apodo inventado.
    """
    if _aparece(nombre, fuente_norm):
        return True
    palabras = nombre.split()
    cabezas = {"festival", "grupo", "banda", "sala", "plaza", "calle", "el", "la", "los", "las",
               "teatro", "recinto", "ciudad", "concurso"}
    while len(palabras) > 2 and _norm(palabras[0]) in cabezas:
        palabras = palabras[1:]
        if _aparece(" ".join(palabras), fuente_norm):
            return True
    return False


def revisar(
    body_md: str,
    fuente: str,
    *,
    casa: set[str] | frozenset[str] = frozenset(),
    propio: str = "",
    juez: bool = True,
) -> Veredicto:
    """Compara el cuerpo de una noticia con el texto de su artículo (o artículos).

    `casa`: nombres normalizados que no necesitan estar en el artículo
    (`nombres_de_casa(db)`). `propio`: material NUESTRO (el dossier de las
    entidades, sacado de la BD): un nombre que está ahí se puede escribir, pero no
    pone a nadie en un cartel. `juez`: pregunta al modelo por las frases de
    participación sin nombres; sin él, esas frases no se juzgan.
    """
    if not (fuente or "").strip():
        return Veredicto(sin_articulo=True)

    fuente_norm = _norm(fuente)
    propio_norm = _norm(propio)
    casa_norm = {_norm(c) for c in casa}
    bloqueos: list[Hallazgo] = []

    def consta(nombre: str) -> bool:
        return bool(_en_fuente(nombre, fuente_norm) or _de_casa(_norm(nombre), casa_norm)
                    or (propio_norm and _en_fuente(nombre, propio_norm)))

    for frase in frases(_texto_plano(body_md)):
        nombres = nombres_en(frase, consta)
        participa = bool(_PARTICIPACION.search(frase))
        for nombre in nombres:
            n = _norm(nombre)
            if _en_fuente(nombre, fuente_norm):
                continue
            if participa and n not in _DE_CASA_SIEMPRE:
                bloqueos.append(Hallazgo("participacion", nombre, frase))
            elif not _de_casa(n, casa_norm) and not (propio_norm and _en_fuente(nombre, propio_norm)):
                bloqueos.append(Hallazgo("nombre", nombre, frase))
        sin_nombres_ajenos = all(
            _norm(nm) in _DE_CASA_SIEMPRE or _en_fuente(nm, fuente_norm) for nm in nombres
        )
        if participa and sin_nombres_ajenos and juez and not _NIEGA_ANUNCIO.search(frase):
            from app.services.instagram.caption_guard import _lo_dice_el_articulo

            veredicto = _lo_dice_el_articulo(frase, fuente)
            if veredicto.get("verdict") != "supported":
                bloqueos.append(Hallazgo("sin_respaldo", "", frase))

    return Veredicto(bloqueos=bloqueos)


def quitar_frases(body_md: str, veredicto: Veredicto) -> str:
    """Retira del cuerpo las frases bloqueadas, y la sección que se quede vacía.

    En una noticia, una frase que pone a alguien en un cartel que no existe es
    falsa ENTERA: no hay parte buena que salvar. Lo que no se toca es el resto.
    """
    malas = veredicto.frases_bloqueadas()
    if not malas:
        return body_md
    planas = {_norm(f) for f in malas}
    # Quien cae no puede quedarse en la frase siguiente («Kutxi ha mencionado
    # que…»): se retira también lo que lo vuelve a nombrar, por cualquiera de sus
    # palabras. Nunca por una palabra de casa: «Los Robe» no arrastra a «Robe».
    palabras_caidas = {
        w for h in veredicto.bloqueos if h.nombre
        for w in _norm(h.nombre).split()
        if len(w) > 3 and w not in _DE_CASA_SIEMPRE and w not in _CONECTORES
    }

    def es_mala(trozo: str) -> bool:
        plano = _norm(_texto_plano(trozo)).strip()
        if plano in planas:
            return True
        return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", plano) for w in palabras_caidas)

    salida: list[str] = []
    for parrafo in re.split(r"\n\s*\n", body_md or ""):
        if parrafo.lstrip().startswith("#"):
            salida.append(parrafo)
            continue
        trozos = re.split(r"(?<=[.!?…])\s+", parrafo)
        quedan = [t for t in trozos if not es_mala(t)]
        texto = " ".join(quedan).strip()
        if texto:
            salida.append(texto)
    # Un encabezado sin nada debajo hasta el siguiente no aporta.
    limpio: list[str] = []
    for i, bloque in enumerate(salida):
        siguiente = salida[i + 1] if i + 1 < len(salida) else None
        if bloque.lstrip().startswith("#") and (siguiente is None or siguiente.lstrip().startswith("#")):
            continue
        limpio.append(bloque)
    return "\n\n".join(limpio).strip()


# --------------------------------------------------------------------------- #
# Material: el artículo y lo de casa
# --------------------------------------------------------------------------- #
def articulo_de(url: str | None) -> str:
    """Texto del artículo de una noticia, resolviendo Google News. Vacío si no hay.

    No cae al resumen del RSS ni al titular: con eso no se puede comprobar nada,
    y caer en silencio es lo que dejó publicar el post de Flores Amarillas.
    """
    if not url:
        return ""
    from app.services.article_extract import fetch_article

    try:
        resultado = fetch_article(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[grounding] no se pudo bajar %s: %s", url[:80], exc)
        return ""
    if not resultado.ok or not resultado.text:
        logger.info("[grounding] sin artículo (%s) para %s", resultado.status, url[:80])
        return ""
    return resultado.text


def nombres_de_casa(db) -> set[str]:
    """Todo lo que tiene ficha o es del catálogo, normalizado."""
    from app.db.models import Album, Artist, Band, Concept, Person, Place, Song, Theme

    nombres: set[str] = set()
    consultas = (
        (Artist.name,), (Album.title,), (Song.title,), (Band.name,), (Place.name,),
        (Theme.name,), (Concept.name,), (Person.full_name, Person.stage_name),
    )
    for columnas in consultas:
        try:
            for fila in db.query(*columnas).all():
                for valor in fila:
                    if valor:
                        nombres.add(_norm(re.sub(r"\s*\(.*?\)\s*", " ", valor)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[grounding] no se pudo leer %s: %s", columnas, exc)
            db.rollback()
    return {n for n in nombres if n}
