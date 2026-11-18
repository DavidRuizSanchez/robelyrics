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

    def to_dict(self) -> dict:
        return asdict(self)


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


def inventario(db, album, *, hechos_duros: str, usar_web: bool = True) -> list[Historia]:
    """Las historias afirmables (y las que no, con su motivo) de un disco."""
    from sqlalchemy import select

    from app.db.models import Song
    from app.services.news_research import _json

    canciones = [t for (t,) in db.execute(
        select(Song.title).where(Song.album_id == album.id)
        .order_by(Song.track_number.nulls_last())).all()]
    pasajes = _pasajes(db, consultas_del_disco(album.title, canciones))
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
                        list(h.get("canciones") or []))
    p = por_id.get(fuente_id)
    if not p or not tramo_literal(tramo, p.get("fragmento") or ""):
        logger.info("[historias] fuera: el tramo no está literal en %s", fuente_id)
        return None
    fuente = f"{fuente_id} · {(p.get('title') or '')[:70]}"
    quien = (h.get("quien") or "tercero").strip()
    kind = p.get("kind")
    historia = Historia(h.get("gancho", ""), ancla, fuente, tramo, quien, False,
                        list(h.get("canciones") or []))
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
    from app.services.corpus_for_queries import en_dos_fuentes
    otras = en_dos_fuentes(db, tramo)
    if otras:
        historia.afirmable = True
        historia.motivo = "corroborado en dos fuentes: " + " / ".join(o[:50] for o in otras[:2])
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
