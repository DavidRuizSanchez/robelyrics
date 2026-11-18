"""Invariantes del JSON-LD servido: lo que no puede romperse al tocar los datos estructurados.

Plan de datos estructurados, fase 0 (12-11-2026). David pidió «dejar este tema zanjado
de una vez, ya que cada vez que miro, hay algo que falla». Antes de añadir una sola
relación hay que poder ver lo que se pierde, así que este módulo mira el HTML
SERVIDO (el JSON-LD lo montan las páginas de Next al servir, no el api) y comprueba
cuatro cosas:

- **Contención** (`huella` + `perdidas`): lo que una página marcaba ayer lo sigue
  marcando hoy. La huella es el conjunto de «sujeto · propiedad» y «sujeto ·
  propiedad → @id». No mira el valor de los literales: un title que cambia ya lo
  avisa el monitor, y aquí lo que importa es que no desaparezca una relación.
- **Sin `@id` colgantes** (`ids_colgantes`): todo `@id` interno que se cita existe
  como nodo en la URL que implica. Así salen el sello que apunta a `/grupos/…` y las
  pistas de los recopilatorios, que citan grabaciones que no existen.
- **Vocabulario** (`vocabulario`): el tipo existe, la propiedad existe y vale para
  ese tipo, y un nodo anidado es del rango que admite la propiedad. Contra el
  fichero OFICIAL de schema.org versionado en `data/schemaorg/`, no contra la
  memoria de nadie: así se vio que `MusicAlbum.track` no admite `MusicComposition`.
- **Nombre y rayas** (`nombre_y_rayas`): el JSON-LD no pasa por el listener del ORM,
  y una etiqueta de Wikidata puede traer «Robe Iniesta».

Puro salvo `cargar_vocabulario`, que lee un fichero. Lo usan los tests, el script
`scripts/seo/audit_jsonld.py` y el monitor diario (`page_monitor`).
"""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup

from app.services.text_sanitizer import _RE_ROBE_INIESTA

SITE_HOSTS = ("https://entreinteriores.com", "http://entreinteriores.com",
              "https://www.entreinteriores.com")
RAYAS = ("—", "―")
VOCABULARIO = "schemaorg-current-2026-11-12.jsonld"
_CANDIDATOS_DATA = (Path("/app/data"), Path(__file__).resolve().parents[3] / "data")
# Propiedades cuyo valor es una URL o un identificador: ni nombre ni rayas que mirar.
_PROPS_URL = frozenset({"url", "sameAs", "image", "logo", "contentUrl", "embedUrl",
                        "thumbnailUrl", "mainEntityOfPage", "@id", "item", "target"})


def ruta_data(nombre: str) -> Path:
    """`data/<nombre>` en el contenedor (`/app/data`) o en el repo. Los tests corren en
    los dos sitios y en CI `data/` va montado en `/app/data`."""
    for base in _CANDIDATOS_DATA:
        if (base / nombre).exists():
            return base / nombre
    raise FileNotFoundError(f"no encuentro data/{nombre}")


# --------------------------------------------------------------------------- #
# HTML → nodos
# --------------------------------------------------------------------------- #
def bloques(html: str) -> list:
    """Cada `<script type="application/ld+json">` ya parseado. Un bloque que no es
    JSON válido sale como `{"__invalido__": texto}`: también es un fallo."""
    out = []
    for s in BeautifulSoup(html or "", "html.parser").find_all(
            "script", type="application/ld+json"):
        texto = s.string or ""
        try:
            out.append(json.loads(texto))
        except ValueError:
            out.append({"__invalido__": texto[:200]})
    return out


def raices(bloques_ld: list) -> list[dict]:
    """Los nodos de primer nivel: se abre `@graph` y las listas."""
    out: list[dict] = []
    for b in bloques_ld:
        if isinstance(b, list):
            out += raices(b)
        elif isinstance(b, dict):
            if "@graph" in b:
                out += raices([b["@graph"]])
            else:
                out.append(b)
    return out


