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
    citable: bool = False       # se puede entrecomillar (entrevista ESCRITA de Robe)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("contexto", None)
        return d


_HOSTS_HABLADOS = re.compile(r"youtube\.com|youtu\.be|ivoox|spotify|podcast|cadenaser|rtve",
                             re.I)


def es_transcrita(p: dict) -> bool:
    """¿El pasaje es una entrevista HABLADA (vídeo, radio) transcrita a máquina?
    Criterio de David (18-11-2026): se afirma lo que cuenta, pero no se entrecomilla.
    En el corpus casi todas las entrevistas de Robe son vídeos de YouTube, con kind
    `robe_interview`: mirar solo el kind `youtube_transcript` las dejaba citables."""
    from app.services.corpus_for_queries import es_entrevista_transcrita

    return (es_entrevista_transcrita(p.get("kind"), p.get("title"))
            or bool(_HOSTS_HABLADOS.search(p.get("url") or "")))


def _plano(s: str) -> str:
    s = re.sub(r"[«»\"“”‘’']", "", s or "")
    s = re.sub(r"(?:\.\s*){2,}|…", ". ", s)   # «tristes...» y «tristes.» son lo mismo
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
    "- Los DATOS DUROS también dan historias (fuente «hechos duros»): cómo se grabó y "
    "quién lo produjo, el sencillo que lo adelantó, la canción más larga, cómo le fue en "
    "listas. La fecha de salida y el sello NO son una historia: van en la entradilla.\n"
    "- El «gancho» cuenta lo CURIOSO, no el dato seco.\n"
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
    # «Destrozares, canciones para el final de los tiempos» casi nunca se dice entero.
    corto = titulo.split(",")[0].strip()
    titulo = corto if len(corto) >= 6 else titulo
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

    from app.services.corpus_for_queries import claves_de, sql_contiene, tramos_con
    from app.services.web_verify import classify_with_evidence

    claves = claves_de(tramo)
    if db is None or len(claves) < 2:
        return None
    cond = " and ".join(sql_contiene(i) for i in range(len(claves)))
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
    # Lo que Robe dijo de una canción del disco también es del disco («El poder del
    # arte», «podría haber hecho una cosa más»); solo títulos largos, que no casan solos.
    de_canciones = [x for c in canciones if len(c) >= 10
                    for x in pasajes_de_robe(db, c, max_por_fuente=1, maximo=2)][:8]
    pasajes = pasajes_de_robe(db, album.title) + de_canciones + _pasajes(
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
    out = out[:MAX_HISTORIAS]
    grabacion = historia_de_grabacion(hechos_duros)
    if grabacion and not any(h.ancla == "grabacion" and h.afirmable for h in out):
        # Es lo primero que pide el juez a un aniversario, y el editor a veces no la
        # elegía teniendo los datos (#425, 19-11-2026: rechazada por eso con 38).
        out.append(grabacion)
    return out


_CIFRA = re.compile(r"\bn[uú]mero (?:uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
                    r"\d+)\b|\bn\.º ?\d+|\b\d{2,}\b", re.I)


def cifras_repetidas(texto: str, resto: str, album) -> list[str]:
    """Cifras de la entradilla que ya da alguna sección (sin contar el día y el año de
    salida, que la entradilla tiene que dar)."""
    salida = getattr(album, "release_date", None)
    propias = {str(salida.day), str(salida.year)} if salida else set()
    propias |= set(getattr(album, "fechas_propias", ()) or ())
    rep = _cifras(texto) & _cifras(resto)
    return [f"repite «{x}», que ya va en una sección" for x in sorted(rep - propias)]


def _fechas_de(d) -> tuple[str, ...]:
    return (str(d.day), str(d.year)) if d else ()


_NUM_PALABRA_CIFRA = {"uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
                      "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10"}


def _cifras(texto: str) -> set[str]:
    """Las cifras de un texto, con «número uno», «n.º 1» y «número 1» como la misma."""
    out = set()
    for m in _CIFRA.finditer(texto or ""):
        x = m.group(0).lower()
        n = re.match(r"(?:n[uú]mero|n\.º) ?(\w+)", x)
        out.add("n.º " + _NUM_PALABRA_CIFRA.get(n.group(1), n.group(1)) if n else x)
    return out


def cifras_ajenas(texto: str, contexto: str, pieza) -> list[str]:
    """Cifras de una sección que no son de SU historia (ni fechas propias de la pieza).
    En la efeméride, «murió el 10 de diciembre de 2025, a los 63 años» acababa en tres
    secciones (19-11-2026): cada una solo cuenta lo suyo."""
    suyas = _cifras(contexto)
    # Solo el día y el año de salida de un disco: las demás fechas propias de la pieza
    # (la muerte en la efeméride) son de la entradilla, no de cada sección.
    propias = set(_fechas_de(getattr(pieza, "release_date", None)))
    ajenas = _cifras(texto) - suyas - propias
    return [f"«{x}» no es de esta historia: quítalo" for x in sorted(ajenas)]


def gancho_fiel(h: Historia) -> Historia:
    """El gancho es una paráfrasis del editor y la sección se comprueba contra el tramo:
    si el gancho dice más que el tramo, el redactor acaba matizando («pero no explicó
    que…», asesor 19-11-2026). Si el tramo no lo sostiene, el gancho pasa a ser el tramo."""
    if not h.afirmable:
        return h
    try:
        from app.services.web_verify import classify_with_evidence
        ok = classify_with_evidence(h.gancho, [h.tramo]) == "supported"
    except Exception:  # noqa: BLE001 — sin juez, el gancho prudente
        ok = False
    if not ok:
        h.gancho = f"Cuenta lo que dice este tramo, sin añadir nada: «{h.tramo[:220]}»"
    return h


_PRIORIDAD_ANCLA = {"declaracion": 0, "grabacion": 1, "testimonio": 2, "portada_titulo": 3,
                    "video": 4, "directo": 5, "listas": 6, "contexto": 7, "dato": 8}
RONDAS = 3
VERSION_INVENTARIO = 1


def _dir_inventario():
    import os
    import tempfile
    from pathlib import Path
    return Path(os.environ.get("HISTORIAS_DIR") or Path(tempfile.gettempdir()) / "historias")


def inventario_congelado(db, album, *, hechos_duros: str, rondas: int = RONDAS,
                         refrescar: bool = False) -> list[Historia]:
    """El inventario del disco, UNO y estable: la unión de varias pasadas del editor,
    validada y guardada. Sortear inventario y redacción a la vez impedía ver si el
    redactor mejoraba (asesor, 19-11-2026). Se rehace con `refrescar` o si cambian los
    datos duros."""
    import hashlib
    import json

    ruta = _dir_inventario() / f"{getattr(album, 'slug', album.id)}.json"
    firma = hashlib.sha1((hechos_duros or "").encode()).hexdigest()[:12]
    if ruta.exists() and not refrescar:
        try:
            guardado = json.loads(ruta.read_text())
            if guardado.get("version") == VERSION_INVENTARIO and guardado.get("firma") == firma:
                return [Historia(**d) for d in guardado["historias"]]
        except Exception:  # noqa: BLE001 — caché rota: se rehace
            pass
    union: list[Historia] = []
    for _ in range(max(1, rondas)):
        for h in inventario(db, album, hechos_duros=hechos_duros):
            t = _plano(h.tramo)
            if any(t in _plano(x.tramo) or _plano(x.tramo) in t for x in union):
                continue
            # Dos citas de la MISMA fuente con el mismo ancla son la misma historia: la
            # gira en dos partes de «Bienvenidos al temporal» salía en dos secciones.
            if h.quien != "hechos" and any(x.fuente == h.fuente and x.ancla == h.ancla
                                           for x in union):
                continue
            # Un dato duro sin cifra ni nombre propio no es una historia («los temas ya
            # existían; el disco aporta versiones distintas»): repetirlo era relleno.
            if h.quien == "hechos" and not re.search(r"\d|\s[A-ZÁÉÍÓÚÑ«]", h.tramo[1:]):
                continue
            union.append(h)
    buenas = sorted((gancho_fiel(h) for h in union if h.afirmable),
                    key=lambda h: _PRIORIDAD_ANCLA.get(h.ancla, 9))
    # Una historia por ancla de dato duro (listas, grabación): repetirlas es repetir datos.
    vistas, elegidas = set(), []
    for h in buenas:
        clave = h.ancla if h.quien == "hechos" else id(h)
        if clave in vistas:
            continue
        vistas.add(clave)
        elegidas.append(h)
    elegidas = elegidas[:MAX_HISTORIAS]
    fuera = [h for h in union if not h.afirmable]
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"version": VERSION_INVENTARIO, "firma": firma,
                                    "historias": [asdict(h) for h in elegidas + fuera]},
                                   ensure_ascii=False, indent=1))
    except OSError as exc:
        logger.warning("[historias] no se pudo guardar el inventario: %s", exc)
    return elegidas + fuera


