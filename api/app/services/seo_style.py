"""Criterio editorial del title y la description. Fuente ÚNICA.

Antes de esto había **catorce caminos** que escribían un `meta_title`, con cinco
prompts distintos y tres longitudes de description en circulación (155, 158 y 160).
Nadie podía cambiar el criterio en un sitio: había que acordarse de catorce.

## El criterio (David, 22-09-2026)

**El title representa el contenido de la página.** Se optimiza para el término
principal, y si además se puede hilar otro término, bien; si no se puede, NO SE
FUERZA. Nunca se cambia el sentido del title para colocar una keyword.

**La description no es un elemento de ranking: es lo que capta el clic.** Se escribe
para que alguien la lea en la SERP y entre, no para resumir la página.

## Lo que lo provocó

El motor ordenaba, en cinco sitios, colocar la keyword objetivo «al INICIO del
meta_title». Con `target_keyword = 'Barricada grupo'` eso produce
«Barricada grupo: historia y legado…», que no es español. El criterio correcto no es
**pegar** el término sino **cubrirlo**: «Barricada: miembros, historia y legado del
grupo de rock español» lo cubre entero y se lee natural.

## Por qué los topes son estos y no 60

Medido el 22-09-2026 contra el title que escribió David: **64 caracteres**. El tope de
60 se lo habría comido —`Barricada: miembros, historia y legado del grupo de rock`—
y su description (119) está por debajo del mínimo de 125 que pedía el prompt, o sea
que el motor nunca la habría escrito. Las constantes no describían el criterio: lo
contradecían. El límite real de Google es de píxeles (~580 px), no de caracteres; 60
es una aproximación cómoda para pedírselo al modelo, no una frontera que justifique
mutilar un texto bueno. Por eso hay dos números: uno que se pide y otro que rechaza.

**Y ya no se trunca en ningún sitio.** Cortar a `[:60]` parte palabras a mitad («…amor
y libe») y es lo que obligó a existir a `optimize_meta`. Si no cabe limpio, se
rechaza y se reintenta; nunca se publica un texto cortado.

## Cómo están escritas las guardas

En **negativo** y **midiendo el delta**. Dicen qué es inaceptable, no puntúan calidad:
un gate que juzga lo bueno acaba rechazando lo correcto y desactivándose. Ya pasó —la
primera versión de `verify_no_invention` tumbó una description correcta por el verbo
«cuenta»—, así que la anti-invención solo mira cifras y nombres propios.

Hay una parte del criterio que **no es verificable** y no se finge que lo sea: la
description publicada de Barricada («Barricada, grupo clave del rock español, influyó
en bandas como Extremoduro…») tiene verbos, cabe, menciona el diferencial y no es
telegráfica. Ninguna regla razonable la caza, y sin embargo es un RESUMEN, no una
promesa. Eso vive en `PROMPT_META_RULES` y en `EJEMPLOS_ORO` como contraejemplo, y en
el aviso blando `sin_gancho`. Lo determinista solo caza lo que está claramente roto.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Longitudes — la única fuente. Ver el docstring para por qué son dos números.
# --------------------------------------------------------------------------- #
TITLE_TARGET = 60       # lo que se le pide al modelo
TITLE_HARD_MAX = 65     # lo que se rechaza (nunca se corta)
TITLE_MIN = 20
DESC_TARGET = (115, 150)
DESC_HARD_MIN = 110
DESC_HARD_MAX = 155

_STOP = {
    "de", "la", "el", "los", "las", "y", "en", "del", "que", "a", "un", "una",
    "por", "con", "para", "su", "sus", "es", "al", "lo", "se", "como", "o", "e",
}

# Palabras con las que se BUSCA, no cosas que una página pueda cubrir. Sin esta
# lista, «letras de extremoduro desarraigo» salía como hueco de contenido en una
# página que tiene la letra entera: el cuerpo dice «letra», en singular.
_MODIFICADORES = {
    "letra", "letras", "lyrics", "wikipedia", "wiki", "youtube", "video",
    "videos", "cancion", "canciones", "tema", "temas", "musica", "grupo",
    "banda", "descargar", "escuchar", "completa", "completo", "online",
}

# Prefijo con el que se compara un token contra el texto. En español la flexión
# vive al final («miembro»/«miembros»), así que comparar por los primeros
# caracteres evita falsos huecos sin abrir la mano de más.
_PREFIJO = 5


# --------------------------------------------------------------------------- #
# Primitivas de texto
# --------------------------------------------------------------------------- #
def flatten(texto: str | None) -> str:
    """Texto sin acentos, sin markdown y con un solo espacio: el terreno de cotejo."""
    s = unicodedata.normalize("NFD", (texto or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip() + " "


def content_tokens(query: str) -> list[str]:
    """Tokens que representan CONTENIDO (fuera stopwords y modificadores de búsqueda)."""
    return [
        t
        for t in re.findall(r"[a-z0-9]+", flatten(query))
        if t not in _STOP and t not in _MODIFICADORES and len(t) > 1
    ]


def _token_en(texto_plano: str, token: str) -> bool:
    if f" {token} " in texto_plano or f" {token}" in texto_plano:
        return True
    if len(token) > _PREFIJO:
        return bool(re.search(r" " + re.escape(token[:_PREFIJO]) + r"[a-z0-9]*", texto_plano))
    return False


def expandir_alias(texto_plano: str, alias: dict[str, str] | None) -> str:
    """Añade al texto las OTRAS formas de nombrar a quien ya nombra.

    Una ficha que dice «Robe» responde de sobra a quien busca «Roberto Iniesta», y
    la que dice «Milindris» a quien busca «Iñaki Setién». Sin esto, el clasificador
    las daba por no cubiertas y mandaba a escribir contenido que ya estaba: medido
    el 22-09-2026, 2 de las 15 oportunidades de cuerpo eran eso —una con 316
    impresiones, sobre una página que tiene la letra entera— y otras 4 lo eran en
    parte.

    `alias` mapea forma normalizada → todas sus formas, y sale de la BD
    (`nombre_alias_index`), no de una lista escrita a mano: así un fichaje nuevo se
    reconoce solo.
    """
    if not alias:
        return texto_plano
    extra = [formas for clave, formas in alias.items() if f" {clave} " in texto_plano]
    return texto_plano + " " + " ".join(extra) + " " if extra else texto_plano


def cubre(texto_plano: str, query: str) -> bool:
    """¿Este texto responde a la consulta? Todos sus tokens de contenido presentes."""
    toks = content_tokens(query)
    return bool(toks) and all(_token_en(texto_plano, t) for t in toks)


def clean_to_len(text: str, max_len: int) -> str:
    """Recorta a `max_len` sin partir palabra. Para CONSTRUIR, nunca para validar."""
    text = (text or "").strip().strip('"').strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-–—")


def fit_or_none(text: str, max_len: int) -> str | None:
    """O cabe entero, o no hay texto. La alternativa a truncar, que mutilaba."""
    text = (text or "").strip().strip('"').strip()
    return text if text and len(text) <= max_len else None


def tokens_permitidos(*textos: str | None) -> set[str]:
    permitidos: set[str] = set()
    for t in textos:
        for tok in re.findall(r"[a-z0-9]+", flatten(t)):
            permitidos.add(tok[:_PREFIJO] if len(tok) > _PREFIJO else tok)
    return permitidos


def verify_no_invention(propuesta: str, permitidos: set[str]) -> list[str]:
    """Datos de la propuesta que no salen de ninguna fuente autorizada.

    Vigila lo que de verdad se ha inventado alguna vez aquí: **cifras** (el año
    falso de Rock Transgresivo estuvo en 24 fichas) y **nombres propios** (Fito
    Páez por Fito Cabrales). El vocabulario común no, y eso no es dejadez: la
    primera versión tumbó una description correcta por la palabra «cuenta», y una
    guarda que rechaza lo bueno acaba apagada.
    """
    fuera = []
    frases = re.split(r"(?<=[.!?:;])\s+|\n", propuesta or "")
    for frase in frases:
        palabras = re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ'’-]+", frase)
        for i, palabra in enumerate(palabras):
            limpia = palabra.strip("'’-")
            if not limpia:
                continue
            es_cifra = any(c.isdigit() for c in limpia)
            # La primera palabra de la frase va en mayúscula por ortografía, no por
            # ser un nombre propio: mirarla daría un falso positivo en cada frase.
            es_propio = i > 0 and limpia[:1].isupper() and not limpia.isupper()
            if not (es_cifra or es_propio):
                continue
            tok = re.sub(r"[^a-z0-9]", "", flatten(limpia))
            if not tok:
                continue
            clave = tok[:_PREFIJO] if len(tok) > _PREFIJO else tok
            if clave not in permitidos:
                fuera.append(limpia)
    return fuera


def spanish_case(texto: str, fuentes: str) -> str:
    """Devuelve el texto con capitalización española.

    GPT escribe los títulos en Title Case inglés («Significado y Canciones
    Clave»), que en español chirría y delata la máquina. Se baja a minúscula toda
    palabra capitalizada que no abra frase, no vaya tras dos puntos y no aparezca
    también capitalizada en `fuentes`: así los nombres propios se quedan como
    están, porque de ahí salieron.

    OJO con `fuentes`: tiene que traer el cuerpo Y los nombres del catálogo. Con
    `fuentes=""` esto convierte «El Drogas» en «el drogas».
    """
    palabras = (texto or "").split(" ")
    salida = []
    abre_frase = True
    for w in palabras:
        nucleo = w.strip(".,;:!?«»\"'()")
        if (not abre_frase and nucleo and nucleo[:1].isupper() and not nucleo.isupper()
                and nucleo not in fuentes):
            w = w.replace(nucleo, nucleo[0].lower() + nucleo[1:], 1)
        abre_frase = w.endswith((":", ".", "!", "?"))
        salida.append(w)
    return " ".join(salida)


# --------------------------------------------------------------------------- #
# El title
# --------------------------------------------------------------------------- #
@dataclass
class MetaVerdict:
    """`motivos` bloquea; `avisos` no bloquea y da pie a UN reintento con pista."""

    ok: bool = True
    motivos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    facetas: list[str] = field(default_factory=list)

    def bloquear(self, motivo: str) -> None:
        self.ok = False
        self.motivos.append(motivo)


# Sustantivos que, pegados a un nombre propio y sin preposición, delatan la
# keyword metida en crudo: «Barricada grupo», «Libertad significado», «Inconscientes
# banda». `letra` NO está aquí, y no es un olvido: «<Canción> letra: …» es el patrón
# canónico de 99 fichas y es como se busca. Decisión de David, 22-09-2026.
_GENERICOS_PEGADOS = ("grupo", "banda", "disco", "album", "álbum", "significado",
                      "biografia", "biografía", "historia")

# Facetas que describen el GÉNERO de la página, no un tema suyo. Se aceptan sin
# respaldo léxico porque una ficha de grupo cuenta su historia aunque no escriba la
# palabra «historia» — la de Barricada la cuenta bajo «Origen y evolución». La lista
# es corta a propósito: cada entrada es un agujero en la guarda de facetas.
FACETAS_DE_GENERO: dict[str, set[str]] = {
    "band": {"historia", "miembros", "discografia", "legado", "origen",
             "trayectoria", "formacion", "componentes", "integrantes"},
    "artist": {"historia", "discografia", "miembros", "canciones", "discos",
               "legado", "trayectoria", "formacion", "integrantes"},
    "album": {"canciones", "significado", "letras", "tracklist", "disco"},
    "song": {"letra", "significado", "analisis"},
    "person": {"biografia", "trayectoria", "vida", "carrera", "discografia"},
    "place": {"historia", "lugar"},
    "theme": {"significado", "analisis"},
    "concept": {"significado", "analisis"},
}


def parse_title(title: str) -> tuple[str, list[str]]:
    """Parte el title en (cabeza, facetas). La cabeza es lo que la página ES."""
    t = (title or "").strip()
    m = re.split(r"\s*[:—–|]\s*", t, maxsplit=1)
    cabeza = m[0].strip()
    cola = m[1].strip() if len(m) > 1 else ""
    if not cola:
        return cabeza, []
    facetas = [f.strip() for f in re.split(r",|\s+y\s+|\s+·\s+", cola) if f.strip()]
    return cabeza, facetas


def title_pattern(title: str) -> str:
    """`antinatural` si lleva la keyword pegada en crudo; `canonical` si es el
    patrón «<algo> letra: …» del sitio; `ok` en lo demás."""
    t = (title or "").strip()
    for gen in _GENERICOS_PEGADOS:
        if re.search(rf"[A-ZÁÉÍÓÚÑ][\wáéíóúñ'´]*\s+{gen}\b", t):
            return "antinatural"
    if re.search(r"\bletras?\b", flatten(t)):
        return "canonical"
    return "ok"


def _faceta_respaldada(faceta: str, body_plano: str, headings_plano: str,
                       genero: set[str]) -> bool:
    toks = content_tokens(faceta)
    if not toks:
        return True                       # sin contenido propio: no promete nada
    if any(t in genero for t in toks):
        return True
    return any(_token_en(headings_plano, t) or _token_en(body_plano, t) for t in toks)


def cubre_termino(title: str, target_keyword: str | None) -> bool:
    """¿El title CUBRE el término principal? Cubrir no es pegar.

    `Barricada: miembros, historia y legado del grupo de rock español` cubre
    `Barricada grupo` sin contenerlo literal, y eso es exactamente lo que se busca.
    No se exige ni literalidad ni que vaya al principio: esa exigencia es la que
    producía los titles antinaturales.
    """
    if not target_keyword:
        return True
    return cubre(flatten(title), target_keyword)


def title_verdict(nuevo: str, *, body_md: str, subject: str,
                  entity_type: str = "", anterior: str | None = None,
                  target_keyword: str | None = None) -> MetaVerdict:
    """¿Este title representa el contenido de la página?"""
    v = MetaVerdict()
    nuevo = (nuevo or "").strip()
    body_plano = flatten(body_md)
    headings_plano = flatten(" ".join(re.findall(r"^#{2,4}\s+(.*)$", body_md or "", re.M)))
    cabeza, facetas = parse_title(nuevo)
    v.facetas = facetas

    if not nuevo or len(nuevo) < TITLE_MIN:
        v.bloquear(f"title demasiado corto ({len(nuevo)} caracteres)")
        return v
    if len(nuevo) > TITLE_HARD_MAX:
        v.bloquear(f"title de {len(nuevo)} caracteres (máximo {TITLE_HARD_MAX})")
    if len(nuevo) > TITLE_TARGET:
        v.avisos.append(f"title de {len(nuevo)} caracteres, por encima de {TITLE_TARGET}")

    # A — el sujeto de la página tiene que ser el sujeto del title, y estar delante.
    # No vale con que aparezca: «Miembros y origen de Barricada» habla de los
    # miembros, no del grupo, y esa fue justamente la propuesta que se rechazó.
    toks_cabeza = content_tokens(cabeza)
    toks_sujeto = content_tokens(subject)
    if toks_sujeto:
        pos = next((i for i, t in enumerate(toks_cabeza)
                    if any(_token_en(f" {t} ", s) for s in toks_sujeto)), None)
        if pos is None:
            v.bloquear(f"el title no nombra «{subject}» antes de los dos puntos")
        elif pos > 1:
            v.bloquear(
                f"«{subject}» aparece en cuarto lugar dentro de «{cabeza}»: el title "
                "promete otra cosa distinta de lo que la página es"
            )

    # B — cada faceta enumerada tiene que existir de verdad en la página.
    genero = FACETAS_DE_GENERO.get(entity_type, set())
    for f in facetas:
        if not _faceta_respaldada(f, body_plano, headings_plano, genero):
            v.bloquear(f"el title promete «{f}» y la página no lo cubre")

    # C — la keyword metida en crudo.
    if title_pattern(nuevo) == "antinatural":
        v.bloquear(f"«{nuevo}» pega la keyword en crudo; no se lee natural")

    # D — no se fuerza el término principal, pero si no se cubre, se avisa: el
    # title sigue siendo válido (David: «si no se puede, no se fuerza»).
    if not cubre_termino(nuevo, target_keyword):
        v.avisos.append(f"el title no cubre el término principal «{target_keyword}»")

    # E — delta: reescribir tiene que APORTAR una faceta nueva respaldada. Si no,
    # es cambio por cambiar, y cambiar un title que funciona tiene coste.
    if anterior:
        _, facetas_antes = parse_title(anterior)
        nuevas = {flatten(f).strip() for f in facetas} - {flatten(f).strip() for f in facetas_antes}
        if not nuevas:
            v.avisos.append("el title nuevo no añade ninguna faceta que el anterior no tuviera")
    return v


# --------------------------------------------------------------------------- #
# La description
# --------------------------------------------------------------------------- #
# Formas verbales conjugadas frecuentes en este registro. Es una aproximación
# deliberada: por eso la regla pondera y el umbral es alto (0,55). Reconocer verbos
# en español por terminación no funciona — «historia» acaba en -a como «canta».
_VERBOS = {
    "es", "son", "era", "eran", "fue", "fueron", "esta", "estan", "estuvo", "hay",
    "tiene", "tienen", "tuvo", "cuenta", "cuentan", "habla", "hablan", "dice",
    "dicen", "explica", "explican", "significa", "significan", "nacio", "nacieron",
    "murio", "grabo", "grabaron", "publico", "publicaron", "edito", "salio",
    "dejo", "dejaron", "marco", "marcaron", "influyo", "influyeron", "incluye",
    "incluyen", "recoge", "recogen", "reune", "abre", "cierra", "suena", "suenan",
    "toca", "tocaron", "compuso", "escribio", "canta", "cantan", "canto",
    "aparece", "aparecen", "convirtio", "sigue", "siguen", "queda", "quedo",
    "pasa", "paso", "llega", "llego", "viene", "vino", "va", "hizo",
    "hicieron", "puede", "pueden", "debe", "deben", "guarda", "esconde",
    "atraviesa", "recorre", "repasa", "resume", "analiza", "desgrana", "revela",
    "conserva", "mantiene", "define", "refleja", "retrata", "narra", "relata",
    # imperativos y 2ª persona: el gancho
    "conoce", "descubre", "escucha", "entra", "lee", "mira", "acompana", "adentrate", "asomate", "veras", "encontraras", "sabras",
    "conoceras", "descubriras", "escucharas",
}
_GANCHOS = {"conoce", "descubre", "escucha", "entra", "lee", "mira", "repasa",
            "recorre", "acompana", "adentrate", "asomate", "todo", "asi", "por que",
            "que", "cuando", "donde", "quien", "cuantas", "cuantos"}


def _segmentos(desc: str) -> list[list[str]]:
    """Trozos de la description, en tokens normalizados."""
    out = []
    for seg in re.split(r"[.;:]+", desc or ""):
        toks = re.findall(r"[a-z0-9]+", flatten(seg))
        if toks:
            out.append(toks)
    return out


def ratio_telegrafico(desc: str) -> float:
    """Proporción de PALABRAS que viven en trozos sin un solo verbo conjugado.

    Se pondera por palabras y no por trozos a propósito. Medido contra el ejemplo
    que escribió David: por trozos daba 2 de 3 (0,66) y lo habría rechazado; por
    palabras da 0,20 y pasa, mientras el borrador que él tumbó da 1,00.
    """
    segs = _segmentos(desc)
    total = sum(len(s) for s in segs)
    if not total:
        return 1.0
    sin_verbo = sum(len(s) for s in segs if not any(t in _VERBOS for t in s))
    return sin_verbo / total


def desc_verdict(nueva: str, *, title: str = "", body_md: str = "",
                 entity_type: str = "", anterior: str | None = None) -> MetaVerdict:
    """¿Esta description capta el clic, o solo resume la página?"""
    v = MetaVerdict()
    nueva = (nueva or "").strip()
    if not nueva:
        v.bloquear("description vacía")
        return v

    if not (DESC_HARD_MIN <= len(nueva) <= DESC_HARD_MAX):
        v.bloquear(f"description de {len(nueva)} caracteres "
                   f"(el rango es {DESC_HARD_MIN}-{DESC_HARD_MAX})")
    if "!" in nueva or "|" in nueva:
        v.bloquear("description con «!» o «|»: no es el registro del sitio")

    ratio = ratio_telegrafico(nueva)
    if ratio >= 0.55:
        v.bloquear(
            f"description telegráfica: el {ratio:.0%} de las palabras vive en frases "
            "sin verbo. Enumerar sintagmas no capta a nadie"
        )

    # La description no puede meter DATOS que la página no tiene. Ojo con el
    # alcance: la primera versión de esta guarda miraba todo sustantivo que no
    # estuviera en el cuerpo y tumbó el ejemplo escrito por David —«Conoce todos
    # los datos de este grupo mítico…»— por «todos», «datos» y «mítico», que son
    # el registro de la promesa, no promesas de contenido. Lo que se inventa de
    # verdad son cifras y nombres propios, y de eso se encarga `verify_no_invention`
    # con las fuentes que conoce quien llama (cuerpo, metadata anterior, consultas).
    if body_md:
        fuera = verify_no_invention(nueva, tokens_permitidos(body_md, title))
        if fuera:
            v.bloquear("la description mete datos que no están en la página: "
                       + ", ".join(fuera[:4]))

    if title and flatten(title).strip() in flatten(nueva):
        v.bloquear("la description repite el title palabra por palabra")

    # Avisos: lo que hace que una description sea una PROMESA y no un resumen. No
    # bloquea porque no es verificable — la description publicada de Barricada tiene
    # verbos, cabe y menciona el diferencial, y aun así es un resumen.
    primeros = re.findall(r"[a-z0-9]+", flatten(nueva))[:2]
    if not any(p in _GANCHOS for p in primeros) and not nueva.lstrip().startswith(("«", '"')):
        v.avisos.append("la description abre describiendo, no invitando: es un resumen, "
                        "no una promesa de lo que se va a encontrar")
    if entity_type in ("band", "person", "place") and body_md:
        cuerpo = flatten(body_md)
        universo = any(_token_en(cuerpo, t) for t in ("extremoduro", "robe"))
        if universo and not any(_token_en(flatten(nueva), t) for t in ("extremoduro", "robe")):
            v.avisos.append("el cuerpo documenta la relación con Extremoduro/Robe y la "
                            "description no la nombra: es el ángulo que nadie más tiene")

    if anterior and ratio_telegrafico(anterior) < 0.55 <= ratio:
        v.bloquear("la anterior tenía frases con verbo y la nueva no: es una regresión")
    return v


# --------------------------------------------------------------------------- #
# Los bloques de prompt — escritos UNA vez, consumidos por los 14 caminos
# --------------------------------------------------------------------------- #
PROMPT_META_RULES = f"""\
META — el title y la description NO se escriben igual, porque no sirven para lo mismo:

