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


def en_perimetro(subject: str, texto: str) -> bool:
    """¿Va de Robe o de Extremoduro, o solo los menciona de paso?"""
    n_sujeto = _norm(subject)
    if any(k in n_sujeto for k in ("robe", "extremoduro", "roberto iniesta")):
        return True
    # Sin sujeto claro, que el cuerpo insista lo suficiente.
    n = _norm(texto)
    return n.count("extremoduro") + n.count("robe") >= 3


def es_trayectoria(*, kind: str | None, subject: str, body_md: str,
                   titulos_catalogo: list[str] | None = None) -> bool:
    """¿El texto RECORRE una trayectoria, o solo habla de una cosa concreta?

    El análisis de una canción no dispara aunque nombre a Robe diez veces: lo que
    dispara es enumerar obra o encadenar años.
    """
    if not en_perimetro(subject, body_md):
        return False
    cuerpo = body_md or ""
    if _ENCABEZADO_TRAYECTORIA.search(cuerpo):
        return True
    if len(set(_ANYO.findall(cuerpo))) >= 3:
        return True
    if titulos_catalogo:
        n = _norm(cuerpo)
        citados = sum(1 for t in titulos_catalogo if _norm(t) in n)
        if citados >= 3:
            return True
    return False


def discos_no_citados(db, body_md: str, *, minimo_para_exigir: int = 4) -> list[str]:
    """Discos del catálogo que el texto se deja, si es que está enumerando.

    Con menos de `minimo_para_exigir` citados no se dice nada: mencionar dos
    discos no es hacer una discografía, y exigirlo sería ruido.
    """
    discos = robe_facts.discography(db)
    if not discos:
        return []
    n = _norm(body_md or "")
    citados = [d for d in discos if _norm(d.title) in n]
    if len(citados) < minimo_para_exigir:
        return []
    return [f"{d.title} ({d.year})" for d in discos if d not in citados]


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


def revisar(db, *, kind: str | None, subject: str, body_md: str) -> SensitiveReport:
    """Pasada completa sobre una pieza."""
    rep = SensitiveReport()
    titulos = [d.title for d in robe_facts.discography(db)] if db is not None else []
    rep.es_trayectoria = es_trayectoria(
        kind=kind, subject=subject, body_md=body_md, titulos_catalogo=titulos
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