def historia_de_grabacion(hechos_duros: str) -> Historia | None:
    """La historia de cómo y dónde se grabó, si los datos duros la traen."""
    lineas = [x.strip() for x in (hechos_duros or "").splitlines()
              if re.match(r"\s*Grabaci[oó]n", x)]
    if not lineas:
        return None
    tramo = max(lineas, key=len)
    return Historia("Cómo y dónde se grabó el disco, y con quién", "grabacion",
                    "hechos duros", tramo[:300], "hechos", True, contexto=hechos_duros)


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
        historia.citable = kind == "robe_interview" and not es_transcrita(p)
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


def medio_de(p: dict) -> str:
    """El medio de una entrevista escrita, del título del corpus: «Entrevista a Robe
    (Diario de Noticias de Navarra, 2016)» → «Diario de Noticias de Navarra»."""
    m = re.search(r"\(([^()]+?)(?:,\s*\d{4})?\)\s*$", (p.get("title") or "").strip())
    return m.group(1).strip() if m else ""


def _rotulo(p: dict) -> str:
    """Cómo se presenta el pasaje al redactor. SIN el título de la fuente: con él delante
    escribía «en la entrevista transcrita», el nombre del programa o el de quien
    entrevistaba (asesor, 19-11-2026). Solo una entrevista escrita lleva su medio."""
    kind = p.get("kind")
    if kind == "robe_interview":
        if es_transcrita(p):
            return ("[LO QUE CONTÓ ROBE] (cuéntalo en tu voz y SIN comillas; no nombres el "
                    "programa, el medio ni a quien pregunta)")
        medio = medio_de(p)
        return ("[LO QUE DIJO ROBE] (se puede citar entre comillas"
                + (f"; si lo atribuyes, el medio es {medio}" if medio else "") + ")")
    if kind == "entorno_interview":
        return "[TESTIMONIO DEL ENTORNO] (se afirma en nuestra voz; no se cita ni se nombra)"
    return "[DATO CORROBORADO] (se afirma en nuestra voz; nunca se nombra de dónde sale)"


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

    if not titulos or album_id is None:
        return ""
    bloques = []
    for t, letra in db.execute(select(Song.title, Song.lyrics_clean)
                               .where(Song.album_id == album_id)).all():
        if any(_plano(t) == _plano(x) for x in titulos) and (letra or "").strip():
            bloques.append(f"[LETRA · «{t}»] (verso citable LITERAL, nombrando la canción)\n"
                           + letra.strip()[:1400])
    return "\n\n".join(bloques)


def trayectoria(db, album) -> str:
    """El disco de estudio de antes y el de después en la obra de Robe (sus dos etapas)
    y su muerte: lo que el cierre puede afirmar. Sale de la BD, nunca de memoria."""
    from app.services import robe_facts

    estudio = [x for x in robe_facts.discography(db) if x.kind == "studio" and x.year]
    titulos = [_plano(x.title) for x in estudio]
    if _plano(album.title) not in titulos:
        return robe_facts.DEATH_SENTENCE + "."
    i = titulos.index(_plano(album.title))
    etapa = lambda x: "Robe" if x.artist_slug == "robe" else "Extremoduro"  # noqa: E731
    este, lineas = f"«{album.title}»", []
    if i > 0:
        a = estudio[i - 1]
        lineas.append(f"El disco de estudio de Robe ANTERIOR a {este} fue «{a.title}» "
                      f"({a.year}, {etapa(a)}).")
    if i + 1 < len(estudio):
        d = estudio[i + 1]
        lineas.append(f"El disco de estudio de Robe SIGUIENTE a {este} fue «{d.title}» "
                      f"({d.year}, {etapa(d)}).")
    else:
        lineas.append(f"{este} es el ÚLTIMO disco de estudio de Robe.")
    lineas.append(robe_facts.DEATH_SENTENCE + ".")
    return "\n".join(lineas)


_CITA = re.compile(r"«([^«»]{20,})»")
_TITULO = re.compile(r"«([^«»]+)»")
_QUIEN_LO_DICE = re.compile(
    r"\b(?:Robe|dij[oe]|dec[ií]a|cont[oó]|contaba|explic[oó]|explicaba|añadi[oó]|respondi[oó]"
    r"|record[oó]|asegur[oó]|reconoci[oó]|resumi[oó]|canta|cantaba|verso|estribillo)\b", re.I)


def cierre_falso(texto: str, titulo: str, es_ultimo: bool) -> bool:
    """¿El cierre llama «último» a otro disco, o a este sin serlo? El 19-11-2026
    escribió «"Mayéutica" (2021) fue el último disco de estudio de Robe» a partir de
    «el anterior fue Mayéutica» + «este es el último»."""
    sin_enlaces = re.sub(r"\]\([^)]*\)", "]", texto or "")
    # Por cláusulas: «Llegó después de «Mayéutica» y es el último…» es correcto.
    for frase in re.split(r"(?<=[.!?])\s+|\n+|[,;:]\s*|\s+[ye]\s+", sin_enlaces):
        if not re.search(r"\b[uú]ltim[oa]\b", frase, re.I):
            continue
        otros = [t for t in _TITULO.findall(frase)
                 if _plano(t.strip("[]")) != _plano(titulo)]
        if otros or not es_ultimo:
            return True
    return False


def _es_nombre_propio(c: str) -> bool:
    """«Primeras Flores Amarillas»: todas las palabras con chicha en mayúscula y sin
    puntuación de frase. Una cita es una frase; un nombre, no."""
    palabras = [w for w in re.findall(r"[\wáéíóúñü]+", c, re.I) if len(w) > 3]
    return (bool(palabras) and len(c) <= 60 and not re.search(r"[.,;:?!]", c)
            and all(w[0].isupper() for w in palabras))


