"""Última puerta antes de Instagram: nada sale sin pasar por aquí.

Existe por tres fallos que llegaron publicados en octubre y noviembre de 2026:

- **Texto del proceso.** El #487 y el #374 salieron con «Tramo 45-57s de «…»
  Momento: … Motivos: … Corte: pausa» en el caption: eran las notas internas del
  selector de clips, que vivían en el mismo campo (`summary`) que el texto
  publicable, y cuatro caminos de respaldo las publicaban tal cual.
- **Metatexto del modelo.** «El material disponible no confirma quién tocó…»
  (#472) o «no aporta su letra ni datos que permitan analizarla sin inventar»
  (#468): el redactor escribía la FALTA de material en vez de callarla.
- **El proceso parafraseado.** «seis segmentos seguidos sin voz» (#510), «en un
  tramo sin voz del tema» (#504): el modelo recibía los `Motivos` y los contaba.
  Esto lo arregla de raíz que el redactor no los reciba (ver `notas_internas`);
  aquí queda la red por si alguien vuelve a pasárselos.

Es determinista, sin red ni LLM, y persigue SINTAGMAS, no palabras: «error»
cazaría «antiterrorista» y «Te juzgarán sólo por tus errores», y «no consta» es
una frase legítima del estudio (#408, «de las que no consta que sonaran»). Los
captions reales que lo motivaron, buenos y malos, están congelados en
`app/tests/test_gate_final.py`: si una regla nueva tumba uno bueno, la regla
está mal.

Lo que bloquea no se publica: el item queda en `needs_human` con el motivo, y
`_publicable()` lo deja fuera de la cola hasta que una persona lo mire.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Etiquetas literales de las notas del selector de clips y de la ingesta.
_ETIQUETAS_PROCESO = (
    r"\btramo\s+\d+(?:[.,]\d+)?\s*-\s*\d+",       # «Tramo 45-57s»
    r"(?:^|\n|\s)motivos?\s*:",
    r"(?:^|\n|\s)corte\s*:\s*(?:pausa|puntuacion|aproximada)",
    r"(?:^|\n|\s)momento\s*:\s*\w",
    r"transcripcion del tramo",
    r"(?:^|\n|\s)aviso\s*:",
    r"(?:^|\n|\s)verificado\s*:\s*en\s+\d",
    r"\(fuente\s*:\s*\w+\)",
    r"(?:^|\n)\s*canal\s*:",
    r"verso\s*\(de nuestra letra\)",
    r"medio profesional",
)

# Vocabulario del pipeline: nadie que escriba para un fan dice esto.
_VOCABULARIO_PIPELINE = (
    r"\bsegmentos?\s+(?:seguidos|sin voz|con voz)\b",
    r"\btramo\s+(?:sin voz|con una pausa|largo|de la cancion)\b",
    r"\bwhisper\b",
    r"\bdossier\b",
    r"\bprompt\b",
    r"\bno_speech",
    r"\[\s*hipotesis\s*\]",
    r"\{\s*\"",                                   # restos de JSON
    r"/api/",
    r"\bcorpus\b",
    r"\bpipeline\b",
)

# Fórmulas de «falta de material»: si no hay dato, no se menciona.
FORMULAS_FALTA_DE_MATERIAL = (
    r"\bel material (?:disponible|que hay|con el que)",
    r"\bmaterial disponible\b",
    # «el material» + cualquier cosa, salvo los usos legítimos de la palabra.
    # Al re-preparar la cola el 09-11-2026 el modelo parafraseó tres veces
    # seguidas: «El material no concreta…» (#281), «En el material de casa…» y
    # «El material sitúa…» (#424). Perseguir verbos no acaba nunca. Medido sobre
    # los 411 captions de prod: solo casa con los cinco que hablaban de nuestras
    # fuentes; «Este material inédito» (#226) y «Material defectuoso» (un disco)
    # quedan fuera por la lista blanca.
    r"\b(?:el|del|en el|nuestro|ese|este) material\b(?!\s+(?:defectuoso|inedito|original|"
    r"de archivo|grabado|audiovisual|nuevo|en directo))",
    r"\bmaterial de casa\b",
    r"\bno le cuelgo\b",
    r"\b(?:datos|historias|creditos|cosas) que no constan\b",
    r"\bno (?:me |nos )?consta(?:n)? (?:en el material|en nuestras fuentes)\b",
    r"\bsin inventar\b",
    r"\bno permite precisar\b",
    r"\bno aporta (?:datos|su letra|informacion)\b",
    r"\bno se dispone de\b",
    r"\bno (?:hay|tenemos) datos (?:verificables|suficientes)\b",
    r"\bno (?:podemos|se puede) confirmar\b",
)

_PATRONES = (
    # «TODO» va aparte y SIN re.I: con re.I casaba con «todo el universo de Robe»
    # y tumbaba 70 captions buenos en la primera calibración (09-11-2026).
    [("marca de trabajo pendiente", re.compile(r"\b(?:TODO|FIXME|XXX)\b"))]
    + [("texto interno del proceso", re.compile(p, re.I)) for p in _ETIQUETAS_PROCESO]
    + [("vocabulario del proceso", re.compile(p, re.I)) for p in _VOCABULARIO_PIPELINE]
    + [("metatexto de falta de material", re.compile(p, re.I))
       for p in FORMULAS_FALTA_DE_MATERIAL]
)


def _plano(texto: str) -> str:
    """Sin tildes, para que «Transcripción» y «Transcripcion» casen igual."""
    s = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def _fragmento(texto: str, m: re.Match) -> str:
    ini = max(0, m.start() - 30)
    return texto[ini:m.end() + 30].replace("\n", " ").strip()


@dataclass
class VeredictoGate:
    bloqueos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.bloqueos

    @property
    def motivo(self) -> str:
        return "; ".join(self.bloqueos)[:1900]


def problemas_de_texto(texto: str, *, donde: str = "caption") -> list[str]:
    """Lo que en este texto delata el proceso. Lista vacía = limpio."""
    plano = _plano(texto)
    hallados: list[str] = []
    vistos: set[str] = set()
    for etiqueta, patron in _PATRONES:
        m = patron.search(plano)
        if m and patron.pattern not in vistos:
            vistos.add(patron.pattern)
            hallados.append(f"{donde}: {etiqueta} («{_fragmento(plano, m)}»)")
    return hallados


# --- Coherencia de un clip de directo ------------------------------------------------

_ATRIBUCION_A_GRUPO = re.compile(
    r"\bextremoduro\s+(?:la|lo|las|los)?\s*(?:toco|tocaron|interpreto|interpretaron|"
    r"canto|cantaron)\b",
    re.I,
)
_ATRIBUCION_A_ROBE = re.compile(
    r"\brobe\s+(?:la|lo|las|los)?\s*(?:toco|interpreto|canto)\b", re.I
)


def interprete_del_video(video_title: str, channel_title: str = "") -> str | None:
    """Quién toca en el concierto, según lo que declara el propio vídeo.

    Un directo de Robe en solitario NO es de Extremoduro aunque toque canciones
    de Extremoduro: el #504 decía «Extremoduro la tocó en Vigo el 9 de noviembre
    de 2024», cinco años después de la despedida, porque el texto heredaba el
    artista de la canción original. Si el título nombra a los dos, o a ninguno,
    no se sabe, y entonces el gate no afirma nada (devuelve None).
    """
    t = _plano(video_title).lower()
    robe = bool(re.search(r"\brobe\b", t))
    extremo = "extremoduro" in t
    if robe and not extremo:
        return "Robe"
    if extremo and not robe:
        return "Extremoduro"
    # «ROBE "Concierto Completo" … #robe #extremoduro»: los hashtags no cuentan.
    sin_tags = re.sub(r"#\w+", " ", t)
    robe = bool(re.search(r"\brobe\b", sin_tags))
    extremo = "extremoduro" in sin_tags
    if robe and not extremo:
        return "Robe"
    if extremo and not robe:
        return "Extremoduro"
    return None


def problemas_de_clip(
    caption: str,
    *,
    interprete: str | None,
    titulos_permitidos: set[str],
    titulos_catalogo: set[str],
) -> list[str]:
    """El texto de un clip habla del clip, y de nada más.

    - Quien tocó es quien declara el vídeo.
    - Todo título del catálogo citado entre comillas es la canción del clip o su
      disco. En el #504 la pregunta de cierre citaba «Agila» y el título «La
      Carrera»: dos títulos de otra cosa en el mismo post.
    """
    plano = _plano(caption)
    hallados: list[str] = []
    if interprete == "Robe" and _ATRIBUCION_A_GRUPO.search(plano):
        hallados.append("clip: atribuye a Extremoduro un concierto de Robe")
    if interprete == "Extremoduro" and _ATRIBUCION_A_ROBE.search(plano):
        hallados.append("clip: atribuye a Robe en solitario un concierto de Extremoduro")

    permitidos = {_norm_titulo(t) for t in titulos_permitidos if t}
    catalogo = {_norm_titulo(t) for t in titulos_catalogo if t}
    for citado in re.findall(r"«([^»]{2,80})»", caption or ""):
        n = _norm_titulo(citado)
        if n in catalogo and n not in permitidos:
            hallados.append(f"clip: cita «{citado}», que no es la canción del clip ni su disco")
    return hallados


def _norm_titulo(t: str) -> str:
    s = _plano(t).lower()
    s = re.sub(r"\(.*?\)", " ", s)          # «La carrera (En Directo)» → «la carrera»
    return re.sub(r"[^a-z0-9ñ]+", " ", s).strip()


def revisar(
    *,
    caption: str,
    slides: list[str] | None = None,
    rotulo: str = "",
    clip: dict | None = None,
) -> VeredictoGate:
    """Veredicto sobre TODO lo que va a ver la gente.

    El primer comentario sale de la pregunta del caption (`community`), así que
    revisar el caption lo cubre. Las slides van quemadas en la imagen y el rótulo
    en el vídeo: después de publicar no se pueden corregir, por eso se miran
    aunque ya las revisara el redactor.

    `clip`: {interprete, titulos_permitidos, titulos_catalogo} cuando es un clip
    de directo.
    """
    v = VeredictoGate()
    v.bloqueos += problemas_de_texto(caption, donde="caption")
    for i, s in enumerate(slides or []):
        v.bloqueos += problemas_de_texto(s, donde=f"slide {i + 1}")
    if rotulo:
        v.bloqueos += problemas_de_texto(rotulo, donde="rótulo del vídeo")
    if clip:
        v.bloqueos += problemas_de_clip(
            caption + ("\n" + rotulo if rotulo else ""),
            interprete=clip.get("interprete"),
            titulos_permitidos=set(clip.get("titulos_permitidos") or ()),
            titulos_catalogo=set(clip.get("titulos_catalogo") or ()),
        )
    return v
