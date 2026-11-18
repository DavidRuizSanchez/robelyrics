"""Datos de edición de un disco (sello, producción, grabación, primer sencillo) con fuente.

Plan del blog (18-11-2026). El aniversario de «Destrozares» se descartó por no dar el
sello ni el contexto de grabación, y esos datos no estaban en ningún sitio de la casa:
el disco solo tenía su `sameAs` a MusicBrainz. Los dos sitios donde sí están:

- **MusicBrainz** (T1): el sello de cada edición (`label-info`). Ojo: de las dos
  ediciones de «Destrozares» solo una lo trae, así que se recorren todas.
- **La ficha de Wikipedia en español** (`Ficha de álbum`): discográfica, productor,
  grabación, primer sencillo. Una sola fuente secundaria: cada dato se da por bueno
  solo si lo corrobora MusicBrainz, la BD o un texto del corpus que hable del disco
  (el productor de «Destrozares», José Luis Crespo, lo nombra la banda en la rueda de
  prensa de presentación).

Lo que no se corrobora no se devuelve: no llega al redactor. Se guarda en
`data/album_facts/<slug>.json` con la fecha de extracción, para no volver a pedirlo y
para poder rastrear de dónde salió cada dato.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

UA = {"User-Agent": "EntreInteriores/1.0 (https://entreinteriores.com)"}
PAUSA_MB = 1.2


@dataclass
class Dato:
    campo: str          # sello | productor | grabacion | estudio | sencillo
    valor: str
    fuentes: list[dict] = field(default_factory=list)  # {kind, tier, url, cita}

    def linea(self) -> str:
        if self.campo == "listas":
            return f"Listas: {self.valor}."
        if self.campo == "productor":
            # En la rueda de prensa de «Destrozares» la producción se cuenta como cosa de
            # varios, con José Luis Crespo entre ellos: «participó» es lo que sostienen
            # las dos fuentes; «lo produjo X» solo lo dice una.
            return f"Producción: participó {self.valor}."
        nombre = {"sello": "Sello", "grabacion": "Grabación",
                  "estudio": "Grabación", "sencillo": "Primer sencillo"}[self.campo]
        return f"{nombre}: {self.valor}."


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _dir_cache() -> Path:
    """`data/` va montado en solo lectura en los contenedores: la caché vive en /tmp.
    Es solo caché; la procedencia de cada dato viaja en el propio dato."""
    import os
    import tempfile

    return Path(os.environ.get("ALBUM_FACTS_DIR") or Path(tempfile.gettempdir()) / "album_facts")


# --------------------------------------------------------------------------- #
# Fuentes
# --------------------------------------------------------------------------- #
def _mb_get(http, url: str, params: dict):
    """GET a MusicBrainz con reintento: con varias consultas seguidas responde 503 por
    su límite de peticiones, y un 503 dejaba el disco sin sello (18-11-2026)."""
    r = None
    for intento in range(4):
        r = http.get(url, params=params)
        if r.status_code != 503:
            return r
        time.sleep(PAUSA_MB * (intento + 2))
    return r


def sellos_musicbrainz(http, release_group: str) -> list[str]:
    """Sello(s) de la PRIMERA edición del release-group.

    Se recorren todas las ediciones (de las dos de «Destrozares» solo una trae
    `label-info`), pero se queda el sello de las de fecha más temprana: «Agila» salía
    con DRO y con Warner Music Spain, que es de una reedición posterior."""
    r = _mb_get(http, f"https://musicbrainz.org/ws/2/release-group/{release_group}",
                {"inc": "releases", "fmt": "json"})
    if r.status_code != 200:
        return []
    por_fecha: list[tuple[str, str]] = []
    for rel in r.json().get("releases") or []:
        time.sleep(PAUSA_MB)
        d = _mb_get(http, f"https://musicbrainz.org/ws/2/release/{rel['id']}",
                    {"inc": "labels", "fmt": "json"})
        if d.status_code != 200:
            continue
        fecha = (rel.get("date") or "9999")[:10]
        for li in d.json().get("label-info") or []:
            nombre = ((li.get("label") or {}).get("name") or "").strip()
            if nombre and nombre != "[no label]":
                por_fecha.append((fecha, nombre))
    if not por_fecha:
        return []
    primera = min(f for f, _ in por_fecha)
    return list(dict.fromkeys(n for f, n in por_fecha if f == primera))


def _limpiar_wiki(v: str) -> str:
    v = re.sub(r"<ref[^>]*/>", "", v)
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\{\{[^}]*\}\}", "", v)
    v = re.sub(r"<[^>]+>", "", v)
    return " ".join(v.replace("'''", "").replace("''", "").split()).strip(" ,;")


def ficha_wikipedia(texto: str) -> dict[str, str]:
    """Campos de la `Ficha de álbum` (wikitexto) que interesan, ya limpios."""
    out: dict[str, str] = {}
    # [ \t]* y no \s*: con \s* un campo VACÍO («|calificación =») se tragaba el salto de
    # línea y se quedaba con la línea siguiente (el posicionamiento).
    for m in re.finditer(r"^\|[ \t]*([^=|\n]+?)[ \t]*=[ \t]*(.*)$", texto or "", re.M):
        clave, valor = _norm(m.group(1)), _limpiar_wiki(m.group(2))
        if valor:
            out.setdefault(clave, valor)
    sencillo = re.search(r"\|\s*single 1\s*=\s*(.+)", texto or "")
    if sencillo:
        out["sencillo"] = _limpiar_wiki(sencillo.group(1))
    return out


def pagina_wikipedia(http, titulo_disco: str, artista: str) -> tuple[str, str] | None:
    """(título, wikitexto) de la ficha del disco en eswiki, si su ficha dice que es de
    ese artista y se llama como el disco. Sin eso, nada: un homónimo no vale."""
    r = http.get("https://es.wikipedia.org/w/api.php", params={
        "action": "query", "list": "search", "srsearch": f"{titulo_disco} {artista} álbum",
        "srlimit": 5, "format": "json"})
    if r.status_code != 200:
        return None
    for hit in (r.json().get("query") or {}).get("search") or []:
        t = hit["title"]
        p = http.get("https://es.wikipedia.org/w/api.php", params={
            "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main",
            "format": "json", "titles": t, "redirects": 1})
        pages = (p.json().get("query") or {}).get("pages") or {}
        for page in pages.values():
            txt = ((page.get("revisions") or [{}])[0].get("slots") or {}).get("main", {}).get("*", "")
            ficha = ficha_wikipedia(txt.split("\n'''")[0])
            nombre, de = _norm(ficha.get("nombre", "")), _norm(ficha.get("artista", ""))
            base = _norm(titulo_disco).split(",")[0]
            if "ficha de album" in _norm(txt[:200]) and nombre.startswith(base) \
                    and _norm(artista) in de:
                return page.get("title", t), txt
    return None


# --------------------------------------------------------------------------- #
# Corroboración
# --------------------------------------------------------------------------- #
def corroborado_en_corpus(db, titulo_disco: str, valor: str,
                          contexto: str | None = None) -> dict | None:
    """Un texto del corpus que nombra el disco Y el valor (y, si se pide, el valor
    cerca de `contexto`, p. ej. «sencillo»). Devuelve la fuente."""
    from sqlalchemy import text

    base = (titulo_disco or "").split(",")[0].strip()
    if len(base) < 4 or len(valor) < 4:
        return None
    v = r"\m" + re.escape(valor) + r"\M"
    if contexto:
        v = rf"({v}.{{0,120}}({contexto})|({contexto}).{{0,120}}{v})"
    fila = db.execute(text(
        "select id, kind, title from interpretation_sources "
        "where content_clean ~* :d and content_clean ~* :v limit 1"),
        {"d": r"\m" + re.escape(base) + r"\M", "v": v},
    ).first()
    if not fila:
        return None
    return {"kind": "corpus", "tier": "T2", "url": f"interpretation_sources:{fila.id}",
            "cita": fila.title}


def _ref_urls(wikitexto: str, campo: str) -> list[str]:
    """Las URLs de las referencias de un campo de la ficha (antes de limpiarlo)."""
    m = re.search(rf"^\|\s*{re.escape(campo)}\s*=(.*?)(?=^\|)", wikitexto or "", re.M | re.S)
    return re.findall(r"url\s*=\s*(https?://[^\s|}]+)", m.group(1)) if m else []


def _lista_comprobada(wikitexto: str, posicionamiento: str, http=None) -> Dato | None:
    """El puesto de la ficha, solo si la página de spanishcharts que cita lo confirma."""
    puesto = re.search(r"N\.?\s*º\s*(\d+)", posicionamiento or "")
    urls = [u for u in _ref_urls(wikitexto, "posicionamiento") if "spanishcharts" in u]
    if not puesto or not urls:
        return None
    try:
        import httpx

        cliente = http or httpx.Client(timeout=20, headers=UA, follow_redirects=True)
        r = cliente.get(urls[0])
        texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text)) if r.status_code == 200 else ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("[album_facts] lista: %s", exc)
        return None
    pico = re.search(r"Peak position (\d+)", texto)
    if not pico or pico.group(1) != puesto.group(1):
        return None
    semanas = re.search(r"Weeks on chart (\d+)", texto)
    entrada = re.search(r"Entry \d+ (\d{2}/\d{2}/\d{4})", texto)
    valor = f"n.º {pico.group(1)} en la lista oficial de álbumes de España"
    if semanas:
        valor += f", {semanas.group(1)} semanas en lista"
    if entrada:
        valor += f" (entró el {entrada.group(1).replace('/', '-')})"
    return Dato("listas", valor, [
        {"kind": "wikipedia", "tier": "T2", "url": None, "cita": f"posicionamiento = N.º {puesto.group(1)}"},
        {"kind": "listas", "tier": "T1", "url": str(r.url), "cita": f"Peak position {pico.group(1)}"}])


def datos_corroborados(db, album, *, release_group: str | None, sellos_mb: list[str],
                       wiki: tuple[str, str] | None) -> list[Dato]:
    datos: list[Dato] = []
    ficha = ficha_wikipedia(wiki[1].split("\n'''")[0]) if wiki else {}
    wiki_url = (f"https://es.wikipedia.org/wiki/{wiki[0].replace(' ', '_')}" if wiki else None)
    mb_url = f"https://musicbrainz.org/release-group/{release_group}" if release_group else None

    # Sello: MusicBrainz es T1 por sí solo; Wikipedia, solo si coincide o lo corrobora el corpus.
    sello_wiki = ficha.get("discografica")
    for s in sellos_mb:
        fuentes = [{"kind": "musicbrainz", "tier": "T1", "url": mb_url, "cita": "label-info"}]
        if sello_wiki and _norm(sello_wiki) == _norm(s):
            fuentes.append({"kind": "wikipedia", "tier": "T2", "url": wiki_url,
                            "cita": f"discográfica = {sello_wiki}"})
        datos.append(Dato("sello", s, fuentes))
    if sello_wiki and not datos:
        c = corroborado_en_corpus(db, album.title, sello_wiki,
                                  contexto=r"sello|discogr[aá]fica|edit")
        if c:
            datos.append(Dato("sello", sello_wiki, [
                {"kind": "wikipedia", "tier": "T2", "url": wiki_url,
                 "cita": f"discográfica = {sello_wiki}"}, c]))

    # Productor y estudio: solo con el corpus detrás (una sola fuente secundaria no basta).
    for clave_wiki, campo in (("productor", "productor"), ("estudio", "estudio")):
        valor = ficha.get(clave_wiki)
        if not valor:
            continue
        nombres = [v.strip() for v in re.split(r",| y ", valor) if v.strip()]
        buenos = []
        fuentes = [{"kind": "wikipedia", "tier": "T2", "url": wiki_url,
                    "cita": f"{clave_wiki} = {valor}"}]
        for n in nombres:
            # Que el nombre salga cerca del disco no lo hace productor: tiene que ir
            # junto a «produc…» (o «estudio» para el estudio).
            c = corroborado_en_corpus(db, album.title, n,
                                      contexto=r"produc" if campo == "productor" else r"estudio|grab")
            if c:
                buenos.append(n)
                fuentes.append(c)
        if buenos:
            datos.append(Dato(campo, ", ".join(buenos), fuentes))

    # Recepción: el puesto en la lista oficial que da la ficha, comprobado en la fuente que
    # ella misma cita (el archivo de listas de spanishcharts.com, que reproduce la lista
    # de Promusicae). «Destrozares»: n.º 5, 48 semanas (18-11-2026).
    lista = _lista_comprobada(wiki[1] if wiki else "", ficha.get("posicionamiento", ""))
    if lista:
        datos.append(lista)

    # Primer sencillo: que la canción esté en el disco no prueba que fuera el sencillo
    # (asesor, 18-11-2026). Hace falta un texto del corpus que nombre la canción como
    # sencillo o adelanto del disco.
    sencillo = ficha.get("sencillo")
    if sencillo:
        from sqlalchemy import select

        from app.db.models import Song

        titulos = {_norm(t) for t in db.execute(
            select(Song.title).where(Song.album_id == album.id)).scalars()}
        c = (corroborado_en_corpus(db, album.title, sencillo, contexto=r"sencillo|single|adelanto")
             if _norm(sencillo) in titulos else None)
        if c:
            datos.append(Dato("sencillo", sencillo, [
                {"kind": "wikipedia", "tier": "T2", "url": wiki_url, "cita": "single 1"}, c]))
    return datos


# --------------------------------------------------------------------------- #
# Entrada: con caché en data/album_facts/<slug>.json
# --------------------------------------------------------------------------- #
def _release_group(db, album) -> str | None:
    from app.db.models import EntityRelation

    for r in db.query(EntityRelation).filter(
            EntityRelation.subject_type == "album", EntityRelation.subject_id == album.id,
            EntityRelation.predicate == "sameAs", EntityRelation.status == "verificada"):
        lit = r.object_literal if isinstance(r.object_literal, str) else json.dumps(r.object_literal)
        m = re.search(r"musicbrainz\.org/release-group/([0-9a-f-]{36})", lit or "")
        if m:
            return m.group(1)
    return None


def datos_del_disco(db, album, *, refrescar: bool = False) -> list[Dato]:
    """Los datos corroborados del disco. Nunca lanza: ante un fallo, lista vacía."""
    ruta = _dir_cache() / f"{album.slug}.json"
    if ruta.exists() and not refrescar:
        try:
            return [Dato(**d) for d in json.loads(ruta.read_text())["datos"]]
        except Exception:  # noqa: BLE001 — caché rota: se rehace
            pass
    try:
        import httpx

        from app.db.models import Artist

        artista = db.get(Artist, album.artist_id)
        rg = _release_group(db, album)
        with httpx.Client(timeout=30, headers=UA, follow_redirects=True) as http:
            sellos = sellos_musicbrainz(http, rg) if rg else []
            wiki = pagina_wikipedia(http, album.title, artista.name if artista else "")
        datos = datos_corroborados(db, album, release_group=rg, sellos_mb=sellos, wiki=wiki)
    except Exception as exc:  # noqa: BLE001 — sin red, sin datos (no se inventan)
        logger.warning("[album_facts] %s: %s", album.slug, exc)
        return []
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({
            "album": album.slug, "extraido": datetime.now(UTC).isoformat(timespec="seconds"),
            "datos": [asdict(d) for d in datos]}, ensure_ascii=False, indent=1))
    except OSError as exc:
        logger.warning("[album_facts] no se pudo guardar la caché: %s", exc)
    return datos
