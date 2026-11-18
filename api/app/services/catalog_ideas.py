"""Ideas para el blog desde el CATÁLOGO, con material comprobado antes de proponer.

Plan del blog (18-11-2026), bloque B. Las ideas salían de un research de keywords: unas
2.000 cada lunes, que un LLM agrupaba en 3-9 propuestas (con prohibición expresa de
escribir sobre un disco, una canción o una persona), y con una lista negra que crecía sin
fin. Resultado: diez variantes de «La evolución musical de Extremoduro» y la sensación de
que no quedaban temas, con 20 discos, 132 canciones, 53 personas y 22 lugares en casa.

Aquí cada entidad con ficha publicada se cruza con un juego fijo de ÁNGULOS de historia
(lo que la ficha no cuenta). Para cada candidata se mide, sin inventar:
- **material**: pasajes del corpus que responden al ángulo, separando lo PROPIO (voz de
  Robe, testimonio del entorno, entrevistas transcritas) del fondo;
- **demanda**: impresiones de GSC de la ficha en consultas de ese ángulo (periodo del
  fichero) y volumen de DataForSEO si se pide; sin dato, None (n/d), nunca un 0;
- **canibalización**: si la ficha ya posiciona (pos. ≤ 20) una consulta de ese ángulo,
  el ángulo es de la ficha: se propone ampliarla, no un post.
Temas vetados por David (18-11-2026): descargas y vida privada/parejas.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Angulo:
    clave: str
    tipos: tuple[str, ...]
    titulo: str                     # plantilla con {n}
    encargo: str                    # lo que el post tiene que contar
    consultas: tuple[str, ...]      # al corpus, con {n}
    keyword: str                    # la consulta objetivo, con {n}
    señales_gsc: tuple[str, ...]    # palabras de una consulta de GSC que piden ESTE ángulo


ANGULOS: tuple[Angulo, ...] = (
    Angulo("historia", ("album",), "Cómo se hizo «{n}»",
           "la historia del disco: cuándo y cómo nació, quién estuvo, qué contó Robe de él",
           ("cómo se grabó el disco {n}", "historia del disco {n}", "Robe habla de {n}"),
           "{n} historia", ("historia", "grab", "productor", "estudio", "como se hizo")),
    Angulo("directo", ("album", "song"), "«{n}» en directo",
           "cómo ha sonado en los conciertos: giras, cambios, momentos documentados",
           ("{n} en directo", "{n} en concierto gira"),
           "{n} en directo", ("directo", "en vivo", "concierto", "gira", "live")),
    Angulo("historia", ("song",), "La historia de «{n}»",
           "cómo nació la canción, quién la firma y qué contó Robe de ella",
           ("cómo nació la canción {n}", "historia de la canción {n}", "quién escribió {n}"),
           "{n} historia", ("historia", "quien escribio", "autor", "origen", "inspir")),
    Angulo("con-robe", ("person",), "{n} y Robe",
           "su relación con Robe: dónde coincidieron, qué hicieron juntos, qué contó",
           ("{n} Robe", "{n} Extremoduro", "{n} habla de Robe"),
           "{n} robe", ("robe",)),
    Angulo("robe-aqui", ("place",), "Robe y {n}",
           "lo que une a Robe y Extremoduro con este lugar: canciones, conciertos, vida",
           ("Robe en {n}", "Extremoduro en {n}", "{n} Robe Extremoduro"),
           "robe {n}", ("robe", "extremoduro")),
)

# Vetos de David (18-11-2026). La causa de la muerte NO se veta.
_ARTICULOS = {"el", "la", "los", "las", "un", "una"}
_VETO = re.compile(r"\b(?:pareja|novia|novio|esposa|esposo|mujer de|marido|hij[oa]s?|"
                   r"vida privada|descarga\w*|mp3|torrent|gratis)\b", re.I)
PROPIOS = ("robe_interview", "entorno_interview")
# Material mínimo para proponer: pasajes que de verdad responden al ángulo.
MIN_PROPIOS, MIN_TOTAL = 1, 3
SEMANAS_SIN_REPETIR = 6


@dataclass
class Idea:
    tipo: str
    entidad_id: int
    nombre: str
    ruta: str
    angulo: str
    titulo: str
    encargo: str
    keyword: str
    material_propio: int = 0
    material_total: int = 0
    fuentes: list[str] = field(default_factory=list)
    gsc_impresiones: int | None = None
    gsc_consultas: list[str] = field(default_factory=list)
    volumen: int | None = None
    canibaliza: str | None = None
    descarte: str | None = None

    @property
    def puntos(self) -> float:
        """Transparente: material (lo propio pesa el doble) × (1 + demanda)."""
        dem = (self.gsc_impresiones or 0) + (self.volumen or 0)
        return (2 * self.material_propio + self.material_total) * (1 + dem / 100)

    def to_dict(self) -> dict:
        return {**asdict(self), "puntos": round(self.puntos, 1)}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _pliega(s: str) -> str:
    """Sin tildes pero CON mayúsculas: la mayúscula es lo que distingue el nombre propio."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def nombra(texto: str, nombre: str) -> bool:
    """¿Nombra el texto la entidad? Como palabra completa y como NOMBRE PROPIO: con su
    palabra significativa en mayúscula («La Hoguera», «Mayéutica») o citada entre comillas
    o tras «canción/disco». Así no cuenta «nosotros en la hoguera» (una reseña de *Tú en tu
    casa…*: asesor, 18-11-2026) ni un «salir» cualquiera. Mismo espíritu que
    `youtube_relevance` con los títulos cortos."""
    t, n = _pliega(texto), _pliega(nombre).strip()
    if not n:
        return False
    for m in re.finditer(rf"(?<![\w]){re.escape(n)}(?![\w])", t, re.I):
        trozo = m.group(0)
        palabras = trozo.split()
        significativa = next((w for w in palabras if w.lower() not in _ARTICULOS), palabras[0])
        if significativa[:1].isupper():
            return True
        antes = t[max(0, m.start() - 12):m.start()].lower()
        if re.search(r"(?:[«\"“]|\b(?:cancion|tema|disco|album)\s+)$", antes):
            return True
    return False


