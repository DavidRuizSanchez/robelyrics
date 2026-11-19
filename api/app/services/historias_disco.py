"""Las historias de un disco: qué hay que CONTAR antes de escribir.

Criterio de David (18-11-2026), tras leer tres borradores de discos: «parece una
concatenación de canciones y versos, sin ningún toque fan ni explicación ni anécdota.
Debe ser una mezcla entre exactitud técnica y comentarios sobre cosas curiosas del
disco». El motor de fichas planifica desde una lista de cosas que cubrir (fecha, sello,
canciones, sonido) y escribe sección a sección: sale una ficha, por mucho «escribe como
un fan» que se le pida.

Aquí se hace al revés: primero el inventario de historias, cada una con un ANCLA que no
es la letra (una declaración, la grabación, el vídeo, las listas, un directo, la
portada…), su tramo LITERAL de la fuente y quién lo dice. Luego se escribe una sección
por historia. Tres reglas que salen de lo medido el 18-11:

- **El tramo se comprueba por texto**: si no está literal en su fuente, la historia no
  existe (el redactor no puede apoyarse en una paráfrasis del inventario).
- **Quién habla**: en una entrevista transcrita, «después de doce años casi todos
  juntos» era la pregunta del locutor, no Robe (`habla_el_protagonista`).
- **Ni una historia por canción**: la crítica de Mondo Sonoro y las diez letras van
  canción a canción, y meterlas como candidatas reproducía el repaso. Una canción entra
  dentro de una historia, no como historia.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

ANCLAS = ("declaracion", "testimonio", "grabacion", "video", "listas", "directo",
          "portada_titulo", "contexto", "dato")
PROPIOS = ("robe_interview", "entorno_interview")
MAX_HISTORIAS = 7
_ETIQUETA_ROBE = re.compile(r"^\s*Robe\s*:\s*")


@dataclass
class Historia:
    gancho: str                 # qué se cuenta, en una línea
    ancla: str                  # una de ANCLAS: nunca «la letra»
    fuente: str                 # «P3 · título» o «hechos duros»
    tramo: str                  # LITERAL de la fuente
    quien: str                  # robe | entorno | tercero | hechos
    afirmable: bool             # propio, hecho duro o corroborado
    canciones: list[str] = field(default_factory=list)
    motivo: str = ""            # por qué no es afirmable, si no lo es
    contexto: str = ""          # el pasaje entero, para escribir y verificar

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("contexto", None)
        return d


def _plano(s: str) -> str:
    s = re.sub(r"[«»\"“”‘’']", "", s or "")
    return re.sub(r"\s+", " ", s).strip().lower()


def tramo_literal(tramo: str, fuente: str) -> bool:
    """¿El tramo está, palabra por palabra, en su fuente? (sin contar comillas ni
    espacios). Mínimo 25 caracteres: un tramo corto casa con cualquier cosa."""
    t = _plano(tramo)
    return len(t) >= 25 and t in _plano(fuente)


def consultas_del_disco(titulo: str, canciones: list[str]) -> list[str]:
    """Consultas que buscan HISTORIAS, no cobertura."""
    base = [
        f"Robe cuenta cómo nació el disco {titulo}",
        f"Robe habla del disco {titulo} en una entrevista",
        f"anécdotas de la grabación de {titulo}",
        f"rueda de prensa de presentación de {titulo}",
        f"portada y título del disco {titulo}",
        f"videoclip de {titulo}",
        f"gira y conciertos de {titulo}",
        f"los músicos de la banda de Robe en {titulo}",
    ]
    return base + [f"Robe explica la canción {c}" for c in canciones[:12]]


_SYS_EDITOR = (
    "Eres el editor de un blog de fans de Robe y Extremoduro. Te dan PASAJES del corpus "
    "(cada uno con su id, tipo y autor) y los DATOS DUROS de un disco. Eliges las "
    "HISTORIAS que merecen contarse en un post sobre ese disco: lo curioso, la anécdota, "
    "lo que contó Robe, cómo se grabó, el vídeo, cómo le fue en listas, los directos.\n"
    "REGLAS:\n"
    "- Cada historia tiene un ANCLA que NO es la letra de una canción: declaracion (Robe "
    "lo dice), testimonio (alguien de su entorno), grabacion, video, listas, directo, "
    "portada_titulo, contexto o dato.\n"
    "- NADA de una historia por canción. Una canción solo entra DENTRO de una historia "
    "que tenga otro ancla (en «canciones» la nombras).\n"
    "- «tramo»: copia LITERAL, sin cambiar una palabra, el trozo del pasaje (o de los "
    "datos duros) que sostiene la historia; entre 25 y 300 caracteres.\n"
    "- «quien»: robe, entorno, tercero (crítico, analista, fan, locutor) o hechos (datos "
    "duros). En una entrevista transcrita, una PREGUNTA es del entrevistador: quien = "
    "tercero.\n"
    "- Cada dato en UNA sola historia. Entre 3 y 7 historias; si no hay material para 3, "
    "devuelve las que haya.\n"
    'Devuelve JSON {"historias": [{"gancho": "...", "ancla": "...", "fuente": "P3", '
    '"tramo": "...", "quien": "...", "canciones": ["..."]}]}'
)


def _pasajes(db, consultas: list[str]) -> list[dict]:
    from app.services.corpus_for_queries import material_para_consultas

    return material_para_consultas(db, consultas, k=6, max_pasajes=30)


VENTANA_ROBE = 700


def pasajes_de_robe(db, titulo: str, *, max_por_fuente: int = 3, maximo: int = 12
                    ) -> list[dict]:
    """Lo que Robe (o su entorno) dijo nombrando el disco, buscado por TEXTO.

    La búsqueda por parecido no lo encontraba: el 18-11-2026, para «Se nos lleva el
    aire», no salió la entrevista de RockFM donde Robe cuenta que para la gira «hicimos
    dos canciones». Una entrevista larga habla de muchas cosas y su trozo no se parece
    a ninguna consulta; que nombre el disco, sí se puede buscar."""
    from sqlalchemy import text

    if not titulo or db is None:
        return []
    filas = db.execute(text(
        "select id, kind, author, title, url, content_clean from interpretation_sources "
        "where kind = any(:kinds) and content_clean ilike :t limit 40"),
        {"kinds": list(PROPIOS), "t": f"%{titulo}%"}).all()
    out = []
    for sid, kind, autor, tit, url, contenido in filas:
        low, n = (contenido or "").lower(), 0
        ultimo_fin = -1
        for m in re.finditer(re.escape(titulo.lower()), low):
            ini = max(0, m.start() - VENTANA_ROBE)
            if ini < ultimo_fin:
                continue  # solapa con la ventana anterior
            fin = m.end() + VENTANA_ROBE
            out.append({"fragmento": contenido[ini:fin], "kind": kind, "author": autor,
                        "title": tit, "url": url, "source_id": sid})
            ultimo_fin, n = fin, n + 1
            if n >= max_por_fuente:
                break
    return out[:maximo]


def corroborado_en_otra_fuente(db, tramo: str, *, autor: str | None) -> str | None:
    """Título de una fuente del corpus, de OTRO autor, que DICE lo mismo; o None.

    Primero localiza (los nombres y cifras del tramo, juntos) y después juzga si ese
    trozo lo afirma (`classify_with_evidence`). Medido el 18-11-2026: contando solo
    nombres juntos, «la formación lleva doce años junta» se dio por corroborado con una
    entrevista de Radio 3 que nombra a la banda y no dice nada de doce años."""
    from sqlalchemy import text

    from app.services.corpus_for_queries import claves_de, tramos_con
    from app.services.web_verify import classify_with_evidence

    claves = claves_de(tramo)
    if db is None or len(claves) < 2:
        return None
    cond = " and ".join(f"content_clean ~* :c{i}" for i in range(len(claves)))
    params = {f"c{i}": r"\m" + re.escape(c) + r"\M" for i, c in enumerate(claves)}
    params["autor"] = autor or ""
    filas = db.execute(text(
        "select title, content_clean from interpretation_sources where kind <> "
        f"'youtube_comment' and coalesce(author, title) <> :autor and {cond} limit 8"),
        params).all()
    for titulo, contenido in filas:
        trozos = tramos_con(contenido or "", tramo)
        if trozos and classify_with_evidence(tramo, trozos) == "supported":
            return titulo
    return None


def inventario(db, album, *, hechos_duros: str, usar_web: bool = True) -> list[Historia]:
    """Las historias afirmables (y las que no, con su motivo) de un disco."""
    from sqlalchemy import select

    from app.db.models import Song
    from app.services.news_research import _json

    canciones = [t for (t,) in db.execute(
        select(Song.title).where(Song.album_id == album.id)
        .order_by(Song.track_number.nulls_last())).all()]
    pasajes = pasajes_de_robe(db, album.title) + _pasajes(
        db, consultas_del_disco(album.title, canciones))
    bloques, por_id = [], {}
    for i, p in enumerate(pasajes, 1):
        pid = f"P{i}"
        por_id[pid] = p
        bloques.append(f"[{pid} · {p.get('kind')} · {p.get('author') or '?'} · "
                       f"{(p.get('title') or '')[:80]}]\n{(p.get('fragmento') or '')[:1500]}")
    data = _json(_SYS_EDITOR,
                 f"DISCO: «{album.title}»\n\nDATOS DUROS:\n{hechos_duros}\n\nPASAJES:\n\n"
                 + "\n\n----\n\n".join(bloques),
                 max_tokens=2500, temperature=0.2)
    out: list[Historia] = []
    for h in (data or {}).get("historias") or []:
        historia = _validar(db, h, por_id, hechos_duros, usar_web=usar_web)
        if historia:
            out.append(historia)
    return out[:MAX_HISTORIAS]


def _validar(db, h: dict, por_id: dict, hechos_duros: str, *, usar_web: bool
             ) -> Historia | None:
    ancla = (h.get("ancla") or "").strip()
    tramo = (h.get("tramo") or "").strip()
    fuente_id = (h.get("fuente") or "").split("·")[0].strip()
    if ancla not in ANCLAS or not tramo:
        return None
    if fuente_id.lower().startswith("hechos") or fuente_id.lower().startswith("datos"):
        if not tramo_literal(tramo, hechos_duros):
            return None
        return Historia(h.get("gancho", ""), ancla, "hechos duros", tramo, "hechos", True,
                        list(h.get("canciones") or []), contexto=hechos_duros)
    p = por_id.get(fuente_id)
    if not p or not tramo_literal(tramo, p.get("fragmento") or ""):
        logger.info("[historias] fuera: el tramo no está literal en %s", fuente_id)
        return None
    fuente = f"{fuente_id} · {(p.get('title') or '')[:70]}"
    quien = (h.get("quien") or "tercero").strip()
    kind = p.get("kind")
    historia = Historia(h.get("gancho", ""), ancla, fuente, tramo, quien, False,
                        list(h.get("canciones") or []),
                        contexto=_rotulo(p) + "\n" + (p.get("fragmento") or "")[:2500])
    if kind in PROPIOS:
        if kind == "robe_interview" and _ETIQUETA_ROBE.match(tramo):
            # Entrevista escrita: «Robe: …» es la etiqueta de quien responde. Medido el
            # 18-11-2026: el juez de quién habla lo leía como «nombra al sujeto».
            historia.tramo = _ETIQUETA_ROBE.sub("", tramo, count=1)
        elif kind == "robe_interview":
            from app.services.instagram.clip_picker import habla_el_protagonista
            es_robe, motivo = habla_el_protagonista(tramo)
            if not es_robe:
                historia.quien, historia.motivo = "tercero", motivo
                return historia
        historia.quien = "robe" if kind == "robe_interview" else "entorno"
        historia.afirmable = True
        return historia
    # Un tercero: solo se afirma si se corrobora por otra vía. Primero, dos fuentes del
    # corpus de autores distintos (criterio de David, 18-11-2026); después, la web.
    otra = corroborado_en_otra_fuente(db, tramo, autor=p.get("author") or p.get("title"))
    if otra:
        historia.afirmable = True
        historia.motivo = f"lo dice también: {otra[:70]}"
        return historia
    if usar_web:
        from app.services.web_verify import classify_fact
        res = classify_fact(tramo)
        if res.get("verdict") == "supported":
            historia.afirmable = True
            historia.motivo = "corroborado en la web"
        else:
            historia.motivo = ("sin comprobar: la búsqueda falló" if res.get("sin_red")
                               else "un tercero, sin corroborar")
    else:
        historia.motivo = "un tercero, sin corroborar"
    return historia


def _rotulo(p: dict) -> str:
    """Cómo se presenta el pasaje al redactor: de quién es y si se puede citar."""
    kind, titulo = p.get("kind"), (p.get("title") or "").strip()
    if kind == "robe_interview":
        from app.services.corpus_for_queries import es_entrevista_transcrita
        if es_entrevista_transcrita(kind, titulo):
            return (f"[ENTREVISTA A ROBE TRANSCRITA · {titulo}] (afirma lo que cuenta; "
                    "PROHIBIDO entrecomillar: la transcripción trae erratas)")
        return f"[LO QUE DIJO ROBE · {titulo}] (se puede citar entre comillas, con el medio)"
    if kind == "entorno_interview":
        return "[TESTIMONIO DEL ENTORNO] (se afirma; no se cita ni se nombra la fuente)"
    return "[DATO DE UN TERCERO, CORROBORADO] (se afirma en nuestra voz; nunca se nombra la fuente)"


# --------------------------------------------------------------------------- #
# El redactor: una entradilla y una sección por historia
# --------------------------------------------------------------------------- #
MIN_HISTORIAS = 3

_REGLAS_VOZ = (
    "VOZ: un fan que se lo sabe todo y lo cuenta bien: el dato exacto junto a lo curioso, "
    "y por qué importa. Nombra a Robe como «Robe». Comillas «». Nada de loas vacías "
    "(«icónico», «legado imborrable», «la esencia»). NUNCA hables del proceso («el "
    "material», «las fuentes», «no consta», «no se especifica»): lo que no sabes, no lo "
    "menciones. NO nombres medios, blogs, críticos ni analistas: solo Robe se cita, con "
    "su medio, y solo si su bloque dice que se puede citar. Sin vivencias inventadas "
    "(no digas que estuviste ni que lo escuchaste). No escribas «hoy» ni «este mes». "
    "Nada de enumerar el tracklist."
)


def _letras(db, titulos: list[str], album_id: int) -> str:
    from sqlalchemy import select

    from app.db.models import Song

    if not titulos:
        return ""
    bloques = []
    for t, letra in db.execute(select(Song.title, Song.lyrics_clean)
                               .where(Song.album_id == album_id)).all():
        if any(_plano(t) == _plano(x) for x in titulos) and (letra or "").strip():
            bloques.append(f"[LETRA · «{t}»] (verso citable LITERAL, nombrando la canción)\n"
                           + letra.strip()[:1400])
    return "\n\n".join(bloques)


def escribir(db, client, album, historias: list[Historia], *, hechos_duros: str,
             encargo: str = "") -> str | None:
    """El cuerpo del post, o None si no hay historias afirmables bastantes."""
    from app.services import source_guard
    from app.services.text_sanitizer import strip_ai_tells
    from scripts.seo.generate_deep import _chat, _verify_section

    buenas = [h for h in historias if h.afirmable]
    if len(buenas) < MIN_HISTORIAS:
        logger.info("[historias] «%s»: %d historia(s) afirmable(s), no da para un post",
                    album.title, len(buenas))
        return None
    indice = "\n".join(f"{i}. {h.gancho}" for i, h in enumerate(buenas, 1))
    entradilla = _chat(client, (
        f"Escribe la ENTRADILLA de un post sobre el disco «{album.title}» de Robe. "
        f"{encargo}\nDos o tres frases, sin encabezado: engancha con lo más curioso de "
        "lo que se va a contar y da la fecha de salida y el sello. No resumas el post.\n"
        f"{_REGLAS_VOZ}\nLo que se va a contar:\n{indice}\n\nDATOS DUROS:\n{hechos_duros}\n"
        'Devuelve JSON {"body_md": "..."}'), max_tokens=500, temp=0.6).get("body_md", "")
    partes = [_verify_section(client, entradilla, hechos_duros).strip()] if entradilla else []
    usados: list[str] = []
    for i, h in enumerate(buenas):
        letras = _letras(db, h.canciones, album.id)
        otras = "; ".join(x.gancho for x in buenas if x is not h)
        data = _chat(client, (
            f"Escribe UNA sección de un post sobre el disco «{album.title}» de Robe. Cuenta "
            f"esta historia: {h.gancho}\n"
            f"Se apoya en: «{h.tramo}» ({h.fuente}).\n"
            f"Las otras secciones cuentan (no las invadas): {otras}\n"
            + (f"DATOS YA DICHOS en secciones anteriores (NO los repitas): "
               f"{'; '.join(usados)}\n" if usados else "")
            + "INSTRUCCIONES:\n- Empieza con «## » y un encabezado natural, como lo escribiría "
            "una persona (sin dos puntos ni «Sujeto: tema»).\n"
            "- 120-260 palabras. Cuenta la historia con sus detalles concretos y explica por "
            "qué importa; mete los datos técnicos de los DATOS DUROS que encajen con ESTA "
            "historia (y solo esos).\n"
            "- Si la historia trae canciones, explica qué quieren decir; como mucho un verso "
            "LITERAL de su [LETRA], nunca uno inventado.\n"
            f"- {_REGLAS_VOZ}\n"
            f"PASAJE:\n\"\"\"{h.contexto}\"\"\"\n\n{letras}\n\nDATOS DUROS:\n{hechos_duros}\n"
            'Devuelve JSON {"body_md": "...", "datos": ["cada dato concreto que has usado"]}'),
            max_tokens=1500, temp=0.6)
        sec = (data.get("body_md") or "").strip()
        if not sec:
            continue
        sec = _verify_section(client, sec, f"{hechos_duros}\n\n{h.contexto}\n\n{letras}")
        if sec.strip():
            partes.append(sec.strip())
            usados += [str(d) for d in (data.get("datos") or [])][:8]
    cuerpo = "\n\n".join(p for p in partes if p)
    cuerpo = strip_ai_tells(cuerpo) or cuerpo
    cuerpo, _ = source_guard.limpiar(cuerpo, source_guard.nombres_de_fuentes(db))
    cuerpo, _ = source_guard.quitar_confesiones(cuerpo)
    return cuerpo if len(cuerpo) >= 300 else None
