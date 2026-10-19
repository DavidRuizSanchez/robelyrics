"""La voz es nuestra: el texto publicado no nombra a editores externos.

Criterio de David (19-10-2026), al tumbar el primer borrador de una fusión: «se
hace mención a editores externos como Juancares, El País, blogs de manera
explícita; esto nunca debe ser así: debemos crear contenido propio basado en
nuestro corpus». El borrador decía, literal:

  - «El blog javitojavierito recoge que Extremoduro definió su estilo…»
  - «Mikel López Iturriaga, en El País, describió…»
  - «El análisis de Juancares en YouTube describe una canción…»

No era el modelo: se lo ordenaba el motor. `corpus_for_queries` etiquetaba cada
pasaje con «cítalo como «…»». La voz del sitio ya decía lo contrario («SIN
nombrarlas en el texto», «NUNCA menciones el medio»).

Lo que SÍ se nombra:
  - **Robe, y el medio donde lo dijo** («Robe contó a RockFM que…»). Es la voz del
    protagonista, no un editor externo (decisión de David, 19-10-2026).
  - **setlist.fm y MusicBrainz**, cuyos términos exigen la atribución.

Determinista, sin red y sin LLM. Dos usos: `fuentes_nombradas` para bloquear o
avisar, y `limpiar` para quitar las frases culpables cuando se puede.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

# Medios de prensa, radio y tele. Son los ÚNICOS que pueden aparecer, y solo
# cuando la frase pone palabras en boca de Robe («Robe contó a RockFM…»).
_MEDIOS = (
    "rockfm", "rock fm", "cadena ser", "rne", "radio nacional", "rtve", "movistar",
    "los40", "cadena 100", "europa fm", "efe eme", "mondo sonoro", "mondosonoro",
    "rockdelux", "jenesaispop", "muzikalia", "binaural", "mariskal rock", "rockzone",
    "indie hoy", "dirty rock", "science of noise", "20minutos", "el confidencial",
    "eldiario", "la razón", "el español", "infolibre", "la vanguardia", "diario hoy",
    "hoy.es", "fuego y chinchetas", "la gran travesía", "el periódico extremadura",
)
# Medios cuyo nombre es también una frase corriente («todo el mundo», «el público
# cantaba»): solo cuentan escritos tal cual, con su mayúscula.
_MEDIOS_MAYUS = ("El País", "El Mundo", "Público", "ABC", "El Periódico")
# Analistas, blogs, canales y plataformas de fans: nunca, ni hablando de Robe.
_ANALISTAS = (
    "genius", "reddit", "wikipedia", "juancares", "juancaraes", "tesónica", "tesonica",
    "la ley de extremoduro", "laleydeextremoduro", "javitojavierito", "noche de rock",
    "mediavida", "foro azkena",
)

# Fórmulas de atribución aunque el nombre no esté en ninguna lista.
_FORMULAS = re.compile(
    r"\bseg[uú]n (?:el|la|un|una|los|las|su) (?:blog|an[aá]lisis|canal|v[ií]deo|art[ií]culo"
    r"|cr[ií]tica|rese[ñn]a|anotaci[oó]n|web|medio|peri[oó]dico|revista|foro|fan|usuario)"
    r"|\b(?:el|un|una|este|ese) (?:blog|canal|foro|youtuber|bloguero|comentarista)\b"
    r"|\banotaci[oó]n de genius\b|\ben (?:youtube|reddit|genius|wikipedia|un foro)\b"
    r"|\b(?:el|un) an[aá]lisis de [A-ZÁÉÍÓÚÑ]"
    r"|\bcomo (?:recoge|se[ñn]ala|apunta|explica|sostiene) (?:el|la|un|una) "
    r"(?:blog|an[aá]lisis|canal|art[ií]culo|cr[ií]tica)",
    re.I,
)

# Robe hablando: su palabra se cita, y con el medio.
_ROBE_HABLA = re.compile(
    r"\bRobe\b[^.!?]{0,60}\b(?:dijo|cont[oó]|explic[oó]|declar[oó]|confes[oó]|asegur[oó]"
    r"|reconoci[oó]|coment[oó]|afirm[oó]|record[oó]|habl[oó]|respond[ií]a|respondi[oó]"
    r"|dec[ií]a|contaba|explicaba|confesaba)\b",
    re.I,
)
_EXENTAS = ("setlist.fm", "musicbrainz")

# Frases que hablan del PROCESO y no del tema: eco de las instrucciones. Medidas
# en los borradores reales del 19-10-2026: «Estos nombres responden a las
# búsquedas…», «El fragmento disponible no identifica el título…», «El material no
# confirma por qué…».
_METATEXTO = re.compile(
    r"\bb[uú]squedas?\b|\bpalabras? clave\b|\bkeywords?\b|\bSEO\b"
    r"|\bregistro de (?:miembros|integrantes)\b|\bformaci[oó]n registrada\b"
    r"|\bperiodos? (?:confirmados|registrados)\b|\ben el registro\b"
    r"|\bel fragmento\b|\bel material (?:disponible|no|consultado)\b"
    r"|\bel an[aá]lisis disponible\b|\bel texto disponible\b"
    r"|\blas fuentes (?:consultadas|disponibles)\b|\bno corresponde adjudic"
    r"|\ben el texto\b|\bformaci[oó]n citada\b|\bseg[uú]n el material\b",
    re.I,
)
_FRASE = re.compile(r"[^.!?\n]+[.!?]?")


def _plano(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _limpia_nombre(n: str) -> str:
    n = re.sub(r"^google news ·.*$", "", n, flags=re.I)
    n = re.sub(r"\s+[—–-]\s+.*$", "", n)          # «El País — Cultura» → «El País»
    n = re.sub(r"\s*\(.*?\)\s*", " ", n)           # «… (juancaraes)» → «…»
    return n.strip().strip("@").strip()


@lru_cache(maxsize=1)
def _nombres_yaml() -> tuple[str, ...]:
    out: list[str] = []
    for base in (Path("/app/data"), Path(__file__).resolve().parents[3] / "data"):
        # Solo el registro del corpus de fans. Las noticias (`news_sources.yaml`)
        # son prensa, que ya cubre `_MEDIOS`, y algunos de sus nombres son títulos
        # de canción («Maneras de Vivir»).
        for fichero in ("sources.yaml",):
            p = base / fichero
            if not p.exists():
                continue
            for m in re.finditer(r"^\s*(?:-\s*)?(?:name|handle):\s*\"?([^\"\n]+)\"?",
                                 p.read_text(encoding="utf-8"), re.M):
                n = _limpia_nombre(m.group(1))
                if len(n) < 4 or len(n) > 40 or n.lower().startswith("r/"):
                    continue
                # «La historia de Extremoduro» o «Extremoduro en Plasencia» son el
                # nombre de una fuente y también una frase que el texto puede decir
                # con todo derecho. Esas se quedan fuera; las que importan de verdad
                # (La Ley de Extremoduro…) están en `_ANALISTAS`.
                if " " in n and re.search(r"extremoduro|robe", _plano(n)):
                    continue
                out.append(n)
        if out:
            break
    return tuple(out)


def nombres_de_fuentes(db=None) -> list[str]:
    """Todo nombre de analista, blog o canal que no puede aparecer en el texto.

    Los medios de prensa van aparte (`_MEDIOS`): esos sí pueden salir cuando habla
    Robe.
    """
    medios = {_plano(m) for m in _MEDIOS}
    nombres = list(_ANALISTAS) + [n for n in _nombres_yaml() if _plano(n) not in medios]
    if db is not None:
        try:
            from app.db.models import InterpretationSource, Person

            # La gente del universo no es un editor externo: Manolo Chinato puede
            # ser autor de una entrevista del corpus y, a la vez, quien firma el
            # poema de una canción (y eso hay que decirlo, ver AUTORÍA en la voz).
            gente = {_plano(n) for p in db.query(Person).all()
                     for n in (p.stage_name, p.full_name) if n}
            for (autor,) in db.query(InterpretationSource.author).distinct().all():
                if autor and len(autor.strip()) >= 4 and _plano(autor) not in gente:
                    nombres.append(autor.strip())
        except Exception:  # noqa: BLE001
            pass
    vistos, out = set(), []
    for n in nombres:
        k = _plano(n)
        # «Robe» puede ser autor de una entrevista: no es un editor externo.
        if k and k not in vistos and k not in ("robe", "roberto iniesta"):
            vistos.add(k)
            out.append(n)
    return out


def _busca(nombre: str, plano: str) -> bool:
    return bool(re.search(r"(?<![\w])" + re.escape(_plano(nombre)) + r"(?![\w])", plano))


def _culpa(frase: str, nombres: list[str]) -> str | None:
    """Qué hace que esta frase nombre a un editor externo, o None."""
    plano = _plano(frase)
    if any(e in plano for e in _EXENTAS):
        return None
    # Analistas, blogs y canales: nunca, aunque la frase cite a Robe («Juancares
    # explica que Robe dijo…» sigue siendo nombrar a Juancares).
    m = _FORMULAS.search(frase)
    if m:
        return m.group(0)
    for n in nombres:
        if _busca(n, plano):
            return n
    # Prensa: solo si la frase NO es Robe hablando.
    medio = next((m for m in _MEDIOS if _busca(m, plano)), None) or next(
        (m for m in _MEDIOS_MAYUS
         if re.search(r"(?<![\w])" + re.escape(m) + r"(?![\w])", frase)), None)
    if medio and not _ROBE_HABLA.search(frase):
        return medio
    return None


def fuentes_nombradas(texto: str, nombres: list[str] | None = None) -> list[tuple[str, str]]:
    """[(frase, lo que la delata)] de cada frase que nombra a un editor externo."""
    nombres = nombres if nombres is not None else nombres_de_fuentes()
    out = []
    for linea in (texto or "").split("\n"):
        if linea.lstrip().startswith("#"):
            continue
        # Un enlace no es mención: el texto del enlace sí lo es, la URL no.
        sin_urls = re.sub(r"\]\(x*\)", "]", _enmascarar(linea))
        for frase in _FRASE.findall(sin_urls):
            culpa = _culpa(frase, nombres)
            if culpa:
                out.append((frase.strip(), culpa))
    return out


def metatexto(texto: str) -> list[str]:
    return [f.strip() for linea in (texto or "").split("\n")
            if not linea.lstrip().startswith("#")
            for f in _FRASE.findall(linea) if _METATEXTO.search(f)]


def _enmascarar(linea: str) -> str:
    """La misma línea con las URLs de los enlaces tapadas por caracteres del mismo
    largo: así el troceo por frases no corta en el punto de «entreinteriores.com» y
    las posiciones siguen valiendo sobre el original."""
    linea = re.sub(r"\]\(([^)]*)\)", lambda m: "](" + "x" * len(m.group(1)) + ")", linea)
    return re.sub(r"https?://\S+", lambda m: "x" * len(m.group(0)), linea)


def limpiar(texto: str, nombres: list[str] | None = None) -> tuple[str, list[str]]:
    """Quita las frases que nombran fuentes o hablan del proceso.

    Devuelve (texto, frases quitadas). Los headings no se tocan, y se quita SOLO la
    frase culpable: la primera versión, cuando un párrafo llevaba un enlace, lo
    evaluaba entero y una frase mala se llevaba por delante las buenas.
    """
    nombres = nombres if nombres is not None else nombres_de_fuentes()
    quitadas: list[str] = []
    lineas = []
    for linea in (texto or "").split("\n"):
        if linea.lstrip().startswith("#") or not linea.strip():
            lineas.append(linea)
            continue
        mascara = _enmascarar(linea)
        buenas = []
        for m in _FRASE.finditer(mascara):
            original = linea[m.start():m.end()]
            evaluable = re.sub(r"\]\(x*\)", "]", m.group(0))
            if _METATEXTO.search(evaluable) or _culpa(evaluable, nombres):
                quitadas.append(original.strip())
            else:
                buenas.append(original)
        lineas.append("".join(buenas).strip())
    limpio = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return limpio, quitadas


def quitar_metatexto(texto: str) -> tuple[str, list[str]]:
    """Solo el metatexto (sin tocar menciones). Para el texto que no es corpus."""
    return limpiar(texto, nombres=[]) if _METATEXTO.search(texto or "") else (
        (texto or "").strip(), [])