def citas_que_fallan(texto: str, fuente: str, titulos: list[str], *,
                     no_citable: str = "") -> list[str]:
    """Lo que la sección pone entre comillas sin estar LITERAL en su fuente, y los
    párrafos con las comillas descuadradas. Medido el 19-11-2026: el verificador recortó
    el arranque de una cita de Robe y su final («…que yo tenía guardadas de antes.»)
    quedó como si lo dijera el narrador."""
    fallos = []
    # El subtítulo también es título: «canciones para el final de los tiempos».
    tit = {_plano(t) for t in titulos} | {_plano(x) for t in titulos for x in t.split(",")}
    for m in _CITA.finditer(texto or ""):
        c = m.group(1)
        if _plano(c) in tit:
            continue
        inicio = (texto or "").rfind("\n", 0, m.start()) + 1
        if _es_nombre_propio(c):
            continue   # «Primeras Flores Amarillas» es el nombre de un festival, no una cita
        if not _QUIEN_LO_DICE.search(texto[inicio:m.start()]):
            fallos.append(f"«{c[:60]}» va sin decir antes quién lo dice")
            continue
        if no_citable and _plano(c) in _plano(no_citable):
            fallos.append(f"«{c[:60]}» no se puede entrecomillar (entrevista hablada "
                          "transcrita o palabras de un tercero): cuenta lo que dijo SIN "
                          "comillas")
        elif _plano(c) not in _plano(fuente):
            fallos.append(f"la cita «{c[:80]}» no está literal en el pasaje")
    for parrafo in (texto or "").split("\n"):
        if parrafo.count("«") != parrafo.count("»"):
            fallos.append(f"comillas descuadradas en: {parrafo[:90]}")
    return fallos


_SYS_FIEL = (
    "Comparas una SECCIÓN de un post con el PASAJE en el que se apoya. Señala SOLO lo que "
    "la sección atribuye a alguien (lo que dijo, pensaba o hizo) o da como hecho y que el "
    "pasaje NO dice, o dice al revés. Una explicación o una opinión del autor del post no "
    "es un fallo; cambiar el sentido de lo que alguien dijo, sí. "
    'Devuelve JSON {"fallos": ["…"]} (lista vacía si es fiel).'
)


def fallos_de_fidelidad(texto: str, fuente: str) -> list[str]:
    from app.services.news_research import _json

    try:
        data = _json(_SYS_FIEL, f'PASAJE:\n"""{fuente[:6000]}"""\n\nSECCIÓN:\n"""{texto}"""',
                     max_tokens=400, temperature=0)
    except Exception as exc:  # noqa: BLE001 — sin revisor no se da por buena
        return [f"no se pudo comprobar la fidelidad: {exc}"]
    if not isinstance(data, dict) or "fallos" not in data:
        return ["no se pudo comprobar la fidelidad"]
    return [str(x) for x in data.get("fallos") or []]


_PROCESO = re.compile(
    r"\bd?el material\b|\bseg[uú]n (?:el|la|los|las) (?:art[ií]culo|informaci[oó]n|noticia|"
    r"datos|fuentes?)\b|\b(?:la informaci[oó]n|el art[ií]culo|la noticia) (?:fecha|señala|"
    r"indica|dice|recoge|apunta|sit[uú]a|cuenta|a[ñn]ade|menciona)\b"
    r"|\bla (?:conversaci[oó]n|entrevista|fuente) no (?:identifica|permite|"
    r"recoge|dice|precisa|aclara)|\bno permite (?:asegurar|afirmar|saber)|\bqueda limitad[ao] a "
    r"lo que|\bentrevista transcrita\b|\bla (?:entrevista|transcripci[oó]n) (?:recoge|permite|"
    r"menciona|cita|incluye)\b"
    # Lo que alguien NO dijo: eco de la revisión de fidelidad («pero no explicó que el
    # aire se lleve las cosas», 19-11-2026). Lo que no sabes, no lo menciones.
    r"|\bno (?:explic[oó]|afirm[oó]|precis[oó]|aclar[oó]|dijo|detall[oó]|concret[oó]|"
    r"especific[oó]) (?:que|qu[eé]|cu[aá]l|cu[aá]les|por qu[eé]|c[oó]mo)"
    r"|\bno (?:viene|va|aparece) acompañad[oa]|\bno present[oó] (?:el|la|los|las) ",
    re.I)


def fallos_de_letra(db, texto: str) -> list[str]:
    """La guarda de versos sobre la sección: una cita de Robe que parece un verso
    (porque la canción va al lado y quién habla va detrás) se reescribe AQUÍ, antes de
    que la pare el gate entero (19-11-2026, dos de cuatro borradores)."""
    if db is None:
        return []
    from app.services.lyric_guard import check_lyrics

    rep = check_lyrics(db, texto)
    return [f"«{v.quote[:60]}» se lee como verso de «{v.attributed_song}» y no lo es: si es "
            "una declaración, di ANTES quién la dice y dónde; si es un verso, cópialo literal"
            for v in rep.blocking + rep.to_review]


def limpiar_seccion(db, texto: str) -> tuple[str, list[str]]:
    """Las mismas limpiezas que el cuerpo sufre DESPUÉS (post-proceso del borrador), aquí,
    antes de comprobar: así lo que se comprueba es lo que se publica. Devuelve el texto y
    las frases que habrían quitado (con ellas, la sección se reescribe entera; quitarlas a
    secas dejaba frases cojas como «También vinculó esa imagen…»)."""
    from app.services import source_guard
    from app.services.text_sanitizer import strip_ai_tells

    t = strip_ai_tells(texto) or texto
    quitadas: list[str] = []
    t, q = source_guard.limpiar(t, source_guard.nombres_de_fuentes(db) if db is not None
                                else None)
    quitadas += q
    t, q = source_guard.quitar_confesiones(t)
    quitadas += q
    if db is not None:
        from app.services.fact_check import corregir_anios_de_disco
        t, _ = corregir_anios_de_disco(db, t)
    return t.strip(), quitadas


def _seccion(client, prompt: str, fuente: str, titulos: list[str], *, max_tokens: int,
             intentos: int = 2, db=None, no_citable: str = "",
             extra_check=None) -> tuple[str, list[str]]:
    """Escribe, verifica, limpia y revisa (citas literales, proceso, versos y fidelidad);
    con los fallos delante se reescribe una vez, pidiendo QUITAR lo que falla. Si no queda
    limpia, no entra: mejor una sección menos."""
    from scripts.seo.generate_deep import _chat, _verify_section

    fallos: list[str] = []
    for _ in range(intentos):
        extra = ("\nLA VERSIÓN ANTERIOR TENÍA ESTOS FALLOS. Escríbela de nuevo QUITANDO esas "
                 "afirmaciones o frases (no las corrijas, no las matices y no digas lo que no "
                 "se dijo):\n- " + "\n- ".join(fallos)) if fallos else ""
        try:
            data = _chat(client, prompt + extra, max_tokens=max_tokens, temp=0.6)
        except Exception as exc:  # noqa: BLE001 — un 500 de OpenAI es un intento fallido
            logger.warning("[historias] el modelo falló (%s): se reintenta", exc)
            fallos = ["fallo técnico del modelo"]
            continue
        sec = (data.get("body_md") or "").strip()
        if not sec:
            fallos = ["vacía"]
            continue
        try:
            sec = _verify_section(client, sec, fuente).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[historias] el verificador falló (%s): se reintenta", exc)
            fallos = ["fallo técnico del verificador"]
            continue
        if not sec:
            fallos = ["el verificador no dejó nada"]
            continue
        sec, quitadas = limpiar_seccion(db, sec)
        fallos = ([f"nombra una fuente o habla del proceso: «{q}»" for q in quitadas]
                  + citas_que_fallan(sec, fuente, titulos, no_citable=no_citable)
                  + [f"habla del proceso: «{m.group(0)}»" for m in _PROCESO.finditer(sec)]
                  + fallos_de_letra(db, sec)
                  + (extra_check(sec) if extra_check else []))
        fallos = fallos or [f"no lo dice el pasaje: {x}"
                            for x in fallos_de_fidelidad(sec, fuente)]
        if not fallos:
            return sec, [str(d) for d in (data.get("datos") or [])][:8]
    logger.info("[historias] sección fuera: %s", " || ".join(fallos)[:1500])
    return "", []


