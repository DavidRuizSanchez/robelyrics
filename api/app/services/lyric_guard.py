"""Guardia determinista de CITAS DE LETRA (anti-alucinación de versos).

Motivo (incidente 2026-07): se publicó un post que atribuía a "So payaso" el
verso «Si te vas, te voy a colgar de las piernas…» y a "Salir" «…quisiera que el
alma me saliera de su escondite» — versos que NO existen en ninguna canción del
corpus. El `fact_check` de la casa descarta por diseño las citas entre comillas
(no las verifica), así que un verso inventado pasa todos los gates.

Este módulo cierra ese agujero: extrae cada cita entrecomillada presentada como
LETRA de una canción y comprueba, de forma DETERMINISTA (sin LLM), que exista de
verdad en la letra real (`songs.lyrics_clean` / `lines.text`).

Filosofía anti-FALSOS-POSITIVOS (crítica): un verso REAL no puede bloquearse por
una coma, un acento, un apócope castizo ("descolorío'"), un singular/plural o un
signo de puntuación. Por eso el match es tolerante (normalización agresiva +
fuzzy por ventana) y los umbrales son por tramos, NO binarios:

  - coincidencia alta  → OK (pasa).
  - coincidencia media → a REVISIÓN humana (nunca auto-bloqueo).
  - coincidencia nula  → BLOQUEO por fabricación (inequívocamente inventado).

El bloqueo duro se reserva a lo que no tiene solapamiento real con la letra. Las
canciones sin letra en el corpus (Pedrá, Por la boca vive el pez — Genius roto)
no admiten cita literal: se bloquean salvo que el verso esté curado a mano en
`data/external_verses.yaml`.
"""
from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Umbrales del matcher fuzzy (calibrados con letras reales del corpus).
_OK_RATIO = 0.86        # >= → el verso existe en la canción
_REVIEW_RATIO = 0.66    # [review, ok) → zona gris → revisión humana
# < _REVIEW_RATIO → no está en esa letra

_MIN_QUOTE_WORDS = 3    # citas más cortas (títulos, énfasis) no se tratan como verso
_ATTRIB_WINDOW = 420    # chars antes de la cita donde buscar la canción atribuida

# Indica que lo entrecomillado es una LETRA aunque no haya título justo al lado.
_LYRIC_HINT = re.compile(
    r"\b(canta|cantaba|verso|versos|letra|estribillo|reza la (?:letra|cancion)|"
    r"dice (?:la|el) (?:cancion|tema|estribillo)|en la cancion)\b",
    re.IGNORECASE,
)

_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "«": '"', "»": '"'})

Status = Literal["ok", "fabricated", "misattributed", "no_lyrics", "review"]


# --------------------------------------------------------------------------- #
# Normalización tolerante (núcleo puro, testeable sin BD)
# --------------------------------------------------------------------------- #
def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )


def normalize(s: str) -> str:
    """Minúsculas, sin acentos, sin puntuación NI apóstrofos (los apócopes
    castizos "pa'"/"na'"/"descolorío'" quedan como "pa"/"na"/"descolorio"),
    espacios colapsados. Ambos lados de la comparación se normalizan igual, así
    que comas, saltos de verso, mayúsculas y tildes dejan de importar."""
    s = _strip_accents((s or "").translate(_QUOTES)).lower()
    s = re.sub(r"[^a-z0-9ñ ]+", " ", s)   # puntuación y apóstrofos → espacio
    return re.sub(r"\s+", " ", s).strip()


def best_ratio(quote_norm: str, lyrics_norm: str) -> float:
    """Mejor solapamiento del verso citado dentro de una letra (ambos ya
    normalizados). 1.0 si la cita es subcadena literal de la letra (tolerante a
    puntuación/acentos por la normalización); si no, fuzzy por ventana deslizante
    de tokens para absorber apócopes, plurales y fragmentos parciales."""
    if not quote_norm or not lyrics_norm:
        return 0.0
    if quote_norm in lyrics_norm:
        return 1.0
    q_tokens = quote_norm.split()
    l_tokens = lyrics_norm.split()
    if not q_tokens or not l_tokens:
        return 0.0
    n = len(q_tokens)
    best = 0.0
    matcher = difflib.SequenceMatcher(None, quote_norm, "")
    matcher.set_seq1(quote_norm)
    # Ventanas de tamaño n-1..n+1 para tolerar una palabra de más/menos (elisión).
    for win in (n, n + 1, max(1, n - 1)):
        upper = len(l_tokens) - win + 1
        if upper < 1:
            upper = 1
        for i in range(0, upper):
            cand = " ".join(l_tokens[i:i + win])
            matcher.set_seq2(cand)
            # quick_ratio es una cota superior barata: si ni así llega, no calcula ratio.
            if matcher.quick_ratio() <= best:
                continue
            r = matcher.ratio()
            if r > best:
                best = r
                if best >= 0.999:
                    return best
    return best