TITLE (≤{TITLE_TARGET} caracteres, nunca más de {TITLE_HARD_MAX}, sin cortar palabras):
- REPRESENTA EL CONTENIDO de la página. Nunca cambies su sentido para colocar un
  término: si la página va de un grupo, el title va del grupo, no de sus miembros.
- La entidad principal abre el title, antes de los dos puntos.
- Cubre el término principal con NATURALIDAD. Cubrir no es pegar: «Barricada grupo»
  está mal escrito; «Barricada: … del grupo de rock español» lo cubre y se lee.
- Si además se puede hilar otro término, bien. SI NO SE PUEDE, NO SE FUERZA.
- Las facetas se enumeran en lenguaje corriente («miembros, historia y legado») y
  cada una tiene que existir de verdad en la página.
- Capitalización española: mayúscula inicial y en nombres propios. Nada de Title Case.

DESCRIPTION ({DESC_TARGET[0]}-{DESC_TARGET[1]} caracteres):
- NO es un elemento de ranking: es lo que capta el clic. Se escribe para que alguien
  la lea en la página de resultados y entre, no para resumir lo que hay dentro.
- Abre invitando y PROMETE lo que va a encontrar, en frases con verbo. Enumerar
  sintagmas sueltos («Grupo de Pamplona. Miembros clave: …») no capta a nadie.