@dataclass
class Pieza:
    """Lo que cambia entre un post de disco y otro post por historias (la efeméride del
    primer aniversario, 19-11-2026). El resto del redactor —secciones, comprobaciones,
    limpieza— es el mismo."""
    objeto: str                 # «el disco «X» de Robe»
    titulo: str                 # para la lista de títulos y el cierre
    entradilla_pide: str        # qué da la entradilla además del gancho
    aviso_seccion: str          # lo que las secciones no repiten
    cierre_pide: str
    cierre_datos: str           # lo único que el cierre puede afirmar
    album_id: int | None = None
    release_date: object = None
    es_ultimo: bool | None = None   # None: no se comprueba «último disco»
    fechas_propias: tuple[str, ...] = ()   # cifras que la entradilla SÍ da (día y año…)
    otros_titulos: tuple[str, ...] = ()    # títulos que no son del catálogo («El mapa de Robe»)
    palabras_dato: str = "40-120"          # largo de una sección de dato duro
    entradilla_fija: str = ""              # primera frase ya verificada (la efeméride)
    min_historias: int = 3                 # sin estas, no hay post


def pieza_de_disco(db, album) -> Pieza:
    tray = trayectoria(db, album)
    return Pieza(
        objeto=f"el disco «{album.title}» de Robe", titulo=album.title,
        entradilla_pide=("da la fecha de salida, el sello y quién lo produjo (si está en los "
                         "DATOS DUROS)"),
        aviso_seccion="La fecha de salida, el sello y la producción van en la entradilla: NO "
                      "los repitas aquí.",
        cierre_pide=("dos a cuatro frases que lo sitúen en su obra (el disco de antes y el de "
                     "después) y, si encaja, que Robe murió: solo el dato, sin comentarlo"),
        cierre_datos=tray, album_id=album.id,
        release_date=getattr(album, "release_date", None), es_ultimo="ÚLTIMO" in tray,
        fechas_propias=_fechas_de(getattr(album, "release_date", None)))


def escribir(db, client, album, historias: list[Historia], *, hechos_duros: str,
             encargo: str = "") -> str | None:
    """El cuerpo del post de un disco, o None si no hay historias afirmables bastantes."""
    return escribir_pieza(db, client, pieza_de_disco(db, album), historias,
                          hechos_duros=hechos_duros, encargo=encargo)


