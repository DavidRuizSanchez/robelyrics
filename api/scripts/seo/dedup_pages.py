"""De-duplicación de páginas de entidad: quita la REDUNDANCIA entre secciones
(el fallo dominante de la auditoría) SIN perder información ni hacer gutting.

La generación sección-a-sección de las fichas repite ideas/metáforas/hechos entre
H2. Este pase reescribe el cuerpo eliminando SOLO la repetición: cada hecho, verso
citado, nombre propio y enlace interno aparece UNA vez, en su mejor sitio. No añade
nada. Guardas duras (data-integrity + anti-gutting):

  1. Pérdida de info CERO: todos los versos citados («…»/"…"), los enlaces markdown
     y los nombres de entidad del original DEBEN seguir en el resultado. Si falta
     uno → se descarta el dedup (no-op, se conserva el original).
  2. No-gutting: len(dedup) >= 55% del original y >= 1500 chars.
  3. Solo mejora: el rigor del dedup no puede bajar respecto al original.

Objetivo: páginas LARGAS-porque-redundantes (las thin cortas no se tocan: no hay
qué de-duplicar). Excluye libros (curados a mano).

Modos:
  --sample --slugs a,b,c   Muestra before/after (no persiste).
  --apply                  Aplica con BACKUP por stdout (base64) para rollback.
  --apply --entity-type song

SIEMPRE --sample primero.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from openai import OpenAI

from app.config import get_settings
from app.db.models import SeoContent
from app.db.session import SessionLocal
from app.services.editorial_review import review as editorial_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEO_TYPES = ("song", "album", "band", "person", "place", "theme", "concept", "artist")
MIN_CHARS_TO_DEDUP = 2800   # por debajo no hay redundancia que quitar (thin, se deja)
FLOOR_RATIO = 0.55          # el dedup no puede bajar de este % del original
FLOOR_ABS = 1500

_VERSE = re.compile(r"[«\"]([^«»\"]{12,})[»\"]")           # versos citados (>=12 chars)
_LINK = re.compile(r"\]\((https?://[^)]+)\)")               # URLs de enlaces markdown
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")                    # años (fechas concretas)
_H2 = re.compile(r"^##\s+(.+)$", re.M)

_PROMPT = (
    "Tienes una ficha en markdown sobre «{subject}». Tiene REDUNDANCIA: repite las "
    "mismas ideas, metáforas, hechos o versos entre secciones distintas.\n\n"
    "Reescríbela eliminando SOLO la repetición, con estas reglas ESTRICTAS:\n"
    "- Cada HECHO, VERSO citado (entre comillas), NOMBRE PROPIO y ENLACE markdown "
    "[texto](url) debe aparecer EXACTAMENTE UNA vez, en la sección donde mejor encaje. "
    "NO elimines ninguno: solo quita sus repeticiones.\n"
    "- NO añadas información nueva, ni relleno, ni conclusiones vacías.\n"
    "- Mantén el markdown y los encabezados H2 (##). Puedes FUSIONAR dos secciones si "
    "dicen lo mismo, pero conserva todo el contenido único.\n"
    "- Conserva las comillas de los versos textuales EXACTAS (no las cambies).\n"
    "- Devuelve SOLO el markdown resultante, sin comentarios.\n\n"
    "FICHA:\n\"\"\"\n{body}\n\"\"\""
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _facts(body: str) -> tuple[set[str], set[str], set[str]]:
    """(versos_normalizados, urls, años) del texto — para el chequeo bidireccional:
    ni se pierde nada del original ni se AÑADE nada nuevo (dedup = solo quitar
    repetición, jamás inventar datos)."""
    verses = {_norm(m) for m in _VERSE.findall(body) if len(m.strip()) >= 12}
    links = set(_LINK.findall(body))
    years = set(_YEAR.findall(body))
    return verses, links, years


def _dedup_one(client: OpenAI, subject: str, body: str) -> str | None:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": _PROMPT.format(subject=subject, body=body)}],
            temperature=0.2, max_tokens=3000,
        )
        out = (resp.choices[0].message.content or "").strip()
        # Quita fences ```markdown … ``` si el modelo los mete.
        out = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", out).strip()
        return out or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[dedup] LLM falló para %s: %s", subject, exc)
        return None


def _evaluate(subject: str, kind: str, original: str, deduped: str) -> dict:
    """Aplica las guardas. Devuelve dict con ok + motivo + métricas."""
    ov, ol, oy = _facts(original)
    dv, dl, dy = _facts(deduped)
    missing_verses = [v for v in ov if v not in dv]
    missing_links = [u for u in ol if u not in dl]
    # AÑADIDOS (dedup solo puede quitar repetición, jamás inventar): versos/enlaces/años
    # que aparecen en el resultado pero NO en el original.
    added_verses = [v for v in dv if v not in ov]
    added_links = [u for u in dl if u not in ol]
    added_years = [y for y in dy if y not in oy]
    ratio = len(deduped) / max(len(original), 1)
    res = {"before_len": len(original), "after_len": len(deduped),
           "ratio": round(ratio, 2), "missing_verses": len(missing_verses),
           "missing_links": len(missing_links)}
    if missing_verses or missing_links:
        res["ok"] = False
        res["reason"] = f"pérdida de info: -{len(missing_verses)} versos, -{len(missing_links)} enlaces"
        return res
    if added_verses or added_links or added_years:
        res["ok"] = False
        res["reason"] = (f"AÑADE datos (no es de-dup puro): +{len(added_verses)} versos, "
                         f"+{len(added_links)} enlaces, +{len(added_years)} años {added_years[:4]}")
        return res
    if len(deduped) < FLOOR_ABS or ratio < FLOOR_RATIO:
        res["ok"] = False
        res["reason"] = f"gutting (ratio {ratio:.2f} < {FLOOR_RATIO})"
        return res
    v_before = editorial_review(original, kind=kind, subject=subject)
    v_after = editorial_review(deduped, kind=kind, subject=subject)
    res["score_before"] = v_before.score
    res["score_after"] = v_after.score
    res["verdict_after"] = v_after.verdict
    if v_after.score < v_before.score:
        res["ok"] = False
        res["reason"] = f"el rigor baja ({v_before.score}→{v_after.score})"
        return res
    # Merece aplicarse solo si hay cambio REAL: sube el rigor, o acorta ≥8% (quitó
    # redundancia de verdad). Un rewrite de igual longitud y score no aporta.
    improved = v_after.score > v_before.score
    shortened = ratio <= 0.92
    if not (improved or shortened):
        res["ok"] = False
        res["reason"] = f"sin cambio real (ratio {ratio:.2f}, rigor {v_before.score}→{v_after.score})"
        return res
    res["ok"] = True
    res["reason"] = f"OK ({v_before.score}→{v_after.score}, {len(original)}→{len(deduped)}c)"
    return res


def _targets(db, entity_type, slugs):
    q = db.query(SeoContent)
    if entity_type:
        q = q.filter(SeoContent.entity_type == entity_type)
    else:
        q = q.filter(SeoContent.entity_type.in_(SEO_TYPES))
    rows = []
    only = {s.strip() for s in slugs.split(",")} if slugs else None
    vistos: dict[str, int] = {}
    for sc in q.all():
        if only and sc.slug not in only:
            continue
        if only:
            # Un slug de cancion se repite entre discos: si pides uno y salen
            # dos fichas, no estas de-duplicando lo que crees.
            vistos[sc.slug] = vistos.get(sc.slug, 0) + 1
            if vistos[sc.slug] > 1:
                logger.warning(
                    "«%s» corresponde a mas de una ficha (%s#%s); acota con "
                    "--entity-type", sc.slug, sc.entity_type, sc.entity_id,
                )
        body = sc.body_md or ""
        if not only and len(body) < MIN_CHARS_TO_DEDUP:
            continue  # thin: nada que de-duplicar (salvo que se pida explícito por slug)
        rows.append(sc)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--entity-type", default=None)
    ap.add_argument("--slugs", default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    client = OpenAI(api_key=get_settings().openai_api_key)
    with SessionLocal() as db:
        targets = _targets(db, args.entity_type, args.slugs)
        rows = [{"id": sc.id, "type": sc.entity_type, "slug": sc.slug,
                 "subject": sc.h1 or sc.meta_title or sc.slug, "body": sc.body_md}
                for sc in targets]
    logger.info("Objetivos: %d", len(rows))

    def work(r):
        deduped = _dedup_one(client, r["subject"], r["body"])
        if not deduped:
            return {**r, "ok": False, "reason": "sin salida LLM"}
        ev = _evaluate(r["subject"], r["type"], r["body"], deduped)
        return {**r, "deduped": deduped, **ev}

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(work, rows):
            results.append(res)

    if args.sample:
        for r in results:
            print(f"\n===== {r['type']}/{r['slug']} — {r.get('reason')} =====")
            if r.get("deduped"):
                print(f"[{r['before_len']}→{r['after_len']}c · ratio {r.get('ratio')} · "
                      f"rigor {r.get('score_before')}→{r.get('score_after')} · aplicaría={r['ok']}]")
                print("----- DEDUP -----")
                print(r["deduped"])
        return

    if args.apply:
        applied = skipped = 0
        with SessionLocal() as db:
            for r in results:
                if not r.get("ok"):
                    logger.info("  %s/%s: no aplica (%s)", r["type"], r["slug"], r.get("reason"))
                    skipped += 1
                    continue
                print("<<<BACKUP>>>" + json.dumps({
                    "seo_id": r["id"], "slug": r["slug"], "entity_type": r["type"],
                    "old_body_b64": base64.b64encode(r["body"].encode()).decode()}))
                sc = db.get(SeoContent, r["id"])
                sc.body_md = r["deduped"]
                sc.generated_at = datetime.now(timezone.utc)
                # Marca de procedencia, no un historial: anteponer el prefijo cada
                # vez daba «dedup-dedup-dedup-dedup-dedup-gpt-4o» y a la quinta
                # pasada reventaba el VARCHAR(32) con StringDataRightTruncation,
                # abortando el lote entero a mitad.
                previo = (sc.generated_by or "").removeprefix("dedup-")
                sc.generated_by = f"dedup-{previo}"[:32]
                db.commit()
                applied += 1
                logger.info("  ✓ %s/%s: %s", r["type"], r["slug"], r["reason"])
        logger.info("Dedup: %d aplicadas · %d saltadas · de %d", applied, skipped, len(results))


if __name__ == "__main__":
    main()
