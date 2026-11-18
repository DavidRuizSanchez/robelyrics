"""Headings humanos en páginas ya publicadas (criterio de David, 10-11-2026).

Reescribe SOLO las líneas `## ` de una página: el resto del cuerpo queda idéntico
byte a byte, y se comprueba. Cada heading nuevo pasa dos guardas:

- `seo_style.heading_verdict`: el nombre del protagonista como mucho en uno, nada
  de molde «Sujeto: tema».
- `ranking_guard.renombre_permitido` medido SIN el sujeto: ningún heading deja de
  cubrir una búsqueda protegida de GSC (clics o posición ≤ 20). Si uno la perdería,
  ese se queda como estaba.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services import ranking_guard, seo_style

_H2 = re.compile(r"^(##)(?!#)[ \t]*(.+?)[ \t]*$", re.M)


def extraer(body_md: str) -> list[str]:
    return [m.group(2) for m in _H2.finditer(body_md or "")]


def reemplazar(body_md: str, nuevos: list[str]) -> str:
    """Cambia los H2 en orden; el resto del texto no se toca."""
    it = iter(nuevos)
    return _H2.sub(lambda m: f"## {next(it)}", body_md)


def solo_cambian_headings(antes: str, despues: str) -> bool:
    """Independiente de la regex de arriba: línea a línea, todo lo que no sea un H2
    tiene que ser idéntico, y el número de líneas también."""
    la, ld = (antes or "").split("\n"), (despues or "").split("\n")
    if len(la) != len(ld):
        return False
    es_h2 = lambda s: s.startswith("## ")  # noqa: E731
    return all((es_h2(a) and es_h2(d)) or a == d for a, d in zip(la, ld, strict=True))


def reescribir_headings(client, subject: str, headings: list[str], resumenes: list[str],
                        *, motivos: list[str] | None = None) -> list[str] | None:
    """Pide al modelo los mismos headings, humanos. None si no devuelve lo pedido."""
    from scripts.seo.generate_deep import _chat

    lista = "\n".join(f"{i + 1}. {h}  — trata: {r[:220]}" for i, (h, r) in
                      enumerate(zip(headings, resumenes, strict=False)))
    user = (
        f"Página sobre «{subject}». Reescribe estos headings H2 para que suenen humanos y "
        "naturales, sin cambiar de qué va cada sección ni su orden.\n"
        f"{seo_style.PROMPT_HEADING_RULES}\nEjemplos (la FORMA, no la frase):\n"
        f"{seo_style.EJEMPLOS_ORO_HEADINGS}\n"
        + (f"Lo que falla ahora: {'; '.join(motivos)}\n" if motivos else "")
        + f"OBLIGATORIO: «{subject}» aparece, con naturalidad, en UNO de los headings (dos "
        "como mucho), por ejemplo en el que presenta quién o qué es; en los demás, no. "
        "Nunca como «" + subject + ": …».\n"
        + f"HEADINGS:\n{lista}\n"
        f'Devuelve JSON {{"headings": [exactamente {len(headings)} textos, en el mismo orden]}}.'
    )
    try:
        data = _chat(client, user, max_tokens=700, temp=0.3)
    except Exception:  # noqa: BLE001
        return None
    nuevos = [str(h).strip().strip("#").strip() for h in (data.get("headings") or [])]
    if len(nuevos) != len(headings) or not all(nuevos):
        return None
    return nuevos


@dataclass
class Propuesta:
    antes: list[str]
    despues: list[str]
    mantenidos: list[str] = field(default_factory=list)   # «heading: motivo»
    veredicto_antes: list[str] = field(default_factory=list)
    veredicto_despues: list[str] = field(default_factory=list)
    veredicto_despues_bloquea: bool = False
    avisos_despues: list[str] = field(default_factory=list)
    body_nuevo: str = ""

    @property
    def cambia(self) -> bool:
        return self.antes != self.despues

    @property
    def aplicable(self) -> bool:
        """Se aplica si mejora algo. Si queda un bloqueo, solo vale cuando lo causa un
        heading que se ha conservado a propósito (posicionamiento o invención): las
        mejoras del resto no tienen por qué esperar."""
        if not self.cambia:
            return False
        if not self.veredicto_despues_bloquea:
            return True
        conservados = {m.split(": ", 1)[0] for m in self.mantenidos}
        return all(any(h in mot for h in conservados) for mot in self.veredicto_despues
                   if mot not in self.avisos_despues)


def _resumenes(body_md: str) -> list[str]:
    trozos = _H2.split(body_md or "")
    # split con 2 grupos: [intro, '##', h1, cuerpo1, '##', h2, cuerpo2, ...]
    return [re.sub(r"\s+", " ", trozos[i + 2]).strip() for i in range(1, len(trozos) - 1, 3)]


def proponer(client, *, body_md: str, subject: str, protegidas: list[dict],
             alias: dict[str, str] | None = None, comun: bool = False) -> Propuesta:
    """`comun`: el sujeto es un nombre común (temas y conceptos), ver `heading_verdict`."""
    def veredicto(hs: list[str]) -> seo_style.MetaVerdict:
        return seo_style.heading_verdict(hs, subject=subject, comun=comun)

    antes = extraer(body_md)
    va = veredicto(antes)
    prop = Propuesta(antes=antes, despues=list(antes), veredicto_antes=va.motivos + va.avisos)
    if not antes or (va.ok and not va.avisos):
        prop.body_nuevo = body_md
        return prop
    secciones = _resumenes(body_md)
    nuevos = reescribir_headings(client, subject, antes, secciones,
                                 motivos=va.motivos + va.avisos) or antes
    vn = veredicto(nuevos)
    if not vn.ok:
        # Segunda vuelta con lo que sigue fallando delante (10-11-2026: en 118 de 134
        # páginas el modelo quitó el nombre de todos los headings a la primera).
        nuevos = reescribir_headings(client, subject, nuevos, secciones,
                                     motivos=vn.motivos) or nuevos
    from scripts.seo.merge_deep import terminos_del_sujeto

    sujeto = terminos_del_sujeto(subject, alias)
    finales, mantenidos, faltan = _filtrar(antes, nuevos, secciones, subject, sujeto,
                                           protegidas, alias)
    if faltan:
        # Tercera vuelta (11-11-2026): un heading que se conserva porque el nuevo soltaba
        # una búsqueda protegida no se queda feo por eso. Se pide otra vez CON esas
        # palabras dentro («Qué significa «Guerrero»» sigue cubriendo «significado»).
        # Solo cambian esas posiciones; lo ya bueno no se vuelve a tocar.
        motivos = [f"el heading {i + 1} («{antes[i]}») tiene que seguir diciendo: "
                   f"{', '.join(pal)}" for i, pal in sorted(faltan.items())]
        otra = reescribir_headings(client, subject, finales, secciones,
                                   motivos=motivos + veredicto(finales).motivos)
        if otra:
            mezcla = [otra[i] if i in faltan else h for i, h in enumerate(finales)]
            f2, m2, _ = _filtrar(antes, mezcla, secciones, subject, sujeto, protegidas, alias)
            if len(veredicto(f2).motivos) <= len(veredicto(finales).motivos):
                finales, mantenidos = f2, m2
    prop.mantenidos = mantenidos
    vd = veredicto(finales)
    prop.despues = finales
    prop.veredicto_despues = vd.motivos + vd.avisos
    prop.veredicto_despues_bloquea = not vd.ok
    prop.avisos_despues = list(vd.avisos)
    prop.body_nuevo = reemplazar(body_md, finales)
    assert solo_cambian_headings(body_md, prop.body_nuevo)
    return prop


def _filtrar(antes, nuevos, secciones, subject, sujeto, protegidas, alias
             ) -> tuple[list[str], list[str], dict[int, list[str]]]:
    """Cada heading nuevo pasa la no-invención y el posicionamiento; si no, se queda el
    viejo. Devuelve también, por posición, las palabras de búsqueda que faltaban."""
    finales: list[str] = []
    mantenidos: list[str] = []
    faltan: dict[int, list[str]] = {}
    for i, (viejo, nuevo) in enumerate(zip(antes, nuevos, strict=True)):
        if nuevo == viejo:
            finales.append(viejo)
            continue
        # Un heading no puede afirmar lo que su sección no dice (10-11-2026: «Estudios
        # de grabación en Madrid» → «La grabación del debut en los estudios M-20»).
        permitidos = seo_style.tokens_permitidos(secciones[i] if i < len(secciones) else "",
                                                 viejo, subject)
        inventado = seo_style.verify_no_invention(nuevo, permitidos)
        if inventado:
            finales.append(viejo)
            mantenidos.append(f"{viejo}: el nuevo metía {', '.join(inventado[:3])}, "
                              "que su sección no dice")
            continue
        r = ranking_guard.renombre_permitido(viejo, nuevo, protegidas, alias, sujeto=sujeto)
        if r.ok:
            finales.append(nuevo)
        else:
            finales.append(viejo)
            mantenidos.append(f"{viejo}: {r.motivo}")
            faltan[i] = list(r.perdidas)
    return finales, mantenidos, faltan
