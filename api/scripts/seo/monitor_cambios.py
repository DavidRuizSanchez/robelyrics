"""Pasada diaria del monitor de cambios: foto de cada URL y qué cambió desde ayer.

Recorre el sitemap (más las URLs que ya conocía, para ver las que desaparecen),
compara con la foto anterior (`page_monitor.diff`), busca la causa de cada cambio
en lo que el propio sistema hizo en ese intervalo y guarda todo en `page_changes`.

La primera pasada es la FOTO DE REFERENCIA: guarda y no compara.

Correo: solo con `MONITOR_CAMBIOS_CORREO=1`. La primera semana va en sombra
(guarda y se ve en el panel, sin correo) para medir el ruido antes de avisar, como
con `CORPUS_AUTO_ENTRY`. Con `--dry-run` no escribe nada.

Uso:
    python -m scripts.seo.monitor_cambios --dry-run --limit 20
    python -m scripts.seo.monitor_cambios
    python -m scripts.seo.monitor_cambios --base http://web:3000     (sin Cloudflare)
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    ContentRevision,
    NotificationDigest,
    PageChange,
    PageMonitorRun,
    PageSnapshot,
    Post,
    SeoContent,
    SeoOpportunity,
)
from app.db.session import SessionLocal
from app.services import page_monitor as pm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

_KIND = "monitor_cambios"
HILOS = 3
PAUSA_S = 0.2
# Más de esta parte de las URLs cambiando de golpe es un evento global (plantilla,
# caída): un solo correo resumen.
UMBRAL_GLOBAL = 0.3
ORDEN_SEVERIDAD = {"critico": 0, "estructural": 1, "contenido": 2, "aviso": 3}


def urls_del_sitemap(client, base: str) -> list[str]:
    xml = client.get(f"{base.rstrip('/')}/sitemap.xml",
                     headers={"User-Agent": pm.USER_AGENT}).text
    return sorted({pm._path(u) for u in re.findall(r"<loc>\s*([^<\s]+)", xml)})


def _foto(client, path: str, base: str) -> pm.Foto | Exception:
    """Una foto, con un reintento: un tropiezo de red no es una página caída."""
    for intento in range(2):
        try:
            return pm.snapshot(client, path, base=base)
        except httpx.HTTPError as exc:
            if intento:
                return exc
            time.sleep(2)
        finally:
            time.sleep(PAUSA_S)
    return RuntimeError("inalcanzable")


def causas(db, desde: datetime | None) -> dict[str, list[str]]:
    """Por ruta, lo que el sistema hizo en ella desde la pasada anterior."""
    from app.services.url_resolver import canonical_path_for

    out: dict[str, list[str]] = {}
    if desde is None:
        return out

    def add(path: str | None, texto: str) -> None:
        if path:
            out.setdefault(pm._path(path), []).append(texto)

    for r in db.execute(select(ContentRevision).where(ContentRevision.created_at >= desde)
                        ).scalars():
        add(r.path, f"se aplicó un borrador (oportunidad #{r.opportunity_id})"
            if r.opportunity_id else "se aplicó un borrador")
    for o in db.execute(select(SeoOpportunity).where(SeoOpportunity.applied_at >= desde)
                        ).scalars():
        add(o.path, f"oportunidad SEO #{o.id} aplicada ({o.action})")
    for p in db.execute(select(Post).where(Post.published_at >= desde)).scalars():
        add(f"/blog/{p.slug}", "post publicado")
    for sc in db.execute(select(SeoContent).where(SeoContent.generated_at >= desde)).scalars():
        path = (canonical_path_for(db, sc.entity_type, sc.entity_id)
                if sc.entity_type != "page" else None)
        add(path, f"ficha regenerada ({sc.generated_by or 'motor'})")
    return out


def _guardar_foto(db, snap: PageSnapshot | None, foto: pm.Foto, *, en_sitemap: bool,
                  ahora: datetime) -> None:
    if snap is None:
        snap = PageSnapshot(path=foto.path, first_seen_at=ahora)
        db.add(snap)
    snap.status, snap.final_url, snap.cadena = foto.status, foto.final_url, foto.cadena
    snap.ms, snap.bytes, snap.campos = foto.ms, foto.bytes, foto.campos
    snap.in_sitemap, snap.checked_at = en_sitemap, ahora


def _como_dict(x) -> dict:
    return {"status": x.status, "final_url": x.final_url, "cadena": x.cadena, "ms": x.ms,
            "campos": x.campos}


def pasada(db, *, base: str, limit: int | None = None, dry_run: bool = False):
    ahora = datetime.now(UTC)
    previas = {s.path: s for s in db.execute(select(PageSnapshot)).scalars()}
    ultima = db.execute(select(PageMonitorRun).where(PageMonitorRun.finished_at.isnot(None))
                        .order_by(PageMonitorRun.id.desc()).limit(1)).scalar_one_or_none()
    baseline = not previas

    with httpx.Client(timeout=30) as client:
        en_sitemap = set(urls_del_sitemap(client, base))
        rutas = sorted(en_sitemap | pm.LISTADOS | set(previas))
        if limit:
            rutas = rutas[:limit]
        with ThreadPoolExecutor(HILOS) as ex:
            fotos = dict(zip(rutas, ex.map(lambda p: _foto(client, p, base), rutas),
                             strict=True))

    run = PageMonitorRun(started_at=ahora, urls=len(rutas), baseline=baseline)
    db.add(run)
    db.flush()
    por_causa = causas(db, ultima.started_at if ultima else None)
    cambios: list[PageChange] = []
    errores = 0
    for path, foto in fotos.items():
        if isinstance(foto, Exception):
            errores += 1
            logger.warning("[monitor] %s no respondió: %s", path, foto)
            continue
        previa = previas.get(path)
        dentro = path in en_sitemap
        misma_version = previa is not None and \
            (previa.campos or {}).get("v") == pm.VERSION_PARSER
        if previa is not None and not misma_version:
            encontrados = []          # foto de otra versión del parser: se renueva
        elif previa is not None and not baseline:
            encontrados = pm.diff(_como_dict(previa), _como_dict(foto), path=path)
            if previa.in_sitemap and not dentro:
                encontrados.append(pm.Cambio("sitemap", "dentro", "fuera", "critico"))
            if not previa.in_sitemap and dentro:
                encontrados.append(pm.Cambio("sitemap", "fuera", "dentro", "aviso"))
        elif previa is None and not baseline:
            encontrados = [pm.Cambio("nueva", None, foto.campos.get("title") or path, "aviso")]
        else:
            encontrados = []
        causa = "; ".join(por_causa.get(path, [])) or None
        if path == "/blog" and any(k.startswith("/blog/") for k in por_causa):
            causa = causa or "post publicado"
        for c in encontrados:
            cambios.append(PageChange(run_id=run.id, path=path, campo=c.campo,
                                      severidad=c.severidad, antes=c.antes, despues=c.despues,
                                      detalle=c.detalle, causa=causa, detected_at=ahora))
        _guardar_foto(db, previa, foto, en_sitemap=dentro, ahora=ahora)

    run.errors = errores
    run.changed_urls = len({c.path for c in cambios})
    run.global_event = bool(rutas) and run.changed_urls / len(rutas) > UMBRAL_GLOBAL
    run.finished_at = datetime.now(UTC)
    db.add_all(cambios)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return run, cambios


# --------------------------------------------------------------------------- #
# Correo
# --------------------------------------------------------------------------- #
CAMPO_LABEL = {
    "status": "código HTTP", "redireccion": "redirección", "title": "title",
    "description": "description", "canonical": "canonical", "h1": "H1",
    "robots": "meta robots", "x_robots": "cabecera X-Robots-Tag", "hreflang": "hreflang",
    "headings": "encabezados", "contenido": "contenido", "enlaces": "enlaces internos",
    "jsonld": "tipos de JSON-LD", "og": "Open Graph", "imgs_sin_alt": "imágenes sin alt",
    "tiempo": "tiempo de respuesta", "sitemap": "sitemap", "nueva": "URL nueva",
}


def _html(run, cambios: list[PageChange]) -> str:
    site = pm.SITE
    inesperados = [c for c in cambios if not c.causa]
    esperados = [c for c in cambios if c.causa]
    p = ["<div style='background:#0d0b0a;color:#ede4d3;padding:24px;font-family:Georgia,serif'>",
         "<h2 style='color:#a83a3a;margin:0 0 8px'>Cambios en la web</h2>",
         f"<p style='color:#9a8f80'>{run.changed_urls} URLs con cambios de {run.urls} "
         f"revisadas · {len(inesperados)} cambios sin causa conocida · "
         f"{len(esperados)} explicados por el propio sistema.</p>"]
    if run.global_event:
        p.append("<p style='background:#2a1414;padding:12px;border-left:3px solid #a83a3a'>"
                 "<b>Ha cambiado más de un 30 % de la web de golpe.</b> Suele ser la "
                 "plantilla (un deploy) o una caída. Aquí va el resumen; el detalle, en el "
                 "panel.</p>")
        por_campo = Counter(c.campo for c in cambios)
        p.append("<ul>" + "".join(f"<li>{CAMPO_LABEL.get(k, k)}: {n}</li>"
                                  for k, n in por_campo.most_common()) + "</ul>")
    else:
        for titulo, grupo in (("Sin causa conocida", inesperados),
                              ("Explicados por el sistema", esperados)):
            if not grupo:
                continue
            p.append(f"<h3 style='color:#ede4d3'>{titulo}</h3><ul style='line-height:1.6'>")
            for c in sorted(grupo, key=lambda c: (ORDEN_SEVERIDAD.get(c.severidad, 9),
                                                  c.path))[:60]:
                antes = (c.antes or "—")[:160]
                despues = (c.despues or "—")[:160]
                extra = f" <i style='color:#9a8f80'>({c.causa})</i>" if c.causa else ""
                cuerpo = ("" if c.campo in ("contenido", "enlaces", "headings")
                          else f"<br><span style='color:#9a8f80'>{antes} → {despues}</span>")
                p.append(f"<li><b>{CAMPO_LABEL.get(c.campo, c.campo)}</b> en "
                         f"<a style='color:#a83a3a' href='{site}{c.path}'>{c.path}</a>"
                         f"{extra}{cuerpo}</li>")
            p.append("</ul>")
    p.append(f"<p><a style='color:#a83a3a' href='{site}/biblioteca/admin/cambios'>"
             "Ver los cambios en el panel</a></p></div>")
    return "".join(p)


def avisar(db, run, cambios: list[PageChange], *, dry_run: bool) -> None:
    if not cambios:
        logger.info("[monitor] sin cambios: no hay correo")
        return
    if os.environ.get("MONITOR_CAMBIOS_CORREO", "").strip() != "1":
        logger.info("[monitor] modo sombra: %d cambios guardados, sin correo", len(cambios))
        return
    to = get_settings().admin_email
    if not to:
        logger.warning("[monitor] sin ADMIN_EMAIL: no se envía")
        return
    criticos = [c for c in cambios if c.severidad == "critico"]
    if criticos:
        subject = (f"[Entre Interiores] CRÍTICO: {CAMPO_LABEL.get(criticos[0].campo)} en "
                   f"{criticos[0].path}" + (f" y {len(criticos) - 1} más" if len(criticos) > 1
                                            else ""))
    else:
        subject = f"[Entre Interiores] Cambios en {run.changed_urls} páginas"
    if dry_run:
        logger.info("(dry-run) enviaría a %s: %s", to, subject)
        return
    from app.services.email import send_email

    send_email(to, subject, _html(run, cambios))
    run.notified_at = datetime.now(UTC)
    db.add(NotificationDigest(kind=_KIND, signature=f"run:{run.id}", sent_at=run.notified_at))
    db.commit()
    logger.info("[monitor] aviso enviado a %s: %s", to, subject)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--base", default=os.environ.get("MONITOR_BASE_URL", "").strip() or pm.SITE)
    args = ap.parse_args()

    with SessionLocal() as db:
        run, cambios = pasada(db, base=args.base, limit=args.limit, dry_run=args.dry_run)
        tipo = "foto de referencia" if run.baseline else "pasada"
        logger.info("[monitor] %s: %d URLs · %d con cambios · %d sin responder%s", tipo,
                    run.urls, run.changed_urls, run.errors,
                    " · EVENTO GLOBAL" if run.global_event else "")
        for c in sorted(cambios, key=lambda c: ORDEN_SEVERIDAD.get(c.severidad, 9))[:40]:
            logger.info("   %-11s %-12s %s%s", c.severidad, c.campo, c.path,
                        f" ({c.causa})" if c.causa else "")
        if not run.baseline:
            avisar(db, run, cambios, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
