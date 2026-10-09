"""El verso 🎵 que cierra un post de Instagram: de SU canción o ninguno.

Ver `verso_de_cancion`. Hasta el 09-10-2026 se elegía por parecido vectorial
con el texto del post y salían versos de canciones ajenas al tema.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from sqlalchemy.orm import Session

from app.db.models import Song

logger = logging.getLogger(__name__)


def _clean_song_title(title: str) -> str:
    """Quita sufijos de versión: '[En Directo]', '(Maqueta)', etc."""
    title = re.sub(r"\s*\[[^\]]*\]\s*$", "", title)
    title = re.sub(
        r"\s*\((?:en directo|directo|maqueta|remasterizad[ao])[^)]*\)\s*$",
        "", title, flags=re.IGNORECASE,
    )
    return title.strip()


def _norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


_TERMINAL = re.compile(r'[.!?…]["»)]?\s*$')


# --------------------------------------------------------------------------- #
# El verso de SU canción
# --------------------------------------------------------------------------- #
# Hasta el 09-10-2026 el verso se elegía por PARECIDO con el texto del post
# (búsqueda vectorial sobre todas las líneas). Medido en prod: 192 posts con
# verso y 153 con uno de solo TRES versos comodín — «Mira por donde va el Robe»
# atraía a cualquier noticia con «Robe» dentro. Un clip de «Si te vas...» salió
# con un verso de «Bri, bri, bli, bli» teniendo el estribillo bueno en la BD.
#
# Criterio de David: lleva verso SOLO el post que va de una canción concreta, y
# el verso es de ESA canción (en su versión original). Sin canción, sin verso.

# Charla de la grabación que Genius transcribe como si fuera letra.
_CHARLA = re.compile(r"^(toma\b|eh[,!]|uno,? dos|vamos\b|venga\b)", re.IGNORECASE)
MAX_CHARS_VERSO = 160


def _palabras(s: str) -> list[str]:
    return re.findall(r"[a-zñ0-9]+", _strip_accents(s))


def verso_decente(verso: str, titulo: str) -> bool:
    """¿Funciona como cita? Descarta lo que se publicó como «Deltoya, deltoya…»
    ×35 (solo el título repetido), la charla de estudio («Toma primera…») y lo
    que no cabe."""
    v = (verso or "").strip()
    if not v or len(v) > MAX_CHARS_VERSO:
        return False
    palabras = _palabras(v)
    del_titulo = set(_palabras(_clean_song_title(titulo)))
    propias = {p for p in palabras if p not in del_titulo}
    if len(set(palabras)) < 4 or len(propias) < 3:
        return False
    return not _CHARLA.search(v)


def _estribillo(textos: list[str]) -> int | None:
    """Índice de la primera aparición del estribillo: un verso que se repite 3+
    veces Y vuelve a lo largo de la canción (dispersión ≥ 0,35). Mismo criterio
    que `momentos`, por el mismo motivo: lo que se repite al principio es la
    letanía de entrada, no el estribillo."""
    from app.services.instagram.momentos import DISPERSION_MIN, REPETICIONES_ESTRIBILLO

    n = len(textos)
    pos: dict[str, list[int]] = {}
    for i, t in enumerate(textos):
        k = _norm_line(t)
        if len(k) > 12:
            pos.setdefault(k, []).append(i)
    mejores = [
        (len(ix), ix[0]) for ix in pos.values()
        if len(ix) >= REPETICIONES_ESTRIBILLO and (ix[-1] - ix[0]) / max(n, 1) >= DISPERSION_MIN
    ]
    return max(mejores)[1] if mejores else None


def _linea_ok(linea: str, titulo: str) -> bool:
    """Una línea suelta que no aporta nada propio: solo el título repetido
    («Deltoya, deltoya…») o charla de la grabación. Se mira línea a línea: en el
    bloque entero, una buena al lado la camuflaba."""
    palabras = _palabras(linea)
    if not palabras or _CHARLA.search(linea.strip()):
        return False
    raices = {w[:4] for w in _palabras(_clean_song_title(titulo)) if len(w) >= 4}
    # Por raíz y no por palabra exacta: la letra trae apócopes («delto'»), y una
    # línea con «deltoya» cuatro veces y un «delto'» al final seguía pasando.
    del_titulo = [w for w in palabras if len(w) >= 4 and w[:4] in raices]
    return len(del_titulo) / len(palabras) <= 0.5


def _bloque(textos: list[str], idx: int, titulo: str, max_lines: int = 4) -> list[str]:
    """La frase completa alrededor de `idx` (hasta cerrar con puntuación), con
    tope de líneas, sin repetir la misma línea dos veces seguidas y cortando en
    cuanto aparece una línea que no vale (`_linea_ok`)."""
    if not _linea_ok(textos[idx] or "", titulo):
        return []
    start = idx
    while start > 0 and textos[start - 1] and not _TERMINAL.search(textos[start - 1]) \
            and _linea_ok(textos[start - 1], titulo) and (idx - start) < 1:
        start -= 1
    out: list[str] = []
    for t in textos[start:]:
        t = (t or "").strip()
        if not t:
            if out:
                break
            continue
        if not _linea_ok(t, titulo):
            break
        if out and _norm_line(t) == _norm_line(out[-1]):
            continue
        out.append(t)
        if len(out) >= max_lines or _TERMINAL.search(t):
            break
    return out


def verso_de_cancion(db: Session, song_id: int | None, preferido: str | None = None) -> dict:
    """El verso de la canción `song_id`, en su versión ORIGINAL, o `{}`.

    Orden: el `preferido` si está en la letra (el clip ya sabe qué verso suena),
    luego el estribillo, luego el primer bloque que funcione como cita. Las
    líneas se unen con « / », que es como se cita un verso. Nunca se reescribe.
    """
    if not song_id:
        return {}
    from app.services.versiones import version_original

    song = db.get(Song, song_id)
    if song is None:
        return {}
    song = version_original(db, song)
    textos = [(ln.text or "").strip() for ln in song.lines]
    if not any(textos):
        return {}

    candidatos: list[int] = []
    if preferido:
        objetivo = _norm_line(preferido)
        candidatos += [i for i, t in enumerate(textos) if _norm_line(t) and _norm_line(t) in objetivo]
    est = _estribillo(textos)
    if est is not None:
        candidatos.append(est)
    candidatos += list(range(len(textos)))

    vistos: set[int] = set()
    for i in candidatos:
        if i in vistos or not textos[i]:
            continue
        vistos.add(i)
        bloque = _bloque(textos, i, song.title)
        verso = " / ".join(bloque)
        if verso_decente(verso, song.title):
            album = song.album
            artist = album.artist if album is not None else None
            return {
                "line": verso,
                "song": _clean_song_title(song.title),
                "song_id": song.id,
                "artist": artist.name if artist is not None else "Extremoduro",
                "year": album.year if album is not None else None,
            }
    return {}


def cancion_del_post(db: Session, item) -> tuple[int | None, str | None]:
    """¿De qué canción va este post? `(song_id, verso_preferido)` o `(None, None)`.

    Solo dos casos la saben con certeza, y por eso solo esos llevan verso:
      - un CLIP de concierto: `propose_clips` dejó «Canción:» y el verso de
        nuestra letra en el `summary`;
      - un post del blog que es la ficha de una canción (`spotlight:song_<id>`).
    Una noticia que NOMBRA una canción no va de ella: no se adivina.
    """
    from app.db.models import Post

    if (item.media_type or "") == "CLIP" or (item.content_type or "") == "clip":
        datos: dict[str, str] = {}
        for linea in (item.summary or "").splitlines():
            if ":" in linea:
                k, v = linea.split(":", 1)
                datos[k.strip().lower()] = v.strip()
        titulo = datos.get("canción") or datos.get("cancion")
        if titulo:
            sid = db.query(Song.id).filter(Song.title == titulo).order_by(Song.id).scalar()
            if sid:
                return sid, datos.get("verso (de nuestra letra)")
        return None, None

    if item.blog_post_id:
        post = db.get(Post, item.blog_post_id)
        ck = (getattr(post, "content_key", None) or "") if post else ""
        m = re.match(r"spotlight:song_(\d+)$", ck)
        if m:
            return int(m.group(1)), None
    return None, None
