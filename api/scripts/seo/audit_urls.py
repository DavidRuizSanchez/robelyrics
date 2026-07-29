"""Auditoría de coherencia de URLs: que cada ruta del site lleve a lo que dice.

Sustituye a `audit_internal_links.py` (solo miraba enlaces de `seo_content`, y
daba por buena cualquier URL fuera de `/artista/*`) y a `fix_internal_links_manual.py`
(una lista negra escrita a mano, caso por caso).

El fallo que lo motiva: `/extremoduro/pedra/ama-ama-ama-y-ensancha-el-alma-en-directo`
devolvía **200** con el artículo de una canción y el disco de otra. Nacía de enlaces
que el LLM se inventaba dentro de los artículos. Los cuatro guards que había
(`fact_check`, `focus_check`, `lyric_guard`, `editorial_review`) revisan el TEXTO;
ninguno miraba una URL.

Cinco chequeos, todos contra `app/services/url_resolver.py` (la misma resolución
que usa el sitio, así que lo que aquí sale bien es lo que el visitante ve bien):

  link_cross / link_broken  enlaces internos en los cuerpos publicados
  seo_slug_desync           `seo_content.slug` desincronizado de su entidad
  dup_entity_slug           slugs repetidos entre discos (lo que hace peligroso `.first()`)
  sitemap_mismatch          URLs que el sitemap emite y no resuelven
  gsc_orphan                URLs que Google YA indexó y no llevan a lo que dicen (--gsc)

  --fix      reescribe el enlace a su ruta real; desenlaza el fantasma
  --review   abre errata por lo que no sabe resolver

Nada se borra: ni una fila, ni un `seo_content`, ni una entidad. Lo dudoso va al
panel de erratas y lo remata una persona con el botón «Arreglar», que vuelve a
resolver con los datos de ese momento (`app/services/errata_fix.py`).

Uso:
  python -m scripts.seo.audit_urls                     # informe
  python -m scripts.seo.audit_urls --fix --review      # lo del cron
  python -m scripts.seo.audit_urls --checks links --verbose
  python -m scripts.seo.audit_urls --gsc               # cruza con lo indexado
"""
from __future__ import annotations

import argparse
import logging
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.db.models import Album, ErrataReport, Post, SeoContent, Song
from app.db.session import SessionLocal
from app.services import url_resolver as ur

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CHECKS = (
    "links", "seo_slug_desync", "dup_entity_slug", "sitemap_mismatch", "gsc_orphan",
)

# Tabla de la que sale cada `entity_type` de `seo_content`, para comparar slugs.
_MODELOS_SEO = {
    "artist": "Artist", "album": "Album", "song": "Song",
    "person": "Person", "band": "Band",
}


@dataclass
class UrlFinding:
    """Una incoherencia concreta, con de dónde sale y a dónde debería ir."""

    check: str
    source: str            # "seo:song#123" | "post:45" | "sitemap" | "gsc"
    source_id: int
    url: str
    canonical: str | None = None
    reason: str = ""
    severity: str = "review"       # blocking | review
    evidence: list[str] = field(default_factory=list)

    @property
    def arreglable(self) -> bool:
        """¿Se puede reescribir sin decisión humana?"""
        return self.check in ("link_cross", "seo_slug_desync") and bool(self.canonical)


# --------------------------------------------------------------------------- #
# Chequeos
# --------------------------------------------------------------------------- #
def _revisar_cuerpo(
    cat, texto: str, origen: str, origen_id: int
) -> list[UrlFinding]:
    salida: list[UrlFinding] = []
    for ruta in ur.extract_internal_links(texto or ""):
        res = ur.resolve_path(cat, ruta)
        if res.is_ok:
            continue
        if res.status == "redirect":
            salida.append(UrlFinding(
                check="link_cross", source=origen, source_id=origen_id, url=ruta,
                canonical=res.canonical_path, reason=res.reason or "",
                severity="blocking",
            ))
        else:
            salida.append(UrlFinding(
                check="link_broken", source=origen, source_id=origen_id, url=ruta,
                reason=res.reason or "", severity="blocking",
            ))
    return salida


