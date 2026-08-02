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

# Un topic del original se da por cubierto si algún heading del nuevo lo iguala
# semánticamente por encima de este coseno. 0.72 sale de que headings del mismo
# tema pero redactados distinto ("Contexto y lanzamiento" vs "El contexto de
# Agila") quedan sobre 0.8, y temas realmente distintos por debajo de 0.6.
TOPIC_COSINE_MIN = 0.72

# Una regeneración que encoge por debajo de esto es sospechosa aunque conserve
# los hechos: suele significar que ha resumido sin decirlo.
LENGTH_RATIO_MIN = 0.90

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


def extract_facts(md: str) -> Facts:
    """Datos duros del cuerpo. Lo que esté aquí tiene que seguir estando después."""
    body = md or ""
    return Facts(
        verses=frozenset(_norm(v) for v in _verses(body)),
        links=frozenset(_LINK.findall(body)),
        years=frozenset(_YEAR.findall(body)),
        numbers=frozenset(_NUM.findall(body)),
    )


def extract_topics(md: str) -> list[str]:
    """Los temas que trata la ficha, tal como los declara en sus encabezados."""
    return [h.strip() for h in _HEADING.findall(md or "") if h.strip()]


def _cosine_matrix(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    import numpy as np
    A = np.asarray(a, dtype="float32")
    B = np.asarray(b, dtype="float32")
    A /= (np.linalg.norm(A, axis=1, keepdims=True) or 1)
    B /= (np.linalg.norm(B, axis=1, keepdims=True) or 1)
    return (A @ B.T).tolist()


def topic_coverage(
    original: str, nuevo: str, *, min_cosine: float = TOPIC_COSINE_MIN
) -> list[str]:
    """Topics del original que el nuevo NO cubre. Lista vacía = no se perdió nada.

    Se compara por SIGNIFICADO, no por texto: reescribir «Legado» como «Su huella
    en el rock español» no es perder un tema, es redactarlo distinto.
    """
    viejos = extract_topics(original)
    nuevos = extract_topics(nuevo)
    if not viejos:
        return []
    if not nuevos:
        return viejos

    try:
        from app.services.embeddings import get_embedder
        emb = get_embedder()
        va = emb.embed(viejos)
        vb = emb.embed(nuevos)
        sims = _cosine_matrix(va, vb)
        return [t for t, fila in zip(viejos, sims) if max(fila) < min_cosine]
    except Exception as exc:  # noqa: BLE001
        # Sin embeddings NO se da por bueno: se degrada a comparación léxica,
        # que es más estricta. Mejor un falso rechazo que una pérdida silenciosa.
        logger.warning("[content_guard] sin embeddings (%s): comparación léxica", exc)
        nn = [_norm(t) for t in nuevos]
        faltan = []
        for t in viejos:
            tn = _norm(t)
            toks = {w for w in tn.split() if len(w) > 3}
            if not any(tn in x or (toks and toks <= set(x.split())) for x in nn):
                faltan.append(t)
        return faltan


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