- Apóyate en el ángulo que solo tiene este sitio —la relación con Extremoduro y con
  Robe— SIEMPRE QUE EL CUERPO LO DOCUMENTE. Si no lo documenta, no lo menciones:
  jamás inventes un vínculo.
- No repitas el title palabra por palabra. Sin signos de exclamación."""

PROMPT_META_SHORT = (
    f"meta_title (≤{TITLE_TARGET} c, la entidad al inicio, que REPRESENTE el contenido "
    "de la página y cubra su término principal con naturalidad, sin pegar la keyword "
    f"en crudo) y meta_description ({DESC_TARGET[0]}-{DESC_TARGET[1]} c, escrita para "
    "captar el clic: promete lo que se va a encontrar, en frases con verbo)"
)

EJEMPLOS_ORO = """\
EJEMPLOS (de esta misma web, revisados a mano):

✗ «Barricada grupo: historia y legado en el rock español»
  → pega la keyword en crudo: «Barricada grupo» no es español.
✗ «Miembros y origen de Barricada: El Drogas y Piedrafita»
  → cambia el SENTIDO: la página va del grupo, no de sus miembros.
✓ «Barricada: miembros, historia y legado del grupo de rock español»
  → el sujeto sigue siendo el grupo, y «miembros» entra como una faceta más.

