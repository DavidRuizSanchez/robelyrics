"""Acredita la identidad externa (Q-ID de Wikidata, MBID de MusicBrainz) de nuestras
entidades. Plan de relaciones (18-11-2026), PR B. Nunca por nombre suelto:

1. **Sitelink.** La entidad tiene `wikipedia_url`: el Q-ID es el `wikibase_item` de esa
   página de eswiki (mismo método que `seed_persons`), y se comprueba de vuelta que el
   sitelink eswiki de ese Q-ID es esa página.
2. **Anclaje.** Una entidad YA acreditada declara en Wikidata una relación (miembro,
   lugar de nacimiento, lugar de fundación…) con un Q-ID cuya etiqueta es EXACTAMENTE el
   nombre de una entidad nuestra del tipo compatible que no tiene Q-ID. Ejemplo: Platero y
   Tú (Q263632) declara P527 = Q9016238 «Juantxu Olano», y nuestra persona
   `juantxu-mongol-olano` se llama así. Un lugar exige además estar en España (P17 = Q29).
   Si dos entidades nuestras casan con la misma etiqueta, no se acredita ninguna.
3. **MBID desde Wikidata.** Para lo que tiene Q-ID y no MBID: P434 (artista), P966
   (sello), P436 (grupo de lanzamiento), P435 (obra). Solo vale si MusicBrainz enlaza de
   vuelta a ese mismo Q-ID (`url-rels`).

Genera YAML de filas `sameAs` (T1 de Wikidata o MusicBrainz) para `seed_relaciones`, que
vuelve a validarlo todo. No escribe en la BD.

    python -m scripts.relaciones.identidades --salida /tmp/id --verificado-por "…"
"""
from __future__ import annotations

import argparse
import json
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

import httpx
import yaml

from app.db.models import Album, Band, EntityRelation, Person, Place
from app.db.session import SessionLocal
from scripts.relaciones.descubrir import (
    MAPA_WD,
    PAUSA_MB,
    UA,
    _etiqueta,
    _mb,
    _objetivos,
    _qid,
    _ref,
    wd_entidades,
)

MB = "https://musicbrainz.org/ws/2"
# Tipo de nodo esperado → tipos nuestros compatibles.
COMPATIBLES = {"Person": ("person",), "MusicGroup": ("band",), "Place": ("place",),
               "Organization": ("label",)}
PROP_MB = {"person": ("P434", "artist"), "band": ("P434", "artist"),
           "label": ("P966", "label"), "album": ("P436", "release-group")}


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _sameas_existentes(db) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for f in db.query(EntityRelation).filter(EntityRelation.predicate == "sameAs").all():
        r = _ref(db, f.subject_type, f.subject_id)
        if r and isinstance(f.object_literal, str):
            out[r].add(f.object_literal)
    return out