def norm_id(valor: str, path: str) -> str:
    """Un `@id` sin dominio: `https://entreinteriores.com/personas/x#person` →
    `/personas/x#person`; `#x` → `<path>#x`. Lo externo se queda como está."""
    v = (valor or "").strip()
    for h in SITE_HOSTS:
        if v.startswith(h):
            v = v[len(h):] or "/"
            break
    else:
        if v.startswith("#"):
            v = path + v
        elif not v.startswith("/"):
            return v
    base, _, frag = v.partition("#")
    base = "/" + base.strip("/") if base.strip("/") else "/"
    return f"{base}#{frag}" if frag else base


def es_interno(id_norm: str) -> bool:
    return id_norm.startswith("/")


def tipos(nodo: dict) -> list[str]:
    t = nodo.get("@type")
    lista = t if isinstance(t, list) else [t] if t else []
    return [_sin_prefijo(x) for x in lista if isinstance(x, str)]


def _sin_prefijo(t: str) -> str:
    for p in ("https://schema.org/", "http://schema.org/", "schema:"):
        if t.startswith(p):
            return t[len(p):]
    return t


def _es_ref(v: dict) -> bool:
    return set(v) == {"@id"}


# --------------------------------------------------------------------------- #
# Análisis de una página
# --------------------------------------------------------------------------- #
@dataclass
class Pagina:
    path: str
    huella: set[str] = field(default_factory=set)
    definidos: dict[str, list[str]] = field(default_factory=dict)   # @id → tipos
    referencias: set[str] = field(default_factory=set)               # @id citados
    nodos: list[tuple[str, dict, str | None]] = field(default_factory=list)
    invalidos: list[str] = field(default_factory=list)


def analizar(html_o_bloques, path: str) -> Pagina:
    """Recorre el JSON-LD de una página y saca su huella, sus nodos y sus `@id`."""
    bl = bloques(html_o_bloques) if isinstance(html_o_bloques, str) else html_o_bloques
    pag = Pagina(path=path)
    for b in bl:
        if isinstance(b, dict) and "__invalido__" in b:
            pag.invalidos.append(b["__invalido__"])
    for raiz in raices(bl):
        # Un nodo raíz sin @id se nombra por su tipo, no por su posición: reordenar los
        # bloques de la página no es perder nada.
        _recorrer(pag, raiz, clave=None, padre_prop=None, anonimo=f"{path}#~")
    return pag


def _recorrer(pag: Pagina, nodo: dict, *, clave: str | None, padre_prop: str | None,
              anonimo: str) -> str:
    ts = tipos(nodo)
    if "@id" in nodo and isinstance(nodo["@id"], str):
        clave = norm_id(nodo["@id"], pag.path)
        if not _es_ref(nodo):
            prev = pag.definidos.setdefault(clave, [])
            prev += [t for t in ts if t not in prev]
    else:
        # Sin @id la clave sale del camino (sin índice de lista: reordenar no es perder)
        clave = anonimo + (f"[{'|'.join(sorted(ts))}]" if ts else "")
    pag.nodos.append((clave, nodo, padre_prop))
    for t in ts:
        pag.huella.add(f"{clave} @type {t}")
    for prop, valor in nodo.items():
        if prop.startswith("@"):
            continue
        for v in valor if isinstance(valor, list) else [valor]:
            if isinstance(v, dict):
                if "@id" in v and isinstance(v["@id"], str):
                    destino = norm_id(v["@id"], pag.path)
                    pag.huella.add(f"{clave} {prop} → {destino}")
                    pag.referencias.add(destino)
                    if not _es_ref(v):
                        _recorrer(pag, v, clave=None, padre_prop=prop, anonimo="")
                else:
                    pag.huella.add(f"{clave} {prop}")
                    _recorrer(pag, v, clave=None, padre_prop=prop,
                              anonimo=f"{clave}>{prop}")
            elif v is not None and v != "":
                pag.huella.add(f"{clave} {prop}")
    return clave