def escribir_pieza(db, client, pieza: Pieza, historias: list[Historia], *,
                   hechos_duros: str, encargo: str = "") -> str | None:
    """El cuerpo del post, o None si no hay historias afirmables bastantes."""
    from sqlalchemy import select

    from app.db.models import Song

    buenas = [h for h in historias if h.afirmable]
    if len(buenas) < pieza.min_historias:
        logger.info("[historias] «%s»: %d historia(s) afirmable(s), no da para un post",
                    pieza.titulo, len(buenas))
        return None
    # Todo el catálogo: «Lo que aletea en nuestras cabezas» entre comillas es un título,
    # no una cita (tumbaba los cierres de «Destrozares», 19-11-2026).
    from app.services import robe_facts
    titulos = ([pieza.titulo, *pieza.otros_titulos] + [x.title for x in robe_facts.discography(db)]
               + [t for (t,) in db.execute(select(Song.title)).all()])
    indice = "\n".join(f"{i}. {h.gancho}" for i, h in enumerate(buenas, 1))
    usados: list[str] = []
    partes: list[str] = []
    hechas = 0
    for h in buenas:
        letras = _letras(db, h.canciones, pieza.album_id)
        otras = "; ".join(x.gancho for x in buenas if x is not h)
        fuente = f"{hechos_duros}\n\n{h.contexto}\n\n{letras}"
        sec, datos = _seccion(client, (
            f"Escribe UNA sección de un post sobre {pieza.objeto}. Cuenta "
            f"esta historia: {h.gancho}\n"
            f"Se apoya en: «{h.tramo}».\n"
            f"Las otras secciones cuentan (no las invadas): {otras}\n"
            + f"{pieza.aviso_seccion}\n"
            + (f"DATOS YA DICHOS en otras secciones (NO los repitas): "
               f"{'; '.join(usados)}\n" if usados else "")
            + "INSTRUCCIONES:\n- Empieza con «## » y un encabezado natural, como lo escribiría "
            "una persona (sin dos puntos ni «Sujeto: tema»).\n"
            + (f"- {pieza.palabras_dato} palabras: es un dato, cuéntalo una vez y con su "
               "porqué, sin repetirlo con otras palabras." if h.quien == "hechos"
               else "- 80-220 palabras.")
            + " Abre con lo curioso, no con el dato. Cuéntalo como se lo "
            "contarías a otro fan: con sus detalles concretos y por qué importa. Si la "
            "historia da para poco, que la sección sea corta: NUNCA repitas ni resumas al "
            "final lo que ya has dicho, ni cuentes una cita y luego la parafrasees.\n"
            "- Lo que dijo alguien se cuenta con SU sentido, sin darle la vuelta. "
            + ("Si lo citas, quién lo dice y dónde va DELANTE («Robe contó a RockFM: «…»») y "
               "la cita va ENTERA entre «» y copiada LITERAL del pasaje.\n" if h.citable else
               "Es una entrevista hablada transcrita: cuéntalo en tu voz, SIN comillas y sin "
               "nombrar el programa.\n")
            + "- Los DATOS DUROS son para no equivocarte: usa solo los que sean de ESTA "
            "historia y no estén ya dichos.\n"
            "- Los nombres de giras y de programas van en cursiva y sin comillas "
            "(*Ahora es cuando*); las comillas «» son para canciones, discos y citas.\n"
            "- Si la historia trae canciones, explica qué quieren decir; como mucho un verso "
            "LITERAL de su [LETRA], nunca uno inventado.\n"
            f"- {_REGLAS_VOZ}\n"
            f"PASAJE:\n\"\"\"{h.contexto}\"\"\"\n\n{letras}\n\nDATOS DUROS:\n{hechos_duros}\n"
            'Devuelve JSON {"body_md": "...", "datos": ["cada dato concreto que has usado"]}'),
            fuente, titulos, max_tokens=1500, db=db,
            no_citable="" if h.citable or h.quien == "hechos" else h.contexto,
            extra_check=lambda t, h=h: cifras_ajenas(t, h.contexto, pieza))
        if sec:
            partes.append(sec)
            usados += datos
            hechas += 1
    if hechas < pieza.min_historias:
        logger.info("[historias] «%s»: solo %d sección(es) limpias", pieza.titulo, hechas)
        return None
    # La entradilla, la ÚLTIMA: sabiendo qué cuentan ya las secciones. Escrita la primera,
    # repetía el n.º 1 y las 132 semanas que luego tenían su sección (19-11-2026).
    resto = "\n\n".join(partes)
    entradilla, _ = _seccion(client, (
        f"Escribe la ENTRADILLA de un post sobre {pieza.objeto}. "
        f"{encargo}\nDos o tres frases, sin encabezado: engancha con lo más curioso de "
        f"lo que se va a contar y {pieza.entradilla_pide}. NO repitas ningún dato de las secciones (ni listas, ni semanas, ni "
        "grabación, ni sencillos). No resumas el post ni digas lo que el post NO cuenta.\n"
        f"{_REGLAS_VOZ}\nLAS SECCIONES YA CUENTAN ESTO (no lo repitas):\n{'; '.join(usados)}\n"
        f"Lo que se va a contar:\n{indice}\n\nDATOS DUROS:\n{hechos_duros}\n"
        'Devuelve JSON {"body_md": "..."}'),
        hechos_duros, titulos, max_tokens=500, db=db,
        extra_check=lambda t: cifras_repetidas(t, resto, pieza))
    if pieza.entradilla_fija:
        # La primera frase va fija y verificada; el modelo solo añade el enganche, y si
        # no sale limpio, la entradilla es la frase fija sola. En la efeméride el modelo
        # mezclaba «el primer aniversario» con la fecha de la muerte (19-11-2026).
        enganche, _ = _seccion(client, (
            f"Este post sobre {pieza.objeto} empieza con esta frase: «{pieza.entradilla_fija}» "
            "Escribe UNA sola frase que vaya detrás y enganche con lo que se va a contar, sin "
            "repetir esa frase ni ningún dato de las secciones. Sin encabezado.\n"
            f"{_REGLAS_VOZ}\nLo que se va a contar:\n{indice}\n"
            'Devuelve JSON {"body_md": "..."}'),
            f"{pieza.entradilla_fija}\n{hechos_duros}", titulos, max_tokens=200, db=db,
            extra_check=lambda t: cifras_repetidas(t, resto, pieza))
        entradilla = f"{pieza.entradilla_fija} {enganche}".strip()
    lineas_e = entradilla.strip().split("\n")
    if lineas_e and lineas_e[0].lstrip().startswith("#"):
        # Un encabezado aquí («## «Destrozares…»») es ruido: fuera, o fuera las almohadillas.
        resto_e = "\n".join(lineas_e[1:]).strip()
        entradilla = resto_e or re.sub(r"^\s*#+\s*", "", lineas_e[0])
    entradilla = entradilla.strip()
    if entradilla:
        partes.insert(0, entradilla)
    tray = pieza.cierre_datos
    cierre, _ = _seccion(client, (
        f"Escribe el CIERRE de un post sobre {pieza.objeto}: empieza con «## » y un "
        f"encabezado natural, y luego {pieza.cierre_pide}. {encargo}\n{_REGLAS_VOZ}\n"
        f"DATOS (solo estos):\n{tray}\n"
        f"DATOS YA DICHOS (no los repitas): {'; '.join(usados)}\n"
        'Devuelve JSON {"body_md": "..."}'), tray, titulos, max_tokens=400)
    if cierre and pieza.es_ultimo is not None and cierre_falso(cierre, pieza.titulo,
                                                                pieza.es_ultimo):
        logger.info("[historias] cierre fuera (confunde el último disco): %s",
                    cierre.replace("\n", " ⏎ ")[:400])
        cierre = ""
    if cierre:
        partes.append(cierre)
    # Última red, parte a parte: si alguna limpieza quitaría algo, la parte entera fuera
    # (quitar la frase dejaría otra coja). Con la limpieza ya dentro de cada sección,
    # aquí no debería caer nada.
    finales = []
    for parte in (p for p in partes if p):
        limpia, quitadas = limpiar_seccion(db, parte)
        if quitadas:
            logger.info("[historias] parte fuera en la red final: %s", " || ".join(quitadas))
            continue
        finales.append(limpia)
    cuerpo = "\n\n".join(finales)
    # Última red: un párrafo con las comillas descuadradas pone palabras de alguien en
    # boca del narrador. Fuera entero.
    cuerpo = "\n".join(p for p in cuerpo.split("\n") if p.count("«") == p.count("»"))
    cuerpo = re.sub(r"\n{3,}", "\n\n", cuerpo).strip()
    return cuerpo if len(cuerpo) >= 300 else None


# --------------------------------------------------------------------------- #
# Noticias por historias (19 y 20-11-2026)
# --------------------------------------------------------------------------- #
# El motor de siempre hablaba del proceso («la información disponible no identifica…»),
# montaba secciones sobre lo que no sabía y copiaba errores del artículo. Aquí la noticia
# se cuenta con las historias de SU artículo y, detrás, el contexto que solo tenemos
# nosotros (fichas, letras y lo que ya hemos publicado).
#
# La FORMA es la de las dos noticias que David aprobó escritas a mano (el sello de Correos
# y el cuadro «El rey de Extremadura»): un cuerpo de dos o tres párrafos SIN encabezados,
# con cada dato una sola vez, y una sección de contexto. La primera versión escribía una
# sección por historia, como en un disco, y medida sobre siete noticias reales (20-11)
# salían cinco apartados repitiendo el mismo hecho y un cierre con la biografía de Robe:
# el juez las tumbaba con 22-42, y con razón.
#
# Reglas (David, 19-11):
# - **Solo se entrecomilla a Robe.** Lo que dice otra persona se cuenta en nuestra voz,
#   con su nombre, y sin comillas.
# - **El título de una obra ajena no es una cita**: un cuadro o un libro van entre «» y
#   nadie «lo dice». El inventario los recoge literales del artículo.
# - **Una noticia breve lleva contexto**, del material de casa y con su tramo literal.
# - **Sin historia del artículo no hay post.** Con un artículo fino hay post breve: una
#   historia del artículo más el contexto.
FUENTE_NOTICIA = "artículo de la noticia"
FUENTE_CASA = "material de casa"
# David (20-11-2026), con la primera muestra delante: «me vale, pero es demasiado corta,
# hay que añadir más contexto». Hasta cuatro hechos de casa en la sección de contexto.
MAX_CONTEXTO = 4

