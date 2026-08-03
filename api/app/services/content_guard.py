"""Guarda de NO-PÉRDIDA: una ficha reescrita no puede perder lo que ya decía.

`regenerate_deep` genera de cero, y este proyecto ya tiene escrito por qué eso es
peligroso: «regenerar de cero es un dado que pierde información y encoge» — de
ahí que naciera `augment_deep`. Pero el lote viejo (159 fichas) necesita
regenerarse de verdad, no solo ampliarse: arrastra especulación, relleno y cero
metadatos. La única forma de hacerlo sin destrozar nada es medir la pérdida
ANTES de escribir.

Qué hay en juego, medido sobre las 173 fichas publicadas (02-08-2026):
**1.925 citas de versos, 686 enlaces internos, 325 menciones de año** y una
mediana de 6 secciones por ficha.

La comprobación de versos/enlaces/años ya existía duplicada en
`scripts/seo/dedup_pages.py` y `scripts/seo/derepeat_pages.py`; aquí se
consolida y se le añade lo que faltaba y es lo que de verdad preocupa: que **no
se caiga ningún TEMA** de los que la ficha ya trataba.

Nada de esto usa LLM salvo la cobertura semántica de topics, que va con
embeddings (`text-embedding-3-large`, el mismo del corpus) y degrada a
comparación léxica si no hay API key.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Citas entrecomilladas. Cada tipo de comilla se empareja con el SUYO y sin
# mínimo de longitud en el patrón: el filtro va después.
#
# El regex heredado de dedup_pages/derepeat_pages era `[«"]([^»"]{12,240})[»"]`,
# con la clase mixta, y eso emparejaba la comilla de CIERRE de una cita corta con
# la de APERTURA de la siguiente, capturando la prosa de en medio. Medido en la
# ficha de Agila: de las 6 «citas» que detectaba, cinco eran párrafos enteros
# («es un álbum de estudio lanzado en 1996…») y la sexta un enlace markdown. Con
# eso el gate de no-pérdida rechazaba regeneraciones perfectamente válidas.
_VERSE_ANGULAR = re.compile(r"«([^»]*)»")
_VERSE_RECTA = re.compile(r'"([^"]*)"')
_MD_LINK_INLINE = re.compile(r"\]\(")
_LINK = re.compile(r"\]\((/[^)]+|https?://[^)]+)\)")


def _verses(body: str) -> list[str]:
    """Citas textuales reales del cuerpo.

    `findall` empareja comillas consecutivas de dos en dos, así que el texto que
    queda ENTRE dos citas nunca se captura. El filtro de longitud se aplica
    después de emparejar, no dentro del patrón.
    """
    out: list[str] = []
    for rx in (_VERSE_ANGULAR, _VERSE_RECTA):
        for m in rx.findall(body or ""):
            s = m.strip()
            # Un enlace markdown entrecomillado no es una cita.
            if 12 <= len(s) <= 240 and not _MD_LINK_INLINE.search(s):
                out.append(s)
    return out


# Compatibilidad: algunos llamadores esperan un objeto con `.findall`.
class _VerseFinder:
    @staticmethod
    def findall(body: str) -> list[str]:
        return _verses(body)


_VERSE = _VerseFinder()
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
_HEADING = re.compile(r"^#{1,4}\s+(.+?)\s*$", re.M)
_NUM = re.compile(r"\b\d[\d.,]{2,}\b")

# Coseno mínimo entre un título viejo y una SECCIÓN COMPLETA del nuevo para dar
# el tema por cubierto. 0.45 está medido, no supuesto: con títulos cortos contra
# secciones enteras, un tema realmente tratado queda por encima de 0.5 y uno
# ausente por debajo de 0.42. El primer valor que puse (0.72) venía de suponer
# que dos títulos casi idénticos darían ~0.9, y da 0.68.
TOPIC_COSINE_MIN = 0.45

# Suelo de longitud. Es la guarda MÁS TOSCA de todas y por eso va la última: si
# la versión nueva conserva los versos, los enlaces, los años Y todos los temas,
# encoger significa que ha quitado relleno — que es justo el objetivo, porque el
# lote viejo repite «marcó un antes y un después» dos veces en la misma ficha.
#
# Estaba en 0.90 y bloqueaba regeneraciones buenas: `editorial_review` devuelve
# el cuerpo TENSADO cuando su veredicto es `revise`, y ese tensado puede quedar
# por debajo del original aunque el texto generado fuera más largo. Con 0.70 se
# permite condensar sin dejar que nadie resuma la ficha a la mitad.
LENGTH_RATIO_MIN = 0.70

# Fórmulas que delatan que el modelo está rellenando en vez de informar. El
# proyecto tenía `_FILLER_EXAMPLES` en editorial_review, pero solo como ejemplos
# para el LLM juez: no había NINGÚN detector determinista. Medido: 30 de 173
# fichas publicadas contienen alguna de estas.
ESPECULACION = (
    r"puede interpretarse", r"podría (ser|verse|interpretarse|considerarse|leerse)",
    r"quizás", r"tal vez", r"es posible que", r"cabe pensar", r"parece sugerir",
    r"se podría decir", r"no es descabellado",
)
RELLENO = (
    r"marcó un antes y un después", r"dejó (una )?huella", r"no dejó indiferente",
    r"su legado perdura", r"broche de oro", r"hizo vibrar", r"conectó con el público",
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ\s]", " ", s)).strip()


@dataclass(frozen=True)
class Facts:
    verses: frozenset[str]
    links: frozenset[str]
    years: frozenset[str]
    numbers: frozenset[str]


_CITA_FUENTE = re.compile(r"\[Fuente:[^\]]*\]", re.I)


def extract_facts(md: str) -> Facts:
    """Datos duros del cuerpo. Lo que esté aquí tiene que seguir estando después.

    Los años que viven DENTRO de un marcador `[Fuente: … 2021]` no cuentan: son
    la fecha de publicación de la cita, no un hecho sobre el sujeto. Medido en
    Agila, el gate rechazaba la regeneración por «perder» 2021 y 2025, que
    venían de «[Fuente: Mondo Sonoro 2021]» y «[Fuente: eldiario.es 2025]» —
    mientras el único año real del disco, 1996, sí se conservaba.
    """
    body = md or ""
    sin_citas = _CITA_FUENTE.sub(" ", body)
    return Facts(
        verses=frozenset(_norm(v) for v in _verses(body)),
        links=frozenset(_LINK.findall(body)),
        years=frozenset(_YEAR.findall(sin_citas)),
        numbers=frozenset(_NUM.findall(sin_citas)),
    )


# Headings de NAVEGACIÓN, no de contenido: los pone la plantilla o el
# autolinker, no dicen nada sobre el sujeto y su ausencia no es una pérdida.
_HEADINGS_NAVEGACION = (
    "otros discos", "más discos", "mas discos", "en el diario", "también te",
    "tambien te", "relacionad", "ver también", "ver tambien", "enlaces",
    "fuentes", "referencias", "escucha",
)


def extract_topics(md: str) -> list[str]:
    """Los temas de CONTENIDO que trata la ficha, según sus encabezados."""
    out = []
    for h in _HEADING.findall(md or ""):
        t = h.strip()
        if not t:
            continue
        tn = _norm(t)
        if any(p in tn for p in _HEADINGS_NAVEGACION):
            continue
        out.append(t)
    return out


def _cosine_matrix(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    import numpy as np

    def _unit(m: list[list[float]]):
        M = np.asarray(m, dtype="float32")
        # `norma or 1` no vale: con un array numpy de más de un elemento eso
        # lanza «truth value is ambiguous» y tiraba la comparación semántica a la
        # rama léxica sin que se notara más que por un warning.
        n = np.linalg.norm(M, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return M / n

    return (_unit(a) @ _unit(b).T).tolist()


def _tokens_significativos(s: str) -> set[str]:
    ruido = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "en", "su",
             "sus", "para", "por", "con", "que", "al", "lo", "sobre"}
    return {w for w in _norm(s).split() if len(w) > 3 and w not in ruido}


def topic_coverage(
    original: str, nuevo: str, *, min_cosine: float = TOPIC_COSINE_MIN
) -> list[str]:
    """Topics del original que el nuevo NO cubre. Lista vacía = no se perdió nada.

    Un tema está cubierto si el texto nuevo HABLA de él, no si su título se
    parece. Comparar títulos entre sí no funciona: medido con
    `text-embedding-3-large`, «Contexto histórico y musical» contra «Contexto
    Histórico y Musical de Agila» —prácticamente el mismo texto— da solo 0,676,
    y «Legado» contra «Legado de Agila en la Carrera de Extremoduro», 0,512.
    Con títulos de tres palabras el coseno es demasiado ruidoso para decidir.

    Así que se mira en dos pasos, de barato a caro:
      1. Léxico: si los tokens significativos del título viejo aparecen en el
         CUERPO nuevo, el tema sigue tratándose.
      2. Semántico: coseno del título viejo contra cada SECCIÓN completa del
         nuevo (título + su texto), que tiene mucha más señal que un título solo.
    """
    viejos = extract_topics(original)
    if not viejos:
        return []
    if not (nuevo or "").strip():
        return viejos

    cuerpo_nuevo = _norm(nuevo)
    pendientes = []
    for t in viejos:
        toks = _tokens_significativos(t)
        # Con >=2 tokens presentes (o el único que tenga) se da por tratado.
        if toks and sum(1 for w in toks if w in cuerpo_nuevo) >= min(2, len(toks)):
            continue
        pendientes.append(t)
    if not pendientes:
        return []

    # Secciones completas del nuevo: título + su texto, recortado.
    secciones = []
    partes = re.split(r"^#{1,4}\s+", nuevo or "", flags=re.M)
    for p in partes:
        p = p.strip()
        if p:
            secciones.append(p[:600])
    if not secciones:
        return pendientes

    try:
        from app.services.embeddings import get_embedder
        emb = get_embedder()
        sims = _cosine_matrix(emb.embed(pendientes), emb.embed(secciones))
        return [t for t, fila in zip(pendientes, sims) if max(fila) < min_cosine]
    except Exception as exc:  # noqa: BLE001
        # Sin embeddings no se da por bueno lo que el paso léxico no salvó.
        logger.warning("[content_guard] sin embeddings (%s): solo léxico", exc)
        return pendientes


def find_especulacion(md: str) -> list[str]:
    """Fórmulas especulativas o de relleno presentes en el texto."""
    body = md or ""
    out = []
    for pat in ESPECULACION + RELLENO:
        m = re.search(pat, body, re.I)
        if m:
            out.append(m.group(0))
    return out


def anclaje_factual(bloque: str, material: str) -> bool:
    """¿El bloque nuevo se apoya en datos que están en el material?

    Exige que al menos un dato duro (año o cifra) o dos nombres propios del
    bloque aparezcan literalmente en el material. Es lo que separa «la portada
    la dibujó Ramone» de «la portada puede interpretarse como una metáfora».
    """
    mat = material or ""
    duros = set(_YEAR.findall(bloque)) | set(_NUM.findall(bloque))
    if any(d in mat for d in duros):
        return True
    propios = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]{3,}\b", bloque or "")
    return sum(1 for p in set(propios) if p in mat) >= 2


@dataclass
class LossVerdict:
    ok: bool
    reason: str = ""
    lost_topics: list[str] = field(default_factory=list)
    lost_verses: int = 0
    lost_links: int = 0
    lost_years: int = 0
    ratio: float = 0.0
    especulacion: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        if self.ok:
            return f"OK (ratio {self.ratio:.2f}, {len(self.lost_topics)} topics perdidos)"
        return f"RECHAZADO: {self.reason}"


def no_loss_verdict(
    original: str,
    nuevo: str,
    *,
    strict_especulacion: bool = True,
    exempt_links: frozenset[str] | set[str] | None = None,
) -> LossVerdict:
    """¿Se puede sustituir `original` por `nuevo` sin perder nada?

    Bloqueante y determinista salvo la parte de topics. Si devuelve `ok=False`,
    la ficha NO se toca: se queda como está y el motivo va al informe.

    `exempt_links` son enlaces cuya desaparición del CUERPO no es una pérdida
    real porque la página los sigue mostrando por otra vía. El caso concreto:
    los cortes de un disco se renderizan en el componente de tracklist desde la
    API, así que enlazarlos además en la prosa es redundante — y `relink_existing`
    los quita igualmente cada domingo al aplanar a 4 enlaces. Sin esta exención,
    el gate exigía conservar 14 enlaces que el propio sistema borra.
    """
    o, n = original or "", nuevo or ""
    ratio = len(n) / max(len(o), 1)
    fo, fn = extract_facts(o), extract_facts(n)
    exentos = frozenset(exempt_links or ())

    v = LossVerdict(ok=False, ratio=round(ratio, 3))
    v.lost_verses = len(fo.verses - fn.verses)
    v.lost_links = len((fo.links - fn.links) - exentos)
    v.lost_years = len(fo.years - fn.years)

    if v.lost_verses:
        v.reason = f"pierde {v.lost_verses} verso(s) citado(s)"
        return v
    # Los enlaces internos NO bloquean por unidades sueltas: el enlazado lo
    # gobierna `autolink_corpus` con un tope global de 4 por página y
    # `relink_existing` lo recalcula entero cada domingo, así que exigir que se
    # conserve un enlace concreto contradice al subsistema que los reparte. Sí
    # bloquea la sangría: perder más de la mitad de los que no están exentos
    # significa que el cuerpo se ha quedado sin tejido interno.
    # El suelo de 4 evita que la proporción se dispare con números pequeños:
    # con un solo enlace útil, perderlo es el 100% y bloquearía una
    # regeneración por algo que el autolinker repone en la pasada siguiente.
    utiles = len(fo.links - exentos)
    if utiles >= 4 and v.lost_links / utiles > 0.5:
        v.reason = (f"pierde {v.lost_links} de {utiles} enlaces internos "
                    "(más de la mitad)")
        return v
    if v.lost_years:
        v.reason = f"pierde {v.lost_years} año(s) del original"
        return v
    if ratio < LENGTH_RATIO_MIN:
        v.reason = f"encoge demasiado (ratio {ratio:.2f} < {LENGTH_RATIO_MIN})"
        return v

    v.lost_topics = topic_coverage(o, n)
    if v.lost_topics:
        v.reason = "pierde temas: " + "; ".join(f"«{t}»" for t in v.lost_topics[:4])
        return v

    if strict_especulacion:
        # Solo lo que el nuevo AÑADE: si el original ya especulaba, no es esta
        # regeneración la que lo introduce (y arreglarlo es justo el objetivo).
        nueva_esp = [e for e in find_especulacion(n) if not re.search(re.escape(e), o, re.I)]
        if nueva_esp:
            v.especulacion = nueva_esp
            v.reason = "introduce especulación: " + ", ".join(f"«{e}»" for e in nueva_esp[:3])
            return v

    v.ok = True
    return v