def _gsc(ruta_datos: Path | None = None) -> tuple[dict, dict]:
    for base in (Path("/app/data"), Path(__file__).resolve().parents[3] / "data"):
        f = (ruta_datos or base) / "gsc_page_queries.json"
        if f.exists():
            d = json.loads(f.read_text())
            return d.get("pages", {}), d.get("period", {})
    return {}, {}


def candidatas(db) -> list[Idea]:
    """Entidad con ficha publicada × ángulo de su tipo."""
    from app.db.models import Album, Artist, Person, Place, SeoContent, Song
    from app.services.versiones import es_original

    publicadas = {(t, i) for t, i in db.query(SeoContent.entity_type, SeoContent.entity_id)
                  .filter(SeoContent.published.is_(True))}
    artistas = {a.id: a.slug for a in db.query(Artist)}
    discos = {a.id: a for a in db.query(Album)}
    out: list[Idea] = []

    def añadir(tipo: str, ident: int, nombre: str, ruta: str) -> None:
        for a in ANGULOS:
            if tipo in a.tipos:
                n = nombre.split(",")[0].strip()
                # Sin signos que DataForSEO no admite: uno solo tumba el lote entero
                # (como «Garden Lodge, Kensington» en las propuestas de entidades).
                from scripts.relaciones.propuestas import keyword_de
                out.append(Idea(tipo, ident, nombre, ruta, a.clave, a.titulo.format(n=n),
                                a.encargo, keyword_de(a.keyword.format(n=n))))

    for al in discos.values():
        art = artistas.get(al.artist_id)
        if ("album", al.id) in publicadas and art in ("robe", "extremoduro") and al.kind == "studio":
            añadir("album", al.id, al.title, f"/{art}/{al.slug}")
    for s in db.query(Song):
        al = discos.get(s.album_id)
        art = artistas.get(al.artist_id) if al else None
        if ("song", s.id) in publicadas and al and es_original(s, al):
            añadir("song", s.id, s.title, f"/{art}/{al.slug}/{s.slug}")
    for p in db.query(Person):
        if ("person", p.id) in publicadas and p.slug != "robe-iniesta":
            añadir("person", p.id, p.stage_name or p.full_name, f"/personas/{p.slug}")
    for pl in db.query(Place):
        if ("place", pl.id) in publicadas:
            añadir("place", pl.id, pl.name, f"/lugares/{pl.slug}")
    return out


def _pide_angulo(consulta: str, señales: list[str]) -> bool:
    qn = _norm(consulta)
    return "letra" not in qn and any(re.search(rf"\b{re.escape(s)}", qn) for s in señales)


