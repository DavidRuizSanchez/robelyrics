"""Descubre relaciones entre nuestras entidades en Wikidata y MusicBrainz.

Plan de relaciones (18-11-2026), «ejecución 1». Para cada entidad con su identidad
ACREDITADA (Q-ID en la columna o `sameAs` verificada a Wikidata/MusicBrainz) lee sus
relaciones y resuelve la otra punta **por identificador, nunca por nombre**:

- Si la otra punta es nuestra → relación entre dos entidades de la web.
- Si no lo es → nodo literal con su `sameAs` (sale con nombre en el JSON-LD) y,
  además, PROPUESTA de entidad nueva (CSV aparte), que decide una persona.

Cada candidata lleva su fuente T1 (la declaración de Wikidata o la relación de
MusicBrainz, con URL). Las dos bases se funden: si las dos dicen lo mismo, la fila lleva
las dos fuentes, y MusicBrainz aporta rol y fechas.

No escribe en la BD: genera YAML para `seed_relaciones` (que valida todo otra vez) y
el CSV de propuestas.

    python -m scripts.relaciones.descubrir --salida /tmp/rel --verificado-por "…"
    python -m scripts.relaciones.descubrir --solo person:fito-cabrales,band:marea …
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import httpx
import yaml

from app.db.models import Album, Artist, Band, EntityRelation, Person, Place, Song
from app.db.session import SessionLocal

UA = {"User-Agent": "EntreInteriores/1.0 (https://entreinteriores.com)"}
WD_API = "https://www.wikidata.org/w/api.php"
MB = "https://musicbrainz.org/ws/2"
PAUSA_MB = 1.2
PAUSA_WD = 0.3

QID_URL = re.compile(r"wikidata\.org/(?:wiki|entity)/(Q\d+)")
MB_URL = re.compile(r"musicbrainz\.org/(artist|label|release-group|release|work)/([0-9a-f-]{36})")

# (tipo de sujeto, propiedad de Wikidata) → (predicado schema.org, @type del nodo si la
# otra punta no es nuestra). Solo lo que schema.org admite para ese tipo; lo familiar,
# fuera. `P527` (tiene como parte) se guarda al revés: persona memberOf grupo.
MAPA_WD = {
    ("person", "P463"): ("memberOf", "MusicGroup"),
    ("person", "P69"): ("alumniOf", "EducationalOrganization"),
    ("person", "P108"): ("worksFor", "Organization"),
    ("person", "P19"): ("birthPlace", "Place"),
    ("person", "P20"): ("deathPlace", "Place"),
    ("band", "P112"): ("founder", "Person"),
    ("band", "P740"): ("foundingLocation", "Place"),
    ("label", "P112"): ("founder", "Person"),
    ("label", "P740"): ("foundingLocation", "Place"),
    ("label", "P159"): ("location", "Place"),
    ("album", "P162"): ("producer", "Person"),
}
# Instrumentos y voces de MusicBrainz → rol en español.
ROL_ES = {
    "guitar": "guitarra", "electric guitar": "guitarra eléctrica", "bass guitar": "bajo",
    "bass": "bajo", "electric bass guitar": "bajo eléctrico", "drums": "batería",
    "drums (drum set)": "batería", "lead vocals": "voz", "vocal": "voz",
    "vocals": "voz", "keyboard": "teclados", "keyboards": "teclados",
    "saxophone": "saxofón", "violin": "violín", "piano": "piano", "founder": "fundador",
    "original": "miembro original", "percussion": "percusión", "trumpet": "trompeta",
}


# Extremoduro y Robe (el proyecto): su formación manda en `band_memberships`. Como
# nodo literal saldría un «Robe» sin @id junto al artista de verdad.
INTERNOS = {"Q2311472", "Q123516175"}
PAISES = {"Q29"}


def es_lugar(ent: dict, qid: str) -> bool:
    """Un `Place` tiene coordenadas (P625) o país (P17), y no es un país.

    Medido el 18-11-2026: La Fuga declaraba P740 = «Reineta Panera», una variedad de
    manzana; y Cantera, P19 = España."""
    claims = ent.get("claims") or {}
    if qid in PAISES or "Q6256" in _objetivos(ent, "P31"):
        return False
    return bool(claims.get("P625") or claims.get("P17"))


def _qid(u) -> str | None:
    m = QID_URL.search(u or "") if isinstance(u, str) else None
    return m.group(1) if m else None


def _mb(u) -> tuple[str, str] | None:
    m = MB_URL.search(u or "") if isinstance(u, str) else None
    return (m.group(1), m.group(2)) if m else None


def _ref(db, tipo: str, ident: int) -> str | None:
    if tipo in ("band", "label"):
        b = db.get(Band, ident)
        return b and f"{tipo}:{b.slug}"
    if tipo == "album":
        a = db.get(Album, ident)
        return a and f"album:{a.artist.slug}/{a.slug}"
    if tipo == "song":
        s = db.get(Song, ident)
        return s and f"song:{s.album.artist.slug}/{s.album.slug}/{s.slug}"
    modelo = {"person": Person, "artist": Artist, "place": Place}.get(tipo)
    fila = db.get(modelo, ident) if modelo else None
    return fila and f"{tipo}:{fila.slug}"


def indices(db) -> tuple[dict, dict, dict]:
    """Q-ID → ref, MBID → ref y ref → (qid, mbid) de todo lo acreditado."""
    por_qid: dict[str, str] = {}
    por_mbid: dict[str, str] = {}
    ident: dict[str, dict] = defaultdict(dict)
    for p in db.query(Person).filter(Person.wikidata_id.isnot(None)).all():
        if p.wikidata_id:
            r = f"person:{p.slug}"
            por_qid[p.wikidata_id] = r
            ident[r]["qid"] = p.wikidata_id
    for b in db.query(Band).filter(Band.wikidata_id.isnot(None)).all():
        if b.wikidata_id:
            r = f"{'label' if b.kind == 'label' else 'band'}:{b.slug}"
            por_qid[b.wikidata_id] = r
            ident[r]["qid"] = b.wikidata_id
    for fila in (db.query(EntityRelation).filter(EntityRelation.predicate == "sameAs",
                                                  EntityRelation.status == "verificada").all()):
        r = _ref(db, fila.subject_type, fila.subject_id)
        if not r:
            continue
        q = _qid(fila.object_literal)
        if q:
            por_qid.setdefault(q, r)
            ident[r].setdefault("qid", q)
        m = _mb(fila.object_literal)
        if m:
            por_mbid.setdefault(m[1], r)
            ident[r].setdefault("mb", m)
    return por_qid, por_mbid, ident


def existentes(db) -> set[tuple]:
    """(sujeto, predicado, objeto) ya cargados, para no proponer lo que hay."""
    out = set()
    for f in db.query(EntityRelation).filter(EntityRelation.predicate != "sameAs").all():
        s = _ref(db, f.subject_type, f.subject_id)
        if f.object_id is not None:
            o = _ref(db, f.object_type, f.object_id)
        else:
            lit = f.object_literal or {}
            o = "lit:" + (_qid(lit.get("sameAs")) or lit.get("name", "") if isinstance(lit, dict)
                          else str(lit))
        out.add((s, f.predicate, o))
        out.add((s, f.predicate, "*"))  # el sujeto ya tiene ese predicado
    return out


# --------------------------------------------------------------------------- #
# Wikidata
# --------------------------------------------------------------------------- #
def wd_entidades(http: httpx.Client, qids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(qids), 50):
        r = http.get(WD_API, params={"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                                     "props": "claims|labels|sitelinks", "languages": "es|en",
                                     "format": "json"})
        r.raise_for_status()
        out.update(r.json().get("entities", {}))
        time.sleep(PAUSA_WD)
    return out


def _etiqueta(ent: dict) -> str | None:
    labels = ent.get("labels") or {}
    return (labels.get("es") or labels.get("en") or {}).get("value")


def _objetivos(ent: dict, prop: str) -> list[str]:
    out = []
    for c in (ent.get("claims") or {}).get(prop, []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


# --------------------------------------------------------------------------- #
# MusicBrainz
# --------------------------------------------------------------------------- #
def mb_get(http: httpx.Client, ruta: str, params: dict) -> dict | None:
    for intento in range(4):
        r = http.get(f"{MB}/{ruta}", params={**params, "fmt": "json"})
        if r.status_code == 503:
            time.sleep(3 * (intento + 1))
            continue
        time.sleep(PAUSA_MB)
        if r.status_code != 200:
            return None
        return r.json()
    return None


def _rol(attrs: list[str]) -> str | None:
    vistos = [ROL_ES.get(a.lower(), a) for a in attrs if a]
    return ", ".join(dict.fromkeys(vistos)) or None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", required=True, help="carpeta para el YAML y el CSV")
    ap.add_argument("--solo", default="", help="refs separadas por comas")
    ap.add_argument("--verificado-por", default="")
    # «pendiente» para lo que corre solo (cron semanal): entra en la cola del panel y
    # no se publica hasta que alguien lo aprueba. «verificada» exige --verificado-por.
    ap.add_argument("--estado", choices=("verificada", "pendiente"), default="pendiente")
    ap.add_argument("--sin-mb", action="store_true")
    args = ap.parse_args()
    if args.estado == "verificada" and not args.verificado_por:
        ap.error("--estado verificada necesita --verificado-por")
    solo = {s.strip() for s in args.solo.split(",") if s.strip()}

    db = SessionLocal()
    por_qid, por_mbid, ident = indices(db)
    ya = existentes(db)
    sujetos = {r: v for r, v in ident.items() if (not solo or r in solo)
               and r.split(":")[0] in ("person", "band", "label", "album")}
    print(f"{len(sujetos)} sujetos con identidad · {len(por_qid)} Q-ID · {len(por_mbid)} MBID")

    filas: dict[tuple, dict] = {}
    propuestas: dict[str, dict] = {}
    rechazos: list[str] = []
    destinos: dict[str, dict] = {}

    def anotar(sujeto, pred, objeto, fuente, nodo_tipo=None, nombre=None, qid=None,
               rol=None, desde=None, hasta=None):
        tipo_suj = sujeto.split(":")[0]
        if objeto is None:
            if not (nombre and qid) or qid in INTERNOS:
                return
            if nodo_tipo == "Place" and not es_lugar(destinos.get(qid, {}), qid):
                rechazos.append(f"{sujeto} {pred} {qid} ({nombre}): no es un lugar o es un país")
                return
            obj_val = {"@type": nodo_tipo, "name": nombre,
                       "sameAs": f"https://www.wikidata.org/wiki/{qid}"}
            clave_obj = f"lit:{qid}"
            prop = propuestas.setdefault(qid, {"qid": qid, "nombre": nombre, "tipo": nodo_tipo,
                                               "relaciones": []})
            prop["relaciones"].append(f"{sujeto} {pred}")
        else:
            if objeto == sujeto:
                return
            obj_val, clave_obj = objeto, objeto
        # Lo familiar está fuera del mapa; lo de Extremoduro y Robe manda en sus tablas.
        if pred in ("memberOf", "member", "founder") and (
                sujeto.startswith("artist:") or str(clave_obj).startswith("artist:")):
            return
        if (sujeto, pred, clave_obj) in ya:
            return
        if pred in ("birthPlace", "deathPlace", "foundingLocation") and (sujeto, pred, "*") in ya:
            return
        k = (sujeto, pred, clave_obj)
        fila = filas.setdefault(k, {"sujeto": sujeto, "predicado": pred, "objeto": obj_val,
                                    "estado": args.estado, "fuentes": []})
        if args.estado == "verificada":
            fila["verificado_por"] = args.verificado_por
        if rol and not fila.get("rol"):
            fila["rol"] = rol
        if desde and not fila.get("desde"):
            fila["desde"] = desde
        if hasta and not fila.get("hasta"):
            fila["hasta"] = hasta
        if fuente not in fila["fuentes"]:
            fila["fuentes"].append(fuente)
        _ = tipo_suj

    with httpx.Client(timeout=40, headers=UA, follow_redirects=True) as http:
        # ---- Wikidata ----
        qids = sorted({v["qid"] for v in sujetos.values() if v.get("qid")})
        ents = wd_entidades(http, qids)
        destino_qids = set()
        for r, v in sujetos.items():
            ent = ents.get(v.get("qid") or "", {})
            tipo = r.split(":")[0]
            for (t, prop), _ in MAPA_WD.items():
                if t == tipo:
                    destino_qids.update(_objetivos(ent, prop))
            if tipo == "band":
                destino_qids.update(_objetivos(ent, "P527"))
        destinos = wd_entidades(http, sorted(destino_qids - set(ents)))
        destinos.update(ents)
        etiquetas = {q: _etiqueta(e) for q, e in destinos.items()}

        for r, v in sujetos.items():
            q = v.get("qid")
            ent = ents.get(q or "", {})
            if not ent:
                continue
            tipo = r.split(":")[0]
            for (t, prop), (pred, nodo_tipo) in MAPA_WD.items():
                if t != tipo:
                    continue
                for oq in _objetivos(ent, prop):
                    fuente = {"kind": "wikidata", "tier": "T1",
                              "url": f"https://www.wikidata.org/wiki/{q}#{prop}",
                              "evidencia": f"{prop} = {oq} ({etiquetas.get(oq) or '?'})"}
                    anotar(r, pred, por_qid.get(oq), fuente, nodo_tipo, etiquetas.get(oq), oq)
            if tipo == "band":
                # P527 (tiene como parte): la persona es memberOf el grupo.
                for oq in _objetivos(ent, "P527"):
                    fuente = {"kind": "wikidata", "tier": "T1",
                              "url": f"https://www.wikidata.org/wiki/{q}#P527",
                              "evidencia": f"P527 = {oq} ({etiquetas.get(oq) or '?'})"}
                    persona = por_qid.get(oq)
                    if persona and persona.startswith("person:"):
                        anotar(persona, "memberOf", r, fuente)
                    elif not persona:
                        anotar(r, "member", None, fuente, "Person", etiquetas.get(oq), oq)

        # ---- MusicBrainz: «member of band», con rol y fechas ----
        if not args.sin_mb:
            for r, v in sujetos.items():
                mb = v.get("mb")
                if not mb or mb[0] != "artist":
                    continue
                datos = mb_get(http, f"artist/{mb[1]}", {"inc": "artist-rels"})
                if not datos:
                    continue
                for rel in datos.get("relations") or []:
                    if rel.get("type") != "member of band":
                        continue
                    otro = (rel.get("artist") or {}).get("id")
                    otro_ref = por_mbid.get(otro)
                    attrs = rel.get("attributes") or []
                    fuente = {"kind": "musicbrainz", "tier": "T1",
                              "url": f"https://musicbrainz.org/artist/{mb[1]}",
                              "evidencia": f"member of band ({rel.get('direction')}) "
                                           f"{(rel.get('artist') or {}).get('name')}"
                                           + (f": {', '.join(attrs)}" if attrs else "")}
                    desde, hasta = rel.get("begin"), rel.get("end")
                    if rel.get("direction") == "forward" and r.startswith("person:") and otro_ref:
                        anotar(r, "memberOf", otro_ref, fuente, rol=_rol(attrs),
                               desde=desde, hasta=hasta)
                    elif rel.get("direction") == "backward" and otro_ref \
                            and otro_ref.startswith("person:") and r.startswith("band:"):
                        anotar(otro_ref, "memberOf", r, fuente, rol=_rol(attrs),
                               desde=desde, hasta=hasta)

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    lista = sorted(filas.values(), key=lambda f: (f["sujeto"], f["predicado"], str(f["objeto"])))
    (salida / "relaciones_candidatas.yaml").write_text(
        yaml.safe_dump({"relaciones": lista}, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8")
    with open(salida / "propuestas_entidades.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["qid", "nombre", "tipo", "n_relaciones", "relaciones"])
        for p in sorted(propuestas.values(), key=lambda p: -len(p["relaciones"])):
            w.writerow([p["qid"], p["nombre"], p["tipo"], len(p["relaciones"]),
                        " | ".join(p["relaciones"])])
    por_pred = defaultdict(int)
    for f in lista:
        por_pred[f["predicado"]] += 1
    (salida / "rechazos.txt").write_text("\n".join(rechazos) + "\n", encoding="utf-8")
    print(json.dumps({"candidatas": len(lista), "por_predicado": por_pred,
                      "propuestas_entidades": len(propuestas), "rechazos": len(rechazos)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
