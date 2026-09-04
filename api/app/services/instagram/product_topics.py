"""De qué va un post que enseña la web: la CONSULTA concreta, sacada del corpus.

Antes, un post de «funcionalidad de la web» se colgaba encima de un tema ajeno
(una noticia, un verso) y `_prepare_product` machacaba su título con el de la
ficha. Resultado: todos se llamaban «Pregúntale al viento» y ninguno decía nada.

Ahora el tema ES la consulta: «¿Qué es la libertad para Robe?», «se acabó lo
bonito». La funcionalidad es el formato en que se cuenta, no el asunto.

## De dónde salen las consultas (por orden)

1. **Lo que la gente pregunta de verdad.** `consult_questions.question` (las
   preguntas al consultorio) y `feature_queries.query` (buscador semántico y
   listas por mood). Son datos reales de la web, no inventados.
2. **De reserva, la taxonomía del corpus.** `Theme` / `Concept` / `Place`, que
   son entidades reales extraídas de las letras, con una plantilla de pregunta.
   Sirve mientras el registro esté flojo, y no se queda nunca sin material.

En los dos casos la RESPUESTA es real: la pide `product_shots` a la propia API
en el momento de componer la pieza. Aquí solo se decide QUÉ se pregunta.

## Privacidad

`feature_queries` guarda texto escrito por usuarios, y el propio modelo lo marca
como PII (por eso no va a analytics). Publicar una de esas consultas exige las
tres cosas de abajo, y aun así el post nace `proposed`: no sale nada sin que una
persona lo apruebe en el panel.

  - nada marcado `flagged`,
  - nada que parezca un dato personal (`_huele_a_personal`),
  - longitud de consulta, no de confesión.

Nunca se publica quién preguntó ni se insinúa que haya alguien detrás: la
consulta se enseña como lo que es, un ejemplo de uso de la herramienta.
"""
from __future__ import annotations

import hashlib
import logging
import random
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Qué fuente del corpus alimenta a cada funcionalidad.
FUENTES: dict[str, str] = {
    "pregúntale-al-viento": "consultorio",
    "como-lo-diria-robe": "buscador",
    "listas-por-mood": "mood",
}

MIN_LONGITUD = 8
MAX_LONGITUD = 90

# Señales de que la consulta lleva algo personal dentro. Ante la duda, fuera:
# perder una consulta buena no cuesta nada, publicar la intimidad de alguien sí.
_PERSONAL = re.compile(
    r"\b(mi|mis|me|conmigo|nuestro|nuestra)\s+\w*"
    r"(madre|padre|hermano|hermana|hijo|hija|novia|novio|mujer|marido|ex|jefe|"
    r"amigo|amiga|abuelo|abuela|perro|gato|casa|curro|trabajo|movil|movida)\b"
    r"|@|\+?\d{6,}|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    re.IGNORECASE,
)


def _sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def _huele_a_personal(texto: str) -> bool:
    return bool(_PERSONAL.search(_sin_tildes(texto)))


def _admisible(texto: str) -> bool:
    t = (texto or "").strip()
    if not (MIN_LONGITUD <= len(t) <= MAX_LONGITUD):
        return False
    if _huele_a_personal(t):
        return False
    # Una sola línea: lo que ocupa más es un desahogo, no una consulta.
    return "\n" not in t


def _presentable(texto: str) -> str:
    """Arregla la TIPOGRAFÍA de una consulta tecleada a vuelapluma.

    La gente escribe «cuantas veces has actuado en plasencia?» y eso, tal cual,
    queda descuidado en un post público. Se pone la mayúscula inicial y la
    apertura de interrogación/exclamación que pide el castellano.

    Solo toca la forma, nunca el contenido: no se corrigen acentos ni palabras
    (eso ya sería reescribir lo que preguntó otra persona), y la pregunta que
    viaja al consultorio es esta misma, así que la respuesta sigue siendo a lo
    que se preguntó.
    """
    t = (texto or "").strip()
    if not t:
        return t
    # La mayúscula va en la primera LETRA, no en el primer carácter: con «¿como
    # te lo pasaste…» el `.upper()` caía sobre el «¿» y no hacía nada.
    i = 0
    while i < len(t) and t[i] in "¿¡«\"'“ ":
        i += 1
    if i < len(t):
        t = t[:i] + t[i].upper() + t[i + 1:]
    if t.endswith("?") and not t.startswith("¿"):
        t = f"¿{t}"
    if t.endswith("!") and not t.startswith("¡"):
        t = f"¡{t}"
    return t


def consulta_id(consulta: str) -> str:
    """Identificador corto y estable de una consulta, para el `content_key`.

    Va en el `content_key`, así que no puede llevar «:» (rompería el parseo) ni
    la consulta en claro (acabaría en la BD duplicada).
    """
    return hashlib.md5(consulta.strip().lower().encode("utf-8")).hexdigest()[:10]


