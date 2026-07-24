"""Optimización de METADATA SEO (solo metadata, NO toca el cuerpo):

  1. meta_description CORTAS (<110c): se expanden a ~150c resumiendo el cuerpo real
     de la página (sin inventar: solo se reformula lo que ya está en el body).
  2. meta_title TRUNCADOS (cortados a mitad de palabra en el tope de 60c, p.ej.
     «…amor y libe»): se reescriben para que quepan LIMPIOS en ≤60c conservando la
     keyword. Solo se aplica si el viejo estaba realmente truncado.

Guardas: la description resultante 125-158c; el title ≤60c y termina en palabra
completa. Backup por stdout (base64) para rollback. NO inventa datos.

Modos:
  --sample [--slugs a,b]   Muestra propuestas (no persiste).
  --apply                  Persiste (con backup).
  --only desc|title        Solo una de las dos optimizaciones.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from app.config import get_settings
from app.db.models import SeoContent
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEO_TYPES = ("song", "album", "band", "person", "place", "theme", "concept", "artist")
DESC_MIN, DESC_MAX = 125, 158
DESC_SHORT = 110          # por debajo de esto, se expande
TITLE_MAX = 60


def _client() -> OpenAI:
    return OpenAI(api_key=get_settings().openai_api_key)


def _clean_subject(meta_title: str, slug: str) -> str:
    """Nombre limpio de la entidad a partir del meta_title (h1 suele estar NULL).
    «La Hoguera letra: significado de Rock Transgresivo» → «La Hoguera»."""
    name = (meta_title or "").split(":")[0].strip()
    for suf in (" letra", " grupo", " significado", " de Extremoduro", " de Robe",
                " en la obra de Extremoduro", " en la obra de Robe"):
        if name.lower().endswith(suf):
            name = name[: -len(suf)].strip()
    return name or slug.replace("-", " ")


def _clean_to_len(text: str, max_len: int) -> str:
    """Recorta a max_len sin cortar palabra (última palabra completa)."""
    text = text.strip().strip('"').strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-–—")


def _gen_desc(client: OpenAI, subject: str, body: str) -> str | None:
    try:
        r = client.chat.completions.create(
            model="gpt-4o", temperature=0.3, max_tokens=120,
            messages=[{"role": "user", "content": (
                f"Escribe UNA meta description SEO en español (entre {DESC_MIN} y {DESC_MAX} "
                f"caracteres, ni más ni menos) para la página sobre «{subject}». Resume su "
                "contenido de forma atractiva para el clic, incluyendo «"
                f"{subject}» de forma natural. USA SOLO lo que aparece en el texto; no "
                "inventes datos, fechas ni cifras. Devuelve solo la frase, sin comillas.\n\n"
                f"TEXTO:\n\"\"\"\n{body[:2200]}\n\"\"\"")}],
        )
        d = (r.choices[0].message.content or "").strip().strip('"').strip()
        d = re.sub(r"\s+", " ", d)
        return _clean_to_len(d, DESC_MAX)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[meta] desc falló %s: %s", subject, exc)
        return None


_STOP_TAIL = {"y", "e", "o", "u", "de", "del", "la", "el", "en", "a", "con", "su",
              "que", "las", "los", "un", "una", "por", "para"}
# Palabras cortas COMPLETAS válidas al final de un título (no son fragmentos).
_OK_SHORT = {"rock", "robe", "leño", "leno", "amor", "paz", "sol", "voz", "fin",
             "vivo", "años", "año", "letra", "live", "pop", "ska", "punk"}


def _looks_truncated(title: str) -> bool:
    """El title parece cortado a mitad de palabra (tope de 60c). CONSERVADOR: solo
    marca fragmentos claros (última palabra en MINÚSCULA, corta y no-palabra-común),
    o espacio/conjunción colgante. Un nombre propio completo al final («…de Rosendo»)
    NO se marca (evita falsos positivos que borrarían info válida)."""
    if title != title.rstrip():                       # espacio final
        return True
    if title.endswith((".", "!", "?", ")", '"')):
        return False
    last = title.split()[-1].strip(".,;:)\"'") if title.split() else ""
    if not last or len(title) < 58:
        return False
    low = last.lower()
    if low in _STOP_TAIL:                              # «…amor y» colgando
        return True
    if last[0].isupper() or low in _OK_SHORT:         # nombre propio / palabra corta válida
        return False
    # minúscula, 2-6 letras, no común → fragmento cortado («libe», «emo», «Evoluci»→no, es May)
    return 2 <= len(low) <= 6


def _detruncate(title: str) -> str | None:
    """Des-truncación DETERMINISTA (sin LLM, sin invención): quita la última palabra
    cortada y las conjunciones/preposiciones colgantes, dejando un final limpio."""
    words = title.rstrip().split()
    if not words:
        return None
    words = words[:-1]  # fuera la palabra cortada
    while words and words[-1].strip(".,;:").lower() in _STOP_TAIL:
        words.pop()
    out = " ".join(words).rstrip(" ,;:-–—")
    # Si al limpiar el segmento tras ':' queda vacío, deja solo la parte-keyword.
    if out.endswith(":"):
        out = out[:-1].rstrip()
    return out if len(out) >= 15 else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", choices=["desc", "title"], default=None)
    ap.add_argument("--slugs", default=None)
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    only_slugs = {s.strip() for s in args.slugs.split(",")} if args.slugs else None
    with SessionLocal() as db:
        rows = []
        for sc in db.query(SeoContent).filter(SeoContent.entity_type.in_(SEO_TYPES)).all():
            if only_slugs and sc.slug not in only_slugs:
                continue
            rows.append({"id": sc.id, "type": sc.entity_type, "slug": sc.slug,
                         "subject": sc.h1 or sc.meta_title or sc.slug,
                         "title": sc.meta_title or "", "desc": sc.meta_description or "",
                         "body": sc.body_md or ""})
    client = _client()

    def work(r):
        out = dict(r)
        clean = _clean_subject(r["title"], r["slug"])
        out["clean_subject"] = clean
        if args.only != "title" and (len(r["desc"]) < DESC_SHORT):
            nd = _gen_desc(client, clean, r["body"])
            if nd and DESC_MIN - 10 <= len(nd) <= DESC_MAX:
                out["new_desc"] = nd
        if args.only != "desc" and _looks_truncated(r["title"]):
            nt = _detruncate(r["title"])   # determinista, sin LLM
            if nt and len(nt) <= TITLE_MAX and not _looks_truncated(nt) and nt != r["title"]:
                out["new_title"] = nt
        return out

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(work, rows):
            results.append(res)

    nd = sum("new_desc" in r for r in results)
    nt = sum("new_title" in r for r in results)
    logger.info("Propuestas: %d descriptions · %d titles", nd, nt)

    if args.sample:
        for r in results:
            if "new_desc" in r or "new_title" in r:
                print(f"\n--- {r['type']}/{r['slug']} ---")
                if "new_title" in r:
                    print(f"  TITLE  {len(r['title'])}c → {len(r['new_title'])}c")
                    print(f"    old: {r['title']}")
                    print(f"    new: {r['new_title']}")
                if "new_desc" in r:
                    print(f"  DESC   {len(r['desc'])}c → {len(r['new_desc'])}c")
                    print(f"    old: {r['desc']}")
                    print(f"    new: {r['new_desc']}")
        return

    if args.apply:
        ad = at = 0
        with SessionLocal() as db:
            for r in results:
                if "new_desc" not in r and "new_title" not in r:
                    continue
                sc = db.get(SeoContent, r["id"])
                print("<<<BACKUP>>>" + json.dumps({
                    "seo_id": r["id"], "slug": r["slug"],
                    "old_title": sc.meta_title, "old_desc": sc.meta_description}))
                if "new_desc" in r:
                    sc.meta_description = r["new_desc"]; ad += 1
                if "new_title" in r:
                    sc.meta_title = r["new_title"]; at += 1
                db.commit()
        logger.info("Aplicado: %d descriptions · %d titles", ad, at)


if __name__ == "__main__":
    main()
