"""Aplica fotos manuales (URLs externas) re-alojándolas en Cloudinary.

Lee data/manual_photos.yaml con entradas:
  - slug: <slug de persona o álbum>
    url: <URL externa de la imagen>
    kind: person | album        # default person
    attribution: <texto crédito opcional>

Descarga cada imagen y la re-aloja en Cloudinary (dominio permitido por
next/image), luego setea persons.image_url / albums.cover_url. Idempotente:
salta las que ya tienen imagen salvo --force.

Fotos de TERCEROS (decisión de David, 10-11-2026: si no hay foto libre, la que
haya, con crédito): la entrada lleva además
    license: derechos de su autor
    source_url: <página donde se publicó, que nombra a quien retrata>
Antes de guardarla se comprueba que esa página nombra a la persona (o a lo que
diga `identity`) y que no es de una agencia vetada; después pasa
`image_guard.verify_provenance`, que tiene que dar `third_party_credited`.

Uso:
    python -m scripts.seo.apply_manual_photos [--force] [--slug X]
"""
from __future__ import annotations

import argparse
import os

import yaml
from sqlalchemy import select

from app.db.models import Album, Band, Person
from app.services import image_guard
from scripts.research.common import get_session, log
from scripts.seo.fetch_entity_images import _rehost_to_cloudinary

# kind -> (modelo, campo de imagen)
_KIND_MAP = {
    "person": (Person, "image_url"),
    "album": (Album, "cover_url"),
    "band": (Band, "image_url"),
}


def _nombres(row) -> list[str]:
    return [n for n in (getattr(row, "stage_name", None), getattr(row, "full_name", None),
                        getattr(row, "name", None), getattr(row, "title", None)) if n]


def _yaml_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/app/data/manual_photos.yaml",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", "manual_photos.yaml")),
        os.path.normpath(os.path.join(here, "..", "..", "data", "manual_photos.yaml")),
    ):
        if os.path.exists(p):
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-aloja aunque ya tenga imagen")
    ap.add_argument("--slug", help="solo un slug")
    args = ap.parse_args()

    path = _yaml_path()
    if not path:
        log("data/manual_photos.yaml no encontrado", "err")
        return
    entries = (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("photos") or []
    done = skipped = failed = 0
    with get_session() as db:
        for e in entries:
            slug = e.get("slug")
            url = e.get("url")
            kind = e.get("kind", "person")
            if not (slug and url):
                continue
            if args.slug and slug != args.slug:
                continue
            model, field = _KIND_MAP.get(kind, _KIND_MAP["person"])
            row = db.execute(select(model).where(model.slug == slug)).scalar_one_or_none()
            if not row:
                log(f"  {kind} '{slug}' no encontrado", "warn")
                failed += 1
                continue
            if getattr(row, field) and not args.force:
                skipped += 1
                continue
            licencia, fuente = e.get("license"), e.get("source_url")
            tercero = licencia == image_guard.LICENCIA_TERCEROS
            if tercero:
                motivo = image_guard.fuente_no_acredita(fuente, e.get("identity") or _nombres(row))
                if motivo:
                    log(f"  {slug}: no se aplica ({motivo})", "warn")
                    failed += 1
                    continue
            rehosted = _rehost_to_cloudinary(url)
            if not rehosted:
                log(f"  fallo re-alojando {slug} ({url[:60]}…)", "warn")
                failed += 1
                continue
            attr = e.get("attribution")
            if tercero:
                v = image_guard.verify_provenance(
                    entity_name=_nombres(row)[0], image_url=rehosted, source_url=fuente,
                    attribution=attr, license_=licencia)
                if v.status != "third_party_credited":
                    log(f"  {slug}: la guarda no la da por buena ({v.status}: {v.reason})", "warn")
                    failed += 1
                    continue
            setattr(row, field, rehosted)
            if attr and hasattr(row, "image_attribution"):
                row.image_attribution = attr
            if licencia and hasattr(row, "image_license"):
                row.image_license = licencia
            if fuente and hasattr(row, "image_source_url"):
                row.image_source_url = fuente
            done += 1
            log(f"  ✓ {kind}/{slug} -> {rehosted}", "ok")
        db.commit()
    log(f"Fotos manuales: {done} aplicadas · {skipped} ya tenían · {failed} fallos", "ok")


if __name__ == "__main__":
    main()