def check_links(db, cat) -> list[UrlFinding]:
    """Enlaces internos en TODO lo que tiene cuerpo.

    Incluye los `seo_content` sin publicar y los posts en borrador a propósito:
    un borrador se publica luego, y arreglarlo antes sale gratis.
    """
    salida: list[UrlFinding] = []
    for sc in db.execute(select(SeoContent)).scalars().all():
        salida += _revisar_cuerpo(
            cat, sc.body_md, f"seo:{sc.entity_type}#{sc.entity_id}", sc.id,
        )
    for post in db.execute(select(Post)).scalars().all():
        salida += _revisar_cuerpo(cat, post.body_md, f"post:{post.slug}", post.id)
        salida += _revisar_cuerpo(cat, post.excerpt or "", f"post:{post.slug}", post.id)
    return salida


def check_seo_slug_desync(db, cat) -> list[UrlFinding]:
    """`seo_content.slug` es una copia del slug de la entidad; si se desincroniza,
    el sitemap emitía URLs cruzadas (ya arreglado, pero el dato sigue mal)."""
    from app.db import models

    salida: list[UrlFinding] = []
    for sc in db.execute(select(SeoContent)).scalars().all():
        nombre = _MODELOS_SEO.get(sc.entity_type)
        if not nombre:
            continue
        fila = db.get(getattr(models, nombre), sc.entity_id)
        if fila is None:
            salida.append(UrlFinding(
                check="seo_slug_desync", source=f"seo:{sc.entity_type}#{sc.entity_id}",
                source_id=sc.id, url=sc.slug,
                reason="huérfano: la entidad ya no existe", severity="review",
            ))
            continue
        if fila.slug != sc.slug:
            salida.append(UrlFinding(
                check="seo_slug_desync", source=f"seo:{sc.entity_type}#{sc.entity_id}",
                source_id=sc.id, url=sc.slug, canonical=fila.slug,
                reason=f"la entidad se llama «{fila.slug}»", severity="blocking",
            ))
    return salida


def check_dup_entity_slug(db, cat) -> list[UrlFinding]:
    """Slugs repetidos entre discos o entre artistas.

    No es un error hoy, es la bomba de relojería: mientras existan, cualquier
    `.first()` que quede por ahí devuelve una fila al azar.
    """
    salida: list[UrlFinding] = []
    for modelo, etiqueta in ((Song, "canción"), (Album, "disco")):
        repetidos = db.execute(
            select(modelo.slug, func.count())
            .group_by(modelo.slug).having(func.count() > 1)
        ).all()
        for slug, n in repetidos:
            filas = db.execute(select(modelo).where(modelo.slug == slug)).scalars().all()
            donde = [ur.DbCatalog(db).canonical_path(
                "song" if modelo is Song else "album", f.id) for f in filas]
            salida.append(UrlFinding(
                check="dup_entity_slug", source=f"catalogo:{etiqueta}",
                source_id=filas[0].id, url=slug,
                reason=f"{n} {etiqueta}s comparten el slug «{slug}»",
                severity="review",
                evidence=[d for d in donde if d],
            ))
    return salida


def check_sitemap_mismatch(db, cat) -> list[UrlFinding]:
    """Cada URL que el sitemap emite tiene que resolver a su entidad."""
    from app.routers.public import public_sitemap_entries

    class _Resp:
        headers: dict = {}

    salida: list[UrlFinding] = []
    for entrada in public_sitemap_entries(_Resp(), db):
        res = ur.resolve_path(cat, entrada.url_path)
        if res.is_ok:
            continue
        salida.append(UrlFinding(
            check="sitemap_mismatch", source="sitemap", source_id=0,
            url=entrada.url_path, canonical=res.canonical_path,
            reason=res.reason or "", severity="blocking",
        ))
    return salida


