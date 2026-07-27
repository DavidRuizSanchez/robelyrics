"""Guarda de imágenes: que ninguna foto se publique sin acreditar A QUIÉN retrata,
y que ninguna imagen del site dependa de un servidor ajeno.

Nace de dos fallos reales y repetidos:

  1. **Imágenes rotas.** Las fotos de entidades se guardaban como hot-link a
     `upload.wikimedia.org`. Wikimedia rate-limita el hotlinking: el optimizador de
     Next pide varias a la vez desde la IP del server y Commons responde **429**, así
     que se rompen unas u otras según el momento — nunca las mismas, nunca del todo.
     Existía un `--rehost` manual, pero el camino de asignación seguía guardando
     hotlinks, así que el problema volvía solo. Aquí la regla es al revés: una URL
     externa NUNCA llega a la BD (`must_rehost`).

  2. **Imágenes falsas.** Las fotos se buscaban POR NOMBRE en Commons/Wikidata y se
     asignaban sin comprobar que la fuente dijera que son ellos. Resultado: una foto
     de las fiestas de San Isidro como retrato de Los Enemigos, un homónimo mexicano
     para Los Niños de los Ojos Rojos, y una foto de prensa de vaya usted a saber
     quién como Rebrote. `verify_provenance` exige que la PROCEDENCIA acredite la
     identidad; si no la acredita, no se publica. Mejor sin foto que con la de otro.

No se trata de reconocer caras (ni un modelo de visión sabe quién es Rebrote): se
trata de exigir que alguien fiable haya dicho que esa foto es de esa entidad.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

# Dominios cuyo contenido servimos nosotros (no dependen de terceros).
_OWN_HOSTS = ("res.cloudinary.com",)

# Hosts que rate-limitan el hotlinking (el 429 de Wikimedia es el caso vivo).
_HOTLINK_HOSTS = ("upload.wikimedia.org", "wikipedia.org", "wikimedia.org")

_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_UA = "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com)"

# Pistas de que un fichero de Commons retrata a un homónimo de otro país. No
# deciden solas: marcan el caso para que lo mire un humano.
_FOREIGN_HINTS = (
    "mexico", "méxico", "puebla", "argentina", "chile", "colombia", "peru", "perú",
    "venezuela", "uruguay", "bolivia", "ecuador", "brasil", "guatemala",
)

# Señales de que el fichero va de música. Un apodo de una sola palabra («Salo»,
# «Fito», «Uoho») casa con cualquier cosa —«Salo (food) in Ukraine» acreditaba al
# batería de Extremoduro con una foto de tocino—, así que para esos nombres se
# exige además contexto musical.
_DOMAIN_HINTS = (
    "music", "musica", "musico", "musik", "musika", "band", "banda", "grupo", "rock",
    "punk", "metal", "concert", "concierto", "gira", "tour", "festival", "singer",
    "cantante", "guitar", "guitarra", "bass", "bajo", "drummer", "bateria", "album",
    "extremoduro", "robe", "song", "cancion", "live", "directo", "discografia",
    "songwriter", "escenario", "stage",
)

# Señales de que una imagen alojada por nosotros VIENE de una fuente libre: se
# re-alojó en su día y se perdió el fichero de origen. Hay traza (autor + licencia),
# así que no se toca; solo se anota que no se puede re-verificar.
_CC_TRACE = ("wikimedia", "commons", "creative commons", "cc by", "cc-by", "flickr")

Status = str  # own_art | accredited | unaccredited | homonym_risk | unsourced | unknown


@dataclass
class ProvenanceVerdict:
    """¿Podemos afirmar que esta imagen es de esta entidad?"""

    status: Status
    reason: str
    evidence: list[str] = field(default_factory=list)

    @property
    def publishable(self) -> bool:
        """Lo que puede seguir publicado: acreditado, arte propio (no afirma
        identidad) y lo re-alojado con traza de licencia libre."""
        return self.status in ("own_art", "accredited", "legacy_cc")

    @property
    def needs_human(self) -> bool:
        """Ni se publica a ciegas ni se borra sola: la mira un humano.

        NINGUNA foto se retira automáticamente, ni siquiera cuando Commons no la
        acredita. Los metadatos son irregulares —a Leiva lo escriben «Leyva»— y un
        falso positivo borraría contenido bueno de una web pública. La duda se
        señala; el borrado lo ejecuta una persona desde el botón «Arreglar»."""
        return self.status in ("homonym_risk", "unverifiable", "unaccredited")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _strip_authorship(description: str) -> str:
    """Quita de la descripción a QUIEN HIZO la imagen, para no confundirlo con
    quien SALE en ella.

    Caso real: «Francisco de Miranda **by Lorenzo Gonzalez**, 1977» se aceptó como
    retrato de Lorenzo González (un homónimo pintor) cuando el retratado es otro.
    El autor no acredita el contenido.
    """
    if not description:
        return ""
    patron = r"\b(?:by|por|photo(?:graph)?(?:\s+by)?|foto(?:graf[íi]a)?|©|\(c\))\s*:?\s*[^,.;()]{0,60}"
    return re.sub(patron, " ", description, flags=re.IGNORECASE)


def _significant_words(name: str) -> list[str]:
    """Palabras con las que reconocer el nombre en un texto ajeno. Fuera artículos
    y preposiciones: «Los Enemigos» tiene que casar por «enemigos», no por «los»."""
    stop = {"los", "las", "el", "la", "de", "del", "y", "e", "en", "un", "una"}
    return [w for w in _norm(name).split() if w not in stop and len(w) > 2]


def is_own_host(url: str | None) -> bool:
    return bool(url) and any(h in url for h in _OWN_HOSTS)


def must_rehost(url: str | None) -> bool:
    """¿Esta URL hay que traérsela antes de guardarla? Todo lo que no sea nuestro
    o una ruta local del propio site."""
    if not url:
        return False
    if url.startswith("/"):          # servida por el propio Next (public/)
        return False
    return not is_own_host(url)


def hotlinks_a_tercero(url: str | None) -> bool:
    """URL que además vive en un host que castiga el hotlinking (429)."""
    return bool(url) and any(h in url for h in _HOTLINK_HOSTS)


def commons_filename(url: str | None, source_url: str | None = None) -> str | None:
    """Nombre canónico del fichero de Commons a partir de la URL de imagen o de la
    página File:. Devuelve None si no es de Commons."""
    for candidate in (source_url, url):
        if not candidate:
            continue
        m = re.search(r"/wiki/File:(.+)$", candidate)
        if m:
            return unquote(m.group(1))
        if "upload.wikimedia.org" in candidate:
            # .../commons/thumb/d/d9/Leño_en_1981.jpg/1280px-Leño_en_1981.jpg
            m = re.search(r"/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/]+)", candidate)
            if m:
                return unquote(m.group(1))
    return None


def commons_evidence(filename: str, *, timeout: float = 15.0) -> dict:
    """Categorías + descripción de un fichero de Commons. Es lo que usa la
    comunidad para decir QUÉ hay en la foto, y por tanto lo que puede acreditar
    una identidad. Nunca lanza: sin red, no se acredita nada (y no se publica)."""
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "titles": f"File:{filename}",
        "prop": "categories|imageinfo", "iiprop": "extmetadata", "cllimit": "50",
    }
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": _UA}) as client:
            r = client.get(_COMMONS_API, params=params)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[image_guard] Commons no responde para %s: %s", filename, exc)
        return {}
    if not pages:
        return {}
    page = pages[0]
    meta = (page.get("imageinfo") or [{}])[0].get("extmetadata", {})
    return {
        "categories": [c.get("title", "").replace("Category:", "")
                       for c in page.get("categories", [])],
        "description": re.sub(r"<[^>]+>", " ", meta.get("ImageDescription", {}).get("value", "")),
        "missing": page.get("missing", False),
    }


def verify_provenance(
    *,
    entity_name: str,
    image_url: str | None,
    source_url: str | None = None,
    attribution: str | None = None,
    license_: str | None = None,
    aliases: list[str] | None = None,
) -> ProvenanceVerdict:
    """¿La procedencia acredita que esta imagen es de esta entidad?

    `aliases` son otras formas de llamarla (nombre artístico y nombre completo de
    una persona): basta que UNA case, porque Commons etiqueta a Kutxi Romero por su
    nombre artístico y a otros por el de pila."""
    if not image_url:
        return ProvenanceVerdict("unknown", "Sin imagen.")

    # Arte propio: no afirma ser un retrato, se publica con su crédito.
    if is_own_host(image_url) and "generado por ia" in _norm(attribution or "").replace("í", "i"):
        return ProvenanceVerdict("own_art", "Arte propio generado por IA (no es un retrato).")
    if is_own_host(image_url) and _norm(attribution or "").startswith("arte generado"):
        return ProvenanceVerdict("own_art", "Arte propio generado por IA (no es un retrato).")

    fname = commons_filename(image_url, source_url)
    if not fname:
        attr_norm = _norm(attribution or "")
        if any(t in attr_norm for t in _CC_TRACE) or _norm(license_ or "").startswith("cc"):
            # Se re-alojó en su día desde una fuente libre y se perdió el fichero
            # original. Hay autor y licencia: se conserva, pero conste que no se
            # puede re-verificar contra Commons.
            return ProvenanceVerdict(
                "legacy_cc",
                "Re-alojada desde una fuente libre; sin fichero de origen para re-verificar.",
                evidence=[f"crédito: {attribution or '—'}", f"licencia: {license_ or '—'}"],
            )
        # Ni arte propio, ni Commons, ni traza de licencia: una foto de la web con
        # un crédito escrito a mano. Es el caso «Rebrote». No se puede afirmar que
        # sea esta entidad, pero tampoco se borra sola: lo decide un humano.
        return ProvenanceVerdict(
            "unverifiable",
            "Foto sin fuente verificable: nada acredita que sea esta entidad.",
            evidence=[f"crédito: {attribution or '—'}", f"licencia: {license_ or '—'}"],
        )

    ev = commons_evidence(fname)
    if not ev or ev.get("missing"):
        return ProvenanceVerdict(
            "unaccredited", f"El fichero «{fname}» no está en Commons o no se pudo consultar.")

    haystack = _norm(" ".join(ev.get("categories", [])) + " " + _strip_authorship(
        ev.get("description", "")))
    candidatos = [n for n in ([entity_name] + list(aliases or [])) if _significant_words(n)]
    if not candidatos:
        # Sin nombre no se puede acreditar NI desacreditar: sería retirar fotos buenas
        # por un fallo nuestro (pasó al leer `Person.name`, que no existe: es
        # stage_name/full_name).
        return ProvenanceVerdict(
            "unknown", "No sé con qué nombre acreditar esta entidad.",
            evidence=[f"fichero: {fname}"])

    tiene_contexto_musical = any(h in haystack for h in _DOMAIN_HINTS)
    categorias_norm = {_norm(c) for c in ev.get("categories", [])}

    def _casa(nombre: str) -> bool:
        palabras = _significant_words(nombre)
        if not all(w in haystack for w in palabras):
            return False
        if len(palabras) >= 2 or tiene_contexto_musical:
            return True
        # Un nombre de una sola palabra no acredita por sí solo («Salo» casa con
        # salo, el tocino ucraniano). Salvo que Commons le dedique una categoría
        # ENTERA: «Category:Rosendo» sí dice de quién es la foto.
        return _norm(nombre) in categorias_norm

    acredita = any(_casa(n) for n in candidatos)

    if not acredita:
        return ProvenanceVerdict(
            "unaccredited",
            f"Commons no dice que «{entity_name}» esté en esta foto.",
            evidence=[f"fichero: {fname}",
                      f"categorías: {', '.join(ev.get('categories', [])[:5]) or '—'}",
                      f"descripción: {(ev.get('description') or '—').strip()[:120]}"],
        )

    foreign = [h for h in _FOREIGN_HINTS if h in haystack]
    if foreign:
        return ProvenanceVerdict(
            "homonym_risk",
            f"El nombre casa, pero la foto es de {foreign[0]}: puede ser un homónimo.",
            evidence=[f"fichero: {fname}",
                      f"categorías: {', '.join(ev.get('categories', [])[:5])}",
                      f"descripción: {(ev.get('description') or '').strip()[:120]}"],
        )

    return ProvenanceVerdict(
        "accredited",
        f"Commons acredita a «{entity_name}» en esta foto.",
        evidence=[f"fichero: {fname}",
                  f"categorías: {', '.join(ev.get('categories', [])[:5])}"],
    )
