"""Limpia las transcripciones de entrevistas (subtítulos automáticos de YouTube)
con gpt-4o: las deja legibles y FIELES, con los tacos literales, reconstruyendo
lo garbled desde el contexto y OMITIENDO lo ininteligible (sin inventar).

Lee data/robe_interview_transcripts.json (content_clean = subtítulos en bruto),
limpia cada uno y escribe el JSON limpio a --out (por defecto /tmp). Luego se
re-importa + re-vectoriza robe_voice_v1.

Uso:
    docker compose exec api python -m scripts.research.clean_interview_transcripts --out /tmp/clean.json
"""
from __future__ import annotations

import argparse
import json

from openai import OpenAI

from app.config import get_settings
from scripts.research.common import DATA_DIR, log

MODEL = "gpt-4o"

_SYS = """\
Esto son SUBTÍTULOS AUTOMÁTICOS de YouTube de una entrevista (a Robe Iniesta,
de Extremoduro, o sobre él). Vienen MAL: sin puntuación, con errores de
transcripción, palabras pegadas o cortadas, y tacos CENSURADOS como "[ __ ]".

Devuelve una versión LIMPIA, LEGIBLE y FIEL a lo que se dijo:
- Restaura puntuación, mayúsculas y separación en frases y párrafos.
- Reconstruye palabras claramente mal transcritas o cortadas usando el contexto
  (p.ej. "yon" -> "yonki", "rotad imo" -> "rebotado", "caguas" -> "cague").
- DES-CENSURA los tacos al término real cuando el contexto lo deje claro:
  "[ __ ]" -> "cojones" / "hostia" / "mierda" / "yonki" / "puta", etc. Robe habla
  con tacos: déjalos literales, NO los suavices ni los censures.
- Si un fragmento es ININTELIGIBLE y no puedes reconstruirlo con sentido,
  OMÍTELO entero. No inventes contenido ni rellenes. Mejor menos y claro.
- NO resumas, NO añadas nada que no esté: solo limpia y transcribe fielmente.
- PROHIBIDO el em-dash. Devuelve SOLO el texto limpio, en párrafos."""


def clean_one(client: OpenAI, text: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": text[:24000]},
        ],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/robe_interview_transcripts.clean.json")
    ap.add_argument("--min-chars", type=int, default=200)
    args = ap.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    path = DATA_DIR / "robe_interview_transcripts.json"
    rows = json.loads(path.read_text(encoding="utf-8")) or []
    out = []
    for r in rows:
        raw = (r.get("content_clean") or "").strip()
        if len(raw) < args.min_chars:
            continue
        cleaned = clean_one(client, raw)
        if len(cleaned) < args.min_chars:
            log(f"  ! {(r.get('title') or '')[:50]}: limpieza demasiado corta, omitida", "warn")
            continue
        nr = dict(r)
        nr["content_clean"] = cleaned
        out.append(nr)
        log(f"  ✓ {(r.get('title') or '')[:50]} ({len(raw)}→{len(cleaned)} chars)", "ok")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"Limpias: {len(out)}/{len(rows)} → {args.out}", "ok")


if __name__ == "__main__":
    main()
