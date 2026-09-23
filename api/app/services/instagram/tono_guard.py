"""¿Este texto dice algo, o vale para cualquier otro post?

El gate de identidad (`caption_guard`) comprueba que lo que se afirma sea
VERDAD. Esto comprueba otra cosa: que merezca leerse. Son preguntas distintas y
un post puede pasar la primera y fallar la segunda — de hecho es lo que pasaba,
y por eso el feed estaba lleno de «Un Canto a la Libertad» y «La Evolución
Musical de Extremoduro».

Determinista y sin factura, igual que `find_especulacion`. Las fórmulas de la
lista no son inventadas: están copiadas de titulares REALES que el pipeline
publicó (se ven en el log de producción del 21-09-2026).

Criterio de calibración, el mismo que `seo_style`: si esta guarda tumba un texto
bueno, la guarda está mal. Por eso no persigue palabras sueltas («viaje»,
«legado», «alma» son legítimas), sino sintagmas completos de molde.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Sintagmas de molde. Cada uno se midió en un post publicado.
MOLDES = (
    r"un canto a la libertad",
    r"la evoluci[oó]n musical de",
    r"un viaje sonoro",
    r"un viaje (musical )?(con|por|a trav[eé]s de)",
    r"la evoluci[oó]n del rock",
    r"sigue vivo en cada (nota|verso|canci[oó]n)",
    r"un antes y un despu[eé]s",
    r"(la )?banda sonora de (nuestras|tu|mi) vida",
    r"m[aá]s all[aá] de la m[uú]sica",
    r"(una )?leyenda (viva|del rock)",
    r"nos dej[oó] un vac[ií]o",
    r"un ic[oó]no (del|de la)",
    r"toc[oó] el alma de",
    # Muletillas de análisis. `voice._RULES_HARD` ya las prohíbe: si salen, es
    # que el modelo no ha hecho caso, no que sean discutibles.
    r"encapsula",
    r"(una )?oda a\b",
    # «esencia» con determinante. Medido el 23-09-2026 sobre los 349 captions
    # de la cuenta: la palabra sale en 40 frases y en las 40 es relleno («la
    # esencia del rock», «la esencia de la banda», «revivir la esencia»). No
    # hay un solo uso que diga algo, así que no se persiguen las variantes una
    # a una: se veta el sintagma.
    #
    # Las dos formas anteriores pedían «la esencia» seguida de una lista corta
    # de palabras, y por ahí se coló en producción «Robe en SU esencia PURA,
    # caminando por encima de todo lo que lo quiere atrapar» — un caption de
    # clip de directo, que es justo donde no se puede interpretar la letra al
    # aire. También se escapaban «esa esencia única» y «la esencia cruda»: el
    # adjetivo por medio rompía el patrón.
    r"\b(la|las|el|su|sus|esa|esta|una|mi|tu)\s+esencia\b",
    r"met[aá]fora (especialmente )?poderosa",
    r"no es casualidad que",
    r"refleja (a la perfecci[oó]n|el esp[ií]ritu)",
    r"al m[aá]s puro estilo",
    r"(himno|grito) generacional",
    r"pura poes[ií]a",
    # `content_guard.RELLENO` ya veta «dejó huella», pero solo esa forma: el
    # gerundio se coló en un caption re-preparado en producción el 23-09-2026
    # («dejando una huella imborrable en el rock español»).
    r"(dejando|deja|dejaron) (una )?huella",
    r"huella (imborrable|indeleble|eterna)",
    # Interpretar la letra al aire, que es lo que sale cuando no hay material
    # del momento. Copiado de un caption de clip de concierto: «refleja la lucha
    # interna de Robe», «el estribillo es un grito de desesperación».
    r"refleja (la|el|su) (lucha|dolor|alma|esencia|sentir|esp[ií]ritu|"
    r"distanciamiento|soledad)",
    r"es un (grito|canto|himno|homenaje) (de|a|al)\b",
    r"no te lo pierdas",
    r"d[eé]janos tu comentario",
    # La familia entera, no solo la forma que salió aquel día: el linter
    # perseguía «huella imborrable» y el modelo escribió «una marca indeleble
    # en la historia del rock español» (caption de `#370`, 23-09-2026). Igual
    # que «su esencia pura» esquivó «la esencia»: si se persigue el sustantivo,
    # basta cambiar el sustantivo.
    r"(huella|marca|impronta|sello|legado) "
    r"(imborrable|indeleble|eterna?|imperecedera?)",
    r"sigue (resonando|latiendo|sonando) (en|m[aá]s all[aá])",
    r"m[aá]s all[aá] de su (ausencia|muerte|partida)",
)

# Preguntas de cierre que valen para cualquier post. Van aparte de `MOLDES`
# porque no son lo mismo: una frase de molde es humo, y una pregunta genérica
# puede ser perfectamente cierta — lo que le pasa es que no comenta ESTE post,
# y por eso no abre ninguna conversación.
#
# Medido el 23-09-2026: 39 de 309 captions cerraban con «¿Cómo lo veis
# vosotros?» o «¿Qué os parece?». Las que SÍ funcionan hablan del contenido
# («¿Y a ti, qué verso de «Pepe Botika» se te quedó dentro?»), así que la
# frontera no es «pregunta sí/no» sino si la pregunta sabe de qué va el post.
PREGUNTAS_DE_MOLDE = (
    r"qu[eé] (os|te) parece",
    r"c[oó]mo lo v[eé]is",
    r"qu[eé] opin[aá](is|s)",
    r"a[ñn]adir[ií]ais algo",
    r"est[aá]is de acuerdo",
    r"qu[eé] pens[aá](is|s)",
    r"y (vosotros|t[uú]),? qu[eé]\??$",
    r"qu[eé] me cont[aá](is|s)",
)

# Un kicker es una etiqueta, no un contador. «CLAVE 01» encima de una frase
# troceada es exactamente el síntoma que había que quitar.
_KICKER_CONTADOR = re.compile(
    r"^(clave|punto|dato|idea|parte|nota|paso)?\s*\d{1,2}$", re.I
)

_ANIO = re.compile(r"\b(19|20)\d{2}\b")
_CIFRA = re.compile(r"\b\d+([.,]\d+)?\s*(%|años|discos|canciones|temas|mil|millones)?\b")
_ENTRECOMILLADO = re.compile(r"[«\"']([^»\"']{4,})[»\"']")
# Nombre propio que NO abre la frase: es el patrón de un dato concreto
# («…grabado en Plasencia», «…con Iñaki Antón»), no el de un sujeto genérico.
_PROPIO_INTERNO = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]{2,}\b")


# Las mismas fórmulas, en cristiano, para meterlas en el prompt. Que la guarda
# conozca una lista y el prompt no es hacer que el modelo la adivine a base de
# rechazos: se le dicen, y el rechazo queda para quien no hace caso.
EJEMPLOS_PROHIBIDOS = (
    "un canto a la libertad", "la evolución musical de", "un viaje sonoro",
    "sigue vivo en cada nota", "un antes y un después", "la esencia de",
    "encapsula", "una oda a", "metáfora poderosa", "no es casualidad que",
    "refleja a la perfección", "al más puro estilo", "himno generacional",
    "pura poesía", "dejó huella", "no dejó indiferente", "su legado perdura",
    "broche de oro", "hizo vibrar", "conectó con el público",
    "¿qué os parece?", "¿cómo lo veis?",
)


def bloque_prohibidas() -> str:
    """El aviso que va al prompt, sacado de la misma lista que juzga."""
    return (
        "FRASES PROHIBIDAS (se rechaza el texto automáticamente si aparece "
        "alguna, en cualquier forma): "
        + "; ".join(f"«{f}»" for f in EJEMPLOS_PROHIBIDOS)
        + ". No son ejemplos de lo que evitar: son literales vetados."
    )


@dataclass
class VeredictoTono:
    bloqueos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.bloqueos


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def moldes_en(texto: str) -> list[str]:
    """Sintagmas de molde presentes en el texto."""
    plano = _norm(texto)
    return [m.group(0) for pat in MOLDES if (m := re.search(pat, plano))]


def pregunta_de_molde(texto: str) -> str | None:
    """La fórmula genérica que trae esta pregunta, si trae alguna."""
    plano = _norm(texto)
    for pat in PREGUNTAS_DE_MOLDE:
        if (m := re.search(pat, plano)):
            return m.group(0)
    return None


def bloque_preguntas() -> str:
    """Lo que se le dice al modelo sobre la pregunta de cierre.

    Sale de la MISMA lista que la juzga: que la guarda conozca una lista y el
    prompt no es hacer que el modelo la adivine a base de rechazos.
    """
    return (
        "PREGUNTAS PROHIBIDAS (valen para cualquier post, así que no son de "
        "este): «¿qué os parece?», «¿cómo lo veis?», «¿qué opináis?», "
        "«¿añadiríais algo?», «¿estáis de acuerdo?», «¿qué pensáis?». "
        "Tampoco pidas una valoración de lo que acabas de contar."
    )


def tiene_ancla(texto: str) -> bool:
    """¿Hay algo concreto aquí, o es una frase que vale para cualquier post?

    Ancla = un año, una cifra, algo entrecomillado (un verso, un título) o dos
    nombres propios dentro de la frase. Es deliberadamente generoso: basta con
    que UNA slide del carrusel lo cumpla.
    """
    t = texto or ""
    if _ANIO.search(t) or _ENTRECOMILLADO.search(t):
        return True
    if re.search(r"\b\d+\s*(%|años|discos|canciones|temas|millones)\b", t, re.I):
        return True
    return len(set(_PROPIO_INTERNO.findall(t))) >= 2


def revisar(
    *, titular: str = "", comentario: str = "", slides: list[dict] | None = None,
    cierre: str = "", pregunta: str = "",
) -> VeredictoTono:
    """Veredicto sobre el texto que hemos escrito NOSOTROS.

    No mira el titular del medio ni el verso citado: eso es ajeno y se cita, no
    se juzga.
    """
    v = VeredictoTono()
    slides = slides or []

    todo = "\n".join(
        [titular, comentario, cierre, pregunta]
        + [s.get("text", "") for s in slides]
    )
    for molde in moldes_en(todo):
        v.bloqueos.append(f"frase de molde: «{molde}»")

    # La pregunta de cierre es lo único que le pedimos a quien lee, así que
    # tiene que saber de qué va el post. NO se le exige `tiene_ancla`: «¿Dónde
    # estabas la primera vez que escuchaste esto?» no trae ni un año ni un
    # nombre propio y es de las que mejor funcionan. Lo que se le exige es que
    # no sea una de las que valen para todo.
    if pregunta and (formula := pregunta_de_molde(pregunta)):
        v.bloqueos.append(
            f"la pregunta de cierre vale para cualquier post: «{formula}»"
        )

    for s in slides:
        kicker = (s.get("kicker") or "").strip()
        if kicker and _KICKER_CONTADOR.match(kicker):
            v.bloqueos.append(f"el kicker «{kicker}» es un contador, no una etiqueta")

    # Al menos una tarjeta tiene que traer un dato. Si ninguna lo trae, el
    # carrusel es humo bien maquetado.
    if slides and not any(tiene_ancla(s.get("text", "")) for s in slides):
        v.bloqueos.append(
            "ninguna slide trae un dato concreto (año, cifra, título o nombre)"
        )

    # Repetir el comentario en una slide es gastar una tarjeta en nada. Avisa,
    # no bloquea: a veces la frase buena es la misma y conviene que se vea.
    plano_com = _norm(comentario)
    for s in slides:
        frag = _norm(s.get("text", ""))[:60]
        if frag and frag in plano_com:
            v.avisos.append("una slide repite una frase del comentario")
            break

    return v
