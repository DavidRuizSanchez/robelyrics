"""Relaciones del JSON-LD con fuente (`entity_relations`): validar, cargar y emitir.

Plan de datos estructurados, fase 1 (13-11-2026). Tres reglas que no se negocian:

1. **Sin fuente verificada no se emite.** Solo sale lo `verificada`, y solo es
   `verificada` lo que tiene un T1 o dos T2 de dominios distintos, con quien lo
   verificó. Un T1 de MusicBrainz o de Wikidata exige además que sujeto y objeto
   tengan su identidad ACREDITADA en esa base: sin eso es buscar por nombre, que es
   justo el fallo de los homónimos.
2. **Una autoridad por predicado.** La formación de Extremoduro y Robe vive en
   `band_memberships`, los créditos en `song_credits` y las pistas en `album_tracks`:
   eso no se carga aquí, o dos fuentes dirían lo mismo y acabarían discrepando.
3. **Se valida al cargar, no en la auditoría.** Cada relación se monta como nodo y
   pasa por los mismos chequeos que el JSON-LD servido (`jsonld_audit`): vocabulario
   (dominio y rango, también de la inversa), nombre y rayas.

Los `@id` salen de la ruta canónica (`url_resolver.DbCatalog`) y del sufijo que de
verdad define cada familia de página (medido en `data/jsonld/linea_base.json`). Una
entidad cuya página no se sirve sale solo con el nombre: un `@id` hacia un 404 es un
colgante.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services import jsonld_audit as ja
from app.services.entity_resolver import SITE_URL_DEFAULT

ESTADOS = ("verificada", "pendiente", "rechazada")
NIVELES = ("T1", "T2", "T3")

# tipo interno → (@type del nodo, sufijo del @id). El sufijo es el que DEFINE cada
# familia de página en lo servido (línea base del 12-11-2026). `place` va sin @type:
# la ficha lo sirve como Place si tiene coordenadas y como DefinedTerm si no.
TIPOS: dict[str, tuple[str | None, str]] = {
    "person": ("Person", "person"),
    "artist": ("MusicGroup", "musicgroup"),
    "band": ("MusicGroup", "musicgroup"),
    "label": ("Organization", "organization"),
    "album": ("MusicAlbum", "musicalbum"),
    "song": ("MusicComposition", "musiccomposition"),
    "place": (None, "place"),
    "theme": ("DefinedTerm", "definedterm"),
    "concept": ("DefinedTerm", "definedterm"),
    "book": ("Book", "book"),
}

# Lo que ya tiene autoridad en otra tabla (plan, fase 2).
_FORMACION = {"member", "memberOf", "founder"}
_CREDITOS = {"lyricist", "composer", "contributor"}
_PISTAS = {"track", "inAlbum", "recordingOf", "recordedAs"}

# Inversas que se derivan al servir: el hecho se guarda una vez.
INVERSA = {
    "memberOf": "member", "member": "memberOf",
    "parentOrganization": "subOrganization", "subOrganization": "parentOrganization",
    "isPartOf": "hasPart", "hasPart": "isPartOf",
    "subjectOf": "about", "about": "subjectOf",
}
# Propiedades cuyo Role es un OrganizationRole (rol en una organización).
_ORG_ROLE = {"memberOf", "member", "worksFor", "affiliation", "alumniOf"}

# Bases cuyo T1 exige identidad acreditada, y cómo se reconoce su URL en `sameAs`.
_IDENTIDAD = {"musicbrainz": "musicbrainz.org", "wikidata": "wikidata.org",
              "discogs": "discogs.com"}

_REF = re.compile(r"^(person|artist|band|label|album|song|place|theme|concept|book):(.+)$")


# --------------------------------------------------------------------------- #
# Referencias
# --------------------------------------------------------------------------- #
@dataclass
class Ref:
    tipo: str
    id: int
    nombre: str
    path: str | None
    publicada: bool
    wikidata_id: str | None = None
    # El @type con el que lo sirve su página. Un lugar sin coordenadas sale como
    # DefinedTerm (TaxonomyDetailLayout), y validar contra Place lo dejaría pasar
    # para luego fallar en la auditoría de lo servido.
    tipo_servido: str | None = None


def resolver_ref(db: Session, texto: str) -> Ref | None:
    """`person:alen-ayerdi`, `band:marea`, `label:el-dromedario-records`,
    `album:extremoduro/agila`, `song:extremoduro/agila/so-payaso`…"""
    from app.db.models import Album, Artist, Band, Book, Concept, Person, Place, Song, Theme
    from app.services.url_resolver import DbCatalog

    m = _REF.match(texto.strip())
    if not m:
        return None
    tipo, slug = m.groups()
    cat = DbCatalog(db)
    fila = None
    if tipo in ("band", "label"):
        fila = db.query(Band).filter(Band.slug == slug).first()
        if fila is None or (fila.kind or "band") != ("label" if tipo == "label" else "band"):
            return None
        return Ref(tipo, fila.id, fila.name, cat.canonical_path("band", fila.id),
                   cat._publicado("band", fila.id), fila.wikidata_id, TIPOS[tipo][0])
    if tipo == "album":
        art, _, alb = slug.partition("/")
        fila = (db.query(Album).join(Artist, Album.artist_id == Artist.id)
                .filter(Artist.slug == art, Album.slug == alb).first())
        nombre = fila and fila.title
    elif tipo == "song":
        art, alb, son = (slug.split("/") + ["", ""])[:3]
        fila = (db.query(Song).join(Album, Song.album_id == Album.id)
                .join(Artist, Album.artist_id == Artist.id)
                .filter(Artist.slug == art, Album.slug == alb, Song.slug == son).first())
        nombre = fila and fila.title
    else:
        modelo = {"person": Person, "artist": Artist, "place": Place, "theme": Theme,
                  "concept": Concept, "book": Book}[tipo]
        fila = db.query(modelo).filter(modelo.slug == slug).first()
        if fila is None:
            return None
        nombre = (getattr(fila, "stage_name", None) or getattr(fila, "full_name", None)
                  or getattr(fila, "name", None) or getattr(fila, "title", None))
    if fila is None:
        return None
    # Taxonomías, libros y las dos páginas de artista se sirven sin ficha SEO
    # (`DbCatalog.artist_id` no mira publicación; `_publicado` da True a las otras).
    publicada = True if tipo in ("theme", "place", "concept", "book", "artist") \
        else cat._publicado(tipo, fila.id)
    servido = TIPOS[tipo][0]
    if tipo == "place":
        servido = "Place" if fila.geo_lat is not None and fila.geo_lng is not None else "DefinedTerm"
    return Ref(tipo, fila.id, nombre or slug, cat.canonical_path(tipo, fila.id), publicada,
               getattr(fila, "wikidata_id", None), servido)


def ref_por_id(db: Session, tipo: str, ident: int) -> Ref | None:
    from app.db.models import Album, Artist, Band, Book, Concept, Person, Place, Song, Theme

    modelo = {"person": Person, "artist": Artist, "band": Band, "label": Band,
              "album": Album, "song": Song, "place": Place, "theme": Theme,
              "concept": Concept, "book": Book}.get(tipo)
    fila = db.get(modelo, ident) if modelo else None
    if fila is None:
        return None
    if tipo in ("band", "label"):
        return resolver_ref(db, f"{tipo}:{fila.slug}")
    if tipo == "album":
        return resolver_ref(db, f"album:{fila.artist.slug}/{fila.slug}")
    if tipo == "song":
        return resolver_ref(db, f"song:{fila.album.artist.slug}/{fila.album.slug}/{fila.slug}")
    return resolver_ref(db, f"{tipo}:{fila.slug}")


def nodo_ref(ref: Ref, base: str) -> dict:
    """Cómo se cita una entidad nuestra. Sin página servida, solo el nombre."""
    tipo_ld, frag = TIPOS[ref.tipo]
    nodo: dict[str, Any] = {"@type": tipo_ld} if tipo_ld else {}
    if ref.publicada and ref.path:
        nodo |= {"@id": f"{base}{ref.path}#{frag}", "name": ref.nombre,
                 "url": f"{base}{ref.path}"}
    else:
        nodo |= {"name": ref.nombre}
        if not tipo_ld:
            nodo["@type"] = "Place"
    return nodo


# --------------------------------------------------------------------------- #
# Validación
# --------------------------------------------------------------------------- #
@dataclass
class Propuesta:
    """Una relación tal como viene del YAML o de un recolector, antes de guardarla."""
    sujeto: str
    predicado: str
    objeto: str | dict
    rol: str | None = None
    desde: str | None = None
    hasta: str | None = None
    estado: str = "pendiente"
    verificado_por: str | None = None
    fuentes: list[dict] = field(default_factory=list)


def clave(st: str, sid: int, pred: str, ot: str | None, oid: int | None,
          literal: Any, rol: str | None, desde: str | None) -> str:
    """Clave única, derivada y NO nula (los NULL de Postgres son todos distintos)."""
    if oid is not None:
        obj = f"{ot}:{oid}"
    else:
        obj = "lit:" + hashlib.sha1(json.dumps(literal, sort_keys=True,
                                               ensure_ascii=False).encode()).hexdigest()
    return f"{st}:{sid}|{pred}|{obj}|{(rol or '').strip().lower()}|{desde or ''}"


def _dominio(url: str | None) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def identidad_acreditada(db: Session, ref: Ref, base_externa: str) -> bool:
    """¿Tiene esta entidad su identidad acreditada en esa base?"""
    from app.db.models import EntityRelation

    if base_externa == "wikidata" and ref.wikidata_id:
        return True
    dominio = _IDENTIDAD[base_externa]
    filas = (db.query(EntityRelation.object_literal)
             .filter(EntityRelation.subject_type == ref.tipo,
                     EntityRelation.subject_id == ref.id,
                     EntityRelation.predicate == "sameAs",
                     EntityRelation.status == "verificada").all())
    return any(isinstance(u, str) and dominio in _dominio(u) for (u,) in filas)


def _autoridad_ajena(suj: Ref, pred: str, obj: Ref | None) -> str | None:
    tipos = {suj.tipo, obj.tipo if obj else None}
    if pred in _FORMACION and "artist" in tipos:
        return "la formación de Extremoduro y Robe manda en band_memberships"
    if pred in _CREDITOS and "song" in tipos:
        return "los créditos de canción mandan en song_credits"
    if pred in _PISTAS:
        return "las pistas mandan en album_tracks"
    return None


def _problemas_vocabulario(tipo_suj: str, pred: str, valor: Any) -> list[str]:
    """Monta {sujeto: pred → valor} en una página de prueba y la audita."""
    voc = ja.cargar_vocabulario()
    path = "/__validacion__"
    nodo = {"@context": "https://schema.org", "@type": tipo_suj,
            "@id": f"{SITE_URL_DEFAULT}{path}#sujeto", pred: valor}
    pag = ja.analizar([nodo], path)
    return [f.detalle for f in ja.problemas_de_pagina(pag, voc)]


def validar(db: Session, p: Propuesta, base: str | None = None) -> tuple[list[str], dict | None]:
    """Errores de la propuesta y, si no hay, la fila lista para guardar."""
    base = (base or SITE_URL_DEFAULT).rstrip("/")
    err: list[str] = []
    if p.estado not in ESTADOS:
        err.append(f"estado desconocido {p.estado!r}")
    suj = resolver_ref(db, p.sujeto)
    if suj is None:
        return [f"sujeto desconocido {p.sujeto!r}"], None
    obj: Ref | None = None
    literal: Any = None
    if isinstance(p.objeto, str) and _REF.match(p.objeto):
        obj = resolver_ref(db, p.objeto)
        if obj is None:
            return [f"objeto desconocido {p.objeto!r}"], None
    elif p.predicado == "sameAs":
        if not (isinstance(p.objeto, str) and p.objeto.startswith("https://")):
            err.append("sameAs necesita una URL https")
        literal = p.objeto
    elif isinstance(p.objeto, dict) and p.objeto.get("@type") and p.objeto.get("name"):
        literal = {k: v for k, v in p.objeto.items() if not str(k).startswith("@id")}
    else:
        err.append(f"objeto no válido {p.objeto!r}: ni referencia, ni nodo con @type y name")

    ajena = _autoridad_ajena(suj, p.predicado, obj)
    if ajena:
        err.append(ajena)

    # Vocabulario, en el sentido guardado y en la inversa que se derivará.
    tipo_suj = suj.tipo_servido or TIPOS[suj.tipo][0]
    if p.predicado != "sameAs":
        if obj is not None:
            valor = {"@type": obj.tipo_servido or TIPOS[obj.tipo][0], "name": obj.nombre}
        else:
            valor = literal
        if valor is not None:
            err += _problemas_vocabulario(tipo_suj, p.predicado, valor)
            inv = INVERSA.get(p.predicado)
            if inv and obj is not None:
                err += [f"inversa: {e}" for e in _problemas_vocabulario(
                    valor["@type"], inv, {"@type": tipo_suj, "name": suj.nombre})]

    # Fuentes
    if not p.fuentes:
        err.append("sin fuentes")
    for f in p.fuentes:
        if f.get("tier") not in NIVELES or not f.get("kind"):
            err.append(f"fuente incompleta {f!r}: hacen falta kind y tier (T1/T2/T3)")
        if not (f.get("url") or f.get("evidencia")):
            err.append(f"fuente sin url ni evidencia {f!r}")
    if p.estado == "verificada":
        t1 = [f for f in p.fuentes if f.get("tier") == "T1"]
        t2_dominios = {_dominio(f.get("url")) for f in p.fuentes if f.get("tier") == "T2"}
        if not t1 and len(t2_dominios - {""}) < 2:
            err.append("verificada necesita un T1 o dos T2 de dominios distintos")
        if not p.verificado_por:
            err.append("verificada necesita verificado_por")
        for f in t1:
            externa = f.get("kind")
            if externa in _IDENTIDAD and p.predicado != "sameAs":
                for ref in (suj, obj):
                    if ref is not None and not identidad_acreditada(db, ref, externa):
                        err.append(f"T1 de {externa} sin identidad acreditada de "
                                   f"{ref.tipo}:{ref.id} ({ref.nombre}) en {externa}")

    if err:
        return err, None
    return [], {
        "clave": clave(suj.tipo, suj.id, p.predicado, obj and obj.tipo, obj and obj.id,
                       literal, p.rol, p.desde),
        "subject_type": suj.tipo, "subject_id": suj.id, "predicate": p.predicado,
        "object_type": obj.tipo if obj else None, "object_id": obj.id if obj else None,
        "object_literal": literal, "role_name": p.rol, "start_date": p.desde,
        "end_date": p.hasta, "fuentes": p.fuentes, "status": p.estado,
        "verified_by": p.verificado_por if p.estado == "verificada" else None,
    }


# --------------------------------------------------------------------------- #
# Emisión
# --------------------------------------------------------------------------- #
def _envolver(pred: str, destino: dict, rol: str | None, desde: str | None,
              hasta: str | None) -> dict:
    """Rol y fechas van en un Role que repite la propiedad que envuelve."""
    if not (rol or desde or hasta):
        return destino
    nodo: dict[str, Any] = {"@type": "OrganizationRole" if pred in _ORG_ROLE else "Role",
                            pred: destino}
    if rol:
        nodo["roleName"] = rol
    if desde:
        nodo["startDate"] = desde
    if hasta:
        nodo["endDate"] = hasta
    return nodo


def jsonld_de(db: Session, tipo: str, ident: int, *, site_url: str | None = None
              ) -> dict[str, list] | None:
    """Las propiedades verificadas de la entidad, listas para fusionar en su nodo.

    Incluye lo que se guardó en el otro sentido (la inversa). None si no hay nada, para
    que la salida sea idéntica a la de antes con la tabla vacía."""
    from app.db.models import EntityRelation

    base = (site_url or SITE_URL_DEFAULT).rstrip("/")
    out: dict[str, list] = {}

    def poner(prop: str, valor: Any) -> None:
        lista = out.setdefault(prop, [])
        if valor not in lista:
            lista.append(valor)

    directas = (db.query(EntityRelation)
                .filter(EntityRelation.subject_type == tipo, EntityRelation.subject_id == ident,
                        EntityRelation.status == "verificada")
                .order_by(EntityRelation.id).all())
    for r in directas:
        if r.predicate == "sameAs":
            poner("sameAs", r.object_literal)
            continue
        if r.object_id is not None:
            ref = ref_por_id(db, r.object_type, r.object_id)
            if ref is None:
                continue
            destino = nodo_ref(ref, base)
        else:
            destino = r.object_literal
        poner(r.predicate, _envolver(r.predicate, destino, r.role_name, r.start_date,
                                     r.end_date))

    inversas = (db.query(EntityRelation)
                .filter(EntityRelation.object_type == tipo, EntityRelation.object_id == ident,
                        EntityRelation.status == "verificada",
                        EntityRelation.predicate.in_(list(INVERSA))).order_by(EntityRelation.id)
                .all())
    for r in inversas:
        ref = ref_por_id(db, r.subject_type, r.subject_id)
        if ref is None:
            continue
        inv = INVERSA[r.predicate]
        poner(inv, _envolver(inv, nodo_ref(ref, base), r.role_name, r.start_date, r.end_date))
    return out or None


def rutas_de(db: Session, tipo: str, ident: int) -> set[str]:
    """Rutas internas que la ficha pinta por sus relaciones verificadas (en los dos
    sentidos). Son enlaces de PLANTILLA: `link_policy.plantilla_de` las necesita para
    que el autolinker no gaste presupuesto en lo que luego sale como texto."""
    from app.db.models import EntityRelation

    out: set[str] = set()
    directas = (db.query(EntityRelation.object_type, EntityRelation.object_id)
                .filter(EntityRelation.subject_type == tipo, EntityRelation.subject_id == ident,
                        EntityRelation.status == "verificada",
                        EntityRelation.object_id.isnot(None)).all())
    inversas = (db.query(EntityRelation.subject_type, EntityRelation.subject_id)
                .filter(EntityRelation.object_type == tipo, EntityRelation.object_id == ident,
                        EntityRelation.status == "verificada",
                        EntityRelation.predicate.in_(list(INVERSA))).all())
    for t, i in [*directas, *inversas]:
        ref = ref_por_id(db, t, i)
        if ref is not None and ref.publicada and ref.path:
            out.add(ref.path)
    return out
