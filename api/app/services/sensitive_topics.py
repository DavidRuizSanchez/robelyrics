"""Cuándo un texto sobre Robe se ha dejado fuera algo que no se puede omitir.

El caso que lo motiva, publicado el 21-09-2026: un artículo recorría la
discografía de Extremoduro disco a disco, contaba la disolución, decía que «Robe
siguió explorando su creatividad» con «Mayéutica» (2021)… y ahí se paraba. Ni una
palabra de que había muerto en diciembre de 2025. Respetuoso, bien escrito, y
falso por omisión: deja al lector pensando que la historia sigue.

Es deliberadamente DETERMINISTA. El gate editorial ya juzga con un LLM, y ese
juez tiene varianza medida (tres pasadas sobre el mismo texto dieron revise,
reject y reject); una omisión se ve mejor con reglas que con olfato. Además esto
no rechaza nada: solo levanta la mano para que lo mire una persona.

Y es deliberadamente ESTRECHO. No todo lo que menciona a Robe tiene que hablar de
su muerte: un análisis de un verso de «So payaso» no es una necrológica. La regla
solo aplica cuando el texto RECORRE una trayectoria —enumera discos, encadena
años, titula «carrera» o «legado»— y el sujeto es Robe o Extremoduro. Si el
detector se pasa de listo, el remedio es peor: once días sin publicar ya pasó una
vez en este proyecto por un gate demasiado duro.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.services import robe_facts

# Decir que alguien murió y hablar en tono luctuoso NO son lo mismo, y confundirlo
# cuesta caro: `instagram/tone.py` marca como sobrio todo lo que huela a duelo
# —«homenaje», «tributo», «ausencia», «despedida»— porque su trabajo es elegir el
# emoji y el CTA del post. Probado contra el artículo real, esa regex daba por
# mencionada la muerte en un texto que solo decía «la gira de despedida fue
# cancelada». Aquí hace falta lo contrario: pocas palabras, y que todas
# signifiquen que murió.
_MENCIONA_MUERTE = re.compile(
    r"\b(muri[oó]|muere|ha\s+muerto|falleci[oó]|fallecimiento|defunci[oó]n|"
    r"su\s+muerte|la\s+muerte\s+de|tras\s+su\s+muerte|p[oó]stum\w+|"
    r"in\s+memoriam|nos\s+dej[oó])\b",
    re.IGNORECASE,
)

# Señales de que el texto hace RECORRIDO, no una mención de pasada.
_ENCABEZADO_TRAYECTORIA = re.compile(
    r"^#{1,4}\s.*\b(trayectoria|carrera|historia|evoluci[oó]n|discograf[ií]a|"
    r"legado|etapa|disoluci[oó]n|en solitario|a[nñ]os)\b",
    re.IGNORECASE | re.MULTILINE,
)
_ANYO = re.compile(r"\b(19[8-9]\d|20[0-2]\d)\b")

# El error del debut. Se mira FRASE a FRASE y no por proximidad: la redacción
# correcta —«su debut fue "Tú en tu casa" (1990); "Rock Transgresivo" (1994) es la
# regrabación que lo sustituyó»— nombra las dos cosas juntas, y con una regex de
# cercanía se marcaba como error justo el texto que queremos escribir.
_FRASE = re.compile(r"[^.!?\n]+[.!?\n]?")
_DEBUT = re.compile(r"\bdebut\w*\b", re.IGNORECASE)
_DEBUT_MAL = re.compile(r"\b1994\b|rock\s+transgresivo", re.IGNORECASE)
_DEBUT_BIEN = re.compile(r"\b1990\b|t[uú]\s+en\s+tu\s+casa", re.IGNORECASE)

# La disolución mal fechada.
_DISOLUCION_2018 = re.compile(
    r"disol\w+[^.]{0,60}\b2018\b|\b2018\b[^.]{0,40}disol\w+", re.IGNORECASE
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _sin_urls(s: str) -> str:
    """Vacía la URL de cada enlace markdown, conservando la longitud.

    Un slug NO es una mención. `lyric_guard._mask_link_urls` hace exactamente esto
    desde que un `/extremoduro/yo-minoria-absoluta/menamoro` falseaba la atribución
    de un verso; aquí el mismo slug contaba como «disco citado». Medido el
    24-09-2026: el análisis de una sola canción llegaba a cuatro discos —el suelo
    que dispara el gate— y uno era el `deltoya` de la URL de su propio enlace.
    """
    return re.sub(r"\]\(([^)\n]*)\)", lambda m: "](" + " " * len(m.group(1)) + ")", s or "")


# Un título ambiguo (disco Y canción: «Pedrá», «Agila», «Deltoya»…) solo cuenta
# como DISCO si el texto lo presenta como tal. Sin esto, nombrar dos canciones
# sumaba dos discos.
_MARCA_DISCO = re.compile(
    # Las comillas y el corchete del enlace van entre medias: «su disco '[Pedrá]».
    r"(?:\*|_)$|(?:disco|album|elepe|lp|en su|de su)\s*[\"'«\[*_]*$", re.IGNORECASE
)
_MARCA_DISCO_DERECHA = re.compile(r"^(?:\*|_|\s*\(\s*(?:19|20)\d\d\s*\))")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\n]*)\)")


def _discos_enlazados(cuerpo: str, titulos_norm: list[str]) -> set[str]:
    """Títulos cuyo enlace apunta a la PÁGINA DEL DISCO.

    La URL desambigua mejor que cualquier heurística y está ahí: `/extremoduro/
    deltoya` es el disco y `/extremoduro/deltoya/de-acero` es una canción suya.
    Sin mirarla, un «en "[Deltoya](…)" Robe escribe…» que enlaza al disco se
    descartaba por prudencia y dejaba de contar un recorrido real.
    """
    out: set[str] = set()
    for m in _LINK.finditer(cuerpo or ""):
        ancla = _norm(m.group(1))
        ruta = [x for x in m.group(2).split("?")[0].split("#")[0].split("/") if x]
        if ruta and ruta[0].startswith("http"):   # absoluta: fuera esquema y dominio
            ruta = ruta[2:]
        if len(ruta) != 2:                        # 2 segmentos = artista/disco
            continue
        out.update(t for t in titulos_norm if t in ancla)
    return out


def _cita_como_disco(cuerpo_norm: str, titulo_norm: str) -> bool:
    """¿Alguna aparición del título se presenta como disco y no como canción?

    Señales, todas del propio texto: cursiva markdown (`*Pedrá*`), la palabra
    «disco»/«álbum» justo antes, o el año entre paréntesis justo después.
    """
    for m in re.finditer(re.escape(titulo_norm), cuerpo_norm):
        izq = cuerpo_norm[max(0, m.start() - 24):m.start()]
        der = cuerpo_norm[m.end():m.end() + 10]
        if _MARCA_DISCO.search(izq) or _MARCA_DISCO_DERECHA.match(der):
            return True
    return False


@dataclass
class SensitiveReport:
    """Qué se ha encontrado. `necesita_revision` es lo único que frena algo."""

    es_trayectoria: bool = False
    omite_fallecimiento: bool = False
    debut_erroneo: bool = False
    disolucion_erronea: bool = False
    discos_que_faltan: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)

    @property
    def necesita_revision(self) -> bool:
        """Solo la omisión del fallecimiento manda una pieza a revisión.

        Lo demás (un disco que falta, una fecha mal) es una errata: se avisa y se
        corrige, pero no justifica retener una pieza entera.
        """
        return self.es_trayectoria and self.omite_fallecimiento

    @property
    def hay_erratas(self) -> bool:
        return bool(self.debut_erroneo or self.disolucion_erronea
                    or self.discos_que_faltan)


def menciona_fallecimiento(texto: str) -> bool:
    """¿El texto dice, de alguna forma, que Robe murió?

    Estricto a propósito: «homenaje», «tributo» o «gira de despedida» NO cuentan.
    Un artículo puede ir lleno de despedidas y no haber dicho nunca que murió,
    que es justo lo que pasaba en el post que destapó todo esto.
    """
    return bool(_MENCIONA_MUERTE.search(texto or ""))


def en_perimetro(subject: str, texto: str, entity_slug: str | None = None) -> bool:
    """¿El texto va DE Robe o DE Extremoduro, o solo los menciona?

    Calibrado contra las 352 piezas publicadas, en dos vueltas:

    - Contar menciones en el cuerpo metía 240 piezas, entre ellas las fichas de
      cualquier colaborador: hablan de Robe todo el rato porque tocaron con él.
    - Mirar el título tampoco basta: el de Woody Amores dice «colaborador de
      Robe», y una biografía suya no tiene por qué llevar su obituario.

    Cuando la pieza es una ficha, quien manda es el SLUG de la entidad: dice de
    quién es la página, no a quién cita. Para un post del blog, que no tiene
    entidad, se cae al título — y ahí la exigencia de recorrido hace el resto.
    """
    if entity_slug is not None:
        return entity_slug in robe_facts.PERIMETER_SLUGS
    n_sujeto = _norm(subject)
    return any(k in n_sujeto for k in ("robe", "extremoduro", "roberto iniesta"))


def _titulos_cancion(db) -> set[str]:
    """Títulos de canción normalizados, para saber cuáles colisionan con un disco.

    Sale de la BD, nunca de una lista a mano: «Pedrá», «Agila» o «Deltoya» son a la
    vez disco y canción, y mañana puede haber otro.
    """
    if db is None:
        return set()
    try:
        from sqlalchemy import select

        from app.db.models import Song

        return {_norm(t) for (t,) in db.execute(select(Song.title)) if t}
    except Exception:  # noqa: BLE001 — sin catálogo se calla, no se inventa
        return set()


def discos_citados(cuerpo: str, titulos_catalogo: list[str],
                   titulos_cancion: set[str] | None = None) -> list[str]:
    """Discos que el texto menciona DE VERDAD.

    Dos cosas que no son menciones y se contaban como tales (medidas el
    24-09-2026 sobre el análisis de «De Acero (En Directo)», que sumaba cuatro):

    - El slug de un enlace: `.../extremoduro/deltoya/de-acero` no nombra *Deltoya*.
    - Una canción cuyo título coincide con el de un disco: el texto citaba las
      canciones «Pedrá» y «Standby», y «Pedrá» es además un disco de 1995.

    Cuatro discos es el suelo que marca una pieza como recorrido de trayectoria,
    así que dos falsos bastaban para retener el análisis de una sola canción —
    justo lo que el módulo dice no querer hacer.
    """
    n = _norm(_sin_urls(cuerpo))
    fuera: set[str] = titulos_cancion or set()
    enlazados = _discos_enlazados(cuerpo, [_norm(t) for t in titulos_catalogo])
    out = []
    for t in titulos_catalogo:
        nt = _norm(t)
        if nt not in n:
            continue
        if nt in fuera and nt not in enlazados and not _cita_como_disco(n, nt):
            continue  # en este texto es la canción, no el disco
        out.append(t)
    return out


def es_trayectoria(*, kind: str | None, subject: str, body_md: str,
                   titulos_catalogo: list[str] | None = None,
                   entity_slug: str | None = None,
                   titulos_cancion: set[str] | None = None) -> bool:
    """¿El texto RECORRE una trayectoria, o solo habla de una cosa concreta?

    El análisis de una canción no dispara aunque nombre a Robe diez veces: lo que
    dispara es enumerar obra o encadenar años.
    """
    if not en_perimetro(subject, body_md, entity_slug):
        return False
    cuerpo = body_md or ""
    citados = 0
    if titulos_catalogo:
        citados = len(discos_citados(cuerpo, titulos_catalogo, titulos_cancion))

    # Enumerar obra de verdad es la señal fuerte, y va sola.
    if citados >= 4:
        return True
    # Un encabezado con «legado», «evolución» o «historia» NO basta por sí solo:
    # revisando los 11 marcados salieron un análisis de «Ama, ama, ama», otro de
    # «La ley innata» y una noticia sobre una versión, todos con un titular así y
    # ninguno recorriendo nada. Vale solo si además el texto abarca varios discos.
    return bool(_ENCABEZADO_TRAYECTORIA.search(cuerpo) and citados >= 2)


def discos_no_citados(db, body_md: str, *, minimo_para_exigir: int = 4) -> list[str]:
    """Discos del catálogo que el texto se deja, si es que está enumerando.

    Con menos de `minimo_para_exigir` citados no se dice nada: mencionar dos
    discos no es hacer una discografía, y exigirlo sería ruido. Cuenta con el
    mismo criterio que `es_trayectoria` — si contara distinto, una pieza podría
    quedar retenida por «enumerar» y a la vez no enumerar.
    """
    discos = robe_facts.discography(db)
    if not discos:
        return []
    titulos = [d.title for d in discos]
    citados = set(discos_citados(body_md or "", titulos, _titulos_cancion(db)))
    if len(citados) < minimo_para_exigir:
        return []
    return [f"{d.title} ({d.year})" for d in discos if d.title not in citados]


def afirma_debut_erroneo(texto: str) -> bool:
    """«Debutó en 1994 con Rock Transgresivo»: el debut es de 1990.

    Solo se marca la frase que llama debut a lo que no lo es. Si esa misma frase
    nombra el debut de verdad, está explicando la diferencia, no confundiéndola.
    """
    for frase in _FRASE.findall(texto or ""):
        if _DEBUT.search(frase) and _DEBUT_MAL.search(frase) and not _DEBUT_BIEN.search(frase):
            return True
    return False


def afirma_disolucion_erronea(texto: str) -> bool:
    return bool(_DISOLUCION_2018.search(texto or ""))


def revisar(db, *, kind: str | None, subject: str, body_md: str,
            entity_slug: str | None = None) -> SensitiveReport:
    """Pasada completa sobre una pieza."""
    rep = SensitiveReport()
    titulos = [d.title for d in robe_facts.discography(db)] if db is not None else []
    rep.es_trayectoria = es_trayectoria(
        kind=kind, subject=subject, body_md=body_md, titulos_catalogo=titulos,
        entity_slug=entity_slug, titulos_cancion=_titulos_cancion(db),
    )
    if rep.es_trayectoria and not menciona_fallecimiento(body_md):
        rep.omite_fallecimiento = True
        rep.motivos.append(
            "recorre la trayectoria y no menciona que Robe falleció el "
            f"{robe_facts.DEATH_DATE.isoformat()}"
        )
    if afirma_debut_erroneo(body_md):
        rep.debut_erroneo = True
        rep.motivos.append(
            f"da «Rock Transgresivo» (1994) como debut; el debut es "
            f"«{robe_facts.EXTREMODURO_DEBUT[0]}» ({robe_facts.EXTREMODURO_DEBUT[1]})"
        )
    if afirma_disolucion_erronea(body_md):
        rep.disolucion_erronea = True
        rep.motivos.append(
            "data la disolución en 2018; fue el "
            f"{robe_facts.EXTREMODURO_DISSOLUTION_DATE.isoformat()}"
        )
    if db is not None:
        rep.discos_que_faltan = discos_no_citados(db, body_md)
        if rep.discos_que_faltan:
            rep.motivos.append(
                "enumera discografía y se deja: " + ", ".join(rep.discos_que_faltan)
            )
    return rep