# --------------------------------------------------------------------------- #
# Tipos de resultado
# --------------------------------------------------------------------------- #
@dataclass
class LyricVerdict:
    quote: str                      # cita tal como aparece en el texto
    status: Status
    attributed_song: str | None = None   # canción a la que el texto se lo atribuye
    matched_song: str | None = None       # canción cuya letra SÍ contiene el verso
    matched_album: str | None = None
    matched_year: int | None = None
    ratio: float = 0.0
    reason: str = ""

    @property
    def is_blocking(self) -> bool:
        return self.status in ("fabricated", "no_lyrics")

    @property
    def needs_review(self) -> bool:
        return self.status in ("misattributed", "review")


@dataclass
class LyricGuardReport:
    verdicts: list[LyricVerdict] = field(default_factory=list)

    @property
    def blocking(self) -> list[LyricVerdict]:
        """Versos inequívocamente inventados o citas de canciones sin letra
        verificable. NO se publican JAMÁS (ni con force_publish)."""
        return [v for v in self.verdicts if v.is_blocking]

    @property
    def to_review(self) -> list[LyricVerdict]:
        """Zona gris / posible misatribución: a revisión humana, no auto-publica."""
        return [v for v in self.verdicts if v.needs_review]

    @property
    def is_clean(self) -> bool:
        return not self.blocking and not self.to_review

    def summary(self) -> str:
        return (f"{len(self.verdicts)} citas de letra · "
                f"{len(self.blocking)} bloqueantes · {len(self.to_review)} a revisar")


# --------------------------------------------------------------------------- #
# Extracción de citas y de la canción atribuida
# --------------------------------------------------------------------------- #
def _unwrap_md_links(s: str) -> str:
    """`[texto](url)` → `texto`. Un enlace markdown con el TÍTULO de una canción
    como ancla no es un verso citado; sin desenvolverlo, la URL contamina la
    comparación y produce falsos positivos."""
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s or "")


def _mask_link_urls(s: str) -> str:
    """Sustituye la URL de cada enlace markdown `](url)` por espacios de la MISMA
    longitud (preserva posiciones). Así los slugs de las URLs (p.ej.
    `/extremoduro/yo-minoria-absoluta/menamoro`) no se detectan como menciones de
    canción y no falsean la atribución del verso a la 'canción más cercana'."""
    return re.sub(r"\]\(([^)\n]*)\)", lambda m: "](" + " " * len(m.group(1)) + ")", s or "")


def extract_quotes(body_md: str) -> list[tuple[str, int]]:
    """Devuelve [(texto_cita, posición_inicio)] de todo lo entrecomillado con
    comillas dobles/guillemets y de los blockquotes markdown. Ignora comillas
    simples (colisionan con apóstrofos). Desenvuelve enlaces markdown del texto
    citado para no confundir un título enlazado con un verso."""
    body = (body_md or "").translate(_QUOTES)
    out: list[tuple[str, int]] = []
    for m in re.finditer(r'"([^"\n]{3,300})"', body):
        out.append((_unwrap_md_links(m.group(1)).strip(), m.start()))
    # Blockquotes: líneas que empiezan por '>' (se citan versos así a menudo).
    for m in re.finditer(r'(?m)^>\s?(.+)$', body):
        out.append((_unwrap_md_links(m.group(1)).strip(), m.start()))
    return out


def _title_occurrences(body_norm: str, titles_norm: list[str]) -> list[tuple[int, str]]:
    """Posiciones (en el body NORMALIZADO) de cada título de canción mencionado.
    Se buscan del más largo al más corto para no casar un título dentro de otro."""
    occ: list[tuple[int, str]] = []
    for t in sorted(titles_norm, key=len, reverse=True):
        if len(t) < 3:
            continue
        for m in re.finditer(r'(?<![a-z0-9ñ])' + re.escape(t) + r'(?![a-z0-9ñ])', body_norm):
            occ.append((m.start(), t))
    return occ