# --------------------------------------------------------------------------- #
# Invariantes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Fallo:
    regla: str          # contencion | colgante | vocabulario | nombre | rayas | invalido
    path: str
    detalle: str

    def __str__(self) -> str:
        return f"[{self.regla}] {self.path}: {self.detalle}"


def perdidas(antes: set[str] | list[str], despues: set[str] | list[str]) -> list[str]:
    """Lo que la huella de ayer tenía y la de hoy no."""
    return sorted(set(antes) - set(despues))


def ids_colgantes(paginas: dict[str, Pagina]) -> list[Fallo]:
    """Cada `@id` interno citado tiene que estar DEFINIDO en la página que implica su
    URL. Si esa página no está en el conjunto (404, fuera del sitemap), cuelga."""
    out = []
    for path, pag in sorted(paginas.items()):
        for ref in sorted(pag.referencias):
            if not es_interno(ref):
                continue
            destino = ref.split("#", 1)[0] or "/"
            otra = paginas.get(destino)
            if otra is None:
                out.append(Fallo("colgante", path, f"{ref} (la página {destino} no está)"))
            elif ref not in otra.definidos:
                out.append(Fallo("colgante", path, f"{ref} (no está definido en {destino})"))
    return out


@dataclass
class Vocabulario:
    padres: dict[str, set[str]]           # clase → superclases directas
    dominio: dict[str, set[str]]          # propiedad → domainIncludes
    rango: dict[str, set[str]]            # propiedad → rangeIncludes
    obsoletas: set[str]
    datatypes: set[str]

    def ancestros(self, clase: str) -> set[str]:
        return _ancestros(self.padres, clase)

    def es_clase(self, c: str) -> bool:
        return c in self.padres


def _ids(v) -> set[str]:
    lista = v if isinstance(v, list) else [v] if v else []
    return {_sin_prefijo(x["@id"]) for x in lista if isinstance(x, dict) and "@id" in x}


@lru_cache(maxsize=2)
def cargar_vocabulario(ruta: str | None = None) -> Vocabulario:
    data = json.loads(Path(ruta or ruta_data(f"schemaorg/{VOCABULARIO}")).read_text())
    padres, dominio, rango, obsoletas, datatypes = {}, {}, {}, set(), set()
    for n in data["@graph"]:
        nid = _sin_prefijo(n["@id"])
        t = n.get("@type")
        ts = set(t if isinstance(t, list) else [t])
        if "rdfs:Class" in ts or "schema:DataType" in ts:
            padres[nid] = _ids(n.get("rdfs:subClassOf"))
            if "schema:DataType" in ts:
                datatypes.add(nid)
        if "rdf:Property" in ts:
            dominio[nid] = _ids(n.get("schema:domainIncludes"))
            rango[nid] = _ids(n.get("schema:rangeIncludes"))
            if n.get("schema:supersededBy"):
                obsoletas.add(nid)
    # Las subclases de un DataType (URL ⊂ Text, Integer ⊂ Number) también lo son.
    for c in list(padres):
        if any(a in datatypes for a in _ancestros(padres, c)):
            datatypes.add(c)
    return Vocabulario(padres, dominio, rango, obsoletas, datatypes)


def _ancestros(padres: dict[str, set[str]], c: str) -> set[str]:
    vistos, pila = set(), [c]
    while pila:
        x = pila.pop()
        if x not in vistos:
            vistos.add(x)
            pila += list(padres.get(x, ()))
    return vistos