def _qid_de(db, ref: str, sameas: dict) -> str | None:
    tipo, slug = ref.split(":", 1)
    if tipo == "person":
        p = db.query(Person).filter(Person.slug == slug).first()
        if p and p.wikidata_id:
            return p.wikidata_id
    if tipo in ("band", "label"):
        b = db.query(Band).filter(Band.slug == slug).first()
        if b and b.wikidata_id:
            return b.wikidata_id
    for u in sameas.get(ref, ()):
        q = _qid(u)
        if q:
            return q
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--verificado-por", required=True)
    args = ap.parse_args()

    db = SessionLocal()
    sameas = _sameas_existentes(db)
    filas: list[dict] = []
    informe: list[dict] = []

    # Todas nuestras entidades de los tipos con identidad, y sus nombres.
    entidades: dict[str, dict] = {}
    for p in db.query(Person).all():
        entidades[f"person:{p.slug}"] = {"nombres": {_norm(p.stage_name), _norm(p.full_name)} - {""},
                                         "wikipedia": p.wikipedia_url}
    for b in db.query(Band).all():
        t = "label" if b.kind == "label" else "band"
        entidades[f"{t}:{b.slug}"] = {"nombres": {_norm(b.name)}, "wikipedia": b.wikipedia_url}
    for pl in db.query(Place).all():
        entidades[f"place:{pl.slug}"] = {"nombres": {_norm(pl.name)}, "wikipedia": None}
    for al in db.query(Album).all():
        entidades[f"album:{al.artist.slug}/{al.slug}"] = {"nombres": set(), "wikipedia": None}
    qid_de = {r: _qid_de(db, r, sameas) for r in entidades}
    nuevos_qid: dict[str, tuple[str, dict]] = {}

    def fila_sameas(ref: str, url: str, fuente: dict) -> None:
        if url in sameas.get(ref, ()):
            return
        filas.append({"sujeto": ref, "predicado": "sameAs", "objeto": url,
                      "estado": "verificada", "verificado_por": args.verificado_por,
                      "fuentes": [fuente]})
        sameas.setdefault(ref, set()).add(url)

    with httpx.Client(timeout=40, headers=UA, follow_redirects=True) as http:
        # ---- 1. Sitelink ----
        for ref, e in entidades.items():
            if qid_de.get(ref) or not e.get("wikipedia"):
                continue
            titulo = unquote(e["wikipedia"].rsplit("/wiki/", 1)[-1])
            r = http.get("https://es.wikipedia.org/w/api.php", params={
                "action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                "redirects": 1, "titles": titulo, "format": "json"})
            pages = (r.json().get("query") or {}).get("pages") or {}
            q = next((pg.get("pageprops", {}).get("wikibase_item") for pg in pages.values()), None)
            time.sleep(0.3)
            if not q:
                continue
            ent = wd_entidades(http, [q]).get(q, {})
            sl = ((ent.get("sitelinks") or {}).get("eswiki") or {}).get("title", "")
            if _norm(sl) != _norm(titulo.replace("_", " ")):
                informe.append({"ref": ref, "via": "sitelink", "qid": q, "resultado":
                                f"descartado: el sitelink de {q} es «{sl}»"})
                continue
            nuevos_qid[ref] = (q, {"kind": "wikidata", "tier": "T1",
                                   "url": f"https://www.wikidata.org/wiki/{q}",
                                   "evidencia": f"sitelink eswiki «{sl}» = wikipedia_url de la ficha"})

        # ---- 2. Anclaje ----
        acreditadas = {r: q for r, q in qid_de.items() if q}
        ents = wd_entidades(http, sorted(set(acreditadas.values())))
        alcanzados: dict[str, list[str]] = defaultdict(list)   # qid → ["Q… P…"]
        tipo_esperado: dict[str, str] = {}
        for ref, q in acreditadas.items():
            ent = ents.get(q, {})
            tipo = ref.split(":")[0]
            pares = [(p, nt) for (t, p), (_, nt) in MAPA_WD.items() if t == tipo]
            if tipo == "band":
                pares.append(("P527", "Person"))
            if tipo == "person":
                pares.append(("P463", "MusicGroup"))
            for prop, nodo_tipo in pares:
                for oq in _objetivos(ent, prop):
                    alcanzados[oq].append(f"{q} {prop}")
                    tipo_esperado.setdefault(oq, nodo_tipo)
        candidatos = sorted(set(alcanzados) - set(acreditadas.values()))
        cand_ents = wd_entidades(http, candidatos)
        por_nombre: dict[tuple, list[str]] = defaultdict(list)
        for ref, e in entidades.items():
            if qid_de.get(ref) or ref in nuevos_qid:
                continue
            for n in e["nombres"]:
                por_nombre[(ref.split(":")[0], n)].append(ref)
        for oq in candidatos:
            ent = cand_ents.get(oq, {})
            etiqueta = _etiqueta(ent)
            if not etiqueta:
                continue
            for tipo in COMPATIBLES.get(tipo_esperado.get(oq, ""), ()):
                refs = por_nombre.get((tipo, _norm(etiqueta)), [])
                if len(refs) != 1:
                    if len(refs) > 1:
                        informe.append({"ref": " / ".join(refs), "via": "anclaje", "qid": oq,
                                        "resultado": "descartado: varias entidades con ese nombre"})
                    continue
                ref = refs[0]
                if tipo == "place" and "Q29" not in _objetivos(ent, "P17"):
                    informe.append({"ref": ref, "via": "anclaje", "qid": oq,
                                    "resultado": "descartado: el lugar no está en España"})
                    continue
                nuevos_qid[ref] = (oq, {
                    "kind": "wikidata", "tier": "T1", "url": f"https://www.wikidata.org/wiki/{oq}",
                    "evidencia": (f"etiqueta «{etiqueta}» = nombre de la ficha; anclado desde "
                                  + ", ".join(sorted(set(alcanzados[oq]))[:4]))})

        for ref, (q, fuente) in sorted(nuevos_qid.items()):
            fila_sameas(ref, f"https://www.wikidata.org/wiki/{q}", fuente)
            qid_de[ref] = q
            informe.append({"ref": ref, "via": fuente["evidencia"][:40], "qid": q,
                            "resultado": "acreditado"})

        # ---- 3. MBID desde Wikidata, con vuelta ----
        con_qid = {r: q for r, q in qid_de.items() if q and r.split(":")[0] in PROP_MB}
        todas = wd_entidades(http, sorted(set(con_qid.values())))
        for ref, q in sorted(con_qid.items()):
            if any(_mb(u) for u in sameas.get(ref, ())):
                continue
            prop, entidad_mb = PROP_MB[ref.split(":")[0]]
            for mbid in [c["mainsnak"]["datavalue"]["value"]
                         for c in (todas.get(q, {}).get("claims") or {}).get(prop, [])
                         if (c.get("mainsnak") or {}).get("datavalue")][:1]:
                r = http.get(f"{MB}/{entidad_mb}/{mbid}", params={"inc": "url-rels",
                                                                 "fmt": "json"})
                time.sleep(PAUSA_MB)
                if r.status_code != 200:
                    continue
                vuelta = any(q == _qid((rel.get("url") or {}).get("resource"))
                             for rel in r.json().get("relations") or [])
                if not vuelta:
                    informe.append({"ref": ref, "via": "mbid", "qid": q,
                                    "resultado": f"descartado: {mbid} no enlaza de vuelta"})
                    continue
                fila_sameas(ref, f"https://musicbrainz.org/{entidad_mb}/{mbid}", {
                    "kind": "musicbrainz", "tier": "T1",
                    "url": f"https://musicbrainz.org/{entidad_mb}/{mbid}",
                    "evidencia": f"{prop} de {q} = {mbid}; MusicBrainz enlaza de vuelta a {q}"})
                informe.append({"ref": ref, "via": "mbid", "qid": q, "resultado": f"MB {mbid}"})

        # ---- 4. Anclaje por MusicBrainz: miembros y músicos de un artista acreditado ----
        # Los músicos de Robe y de Extremoduro casi nunca tienen Wikipedia, pero sí
        # están en MusicBrainz como miembros o músicos de un artista que ya tenemos
        # acreditado. Misma regla que el anclaje de Wikidata: nombre idéntico y una
        # sola entidad nuestra con ese nombre.
        sin_mb = {r: e for r, e in entidades.items() if r.startswith("person:")
                  and not any(_mb(u) for u in sameas.get(r, ()))}
        por_nombre_mb: dict[str, list[str]] = defaultdict(list)
        for r, e in sin_mb.items():
            for n in e["nombres"]:
                por_nombre_mb[n].append(r)
        anclas = sorted({(ref, m[1]) for ref, urls in sameas.items() for u in urls
                         if (m := _mb(u)) and m[0] == "artist"})
        tipos_rel = {"member of band", "supporting musician", "instrumental supporting musician",
                     "vocal supporting musician", "collaboration"}
        for ref_ancla, mbid_ancla in anclas:
            r = http.get(f"{MB}/artist/{mbid_ancla}", params={"inc": "artist-rels", "fmt": "json"})
            time.sleep(PAUSA_MB)
            if r.status_code != 200:
                continue
            for rel in r.json().get("relations") or []:
                if rel.get("type") not in tipos_rel:
                    continue
                otro = rel.get("artist") or {}
                refs = [x for x in por_nombre_mb.get(_norm(otro.get("name")), [])
                        if not any(_mb(u) for u in sameas.get(x, ()))]
                if len(refs) != 1 or not otro.get("id"):
                    continue
                url = f"https://musicbrainz.org/artist/{otro['id']}"
                fila_sameas(refs[0], url, {
                    "kind": "musicbrainz", "tier": "T1", "url": url,
                    "evidencia": (f"nombre «{otro.get('name')}» = nombre de la ficha; anclado "
                                  f"desde {ref_ancla} (MusicBrainz {mbid_ancla}, "
                                  f"«{rel.get('type')}»)")})
                informe.append({"ref": refs[0], "via": f"anclaje MB desde {ref_ancla}",
                                "qid": otro["id"], "resultado": "acreditado (MB)"})

        # ---- 5. Anclaje por los créditos de nuestros discos acreditados (método tanda2) ----
        releases = sorted({(ref, m[1]) for ref, urls in sameas.items() if ref.startswith("album:")
                           for u in urls if (m := _mb(u)) and m[0] == "release"})
        # Nuestros discos están acreditados por su grupo de lanzamiento: sus ediciones
        # oficiales (las 3 primeras) son las que traen los créditos.
        for ref_disco, rgid in sorted({(ref, m[1]) for ref, urls in sameas.items()
                                       if ref.startswith("album:") for u in urls
                                       if (m := _mb(u)) and m[0] == "release-group"}):
            r = http.get(f"{MB}/release-group/{rgid}", params={"inc": "releases", "fmt": "json"})
            time.sleep(PAUSA_MB)
            if r.status_code != 200:
                continue
            oficiales = [x for x in r.json().get("releases") or []
                         if (x.get("status") or "Official") == "Official"]
            oficiales.sort(key=lambda x: x.get("date") or "9999")
            releases += [(ref_disco, x["id"]) for x in oficiales[:3]]
        for ref_disco, rid in releases:
            r = http.get(f"{MB}/release/{rid}", params={
                "inc": "artist-rels recordings recording-level-rels artist-credits",
                "fmt": "json"})
            time.sleep(PAUSA_MB)
            if r.status_code != 200:
                continue
            datos = r.json()
            creditos = list(datos.get("relations") or [])
            for medio in datos.get("media") or []:
                for pista in medio.get("tracks") or []:
                    creditos += (pista.get("recording") or {}).get("relations") or []
            for rel in creditos:
                otro = rel.get("artist") or {}
                if not otro.get("id"):
                    continue
                refs = [x for x in por_nombre_mb.get(_norm(otro.get("name")), [])
                        if not any(_mb(u) for u in sameas.get(x, ()))]
                if len(refs) != 1:
                    continue
                url = f"https://musicbrainz.org/artist/{otro['id']}"
                fila_sameas(refs[0], url, {
                    "kind": "musicbrainz", "tier": "T1", "url": url,
                    "evidencia": (f"nombre «{otro.get('name')}» = nombre de la ficha; acreditado "
                                  f"en {ref_disco} (MusicBrainz release {rid}, «{rel.get('type')}»)")})
                informe.append({"ref": refs[0], "via": f"créditos de {ref_disco}",
                                "qid": otro["id"], "resultado": "acreditado (MB)"})

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "identidades.yaml").write_text(
        yaml.safe_dump({"relaciones": filas}, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8")
    (salida / "identidades_informe.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"sameAs_nuevas": len(filas),
                      "wikidata": sum(1 for f in filas if "wikidata" in f["objeto"]),
                      "musicbrainz": sum(1 for f in filas if "musicbrainz" in f["objeto"]),
                      "descartes": sum(1 for i in informe if i["resultado"].startswith("descartado"))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