def _norm_positions(body: str) -> tuple[str, list[int]]:
    """Body normalizado + mapa de posición-normalizada → posición-original, para
    poder relacionar la posición de una cita (original) con las menciones de
    título (normalizado)."""
    body = _strip_accents((body or "").translate(_QUOTES)).lower()
    out_chars: list[str] = []
    out_map: list[int] = []
    prev_space = False
    for i, ch in enumerate(body):
        c = ch if re.match(r"[a-z0-9ñ ]", ch) else " "
        if c == " ":
            if prev_space:
                continue
            prev_space = True
        else:
            prev_space = False
        out_chars.append(c)
        out_map.append(i)
    return "".join(out_chars).strip(), out_map


# --------------------------------------------------------------------------- #
# Verificación contra el corpus (DB-facing)
# --------------------------------------------------------------------------- #
@dataclass
class _SongLyrics:
    title: str
    album: str
    year: int
    lyrics_norm: str
    has_lyrics: bool
    tokens: frozenset = field(default_factory=frozenset)  # set de palabras (pre-filtro)

    def __post_init__(self) -> None:
        if not self.tokens and self.lyrics_norm:
            self.tokens = frozenset(self.lyrics_norm.split())


def _overlap(q_tokens: set[str], song_tokens: frozenset) -> float:
    """Fracción de palabras DISTINTAS del verso presentes en la canción. Pre-filtro
    SEGURO: si el verso está de verdad en la letra, todas sus palabras están → 1.0
    (nunca poda un match real). Solo descarta canciones que no pueden contenerlo."""
    if not q_tokens:
        return 0.0
    return len(q_tokens & song_tokens) / len(q_tokens)


# --------------------------------------------------------------------------- #
# Completado de versos: expande un verso citado a la LÍNEA COMPLETA de la letra
# real, para que las citas nunca queden a medias (ni en el blog ni en Instagram).
# --------------------------------------------------------------------------- #
_COMPLETE_MIN_RATIO = 0.6   # parecido mínimo verso↔línea para considerarlo el mismo


def _load_song_lines(db) -> list[dict]:
    """Por canción: líneas (original + normalizada) y el set de palabras (pre-filtro)."""
    from sqlalchemy import select

    from app.db.models import Line, Song

    rows = db.execute(
        select(Song.id, Song.title, Line.text, Line.line_index)
        .join(Line, Line.song_id == Song.id)
        .order_by(Song.id, Line.line_index)
    ).all()
    by_song: dict[int, dict] = {}
    for sid, title, text, _idx in rows:
        s = by_song.setdefault(sid, {"title": title, "lines": []})
        s["lines"].append((text or "", normalize(text or "")))
    out: list[dict] = []
    for s in by_song.values():
        toks: set[str] = set()
        for _o, n in s["lines"]:
            toks.update(n.split())
        out.append({"title": s["title"], "lines": s["lines"], "tokens": frozenset(toks)})
    return out


def _best_complete_line(quote_norm: str, quote_tokens: set[str], song: dict) -> str | None:
    """Línea (o par de líneas consecutivas) de la canción que CONTIENE todas las
    palabras del verso citado y mejor casa con él. Devuelve el texto ORIGINAL
    completo, o None si ninguna línea lo contiene con parecido suficiente."""
    lines = song["lines"]
    best_txt, best_score = None, 0.0
    for i in range(len(lines)):
        for span in (1, 2):  # el verso puede abarcar 2 líneas
            if i + span > len(lines):
                continue
            group = lines[i:i + span]
            gnorm = " ".join(n for _o, n in group if n).strip()
            if not gnorm:
                continue
            gtok = set(gnorm.split())
            if not quote_tokens.issubset(gtok):  # todas las palabras del verso deben estar
                continue
            r = best_ratio(quote_norm, gnorm)
            if r > best_score:
                best_score = r
                best_txt = " / ".join(o.strip() for o, n in group if o.strip())
    return best_txt if best_txt and best_score >= _COMPLETE_MIN_RATIO else None


def complete_verses(db, body_md: str) -> str:
    """Expande cada verso citado (entre comillas) a la LÍNEA COMPLETA de la letra
    real cuando el citado sea un fragmento de ella. Determinista y conservador:
    solo toca la cita si UNA sola línea del corpus la completa sin ambigüedad."""
    if not body_md:
        return body_md
    songs = _load_song_lines(db)
    matches = list(re.finditer(r'["“«]([^"”»\n]{6,240})["”»]', body_md))
    if not matches:
        return body_md
    body = body_md
    for m in reversed(matches):  # de atrás→delante para no invalidar posiciones
        inner = m.group(1).strip()
        qn = normalize(_unwrap_md_links(inner))
        qtok = set(qn.split())
        if len(qtok) < 3:
            continue
        completions = set()
        for s in songs:
            if not qtok.issubset(s["tokens"]):  # pre-filtro: todas las palabras en la canción
                continue
            c = _best_complete_line(qn, qtok, s)
            if c:
                completions.add(c)
        if len(completions) != 1:  # ninguno o ambiguo → no tocar (seguridad)
            continue
        full = completions.pop()
        if normalize(full) == qn:  # el verso ya está completo
            continue
        if len(full) > max(140, len(inner) * 3):  # evitar sobre-expansión
            continue
        body = body[:m.start(1)] + full + body[m.end(1):]
    return body


