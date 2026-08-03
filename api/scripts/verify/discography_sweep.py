"""Barrido de discografía: censo canónico cruzado contra el catálogo.

    python -m scripts.verify.discography_sweep --out /app/kw_out/DISCOGRAFIA.md

NO escribe en la BD. Produce un informe con una fila por lanzamiento y un
veredicto, para que la decisión de qué entra la tome una persona.

Fuentes:
  T1  MusicBrainz (release-groups del artista + status/sello de la release más
      antigua de cada grupo, que es la edición original y no la reedición).
  T2  El catálogo actual (`data/discography.yaml` + BD) para saber qué falta.

Regla dura: nada se propone como ALTA sin `status=Official` en T1. Lo que no se
pueda acreditar sale como REVISAR con el motivo escrito — no se rellena a ojo.
El informe lleva su bloque de fuentes con MBID y fecha de consulta.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Album, Artist
from app.db.session import SessionLocal
from app.services.kw_normalize import kw_norm

MB = "https://musicbrainz.org/ws/2"
UA = "RobeLyrics/1.0 (davidruizsanchez@gmail.com)"
PAUSA = 1.1  # el rate limit público de MusicBrainz es 1 req/s

ARTISTAS = {
    "extremoduro": ("Extremoduro", "f59163ba-1a7a-4349-b0fd-fb9582ebe333"),
    "robe": ("Robe", "b435c75d-25e8-464c-8b82-12ca0eaec926"),
}

# Packs de reedición y recopilaciones de sello sin contenido propio. La decisión
# (01-08-2026) fue dejarlos fuera: no aportan material y generarían páginas que
# compiten con las de los discos que recopilan.
FUERA_PACKS = ("discografía básica", "discografia basica")


@dataclass
class Lanzamiento:
    titulo: str
    mbid: str
    fecha: str
    tipo_primario: str
    tipos_secundarios: tuple[str, ...]
    status: str | None = None
    sello: str | None = None
    pistas: int | None = None
    veredicto: str = ""
    motivo: str = ""
    slug_catalogo: str | None = None

    @property
    def anio(self) -> int | None:
        return int(self.fecha[:4]) if self.fecha[:4].isdigit() else None

    @property
    def clase(self) -> str:
        sec = {s.lower() for s in self.tipos_secundarios}
        if "demo" in sec:
            return "demo"
        if "live" in sec:
            return "live"
        if "compilation" in sec:
            return "compilation"
        if self.tipo_primario == "Single":
            return "single"
        if self.tipo_primario == "EP":
            return "ep"
        return "studio"


def _get(path: str, params: dict) -> dict:
    params = {**params, "fmt": "json"}
    url = f"{MB}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


def release_groups(mbid: str) -> list[Lanzamiento]:
    data = _get("release-group", {"artist": mbid, "limit": 100})
    out = []
    for rg in data.get("release-groups", []):
        out.append(Lanzamiento(
            titulo=rg["title"], mbid=rg["id"],
            fecha=rg.get("first-release-date") or "",
            tipo_primario=rg.get("primary-type") or "?",
            tipos_secundarios=tuple(rg.get("secondary-types") or []),
        ))
    return sorted(out, key=lambda r: r.fecha or "zzzz")


def detalle_release(l: Lanzamiento) -> None:
    """Status, sello y nº de pistas de la release MÁS ANTIGUA del grupo."""
    try:
        data = _get("release", {"release-group": l.mbid, "inc": "labels+recordings",
                                "limit": 5})
    except Exception as exc:  # noqa: BLE001
        l.motivo = f"no se pudo leer la release: {exc}"
        return
    rs = sorted(data.get("releases", []), key=lambda r: r.get("date") or "zzzz")
    if not rs:
        l.motivo = "el release-group no tiene ninguna release"
        return
    r = rs[0]
    l.status = r.get("status")
    sellos = [li.get("label", {}).get("name") for li in r.get("label-info", [])]
    l.sello = ", ".join(s for s in sellos if s) or None
    l.pistas = sum(len(m.get("tracks", [])) for m in r.get("media", []))


def catalogo_actual() -> dict[str, dict[str, str]]:
    """{artist_slug: {titulo_normalizado: album_slug}} desde la BD."""
    db = SessionLocal()
    try:
        out: dict[str, dict[str, str]] = {}
        rows = db.execute(select(Album, Artist).join(Artist, Album.artist_id == Artist.id)).all()
        for album, artist in rows:
            out.setdefault(artist.slug, {})[kw_norm(album.title)] = album.slug
        return out
    finally:
        db.close()


def dictaminar(l: Lanzamiento, en_catalogo: dict[str, str]) -> None:
    norm = kw_norm(l.titulo)

    # Los packs se descartan ANTES de cotejar con el catálogo. Si no, la
    # contención los daba por presentes: «rock transgresivo» está literalmente
    # dentro de «discografía básica: rock transgresivo / somos unos animales /
    # deltoya», y los tres packs salían como YA ESTÁ.
    if any(p in norm for p in FUERA_PACKS):
        l.veredicto = "EXCLUIR"
        l.motivo = "pack de reedición sin contenido propio (decisión 01-08-2026)"
        return

    for titulo_cat, slug in en_catalogo.items():
        # La contención solo vale si los dos títulos son de tamaño comparable.
        # Sin ese freno, un recopilatorio que enumera discos en su título casa
        # con cualquiera de ellos.
        comparables = len(titulo_cat) >= 0.6 * len(norm)
        if norm == titulo_cat or (len(titulo_cat) > 8 and titulo_cat in norm and comparables):
            l.slug_catalogo = slug
            l.veredicto = "YA ESTÁ"
            l.motivo = f"ya en catálogo como «{slug}»"
            return

    if l.status != "Official":
        l.veredicto = "REVISAR"
        l.motivo = f"status T1 = {l.status or 'desconocido'}, no acreditado como oficial"
        return

    if not l.pistas:
        l.veredicto = "REVISAR"
        l.motivo = "sin tracklist en T1 — no se inventa"
        return

    l.veredicto = "ALTA"
    l.motivo = f"oficial ({l.sello or 'sello n/d'}), {l.pistas} pistas"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="/app/kw_out/DISCOGRAFIA.md")
    args = ap.parse_args()

    catalogo = catalogo_actual()
    consultado = datetime.now(timezone.utc).isoformat(timespec="seconds")
    todo: dict[str, list[Lanzamiento]] = {}

    for slug, (nombre, mbid) in ARTISTAS.items():
        print(f"Consultando MusicBrainz: {nombre}…")
        ls = release_groups(mbid)
        time.sleep(PAUSA)
        for l in ls:
            detalle_release(l)
            time.sleep(PAUSA)
            dictaminar(l, catalogo.get(slug, {}))
            print(f"  {l.veredicto:<8} {l.fecha[:10]:<11} {l.clase:<12} {l.titulo}")
        todo[slug] = ls

    lineas = [
        "# Barrido de discografía — censo canónico cruzado",
        "",
        f"Generado: {consultado}",
        "",
        "Nada se propone como ALTA sin `status=Official` en MusicBrainz y tracklist",
        "real. Lo no acreditado sale como REVISAR con su motivo: no se rellena a ojo.",
        "",
    ]
    for slug, (nombre, mbid) in ARTISTAS.items():
        ls = todo[slug]
        lineas += [
            f"## {nombre}",
            "",
            f"MBID `{mbid}` · {len(ls)} lanzamientos en T1 · "
            f"{len(catalogo.get(slug, {}))} en el catálogo actual",
            "",
            "| Veredicto | Fecha | Clase | Título | Status | Sello | Pistas | Motivo |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for l in ls:
            lineas.append(
                f"| **{l.veredicto}** | {l.fecha[:10] or '—'} | {l.clase} | "
                f"{l.titulo} | {l.status or '—'} | {l.sello or '—'} | "
                f"{l.pistas if l.pistas is not None else '—'} | {l.motivo} |"
            )
        lineas.append("")
        altas = [l for l in ls if l.veredicto == "ALTA"]
        if altas:
            lineas += [f"### Propuestas de alta ({len(altas)})", ""]
            for l in altas:
                lineas.append(
                    f"- **{l.titulo}** ({l.anio or '—'}, {l.clase}) — "
                    f"{l.sello or 'sello n/d'}, {l.pistas} pistas · MBID `{l.mbid}`"
                )
            lineas.append("")

    lineas += [
        "## Fuentes",
        "",
        "| Dato | Fuente | Filtro | Fecha de extracción |",
        "|---|---|---|---|",
        f"| Lanzamientos, tipo y fecha | MusicBrainz `ws/2/release-group` | "
        f"`artist=<MBID>`, limit 100 | {consultado} |",
        f"| Status, sello y nº de pistas | MusicBrainz `ws/2/release` | "
        f"`release-group=<MBID>`, `inc=labels+recordings`, release más antigua | {consultado} |",
        "| Catálogo actual | BD del proyecto (`albums` × `artists`) | — | "
        f"{consultado} |",
        "",
        "La release elegida de cada grupo es la **más antigua**, que es la edición",
        "original y no una reedición posterior con otro sello o tracklist.",
        "",
    ]

    from pathlib import Path
    Path(args.out).write_text("\n".join(lineas), encoding="utf-8")
    print(f"\nInforme: {args.out}")
    for slug in todo:
        c = {}
        for l in todo[slug]:
            c[l.veredicto] = c.get(l.veredicto, 0) + 1
        print(f"  {slug}: {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