def medir_demanda(ideas: list[Idea], paginas: dict) -> None:
    """Impresiones de GSC de la ficha en consultas que piden el ángulo, y si la ficha ya
    posiciona alguna (pos. ≤ 20): entonces ese ángulo es de la ficha (canibalización)."""
    for idea in ideas:
        ang = next(a for a in ANGULOS if a.clave == idea.angulo and idea.tipo in a.tipos)
        filas = paginas.get(idea.ruta) or []
        nombre = _norm(idea.nombre)
        # Una señal que forma parte del propio nombre no dice nada («historia» en
        # «Historias prohibidas»), y una consulta de LETRA pide la letra, no el ángulo:
        # sin esto salían canibalizaciones falsas (18-11-2026).
        señales = [s for s in ang.señales_gsc if s not in nombre]

        casan = [f for f in filas if _pide_angulo(f["query"], señales)]
        idea.gsc_impresiones = sum(int(f.get("impressions") or 0) for f in casan) if filas else None
        idea.gsc_consultas = [f["query"] for f in sorted(casan, key=lambda f: -f["impressions"])[:3]]
        protegida = next((f for f in casan if (f.get("position") or 99) <= 20
                          and (f.get("impressions") or 0) >= 10), None)
        if protegida:
            idea.canibaliza = (f"la ficha ya posiciona «{protegida['query']}» "
                               f"(pos. {protegida['position']}): ampliar la ficha")