_SYS_EDITOR_NOTICIA = (
    "Eres el editor de un blog de fans de Robe y Extremoduro. Te dan el ARTÍCULO de una "
    "noticia. Eliges las HISTORIAS que la cuentan: el hecho principal y los detalles que "
    "aportan algo (quién, qué, cuándo, dónde, cifras, lo que dijo alguien).\n"
    "REGLAS:\n"
    "- «tramo»: copia LITERAL del artículo, sin cambiar una palabra, entre 25 y 300 "
    "caracteres, que sostiene la historia.\n"
    "- «ancla»: UNA de estas palabras, tal cual: dato, declaracion (alguien lo dice en el "
    "artículo) o contexto.\n"
    "- «quien»: robe si habla Robe; tercero si habla otra persona; hechos si es un dato.\n"
    "- El «gancho» dice SOLO lo que dice su tramo, sin añadir nada.\n"
    "- Nada que no esté en el artículo. Cada dato en UNA historia: dos historias no "
    "pueden contar lo mismo. La primera es el hecho principal, con su cuándo y su dónde "
    "si el artículo los da. Entre 2 y 8 historias: todo lo que un fan querría saber "
    "(fechas, sitios, cifras, quién participa, cómo conseguirlo); si el artículo da para "
    "poco, menos.\n"
    "- NO elijas como historia la biografía de Robe o de Extremoduro que el artículo "
    "recuerda de pasada (dónde nació, cuándo murió, qué grupo fundó): el lector la sabe.\n"
    "- «titulos»: los NOMBRES de obras, premios, festivales, exposiciones o programas que "
    "el artículo nombra (un cuadro, un libro, un documental, un certamen), copiados "
    "LITERALES y sin comillas. No metas frases ni declaraciones.\n"
    "- «homenaje»: true si la noticia ES un homenaje, un premio, una distinción o un "
    "reconocimiento a Robe o a su obra (un sello, una medalla, un festival en su nombre, "
    "una obra dedicada a él); false en cualquier otro caso.\n"
    'Devuelve JSON {"historias": [{"gancho": "...", "ancla": "...", "tramo": "...", '
    '"quien": "..."}], "titulos": ["..."], "homenaje": false}'
)

_SYS_EDITOR_CONTEXTO = (
    "Eres el editor de un blog de fans de Robe y Extremoduro. Te dan una NOTICIA y el "
    "MATERIAL DE CASA (la lista de reconocimientos a Robe, nuestras fichas, letras y lo "
    "que ya hemos publicado). Eliges entre DOS y CUATRO historias del material que le den "
    "CONTEXTO a la noticia para un fan: la canción, el disco, el lugar o la persona de la "
    "que va, u otros hechos del mismo asunto.\n"
    "- Si la noticia es un homenaje, un premio o un reconocimiento a Robe, elige los OTROS "
    "reconocimientos de la lista: sitúan este entre los demás.\n"
    "REGLAS:\n"
    "- Solo si tiene que ver DIRECTAMENTE con lo que cuenta la noticia. Si nada del "
    "material viene a cuento, devuelve la lista vacía: es lo correcto.\n"
    "- NO vale el contexto genérico sobre Robe o Extremoduro (dónde nació, dónde y cuándo "
    "fundó el grupo, qué estilo hacía): el lector lo sabe y no sitúa ESTA noticia.\n"
    "- «tramo»: copia LITERAL del material, entre 25 y 300 caracteres.\n"
    "- El «gancho» dice SOLO lo que dice su tramo.\n"
    "- No repitas lo que ya cuenta la noticia.\n"
    'Devuelve JSON {"historias": [{"gancho": "...", "tramo": "..."}]}'
)


def _repetida(tramo: str, ya: list[Historia]) -> bool:
    return any(_plano(tramo) in _plano(x.tramo) or _plano(x.tramo) in _plano(tramo) for x in ya)


def titulos_literales(candidatos: list, articulo: str) -> tuple[str, ...]:
    """Los títulos de obras ajenas que el artículo nombra de verdad. Cortos y literales:
    una declaración colada aquí dejaría de comprobarse como cita."""
    out = []
    for t in candidatos or []:
        t = str(t).strip().strip("«»\"“”'")
        # No vale `tramo_literal` (pide 25 caracteres): un título corto que case de más
        # solo exime a ese texto de la comprobación de citas, que empieza en 20.
        if (3 <= len(t) <= 90 and not re.search(r"[.;!?]\s", t)
                and _plano(t) in _plano(articulo)):
            out.append(t)
    return tuple(dict.fromkeys(out))


_ROBE = re.compile(r"\b(?:robe|roberto iniesta|iniesta)\b")
_VERBO_DE_DECIR = (r"(?:recuerda|record[oó]|dijo|dice|explica|explic[oó]|afirma|afirm[oó]|"
                   r"cuenta|cont[oó]|señala|señal[oó]|añade|añadi[oó]|asegura|asegur[oó]|"
                   r"reconoce|reconoci[oó]|comenta|coment[oó]|apunta|apunt[oó]|escribe|"
                   r"escribi[oó]|pregunta|pregunt[oó]|responde|respondi[oó])")
_NOMBRE = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñü]+"
# Quién habla: «Uoho recuerda», «afirmó León», «dijo el consejero». Sobre el texto con
# sus mayúsculas: en minúsculas, cualquier palabra delante de «dijo» parecía un nombre.
_QUIEN_HABLA = re.compile(rf"\b({_NOMBRE}) {_VERBO_DE_DECIR}\b"
                          rf"|\b{_VERBO_DE_DECIR} (?:(?:el|la) )?({_NOMBRE}|[a-záéíóúñü]{{5,}})\b")


def habla_robe(tramo: str, articulo: str, *, ventana: int = 700) -> bool:
    """¿El artículo nombra a Robe en el tramo o poco antes? Es lo mínimo para dar por suya
    una declaración; sin eso, se cuenta sin comillas como la de cualquier otro. La
    ventana es ancha a propósito: con 220 caracteres se quedaban fuera las dos frases de
    la carta al alcalde de Plasencia, que el artículo cita una detrás de otra."""
    plano, t = _plano(articulo), _plano(tramo)
    i = plano.find(t)
    if i < 0:
        return False
    # Si lo último que el artículo dice antes es que habla OTRO («Uoho recuerda:»), la
    # frase es suya, aunque nombre a Robe unas líneas más arriba.
    limpio = tramo.strip().strip("«»\"“”'")
    crudo = (articulo or "").find(limpio)
    if crudo >= 0:
        # Hasta donde empieza la cita: el tramo puede traer dentro su «Robe dijo:».
        abre = re.search(r"[«\"“]", limpio)
        hasta = crudo + (abre.start() if abre else 0)
        ultimo = None
        for ultimo in _QUIEN_HABLA.finditer(articulo[max(0, crudo - 200): hasta]):
            pass
        if ultimo is not None:
            quien = (ultimo.group(1) or ultimo.group(2) or "").lower()
            if not _ROBE.fullmatch(quien) and quien != "roberto":
                return False
    return bool(_ROBE.search(plano[max(0, i - ventana): i + len(t)]))


def inventario_de_noticia(titular: str, articulo: str
                          ) -> tuple[list[Historia], tuple[str, ...], bool]:
    """(historias, títulos de obras ajenas, ¿es un homenaje a Robe?) de una noticia, todo
    del artículo: el tramo tiene que estar literal en él."""
    from app.services.news_research import _json

    data = _json(_SYS_EDITOR_NOTICIA,
                 f"TITULAR: {titular}\n\nARTÍCULO:\n{articulo[:9000]}", max_tokens=1500,
                 temperature=0.2)
    out: list[Historia] = []
    for h in (data or {}).get("historias") or []:
        tramo = (h.get("tramo") or "").strip()
        # El modelo a veces escribe una descripción en «ancla»: se interpreta, no se tira
        # la historia (19-11-2026: así salían 0 historias de artículos con material).
        ancla = (h.get("ancla") or "dato").strip().lower()
        if ancla not in ANCLAS:
            ancla = "declaracion" if re.search(r"declar|dice|cuenta|explica", ancla) else "dato"
        if not tramo_literal(tramo, articulo) or _repetida(tramo, out):
            continue
        quien = (h.get("quien") or "hechos").strip()
        quien = quien if quien in ("robe", "tercero") else "hechos"
        if quien == "robe" and not habla_robe(tramo, articulo):
            # En una entrevista a Uoho, el editor marcó como de Robe una frase suya y se
            # publicó entrecomillada (muestra del 20-11-2026). Sin «Robe» al lado, no.
            quien = "tercero"
        # Un artículo es texto escrito: lo que dice Robe en él se puede entrecomillar. Lo
        # de los demás, no.
        out.append(Historia(h.get("gancho") or tramo, ancla, FUENTE_NOTICIA, tramo, quien,
                            True, citable=quien == "robe"))
    return (out, titulos_literales((data or {}).get("titulos") or [], articulo),
            (data or {}).get("homenaje") is True)