def _impresiones_por_pagina() -> dict[str, int]:
    """Impresiones por ruta, de donde se pueda sacar.

    Dos fuentes, en este orden:

      1. `data/gsc_page_queries.json`, que ya se sincroniza al servidor cada
         semana. Es lo que permite correr esto en el cron **sin** llevar el
         token de GSC a producción: el token se queda en la Mac, que es donde
         se decidió que viva.
      2. La API en vivo, cuando sí hay token (o sea, en la Mac).
    """
    import json
    from pathlib import Path

    for ruta in ("/app/data/gsc_page_queries.json",
                 str(Path(__file__).resolve().parents[2] / "data"
                     / "gsc_page_queries.json")):
        if not Path(ruta).exists():
            continue
        paginas = json.loads(Path(ruta).read_text(encoding="utf-8")).get("pages", {})
        salida: dict[str, int] = {}
        for bruta, consultas in paginas.items():
            norm = ur.normalize_path(bruta)
            if norm:
                salida[norm] = salida.get(norm, 0) + sum(
                    int(c.get("impressions", 0)) for c in consultas
                )
        logger.info("  · %d páginas desde %s", len(salida), ruta)
        return salida

    from datetime import date, timedelta

    from app.services import gsc_client

    if not gsc_client.is_configured():
        logger.info("  · sin datos de GSC (ni fichero ni token): se salta")
        return {}

    hasta = date.today()
    desde = hasta - timedelta(days=90)
    salida = {}
    for fila in gsc_client.page_query_rows(desde.isoformat(), hasta.isoformat()):
        claves = fila.get("keys") or []
        norm = ur.normalize_path(claves[0] if claves else "")
        if norm:
            salida[norm] = salida.get(norm, 0) + int(fila.get("impressions", 0))
    logger.info("  · %d páginas desde la API de GSC", len(salida))
    return salida


def check_gsc_orphan(db, cat) -> list[UrlFinding]:
    """URLs que Google YA indexó y que no llevan a lo que dicen.

    Son las que ningún enlace interno revela: Google las descubrió antes de que
    se arreglaran, y siguen trayendo gente a una página que no era.
    """
    impresiones = _impresiones_por_pagina()
    if not impresiones:
        return []

    salida: list[UrlFinding] = []
    for ruta, imps in sorted(impresiones.items(), key=lambda kv: -kv[1]):
        res = ur.resolve_path(cat, ruta)
        if res.is_ok:
            continue
        salida.append(UrlFinding(
            check="gsc_orphan", source="gsc", source_id=0, url=ruta,
            canonical=res.canonical_path, reason=res.reason or "",
            severity="review",
            evidence=[f"{imps} impresiones en 90 días"],
        ))
    return salida


_CHECKERS = {
    "links": check_links,
    "seo_slug_desync": check_seo_slug_desync,
    "dup_entity_slug": check_dup_entity_slug,
    "sitemap_mismatch": check_sitemap_mismatch,
    "gsc_orphan": check_gsc_orphan,
}


def audit(db, checks: list[str]) -> list[UrlFinding]:
    cat = ur.DbCatalog(db)
    salida: list[UrlFinding] = []
    for nombre in checks:
        logger.info("→ %s", nombre)
        salida += _CHECKERS[nombre](db, cat)
    return salida


# --------------------------------------------------------------------------- #
# Arreglo
# --------------------------------------------------------------------------- #
def fix(db, findings: list[UrlFinding], *, incluir_rotos: bool) -> int:
    """Reescribe enlaces y sincroniza slugs. NO borra nada.

    Por defecto solo toca lo que tiene destino seguro (`link_cross`). Los rotos
    sin canónica se desenlazan solo si se pide (`--unlink`): quitar un enlace es
    editar contenido revisado, y esa decisión es de una persona salvo que se
    pida explícitamente.
    """
    n = 0
    cuerpos: dict[tuple[str, int], object] = {}

    for f in findings:
        if f.check == "seo_slug_desync" and f.canonical:
            sc = db.get(SeoContent, f.source_id)
            if sc is not None:
                sc.slug = f.canonical
                n += 1
                logger.info("  ✓ seo_content#%s slug %s → %s", sc.id, f.url, f.canonical)
            continue

        if f.check not in ("link_cross", "link_broken"):
            continue
        if f.check == "link_broken" and not incluir_rotos:
            continue

        tabla = SeoContent if f.source.startswith("seo:") else Post
        clave = (tabla.__name__, f.source_id)
        fila = cuerpos.get(clave) or db.get(tabla, f.source_id)
        if fila is None:
            continue
        cuerpos[clave] = fila

        if f.canonical:
            nuevo = ur._reenlazar(fila.body_md, f.url, f.canonical)
            accion = f"{f.url} → {f.canonical}"
        else:
            nuevo = ur._desenlazar(fila.body_md, f.url)
            accion = f"{f.url} desenlazado"
        if nuevo != fila.body_md:
            fila.body_md = nuevo
            n += 1
            logger.info("  ✓ %s: %s", f.source, accion)

    db.commit()
    return n