def filtrar(db, ideas: list[Idea]) -> None:
    """Vetos, lo ya propuesto (cualquier estado) y lo reciente sobre la entidad."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.db.models import ContentProposal

    # Ese ángulo de esa entidad ya pasó por el banco, en CUALQUIER estado: se descartó,
    # se usó o está vivo. Sin esto volvía a salir arriba cada lunes y moría en silencio en
    # la clave única (el fallo de los aniversarios otra vez: asesor, 18-11-2026).
    ya = {(st, sid) for st, sid in db.query(ContentProposal.source_type, ContentProposal.source_id)
          .filter(ContentProposal.source_type.like("cat-%"))}
    desde = datetime.now(UTC) - timedelta(weeks=SEMANAS_SIN_REPETIR)
    recientes = [t for (t,) in db.execute(text(
        "select title from content_proposals where created_at >= :d and status <> 'discarded' "
        "union all select title from posts where coalesce(published_at, created_at) >= :d"),
        {"d": desde})]
    for idea in ideas:
        if _VETO.search(f"{idea.titulo} {idea.keyword}"):
            idea.descarte = "tema vetado"
        elif (source_type_de(idea.tipo, idea.angulo), idea.entidad_id) in ya:
            idea.descarte = "ese ángulo de esa entidad ya pasó por el banco"
        elif any(nombra(r, idea.nombre.split(",")[0]) for r in recientes):
            idea.descarte = f"ya hay algo sobre «{idea.nombre}» en las últimas {SEMANAS_SIN_REPETIR} semanas"


def medir_material(db, idea: Idea) -> None:
    from app.services.corpus_for_queries import es_entrevista_transcrita, material_para_consultas

    ang = next(a for a in ANGULOS if a.clave == idea.angulo and idea.tipo in a.tipos)
    n = idea.nombre.split(",")[0].strip()
    pasajes = material_para_consultas(db, [c.format(n=n) for c in ang.consultas], k=5, max_pasajes=8)
    # Solo cuenta lo que nombra a la entidad: un vecino semántico no responde al ángulo.
    utiles = [p for p in pasajes if nombra(p.get("fragmento") or "", n)]
    idea.material_total = len(utiles)
    idea.material_propio = sum(1 for p in utiles if p.get("kind") in PROPIOS
                               or es_entrevista_transcrita(p.get("kind"), p.get("title")))
    idea.fuentes = list(dict.fromkeys(f"{p.get('kind')} · {p.get('title')}" for p in utiles))[:4]
    if idea.material_propio < MIN_PROPIOS and idea.material_total < MIN_TOTAL:
        idea.descarte = idea.descarte or (f"sin material: {idea.material_propio} propio(s), "
                                          f"{idea.material_total} en total")


def banco(db, *, muestra: int = 10, medir_top: int = 40, volumen: bool = True,
          solo: set[tuple[str, str]] | None = None) -> dict:
    """Las mejores ideas con su evidencia. No escribe nada en la BD. `solo`: limitar a
    estos (tipo, ángulo)."""
    paginas, periodo = _gsc()
    ideas = [i for i in candidatas(db) if solo is None or (i.tipo, i.angulo) in solo]
    medir_demanda(ideas, paginas)
    filtrar(db, ideas)
    vivas = [i for i in ideas if not i.descarte and not i.canibaliza]
    # Material (embeddings + Qdrant) solo para `medir_top`: es lo caro. La mitad, las de
    # más demanda; la otra mitad ROTA por semana, para que las canciones (casi todas sin
    # impresiones) lleguen a medirse (asesor, 18-11-2026).
    vivas.sort(key=lambda i: -((i.gsc_impresiones or 0) + (5 if i.tipo == "album" else 0)))
    mitad = medir_top // 2
    resto = vivas[mitad:]
    if resto:
        from datetime import date
        ini = (date.today().isocalendar().week * mitad) % len(resto)
        resto = (resto[ini:] + resto[:ini])[:medir_top - mitad]
    a_medir = vivas[:mitad] + resto
    for i in a_medir:
        medir_material(db, i)
    con_material = [i for i in a_medir if not i.descarte]
    if volumen and con_material:
        from app.services.seo_research import search_volume

        try:
            vols = search_volume(sorted({i.keyword for i in con_material if i.keyword}))
            for i in con_material:
                v = vols.get(i.keyword)
                i.volumen = v.volume if (v is not None and not v.sin_dato) else None
        except Exception:  # noqa: BLE001 — sin DataForSEO, volumen n/d
            pass
    con_material.sort(key=lambda i: -i.puntos)
    # Una idea por entidad en la muestra.
    vistas, elegidas = set(), []
    for i in con_material:
        if (i.tipo, i.entidad_id) not in vistas:
            elegidas.append(i)
            vistas.add((i.tipo, i.entidad_id))
        if len(elegidas) >= muestra:
            break
    return {
        "periodo_gsc": periodo,
        "candidatas": len(ideas),
        "vetadas_o_recientes": sum(1 for i in ideas if i.descarte and not i.descarte.startswith("sin material")),
        "canibalizarian": sum(1 for i in ideas if i.canibaliza),
        "medidas": len(a_medir),
        "sin_material": sum(1 for i in a_medir if i.descarte),
        "muestra": [i.to_dict() for i in elegidas],
        "ejemplos_canibalizacion": [i.to_dict() for i in ideas if i.canibaliza][:5],
    }


# --------------------------------------------------------------------------- #
# Al banco de propuestas (1-2 por semana: decisión de David, 18-11-2026)
# --------------------------------------------------------------------------- #
CATALOGO_POR_SEMANA = 2
# Los ángulos que entran al banco. «Cómo se hizo un disco» pasó su prueba de fuego
# (Mayéutica, 3/3); canciones, personas, lugares y directos se encienden tras la suya:
# por el camino de esos tipos las canciones sacaban 18-42 (18-11-2026).
ANGULOS_ACTIVOS = {("album", "historia")}
_COD_TIPO = {"album": "alb", "song": "son", "person": "per", "place": "pla"}
_COD_ANGULO = {"historia": "his", "directo": "dir", "con-robe": "con", "robe-aqui": "aqu"}
TIPO_DE_CODIGO = {v: k for k, v in _COD_TIPO.items()}


def source_type_de(tipo: str, angulo: str) -> str:
    """`cat-alb-his`: la entidad y el ángulo en la clave única (kind, source_type,
    source_id), para que el mismo ángulo de la misma entidad no se proponga dos veces."""
    return f"cat-{_COD_TIPO[tipo]}-{_COD_ANGULO[angulo]}"


def entidad_de(source_type: str | None) -> tuple[str, str] | None:
    """(tipo, ángulo) de un `source_type` de catálogo, o None."""
    if not (source_type or "").startswith("cat-"):
        return None
    _, t, a = source_type.split("-", 2)
    angulo = {v: k for k, v in _COD_ANGULO.items()}.get(a)
    return (TIPO_DE_CODIGO[t], angulo) if t in TIPO_DE_CODIGO and angulo else None


def filas_para_el_banco(db, *, n: int = CATALOGO_POR_SEMANA) -> list[dict]:
    """Las `n` mejores ideas, listas para `content_proposals` (sin target_keyword: el
    reparto «ampliar o nuevo» no las toca; su ángulo ya es distinto de la ficha)."""
    out = []
    for i in banco(db, muestra=n, solo=ANGULOS_ACTIVOS)["muestra"]:
        evidencia = (f"Material: {i['material_propio']} propio(s) de {i['material_total']} "
                     f"({'; '.join(i['fuentes'][:3])}). Demanda: GSC "
                     f"{'n/d' if i['gsc_impresiones'] is None else i['gsc_impresiones']} impr., "
                     f"volumen {'n/d' if i['volumen'] is None else i['volumen']}/mes.")
        out.append({
            "kind": "evergreen",
            "source_type": source_type_de(i["tipo"], i["angulo"]),
            "source_id": i["entidad_id"],
            "title": i["titulo"],
            "angle": f"{i['encargo'][:1].upper()}{i['encargo'][1:]}. {evidencia}",
            "keywords": [{"keyword": i["keyword"], "volume": i["volumen"]}] if i["keyword"] else [],
            "search_volume": i["volumen"],
            "signal_source": "catalogo",
            "content_key": f"catalogo:{i['tipo']}_{i['entidad_id']}:{i['angulo']}",
        })
    return out