def vocabulario(pag: Pagina, voc: Vocabulario) -> list[Fallo]:
    """Tipo, propiedad, dominio y rango contra el vocabulario oficial.

    Un `Role` repite la propiedad que envuelve (`member: {@type: OrganizationRole,
    member: …}`): ahí esa propiedad vale aunque el dominio no sea un Role. Los
    literales no se comprueban contra el rango: schema.org admite texto donde espera
    una entidad. Una referencia pura (`{"@id": …}`) se comprueba aquí si su nodo está
    en la misma página; si está en otra, en `rangos_cruzados`.
    """
    out: list[Fallo] = []
    for clave, nodo, padre_prop in pag.nodos:
        ts = tipos(nodo)
        for t in ts:
            if not voc.es_clase(t):
                out.append(Fallo("vocabulario", pag.path, f"{clave}: el tipo {t} no existe"))
        anc = set().union(*(voc.ancestros(t) for t in ts)) if ts else set()
        es_role = "Role" in anc
        for prop, valor in nodo.items():
            if prop.startswith("@"):
                continue
            # Anotaciones de las acciones de schema.org: `query-input` describe la
            # entrada de `query` (https://schema.org/docs/actions.html).
            base_accion = re.sub(r"-(input|output)$", "", prop)
            if base_accion != prop and base_accion in voc.dominio:
                continue
            if prop not in voc.dominio:
                out.append(Fallo("vocabulario", pag.path,
                                 f"{clave}: la propiedad {prop} no existe"))
                continue
            if prop in voc.obsoletas:
                out.append(Fallo("vocabulario", pag.path,
                                 f"{clave}: {prop} está obsoleta en schema.org"))
            if ts and not (anc & voc.dominio[prop]) and not (es_role and prop == padre_prop):
                out.append(Fallo("vocabulario", pag.path,
                                 f"{clave}: {prop} no vale para {'/'.join(ts)}"))
            for v in valor if isinstance(valor, list) else [valor]:
                if not isinstance(v, dict):
                    continue
                vts = tipos(v)
                if not vts and "@id" in v:
                    vts = pag.definidos.get(norm_id(v["@id"], pag.path), [])
                if not vts:
                    continue
                fallo = _fuera_de_rango(voc, pag.path, clave, prop, vts)
                if fallo:
                    out.append(fallo)
    return out


def _fuera_de_rango(voc: Vocabulario, path: str, clave: str, prop: str,
                    vts: list[str]) -> Fallo | None:
    rango = voc.rango.get(prop, set())
    vanc = set().union(*(voc.ancestros(t) for t in vts))
    # Un Role vale en el sitio de lo que envuelve (rango de `member`, etc.)
    if not rango or "Role" in vanc or vanc & rango:
        return None
    return Fallo("vocabulario", path, f"{clave}: {prop} → {'/'.join(vts)} fuera de rango "
                                      f"({'/'.join(sorted(rango))})")


def tipos_del_sitio(paginas: dict[str, Pagina]) -> dict[str, list[str]]:
    tg: dict[str, list[str]] = {}
    for pag in paginas.values():
        for k, ts in pag.definidos.items():
            tg.setdefault(k, [])
            tg[k] += [t for t in ts if t not in tg[k]]
    return tg


def rangos_cruzados(paginas: dict[str, Pagina], voc: Vocabulario) -> list[Fallo]:
    """El rango de las referencias a nodos de OTRA página: `track` apunta a
    `/extremoduro/agila/so-payaso#musiccomposition`, y que eso es una
    MusicComposition solo lo dice la página de la canción. Trabaja sobre la huella,
    así que vale también con las fotos guardadas del monitor."""
    tg = tipos_del_sitio(paginas)
    out = []
    for path, pag in sorted(paginas.items()):
        for linea in sorted(pag.huella):
            if " → " not in linea:
                continue
            izquierda, destino = linea.rsplit(" → ", 1)
            clave, _, prop = izquierda.rpartition(" ")
            if destino in pag.definidos or not tg.get(destino):
                continue
            fallo = _fuera_de_rango(voc, path, clave, prop, tg[destino])
            if fallo:
                out.append(fallo)
    return out


def _literales(nodo: dict):
    """Los textos PROPIOS de un nodo (los anidados se miran en su propio nodo)."""
    for prop, valor in nodo.items():
        if prop.startswith("@") or prop in _PROPS_URL:
            continue
        for v in valor if isinstance(valor, list) else [valor]:
            if isinstance(v, str):
                yield prop, v


