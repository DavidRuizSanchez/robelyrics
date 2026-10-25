"""¿Habla de verdad quien el título dice que habla? Se mira DESPUÉS de transcribir.

`corpus_trust.clasificar` solo ve título, descripción y canal. Un nivel A dice
«habla Robe (o Uoho, o Leiva) en un medio reconocido», pero el título no lo
garantiza: «Entrevista a Inconscientes (Iñaki "Uoho" y Jon Calvo)» es Uoho, sí,
hablando de otra banda; y desde que Robe murió casi todos los títulos le nombran
como TEMA. Lo que entra como voz de Robe acaba en `robe_voice_v1`, que el
consultorio usa para hablar COMO él.

Este juez lee la transcripción y responde dos cosas: si la voz habla en primera
persona en ese vídeo y si lo que dice trata de Robe o de Extremoduro. Solo puede
BAJAR de nivel: si no, o si duda, el vídeo entra como `media_report` (fondo, no
voz). `about_robe` no vale como destino porque está en `embed_robe_voice.VOICE_KINDS`.

Ante la duda, NO: atribuir a Robe las palabras de un locutor es peor que perder
una entrevista suya, que sigue en el corpus como fondo. Si el juez no se puede
consultar (sin clave, OpenAI caído) también baja, y el motivo lo dice.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DESTINO_SI_NO_PASA = "media_report"

# Tres ventanas en vez del arranque: los primeros minutos suelen ser del
# presentador («bienvenidos a…»), y con ellos solo el juez diría que no habla.
VENTANAS = (0.10, 0.45, 0.75)
CHARS_POR_VENTANA = 1000
# Y además, los trozos donde sale Robe o Extremoduro. Con solo las ventanas fijas,
# la entrevista de Uoho en ABC («me cuesta mucho hablar de Robe en pasado») salía
# «no se sabe si habla de Robe» porque sus 3 menciones caían fuera (25-10-2026).
# Con las erratas de Whisper que se han visto: «extremo duro», «Robben», «te roben».
_MENCION = re.compile(r"\b(robe|roben|robben|roberto|iniesta|extremo ?duro)\b", re.IGNORECASE)
MENCIONES = 3
CHARS_POR_MENCION = 500

_SYS = """Eres un verificador de un archivo sobre Robe Iniesta y Extremoduro.
Te paso fragmentos de la transcripción AUTOMÁTICA de un vídeo de YouTube (trae
erratas: «Robben y Niesta» es Robe Iniesta). Responde SOLO con JSON:
{"habla": "si"|"no"|"duda", "de_robe": "si"|"no"|"duda", "motivo": "<una frase>"}

- habla: ¿{voz} habla en primera persona EN ESTE VÍDEO (es la persona
  entrevistada, da la charla, responde preguntas)? «no» si solo se habla DE
  {voz}: un locutor, un narrador, un homenaje, un fan o un periodista contándolo.
- de_robe: ¿lo que dice {voz} trata, aunque sea en parte, de Robe o de Extremoduro?
- Si no se puede saber con lo que hay, «duda». No adivines."""


@dataclass(frozen=True)
class Juicio:
    habla: str            # si | no | duda
    de_robe: str          # si | no | duda
    motivo: str

    @property
    def pasa(self) -> bool:
        return self.habla == "si" and self.de_robe == "si"


def extracto(texto: str) -> str:
    t = (texto or "").strip()
    if len(t) <= CHARS_POR_VENTANA * len(VENTANAS):
        return t
    tramos = [(int(len(t) * p), int(len(t) * p) + CHARS_POR_VENTANA) for p in VENTANAS]
    for m in list(_MENCION.finditer(t))[:MENCIONES * 4]:
        if sum(1 for ini, fin in tramos if ini <= m.start() < fin):
            continue  # ya la ve el juez
        mitad = CHARS_POR_MENCION // 2
        tramos.append((max(0, m.start() - mitad), m.start() + mitad))
        if len(tramos) == len(VENTANAS) + MENCIONES:
            break
    return "\n[…]\n".join(t[ini:fin] for ini, fin in sorted(tramos))


def _llm_por_defecto(system: str, user: str) -> dict:
    from app.services.news_research import _json

    return _json(system, user, max_tokens=120, temperature=0)


def juzgar(voz: str, titulo: str | None, canal: str | None, texto: str,
           llm: Callable[[str, str], dict] | None = None) -> Juicio:
    if not (texto or "").strip():
        return Juicio("duda", "duda", "sin transcripción")
    user = (f"VÍDEO: {titulo or '—'}\nCANAL: {canal or '—'}\nVOZ: {voz}\n\n"
            f'TRANSCRIPCIÓN (fragmentos):\n"""\n{extracto(texto)}\n"""')
    try:
        data = (llm or _llm_por_defecto)(_SYS.replace("{voz}", voz), user) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[corpus_judge] no se pudo consultar al juez: %s", exc)
        data = {}
    if not data:
        return Juicio("duda", "duda", "no se ha podido consultar al juez")
    norm = {"si": "si", "sí": "si", "no": "no"}
    return Juicio(norm.get(str(data.get("habla", "")).lower(), "duda"),
                  norm.get(str(data.get("de_robe", "")).lower(), "duda"),
                  str(data.get("motivo") or "").strip()[:300])


def voz_principal(kind: str, voces: list[str] | None, nombres: dict[str, str]) -> str | None:
    """La voz cuyo testimonio se va a guardar, igual que la elige `clasificar`."""
    voces = list(voces or [])
    if kind == "robe_interview":
        return nombres.get("robe-iniesta", "Robe")
    otra = next((v for v in voces if v != "robe-iniesta"), None)
    return nombres.get(otra, otra) if otra else None


def revisar(db, row, texto: str, llm: Callable[[str, str], dict] | None = None) -> Juicio | None:
    """Juzga un nivel A recién transcrito y, si no pasa, lo baja. Devuelve el
    juicio, o None si no había nada que juzgar (B, C, o filas sin nivel del
    inventario curado a mano)."""
    if getattr(row, "nivel", None) != "A":
        return None
    from app.services.corpus_trust import cargar_voces

    nombres = {v.slug: v.nombre for v in cargar_voces(db)}
    voz = voz_principal(row.kind, row.voces, nombres)
    if voz is None:
        juicio = Juicio("duda", "duda", "nivel A sin voz principal")
    else:
        juicio = juzgar(voz, row.title, row.channel, texto, llm=llm)
    veredicto = "pasa" if juicio.pasa else "no pasa"
    nota = (f"juez tras transcribir ({voz or '—'}): {veredicto} · habla={juicio.habla} · "
            f"de Robe={juicio.de_robe}" + (f" · {juicio.motivo}" if juicio.motivo else ""))
    row.motivos = [*(row.motivos or []), nota]
    if not juicio.pasa:
        row.motivos = [*row.motivos, f"baja de A ({row.kind}) a B ({DESTINO_SI_NO_PASA}): "
                                     "entra como fondo, no como voz"]
        row.kind = DESTINO_SI_NO_PASA
        row.nivel = "B"
    return juicio
