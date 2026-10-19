"""Funde una propuesta del blog con una página que ya existe. NO persiste.

`augment_deep` amplía añadiendo UNA sección al final, y eso basta para cubrir un
hueco suelto. Fundir una idea entera es otra cosa: el criterio de David
(19-10-2026) es meter las secciones donde encajan, revisar la página entera para
que se lea de corrido y tocar headings si con eso queda mejor — **sin perder lo
que ya posiciona**.

Contrato:

  1. **Plan estructurado, no reescritura libre.** El modelo propone operaciones
     (`insert`, `rename`, `rewrite_intro`, `puente`, `media`); el texto se monta de
     forma determinista. Lo que ninguna operación toca queda idéntico, byte a
     byte, y se comprueba al final.
  2. **No-pérdida.** Cada sección original sigue entera. La intro, si se
     reescribe, no suelta ninguna cifra ni nombre propio. Los puentes solo
     AÑADEN una frase al final de una sección.
  3. **Rankings** (`ranking_guard`). Las consultas que la página ya gana (GSC:
     algún clic o posición ≤ 20) siguen cubiertas. Un heading solo cambia si el
     nuevo cubre lo que cubría el viejo. Lo que no pasa se descarta operación a
     operación.
  4. **Hechos.** Cada sección nueva sale de `_write_section` + `_verify_section`
     con el material delante; la formación de una banda sale de
     `band_memberships`, nunca del modelo. `lyric_guard` mide el delta y
     `editorial_review` juzga lo añadido (con la válvula de `ModoOptimizacion`:
     si lo rechaza, sale igual con el veredicto colgado y decide una persona).
  5. **SEO.** Title y description con `propose_meta` (mismas reglas de
     `seo_style`; no se toca el title si la keyword no cabe sin forzarlo),
     enlaces internos validados contra la BD, imagen solo con procedencia
     acreditada y alojada en casa, y vídeo verificado.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.services import ranking_guard, seo_style

logger = logging.getLogger(__name__)

MAX_INSERTS = 3
MAX_RENAMES = 2
MAX_PUENTES = 3
_H2 = re.compile(r"^##(?!#)\s*(.+?)\s*$", re.M)
_YT = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})")
_FORMACION = ("integrante", "miembro", "componente", "formacion", "formación", "musicos",
              "músicos", "banda")
INTRO = "__intro__"


# --------------------------------------------------------------------------- #
# Markdown por secciones
# --------------------------------------------------------------------------- #
@dataclass
class Bloque:
    heading: str | None   # None = la intro (lo que va antes del primer H2)
    texto: str            # incluye la línea del heading


def trocear(body: str) -> list[Bloque]:
    body = (body or "").strip("\n")
    cortes = [m.start() for m in _H2.finditer(body)]
    if not cortes:
        return [Bloque(None, body)] if body else []
    bloques = []
    if cortes[0] > 0 and body[:cortes[0]].strip():
        bloques.append(Bloque(None, body[:cortes[0]].strip("\n")))
    for i, ini in enumerate(cortes):
        fin = cortes[i + 1] if i + 1 < len(cortes) else len(body)
        trozo = body[ini:fin].strip("\n")
        bloques.append(Bloque(_H2.match(trozo).group(1).strip(), trozo))
    return bloques


def unir(bloques: list[Bloque]) -> str:
    return "\n\n".join(b.texto.strip("\n") for b in bloques if b.texto.strip()) + "\n"


def _norm_h(h: str | None) -> str:
    return seo_style.flatten(h or "").strip()


def _buscar(bloques: list[Bloque], heading: str) -> int | None:
    if heading == INTRO:
        return 0 if bloques and bloques[0].heading is None else -1
    objetivo = _norm_h(heading)
    for i, b in enumerate(bloques):
        if b.heading is not None and _norm_h(b.heading) == objetivo:
            return i
    return None


@dataclass
class Operaciones:
    inserts: list[dict] = field(default_factory=list)   # {after, heading, texto}
    renames: list[dict] = field(default_factory=list)   # {old, new}
    intro: str | None = None
    puentes: list[dict] = field(default_factory=list)   # {after, texto}


def aplicar(body: str, ops: Operaciones) -> str:
    """Monta el cuerpo nuevo. Determinista: lo que no se toca, no cambia.

    El orden importa: las inserciones se colocan con los headings ORIGINALES (que
    es como las propone el plan), después se renombra, y los puentes se buscan ya
    sobre el resultado (pueden ir tras una sección nueva o una renombrada).
    """
    bloques = trocear(body)
    for ins in ops.inserts:
        i = _buscar(bloques, ins["after"])
        # Varias secciones tras el mismo heading salen en el orden del plan.
        if i is not None and i >= 0:
            while (i + 1 < len(bloques)
                   and any(_norm_h(bloques[i + 1].heading) == _norm_h(x["heading"])
                           for x in ops.inserts)):
                i += 1
        nuevo = Bloque(ins["heading"], ins["texto"].strip())
        if i is None:
            bloques.append(nuevo)
        else:
            bloques.insert(i + 1 if i >= 0 else 0, nuevo)
    for r in ops.renames:
        i = _buscar(bloques, r["old"])
        if i is None or i < 0:
            continue
        resto = bloques[i].texto.partition("\n")[2]
        bloques[i] = Bloque(r["new"], f"## {r['new']}" + (f"\n{resto}" if resto else ""))
    for p in ops.puentes:
        i = _buscar(bloques, p["after"])
        if i is None or i < 0:
            continue
        bloques[i] = Bloque(bloques[i].heading,
                            bloques[i].texto.rstrip() + "\n\n" + p["texto"].strip())
    if ops.intro is not None:
        if bloques and bloques[0].heading is None:
            bloques[0] = Bloque(None, ops.intro.strip())
        else:
            bloques.insert(0, Bloque(None, ops.intro.strip()))
    return unir(bloques)


def secciones_conservadas(antes: str, despues: str, ops: Operaciones) -> list[str]:
    """Las secciones originales que NO aparecen enteras en el resultado.

    Se descuentan las que una operación declarada tocó a propósito: el heading de
    un rename (el cuerpo sí tiene que seguir) y la intro reescrita.
    """
    renombradas = {_norm_h(r["old"]): r["new"] for r in ops.renames}
    faltan = []
    for b in trocear(antes):
        if b.heading is None:
            if ops.intro is not None:
                continue
            if b.texto.strip() not in despues:
                faltan.append("(intro)")
            continue
        cuerpo = b.texto.partition("\n")[2].strip()
        nuevo_h = renombradas.get(_norm_h(b.heading), b.heading)
        if f"## {nuevo_h}" not in despues or (cuerpo and cuerpo not in despues):
            faltan.append(b.heading)
    return faltan


# --------------------------------------------------------------------------- #
# Destino
# --------------------------------------------------------------------------- #
@dataclass
class Destino:
    kind: str                 # ficha | post
    row: Any                  # SeoContent | Post
    path: str
    subject: str
    entity_type: str | None
    entity: Any
    body: str
    title: str | None
    description: str | None
    slug: str


def _sujeto(entity) -> str:
    return (getattr(entity, "stage_name", None) or getattr(entity, "name", None)
            or getattr(entity, "full_name", None) or getattr(entity, "title", None)
            or getattr(entity, "slug", ""))


def cargar_destino(db, opp) -> Destino | None:
    from app.db.models import Artist, Post, SeoContent
    from app.services.seo_opportunities import _entidad

    if opp.entity_type == "post":
        post = db.get(Post, opp.entity_id)
        if not post:
            return None
        from app.services.blog_anchor import resolve_central_entity

        anchor = resolve_central_entity(db, primary_keyword=post.target_keyword,
                                        title=post.title, angle=post.excerpt)
        return Destino("post", post, opp.path, anchor.name if anchor else post.title,
                       anchor.entity_type if anchor else None,
                       anchor.entity if anchor else None, post.body_md or "",
                       post.meta_title or post.title, post.meta_description or post.excerpt,
                       post.slug)

    sc = db.get(SeoContent, opp.seo_content_id) if opp.seo_content_id else None
    if not sc:
        return None
    if sc.entity_type == "page":
        # Las páginas índice hablan de la banda: su material es el de Extremoduro.
        ent = db.query(Artist).filter(Artist.slug == "extremoduro").first()
        return Destino("ficha", sc, opp.path, "Extremoduro", "artist" if ent else None, ent,
                       sc.body_md or "", sc.meta_title, sc.meta_description, sc.slug)
    ent = _entidad(db, sc.entity_type, sc.entity_id)
    if ent is None:
        return None
    return Destino("ficha", sc, opp.path, _sujeto(ent), sc.entity_type, ent,
                   sc.body_md or "", sc.meta_title, sc.meta_description, sc.slug)


# --------------------------------------------------------------------------- #
# Material
# --------------------------------------------------------------------------- #
def formacion(db, consultas: list[str]) -> str:
    """La formación de las bandas del universo, de la BD. Solo si se pregunta por ella.

    El 10-10-2026 un seguidor cazó «Uoho en Deltoya» en una slide: nada cotejaba
    una formación con `band_memberships`. Aquí la formación no se le pide al
    modelo: se le da.
    """
    pregunta = seo_style.flatten(" ".join(consultas))
    if not any(seo_style.flatten(t).strip() in pregunta for t in _FORMACION):
        return ""
    from sqlalchemy import select

    from app.db.models import Artist, BandMembership, Person

    filas = db.execute(
        select(BandMembership, Person, Artist)
        .join(Person, BandMembership.person_id == Person.id)
        .join(Artist, BandMembership.artist_id == Artist.id)
        .order_by(Artist.slug, BandMembership.position)
    ).all()
    if not filas:
        return ""
    lineas = ["FORMACIÓN DE LAS BANDAS (dato verificado: es la ÚNICA fuente válida sobre "
              "quién tocó qué y cuándo; no añadas a nadie que no esté aquí. Cuéntala como "
              "un hecho: no hables de «registros», listas ni de dónde sale el dato):"]
    for m, p, a in filas:
        nombre = p.stage_name or p.full_name
        extra = f" ({p.full_name})" if p.stage_name and p.full_name != p.stage_name else ""
        era = f", {m.era}" if m.era else ""
        fund = ", fundador" if m.is_founder else ""
        lineas.append(f"- {a.name}: {nombre}{extra} — {m.role}{era}{fund} "
                      f"[/personas/{p.slug}]")
    return "\n".join(lineas)


@dataclass
class Material:
    texto: str
    hard: str
    consulta: str
    pasajes: int


def reunir_material(db, destino: Destino, consultas: list[str]) -> Material:
    from app.services.corpus_for_queries import bloque_material, material_para_consultas

    hard, base = "", ""
    if destino.entity is not None and destino.entity_type:
        from app.services.deep_research import gather_entity_dossier

        try:
            d = gather_entity_dossier(db, destino.entity_type, destino.entity)
            hard, base = d.hard_facts, d.material
        except Exception as exc:  # noqa: BLE001
            logger.warning("[merge] dossier falló para %s: %s", destino.path, exc)
    pasajes = material_para_consultas(db, consultas)
    consulta = bloque_material(pasajes)
    form = formacion(db, consultas)
    if form:
        hard = f"{hard}\n\n{form}".strip()
    texto = "\n\n----\n\n".join(x for x in (consulta, base) if x)
    return Material(texto=texto, hard=hard, consulta=consulta, pasajes=len(pasajes))


# Frases que hablan del PROCESO y no del tema. Medido en la primera muestra real
# (19-10-2026, /personas): «Estos nombres y fechas responden a las búsquedas
# «integrantes de Extremoduro»…» y «no se añaden otros músicos sin periodos
# confirmados en el registro de miembros». Es eco de las instrucciones, y una
# página que le habla al lector de sus keywords no se publica.
_METATEXTO = re.compile(
    r"\bb[uú]squedas?\b|\bpalabras? clave\b|\bkeywords?\b|\bSEO\b"
    r"|\bregistro de (?:miembros|integrantes)\b|\bformaci[oó]n registrada\b"
    r"|\bperiodos? (?:confirmados|registrados)\b|\ben el registro\b",
    re.I,
)
_FRASE = re.compile(r"[^.!?\n]+[.!?]?")


def quitar_metatexto(texto: str) -> tuple[str, list[str]]:
    """Quita las frases que hablan del proceso. Devuelve (texto, frases quitadas)."""
    quitadas: list[str] = []
    lineas = []
    for linea in (texto or "").split("\n"):
        if linea.lstrip().startswith("#") or not _METATEXTO.search(linea):
            lineas.append(linea)
            continue
        frases = _FRASE.findall(linea)
        buenas = [f for f in frases if not _METATEXTO.search(f)]
        quitadas += [f.strip() for f in frases if _METATEXTO.search(f)]
        lineas.append("".join(buenas).strip())
    limpio = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return limpio, quitadas


# --------------------------------------------------------------------------- #
# Plan (LLM) — solo propone; las guardas deciden
# --------------------------------------------------------------------------- #
def _esquema(body: str) -> str:
    out = []
    for b in trocear(body):
        resumen = re.sub(r"\s+", " ", b.texto.partition("\n")[2] if b.heading else b.texto)
        out.append(f"- {'(INTRO)' if b.heading is None else '## ' + b.heading}: "
                   f"{resumen[:220]}")
    return "\n".join(out) or "(la página no tiene texto todavía)"


def planificar(client, destino: Destino, consultas: list[str], protegidas: list[dict],
               material: Material, propuesta: str) -> dict:
    from scripts.seo.generate_deep import _chat

    prot = "\n".join(f"- «{q['query']}» (pos {q.get('position')}, "
                     f"{q.get('clicks') or 0} clics)" for q in protegidas[:12]) or "- (ninguna)"
    prompt = (
        f"Vas a AMPLIAR una página publicada sobre «{destino.subject}» ({destino.path}) "
        f"integrando una idea que iba a ser un post aparte: «{propuesta}».\n\n"
        f"BÚSQUEDAS QUE LA PÁGINA DEBE PASAR A RESPONDER:\n- " + "\n- ".join(consultas)
        + "\n\nBÚSQUEDAS QUE YA GANA Y NO PUEDE PERDER (no quites ni cambies lo que las "
        f"cubre):\n{prot}\n\n"
        f"ESTRUCTURA ACTUAL (heading: arranque):\n{_esquema(destino.body)}\n\n"
        f"HECHOS DUROS:\n{material.hard[:3000]}\n\n"
        f"MATERIAL (única fuente de hechos):\n\"\"\"{material.texto[:9000]}\"\"\"\n\n"
        "Propón un PLAN de edición, no texto final:\n"
        f"- insert (máx {MAX_INSERTS}): secciones H2 NUEVAS, cada una colocada DONDE "
        "encaja en el orden de la página (after = heading EXACTO de la sección tras la "
        f"que va, o «{INTRO}» para ir justo tras la intro). Solo si el material sostiene "
        "hechos concretos; si no, no la propongas. Nada que la página ya diga.\n"
        f"- rename (máx {MAX_RENAMES}): solo si un heading existente gana claridad o "
        "cubre mejor una búsqueda SIN dejar de cubrir lo que ya cubre. Si dudas, no.\n"
        "- rewrite_intro: true solo si la intro ya no anuncia bien lo que la página "
        "pasa a contener. Se conservarán todos sus datos.\n"
        "- media: para una sección nueva, un vídeo (query de YouTube concreta) o la "
        "imagen de una persona/disco del universo (nombre exacto). Opcional.\n"
        'Devuelve JSON {"insert":[{"after":"...","heading":"...","covers":"..."}],'
        '"rename":[{"old":"...","new":"...","why":"..."}],"rewrite_intro":false,'
        '"intro_why":"","media":[{"section":"<heading nuevo>","type":"video|image",'
        '"query":"...","entity":"..."}]}. Si no hay nada sólido que añadir, '
        '{"insert":[]}.'
    )
    try:
        data = _chat(client, prompt, max_tokens=1200, temp=0.3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] plan falló para %s: %s", destino.path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def coser(client, destino: Destino, cuerpo: str, nuevas: list[str], material: Material,
          reescribir_intro: bool) -> dict:
    """La revisión de conjunto: intro y frases puente para que se lea de corrido."""
    from scripts.seo.generate_deep import _chat

    intro = next((b.texto for b in trocear(destino.body) if b.heading is None), "")
    pedir_intro = (
        "1. Reescribe la INTRO para que anuncie también lo nuevo. Conserva TODAS sus "
        "cifras, nombres propios y enlaces, y su tono. Misma longitud ±40 %.\n"
        f'INTRO ACTUAL:\n"""{intro}"""\n' if reescribir_intro and intro else
        "1. NO toques la intro (intro: null).\n"
    )
    prompt = (
        f"Página sobre «{destino.subject}» tras añadirle estas secciones: "
        + "; ".join(f"«{h}»" for h in nuevas) + ".\n\n"
        f'CUERPO COMPLETO:\n"""{cuerpo[:12000]}"""\n\n'
        f"{pedir_intro}"
        f"2. Hasta {MAX_PUENTES} frases PUENTE, solo donde el salto entre una sección y "
        "la siguiente quede brusco. Cada puente es UNA frase que se AÑADE al final de "
        "una sección existente; no repite datos ni inventa ninguno.\n"
        'Devuelve JSON {"intro": "..." | null, "puentes": [{"after": "<heading '
        'exacto>", "texto": "..."}]}.'
    )
    try:
        data = _chat(client, prompt, max_tokens=900, temp=0.3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] cosido falló para %s: %s", destino.path, exc)
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------- #
# Medios
# --------------------------------------------------------------------------- #
def imagen_para(db, nombre: str) -> dict | None:
    """Imagen de una entidad del universo, solo si su procedencia la acredita."""
    from app.services import image_guard
    from app.services.blog_anchor import _candidates, _norm

    objetivo = _norm(nombre)
    if not objetivo:
        return None
    for _etype, ent, cand in _candidates(db):
        if cand != objetivo:
            continue
        url = getattr(ent, "image_url", None)
        if not url or not image_guard.is_own_host(url):
            return None
        alias = [x for x in (getattr(ent, "stage_name", None),
                             getattr(ent, "full_name", None)) if x]
        v = image_guard.verify_provenance(
            entity_name=_sujeto(ent), image_url=url,
            attribution=getattr(ent, "image_attribution", None),
            license_=getattr(ent, "image_license", None), aliases=alias or None)
        if v.status not in ("accredited", "legacy_cc", "own_art"):
            logger.info("[merge] imagen de %s descartada: %s", nombre, v.status)
            return None
        return {"url": url, "alt": _sujeto(ent),
                "credito": getattr(ent, "image_attribution", None) or "",
                "status": v.status}
    return None


def video_para(query: str, subject: str, ya: set[str]) -> dict | None:
    """Un vídeo verificado con sus metadatos REALES (título, fecha, canal).

    Los metadatos viajan al aplicar a `related_videos`, que es de donde sale el
    `VideoObject` del cuerpo: sin título ni fecha de subida no hay schema válido.
    """
    from app.services.news_research import find_video

    try:
        v = find_video(query, subject)
    except Exception:  # noqa: BLE001
        return None
    if not v or v["youtube_id"] in ya:
        return None
    return {**v, "url": f"https://www.youtube.com/watch?v={v['youtube_id']}"}


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #
def merge_page(db, client, opp, *, propuesta: str = "", gsc_pages: dict | None = None
               ) -> dict:
    """Prepara la fusión. Devuelve {noop, motivo} o el borrador con sus notas."""
    from app.services.entity_resolver import autolink_corpus, build_corpus_index, load_link_stats
    from app.services.seo_opportunities import nombre_alias_index, propose_meta
    from app.services.text_sanitizer import strip_ai_tells
    from app.services.url_resolver import guard_internal_links
    from scripts.seo.augment_deep import confiesa_no_saber
    from scripts.seo.generate_deep import _verify_section, _write_section

    destino = cargar_destino(db, opp)
    if destino is None:
        return {"noop": True, "motivo": "la página de destino ya no existe"}
    consultas = [q.get("query", "") for q in (opp.queries or []) if q.get("query")]
    alias = nombre_alias_index(db)

    if gsc_pages is None:
        from app.services.content_placement import load_gsc_pages

        gsc_pages, _ = load_gsc_pages()
    protegidas = ranking_guard.consultas_protegidas(gsc_pages.get(destino.path) or [])

    material = reunir_material(db, destino, consultas)
    if not material.texto.strip() and not material.hard.strip():
        return {"noop": True, "motivo": "no hay material del corpus que respalde la ampliación"}

    plan = planificar(client, destino, consultas, protegidas, material,
                      propuesta or opp.gap_hint or "")
    notas: dict[str, Any] = {
        "descartado": [], "avisos": [], "protegidas": len(protegidas),
        "pasajes": material.pasajes,
        # La línea base que `merge_watch` compara a las 4 semanas de aplicar.
        "protegidas_detalle": [
            {k: q.get(k) for k in ("query", "position", "clicks", "impressions")}
            for q in protegidas[:30]
        ],
    }
    ops = Operaciones()
    heads = [b.heading for b in trocear(destino.body) if b.heading]
    nuevas: list[str] = []

    # --- Secciones nuevas: escritas, verificadas y sin confesiones ------------- #
    material_escritor = material.texto
    kw_block = ("Lo que el lector quiere saber (úsalo para ELEGIR qué contar; NUNCA "
                "menciones búsquedas, palabras clave, registros ni de dónde sale cada "
                "dato): " + "; ".join(consultas))
    for ins in (plan.get("insert") or [])[:MAX_INSERTS]:
        h = (ins.get("heading") or "").strip().strip("<>").strip()
        if not h or _norm_h(h) in {_norm_h(x) for x in heads + nuevas}:
            continue
        texto = _write_section(client, destino.subject, {"heading": h,
                                                         "covers": ins.get("covers") or h},
                               heads + nuevas, material.hard, material_escritor, kw_block,
                               prior=destino.body, tier="premium")
        texto = _verify_section(client, texto, material.hard + "\n\n" + material_escritor)
        texto, meta = quitar_metatexto(texto)
        if meta:
            notas["descartado"].append(f"«{h}»: frases de metatexto quitadas: "
                                       + " / ".join(m[:80] for m in meta[:3]))
        if not texto.strip() or not re.sub(r"^##.*$", "", texto, flags=re.M).strip():
            notas["descartado"].append(f"«{h}»: el verificador la dejó vacía")
            continue
        confesion = confiesa_no_saber(texto)
        if confesion:
            notas["descartado"].append(f"«{h}»: admite no saberlo («{confesion}»)")
            continue
        if not texto.lstrip().startswith("##"):
            texto = f"## {h}\n\n{texto.strip()}"
        h_real = _H2.match(texto.strip()).group(1).strip()
        after = (ins.get("after") or "").strip()
        if after != INTRO and _buscar(trocear(destino.body), after) is None:
            after = heads[-1] if heads else INTRO
        ops.inserts.append({"after": after, "heading": h_real, "texto": texto.strip()})
        nuevas.append(h_real)

    if not ops.inserts:
        return {"noop": True, "notas": notas,
                "motivo": "el corpus no respalda nada nuevo que añadir a esta página "
                          "(no se rellena con generalidades)"}

    # --- Medios ---------------------------------------------------------------- #
    ya_videos = set(_YT.findall(destino.body))
    imagenes, videos = [], []
    for m in (plan.get("media") or [])[:3]:
        sec = next((i for i in ops.inserts if _norm_h(i["heading"]) == _norm_h(m.get("section"))),
                   None)
        if sec is None:
            continue
        if m.get("type") == "image" and m.get("entity"):
            img = imagen_para(db, m["entity"])
            if img and img["url"] not in destino.body:
                credito = img["credito"].replace('"', "'")
                titulo = f' "{credito}"' if credito else ""
                cab, _, resto = sec["texto"].partition("\n")
                sec["texto"] = f"{cab}\n\n![{img['alt']}]({img['url']}{titulo})\n{resto}"
                imagenes.append({**img, "section": sec["heading"]})
        elif m.get("type") == "video" and m.get("query"):
            vid = video_para(m["query"], destino.subject, ya_videos)
            if vid:
                sec["texto"] = sec["texto"].rstrip() + f"\n\n{vid['url']}"
                ya_videos.add(vid["youtube_id"])
                videos.append({**vid, "section": sec["heading"]})

    # --- Enlazado: solo en lo nuevo, validado contra la BD --------------------- #
    try:
        indice, stats = build_corpus_index(db), load_link_stats()
        for sec in ops.inserts:
            sec["texto"] = autolink_corpus(sec["texto"], indice, max_links=2,
                                           exclude_slug=destino.slug, link_stats=stats)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] autolink falló: %s", exc)
    for sec in ops.inserts:
        g = guard_internal_links(db, sec["texto"])
        sec["texto"] = g.body_md
        if g.changed:
            notas["avisos"].append(f"enlaces corregidos en «{sec['heading']}»: {g.summary()}")

    # --- Renombres: solo los que no pierden cobertura -------------------------- #
    for r in (plan.get("rename") or [])[:MAX_RENAMES]:
        viejo, nuevo = (r.get("old") or "").strip(), (r.get("new") or "").strip()
        if not viejo or not nuevo or _buscar(trocear(destino.body), viejo) is None:
            continue
        v = ranking_guard.renombre_permitido(viejo, nuevo, protegidas, alias)
        if not v.ok:
            notas["descartado"].append(f"rename {v.motivo}")
            continue
        ops.renames.append({"old": viejo, "new": nuevo, "why": r.get("why") or ""})

    # --- Cosido: intro y puentes ----------------------------------------------- #
    borrador = aplicar(destino.body, ops)
    cos = coser(client, destino, borrador, nuevas, material, bool(plan.get("rewrite_intro")))
    intro_vieja = next((b.texto for b in trocear(destino.body) if b.heading is None), "")
    intro_nueva = (strip_ai_tells(cos["intro"]) or "").strip() \
        if isinstance(cos.get("intro"), str) else ""
    intro_nueva, _meta = quitar_metatexto(intro_nueva)
    if intro_nueva and intro_vieja and intro_nueva != intro_vieja.strip():
        perdidos = ranking_guard.datos_perdidos(intro_vieja, intro_nueva)
        inventados = seo_style.verify_no_invention(
            intro_nueva, seo_style.tokens_permitidos(destino.body, material.hard,
                                                     material.texto, *nuevas))
        if perdidos:
            notas["descartado"].append("intro: soltaba datos (" + ", ".join(perdidos[:4]) + ")")
        elif inventados:
            notas["descartado"].append("intro: traía datos sin respaldo ("
                                       + ", ".join(inventados[:4]) + ")")
        else:
            ops.intro = intro_nueva
    permitidos = seo_style.tokens_permitidos(destino.body, material.hard, material.texto)
    for p in (cos.get("puentes") or [])[:MAX_PUENTES]:
        texto = quitar_metatexto((strip_ai_tells(p.get("texto") or "") or "").strip())[0]
        if not texto or _buscar(trocear(borrador), p.get("after") or "") in (None, -1):
            continue
        fuera = seo_style.verify_no_invention(texto, permitidos)
        if fuera or len(texto) > 320:
            notas["descartado"].append(f"puente tras «{p.get('after')}» descartado")
            continue
        ops.puentes.append({"after": p["after"], "texto": texto})

    # El saneado (`strip_ai_tells`) se ha pasado SOLO por lo nuevo: pasarlo por el
    # cuerpo entero reescribiría guiones y comillas del texto publicado.
    after = aplicar(destino.body, ops)

    # --- No-pérdida: lo que no se tocó sigue entero ---------------------------- #
    faltan = secciones_conservadas(destino.body, after, ops)
    if faltan:
        return {"noop": True, "notas": notas,
                "motivo": "el montaje perdía secciones existentes: " + "; ".join(faltan[:3])}

    # --- Rankings: cobertura de la página entera ------------------------------- #
    v = ranking_guard.cobertura_conservada(
        ranking_guard.pagina(destino.body, destino.title, destino.description),
        ranking_guard.pagina(after, destino.title, destino.description), protegidas, alias)
    if not v.ok and ops.renames:
        ops.renames = []
        notas["descartado"].append(f"renombres retirados: {v.motivo}")
        after = aplicar(destino.body, ops)
        v = ranking_guard.cobertura_conservada(
            ranking_guard.pagina(destino.body, destino.title, destino.description),
            ranking_guard.pagina(after, destino.title, destino.description), protegidas, alias)
    if not v.ok and ops.intro is not None:
        ops.intro = None
        notas["descartado"].append(f"intro retirada: {v.motivo}")
        after = aplicar(destino.body, ops)
        v = ranking_guard.cobertura_conservada(
            ranking_guard.pagina(destino.body, destino.title, destino.description),
            ranking_guard.pagina(after, destino.title, destino.description), protegidas, alias)
    if not v.ok:
        return {"noop": True, "notas": notas, "motivo": v.motivo}

    # --- Versos y especulación sobre lo añadido -------------------------------- #
    try:
        from app.services.lyric_guard import check_lyrics

        antes_q = {x.quote for x in (check_lyrics(db, destino.body).blocking or [])}
        nuevos = [x for x in (check_lyrics(db, after).blocking or []) if x.quote not in antes_q]
        if nuevos:
            return {"noop": True, "notas": notas, "bloqueo_duro": True,
                    "motivo": "cita versos que no están en la letra: "
                              + "; ".join(x.quote[:60] for x in nuevos[:2])}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] lyric_guard falló: %s", exc)
    try:
        from app.services.content_guard import find_especulacion

        anadido = "\n\n".join(i["texto"] for i in ops.inserts)
        espec = set(find_especulacion(anadido)) - set(find_especulacion(destino.body))
        if espec:
            notas["avisos"].append("fórmulas especulativas en lo nuevo: "
                                   + "; ".join(sorted(espec)[:3]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] find_especulacion falló: %s", exc)

    # --- Editor jefe: juzga lo añadido, con válvula ---------------------------- #
    rigor = None
    try:
        from app.services.editorial_review import review as editorial_review

        allowed = {destino.subject.lower()} | {c.lower() for c in consultas}
        extra = {"material": material.texto or None, "focus": "; ".join(consultas),
                 "repeats_per_1000": 4.0}
        kind = destino.entity_type or "post"
        antes_v = editorial_review(destino.body or after, kind=kind, subject=destino.subject,
                                   allowed_terms=allowed, **extra)
        v2 = editorial_review(destino.body or after, kind=kind, subject=destino.subject,
                              allowed_terms=allowed,
                              spotlight="\n\n".join(i["texto"] for i in ops.inserts), **extra)
        rigor = {"verdict": v2.verdict, "score": v2.score, "before_score": antes_v.score,
                 "reasons": list(v2.reasons or [])}
        # NUNCA se toma `tightened_body_md`: el juez condensa el cuerpo VIEJO (lo
        # nuevo le llega aparte) y aceptarlo rompía la no-pérdida y podía tirar
        # justo lo que se acababa de añadir.
        if v2.verdict == "reject" or v2.score < antes_v.score - 5:
            rigor["forzada"] = True
            notas["avisos"].append(
                f"el editor jefe la RECHAZA (rigor {antes_v.score} → {v2.score}) y se te "
                "enseña igual para que decidas tú: " + "; ".join((v2.reasons or [])[:2]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] rigor falló: %s", exc)

    # --- Title y description --------------------------------------------------- #
    title, description = None, None
    meta_consultas = ([{"query": c} for c in consultas]
                      + [{"query": q["query"]} for q in protegidas[:4]])
    try:
        prop = propose_meta(client, subject=destino.subject, body_md=after,
                            meta_title=destino.title, meta_description=destino.description,
                            queries=meta_consultas,
                            entity_type=destino.entity_type or "post",
                            target_keyword=getattr(destino.row, "target_keyword", None))
        notas["avisos"] += prop.get("avisos") or []
        notas["meta_rechazos"] = prop.get("rechazos") or []
        t, d = prop.get("title"), prop.get("description")
        meta_antes = f"{destino.title or ''} {destino.description or ''}"
        meta_despues = f"{t or destino.title or ''} {d or destino.description or ''}"
        vm = ranking_guard.cobertura_conservada(meta_antes, meta_despues, protegidas, alias)
        if vm.ok:
            title, description = t, d
        else:
            notas["descartado"].append(f"title/description retirados: {vm.motivo}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[merge] propose_meta falló: %s", exc)

    return {
        "noop": False, "after": after, "title": title, "description": description,
        "rigor": rigor,
        "notas": {
            **notas,
            "added_headings": [i["heading"] for i in ops.inserts],
            "placement": [{"heading": i["heading"], "after": i["after"]} for i in ops.inserts],
            "renamed": ops.renames,
            "intro_rewritten": ops.intro is not None,
            "intro_before": intro_vieja if ops.intro is not None else None,
            "puentes": ops.puentes,
            "images_added": imagenes,
            "videos_added": videos,
            "rigor": rigor,
            "before_len": len(destino.body), "after_len": len(after),
            "outline": [b.heading for b in trocear(after) if b.heading],
        },
    }


# --------------------------------------------------------------------------- #
# Enlaces entrantes: los posts que competían apuntan a la página ampliada
# --------------------------------------------------------------------------- #
_ENLACE_MD = re.compile(r"\[[^\]]*\]\([^)]*\)")


def _primera_mencion(body: str, terminos: list[str]) -> tuple[int, int, str] | None:
    """(inicio, fin, término) de la primera mención fuera de enlaces y headings."""
    ocupado = [m.span() for m in _ENLACE_MD.finditer(body)]
    ocupado += [m.span() for m in re.finditer(r"^#.*$", body, re.M)]
    for t in sorted({t for t in terminos if t and len(t) >= 4}, key=len, reverse=True):
        for m in re.finditer(r"(?<![\w/])" + re.escape(t) + r"(?![\w])", body, re.I):
            if not any(a <= m.start() < b for a, b in ocupado):
                return m.start(), m.end(), body[m.start():m.end()]
    return None


def enlazar(body: str, path: str, terminos: list[str]) -> tuple[str, str] | None:
    """El cuerpo con UN enlace a `path` en la primera mención, o None.

    None si ya enlaza a esa página (criterio Moat: un enlace por destino) o si no
    la menciona: no se fuerza una frase para colar el enlace.
    """
    if re.search(r"\]\(" + re.escape(path) + r"(?:[#?/][^)]*)?\)", body or ""):
        return None
    hit = _primera_mencion(body or "", terminos)
    if not hit:
        return None
    ini, fin, txt = hit
    return body[:ini] + f"[{txt}]({path})" + body[fin:], txt


def enlaces_entrantes(db, path_destino: str, competing: list[str],
                      terminos: list[str]) -> list[dict]:
    """Qué posts que competían por la búsqueda enlazarían a la página ampliada."""
    from app.db.models import Post

    out = []
    for ruta in competing or []:
        partes = [p for p in ruta.strip("/").split("/") if p]
        if ruta == path_destino or len(partes) != 2 or partes[0] != "blog":
            continue
        post = (db.query(Post)
                .filter(Post.slug == partes[1], Post.status == "published").first())
        if not post:
            continue
        r = enlazar(post.body_md or "", path_destino, terminos)
        if r:
            out.append({"post_id": post.id, "path": ruta, "anchor": r[1]})
    return out