def _load_songs(db) -> list[_SongLyrics]:
    from sqlalchemy import select

    from app.db.models import Album, Song

    rows = db.execute(
        select(Song.title, Album.title, Album.year, Song.lyrics_clean)
        .join(Album, Song.album_id == Album.id)
    ).all()
    out: list[_SongLyrics] = []
    for title, album, year, lyrics in rows:
        ln = normalize(lyrics or "")
        out.append(_SongLyrics(
            title=title or "", album=album or "", year=int(year or 0),
            lyrics_norm=ln, has_lyrics=bool(ln),
        ))
    return out


_EXTERNAL_VERSES: list[str] | None = None


def _external_verses() -> list[str]:
    """Versos externos verificados a mano (colaboraciones fuera del corpus)."""
    global _EXTERNAL_VERSES
    if _EXTERNAL_VERSES is not None:
        return _EXTERNAL_VERSES
    verses: list[str] = []
    try:
        import yaml
        p = Path(__file__).resolve().parents[2] / "data" / "external_verses.yaml"
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            for item in (data.get("versos") or []):
                text = item.get("verso") if isinstance(item, dict) else str(item)
                if text:
                    verses.append(normalize(text))
    except Exception as exc:  # nunca romper el gate por el YAML
        logger.warning("no se pudo leer external_verses.yaml: %s", exc)
    _EXTERNAL_VERSES = verses
    return verses


def _in_external(quote_norm: str) -> bool:
    return any(best_ratio(quote_norm, v) >= _OK_RATIO or quote_norm in v
              for v in _external_verses())


