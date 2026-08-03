"""De-repetición LÉXICA: cuando una ficha NOMBRA su sujeto (o un término clave)
demasiadas veces (p.ej. «Rock Transgresivo» 16 veces en 5k), reescribe variando las
referencias (pronombres, «el disco», «el álbum», «esta obra», sinónimos) para que
lea natural — SIN perder ningún hecho y SIN keyword-stuffing.

Es un fallo distinto al de `dedup_pages` (que quita ideas/hechos duplicados): aquí el
problema es repetir el NOMBRE, que ni `prior` (anti-redundancia semántica) ni el juez
de rigor (lo tolera como 'revise') corrigen.

Guardas (idénticas en espíritu a dedup): cero pérdida de versos/enlaces/años, nada
añadido, anti-gutting, y el rigor no baja. Además: el nombre debe BAJAR de frecuencia
pero seguir apareciendo (≥2 veces, para SEO: H1/primer párrafo).

Modos:
  --scan                 Mide cuántas fichas sobre-nombran (sin LLM, sin coste).
  --sample --slugs a,b   before/after (no persiste).
  --apply                Aplica con backup.
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
_VERSE = re.compile(r"[«\"]([^«»\"]{12,})[»\"]")
_LINK = re.compile(r"\]\((https?://[^)]+)\)")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
# Para enmascarar (proteger de reescritura): verso COMPLETO con comillas y enlace COMPLETO.
_VERSE_FULL = re.compile(r"[«\"][^«»\"]{12,}[»\"]")
_LINK_FULL = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)")


def _mask(body: str) -> tuple[str, dict]:
    """Sustituye versos citados, enlaces markdown y años por placeholders opacos, para
    que el LLM NO pueda tocarlos al reescribir la prosa. Devuelve (texto_enmascarado, mapa)."""
    tokens: dict[str, str] = {}

    def sub(rx, prefix, text):
        def repl(m):
            key = f"§{prefix}{len(tokens)}§"
            tokens[key] = m.group(0)
            return key
        return rx.sub(repl, text)

    masked = sub(_LINK_FULL, "L", body)      # primero enlaces (contienen texto)
    masked = sub(_VERSE_FULL, "V", masked)
    masked = sub(_YEAR, "Y", masked)
    return masked, tokens


def _unmask(text: str, tokens: dict) -> str:
    for key, val in tokens.items():
        text = text.replace(key, val)
    return text
# Umbral: más de 1 mención del nombre por cada 550 caracteres = sobre-nombra.
CHARS_PER_MENTION = 550
MIN_MENTIONS = 6            # y al menos 6 en absoluto
FLOOR_RATIO = 0.80
FLOOR_ABS = 1500


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _facts(body: str):
    return ({_norm(m) for m in _VERSE.findall(body) if len(m.strip()) >= 12},
            set(_LINK.findall(body)), set(_YEAR.findall(body)))


def _clean_subject(meta_title: str, slug: str) -> str:
    name = (meta_title or "").split(":")[0].strip()
    for suf in (" letra", " grupo", " significado", " de Extremoduro", " de Robe",
                " en la obra de Extremoduro", " en la obra de Robe"):
        if name.lower().endswith(suf):
            name = name[: -len(suf)].strip()
    return name or slug.replace("-", " ")


def _count_name(body: str, name: str) -> int:
    if not name:
        return 0
    return len(re.findall(re.escape(name), body, flags=re.I))


def _over_named(body: str, name: str) -> tuple[bool, int]:
    n = _count_name(body, name)
    return (n >= MIN_MENTIONS and n > len(body) / CHARS_PER_MENTION, n)


# Referencias genéricas DENTRO de comillas. Una comilla marca un título, así que
# «esta obra» entrecomillado nunca es correcto: es la sustitución de este script
# aplicada donde no debía. Pasó en producción — se publicó «La composición de
# "esta obra" refleja…» y «al igual que "la banda"» — porque `_mask` solo protege
# lo entrecomillado de 12+ caracteres y los títulos cortos («Pedrá», «Prometeo»)
# quedaban a merced del LLM.
_GENERICOS = (r"el disco|el álbum|el album|la banda|el grupo|esta obra|este trabajo|"
              r"el tema|la canción|la cancion|su debut|esta canción|esta cancion|"
              r"el conjunto|la obra|este disco|este álbum|este album")
_GENERICO_ENTRECOMILLADO = re.compile(rf"[«\"’']\s*(?:{_GENERICOS})\s*[»\"’']", re.I)


def _genericos_entrecomillados(texto: str) -> list[str]:
    """Genéricos que han acabado entre comillas, o sea, disfrazados de título."""
    return [m.group(0) for m in _GENERICO_ENTRECOMILLADO.finditer(texto or "")]


_PROMPT = (
    "Esta ficha en markdown repite DEMASIADAS veces el nombre «{name}» ({n} veces), lo "
    "que lee mal y parece keyword-stuffing. Reescríbela VARIANDO las referencias al "
    "sujeto (pronombres, «el disco»/«el álbum»/«la banda»/«esta obra»/«su debut»/«el "
    "grupo»/etc., según proceda), con estas reglas ESTRICTAS:\n"
    "- Reduce «{name}» a la MITAD o menos de sus menciones (deja unas 3-6, en el primer "
    "párrafo y algún H2). El resto de veces, sustitúyelo por una referencia variada.\n"
    "- CONSERVA CADA FRASE Y CADA DATO: reescribe frase por frase cambiando solo cómo se "
    "nombra al sujeto. NO borres ninguna frase, NO fusiones párrafos, NO recortes: el "
    "texto debe cubrir EXACTAMENTE lo mismo que el original.\n"
    "- NO pierdas NINGÚN nombre propio ni marcador §V..§/§L..§/§Y..§ (son versos, enlaces "
    "y años: cópialos TAL CUAL en su sitio). NO añadas información nueva.\n"
    "- NUNCA sustituyas lo que va ENTRE COMILLAS: unas comillas marcan un TÍTULO de "
    "canción o de disco, y escribir «esta obra» o «la banda» entre comillas convierte "
    "el título en un sinsentido. Los títulos entrecomillados se copian tal cual.\n"
    "- Mantén el markdown y todos los H2. Español, mismo registro.\n"
    "- Devuelve SOLO el markdown resultante.\n\n"
    "FICHA:\n\"\"\"\n{body}\n\"\"\""
)


def _rewrite(client: OpenAI, name: str, n: int, body: str) -> str | None:
    """De-repite con el cuerpo ENMASCARADO (versos/enlaces/años protegidos). Restaura
    los placeholders al final. Si el LLM perdió alguno, la guarda de _facts lo caza."""
    masked, tokens = _mask(body)
    try:
        r = client.chat.completions.create(
            model="gpt-4o", temperature=0.3, max_tokens=3200,
            messages=[{"role": "user", "content": (
                _PROMPT.format(name=name, n=n, body=masked)
                + "\n\nIMPORTANTE: hay marcadores como §V3§, §L2§, §Y1§ que representan "
                "versos, enlaces y años. NO los toques, NO los borres y NO cambies su texto: "
                "cópialos TAL CUAL en su sitio.")}])
        out = (r.choices[0].message.content or "").strip()
        out = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", out).strip()
        return _unmask(out, tokens) or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[derepeat] LLM falló %s: %s", name, exc)
        return None


def _evaluate(subject, kind, name, original, new):
    ov, ol, oy = _facts(original)
    nv, nl, ny = _facts(new)
    miss = [v for v in ov if v not in nv]
    misl = [u for u in ol if u not in nl]
    add = [v for v in nv if v not in ov] + [u for u in nl if u not in ol] + \
          [y for y in ny if y not in oy]
    ratio = len(new) / max(len(original), 1)
    n_before = _count_name(original, name)
    n_after = _count_name(new, name)
    res = {"before_len": len(original), "after_len": len(new), "ratio": round(ratio, 2),
           "name_before": n_before, "name_after": n_after}
    if miss or misl:
        res["ok"] = False; res["reason"] = f"pérdida: -{len(miss)} versos, -{len(misl)} enlaces"
        return res
    if add:
        res["ok"] = False; res["reason"] = f"añade datos: +{len(add)}"
        return res
    # Un genérico entre comillas es un título destrozado, no una variación de
    # estilo. Solo cuenta si lo introduce ESTA pasada: si ya venía en el original
    # no se bloquea por algo que el script no ha hecho.
    colados = [g for g in _genericos_entrecomillados(new)
               if g not in _genericos_entrecomillados(original)]
    if colados:
        res["ok"] = False
        res["reason"] = f"genérico entrecomillado (destroza un título): {colados[:3]}"
        return res
    if len(new) < FLOOR_ABS or ratio < FLOOR_RATIO:
        res["ok"] = False; res["reason"] = f"gutting (ratio {ratio:.2f})"
        return res
    if n_after < 2:
        res["ok"] = False; res["reason"] = f"borra el nombre del todo ({n_after})"
        return res
    if n_after >= n_before:
        res["ok"] = False; res["reason"] = f"no reduce el nombre ({n_before}→{n_after})"
        return res
    vb = editorial_review(original, kind=kind, subject=subject)
    va = editorial_review(new, kind=kind, subject=subject)
    res["score_before"] = vb.score; res["score_after"] = va.score
    if va.score < vb.score:
        res["ok"] = False; res["reason"] = f"rigor baja ({vb.score}→{va.score})"
        return res
    res["ok"] = True
    res["reason"] = f"OK (nombre {n_before}→{n_after}, rigor {vb.score}→{va.score})"
    return res


def _rows(db, slugs):
    only = {s.strip() for s in slugs.split(",")} if slugs else None
    out = []
    for sc in db.query(SeoContent).filter(SeoContent.entity_type.in_(SEO_TYPES)).all():
        if only and sc.slug not in only:
            continue
        out.append({"id": sc.id, "type": sc.entity_type, "slug": sc.slug,
                    "subject": _clean_subject(sc.meta_title or "", sc.slug),
                    "body": sc.body_md or ""})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--slugs", default=None)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with SessionLocal() as db:
        rows = _rows(db, args.slugs)

    if args.scan:
        flagged = []
        for r in rows:
            over, n = _over_named(r["body"], r["subject"])
            if over:
                flagged.append((r["type"], r["slug"], n, len(r["body"]), r["subject"]))
        flagged.sort(key=lambda x: -x[2])
        by_type = {}
        for t, *_ in flagged:
            by_type[t] = by_type.get(t, 0) + 1
        print(f"\nFichas que SOBRE-NOMBRAN su sujeto: {len(flagged)} de {len(rows)}")
        print("por tipo:", dict(sorted(by_type.items())))
        print("\nTop 25 (nombre · veces · chars):")
        for t, slug, n, ln, subj in flagged[:25]:
            print(f"  {n:>3}× {t:<8} {slug:<45} «{subj}» ({ln}c)")
        return

    client = OpenAI(api_key=get_settings().openai_api_key)
    cands = [r for r in rows if _over_named(r["body"], r["subject"])[0]]
    logger.info("Candidatas: %d", len(cands))

    def work(r, attempts=3):
        n = _count_name(r["body"], r["subject"])
        best = None
        for _ in range(attempts):
            new = _rewrite(client, r["subject"], n, r["body"])
            if not new:
                continue
            ev = _evaluate(r["subject"], r["type"], r["subject"], r["body"], new)
            cand = {**r, "new": new, **ev}
            if ev.get("ok"):
                return cand           # primera que pasa las guardas
            best = best or cand       # guarda la 1ª fallida para el informe
        return best or {**r, "ok": False, "reason": "sin salida LLM"}

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(work, cands):
            results.append(res)

    if args.sample:
        for r in results:
            print(f"\n===== {r['type']}/{r['slug']} — {r.get('reason')} =====")
            if r.get("new"):
                print(f"[nombre {r.get('name_before')}→{r.get('name_after')} · "
                      f"{r['before_len']}→{r['after_len']}c · rigor "
                      f"{r.get('score_before')}→{r.get('score_after')} · aplica={r['ok']}]")
                print("----- NUEVO -----"); print(r["new"])
        return

    if args.apply:
        ok = skip = 0
        with SessionLocal() as db:
            for r in results:
                if not r.get("ok"):
                    logger.info("  %s/%s: no aplica (%s)", r["type"], r["slug"], r.get("reason"))
                    skip += 1; continue
                print("<<<BACKUP>>>" + json.dumps({
                    "seo_id": r["id"], "slug": r["slug"], "entity_type": r["type"],
                    "old_body_b64": base64.b64encode(r["body"].encode()).decode()}))
                sc = db.get(SeoContent, r["id"])
                sc.body_md = r["new"]
                sc.generated_at = datetime.now(timezone.utc)
                sc.generated_by = "derepeat-" + (sc.generated_by or "")
                db.commit(); ok += 1
                logger.info("  ✓ %s/%s: %s", r["type"], r["slug"], r["reason"])
        logger.info("De-repetición: %d aplicadas · %d saltadas · de %d", ok, skip, len(results))


if __name__ == "__main__":
    main()