def nombre_y_rayas(pag: Pagina) -> list[Fallo]:
    """La forma vetada «Robe Iniesta» y la raya larga, en cualquier texto del JSON-LD."""
    out = []
    for clave, nodo, _ in pag.nodos:
        for prop, texto in _literales(nodo):
            if _RE_ROBE_INIESTA.search(texto):
                out.append(Fallo("nombre", pag.path, f"{clave} {prop}: «{texto[:120]}»"))
            if any(r in texto for r in RAYAS):
                out.append(Fallo("rayas", pag.path, f"{clave} {prop}: «{texto[:120]}»"))
    return out


def problemas_de_pagina(pag: Pagina, voc: Vocabulario) -> list[Fallo]:
    """Lo que se puede decir de UNA página sin mirar las demás."""
    out = [Fallo("invalido", pag.path, f"JSON-LD que no es JSON: {t[:80]}")
           for t in pag.invalidos]
    return out + vocabulario(pag, voc) + nombre_y_rayas(pag)


def auditar(paginas: dict[str, Pagina], voc: Vocabulario) -> list[Fallo]:
    """Las invariantes de todo el sitio, salvo la contención (que necesita la foto
    anterior: ver `perdidas`)."""
    out: list[Fallo] = []
    for pag in paginas.values():
        out += problemas_de_pagina(pag, voc)
    return out + rangos_cruzados(paginas, voc) + ids_colgantes(paginas)


def campos_monitor(pag: Pagina) -> dict:
    """Lo que el monitor guarda de una página para comparar mañana y para cruzar los
    `@id` entre páginas. Si el vocabulario no se puede leer, sin fallos de vocabulario
    (el monitor no puede caerse por esto)."""
    try:
        problemas = sorted(str(f) for f in problemas_de_pagina(pag, cargar_vocabulario()))
    except (OSError, ValueError):
        problemas = sorted(str(f) for f in nombre_y_rayas(pag))
    return {"jsonld_huella": sorted(pag.huella),
            "jsonld_definidos": {k: v for k, v in sorted(pag.definidos.items())},
            "jsonld_problemas": problemas}


def pagina_desde_campos(path: str, campos: dict) -> Pagina | None:
    """La parte de una `Pagina` que hace falta para `ids_colgantes`, desde la foto
    guardada. None si la foto es de antes de que se guardara esto."""
    if "jsonld_huella" not in (campos or {}):
        return None
    refs = {linea.rsplit(" → ", 1)[1] for linea in campos["jsonld_huella"] if " → " in linea}
    return Pagina(path=path, huella=set(campos["jsonld_huella"]),
                  definidos=dict(campos.get("jsonld_definidos") or {}), referencias=refs)


# --------------------------------------------------------------------------- #
# Excepciones declaradas
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Excepcion:
    regla: str
    paths: str          # patrón fnmatch sobre la ruta
    detalle: str        # expresión regular sobre el detalle
    motivo: str
    fase: str

    def cubre(self, f: Fallo) -> bool:
        return (f.regla == self.regla and fnmatch.fnmatchcase(f.path, self.paths)
                and re.search(self.detalle, f.detalle) is not None)


def cargar_excepciones(ruta: str | None = None) -> list[Excepcion]:
    import yaml

    data = yaml.safe_load(Path(ruta or ruta_data("jsonld_excepciones.yaml")).read_text()) or {}
    return [Excepcion(e["regla"], e["paths"], e["detalle"], e["motivo"], e["fase"])
            for e in data.get("excepciones", [])]


def separar(fallos: list[Fallo], excepciones: list[Excepcion]
            ) -> tuple[list[Fallo], list[Fallo], list[Excepcion]]:
    """(nuevos, conocidos, excepciones que ya no cubren nada).

    Una excepción que no cubre nada se ha arreglado: hay que quitarla del YAML, o
    volvería a esconder el fallo si regresa."""
    nuevos, conocidos, usadas = [], [], set()
    for f in fallos:
        cubre = next((i for i, e in enumerate(excepciones) if e.cubre(f)), None)
        if cubre is None:
            nuevos.append(f)
        else:
            conocidos.append(f)
            usadas.add(cubre)
    sobran = [e for i, e in enumerate(excepciones) if i not in usadas]
    return nuevos, conocidos, sobran