def check_lyrics(db, body_md: str) -> LyricGuardReport:
    """Verifica todas las citas de letra del cuerpo contra el corpus real.

    Determinista, sin LLM. Solo mira citas presentadas como VERSO de una canción
    (título de canción cercano o palabra-indicador tipo 'canta/verso/estribillo').
    Las citas de entrevistas/declaraciones (sin canción cercana) no son asunto de
    este guardia."""
    songs = _load_songs(db)
    by_title = {normalize(s.title): s for s in songs}
    titles_norm = list(by_title.keys())
    with_lyrics = [s for s in songs if s.has_lyrics]
    # Títulos (canción + álbum) para descartar citas que son NOMBRES de obra, no
    # versos ("Destrozares, Canciones para el Final de los Tiempos" es un disco).
    title_set = set(titles_norm) | {normalize(s.album) for s in songs if s.album}
    title_tok = {t: frozenset(t.split()) for t in title_set}

    # Para localizar menciones de canción usamos el body con las URLs de los
    # enlaces enmascaradas (mismo largo → posiciones intactas), de modo que un slug
    # dentro de una URL no cuente como mención y no falsee la atribución.
    body_norm, norm_map = _norm_positions(_mask_link_urls(body_md))
    # posición-original → índice en el body normalizado (para localizar menciones)
    orig_to_norm: dict[int, int] = {}
    for ni, oi in enumerate(norm_map):
        orig_to_norm.setdefault(oi, ni)
    title_occ = _title_occurrences(body_norm, titles_norm)

    report = LyricGuardReport()
    for quote, start in extract_quotes(body_md):
        q_norm = normalize(quote)
        q_words = q_norm.split()
        if len(q_words) < _MIN_QUOTE_WORDS:
            continue
        q_tokens = set(q_words)
        # ¿la cita es en realidad el TÍTULO de una obra (canción o disco)? Se está
        # citando el nombre, no un verso → no aplica. Exacto primero, luego fuzzy
        # solo sobre títulos con solapamiento de palabras (rápido).
        if q_norm in title_set or any(
            best_ratio(q_norm, t) >= 0.9
            for t, tk in title_tok.items() if _overlap(q_tokens, tk) >= 0.6
        ):
            continue

        # Canción atribuida: la mención de título más cercana ANTES de la cita.
        start_norm = orig_to_norm.get(start)
        if start_norm is None:
            # buscar la posición normalizada más próxima
            cand = [orig_to_norm[o] for o in orig_to_norm if o <= start]
            start_norm = max(cand) if cand else 0
        before = [(p, t) for (p, t) in title_occ if p <= start_norm]
        attributed = None
        if before:
            p, t = max(before, key=lambda x: x[0])
            # solo si está razonablemente cerca (misma frase/párrafo)
            approx_chars = start_norm - p
            if approx_chars <= _ATTRIB_WINDOW:
                attributed = t

        pre_context = body_md[max(0, start - _ATTRIB_WINDOW):start]
        is_lyricish = attributed is not None or bool(_LYRIC_HINT.search(pre_context))
        if not is_lyricish:
            continue  # cita no ligada a canción → no es asunto del guardia de letra

        attr_song = by_title.get(attributed) if attributed else None

        # Canción atribuida SIN letra en el corpus → cita literal no verificable.
        if attr_song is not None and not attr_song.has_lyrics:
            if _in_external(q_norm):
                report.verdicts.append(LyricVerdict(
                    quote=quote, status="ok", attributed_song=attr_song.title,
                    reason="verso externo verificado a mano"))
            else:
                report.verdicts.append(LyricVerdict(
                    quote=quote, status="no_lyrics", attributed_song=attr_song.title,
                    reason=(f"«{attr_song.title}» no tiene letra en el corpus; no se "
                            f"puede verificar la cita. Parafrasea en vez de entrecomillar.")))
            continue

        # Match contra la canción atribuida (si la tiene con letra).
        r_attr = 0.0
        if attr_song and _overlap(q_tokens, attr_song.tokens) >= 0.5:
            r_attr = best_ratio(q_norm, attr_song.lyrics_norm)
        if r_attr >= _OK_RATIO:
            report.verdicts.append(LyricVerdict(
                quote=quote, status="ok", attributed_song=attr_song.title,
                matched_song=attr_song.title, ratio=r_attr))
            continue

        # Barrido de todo el corpus: ¿de qué canción es realmente el verso?
        # Pre-filtro por solapamiento de palabras (SEGURO: si el verso está en una
        # canción, todas sus palabras están → no se poda) para no hacer el fuzzy
        # caro sobre las 144 canciones en cada cita.
        best_song: _SongLyrics | None = None
        best_r = 0.0
        for s in with_lyrics:
            if _overlap(q_tokens, s.tokens) < 0.5:
                continue
            r = best_ratio(q_norm, s.lyrics_norm)
            if r > best_r:
                best_r, best_song = r, s
                if best_r >= 0.999:
                    break

        if best_r >= _OK_RATIO:
            best_norm = normalize(best_song.title) if best_song else ""
            # ¿La canción CORRECTA está referenciada (nombrada o ENLAZADA) junto al
            # verso? El enlace interno la ancla aunque la 'mención más cercana' en
            # prosa apunte a otra: entonces NO es misatribución, está bien citada.
            near = normalize(body_md[max(0, start - 450):start + len(quote) + 450])
            referenced = bool(best_norm) and best_norm in near
            if attributed and best_song and best_norm != attributed \
                    and r_attr < _REVIEW_RATIO and not referenced:
                report.verdicts.append(LyricVerdict(
                    quote=quote, status="misattributed",
                    attributed_song=attr_song.title if attr_song else attributed,
                    matched_song=best_song.title, matched_album=best_song.album,
                    matched_year=best_song.year, ratio=best_r,
                    reason=(f"el verso es de «{best_song.title}» "
                            f"({best_song.album}, {best_song.year}), no de la canción citada")))
            else:
                report.verdicts.append(LyricVerdict(
                    quote=quote, status="ok",
                    attributed_song=attr_song.title if attr_song else None,
                    matched_song=best_song.title if best_song else None, ratio=best_r))
            continue

        if max(r_attr, best_r) >= _REVIEW_RATIO:
            report.verdicts.append(LyricVerdict(
                quote=quote, status="review",
                attributed_song=attr_song.title if attr_song else attributed,
                matched_song=best_song.title if best_song else None,
                ratio=max(r_attr, best_r),
                reason="coincidencia parcial con la letra; revisar a mano"))
            continue

        # Nada: ni la canción atribuida ni ninguna del corpus contiene el verso.
        report.verdicts.append(LyricVerdict(
            quote=quote, status="fabricated",
            attributed_song=attr_song.title if attr_song else attributed,
            ratio=max(r_attr, best_r),
            reason="el verso no aparece en la letra atribuida ni en ninguna canción del corpus"))

    return report
