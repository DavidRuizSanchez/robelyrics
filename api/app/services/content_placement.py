"""¿Esta idea es un post nuevo o amplía una página que ya existe?

El banco de propuestas del blog solo sabía proponer posts nuevos, y ningún paso
comparaba la idea con lo publicado. Medido el 19-10-2026 sobre
`gsc_page_queries.json` (24-07 → 16-10-2026):

  - «integrantes de extremoduro» (#484): la posiciona **`/personas`**, con 9
    variantes, 1.498 impresiones y posiciones de 7,5 a 11,1. `/extremoduro` está
    en la 35–48. Un post nuevo le habría quitado la consulta a la página que la
    gana.
  - «qué género es extremoduro» (#485): `/extremoduro` está en la 6,6, y **dos
    posts** del blog ya compiten por la misma consulta. Sería la tercera página.

Aquí se decide con evidencia, y la decisión es determinista y explicable. NO se da
un «porcentaje de éxito»: no hay con qué medirlo, y un número inventado en el
panel es peor que ninguno. Lo que sí se da es por qué, con la cifra y su ventana.

Las señales, de más a menos fuerte:

  1. **GSC** — qué página nuestra recibe YA impresiones por las keywords de la
     propuesta. Si una concentra la mayoría en posición ≤ 20, Google ya la asocia
     a la búsqueda: escribir otra es canibalizarla.
  2. **SERP** — si una página nuestra sale en el top para la keyword principal.
  3. **Semántica** — la página más parecida (`pages_v1`, ver
     `scripts/seo/embed_pages.py`) y la ficha de la entidad central
     (`blog_anchor.resolve_central_entity`).

Los candidatos son fichas (`seo_content`), posts publicados y las páginas que
viven en código (`PAGINAS_CODIGO`): que una página no esté en la BD no puede
volver a significar que es invisible (ya pasó con los estudios).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services import seo_style

logger = logging.getLogger(__name__)

SITE_HOSTS = ("entreinteriores.com", "www.entreinteriores.com")

# Páginas índice con ficha propia (`seo_content.entity_type='page'`). La clave es
# el `entity_id`. Se amplían como cualquier ficha.
PAGINAS = {
    1: {"slug": "personas", "path": "/personas", "label": "Integrantes y colegas (/personas)"},
}
PAGINA_POR_PATH = {v["path"]: k for k, v in PAGINAS.items()}

# Páginas que existen en código y NO tienen ficha: cuentan para no canibalizarlas,
# pero el motor no puede escribir en ellas («mejora manual»). Prefijos de ruta.
PAGINAS_CODIGO = ("/", "/discografia", "/estudios", "/libros", "/sellos", "/grupos",
                  "/temas", "/lugares", "/conceptos", "/blog")

# --- Umbrales ---------------------------------------------------------------- #
# Una página «es dueña» de la búsqueda si se lleva al menos esta parte de las
# impresiones de la propuesta, en posición media ≤ OWNER_MAX_POSITION y con un
# mínimo de impresiones que no sea ruido.
OWNER_SHARE = 0.5
OWNER_MAX_POSITION = 20.0
OWNER_MIN_IMPRESSIONS = 10
# Para contar como «página que compite» (canibalización existente).
COMPITE_MIN_IMPRESSIONS = 5
COMPITE_MAX_POSITION = 30.0
# Similitud coseno (text-embedding-3-large) entre la propuesta y el resumen de la
# página. PROVISIONALES: calibrar con `placement_backfill --dry-run` sobre el banco
# real antes de fiarse de la rama semántica. Por eso esa rama nunca da «alta».
SIM_AMPLIAR = 0.60
SIM_CANDIDATA = 0.45
MAX_CANDIDATOS = 3


# --------------------------------------------------------------------------- #
# Tipos
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    path: str
    kind: str                 # ficha | post | code
    label: str
    target: str | None = None  # «ficha:<seo_content_id>» | «post:<id>» (None = código)
    entity_type: str | None = None
    entity_id: int | None = None
    gsc_impressions: int = 0
    gsc_clicks: int = 0
    gsc_position: float | None = None
    gsc_queries: list[dict] = field(default_factory=list)
    serp_rank: int | None = None
    similarity: float | None = None
    is_anchor: bool = False

    @property
    def mergeable(self) -> bool:
        return self.target is not None

    def score(self) -> float:
        """Orden del selector: lo que Google ya asocia pesa más que el parecido."""
        s = 0.0
        if self.gsc_impressions:
            pos = self.gsc_position or 100.0
            s += min(self.gsc_impressions, 2000) / 20.0 * (1.0 if pos <= 20 else 0.4)
        if self.serp_rank:
            s += 40.0 / self.serp_rank
        if self.similarity:
            s += self.similarity * 60.0
        if self.is_anchor:
            s += 15.0
        return round(s, 2)


@dataclass
class Placement:
    decision: str              # ampliar | nuevo
    confidence: str            # alta | media | baja
    recommended: str | None    # target recomendado (None = contenido nuevo)
    reasons: list[str]
    candidates: list[Candidate]
    competing: list[str] = field(default_factory=list)  # rutas propias que ya compiten
    period: str | None = None
    serp_checked: bool = False
    semantic_checked: bool = False
    # Desde el 19-10-2026 cada keyword va a SU página: «extremoduro necesito droga
    # y amor» es de la ficha de la canción, no de /extremoduro. `groups` es el
    # reparto (ver `analyze`); los campos de arriba son los del grupo principal.
    groups: list[dict] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for c, raw in zip(self.candidates, d["candidates"], strict=True):
            raw["mergeable"] = c.mergeable
            raw["score"] = c.score()
        d["computed_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        return d


# --------------------------------------------------------------------------- #
# Señal 1 — GSC
# --------------------------------------------------------------------------- #
def load_gsc_pages() -> tuple[dict, str | None]:
    """El volcado de 12 semanas que usa todo el circuito SEO (`gsc_fetch_page_queries`)."""
    for p in (Path("/app/data/gsc_page_queries.json"),
              Path(__file__).resolve().parents[3] / "data" / "gsc_page_queries.json"):
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            per = data.get("period") or {}
            periodo = f"{per.get('start')}..{per.get('end')}" if per else None
            return data.get("pages", {}), periodo
    logger.warning("[placement] no hay data/gsc_page_queries.json")
    return {}, None


def _firma(texto: str) -> frozenset[str]:
    """Tokens de contenido, sin orden y con el mismo prefijo que `seo_style.cubre`.

    «extremoduro integrantes» e «integrantes de extremoduro» son la misma búsqueda;
    «extremoduro integrantes 1990», no.
    """
    pref = seo_style._PREFIJO
    return frozenset(t[:pref] for t in seo_style.content_tokens(texto))


def gsc_matches(pages: dict, keywords: list[str]) -> dict[str, list[dict]]:
    """Por ruta, las consultas de GSC que son alguna de las keywords de la propuesta."""
    firmas = {f for f in (_firma(k) for k in keywords) if f}
    out: dict[str, list[dict]] = {}
    for path, queries in pages.items():
        hits = [q for q in queries if _firma(q.get("query") or "") in firmas]
        if hits:
            out[path] = hits
    return out


def _agregar(hits: list[dict]) -> tuple[int, int, float | None]:
    imp = sum(int(q.get("impressions") or 0) for q in hits)
    clics = sum(int(q.get("clicks") or 0) for q in hits)
    if not imp:
        return 0, clics, None
    pos = sum(float(q.get("position") or 0) * int(q.get("impressions") or 0)
              for q in hits) / imp
    return imp, clics, round(pos, 1)


# --------------------------------------------------------------------------- #
# Ruta → candidato
# --------------------------------------------------------------------------- #
def normalize_path(url_or_path: str) -> str | None:
    """URL absoluta o ruta → ruta del sitio. None si es de otro dominio."""
    if not url_or_path:
        return None
    if url_or_path.startswith("http"):
        u = urlparse(url_or_path)
        if (u.netloc or "").lower() not in SITE_HOSTS:
            return None
        path = u.path or "/"
    else:
        path = url_or_path
    path = "/" + path.strip("/")
    return path


def _es_codigo(path: str) -> bool:
    return any(path == p or (p != "/" and path.startswith(p + "/")) for p in PAGINAS_CODIGO)


def candidate_for_path(db, path: str) -> Candidate | None:
    """Qué hay publicado en esa ruta y si el motor puede escribir en ello."""
    from app.db.models import Post, SeoContent

    if path in PAGINA_POR_PATH:
        pid = PAGINA_POR_PATH[path]
        sc = (db.query(SeoContent)
              .filter(SeoContent.entity_type == "page", SeoContent.entity_id == pid).first())
        label = PAGINAS[pid]["label"]
        if sc and sc.published:
            return Candidate(path=path, kind="ficha", label=label, target=f"ficha:{sc.id}",
                             entity_type="page", entity_id=pid)
        return Candidate(path=path, kind="code", label=label)

    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) == 2 and parts[0] == "blog":
        post = (db.query(Post)
                .filter(Post.slug == parts[1], Post.status == "published").first())
        if post:
            return Candidate(path=path, kind="post", label=post.title,
                             target=f"post:{post.id}", entity_type="post", entity_id=post.id)
        return None

    from scripts.seo.gsc_optimize import _resolve_entity

    ent = _resolve_entity(db, path)
    if ent:
        sc = (db.query(SeoContent)
              .filter(SeoContent.entity_type == ent[0], SeoContent.entity_id == ent[1],
                      SeoContent.published.is_(True)).first())
        if sc and (sc.body_md or "").strip():
            return Candidate(path=path, kind="ficha",
                             label=sc.h1 or sc.meta_title or sc.slug,
                             target=f"ficha:{sc.id}", entity_type=ent[0], entity_id=ent[1])
    if _es_codigo(path):
        return Candidate(path=path, kind="code", label=path)
    return None


def candidate_for_target(db, target: str) -> Candidate | None:
    """El candidato de un target («ficha:12» / «post:7»), sin evidencia."""
    from app.db.models import Post, SeoContent
    from app.services.url_resolver import canonical_path_for

    tipo, _, ident = (target or "").partition(":")
    if not ident.isdigit():
        return None
    if tipo == "post":
        post = db.get(Post, int(ident))
        if not post or post.status != "published":
            return None
        return Candidate(path=f"/blog/{post.slug}", kind="post", label=post.title,
                         target=target, entity_type="post", entity_id=post.id)
    if tipo == "ficha":
        sc = db.get(SeoContent, int(ident))
        if not sc or not sc.published:
            return None
        if sc.entity_type == "page":
            path = (PAGINAS.get(sc.entity_id) or {}).get("path")
        else:
            path = canonical_path_for(db, sc.entity_type, sc.entity_id)
        if not path:
            return None
        return Candidate(path=path, kind="ficha", label=sc.h1 or sc.meta_title or sc.slug,
                         target=target, entity_type=sc.entity_type, entity_id=sc.entity_id)
    return None


def _n(x: float | None, dec: int | None = None) -> str:
    """Cifra con coma decimal, que es como se lee en el panel y en el correo."""
    if x is None:
        return "—"
    txt = f"{x:.{dec}f}" if dec is not None else f"{x}"
    return txt.replace(".", ",")


# --------------------------------------------------------------------------- #
# Decisión (pura: sin BD ni red, para poder testearla con datos reales)
# --------------------------------------------------------------------------- #
def decide(candidates: list[Candidate], *, period: str | None = None,
           serp_checked: bool = False, semantic_checked: bool = False) -> Placement:
    reasons: list[str] = []
    ventana = f" ({period.replace('..', ' → ')})" if period else ""
    total_imp = sum(c.gsc_impressions for c in candidates)

    competing = sorted(
        (c for c in candidates
         if c.gsc_impressions >= COMPITE_MIN_IMPRESSIONS
         and (c.gsc_position or 100) <= COMPITE_MAX_POSITION),
        key=lambda c: (c.gsc_position or 100),
    )

    def _cierra(decision: str, conf: str, rec: Candidate | None) -> Placement:
        ordenados = sorted(candidates, key=lambda c: -c.score())
        if rec is not None and rec in ordenados:
            ordenados.remove(rec)
            ordenados.insert(0, rec)
        return Placement(
            decision=decision, confidence=conf,
            recommended=rec.target if rec is not None else None,
            reasons=reasons, candidates=ordenados[:MAX_CANDIDATOS],
            competing=[c.path for c in competing], period=period,
            serp_checked=serp_checked, semantic_checked=semantic_checked,
        )

    if len(competing) >= 2:
        reasons.append(
            "Ya compiten " + str(len(competing)) + " páginas propias por estas búsquedas: "
            + ", ".join(f"{c.path} (pos {_n(c.gsc_position)}, {c.gsc_impressions} impr.)"
                        for c in competing[:4])
            + f"{ventana}. Otra más sería canibalizar; se amplía la mejor posicionada."
        )

    # 1) Google ya asocia la búsqueda a una página nuestra.
    if total_imp:
        dueno = max(candidates, key=lambda c: c.gsc_impressions)
        share = dueno.gsc_impressions / total_imp
        if (dueno.gsc_impressions >= OWNER_MIN_IMPRESSIONS and share >= OWNER_SHARE
                and (dueno.gsc_position or 100) <= OWNER_MAX_POSITION):
            reasons.insert(0, (
                f"Google ya asocia estas búsquedas a {dueno.path}: "
                f"{dueno.gsc_impressions} impresiones ({round(share * 100)} % del total), "
                f"posición media {_n(dueno.gsc_position)}{ventana}."
            ))
            conf = ("alta" if (dueno.gsc_position or 100) <= 12 and dueno.gsc_impressions >= 50
                    else "media")
            if not dueno.mergeable:
                reasons.append(f"{dueno.path} vive en código: la ampliación es manual. "
                               "No conviene un post nuevo que le quite la consulta.")
            return _cierra("ampliar", conf, dueno)

    # 2) Una página nuestra ya sale en el top de la SERP.
    en_serp = sorted((c for c in candidates if c.serp_rank), key=lambda c: c.serp_rank)
    if en_serp:
        c = en_serp[0]
        reasons.insert(0, f"{c.path} ya aparece en la posición {c.serp_rank} de Google "
                          "para la keyword principal.")
        return _cierra("ampliar", "media", c)

    # Con canibalización pero sin dueño claro: la mejor posicionada.
    if competing:
        mejor = competing[0]
        if len(competing) >= 2:
            return _cierra("ampliar", "media", mejor)

    # 3) Parecido semántico. Umbrales provisionales: nunca da «alta».
    parecidos = sorted((c for c in candidates if c.similarity is not None),
                       key=lambda c: -(c.similarity or 0))
    if parecidos and (parecidos[0].similarity or 0) >= SIM_AMPLIAR:
        c = parecidos[0]
        reasons.insert(0, f"{c.path} ya trata el tema (similitud {_n(c.similarity, 2)}) y "
                          "ninguna página posiciona todavía: ampliarla suma autoridad a "
                          "una URL que ya existe en vez de empezar de cero.")
        return _cierra("ampliar", "baja", c)

    if parecidos and (parecidos[0].similarity or 0) >= SIM_CANDIDATA:
        reasons.insert(0, f"El tema roza {parecidos[0].path} (similitud "
                          f"{_n(parecidos[0].similarity, 2)}) pero no lo cubre: contenido nuevo, "
                          "enlazado a esa página.")
        return _cierra("nuevo", "media", None)

    if not (total_imp or serp_checked or semantic_checked):
        reasons.insert(0, "Sin datos de GSC, SERP ni similitud para comparar: se propone "
                          "contenido nuevo por defecto.")
        return _cierra("nuevo", "baja", None)
    reasons.insert(0, "Ninguna página propia posiciona por estas búsquedas ni trata el "
                      "tema: contenido nuevo.")
    return _cierra("nuevo", "alta" if not total_imp else "media", None)


# --------------------------------------------------------------------------- #
# Señal 3 — semántica (`pages_v1`)
# --------------------------------------------------------------------------- #
PAGES_COLLECTION = "pages_v1"


def semantic_neighbours(texto: str, *, k: int = 5) -> list[dict]:
    """Las páginas publicadas más parecidas al texto. [] si Qdrant no responde."""
    try:
        from app.services.embeddings import get_embedder
        from app.services.qdrant_client import get_qdrant

        vec = get_embedder().embed_one(texto)
        resp = get_qdrant().query_points(collection_name=PAGES_COLLECTION, query=vec,
                                         limit=k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[placement] búsqueda semántica no disponible: %s", exc)
        return []
    return [{"path": (r.payload or {}).get("path"), "score": float(r.score)}
            for r in resp.points if (r.payload or {}).get("path")]


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #
def proposal_keywords(proposal) -> list[str]:
    """Las keywords ACTIVAS: las que David desmarca en el panel no cuentan."""
    kws = [k.get("keyword") for k in (proposal.keywords or [])
           if isinstance(k, dict) and not k.get("excluded")]
    excluidas = {(k.get("keyword") or "").lower() for k in (proposal.keywords or [])
                 if isinstance(k, dict) and k.get("excluded")}
    if proposal.target_keyword and proposal.target_keyword.lower() not in excluidas:
        kws.insert(0, proposal.target_keyword)
    vistos, out = set(), []
    for k in kws:
        k = (k or "").strip()
        if k and k.lower() not in vistos:
            vistos.add(k.lower())
            out.append(k)
    return out


# --------------------------------------------------------------------------- #
# Cada keyword a su página
# --------------------------------------------------------------------------- #
@dataclass
class Ruta:
    path: str | None      # None = ninguna página propia la responde
    via: str              # gsc | titulo | semantica | ninguna
    motivo: str


def dueno_gsc(pages: dict, keyword: str) -> tuple[str, dict] | None:
    """La página que más impresiones recibe por ESTA keyword, en pos. ≤ 20."""
    firma = _firma(keyword)
    mejor = None
    for path, qs in pages.items():
        for q in qs:
            if _firma(q.get("query") or "") != firma:
                continue
            imp, pos = int(q.get("impressions") or 0), float(q.get("position") or 100)
            if imp >= 3 and pos <= OWNER_MAX_POSITION and (
                    mejor is None or imp > mejor[1]["impressions"]):
                mejor = (path, {"impressions": imp, "position": pos})
    return mejor


def repartir(keywords: list[str], *, por_gsc, por_titulo, por_semantica) -> list[tuple[str, Ruta]]:
    """[(keyword, Ruta)]. Puro: las tres búsquedas llegan inyectadas.

    De lo más fuerte a lo más débil: lo que Google ya asocia, el título de una
    canción o un disco (`kw_attribute.dueno`: «extremoduro necesito droga y amor»
    es de esa canción), y el parecido con lo publicado.
    """
    out = []
    for kw in keywords:
        g = por_gsc(kw)
        if g:
            path, d = g
            out.append((kw, Ruta(path, "gsc", f"«{kw}» ya la posiciona {path} "
                                              f"(pos {_n(round(d['position'], 1))}, "
                                              f"{d['impressions']} impr.)")))
            continue
        t = por_titulo(kw)
        if t:
            path, titulo = t
            out.append((kw, Ruta(path, "titulo", f"«{kw}» nombra «{titulo}»: es de su "
                                                 f"ficha, {path}")))
            continue
        sm = por_semantica(kw)
        if sm:
            path, sim = sm
            out.append((kw, Ruta(path, "semantica", f"«{kw}» es de lo que trata {path} "
                                                    f"(similitud {_n(sim, 2)})")))
            continue
        out.append((kw, Ruta(None, "ninguna", f"Ninguna página propia responde «{kw}»")))
    return out


_CONF_VIA = {"gsc": "alta", "titulo": "alta", "semantica": "baja"}


def _texto_destino(db, cand: Candidate) -> tuple[str, str, str]:
    from app.db.models import Post, SeoContent

    tipo, _, ident = (cand.target or "").partition(":")
    if tipo == "ficha" and ident.isdigit():
        sc = db.get(SeoContent, int(ident))
        if sc:
            return sc.body_md or "", sc.meta_title or "", sc.meta_description or ""
    if tipo == "post" and ident.isdigit():
        po = db.get(Post, int(ident))
        if po:
            return po.body_md or "", po.meta_title or po.title, po.meta_description or ""
    return "", "", ""


def ya_cubierto(body: str, title: str, description: str, keywords: list[str],
                gsc_page: list[dict], alias: dict | None = None) -> bool:
    """La página ya lo responde en el cuerpo Y lo promete en la metadata, y Google
    la tiene en pos. ≤ 10: ahí falta posición, no contenido (mismo criterio que
    `seo_opportunities.classify_queries`, que deja eso fuera del circuito)."""
    cuerpo = seo_style.expandir_alias(seo_style.flatten(body), alias)
    meta = seo_style.expandir_alias(seo_style.flatten(f"{title} {description}"), alias)
    for kw in keywords:
        if not (seo_style.cubre(cuerpo, kw) and seo_style.cubre(meta, kw)):
            return False
        pos = [float(q.get("position") or 100) for q in gsc_page
               if _firma(q.get("query") or "") == _firma(kw)]
        if not pos or min(pos) > 10:
            return False
    return bool(keywords)


def _evaluar(db, keywords: list[str], *, texto: str, target_keyword: str | None,
             pages: dict, period: str | None, use_serp: bool, use_semantic: bool,
             client, anchor) -> Placement:
    """La decisión con evidencia de siempre, sobre un grupo de keywords."""
    por_ruta: dict[str, Candidate] = {}

    def _cand(path: str) -> Candidate | None:
        if path in por_ruta:
            return por_ruta[path]
        c = candidate_for_path(db, path)
        if c:
            por_ruta[path] = c
        return c

    for path, hits in gsc_matches(pages, keywords).items():
        c = _cand(path)
        if not c:
            continue
        c.gsc_impressions, c.gsc_clicks, c.gsc_position = _agregar(hits)
        c.gsc_queries = sorted(
            ({"query": q.get("query"), "impressions": int(q.get("impressions") or 0),
              "position": q.get("position")} for q in hits),
            key=lambda q: -q["impressions"])[:6]

    serp_checked = False
    if use_serp and target_keyword:
        from app.services import serp_intent

        v = serp_intent.classify(target_keyword, client=client)
        serp_checked = bool(v.top_urls)
        for rank, url in enumerate(v.top_urls, start=1):
            path = normalize_path(url)
            if path:
                c = _cand(path)
                if c and not c.serp_rank:
                    c.serp_rank = rank

    if anchor:
        from app.services.url_resolver import canonical_path_for

        path = canonical_path_for(db, anchor.entity_type, anchor.entity.id)
        c = _cand(path) if path else None
        if c:
            c.is_anchor = True

    semantic_checked = False
    if use_semantic and texto:
        vecinos = semantic_neighbours(texto)
        semantic_checked = bool(vecinos)
        for v in vecinos:
            c = _cand(v["path"])
            if c and (c.similarity is None or v["score"] > c.similarity):
                c.similarity = round(v["score"], 3)

    return decide(list(por_ruta.values()), period=period,
                  serp_checked=serp_checked, semantic_checked=semantic_checked)


def analyze(db, proposal, *, pages: dict | None = None, period: str | None = None,
            use_serp: bool = True, use_semantic: bool = True, client=None) -> Placement:
    """El análisis completo de una propuesta. No escribe nada en la BD.

    Reparte cada keyword a su página (`repartir`) y evalúa cada grupo por separado.
    El grupo principal (el de la keyword objetivo) da los campos de arriba, que es
    lo que leían el panel y el correo antes de los grupos.
    """
    from app.services.blog_anchor import resolve_central_entity
    from app.services.seo_opportunities import nombre_alias_index

    if pages is None:
        pages, period = load_gsc_pages()
    keywords = proposal_keywords(proposal)
    if not keywords:
        return Placement(decision="nuevo", confidence="baja", recommended=None,
                         reasons=["La propuesta no tiene keywords activas."],
                         candidates=[], period=period)

    indice = None

    def _por_titulo(kw: str):
        nonlocal indice
        try:
            from scripts.seo.kw_attribute import build_index, dueno

            if indice is None:
                indice = build_index()
            info, titulo = dueno(kw, *indice)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[placement] atribución por título no disponible: %s", exc)
            return None
        if not titulo or titulo.startswith("("):   # «(marca:…)» / «(sin atribuir)»
            return None
        cand = candidate_for_path(db, info.get("owner_url") or "")
        return (cand.path, info.get("owner_title") or titulo) if cand else None

    def _por_semantica(kw: str):
        if not use_semantic:
            return None
        vecinos = semantic_neighbours(kw, k=3)
        if vecinos and vecinos[0]["score"] >= SIM_AMPLIAR:
            return vecinos[0]["path"], round(vecinos[0]["score"], 3)
        return None

    rutas = repartir(keywords, por_gsc=lambda kw: dueno_gsc(pages, kw),
                     por_titulo=_por_titulo, por_semantica=_por_semantica)
    grupos: dict[str | None, list[tuple[str, Ruta]]] = {}
    for kw, r in rutas:
        grupos.setdefault(r.path, []).append((kw, r))

    alias = nombre_alias_index(db)
    anchor = resolve_central_entity(db, primary_keyword=proposal.target_keyword,
                                    title=proposal.title, angle=proposal.angle)
    principal = (proposal.target_keyword or keywords[0]).lower()
    salida: list[dict] = []
    placement_principal: Placement | None = None
    for path, miembros in grupos.items():
        kws = [k for k, _ in miembros]
        es_principal = principal in {k.lower() for k in kws}
        texto = " · ".join(x for x in ((proposal.title if es_principal else ""),
                                       *kws, (proposal.angle if es_principal else "")) if x)
        p = _evaluar(db, kws, texto=texto, target_keyword=kws[0], pages=pages,
                     period=period, use_serp=use_serp and es_principal,
                     use_semantic=use_semantic, client=client,
                     anchor=anchor if es_principal else None)
        motivos = [r.motivo for _, r in miembros]
        decision_evidencia = p.decision
        if path is not None:
            cand = next((c for c in p.candidates if c.path == path), None) \
                or candidate_for_path(db, path)
            if cand is not None:
                body, title, desc = _texto_destino(db, cand)
                if cand.mergeable and ya_cubierto(body, title, desc, kws,
                                                  pages.get(path) or [], alias):
                    p.decision, p.recommended, p.confidence = "cubierto", None, "alta"
                    motivos.append(f"{path} ya lo responde en el cuerpo y lo promete en el "
                                   "title/description, y está en el top 10: falta posición, "
                                   "no contenido.")
                else:
                    p.decision = "ampliar"
                    p.recommended = cand.target
                    vias = {r.via for _, r in miembros}
                    p.confidence = min((_CONF_VIA.get(v, "media") for v in vias),
                                       key=["baja", "media", "alta"].index)
                p.candidates = [cand] + [c for c in p.candidates if c.path != path]
                p.candidates = p.candidates[:MAX_CANDIDATOS]
        # Si el reparto contradice a la evaluación genérica («contenido nuevo» para
        # una keyword que nombra una canción), sus motivos no viajan: se leerían
        # como la conclusión.
        evidencia = p.reasons if p.decision == decision_evidencia else []
        p.reasons = motivos + [r for r in evidencia if r not in motivos]
        d = p.to_dict()
        d["keywords"] = kws
        # Por qué se eligió el destino (gsc | titulo | semantica | ninguna): el
        # panel lo explica en claro sin tener que leer los motivos en prosa.
        d["via"] = sorted({r.via for _, r in miembros})
        salida.append(d)
        # El principal manda; si la keyword objetivo estuviera excluida, el primero.
        if es_principal or placement_principal is None:
            placement_principal = p
            placement_principal.keywords = kws

    # El principal primero; el resto por volumen de keywords.
    salida.sort(key=lambda g: principal not in {k.lower() for k in g["keywords"]})
    assert placement_principal is not None
    placement_principal.groups = salida
    return placement_principal


def store(db, proposal, placement: Placement) -> None:
    proposal.placement = placement.to_dict()


# Para que el panel y el correo pinten lo mismo con las mismas palabras. Es una
# FRASE para quien decide, no una etiqueta: dice qué pasa y qué conviene hacer.
def headline(placement: dict | None) -> str:
    if not placement:
        return ""
    if placement.get("decision") == "cubierto":
        rec = (placement.get("candidates") or [None])[0]
        destino = rec["path"] if rec else "una página tuya"
        return (f"Ya tienes una página para esto: {destino}. Escribir más no ayuda; "
                "le falta subir en Google.")
    if placement.get("decision") == "ampliar":
        # `decide` pone siempre el recomendado el primero, también cuando es una
        # página de código (que no tiene target).
        rec = (placement.get("candidates") or [None])[0]
        destino = rec["path"] if rec else "una página existente"
        if rec and not rec.get("mergeable"):
            return (f"{destino} ya responde a esto, pero vive en el código: el motor no "
                    "puede ampliarla y hay que mejorarla a mano.")
        return f"Encaja en {destino}: mejor ampliarla que escribir otra página."
    return "Ninguna página tuya responde a esto: va como contenido nuevo."


def short_evidence(placement: dict | None) -> str:
    if not placement:
        return ""
    return re.sub(r"\s+", " ", " ".join((placement.get("reasons") or [])[:2]))[:400]


def selector_options(placement: dict | None) -> list[dict[str, Any]]:
    """Las opciones del selector de UN grupo (o del principal, si es el placement).

    Los candidatos ampliables, «contenido nuevo» y «omitir» (quitar esas keywords de
    la propuesta, que es lo que toca cuando la página ya lo cubre).
    """
    if not placement:
        return [{"value": "new", "label": "Escribirlas en un post nuevo", "recommended": True}]
    out = []
    for c in placement.get("candidates") or []:
        if not c.get("mergeable"):
            continue
        out.append({"value": c["target"], "label": f"Ampliar {c['path']}",
                    "path": c["path"],
                    "recommended": c["target"] == placement.get("recommended")})
    out.append({"value": "new", "label": "Escribirlas en un post nuevo",
                "recommended": placement.get("decision") == "nuevo"})
    out.append({"value": "skip", "label": "Quitar estas búsquedas de la idea",
                "recommended": placement.get("decision") == "cubierto"})
    return out


def grupos(placement: dict | None) -> list[dict]:
    """Los grupos del reparto; un placement anterior a los grupos es uno solo."""
    if not placement:
        return []
    return placement.get("groups") or [{**placement,
                                        "keywords": placement.get("keywords") or []}]


def analyze_pending(db, *, ids: list[int] | None = None, only_missing: bool = True,
                    dry_run: bool = False, client=None, use_serp: bool = True,
                    use_semantic: bool = True) -> list[tuple[Any, Placement]]:
    """Analiza las propuestas evergreen por validar. Con `dry_run` no guarda nada."""
    from app.db.models import ContentProposal

    q = db.query(ContentProposal).filter(
        ContentProposal.status == "proposed",
        ContentProposal.kind == "evergreen",
        ContentProposal.target_keyword.isnot(None),
    )
    if ids:
        q = q.filter(ContentProposal.id.in_(ids))
    if only_missing:
        q = q.filter(ContentProposal.placement.is_(None))
    pages, period = load_gsc_pages()
    out = []
    for prop in q.order_by(ContentProposal.id).all():
        try:
            pl = analyze(db, prop, pages=pages, period=period, client=client,
                         use_serp=use_serp, use_semantic=use_semantic)
        except Exception:  # noqa: BLE001
            logger.exception("[placement] falló el análisis de la propuesta #%s", prop.id)
            continue
        out.append((prop, pl))
        if not dry_run:
            store(db, prop, pl)
    if not dry_run:
        db.commit()
    return out
