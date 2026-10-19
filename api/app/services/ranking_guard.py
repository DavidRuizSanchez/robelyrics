"""Que ampliar una página no le cueste lo que ya posiciona.

Criterio de David (19-10-2026): al fundir una propuesta con una página se pueden
tocar headings «para que todo tenga sentido y/o quede mejor optimizado», pero hay
que garantizar que no se pierden los rankings actuales.

Garantizar un ranking no se puede —lo decide Google—, pero sí se puede impedir la
causa que está en nuestra mano: que la página deje de decir lo que la hacía
aparecer. Por eso aquí se mide COBERTURA, con la misma vara que el resto del
circuito SEO (`seo_style.cubre`, con alias de nombres):

  - **Consultas protegidas**: las de la página en GSC con algún clic o en
    posición ≤ 20, con un mínimo de impresiones.
  - Cada una que la página cubre ANTES tiene que seguir cubierta DESPUÉS
    (cuerpo + headings + title/description).
  - Un heading solo se puede renombrar si el nuevo sigue cubriendo todas las
    protegidas que cubría el viejo. Medido sobre el heading y no sobre la página
    entera: el texto de un heading pesa más que el de un párrafo.
  - Lo que se reescribe (la intro) no puede perder cifras ni nombres propios.

Todo determinista, sin red y sin LLM. Lo que no pasa se descarta operación a
operación: un rename malo no tumba una ampliación buena.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import seo_style

PROTEGIDA_MAX_POSICION = 20.0
PROTEGIDA_MIN_IMPRESIONES = 3


@dataclass
class Veredicto:
    ok: bool
    perdidas: list[str] = field(default_factory=list)
    motivo: str = ""


def consultas_protegidas(queries: list[dict]) -> list[dict]:
    """Las consultas GSC de una página que no se pueden perder."""
    out = []
    for q in queries or []:
        imp = int(q.get("impressions") or 0)
        clics = int(q.get("clicks") or 0)
        pos = float(q.get("position") or 100)
        if imp < PROTEGIDA_MIN_IMPRESIONES and not clics:
            continue
        if ((clics > 0 or pos <= PROTEGIDA_MAX_POSICION)
                and seo_style.content_tokens(q.get("query") or "")):
            out.append(q)
    return sorted(out, key=lambda q: (-int(q.get("clicks") or 0),
                                      -int(q.get("impressions") or 0)))


def _plano(texto: str, alias: dict[str, str] | None) -> str:
    return seo_style.expandir_alias(seo_style.flatten(texto or ""), alias)


def cubiertas(texto: str, consultas: list[dict], alias: dict[str, str] | None = None
              ) -> set[str]:
    plano = _plano(texto, alias)
    return {q["query"] for q in consultas if seo_style.cubre(plano, q["query"])}


def pagina(body_md: str, title: str | None, description: str | None) -> str:
    return f"{title or ''}\n{description or ''}\n{body_md or ''}"


def cobertura_conservada(antes: str, despues: str, consultas: list[dict],
                         alias: dict[str, str] | None = None) -> Veredicto:
    """¿La página nueva sigue cubriendo todo lo protegido que cubría la vieja?"""
    perdidas = sorted(cubiertas(antes, consultas, alias) - cubiertas(despues, consultas, alias))
    if perdidas:
        return Veredicto(False, perdidas,
                         "la página deja de cubrir: " + "; ".join(perdidas[:5]))
    return Veredicto(True)


def renombre_permitido(viejo: str, nuevo: str, consultas: list[dict],
                       alias: dict[str, str] | None = None) -> Veredicto:
    """Un heading nuevo tiene que seguir cubriendo lo que cubría el viejo."""
    if not (nuevo or "").strip():
        return Veredicto(False, motivo="heading vacío")
    perdidas = sorted(cubiertas(viejo, consultas, alias) - cubiertas(nuevo, consultas, alias))
    if perdidas:
        return Veredicto(False, perdidas,
                         f"«{viejo}» → «{nuevo}» dejaría de cubrir: " + "; ".join(perdidas[:4]))
    return Veredicto(True)


def datos_perdidos(viejo: str, nuevo: str) -> list[str]:
    """Cifras y nombres propios del texto viejo que el nuevo ya no dice.

    Es `verify_no_invention` al revés: allí lo nuevo no puede traer datos de fuera,
    aquí lo reescrito no puede soltar datos que tenía.
    """
    return seo_style.verify_no_invention(viejo, seo_style.tokens_permitidos(nuevo))