# --------------------------------------------------------------------------- #
# Fuentes
# --------------------------------------------------------------------------- #
def _escrita_con_cuidado(texto: str) -> bool:
    """¿La pregunta está escrita con esmero suficiente para ser un titular?

    En el consultorio la consulta se enseña como pregunta destacada, y salía
    «cuantas veces has actuado en plasencia?»: sin tilde y en minúscula. Los
    acentos no se pueden corregir sin reescribir lo que preguntó otra persona,
    así que se decide antes: solo entran las que ya venían abiertas con «¿».

    Es un filtro tonto a propósito — no adivina, mira un signo. Lo que no pasa
    no se pierde: la reserva del corpus siempre tiene material bien escrito.
    """
    return (texto or "").strip().startswith(("¿", "¡"))


def _del_registro(db: Session, fuente: str, limite: int = 300) -> list[str]:
    """Lo que la gente ha preguntado o buscado de verdad."""
    from app.db.models import ConsultQuestion, FeatureQuery

    if fuente == "consultorio":
        filas = db.execute(
            select(ConsultQuestion.question)
            .where(ConsultQuestion.flagged.is_(False))
            .order_by(ConsultQuestion.created_at.desc())
            .limit(limite)
        ).scalars().all()
    else:
        feature = "mood" if fuente == "mood" else "search"
        filas = db.execute(
            select(FeatureQuery.query)
            .where(FeatureQuery.feature == feature)
            .order_by(FeatureQuery.created_at.desc())
            .limit(limite)
        ).scalars().all()

    vistas: set[str] = set()
    salida: list[str] = []
    for fila in filas:
        crudo = fila or ""
        # En el consultorio la consulta es el titular, así que se exige esmero.
        # En el buscador no: ahí una frase suelta en minúscula es exactamente lo
        # que uno teclea en el campo de búsqueda, y así se enseña.
        if fuente == "consultorio" and not _escrita_con_cuidado(crudo):
            continue
        t = _presentable(crudo)
        clave = _sin_tildes(t)
        if clave in vistas or not _admisible(t):
            continue
        vistas.add(clave)
        salida.append(t)
    return salida


# Plantillas de reserva. El SUJETO siempre es una entidad real del corpus
# (`themes`, `concepts`, `places`); esto solo le pone la forma de pregunta.
#
# El término va ENTRECOMILLADO y tal cual está en la BD, sin tocarle las
# mayúsculas: pasarlo por `.lower()` convertía «Plasencia» en «plasencia», y
# meterlo suelto en la frase obligaba a acertar el artículo («el amor», «la
# autodestrucción», «las flores amarillas»). Entre comillas cuela cualquier
# etiqueta del corpus sin pelearse con la gramática.
_PLANTILLAS = {
    "consultorio": (
        "¿Qué es «{x}» para Robe?",
        "¿Qué dice Robe sobre «{x}»?",
        "«{x}»: ¿qué queda de eso en sus letras?",
    ),
    "buscador": ("{x}",),
    "mood": ("{x}",),
}


def _del_corpus(db: Session, fuente: str, semilla: int = 0) -> list[str]:
    """Reserva: taxonomías reales de las letras."""
    from app.db.models import Concept, Place, Theme

    nombres: list[str] = []
    for modelo in (Theme, Concept, Place):
        nombres += [
            n for (n,) in db.execute(select(modelo.name).order_by(modelo.id)).all()
            if n
        ]
    if not nombres:
        return []

    rnd = random.Random(semilla)
    rnd.shuffle(nombres)
    plantillas = _PLANTILLAS.get(fuente, ("{x}",))
    salida = []
    for i, nombre in enumerate(nombres):
        consulta = plantillas[i % len(plantillas)].format(x=nombre.strip())
        if _admisible(consulta):
            salida.append(consulta)
    return salida


def consultas_para(
    db: Session, slug: str, *, excluir: set[str] | None = None, semilla: int = 0,
) -> list[str]:
    """Consultas candidatas para una funcionalidad, las reales primero.

    `excluir` son los `consulta_id` que ya pasaron por la cola: una consulta no
    se repite aunque siga estando en el registro.
    """
    fuente = FUENTES.get(slug)
    if fuente is None:
        return []          # el karaoke no se recompone: vive de su captura
    excluir = excluir or set()

    salida: list[str] = []
    for candidata in _del_registro(db, fuente) + _del_corpus(db, fuente, semilla):
        if consulta_id(candidata) in excluir:
            continue
        if candidata in salida:
            continue
        salida.append(candidata)
    return salida


def consulta_de(db: Session, slug: str, cid: str) -> str:
    """La consulta concreta de un `content_key` ya encolado.

    Se busca por su hash entre las candidatas de ahora. Si ya no está (el
    registro rota), se coge la primera disponible: la pieza sigue siendo real,
    solo cambia el ejemplo.
    """
    for candidata in consultas_para(db, slug):
        if consulta_id(candidata) == cid:
            return candidata
    disponibles = consultas_para(db, slug)
    if not disponibles:
        raise RuntimeError(
            f"no hay ninguna consulta real con la que enseñar «{slug}»"
        )
    logger.info("[product] la consulta %s ya no está; se usa otra", cid)
    return disponibles[0]
