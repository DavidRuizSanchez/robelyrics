"""Quién es quién en una noticia, antes de escribir una sola frase sobre ello.

El fallo que cierra este módulo (item 348, publicado el 17-09-2026): una noticia
sobre el Día de Extremadura cuyo titular decía solo «Guardiola» salió con fotos
de Pep Guardiola y afirmando que «figuras del mundo del fútbol como Guardiola
reconocen la influencia de Robe». El artículo, que nadie descargaba, decía en su
segunda frase «La presidenta de la Junta de Extremadura, María Guardiola».

Tres cosas aprendidas de ese caso, y las tres están en el diseño:

1. **El nombre bueno está en el CUERPO, no en el titular.** Buscar «Guardiola» a
   secas en Wikidata no devuelve a ninguna de las dos personas: devuelve un
   apellido, un género de plantas, tres pueblos y un vértice geodésico. Buscar
   «María Guardiola» devuelve «política española» a la primera. Por eso se extrae
   sobre el material y no sobre el titular.

2. **Desambigua el CONTEXTO de la noticia, no un léxico de oficios.** El
   `_DOMINIO_HINTS` de `photo_finder` ordena los candidatos poniendo delante a los
   músicos; aquí eso es un no-op, porque ni el entrenador ni la presidenta lo son,
   y gana el primero que devuelve Wikidata, que es el más famoso del mundo. Lo que
   distingue es el span literal del artículo: «presidenta de la Junta de
   Extremadura». Y hace falta de verdad: el segundo candidato de «María Guardiola»
   es «Maria Baptista dos Santos Guardiola, política portuguesa», así que ni
   siquiera el oficio basta.

3. **Con dos candidatos vivos no hay entidad.** Nunca se elige «el más probable».

REGLA DURA: una entidad que no resuelve a `corpus` o `wikidata` no aporta foto, no
aporta hashtag, no presta su nombre a ninguna búsqueda de imagen y no puede ser
sujeto ni objeto de ninguna afirmación. Si la que falla es el SUJETO, no hay post.
El cumplimiento se comprueba después y por texto (ver `caption_guard`), no se
confía al prompt.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

from app.services.image_guard import _norm, _significant_words

logger = logging.getLogger(__name__)

_WD_API = "https://www.wikidata.org/w/api.php"
# Sin tildes: las cabeceras HTTP son ASCII y httpx revienta con un
# UnicodeEncodeError que aquí se traga el `except` y deja TODO sin resolver
# en silencio. Pasó en la primera prueba.
_UA = "EntreInteriores/1.0 (https://entreinteriores.com; entity resolution)"

# Palabras del contexto que deben aparecer en la ficha del candidato para darlo
# por bueno sin preguntar a un juez. Dos es poco exigente a propósito: el juez
# resuelve los casos justos, y llamarlo siempre sería lento y caro.
MIN_SOLAPE = 2
MAX_CANDIDATOS = 7

# Tipos que sabemos resolver, con su equivalente en el corpus del proyecto.
KIND_A_CORPUS = {
    "person": "Person",
    "band": "MusicGroup",
    "org": "Organization",
    "place": "Place",
    "work": "MusicComposition",
}

CORPUS = "corpus"
WIKIDATA = "wikidata"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"

_SYS_EXTRAER = (
    "Extraes las entidades nombradas de un artículo de prensa. NO interpretas, "
    "NO deduces y NO añades nada que no esté escrito.\n"
    'Devuelves un objeto JSON con UNA clave, "entities", cuyo valor es la lista.\n'
    "Para cada persona, grupo musical, organización, lugar u obra que el artículo "
    "NOMBRE explícitamente, devuelves:\n"
    '  "surface": su nombre TAL CUAL aparece en el texto, copiado literalmente. '
    "Si el artículo da el nombre completo en algún sitio, usa el COMPLETO.\n"
    '  "kind": person | band | org | place | work\n'
    '  "context": un fragmento LITERAL del artículo, copiado carácter a carácter, '
    "que diga QUIÉN o QUÉ es (su cargo, su oficio, su papel). Si el artículo no "
    "lo dice en ninguna parte, devuelve cadena vacía: no lo inventes ni lo "
    "deduzcas de lo que tú sepas.\n"
    '  "role": "subject" si la entidad protagoniza la noticia, "mentioned" si solo '
    "aparece citada."
)


@dataclass(frozen=True)
class Mention:
    """Una entidad NOMBRADA en el artículo. `surface` y `context` son literales."""

    surface: str
    kind: str
    context: str = ""
    role: str = "mentioned"

    @property
    def es_sujeto(self) -> bool:
        return self.role == "subject"


@dataclass(frozen=True)
class ResolvedEntity:
    """Quién es esa mención, y con qué respaldo se afirma."""

    mention: Mention
    status: str
    label: str | None = None
    description: str | None = None
    qid: str | None = None
    canonical_id: str | None = None
    url: str | None = None
    image_url: str | None = None
    aliases: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""

    @property
    def resuelta(self) -> bool:
        """Tiene identidad acreditada fuera del artículo (corpus o Wikidata)."""
        return self.status in (CORPUS, WIKIDATA)

    @property
    def descrita_por_el_articulo(self) -> bool:
        """El artículo dice quién es, aunque no exista en ninguna base de datos.

        La mayoría de la gente que sale en una noticia es así: un concursante de
        un concurso, un vecino, un músico de un pueblo. No están en Wikidata y no
        van a estarlo nunca.
        """
        return bool(self.mention.context)

    @property
    def da_foto(self) -> bool:
        """Solo se le busca cara a quien está identificado FUERA del artículo.

        Que una noticia diga «Moisés, concursante riojano» no da para salir a
        buscar su foto por internet: ahí es donde se coló la de Pep Guardiola.
        """
        return self.resuelta

    @property
    def silenciada(self) -> bool:
        """Ni identificada ni descrita: no se nombra siquiera.

        Calibrado el 23-09-2026 después de probarlo en producción. La primera
        versión exigía identidad a TODO sujeto, y tumbaba cualquier noticia sobre
        gente corriente: la primera con la que se probó se descartó porque
        «Moisés», un concursante de Pasapalabra, tiene en Wikidata al profeta
        bíblico y poco más. Una guarda que rechaza lo bueno acaba apagada.

        El daño del item 348 no fue no saber quién era: fue ponerle la FOTO de
        otro y atribuirle un oficio y una afinidad que nadie había dicho. Eso lo
        cierran `da_foto`, `caption_guard.contradice_la_identidad` y la
        verificación de relaciones contra el artículo. Lo que queda aquí es el
        caso de verdad peligroso: un nombre del que NI SIQUIERA el artículo dice
        quién es — el «Guardiola» del titular pelado— y que por tanto se puede
        confundir con un homónimo famoso.
        """
        return not (self.resuelta or self.descrita_por_el_articulo)

    @property
    def descripcion_efectiva(self) -> str:
        """Lo que sabemos de ella: su descripción canónica o, si no la hay, lo
        que el artículo dice que es."""
        return self.description or self.mention.context or ""

    @property
    def nombre_publicable(self) -> str | None:
        return self.label or (self.mention.surface if self.descrita_por_el_articulo else None)


# --------------------------------------------------------------------------- #
# Extracción
# --------------------------------------------------------------------------- #
def _aplanar(texto: str) -> str:
    """Colapsa espacios para comparar literalidad sin depender del formato."""
    return re.sub(r"\s+", " ", texto or "").strip()


def extract_mentions(material: str, title: str = "") -> list[Mention]:
    """Entidades nombradas en el artículo, comprobadas contra el propio artículo.

    El LLM propone y una comprobación determinista dispone: se descarta toda
    mención cuyo `surface` no aparezca literalmente en el material, y se vacía
    todo `context` que no sea un fragmento literal. Es el mismo patrón que
    `news_research.validated_event_date`, y es lo único que separa un extractor
    de entidades de un inventor de entidades.
    """
    from app.services.news_research import _json

    material = (material or "").strip()
    if not material:
        return []

    data = _json(
        _SYS_EXTRAER,
        f"TITULAR: {title}\n\nARTÍCULO:\n\"\"\"\n{material[:6000]}\n\"\"\"",
        max_tokens=900,
        temperature=0,
    )
    crudas = data.get("entities") or data.get("menciones") or data.get("entidades")
    if not isinstance(crudas, list):
        # Tolerancia: el modelo a veces bautiza la lista a su gusto. Pedir la
        # clave en el prompt no basta —la primera versión de esto devolvió 0
        # menciones sobre un artículo del que sí sacaba todo, solo porque la
        # llamó `entities` en vez de `menciones`— así que se coge la primera
        # lista que haya.
        crudas = next(
            (v for v in (data or {}).values() if isinstance(v, list)), []
        )
    if not crudas:
        return []

    plano = _aplanar(material)
    plano_norm = _norm(plano)
    fuera: list[str] = []
    menciones: list[Mention] = []
    for m in crudas:
        if not isinstance(m, dict):
            continue
        surface = _aplanar(str(m.get("surface") or ""))
        kind = str(m.get("kind") or "").strip().lower()
        if not surface or kind not in KIND_A_CORPUS:
            continue
        # El nombre tiene que estar en el artículo. Si no, se lo ha inventado.
        if _norm(surface) not in plano_norm:
            fuera.append(surface)
            continue
        contexto = _aplanar(str(m.get("context") or ""))
        if contexto and _norm(contexto) not in plano_norm:
            # El contexto no es literal: se tira el contexto, no la mención.
            # Un contexto inventado es justo lo que haría elegir al homónimo.
            fuera.append(f"{surface} (contexto no literal)")
            contexto = ""
        role = "subject" if str(m.get("role") or "") == "subject" else "mentioned"
        menciones.append(Mention(surface, kind, contexto, role))

    if fuera:
        logger.info("[entidades] descartadas por no ser literales: %s", ", ".join(fuera))
    return _consolidar(menciones)


def _consolidar(menciones: list[Mention]) -> list[Mention]:
    """Funde el nombre corto en el completo: «Guardiola» ⊂ «María Guardiola».

    Un artículo nombra a alguien entero una vez y por el apellido el resto, y el
    extractor devuelve las dos formas. Dejarlas separadas haría que la corta no
    resolviese —«Guardiola» a secas no devuelve ninguna persona en Wikidata— y,
    por la regla dura, silenciaría un apellido que el artículo sí identifica.

    Se queda la forma LARGA, que es la que resuelve, con el contexto más
    informativo y el papel más fuerte de las dos.
    """
    orden = sorted(menciones, key=lambda m: len(m.surface), reverse=True)
    salida: list[Mention] = []
    for m in orden:
        palabras = set(_norm(m.surface).split())
        absorbida = False
        for i, ya in enumerate(salida):
            if ya.kind != m.kind:
                continue
            if palabras and palabras <= set(_norm(ya.surface).split()):
                salida[i] = Mention(
                    surface=ya.surface,
                    kind=ya.kind,
                    context=max((ya.context, m.context), key=len),
                    role="subject" if "subject" in (ya.role, m.role) else ya.role,
                )
                absorbida = True
                break
        if not absorbida:
            salida.append(m)
    return salida


# --------------------------------------------------------------------------- #
# Resolución
# --------------------------------------------------------------------------- #
def _candidatos_wikidata(surface: str, *, timeout: float = 15.0) -> list[dict]:
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": _UA}) as c:
            r = c.get(_WD_API, params={
                "action": "wbsearchentities", "search": surface,
                "language": "es", "uselang": "es", "format": "json",
                "limit": MAX_CANDIDATOS, "type": "item",
            })
            r.raise_for_status()
            return r.json().get("search", []) or []
    except Exception as exc:  # noqa: BLE001
        logger.info("[entidades] Wikidata falló para %r: %s", surface, exc)
        return []


def _ficha(cand: dict, *, con_wikipedia: bool = True) -> str:
    """Todo lo que sabemos del candidato, para cotejarlo con el contexto."""
    partes = [cand.get("label") or "", cand.get("description") or ""]
    if con_wikipedia:
        from app.services.web_verify import wikipedia_extract
        extracto = wikipedia_extract(cand.get("label") or "")
        if extracto:
            partes.append(extracto)
    return " ".join(partes)


def _solape(contexto: str, ficha: str) -> int:
    """Cuántas palabras con contenido del contexto aparecen en la ficha.

    Se mide contra el CONTEXTO de la noticia («presidenta de la Junta de
    Extremadura»), no contra una lista fija de oficios: una lista de oficios
    musicales no distingue a un entrenador de una presidenta, porque ninguno de
    los dos es músico.
    """
    if not contexto or not ficha:
        return 0
    ficha_norm = _norm(ficha)
    return sum(1 for w in set(_significant_words(contexto)) if w in ficha_norm)


def _buscar_en_corpus(db, mention: Mention) -> ResolvedEntity | None:
    """¿Es alguien de casa? Entonces ya tenemos su ficha y su foto verificada."""
    from app.services.entity_resolver import _resolve_one
    from app.services.instagram import config as ig_config

    e_type = KIND_A_CORPUS.get(mention.kind)
    if not e_type:
        return None
    try:
        res = _resolve_one(
            db, {"type": e_type, "name": mention.surface}, ig_config.SITE_URL
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("[entidades] corpus falló para %r: %s", mention.surface, exc)
        return None
    if not res or not res.get("from_corpus"):
        return None

    return ResolvedEntity(
        mention=mention,
        status=CORPUS,
        label=mention.surface,
        description=None,
        canonical_id=res.get("canonical_id"),
        url=res.get("url"),
        image_url=_imagen_de_corpus(db, res.get("url")),
        reason="Ficha propia del corpus.",
    )


def _imagen_de_corpus(db, url: str | None) -> str | None:
    """Foto de la ficha, que ya pasó `verify_provenance` en el cron de imágenes.

    Ojo: `Person` NO tiene campo `name` (es `stage_name` / `full_name`); leerlo
    mal dejó en su día el nombre vacío y marcó como falsas TODAS las fotos de
    personas.
    """
    if not url:
        return None
    from app.db.models import Artist, Person

    slug = url.rstrip("/").split("/")[-1]
    if "/personas/" in url:
        row = db.query(Person).filter(Person.slug == slug).first()
    else:
        row = db.query(Artist).filter(Artist.slug == slug).first()
    return getattr(row, "image_url", None) if row else None


def resolve(db, mention: Mention) -> ResolvedEntity:
    """Identifica una mención. Ante la duda, NO identifica."""
    propia = _buscar_en_corpus(db, mention)
    if propia is not None:
        return propia

    cands = _candidatos_wikidata(mention.surface)
    if not cands:
        return ResolvedEntity(
            mention, UNRESOLVED,
            reason=f"Wikidata no devuelve nada para «{mention.surface}».",
        )

    if not mention.context:
        # Sin contexto no hay con qué desambiguar. Un solo candidato podría ser
        # el bueno, pero también podría ser el más famoso del mundo: con
        # «Guardiola» a secas, el primero que devuelve Wikidata es un apellido.
        return ResolvedEntity(
            mention, AMBIGUOUS,
            candidates=[_resumen(c) for c in cands[:3]],
            reason=(
                f"El artículo no dice quién es «{mention.surface}», así que no hay "
                f"con qué distinguirlo de sus homónimos."
            ),
        )

    puntuados = []
    for c in cands[:5]:
        puntuados.append((_solape(mention.context, _ficha(c)), c))
    puntuados.sort(key=lambda p: p[0], reverse=True)

    mejor, segundo = puntuados[0], (puntuados[1] if len(puntuados) > 1 else (0, None))
    resumenes = [_resumen(c) for _, c in puntuados[:3] if c]

    if mejor[0] >= MIN_SOLAPE and mejor[0] > segundo[0]:
        return _resuelta_por_wikidata(mention, mejor[1], resumenes, mejor[0])

    # Empate o poco solape: que decida el juez, y solo si es UNO.
    ganador = _juez(mention, [c for _, c in puntuados[:3] if c])
    if ganador is not None:
        return _resuelta_por_wikidata(mention, ganador, resumenes, mejor[0], juez=True)

    return ResolvedEntity(
        mention, AMBIGUOUS,
        candidates=resumenes,
        reason=(
            f"Varios candidatos siguen vivos para «{mention.surface}» "
            f"({', '.join(r['description'] or '?' for r in resumenes)}). "
            f"Con dos candidatos vivos no hay entidad."
        ),
    )


def _resumen(cand: dict) -> dict:
    return {
        "qid": cand.get("id"),
        "label": cand.get("label"),
        "description": cand.get("description"),
    }


def _resuelta_por_wikidata(
    mention: Mention, cand: dict, resumenes: list[dict], solape: int, *, juez=False
) -> ResolvedEntity:
    return ResolvedEntity(
        mention=mention,
        status=WIKIDATA,
        label=cand.get("label"),
        description=cand.get("description"),
        qid=cand.get("id"),
        canonical_id=f"https://www.wikidata.org/wiki/{cand.get('id')}",
        aliases=[a for a in (cand.get("aliases") or []) if a],
        candidates=resumenes,
        reason=(
            f"El contexto de la noticia encaja con «{cand.get('description')}»"
            + (" (confirmado por el verificador)." if juez else f" ({solape} coincidencias).")
        ),
    )


def _juez(mention: Mention, cands: list[dict]) -> dict | None:
    """Pregunta a la web por cada candidato. Devuelve uno SOLO si es el único."""
    from app.services.web_verify import classify_fact

    apoyados = []
    for c in cands:
        claim = (
            f"{c.get('label')} ({c.get('description')}) es la persona o entidad a la "
            f"que se refiere este pasaje: «{mention.context}»"
        )
        try:
            veredicto = classify_fact(claim, wiki_title=c.get("label") or "")
        except Exception as exc:  # noqa: BLE001
            logger.info("[entidades] juez falló para %s: %s", c.get("id"), exc)
            continue
        if veredicto.get("verdict") == "supported":
            apoyados.append(c)
    return apoyados[0] if len(apoyados) == 1 else None


def resolve_all(db, material: str, title: str = "") -> list[ResolvedEntity]:
    """Extrae e identifica todas las entidades del artículo."""
    resueltas = [resolve(db, m) for m in extract_mentions(material, title)]
    for r in resueltas:
        logger.info(
            "[entidades] %-28s %-10s %s",
            r.mention.surface[:28], r.status, r.label or r.reason[:60],
        )
    return resueltas


def sujeto(entidades: list[ResolvedEntity]) -> ResolvedEntity | None:
    """La entidad que protagoniza la noticia, si el artículo la señala."""
    return next((e for e in entidades if e.mention.es_sujeto), None)


def silenciadas(entidades: list[ResolvedEntity]) -> list[str]:
    """Nombres que NO pueden aparecer en el texto: ni identificados ni descritos."""
    return [e.mention.surface for e in entidades if e.silenciada]


def sin_foto(entidades: list[ResolvedEntity]) -> list[str]:
    """Nombrables, pero sin identidad acreditada fuera del artículo: no dan cara."""
    return [e.mention.surface for e in entidades if not e.da_foto]
