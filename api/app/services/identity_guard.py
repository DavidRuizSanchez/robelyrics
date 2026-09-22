"""¿La foto es de QUIEN decimos que es?

Hermano de `hero_guard`, y NO el mismo: aquel verifica que una imagen sea
TEMÁTICAMENTE relevante para un artículo, y así está documentado. Aquí la
pregunta es de IDENTIDAD, que es lo que falló cuando una noticia sobre la
presidenta de la Junta de Extremadura salió ilustrada con fotos del entrenador
del Manchester City.

LA DISTINCIÓN QUE HAY QUE NO DESHACER: sin una foto de referencia, NO se pregunta
«¿es esta persona X?», sino «¿hay algo en la imagen que CONTRADIGA que es X?».

Un modelo de visión no puede afirmar que una cara es la de una diputada
extremeña a la que no ha visto nunca; si se le pregunta así, dirá que sí a casi
todo y el gate se vuelve decorativo — verde por el motivo equivocado. Lo que sí
puede hacer, y muy bien, es ver un banquillo, un escudo de club, un uniforme o
un rótulo con otro nombre y decir que eso no cuadra con «política española».

Con foto de referencia (la P18 del QID que resolvimos) sí se pregunta por
identidad directa: comparar dos caras es una tarea que el modelo hace bien.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"

_SYS_CONTRADICCION = (
    "Eres un verificador de imágenes de prensa. Te doy la DESCRIPCIÓN de una "
    "persona o entidad y una FOTO que supuestamente la retrata.\n"
    "NO te pregunto si reconoces a quien sale: no puedes saberlo y no debes "
    "adivinarlo. Te pregunto si hay en la imagen algo que CONTRADIGA la "
    "descripción: un contexto de otra profesión (un banquillo, un escudo de "
    "club, un uniforme, un laboratorio, un plató), un rótulo o marca de agua con "
    "otro nombre, o cualquier señal de que la foto es de otra cosa.\n"
    "Ante la duda, NO contradigas: solo señala lo que se ve de verdad.\n"
    'Devuelve JSON: {"contradice": true|false, "motivo": "qué ves y por qué"}'
)

_SYS_MISMA_PERSONA = (
    "Comparas dos fotos y dices si retratan a la MISMA persona. Fíjate en los "
    "rasgos, no en la ropa, la edad o el contexto.\n"
    'Devuelve JSON: {"misma": true|false, "motivo": "en qué te basas"}'
)


@dataclass(frozen=True)
class IdentityVerdict:
    ok: bool
    reason: str
    checked: bool = True  # False si no se pudo mirar (sin clave, sin imagen)

    @property
    def needs_human(self) -> bool:
        """Pasó sin poder mirarla de verdad: que lo vea una persona."""
        return self.ok and not self.checked


def _b64(url: str) -> str | None:
    try:
        from app.services.instagram import imaging

        img = imaging._fetch_image(url)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:  # noqa: BLE001
        logger.info("[identidad] no se pudo leer %s: %s", (url or "")[:70], exc)
        return None


def _preguntar(system: str, texto: str, imagenes: list[str]) -> dict | None:
    try:
        from openai import OpenAI

        contenido: list[dict] = [{"type": "text", "text": texto}]
        contenido += [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
            for b in imagenes
        ]
        resp = OpenAI(api_key=os.environ["OPENAI_API_KEY"]).chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": contenido}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=300,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        logger.info("[identidad] visión falló: %s", exc)
        return None


def verify_identity(
    image_url: str,
    *,
    label: str,
    description: str = "",
    reference_url: str | None = None,
) -> IdentityVerdict:
    """¿Esta foto puede ser de «label», descrito como «description»?"""
    if not image_url:
        return IdentityVerdict(False, "Sin imagen.")
    if not os.environ.get("OPENAI_API_KEY"):
        # Sin clave no se puede mirar. No se bloquea (el filtro determinista del
        # caller ya ha corrido), pero se marca para que lo vea una persona: dar
        # por buena una foto que nadie ha visto es como se publicó la de Pep.
        return IdentityVerdict(True, "Sin OPENAI_API_KEY: no se ha mirado.", checked=False)

    b64 = _b64(image_url)
    if not b64:
        return IdentityVerdict(False, "No se pudo descargar la imagen.")

    if reference_url:
        ref = _b64(reference_url)
        if ref:
            data = _preguntar(
                _SYS_MISMA_PERSONA,
                f"¿Son la misma persona? La primera foto es la candidata; la "
                f"segunda es la de referencia de {label}.",
                [b64, ref],
            )
            if data is None:
                return IdentityVerdict(False, "La verificación de identidad falló.")
            misma = bool(data.get("misma"))
            return IdentityVerdict(
                misma,
                (data.get("motivo") or "").strip()
                or ("Coincide con la foto de referencia." if misma else "No es la misma persona."),
            )

    data = _preguntar(
        _SYS_CONTRADICCION,
        f"La persona o entidad se describe así: «{label}"
        + (f", {description}" if description else "")
        + "». ¿Hay algo en la foto que lo contradiga?",
        [b64],
    )
    if data is None:
        # Fail-safe, como `hero_guard`: no se da por buena una imagen sin verla.
        return IdentityVerdict(False, "La verificación de identidad falló.")

    contradice = bool(data.get("contradice"))
    motivo = (data.get("motivo") or "").strip()
    return IdentityVerdict(
        not contradice,
        motivo or ("La imagen contradice la descripción." if contradice else "Nada la contradice."),
    )