✗ «Barricada, grupo musical de Pamplona. Miembros clave: El Drogas y Alfredo
   Piedrafita. Influencia en bandas como Extremoduro.»
  → telegráfica: tres sintagmas sin un verbo.
✗ «Barricada, grupo clave del rock español, influyó en bandas como Extremoduro y
   dejó un legado perdurable tras su disolución en 2013.»
  → correcta pero es un RESUMEN, no una promesa: no invita a entrar.
✓ «Conoce todos los datos de este grupo mítico de rock español y su relación con
   Extremoduro: miembros, historia y legado.»
  → abre invitando, promete lo que hay dentro y usa el ángulo propio del sitio."""


def output_json_block(*, con_body: bool = True) -> str:
    """El contrato de salida JSON, con las longitudes de aquí y no copiadas a mano."""
    body = '  "body_md": "<artículo en markdown, sin H1, con H2/H3 concretos>",\n' if con_body else ""
    return (
        "Devuelves SIEMPRE un objeto JSON exactamente con esta forma:\n{\n"
        + body
        + f'  "meta_title": "<≤{TITLE_TARGET} c, entidad al inicio, 3ª persona, '
          'representa el contenido>",\n'
        + f'  "meta_description": "<{DESC_TARGET[0]}-{DESC_TARGET[1]} c, escrita para '
          'captar el clic>",\n'
        + '  "entities": [<lista según el bloque ENTIDADES>]\n}'
    )


def meta_limpio(meta: dict, *, subject: str, body: str) -> tuple[str | None, str | None]:
    """Title y description listos para guardar, o `None` si no caben limpios.

    NO trunca. El `[:60]` de antes partía palabras a mitad —«…amor y libe»— y es la
    razón por la que existía `optimize_meta`. Medido el 22-09-2026: al title que
    escribió David a mano, de 64 caracteres, ese corte le quitaba «español».
    Si no cabe, se devuelve None y el campo queda NULL: la plantilla de
    `seo_templates` cubre el hueco y el informe lo canta. Mejor un hueco que un
    texto mutilado en producción.
    """
    fuentes = f"{body} {subject}"
    t = fit_or_none(
        spanish_case(meta.get("meta_title") or "", fuentes),
        TITLE_HARD_MAX,
    )
    d = fit_or_none(
        spanish_case(meta.get("meta_description") or "", fuentes),
        DESC_HARD_MAX,
    )
    if (meta.get("meta_title") or "") and not t:
        logger.warning("[meta] %s: el title no cabe limpio (%d c), se deja vacío",
                       subject, len(meta.get("meta_title") or ""))
    if (meta.get("meta_description") or "") and not d:
        logger.warning("[meta] %s: la description no cabe limpia (%d c), se deja vacía",
                       subject, len(meta.get("meta_description") or ""))
    return t, d