def inventario_noticia(titular: str, articulo: str) -> list[Historia]:
    return inventario_de_noticia(titular, articulo)[0]


def inventario_contexto(titular: str, articulo: str, casa: str, ya: list[Historia], *,
                        homenaje: bool = False,
                        reconocimientos: tuple[str, ...] = ()) -> list[Historia]:
    """Las historias de CONTEXTO, del material de casa y con su tramo literal.

    Si la noticia es un homenaje a Robe, el contexto son los OTROS reconocimientos de la
    lista de casa, sin preguntar a nadie: dejárselo al editor dio una Medalla de 2026 como
    contexto de una carta del año 2000 y ningún reconocimiento para el sello ni para el
    cuadro (muestra del 20-11-2026). Si no lo es, elige el editor entre las fichas y lo
    ya publicado, y la lista de reconocimientos ni la ve. Si el modelo falla o nada viene
    a cuento, ninguna: la noticia sale sin contexto, no con uno traído por los pelos.
    """
    from app.services.news_research import _json

    if homenaje and reconocimientos:
        otros = [h for h in reconocimientos
                 if not repite_la_noticia(h, articulo) and not _repetida(h, ya)]
        if otros:
            return [Historia(h, "contexto", FUENTE_CASA, h, "hechos", True)
                    for h in otros[-MAX_CONTEXTO:]]
    for h in reconocimientos:
        casa = (casa or "").replace(f"- {h}", "")
    if not (casa or "").strip():
        return []
    try:
        data = _json(_SYS_EDITOR_CONTEXTO,
                     f"NOTICIA: {titular}\n{articulo[:3000]}\n\nMATERIAL DE CASA:\n{casa[:9000]}",
                     max_tokens=700, temperature=0.2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[historias] contexto de la noticia: %s", exc)
        return []
    out: list[Historia] = []
    for h in ((data or {}).get("historias") or [])[:MAX_CONTEXTO]:
        tramo = (h.get("tramo") or "").strip()
        if not tramo_literal(tramo, casa) or _repetida(tramo, ya + out):
            continue
        # Lo que ya dice el artículo no es contexto: es la noticia.
        if tramo_literal(tramo, articulo) or repite_la_noticia(tramo, articulo):
            continue
        out.append(Historia(h.get("gancho") or tramo, "contexto", FUENTE_CASA, tramo,
                            "hechos", True))
    return out


def sin_encabezados(texto: str) -> str:
    """El cuerpo sin encabezados. Una línea corta con «#» es un encabezado y sobra; una
    larga es un PÁRRAFO al que el modelo le puso almohadillas, y se queda sin ellas:
    borrarla se llevó la entradilla entera de la noticia del sello (20-11-2026) y lo
    que quedó empezaba por las medidas del papel."""
    out = []
    for linea in (texto or "").split("\n"):
        if linea.lstrip().startswith("#"):
            limpia = re.sub(r"^\s*#+\s*", "", linea)
            if len(limpia) < 90:
                continue
            linea = limpia
        out.append(linea)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def repite_la_noticia(tramo: str, articulo: str) -> bool:
    """¿Este tramo de casa cuenta lo mismo que el artículo? Nuestra noticia del cuadro
    ya hablaba del sello, y como «contexto» del sello volvía a dar su precio y su tirada.
    Se mira por las cifras y por las palabras largas que comparten."""
    plano = _plano(articulo)
    cifras = set(re.findall(r"\d[\d.,]*\d|\d", tramo))
    if len(cifras) >= 2 and sum(c in plano for c in cifras) >= 2:
        return True
    largas = {w for w in re.findall(r"[a-záéíóúñü]{6,}", _plano(tramo))}
    return len(largas) >= 4 and sum(w in plano for w in largas) / len(largas) >= 0.7


MIN_PALABRAS_CONTEXTO = 40
MAX_PASAJE = 4500


def pasajes_de(articulo: str, tramos: list[str], *, maximo: int = MAX_PASAJE) -> str:
    """Los párrafos del artículo donde están los tramos, en su orden.

    El redactor y sus comprobaciones leen 6.000 caracteres, y un artículo con la nota de
    prensa pegada pasa de 17.000: con el artículo entero, lo que estaba más abajo se daba
    por «no dicho» y tumbaba el cuerpo (muestra del 20-11-2026, tres de seis noticias).
    Si el texto viene en un solo bloque, una ventana alrededor de cada tramo.
    """
    parrafos = [x.strip() for x in re.split(r"\n\s*\n|\n", articulo or "") if x.strip()]
    planos = [_plano(t) for t in tramos if t]
    elegidos = [x for x in parrafos if any(t in _plano(x) for t in planos)]
    if not elegidos or max(len(x) for x in elegidos) > maximo:
        plano = _plano(articulo)
        elegidos = []
        for t in planos:
            i = plano.find(t)
            if i >= 0:
                elegidos.append(plano[max(0, i - 250): i + len(t) + 250])
    out, total = [], 0
    for x in dict.fromkeys(elegidos):
        if total + len(x) > maximo:
            break
        out.append(x)
        total += len(x)
    return "\n\n".join(out)


_DIA_SIN_ANIO = re.compile(
    r"\b(\d{1,2}) de (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|"
    r"noviembre|diciembre)\b(?!\s+de\s+\d{4})", re.I)


def fechas_sin_anio(texto: str) -> list[str]:
    """Los días que el cuerpo da sin su año. «El sábado 14 de noviembre» no sitúa nada a
    quien lo lea dentro de un año, y el juez lo rechazaba tres de tres veces (20-11-2026):
    pedírselo al redactor en el encargo no bastó."""
    return [f"«{m.group(0)}» va sin año: escríbelo con su año"
            for m in _DIA_SIN_ANIO.finditer(texto or "")]


def citas_ajenas(texto: str, de_robe: list[str], titulos: list[str]) -> list[str]:
    """Lo que el cuerpo de una noticia entrecomilla y no es de Robe ni un título. En una
    noticia solo se cita a Robe; lo que dice otra persona se cuenta sin comillas."""
    tit = {_plano(t) for t in titulos}
    robe = [_plano(t) for t in de_robe]
    fallos = []
    for m in _CITA.finditer(texto or ""):
        c = _plano(m.group(1))
        if c in tit or _es_nombre_propio(m.group(1)):
            continue
        if not any(c in t or t in c for t in robe):
            fallos.append(f"«{m.group(1)[:60]}» va entre comillas y no lo dice Robe: cuenta lo "
                          "que se dijo SIN comillas, con el nombre de quien lo dijo")
    return fallos


def _titulos_del_catalogo(db) -> list[str]:
    from sqlalchemy import select

    from app.db.models import Song
    from app.services import robe_facts

    if db is None:
        return []
    return ([x.title for x in robe_facts.discography(db)]
            + [t for (t,) in db.execute(select(Song.title)).all()])


def escribir_noticia(db, titular: str, articulo: str, *, casa: str = "",
                     fecha: str = "", reconocimientos: tuple[str, ...] = ()) -> str | None:
    """El cuerpo de una noticia por historias, o None si el artículo no da para ello.

    `casa`: el material nuestro que puede dar contexto (`news_research.material_de_casa`).
    `fecha`: cuándo se escribe («noviembre de 2026»), para que un día sin año lo lleve.
    """
    import os

    from openai import OpenAI

    from app.services import robe_facts

    if not (articulo or "").strip():
        return None
    del_articulo, otros_titulos, homenaje = inventario_de_noticia(titular, articulo)
    if not del_articulo:
        logger.info("[historias] noticia «%s»: ninguna historia en el artículo", titular)
        return None
    contexto = inventario_contexto(titular, articulo, casa, del_articulo,
                                   homenaje=homenaje, reconocimientos=reconocimientos)
    if len(del_articulo) + len(contexto) < 2:
        logger.info("[historias] noticia «%s»: una historia y sin contexto, no da para un "
                    "post", titular)
        return None
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    titulos = [titular, *otros_titulos, *_titulos_del_catalogo(db)]
    de_casa = "\n".join(robe_facts.must_facts_lines(db))
    def _cuerpo(historias: list[Historia]) -> str:
        citas_de_robe = [h.tramo for h in historias if h.citable]
        pasaje = pasajes_de(articulo, [h.tramo for h in historias])
        palabras = min(90 + 50 * len(historias), 380)
        texto, _ = _seccion(client, (
            f"Escribe el CUERPO de la noticia «{titular}» para un blog de fans de Robe y "
            "Extremoduro.\nINSTRUCCIONES:\n"
            "- SIN encabezados. Dos o tres párrafos. El primero cuenta qué ha pasado, quién, "
            "cuándo y dónde; los siguientes, los detalles.\n"
            f"- Como mucho {palabras} palabras. Cada dato UNA sola vez: no lo repitas con otras "
            "palabras ni lo resumas al final. Sin frase de cierre.\n"
            "- Cuenta SOLO lo que dicen estos TRAMOS del artículo, con sus datos exactos "
            "(nombres, cargos, cifras, fechas) y sin inflarlos:\n"
            + "\n".join(f"  · «{h.tramo}»" for h in historias) + "\n"
            + (f"- Se escribe en {fecha}. Toda fecha lleva su AÑO, también si el artículo no lo "
               "escribe («el sábado 14 de noviembre» es «el sábado 14 de noviembre de 2026» si "
               "es de este año).\n" if fecha else "")
            + "- No expliques quién era Robe ni recuerdes su biografía: el lector lo sabe.\n"
            "- Cuéntalo como hechos: nunca «según el artículo», «según la información» ni "
            "nada que hable de dónde sale el dato.\n"
            + ("- A Robe se le puede citar: quién lo dice va DELANTE («Robe escribió: «…»») y la "
               "cita va ENTERA entre «» y copiada LITERAL del artículo.\n" if citas_de_robe else "")
            + "- Lo que dice otra persona se cuenta en tu voz y SIN comillas, diciendo quién lo "
            "dijo (su nombre y su cargo, si el artículo los da). Los títulos de obras, premios "
            "y canciones sí van entre «».\n"
            "- Los DATOS DE CASA son para no equivocarte (si el artículo dice otra cosa de "
            "Robe, vale lo de casa): no los añadas si la noticia no habla de ello.\n"
            f"- {_REGLAS_VOZ}\n"
            f"ARTÍCULO (no nombres el medio):\n\"\"\"{pasaje}\"\"\"\n\n"
            f"DATOS DE CASA:\n{de_casa}\n"
            'Devuelve JSON {"body_md": "..."}'),
            # Los datos de casa, delante: lo que se comprueba se corta a 6.000 caracteres. Y
            # la fecha en que se escribe, o el verificador quita el año que se le pide al
            # redactor porque «el artículo no lo dice» (20-11-2026, tres intentos de tres).
            f"{de_casa}\n\n"
            + (f"[El artículo es de {fecha}: un día que da sin año es de ese año.]\n\n"
               if fecha else "") + pasaje,
            titulos, max_tokens=1100, db=db, intentos=3,
            extra_check=lambda t: (citas_ajenas(t, citas_de_robe, titulos)
                                   + (fechas_sin_anio(t) if fecha else [])))
        return sin_encabezados(texto)

    cuerpo = _cuerpo(del_articulo)
    sin_declaraciones = [h for h in del_articulo if h.quien != "tercero"]
    if len(cuerpo) < 300 and 0 < len(sin_declaraciones) < len(del_articulo):
        # El redactor se empeña en entrecomillar lo que dijo un tercero (el consejero, en
        # la noticia del cuadro, tres intentos de tres). Antes de quedarse sin noticia,
        # se escribe sin esa declaración: lo que se pierde es una frase, no el hecho.
        logger.info("[historias] noticia «%s»: se reintenta sin las declaraciones de "
                    "terceros", titular)
        cuerpo = _cuerpo(sin_declaraciones)
    if len(cuerpo) < 300:
        logger.info("[historias] noticia «%s»: el cuerpo no salió limpio", titular)
        return None
    partes = [cuerpo]
    if contexto:
        seccion, _ = _seccion(client, (
            f"Escribe UNA sección de CONTEXTO para la noticia «{titular}» en un blog de fans "
            "de Robe y Extremoduro.\nINSTRUCCIONES:\n"
            "- Empieza con «## » y un encabezado natural, como lo escribiría una persona "
            "(sin dos puntos ni «Sujeto: tema»).\n"
            f"- {60 + 40 * len(contexto)}-{110 + 50 * len(contexto)} palabras. Sitúa la "
            "noticia con estos hechos NUESTROS, con sus fechas y sus datos exactos, y solo "
            "con ellos:\n" + "\n".join(f"  · «{h.tramo}»" for h in contexto) + "\n"
            "- Se cuentan como hechos, sin decir de dónde salen ni que «ya lo contamos». No "
            "les pongas fecha si el tramo no la trae.\n"
            "- NO repitas lo que ya dice la noticia. Sin frase de cierre.\n"
            f"- {_REGLAS_VOZ}\n"
            f"LA NOTICIA YA DICE:\n\"\"\"{cuerpo}\"\"\"\n\n"
            f"MATERIAL DE CASA:\n\"\"\"{pasajes_de(casa, [h.tramo for h in contexto])}"
            "\"\"\"\n"
            'Devuelve JSON {"body_md": "..."}'),
            f"{de_casa}\n\n{pasajes_de(casa, [h.tramo for h in contexto])}", titulos,
            max_tokens=600, db=db)
        # Una sola frase bajo un encabezado no es contexto: es un apunte suelto.
        if seccion and len(seccion.split()) >= MIN_PALABRAS_CONTEXTO:
            partes.append(seccion)
    if len(partes) == 1 and len(del_articulo) < 2:
        logger.info("[historias] noticia «%s»: una historia y el contexto no salió limpio",
                    titular)
        return None
    texto = "\n\n".join(partes)
    texto = "\n".join(x for x in texto.split("\n") if x.count("«") == x.count("»"))
    return re.sub(r"\n{3,}", "\n\n", texto).strip()
