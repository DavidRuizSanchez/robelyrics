"""Auditoría de TODAS las imágenes del site: que carguen y que sean de quien dicen.

Dos fallos que se repetían y que nadie vigilaba:

  - **Rotas**: las fotos hotlinkeadas a `upload.wikimedia.org` reciben **429** cuando
    el optimizador de Next pide varias desde la IP del server. Se rompen unas u otras
    según el momento, así que arreglar una URL concreta nunca solucionaba nada.
  - **Falsas**: se buscaban por nombre y se asignaban sin comprobar que la fuente
    dijera que son ellos (una foto de prensa cualquiera como «Rebrote», un homónimo
    mexicano para «Los Niños de los Ojos Rojos»).

Esto recorre todas las tablas con imagen, comprueba disponibilidad real y procedencia
(`app/services/image_guard.py`), y sabe arreglarlo:

  --fix      re-aloja en Cloudinary lo que dependa de terceros (mata el 429)
  --review   abre errata por cada foto dudosa, SIN tocar ninguna imagen

Ninguna foto se borra sola. «No encuentro el nombre» no prueba que la foto sea falsa:
el fichero de Leiva en Commons se llama «Leyva», y con una regla más suelta se habría
retirado una foto buena. Lo dudoso va al panel de erratas y lo retira un humano desde
el botón «Arreglar» (que comprueba la acreditación antes de quitarla).

Uso:
  python -m scripts.seo.audit_images
  python -m scripts.seo.audit_images --fix --review
  python -m scripts.seo.audit_images --types band,person --verbose
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import select

from app.db.models import (
    Album, Artist, Band, Concept, ErrataReport, Person, Place, Post, SeoContent, Theme,
)
from app.db.session import SessionLocal
from app.services import image_guard

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# UA de navegador: Wikimedia responde 403 a peticiones sin UA identificable, y lo
# que queremos medir es si la imagen EXISTE, no si nos bloquean por educación.
_UA = "Mozilla/5.0 (compatible; RobeLyrics/1.0; +https://entreinteriores.com)"


@dataclass
class Target:
    """Una tabla con imágenes. `retrata` = la imagen afirma ser de una persona o
    grupo real (y por tanto necesita acreditación); un tema abstracto, no."""

    name: str
    model: type
    url_field: str = "image_url"
    source_field: str | None = "image_source_url"
    attr_field: str | None = "image_attribution"
    lic_field: str | None = "image_license"
    # Campos de los que sale el nombre, en orden. Person NO tiene `name`: usa
    # stage_name/full_name, y leer un campo inexistente dejaba el nombre vacío y
    # marcaba como «sin acreditar» a TODAS las personas (falso positivo peligroso:
    # con retirada automática habría borrado fotos legítimas).
    name_fields: tuple[str, ...] = ("name",)
    retrata: bool = False


TARGETS: dict[str, Target] = {
    "band": Target("band", Band, retrata=True),
    "person": Target("person", Person, name_fields=("stage_name", "full_name"), retrata=True),
    "artist": Target("artist", Artist, retrata=True),
    "place": Target("place", Place),
    "concept": Target("concept", Concept),
    "theme": Target("theme", Theme),
    "album": Target("album", Album, url_field="cover_url", source_field=None,
                    attr_field=None, lic_field=None, name_fields=("title",)),
    "post": Target("post", Post, url_field="hero_image_url", source_field=None,
                   attr_field=None, lic_field=None, name_fields=("title",)),
    "seo": Target("seo", SeoContent, url_field="hero_image_url", source_field=None,
                  attr_field=None, lic_field=None, name_fields=("slug",)),
}


@dataclass
class Finding:
    kind: str
    slug: str
    name: str
    url: str
    problems: list[str] = field(default_factory=list)
    status: str = ""
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    http: int | None = None

    @property
    def broken(self) -> bool:
        return any(p in ("no_carga", "hotlink") for p in self.problems)

    @property
    def unaccredited(self) -> bool:
        """La fuente existe y no dice que sea esta entidad."""
        return "sin_acreditar" in self.problems

    @property
    def to_review(self) -> bool:
        """Ni acreditada ni desmentida: la decide un humano."""
        return "revisar" in self.problems


# Raíz de los estáticos de Next dentro del contenedor (bind-mount de web/public).
_PUBLIC_DIR = Path("/app/web-public")


def _local_file_missing(url: str) -> bool:
    """¿Una ruta local apunta a un fichero que no está?

    Hacía falta porque `_http_status` corta en seco con las rutas que empiezan
    por `/` y devuelve None, así que un `cover_url` apuntando a un JPG borrado
    pasaba la auditoría impoluto. Hoy no hay ninguno roto, pero el agujero
    estaba abierto — y el renombrado de la contraportada de «Tú en tu casa…»
    era exactamente el caso que lo habría provocado.
    """
    if not url.startswith("/"):
        return False
    p = _PUBLIC_DIR / url.lstrip("/")
    return not p.is_file()


def _http_status(url: str) -> int | None:
    """Código real de la imagen. None si ni siquiera se pudo preguntar."""
    if url.startswith("/"):
        return None  # servida por Next desde public/: no es un tercero
    try:
        with httpx.Client(timeout=20, follow_redirects=True,
                          headers={"User-Agent": _UA}) as client:
            r = client.get(url, headers={"Range": "bytes=0-2048"})
            return r.status_code
    except Exception as exc:  # noqa: BLE001
        logger.debug("  %s no responde: %s", url[:60], exc)
        return 0


def _getattr(row, fieldname: str | None):
    return getattr(row, fieldname, None) if fieldname else None


def audit(db, kinds: list[str], *, check_http: bool = True) -> list[Finding]:
    out: list[Finding] = []
    for kind in kinds:
        t = TARGETS[kind]
        rows = db.execute(select(t.model)).scalars().all()
        for row in rows:
            url = _getattr(row, t.url_field)
            if not url:
                # Antes: `continue` a secas, así que las entidades SIN imagen
                # eran invisibles para la auditoría. Los tres discos que se
                # publicaron ayer sin portada no los reportó nadie.
                nombres = [str(_getattr(row, nf)) for nf in t.name_fields
                           if _getattr(row, nf)]
                out.append(Finding(
                    kind=kind,
                    slug=getattr(row, "slug", str(getattr(row, "id", "?"))),
                    name=nombres[0] if nombres else "",
                    url="",
                    problems=["sin imagen"],
                ))
                continue

            if _local_file_missing(url):
                nombres = [str(_getattr(row, nf)) for nf in t.name_fields
                           if _getattr(row, nf)]
                out.append(Finding(
                    kind=kind,
                    slug=getattr(row, "slug", str(getattr(row, "id", "?"))),
                    name=nombres[0] if nombres else "",
                    url=url,
                    problems=["fichero local ausente"],
                ))
                continue
            nombres = [str(_getattr(row, nf)) for nf in t.name_fields if _getattr(row, nf)]
            f = Finding(
                kind=kind,
                slug=getattr(row, "slug", str(getattr(row, "id", "?"))),
                name=nombres[0] if nombres else "",
                url=url,
            )
            if image_guard.must_rehost(url):
                f.problems.append("hotlink")
            if check_http:
                f.http = _http_status(url)
                if f.http is not None and f.http not in (200, 206):
                    f.problems.append("no_carga")
            if t.retrata:
                v = image_guard.verify_provenance(
                    entity_name=f.name,
                    aliases=nombres[1:],
                    image_url=url,
                    source_url=_getattr(row, t.source_field),
                    attribution=_getattr(row, t.attr_field),
                    license_=_getattr(row, t.lic_field),
                )
                f.status, f.reason, f.evidence = v.status, v.reason, v.evidence
                if v.needs_human:
                    # «sin_acreditar» = la fuente existe y no habla de esta entidad;
                    # «revisar» = no hay fuente, o huele a homónimo. Ninguna se borra
                    # sola: las dos van a la cola de erratas.
                    f.problems.append(
                        "sin_acreditar" if v.status == "unaccredited" else "revisar")
            out.append(f)
    return out


def rehost(db, findings: list[Finding]) -> int:
    """Trae a Cloudinary todo lo que dependa de un tercero. Es lo que mata el 429."""
    from sqlalchemy import update

    from scripts.seo.fetch_entity_images import _rehost_to_cloudinary

    n = 0
    for f in findings:
        if "hotlink" not in f.problems:
            continue
        new_url = _rehost_to_cloudinary(f.url)
        if not new_url:
            logger.warning("  ✗ no se pudo re-alojar %s/%s", f.kind, f.slug)
            continue
        t = TARGETS[f.kind]
        model = t.model
        row = db.execute(select(model).where(model.slug == f.slug)).scalar_one_or_none() \
            if hasattr(model, "slug") else None
        if row is None:
            continue
        db.execute(update(model).where(model.id == row.id)
                   .values(**{t.url_field: new_url}))
        # La procedencia se CONSERVA: la foto sigue siendo de quien era, solo cambia
        # desde dónde la servimos. Si no había source_url, se guarda el origen.
        if t.source_field and not _getattr(row, t.source_field):
            db.execute(update(model).where(model.id == row.id)
                       .values(**{t.source_field: f.url}))
        n += 1
        logger.info("  ✓ %s/%s re-alojado en Cloudinary", f.kind, f.slug)
    db.commit()
    return n


def _open_errata(db, f: Finding, row) -> None:
    from app.services.consensus import errata_exists

    field_key = f"image:{f.kind}/{f.slug}"
    if errata_exists(db, target_type="image", target_id=row.id, field=field_key):
        return
    db.add(ErrataReport(
        target_type="image", target_id=row.id, field=field_key,
        reported_wrong=f"foto sin acreditar en «{f.name}»: {f.reason}",
        suggested_right="pon una foto cuya fuente diga que es esta entidad (Commons con "
                        "categoría propia) o arte propio marcado como ilustración",
        reporter="audit_images", status="needs_human",
        resolution_note=" · ".join(f.evidence)[:2000] or None,
    ))


def review(db, findings: list[Finding]) -> int:
    """Abre errata por cada foto dudosa. NO toca ninguna imagen.

    La imagen es una afirmación de identidad como cualquier otro dato del site, así
    que una foto de otro no puede quedarse — pero tampoco se borra por sospecha:
    los metadatos de Commons son irregulares (a Leiva lo escriben «Leyva») y logos
    de sellos legítimos no tienen fuente citable. Se propone, decide el humano."""
    n = 0
    for f in findings:
        if not (f.unaccredited or f.to_review):
            continue
        t = TARGETS[f.kind]
        row = db.execute(select(t.model).where(t.model.slug == f.slug)).scalar_one_or_none()
        if row is None:
            continue
        _open_errata(db, f, row)
        n += 1
        logger.info("  · a revisión %s/%s (%s)", f.kind, f.slug, f.status)
    db.commit()
    return n


def _report(findings: list[Finding], *, verbose: bool) -> None:
    rotas = [f for f in findings if f.broken]
    sin_acred = [f for f in findings if f.unaccredited]
    revisar = [f for f in findings if f.to_review]
    ausentes = [f for f in findings if "fichero local ausente" in f.problems]
    # Solo se listan los tipos donde faltar imagen es un problema real: un disco
    # sin portada se ve, un concepto abstracto sin foto no.
    sin_img = [f for f in findings
               if "sin imagen" in f.problems and f.kind in ("album", "artist", "band", "person")]
    logger.info("=== %d entidades auditadas ===", len(findings))
    logger.info("  · %d dependen de un tercero o no cargan", len(rotas))
    logger.info("  · %d cuya fuente no las acredita", len(sin_acred))
    logger.info("  · %d sin fuente que las acredite (van a revisión, NO se borran)", len(revisar))
    if ausentes:
        logger.info("  · %d con FICHERO LOCAL AUSENTE (enlace roto)", len(ausentes))
    if sin_img:
        logger.info("  · %d sin imagen (informativo, no se arregla solo)", len(sin_img))
    for grupo, titulo in ((ausentes, "FICHERO LOCAL AUSENTE — enlace roto"),
                          (rotas, "DEPENDEN DE TERCEROS / NO CARGAN"),
                          (sin_acred, "SIN ACREDITAR"),
                          (revisar, "A REVISAR (sin fuente / homónimo)"),
                          (sin_img, "SIN IMAGEN")):
        if not grupo:
            continue
        logger.info("\n--- %s ---", titulo)
        for f in grupo:
            http = f"HTTP {f.http}" if f.http else ""
            logger.info("  %s/%s «%s» %s %s", f.kind, f.slug, f.name,
                        ",".join(f.problems), http)
            if verbose and f.reason:
                logger.info("      %s", f.reason)
                for e in f.evidence:
                    logger.info("      · %s", e)


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditoría de imágenes del site.")
    ap.add_argument("--types", default=",".join(TARGETS),
                    help=f"tipos a auditar ({', '.join(TARGETS)})")
    ap.add_argument("--fix", action="store_true", help="re-aloja en Cloudinary lo hotlinkeado")
    ap.add_argument("--review", action="store_true",
                    help="abre errata por cada foto dudosa (no toca ninguna imagen)")
    ap.add_argument("--no-http", action="store_true", help="salta la comprobación HTTP (rápido)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    kinds = [k.strip() for k in args.types.split(",") if k.strip() in TARGETS]
    if not kinds:
        ap.error(f"tipos no válidos; usa: {', '.join(TARGETS)}")

    db = SessionLocal()
    try:
        findings = audit(db, kinds, check_http=not args.no_http)
        _report(findings, verbose=args.verbose)
        if args.fix:
            logger.info("\n=== re-alojando en Cloudinary ===")
            logger.info("%d imagen(es) re-alojada(s)", rehost(db, findings))
        if args.review:
            logger.info("\n=== fotos dudosas → cola de erratas ===")
            logger.info("%d errata(s) abiertas (ninguna imagen tocada)", review(db, findings))
        if not (args.fix or args.review) and (
                any(f.broken for f in findings) or any(f.unaccredited for f in findings)):
            logger.info("\n(informe: usa --fix --review para aplicarlo)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