def _abrir_errata(db, f: UrlFinding) -> bool:
    from app.services.consensus import errata_exists

    # `url:<check>:<origen>:<ruta>` — el origen dice en qué tabla vive el cuerpo,
    # que es lo que necesita el botón «Arreglar» para saber dónde reescribir.
    # Las rutas nunca llevan «:», así que parsea con un split de 3.
    origen = f.source.split(":", 1)[0]
    clave = f"url:{f.check}:{origen}:{f.url}"
    if errata_exists(db, target_type="internal_url", target_id=f.source_id, field=clave):
        return False
    if f.canonical:
        sugerencia = f"apunta a «{f.canonical}», que es donde vive de verdad"
    else:
        sugerencia = ("quita el enlace (el texto se queda) o crea la ficha que "
                      "falta; no inventes un destino")
    db.add(ErrataReport(
        target_type="internal_url", target_id=f.source_id, field=clave,
        reported_wrong=f"«{f.url}» en {f.source} no lleva a lo que dice ({f.reason})",
        suggested_right=sugerencia,
        reporter="audit_urls", status="needs_human",
        resolution_note=" · ".join(f.evidence)[:2000] or None,
    ))
    return True


def review(db, findings: list[UrlFinding]) -> int:
    """Abre errata por lo que el barrido no sabe arreglar solo."""
    n = 0
    for f in findings:
        if f.arreglable:
            continue
        if _abrir_errata(db, f):
            n += 1
            logger.info("  · a revisión %s «%s» (%s)", f.check, f.url, f.reason)
    db.commit()
    return n


# --------------------------------------------------------------------------- #
# Informe
# --------------------------------------------------------------------------- #
def _report(findings: list[UrlFinding], *, verbose: bool) -> None:
    logger.info("\n=== %d incoherencia(s) ===", len(findings))
    if not findings:
        logger.info("  ✓ todas las rutas del site llevan a lo que dicen")
        return

    por_check = Counter(f.check for f in findings)
    for check, n in por_check.most_common():
        auto = sum(1 for f in findings if f.check == check and f.arreglable)
        logger.info("  · %-18s %3d  (%d con destino seguro)", check, n, auto)

    for check in por_check:
        grupo = [f for f in findings if f.check == check]
        logger.info("\n--- %s ---", check)
        for f in grupo if verbose else grupo[:25]:
            destino = f" → {f.canonical}" if f.canonical else ""
            logger.info("  %-52s%s", f.url[:52], destino)
            logger.info("      en %s · %s", f.source, f.reason)
            for e in f.evidence:
                logger.info("      · %s", e)
        if not verbose and len(grupo) > 25:
            logger.info("  … y %d más (usa --verbose)", len(grupo) - 25)


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoría de coherencia de URLs.")
    ap.add_argument("--checks", default="links,seo_slug_desync,dup_entity_slug,"
                                        "sitemap_mismatch",
                    help=f"chequeos a correr ({', '.join(CHECKS)})")
    ap.add_argument("--gsc", action="store_true",
                    help="añade el cruce con lo que Google ya indexó "
                         "(data/gsc_page_queries.json, o la API si hay token)")
    ap.add_argument("--fix", action="store_true",
                    help="reescribe los enlaces con destino seguro y sincroniza slugs")
    ap.add_argument("--unlink", action="store_true",
                    help="además, desenlaza los fantasmas (conserva el texto)")
    ap.add_argument("--review", action="store_true",
                    help="abre errata por lo que no sabe arreglar")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    checks = [c.strip() for c in args.checks.split(",") if c.strip() in CHECKS]
    if args.gsc and "gsc_orphan" not in checks:
        checks.append("gsc_orphan")
    if not checks:
        ap.error(f"chequeos no válidos; usa: {', '.join(CHECKS)}")

    db = SessionLocal()
    try:
        findings = audit(db, checks)
        _report(findings, verbose=args.verbose)
        if args.fix:
            logger.info("\n=== arreglando lo que tiene destino seguro ===")
            logger.info("%d cambio(s)", fix(db, findings, incluir_rotos=args.unlink))
        if args.review:
            logger.info("\n=== lo dudoso → cola de erratas ===")
            logger.info("%d errata(s) abiertas (nada borrado)", review(db, findings))
        if findings and not (args.fix or args.review):
            logger.info("\n(informe: usa --fix --review para aplicarlo)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
