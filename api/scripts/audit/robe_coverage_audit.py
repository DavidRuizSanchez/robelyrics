"""Qué contenido publicado habla de Robe y se deja lo que no se puede omitir.

DIAGNOSTICA, NO ARREGLA. No tiene `--apply` ni lo va a tener: una pasada
automática sobre 330 fichas es exactamente la forma de romper una web pública.
Lo que hace es darte la lista ordenada por lo que más duele —el tráfico real de
GSC— para que tú decidas qué entra en cada tanda.

Cuatro reglas, todas deterministas (`app.services.sensitive_topics`):

  OMITE_MUERTE   recorre una trayectoria y no dice que Robe murió. Es la grave:
                 deja al lector creyendo que la historia sigue.
  DEBUT          llama debut a «Rock Transgresivo» (1994). El debut es «Tú en tu
                 casa, nosotros en la hoguera» (1990).
  DISOLUCION     data la disolución en 2018; fue el 18 de diciembre de 2019.
  DISCOGRAFIA    enumera discos y se deja alguno del catálogo.

Uso:
    python -m scripts.audit.robe_coverage_audit
    python -m scripts.audit.robe_coverage_audit --type post --min-clicks 1
    python -m scripts.audit.robe_coverage_audit --out /tmp/cobertura.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.db.models import Post, SeoContent
from app.db.session import SessionLocal
from app.services import sensitive_topics as st

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Prefijo público por tipo de entidad. Es el inverso de `url_resolver.SECTIONS`,
# derivado de él para que no se queden desparejados si alguien añade una sección.
def _prefijos() -> dict[str, str]:
    from app.services.url_resolver import SECTIONS

    fuera = {v: k for k, v in SECTIONS.items() if v not in ("post", "book")}
    return fuera


@dataclass
class Hallazgo:
    tipo: str
    id: int
    slug: str
    ruta: str
    titulo: str
    clics: int
    impresiones: int
    reglas: list[str]
    evidencia: str

    @property
    def severidad(self) -> str:
        """Lo que engaña al lector pesa más que lo que está incompleto."""
        return "alta" if "OMITE_MUERTE" in self.reglas else "media"


def _trafico() -> dict[str, tuple[int, int]]:
    """Clics e impresiones por ruta, del último volcado de GSC."""
    for cand in (Path("/app/data/gsc_page_queries.json"),
                 Path(__file__).resolve().parents[3] / "data" / "gsc_page_queries.json"):
        if cand.exists():
            datos = json.loads(cand.read_text(encoding="utf-8"))
            break
    else:
        logger.warning("Sin volcado de GSC: no se podrá priorizar por tráfico.")
        return {}
    out: dict[str, tuple[int, int]] = {}
    for ruta, queries in (datos.get("pages") or {}).items():
        clics = sum(int(q.get("clicks") or 0) for q in queries)
        imps = sum(int(q.get("impressions") or 0) for q in queries)
        out[ruta.rstrip("/") or "/"] = (clics, imps)
    logger.info("Tráfico cargado: %d rutas (periodo %s).", len(out),
                (datos.get("period") or {}).get("start", "?"))
    return out


def _ruta_de_ficha(db, sc: SeoContent, prefijos: dict[str, str]) -> str:
    """Ruta pública de una ficha SEO, que depende de su tipo."""
    if sc.entity_type in ("song", "album", "artist"):
        # Viven dentro del árbol del catálogo y hace falta resolverlas.
        from app.services.url_resolver import canonical_path_for

        try:
            return canonical_path_for(db, sc.entity_type, sc.entity_id) or ""
        except Exception:  # noqa: BLE001
            return ""
    pref = prefijos.get(sc.entity_type)
    return f"/{pref}/{sc.slug}" if pref else ""


def _revisar(db, *, tipo: str, id_: int, slug: str, ruta: str, titulo: str,
             cuerpo: str, kind: str | None, trafico,
             entity_slug: str | None = None) -> Hallazgo | None:
    rep = st.revisar(db, kind=kind, subject=titulo, body_md=cuerpo,
                     entity_slug=entity_slug)
    reglas = []
    if rep.omite_fallecimiento:
        reglas.append("OMITE_MUERTE")
    if rep.debut_erroneo:
        reglas.append("DEBUT")
    if rep.disolucion_erronea:
        reglas.append("DISOLUCION")
    if rep.discos_que_faltan:
        reglas.append("DISCOGRAFIA")
    if not reglas:
        return None
    clics, imps = trafico.get(ruta.rstrip("/") or "/", (0, 0))
    return Hallazgo(tipo=tipo, id=id_, slug=slug, ruta=ruta, titulo=titulo,
                    clics=clics, impresiones=imps, reglas=reglas,
                    evidencia=" · ".join(rep.motivos)[:400])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--type", choices=["post", "seo", "all"], default="all")
    ap.add_argument("--out", help="CSV de salida")
    ap.add_argument("--limit", type=int, help="máximo de filas a listar")
    ap.add_argument("--min-clicks", type=int, default=0,
                    help="solo lo que tenga al menos N clics en GSC")
    args = ap.parse_args()

    trafico = _trafico()
    prefijos = _prefijos()
    hallazgos: list[Hallazgo] = []

    with SessionLocal() as db:
        if args.type in ("post", "all"):
            posts = db.execute(
                select(Post).where(Post.status == "published")
            ).scalars().all()
            logger.info("Posts publicados: %d", len(posts))
            for p in posts:
                h = _revisar(db, tipo="post", id_=p.id, slug=p.slug,
                             ruta=f"/blog/{p.slug}", titulo=p.title or "",
                             cuerpo=p.body_md or "", kind=p.kind, trafico=trafico)
                if h:
                    hallazgos.append(h)

        if args.type in ("seo", "all"):
            fichas = db.execute(
                select(SeoContent).where(SeoContent.published.is_(True))
            ).scalars().all()
            logger.info("Fichas SEO publicadas: %d", len(fichas))
            for sc in fichas:
                ruta = _ruta_de_ficha(db, sc, prefijos)
                h = _revisar(db, tipo=f"seo:{sc.entity_type}", id_=sc.id, slug=sc.slug,
                             ruta=ruta, titulo=sc.meta_title or sc.slug,
                             cuerpo=sc.body_md or "", kind=sc.entity_type,
                             trafico=trafico, entity_slug=sc.slug)
                if h:
                    hallazgos.append(h)

    if args.min_clicks:
        hallazgos = [h for h in hallazgos if h.clics >= args.min_clicks]
    # Primero lo que engaña, y dentro de eso lo que más se lee.
    hallazgos.sort(key=lambda h: (h.severidad != "alta", -h.clics, -h.impresiones))

    graves = [h for h in hallazgos if h.severidad == "alta"]
    con_trafico = [h for h in hallazgos if h.clics > 0]
    logger.info("")
    logger.info("Piezas con algo que corregir: %d  (graves: %d · con clics: %d)",
                len(hallazgos), len(graves), len(con_trafico))
    for regla in ("OMITE_MUERTE", "DEBUT", "DISOLUCION", "DISCOGRAFIA"):
        n = sum(1 for h in hallazgos if regla in h.reglas)
        if n:
            logger.info("  %-12s %d", regla, n)

    logger.info("")
    logger.info("%-4s %-22s %6s %7s  %s", "SEV", "REGLAS", "CLICS", "IMPR", "RUTA")
    for h in hallazgos[: args.limit or 25]:
        logger.info("%-4s %-22s %6d %7d  %s", h.severidad[:4],
                    ",".join(h.reglas), h.clics, h.impresiones, h.ruta or f"({h.slug})")
    if not args.limit and len(hallazgos) > 25:
        logger.info("… y %d más (usa --out para verlas todas).", len(hallazgos) - 25)

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["severidad", "tipo", "id", "ruta", "titulo", "clics",
                        "impresiones", "reglas", "evidencia"])
            for h in hallazgos:
                w.writerow([h.severidad, h.tipo, h.id, h.ruta, h.titulo, h.clics,
                            h.impresiones, ",".join(h.reglas), h.evidencia])
        logger.info("CSV escrito en %s", args.out)

    # Nada se arregla aquí: el código de salida solo informa.
    sys.exit(0)


if __name__ == "__main__":
    main()
