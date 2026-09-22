"""Lo que se afirma en un caption tiene que estar en el artículo.

El dato inventado del item 348 no fue una cifra ni una fecha: fue una RELACIÓN
entre dos entidades — «figuras del mundo del fútbol como Guardiola reconocen la
influencia de Robe». Ninguna guarda del repo mira eso… salvo una que existía y a
la que Instagram no llamaba nunca: `web_verify.verify_connection`, cuyo docstring
es literalmente «¿Están A y B realmente relacionados?».

El resto de guardas del proyecto tampoco corrían aquí. Un caption de noticia
pasaba por UNA cosa: `fact_check.check_body` con `use_web=False`, dentro de un
`try/except: pass`, y eso solo sabe de canción↔álbum↔año.

DOS REGLAS SUTILES, y van aquí porque alguien las va a querer «unificar»:

1. La AUSENCIA de evidencia BLOQUEA. No se aplica el criterio de
   `web_verify.classify_fact`, donde `not_found` ≠ `contradicted`. Aquel criterio
   existe para no BORRAR datos reales de páginas ya publicadas que la web
   simplemente no indexa. Aquí la decisión es la contraria: vamos a AFIRMAR algo
   nuevo en una cuenta pública, así que con no encontrarlo basta para callarse.

2. La relación se comprueba contra EL ARTÍCULO, nunca contra la web. Ver
   `_lo_dice_el_articulo`: preguntarle a Google resultó aprobar tanto la
   afirmación inventada del caso como una cita de otra persona atribuida a la
   protagonista.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services import news_entities as ne

logger = logging.getLogger(__name__)

_SYS_RELACIONES = (
    "Extraes las RELACIONES que un texto AFIRMA entre dos entidades. No "
    "interpretas ni deduces: solo lo que el texto dice.\n"
    "Te doy una lista de entidades conocidas. Devuelve JSON con la clave "
    '"relaciones": una lista de objetos {"a", "relacion", "b"}, donde "a" y "b" '
    "son DOS de las entidades de la lista y \"relacion\" es lo que el texto dice "
    "que las une, en tres o cuatro palabras.\n"
    "Solo relaciones de HECHO (es fan de, admira a, reconoce la influencia de, "
    "colaboró con, versionó a, asistió a, fundó). NO incluyas la simple "
    "coaparición ni las valoraciones de quien escribe.\n"
    "IMPORTANTE: el texto puede nombrar a una entidad de forma PARCIAL (solo el "
    "apellido, solo el nombre artístico). Cuenta igual: devuelve entonces el "
    "nombre tal como está en la lista.\n"
    "Ejemplo. Lista: «María Guardiola, Robe». Texto: «Es un honor que figuras del "
    "mundo del fútbol como Guardiola reconozcan la influencia de Robe». "
    'Respuesta: {"relaciones": [{"a": "María Guardiola", '
    '"relacion": "reconoce la influencia de", "b": "Robe"}]}.\n'
    "Si el texto no afirma ninguna relación entre dos entidades de la lista, "
    "devuelve la lista vacía."
)


@dataclass
class Veredicto:
    """Qué impide publicar esto, y qué solo hay que mirar."""

    bloqueos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.bloqueos


def _entidades_conocidas(entidades: list[ne.ResolvedEntity]) -> list[str]:
    """Con quién se puede afirmar una relación: las identificadas, más los de casa.

    Se dan las DOS formas del nombre (la canónica y la que usa el artículo),
    porque un texto nombra a alguien entero una vez y por el apellido el resto:
    con solo «María Guardiola» en la lista, el extractor no veía la relación en
    una frase que decía «Guardiola», y la afirmación inventada pasaba entera.
    """
    nombres: set[str] = {"Robe", "Extremoduro"}
    for e in entidades:
        if not e.resuelta:
            continue
        if e.label:
            nombres.add(e.label)
        if e.mention.surface:
            nombres.add(e.mention.surface)
    return sorted(nombres)


def _en_el_material(relacion: dict, material: str) -> bool:
    """¿El artículo respalda esta relación? Determinista y gratis, primero.

    Se pide que los DOS extremos y alguna palabra con contenido de la relación
    estén en el material. No prueba que el artículo lo afirme —para eso está el
    verificador—, pero descarta barato lo que sí está escrito.
    """
    import re

    from app.services.content_guard import anclaje_factual
    from app.services.image_guard import _norm, _significant_words

    mat = _norm(material)

    def _esta(palabra: str) -> bool:
        """Palabra COMPLETA, no substring.

        Con `in` a secas, «fan» casaba dentro de «infantil» y daba por buena la
        afirmación «Guardiola es fan de Extremoduro» contra un artículo que no la
        menciona. Es el mismo bug que el de los títulos cortos del catálogo, donde
        «carrera» casaba dentro de «su carrera» y colaba un vídeo de otra cantante.
        """
        return re.search(rf"\b{re.escape(palabra)}\b", mat) is not None

    for extremo in (relacion.get("a"), relacion.get("b")):
        palabras = _significant_words(extremo or "")
        if not palabras or not all(_esta(w) for w in palabras):
            return False
    verbos = _significant_words(relacion.get("relacion") or "")
    if verbos and not any(_esta(v) for v in verbos):
        return False
    return anclaje_factual(
        f"{relacion.get('a')} {relacion.get('relacion')} {relacion.get('b')}", material
    )


def verificar_relaciones(
    texto: str, material: str, entidades: list[ne.ResolvedEntity]
) -> tuple[list[str], list[dict]]:
    """Devuelve (motivos de bloqueo, afirmaciones con su veredicto)."""
    from app.services.news_research import _json

    conocidas = _entidades_conocidas(entidades)
    if not texto.strip() or len(conocidas) < 2:
        return [], []

    data = _json(
        _SYS_RELACIONES,
        f"ENTIDADES: {', '.join(conocidas)}\n\nTEXTO:\n\"\"\"\n{texto}\n\"\"\"",
        max_tokens=500,
        temperature=0,
    )
    crudas = data.get("relaciones")
    if not isinstance(crudas, list):
        crudas = next((v for v in (data or {}).values() if isinstance(v, list)), [])

    bloqueos: list[str] = []
    claims: list[dict] = []
    for r in crudas:
        if not isinstance(r, dict):
            continue
        a, b = (r.get("a") or "").strip(), (r.get("b") or "").strip()
        rel = (r.get("relacion") or "").strip()
        if not a or not b or a == b:
            continue
        frase = f"{a} — {rel} — {b}"

        if _en_el_material(r, material):
            claims.append({"claim": frase, "verdict": "supported", "source": "material",
                           "evidence": "Lo dice el propio artículo."})
            continue

        veredicto = _lo_dice_el_articulo(frase, material)
        claims.append({"claim": frase, **veredicto})
        if veredicto["verdict"] != "supported":
            bloqueos.append(
                f"El texto afirma que {frase}, y el artículo no lo dice."
            )
    return bloqueos, claims


_SYS_RESPALDO = (
    "Dices si un ARTÍCULO respalda una AFIRMACIÓN. Solo cuenta lo que el artículo "
    "dice o se deduce sin lugar a dudas de lo que dice. No aportes nada que sepas "
    "por tu cuenta.\n"
    'Devuelve JSON: {"respalda": true|false, "cita": "el fragmento LITERAL del '
    'artículo que lo respalda, o cadena vacía"}'
)


def _lo_dice_el_articulo(frase: str, material: str) -> dict:
    """¿El ARTÍCULO respalda esta afirmación? La web aquí no pinta nada.

    La primera versión preguntaba a `web_verify.verify_connection`, y eso resultó
    ser una puerta trasera de las gordas. Medido el 22-09-2026:

      · «Guardiola reconoce la influencia de Robe» → confirmado, y la evidencia
        era LA PROPIA NOTICIA: el verificador buscaba en Google, encontraba el
        titular y daba por bueno que existía una relación. Confirma coaparición,
        no la relación concreta.
      · «María Guardiola es fan de Extremoduro» → confirmado, con la evidencia
        «fan absoluto que soy de Extremoduro»… que es una frase de OTRA persona,
        pescada de una página cualquiera y atribuida a ella.

    Un post de noticia habla de UNA noticia: su única fuente legítima es ese
    artículo. Que Google encuentre un fragmento parecido no autoriza a afirmar
    nada, y ya se vio adónde lleva.
    """
    from app.services.news_research import _json

    if not material.strip():
        return {"verdict": "not_found", "source": "", "evidence": "No hay artículo."}

    data = _json(
        _SYS_RESPALDO,
        f"AFIRMACIÓN: {frase}\n\nARTÍCULO:\n\"\"\"\n{material[:6000]}\n\"\"\"",
        max_tokens=300,
        temperature=0,
    )
    cita = (data.get("cita") or "").strip()
    # El juez propone, el artículo dispone: la cita tiene que estar de verdad.
    respalda = bool(data.get("respalda")) and bool(cita) and cita[:60] in material
    return {
        "verdict": "supported" if respalda else "not_found",
        "source": "material",
        "evidence": cita[:400] if respalda else "No está en el artículo.",
    }


def _variantes(nombre: str) -> list[str]:
    """Formas en que un texto puede nombrar a esta entidad.

    Hace falta porque el artículo y el caption no la llaman igual: el artículo
    dice «María Guardiola» (y de ahí sale la mención), pero el caption decía solo
    «Guardiola». Buscando únicamente el nombre completo, la guarda no encontraba
    la frase y el post pasaba — lo comprobó el barrido de `audit_identidad` sobre
    el caso real, que dijo «nada que revisar» del post que había que cazar.
    """
    from app.services.image_guard import _significant_words

    partes = (nombre or "").split()
    formas = [nombre]
    if len(partes) >= 2 and _significant_words(partes[-1]):
        formas.append(partes[-1])  # el apellido, que es como se le nombra luego
    return [f for f in formas if f]


def _frases_con(nombre: str, texto: str) -> list[str]:
    """Frases del texto que nombran a esta entidad, la llamen como la llamen."""
    import re

    from app.services.instagram.newsroom import _aparece

    frases = re.split(r"(?<=[.!?\n])\s+", texto or "")
    return [
        f for f in frases
        if any(_aparece(v, f) for v in _variantes(nombre))
    ]


def contradice_la_identidad(
    texto: str, entidades: list[ne.ResolvedEntity]
) -> list[str]:
    """¿El texto le atribuye a alguien un oficio que no es el suyo?

    ESTA es la guarda que cazaba el item 348, y costó encontrarla: lo falso de
    aquel caption no era la relación —«Guardiola reconoce la influencia de Robe»
    se sostiene en el artículo, que habla de un lema inspirado en él— sino el
    inciso «figuras del MUNDO DEL FÚTBOL como Guardiola». Eso no es una relación
    entre dos entidades: es un atributo, y contradecía frontalmente a la entidad
    que habíamos identificado, «política española».

    Se mira frase a frase, no en todo el texto: un post sobre música puede
    nombrar un estadio sin que eso convierta a nadie en futbolista.
    """
    from app.services.image_guard import conflicto_de_dominio

    problemas: list[str] = []
    for e in entidades:
        # `descripcion_efectiva` es la de Wikidata o, si no la hay, lo que el
        # artículo dice que es. Así también se protege a quien no está en ninguna
        # base de datos: si la noticia dice «concursante riojano» y el caption lo
        # convierte en futbolista, salta igual.
        referencia = e.descripcion_efectiva
        if e.silenciada or not referencia:
            continue
        nombre = e.label or e.mention.surface
        for frase in _frases_con(nombre, texto) + _frases_con(e.mention.surface, texto):
            intruso = conflicto_de_dominio(referencia, frase)
            if intruso:
                problemas.append(
                    f"El texto sitúa a {nombre} en el mundo de {intruso}, y es "
                    f"{referencia}: «{frase.strip()[:90]}»"
                )
                break
    return problemas


def revisar(
    db, texto: str, material: str, entidades: list[ne.ResolvedEntity]
) -> Veredicto:
    """Pasa el caption por todas las guardas. Determinista y gratis primero."""
    from app.services import lyric_guard, sensitive_topics
    from app.services.content_guard import anclaje_factual, find_especulacion
    from app.services.instagram import newsroom

    v = Veredicto()

    # 1. Lo silenciado no se nombra. Sin red, sin clave, sin coste.
    coladas = newsroom.comprobar_silenciadas(texto, entidades)
    if coladas:
        v.bloqueos.append(
            f"El texto nombra a {', '.join(coladas)}, y no sabemos quién es."
        )

    # 2. Nadie cambia de oficio por el camino.
    v.bloqueos.extend(contradice_la_identidad(texto, entidades))

    # 3. ¿Se apoya en el artículo?
    if material and not anclaje_factual(texto, material):
        v.bloqueos.append(
            "Ni un solo dato del texto aparece en el artículo: es relleno."
        )

    # 4. Fórmulas de relleno y especulación.
    especulacion = find_especulacion(texto)
    if especulacion:
        v.bloqueos.append(f"Especula en vez de contar: {', '.join(especulacion[:3])}.")

    # 5. Versos: ni se inventa una letra ni se atribuye a la canción equivocada.
    #    `blocking` no se publica jamás; `to_review` es zona gris y va a una
    #    persona. Los captions llevan un verso casi siempre, así que esto importa.
    try:
        informe = lyric_guard.check_lyrics(db, texto)
        if informe.blocking:
            v.bloqueos.append(
                f"Verso que no existe o sin letra verificable: {informe.blocking[0].quote[:60]}"
            )
        elif informe.to_review:
            v.avisos.append(
                f"Verso posiblemente mal atribuido: {informe.to_review[0].quote[:60]}"
            )
    except Exception as exc:  # noqa: BLE001
        # No se traga en silencio: un `pass` mudo es como muere una guarda sin
        # que nadie se entere (ver `captions.py:289`).
        logger.warning("[caption] lyric_guard no pudo correr: %s", exc)
        v.avisos.append("No se han podido comprobar las citas de letra.")

    # 6. Relaciones afirmadas (lo caro: al final, y solo si lo demás pasa).
    if not v.bloqueos:
        bloqueos, claims = verificar_relaciones(texto, material, entidades)
        v.bloqueos.extend(bloqueos)
        v.claims.extend(claims)

    # 7. Avisos que NO bloquean: los mira una persona.
    if sensitive_topics.menciona_fallecimiento(texto):
        v.avisos.append("El texto menciona el fallecimiento de Robe: comprueba el tono.")

    return v
