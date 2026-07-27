"""Gate de RELEVANCIA de la imagen hero: garantiza que la foto de un post muestre
de verdad a su sujeto antes de publicarse.

Hasta ahora la imagen se elegía por ranking del buscador + hash del título, sin
que nada "viera" la foto: por eso un post de Rosendo acabó con un óleo de una
mujer y el crédito de Robe. Este módulo mira la imagen y decide.

Dos capas (espejo de `lyric_guard`/`fact_check`):
  - **Confianza por fuente:** el arte editorial propio (generado DEL sujeto) es
    on-topic por construcción → pasa sin visión (coste 0).
  - **Visión (backstop real):** para fotos web/Wikimedia/entidad, se descarga la
    imagen y se le pregunta a gpt-4o si muestra al sujeto o algo directamente
    relacionado. Fail-safe: si falla la descarga o el modelo dice que no, el
    veredicto es NEGATIVO y el caller degrada a arte IA propio (nunca publica una
    imagen sin verificar).

Coste acotado: la generación de heros es de pocos posts/semana. Si no hay
`OPENAI_API_KEY` o el gate está desactivado (`HERO_VISION_GATE=0`), NO se puede
ver la imagen: se deja pasar (ok=True) con aviso, para no romper entornos sin
clave. En producción, con clave, el gate está activo.
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

_SYS = (
    "Eres un editor gráfico de Entre Interiores, un sitio sobre Robe y Extremoduro "
    "(rock urbano español). Te doy el SUJETO de un artículo y una IMAGEN candidata "
    "para ilustrarlo. Decides si la imagen es APROPIADA temáticamente.\n"
    "NO tienes que confirmar la IDENTIDAD exacta de la persona (no eres un sistema "
    "de reconocimiento facial): una foto de un músico tocando o cantando en un "
    "concierto ES apropiada para un artículo sobre un músico o una banda, aunque no "
    "puedas asegurar quién es. Acepta también carátulas de disco, instrumentos, "
    "público de concierto, o un lugar/recinto pertinente.\n"
    "RECHAZA SOLO si la imagen es CLARAMENTE ajena al tema: una pintura u obra de "
    "arte sin relación (p.ej. un retrato clásico), un paisaje o edificio sin "
    "conexión, un objeto/animal/comida fuera de lugar, un logo o marca distinta, o "
    "una persona que es EVIDENTEMENTE otro personaje conocido y distinto del sujeto. "
    "Ante la duda con una imagen plausiblemente musical/on-topic, ACEPTA. "
    "Devuelve SOLO JSON: "
    '{"relevant": bool, "describes": "2-4 palabras de lo que se ve", '
    '"reason": "motivo breve en español"}.'
)


@dataclass
class HeroVerdict:
    ok: bool
    reason: str
    describes: str | None = None


def _gate_enabled() -> bool:
    return os.environ.get("HERO_VISION_GATE", "1").strip().lower() not in ("0", "false", "")


def _is_trusted(hero: dict) -> bool:
    """Fuentes on-topic por construcción que no necesitan visión: nuestro arte
    editorial IA (generado DEL sujeto) y las portadas propias de disco."""
    attr = (hero.get("attribution") or "")
    if "Entre Interiores" in attr or (hero.get("license") or "").lower() == "propio":
        return True
    if attr.startswith("Portada de") or attr.startswith("Arte generado"):
        return True
    return False


def _entity_names(entities: list[dict] | None) -> str:
    names = []
    for e in entities or []:
        n = (e.get("label") or e.get("name") or "").strip()
        if n and n not in names:
            names.append(n)
    return ", ".join(names[:8])


def _vision_relevance(url: str, subject: str, entities: list[dict] | None) -> HeroVerdict:
    """Descarga la imagen y pregunta a gpt-4o si es relevante para el sujeto."""
    if not os.environ.get("OPENAI_API_KEY"):
        # Sin clave no podemos ver la imagen: no bloqueamos (entorno sin LLM).
        return HeroVerdict(True, "sin OPENAI_API_KEY: gate de visión omitido", None)
    try:
        from app.services.instagram import imaging

        img = imaging._fetch_image(url)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:  # noqa: BLE001
        return HeroVerdict(False, f"no se pudo descargar/leer la imagen: {exc}", None)

    ents = _entity_names(entities)
    user_text = (
        f"SUJETO del artículo: {subject or '(sin especificar)'}.\n"
        f"Entidades citadas: {ents or '(ninguna)'}.\n"
        "¿La imagen es relevante para ilustrar este artículo?"
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=300,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        # Fail-safe: si el modelo falla, no damos por buena una imagen sin ver.
        return HeroVerdict(False, f"visión falló: {exc}", None)

    relevant = bool(data.get("relevant"))
    reason = (data.get("reason") or "").strip() or ("relevante" if relevant else "no relevante")
    return HeroVerdict(relevant, reason, (data.get("describes") or "").strip() or None)


def verify_hero(
    hero: dict | None,
    *,
    subject: str,
    entities: list[dict] | None = None,
    trusted: bool | None = None,
) -> HeroVerdict:
    """Decide si `hero` (paquete {url,alt,attribution,license,source}) es una
    imagen RELEVANTE para un post sobre `subject`.

    - `hero` None / sin url → ok=True (un post sin imagen es válido; no hay nada
      incorrecto que bloquear).
    - Fuente de confianza (arte IA propio / portada) → ok=True sin visión.
    - Resto → visión gpt-4o. Fail-safe a ok=False si no se puede verificar.

    `trusted`: fuérzalo si el caller conoce el origen; si es None se infiere del
    paquete. `HERO_VISION_GATE=0` desactiva la visión (ok=True con aviso).
    """
    if not hero or not hero.get("url"):
        return HeroVerdict(True, "sin imagen", None)
    if trusted is None:
        trusted = _is_trusted(hero)
    if trusted:
        return HeroVerdict(True, "fuente de confianza (arte propio/portada)", None)
    if not _gate_enabled():
        return HeroVerdict(True, "gate de visión desactivado (HERO_VISION_GATE=0)", None)
    return _vision_relevance(hero["url"], subject, entities)
