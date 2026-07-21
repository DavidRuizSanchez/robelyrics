"""Validación factual del contenido generado (blog + SEO + auditoría).

Motivo: el LLM alucina hechos concretos (atribuyó "La vereda de la puerta de
atrás" al disco Agila de 1996 cuando es de "Yo, Minoría Absoluta" de 2002;
inventó un libro de Robe que no existe). Este módulo es la red de seguridad
TRANSVERSAL: extrae las afirmaciones factuales de alto riesgo de un texto, las
resuelve en CASCADA contra fuentes de verdad y corrige lo que esté mal.

Cascada de verdad (corta en cuanto un nivel confirma/refuta):
  1. BD (determinista, sin LLM): discografía (Song→Album→year/Artist) y libros
     (Book). Es la verdad canónica del catálogo. Aquí se caza el bug de "La
     vereda…": canción→álbum no coincide → refuted + valor correcto.
  2. Corpus: fan-content destilado + fuentes + digests de libros. Confirma;
     rara vez refuta.
  3. Web: `web_verify.verify_fact` (Wikipedia + Google + juez, ya cacheado).

Consumidores:
  - Blog (`scripts.blog.materialize_proposals`): gate pre-publicación.
  - SEO (`scripts.seo.common.call_llm`): puente opcional con `db`.
  - Auditoría retroactiva (`scripts.audit.fact_audit`): corrige lo ya publicado.

Filosofía heredada del proyecto: ante la duda, NO se confirma; mejor un dato
omitido que uno inventado. La corrección preserva voz, opinión, encabezados,
enlaces markdown y versos citados — solo toca el hecho no respaldado.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"

ClaimType = Literal[
    "song_album",   # "X" pertenece al disco "Y"   (canónico en BD)
    "song_year",    # "X" es de 19XX/20XX          (canónico en BD)
    "album_year",   # disco "Y" salió en 20XX       (canónico en BD)
    "work_exists",  # existencia de una obra (libro/disco/canción/película)
    "person_fact",  # persona, formación, colaboración, premio
    "date_event",   # fecha de un evento (concierto, gira, fallecimiento)
    "other",        # cualquier otro hecho concreto verificable
]
Status = Literal["confirmed", "refuted", "unverifiable"]
Risk = Literal["high", "medium"]


# --------------------------------------------------------------------------- #
# Tipos
# --------------------------------------------------------------------------- #
@dataclass
class Claim:
    text: str                      # afirmación autocontenida tal como la entiende el LLM
    type: ClaimType
    quote: str = ""                # substring LITERAL del body que la ancla
    subject: str = ""              # entidad principal (canción/disco/persona/obra)
    object: str = ""               # valor afirmado (álbum/año/…)
    risk: Risk = "high"


@dataclass
class Verdict:
    claim: Claim
    status: Status
    correct_value: str | None = None   # valor canónico cuando refuted y hay reemplazo
    correct_year: str | None = None    # año canónico asociado (para song_album: año del álbum real)
    evidence: str = ""
    source: str = ""                   # "db" | "corpus" | "wikipedia" | "google" | ""


@dataclass
class FactCheckReport:
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Limpio = nada que auto-corregir y nada que mandar a revisión."""
        return not self.autofixes and not self.to_review

    @property
    def autofixes(self) -> list[Verdict]:
        """SOLO contradicciones canónicas de BD (canción↔álbum↔año): verdad dura,
        determinista, cero falsos positivos. Es lo único que se auto-corrige
        in-place. La verificación web NUNCA auto-borra (genera falsos positivos
        sobre noticias); solo señala para revisión."""
        return [v for v in self.verdicts if v.status == "refuted" and v.source == "db"]

    @property
    def to_review(self) -> list[Verdict]:
        """Candidatos a revisión HUMANA detectados por la web (refutados o no
        verificables de alto riesgo). NO se tocan automáticamente."""
        return [v for v in self.verdicts if v.source == "web" and (
            v.status == "refuted"
            or (v.status == "unverifiable" and v.claim.risk == "high")
        )]

    @property
    def corrections(self) -> list[Verdict]:
        """Todo lo que rompe la limpieza (auto-corregible + a revisar)."""
        return self.autofixes + self.to_review

    def summary(self) -> str:
        n = len(self.verdicts)
        return (f"{n} afirmaciones · {len(self.autofixes)} a corregir · "
                f"{len(self.to_review)} a revisar")


# --------------------------------------------------------------------------- #
# Normalización (local, sin dependencias de otros módulos para evitar ciclos)
# --------------------------------------------------------------------------- #
def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    )


_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "«": '"', "»": '"'})


def _norm(s: str) -> str:
    """Minúsculas sin acentos, comillas normalizadas, artículo inicial fuera y
    espacios colapsados. Para casar títulos de forma robusta."""
    s = _strip_accents((s or "").translate(_QUOTES)).lower()
    s = s.strip().strip('"').strip("'").strip()
    s = re.sub(r'^(el|la|los|las)\s+', "", s)
    s = re.sub(r"[^a-z0-9ñ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _title_matches(a: str, b: str) -> bool:
    """¿Dos títulos designan la misma obra? Tolera nombre corto vs largo con
    subtítulo: «Destrozares» ≡ «Destrozares, Canciones para el Final de los
    Tiempos» (uno es prefijo de palabras del otro). Evita refutar por usar el
    nombre coloquial de un disco."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    wa, wb = na.split(), nb.split()
    shorter, longer = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return len(shorter) >= 1 and longer[:len(shorter)] == shorter


# Contexto de un año que NO es el de lanzamiento original (grabación, composición,
# reedición, remasterización, gira…): no debe usarse para refutar el año del disco
# ("grabado en 2019, lanzado en 2021"; "la reedición de Rock Transgresivo en 1994").
_RECORDING_RE = re.compile(
    r"grab|compu|escrib|sesion|maquet|ensay|produc|mezcl|gest|"
    r"reedi|reedit|remaster|remasteriz|relanz|reissue|gira|directo|en vivo|aniversari",
    re.I,
)


# --------------------------------------------------------------------------- #
# Índice de catálogo (verdad dura de BD) — cacheable entre items en auditoría
# --------------------------------------------------------------------------- #
@dataclass
class _SongRef:
    album_title: str
    album_year: int
    artist: str
    kind: str  # studio|live|compilation|ep
    # Primera aparición canónica (la fija catalog_consensus en Song). Cuando está,
    # manda sobre el álbum/año de esta fila (evita que un recopilatorio enmascare
    # la verdad: caso "Amor castúo" atribuida a un disco en directo).
    original_album_slug: str | None = None
    original_year: int | None = None


@dataclass
class CatalogIndex:
    songs: dict[str, list[_SongRef]]   # norm(title) -> refs (puede haber versiones)
    albums: dict[str, int]             # norm(title) -> year
    album_titles: set[str]             # norm(title) presentes
    album_kind: dict[str, str]         # norm(title) -> kind (studio|live|compilation|ep)
    album_url: dict[str, str]          # norm(title) -> "/{artist_slug}/{album_slug}"
    album_display: dict[str, str]      # norm(title) -> título original (con signos)
    book_titles: set[str]              # norm(title) presentes

    def url_for_album(self, title: str) -> str | None:
        u = self.album_url.get(_norm(title))
        if u:
            return u
        for an, url in self.album_url.items():
            if _title_matches(title, an):
                return url
        return None

    def is_live_album(self, title: str) -> bool:
        """¿El álbum es en directo/recopilatorio? Una canción puede aparecer en
        él además de en su disco de estudio (relación 1→N que la BD no modela)."""
        kind = self.album_kind.get(_norm(title))
        if kind in ("live", "compilation"):
            return True
        for an, k in self.album_kind.items():
            if k in ("live", "compilation") and _title_matches(title, an):
                return True
        return False

    def _fuzzy_song_key(self, n: str) -> str | None:
        """Clave de canción más parecida al título normalizado `n` (difflib).
        Tolera variantes triviales del título que rompen el lookup exacto, p.ej.
        «Ama, ama y ensancha el alma» (2 «ama») vs la del catálogo «Ama, Ama, Ama
        y Ensancha el Alma» (3 «ama»). Umbral alto (0.9) para no confundir canciones
        distintas de título parecido."""
        if not n:
            return None
        best, bestr = None, 0.0
        for k in self.songs:
            r = difflib.SequenceMatcher(None, n, k).ratio()
            if r > bestr:
                best, bestr = k, r
        return best if bestr >= 0.9 else None

    def refs_for_song(self, title: str) -> list[_SongRef]:
        """Referencias de una canción: lookup exacto y, si falla, fuzzy tolerante."""
        refs = self.songs.get(_norm(title))
        if refs:
            return refs
        key = self._fuzzy_song_key(_norm(title))
        return self.songs.get(key, []) if key else []

    def album_for_song(self, title: str, artist: str | None = None) -> _SongRef | None:
        """Mejor referencia para una canción: prioriza la primera aparición canónica
        (Song.original_*), luego el álbum de estudio más antiguo. Si se pasa `artist`,
        NO mezcla proyectos (Robe solista vs Extremoduro) cuando hay homónimas."""
        refs = self.refs_for_song(title)
        if artist:
            an = _norm(artist)
            same = [r for r in refs if _norm(r.artist) == an]
            refs = same or refs
        if not refs:
            return None
        # 1) primera aparición canónica fijada por catalog_consensus
        canonical = [r for r in refs if r.original_year]
        if canonical:
            return sorted(canonical, key=lambda r: r.original_year)[0]
        # 2) álbum de estudio más antiguo
        studio = [r for r in refs if r.kind == "studio"]
        pool = studio or refs
        return sorted(pool, key=lambda r: r.album_year)[0]


def build_catalog_index(db: Session) -> CatalogIndex:
    """Construye el índice canción/álbum/libro desde BD. Una sola pasada."""
    from app.db.models import Album, Artist, Book, Song

    songs: dict[str, list[_SongRef]] = {}
    rows = db.execute(
        select(
            Song.title, Album.title, Album.year, Album.kind, Artist.name,
            Song.original_album_slug, Song.original_year,
        )
        .join(Album, Song.album_id == Album.id)
        .join(Artist, Album.artist_id == Artist.id)
    ).all()
    for song_title, album_title, year, kind, artist, orig_slug, orig_year in rows:
        ref = _SongRef(
            album_title or "", int(year or 0), artist or "", kind or "studio",
            original_album_slug=orig_slug, original_year=orig_year,
        )
        songs.setdefault(_norm(song_title), []).append(ref)

    albums: dict[str, int] = {}
    album_titles: set[str] = set()
    album_kind: dict[str, str] = {}
    album_url: dict[str, str] = {}
    album_display: dict[str, str] = {}
    for title, year, kind, aslug, artslug in db.execute(
        select(Album.title, Album.year, Album.kind, Album.slug, Artist.slug)
        .join(Artist, Album.artist_id == Artist.id)
    ).all():
        n = _norm(title)
        albums[n] = int(year or 0)
        album_titles.add(n)
        album_kind[n] = kind or "studio"
        album_display[n] = title or ""
        if aslug and artslug:
            album_url[n] = f"/{artslug}/{aslug}"

    book_titles = {_norm(t) for (t,) in db.execute(select(Book.title)).all()}

    return CatalogIndex(
        songs=songs, albums=albums, album_titles=album_titles,
        album_kind=album_kind, album_url=album_url, album_display=album_display,
        book_titles=book_titles,
    )


# --------------------------------------------------------------------------- #
# 1. Extracción de afirmaciones (LLM, structured output)
# --------------------------------------------------------------------------- #
_EXTRACT_SYS = (
    "Eres un extractor de AFIRMACIONES FACTUALES VERIFICABLES de un texto sobre "
    "Extremoduro y Robe (Roberto Iniesta). Te doy un ARTÍCULO en markdown y "
    "devuelves SOLO los hechos concretos y comprobables que afirma, NO la "
    "opinión ni la interpretación.\n\n"
    "INCLUYE solo hechos como: a qué disco pertenece una canción (song_album), "
    "el año de una canción (song_year) o de un disco (album_year), la existencia "
    "de una obra concreta —libro, disco, película, canción— (work_exists), datos "
    "de personas/formaciones/colaboraciones/premios (person_fact), fechas de "
    "eventos (date_event), u otros hechos concretos (other).\n\n"
    "IMPORTANTE sobre años: song_year/album_year se refieren SIEMPRE al año de "
    "LANZAMIENTO o publicación ('salió en', 'se publicó en', 'de 1996'). Un año "
    "de GRABACIÓN, composición, escritura o sesiones ('grabado en 2019') NO es "
    "song_year/album_year: si aparece, clasifícalo como 'other' o no lo incluyas. "
    "Usa el TÍTULO de la obra tal como aparece en el texto (no lo expandas).\n\n"
    "NO incluyas (deja fuera): opiniones, lecturas interpretativas, sensaciones, "
    "metáforas, valoraciones estéticas, frases poéticas, ni VERSOS o letras "
    "citados entre comillas o en blockquote. Si una frase no es un hecho que se "
    "pueda comprobar en una enciclopedia, NO la incluyas.\n\n"
    "Para cada afirmación devuelve: text (el hecho redactado de forma "
    "autocontenida), type (uno de los tipos), quote (un substring EXACTO y "
    "literal del artículo, copiado tal cual, que contiene el hecho — "
    "imprescindible, sin parafrasear), subject (la entidad principal: título de "
    "la canción/obra, nombre de la persona…), object (el valor afirmado: nombre "
    "del disco, año…), risk ('high' si es un dato muy concreto y comprometido "
    "—título de disco, año, existencia de una obra—, 'medium' si es secundario).\n"
    "Devuelve SOLO JSON: {\"claims\": [ {…}, … ]}. Si no hay hechos comprobables, "
    "{\"claims\": []}."
)


def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurado")
    return OpenAI(api_key=api_key)


def extract_claims(body_md: str, *, max_claims: int = 12, client: OpenAI | None = None) -> list[Claim]:
    """Extrae hasta `max_claims` afirmaciones factuales del texto. Degrada a []."""
    if not body_md or not body_md.strip():
        return []
    try:
        cli = client or _client()
        resp = cli.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _EXTRACT_SYS},
                {"role": "user", "content": f"ARTÍCULO:\n\"\"\"{body_md[:12000]}\"\"\""},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fact_check] extracción falló: %s", exc)
        return []

    out: list[Claim] = []
    for raw in (data.get("claims") or [])[:max_claims]:
        if not isinstance(raw, dict):
            continue
        ctype = raw.get("type") or "other"
        if ctype not in (
            "song_album", "song_year", "album_year", "work_exists",
            "person_fact", "date_event", "other",
        ):
            ctype = "other"
        def _s(key: str) -> str:
            val = raw.get(key)
            return str(val).strip() if val is not None else ""
        text = _s("text")
        if not text:
            continue
        out.append(Claim(
            text=text,
            type=ctype,  # type: ignore[arg-type]
            quote=_s("quote"),
            subject=_s("subject"),
            object=_s("object"),
            risk="medium" if raw.get("risk") == "medium" else "high",
        ))
    return out


# --------------------------------------------------------------------------- #
# 2. Resolución en cascada
# --------------------------------------------------------------------------- #
_YEAR_RE = re.compile(r"\b((?:18|19|20)\d{2})\b")


def _year_in(text: str) -> int | None:
    m = _YEAR_RE.search(text or "")
    return int(m.group(1)) if m else None


def _year_near_title(quote: str, title: str, year: int, window: int = 30) -> bool:
    """¿El año está PEGADO al título en la frase? Distingue una atribución de año
    de lanzamiento ("Pedrá (1995)") de un año de evento lejano ("En 1993 se
    unió… que culminaría en Pedrá"). Conservador: si no puede comprobarlo, False."""
    if not quote:
        return False
    q = _strip_accents(quote).lower()
    ys = str(year)
    yi = q.find(ys)
    if yi < 0:
        return False
    t = _strip_accents(title).lower().strip().strip('"').strip("'")
    ti = q.find(t)
    if ti < 0:
        frag = t[:15]
        ti = q.find(frag) if len(frag) >= 6 else -1
    if ti < 0:
        return False
    tlen = min(len(t), 15) if q.find(t) < 0 else len(t)
    dist = (yi - (ti + tlen)) if yi >= ti else (ti - (yi + len(ys)))
    return dist <= window


def _resolve_db(index: CatalogIndex, claim: Claim) -> Verdict | None:
    """Nivel 1 — verdad canónica de BD. Devuelve None si BD no aplica/no decide."""
    if claim.type == "song_album":
        ref = index.album_for_song(claim.subject)
        if ref is None:
            return None  # canción no está en el catálogo → niveles siguientes
        refs = index.refs_for_song(claim.subject)
        if any(_title_matches(claim.object, r.album_title) for r in refs):
            return Verdict(claim, "confirmed", evidence=f"{claim.subject} ∈ {ref.album_title}", source="db")
        # GUARD anti-falso-positivo: solo es una atribución de álbum ERRÓNEA si el
        # `object` afirmado es REALMENTE un álbum del catálogo. Si no lo es (el
        # texto mencionaba la banda "Extremoduro"/"Robe", un año, o un verso), el
        # extractor se confundió: no hay error de álbum que corregir.
        object_is_album = any(_title_matches(claim.object, a) for a in index.album_titles)
        if not object_is_album:
            return None
        # GUARD discos EN DIRECTO/recopilatorios: una canción aparece legítimamente
        # en un disco en vivo además de en su álbum de estudio (la BD solo modela
        # el de estudio). Si el álbum afirmado es live/compilation, NO es un error.
        if index.is_live_album(claim.object):
            return None
        return Verdict(
            claim, "refuted", correct_value=ref.album_title,
            correct_year=str(ref.album_year) if ref.album_year else None,
            evidence=f'"{claim.subject}" pertenece a «{ref.album_title}» ({ref.album_year}), no a «{claim.object}»',
            source="db",
        )

    if claim.type == "song_year":
        refs = index.refs_for_song(claim.subject)
        if not refs:
            return None
        claimed = _year_in(claim.object) or _year_in(claim.text)
        if claimed is None:
            return None
        real_years = {r.album_year for r in refs if r.album_year}
        if claimed in real_years:
            return Verdict(claim, "confirmed", evidence=f"{claim.subject}: {claimed}", source="db")
        if _RECORDING_RE.search(claim.quote or claim.text):
            return None  # año de grabación/composición, no de lanzamiento → no refutar
        ref = index.album_for_song(claim.subject)
        correct = str(ref.album_year) if ref and ref.album_year else None
        return Verdict(
            claim, "refuted", correct_value=correct,
            evidence=f'"{claim.subject}" es de {correct or "otro año"}, no de {claimed}',
            source="db",
        )

    if claim.type == "album_year":
        year = _album_year_lookup(index, claim.subject)
        if year is None:
            return None
        claimed = _year_in(claim.object) or _year_in(claim.text)
        if claimed is None:
            return None
        if claimed == year:
            return Verdict(claim, "confirmed", evidence=f"{claim.subject}: {year}", source="db")
        if _RECORDING_RE.search(claim.quote or claim.text):
            return None  # "grabado en X / lanzado en Y": el año de grabación no refuta
        # GUARD año-de-evento: si el año afirmado está LEJOS del título en la frase
        # (p.ej. "En 1993 Selu se unió… que culminaría en Pedrá"), probablemente es
        # el año de un evento, no del lanzamiento → no refutar.
        if not _year_near_title(claim.quote, claim.subject, claimed):
            return None
        return Verdict(
            claim, "refuted", correct_value=str(year),
            evidence=f'«{claim.subject}» es de {year}, no de {claimed}', source="db",
        )

    if claim.type == "work_exists":
        n = _norm(claim.subject)
        if not n:
            return None
        known = list(index.book_titles) + list(index.album_titles) + list(index.songs.keys())
        if any(_title_matches(claim.subject, t) for t in known):
            return Verdict(claim, "confirmed", evidence=f"«{claim.subject}» existe en el catálogo", source="db")
        return None  # no está en BD: no se puede afirmar inexistencia desde aquí → web

    return None


def _album_year_lookup(index: CatalogIndex, title: str) -> int | None:
    """Año de un álbum por título, con tolerancia a nombre corto/largo."""
    n = _norm(title)
    if n in index.albums:
        return index.albums[n]
    for an, yr in index.albums.items():
        if _title_matches(title, an):
            return yr
    return None


def _resolve_web(claim: Claim) -> Verdict:
    """Nivel 3 — Wikipedia/Google con juez de 3 estados (cacheado).

    Distingue 'contradicho' (evidencia de falsedad → refutar) de 'no encontrado'
    (ausencia de información → no tocar, salvo el caso especial de obras). Así no
    se borran datos reales de noticias locales que la web no indexa.
    """
    try:
        from app.services.web_verify import classify_fact
        res = classify_fact(claim.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[fact_check] classify_fact falló: %s", exc)
        return Verdict(claim, "unverifiable", evidence="verificación web no disponible")

    verdict = res.get("verdict")
    ev = res.get("evidence", "")
    if verdict == "supported":
        return Verdict(claim, "confirmed", evidence=ev, source="wikipedia")
    if verdict == "contradicted":
        return Verdict(claim, "refuted", evidence=ev or "la evidencia externa lo contradice", source="web")
    # not_found: caso especial — una OBRA (libro/disco) atribuida a un artista
    # tan conocido sería googleable; su ausencia total es señal fuerte de
    # invención, así que se refuta. Para hechos de persona/evento/otros, la
    # ausencia NO basta para borrar: queda como no verificable (a revisar).
    if claim.type == "work_exists":
        return Verdict(claim, "refuted", evidence=ev or "sin rastro de esta obra en fuentes externas", source="web")
    return Verdict(claim, "unverifiable", evidence=ev or "sin respaldo claro", source="web")


def resolve_claim(
    db: Session, claim: Claim, *, index: CatalogIndex | None = None, use_web: bool = True
) -> Verdict:
    """Resuelve un claim en cascada: BD (verdad dura) → web (asistida).

    `use_web`: si False, los claims no cubiertos por BD quedan como
    'unverifiable/skipped' (sin gastar llamadas ni señalar revisión). La
    auditoría masiva usa False por defecto (auto-corrige solo lo canónico, gratis
    e instantáneo); con --web añade la capa de revisión externa.
    """
    idx = index or build_catalog_index(db)
    db_verdict = _resolve_db(idx, claim)
    if db_verdict is not None:
        return db_verdict
    if not use_web:
        return Verdict(claim, "unverifiable", evidence="no verificado (web desactivada)", source="skipped")
    return _resolve_web(claim)


# --------------------------------------------------------------------------- #
# 2b. Extractor DETERMINISTA de atribuciones canción→álbum (sin LLM)
# --------------------------------------------------------------------------- #
# Frase que atribuye una canción a un disco ("«X», del álbum «Y»"). Sobre texto
# ya normalizado (sin acentos, minúsculas).
_ATTRIB_ALBUM_RE = re.compile(
    r"\b(?:del|en el|de su|dentro del|incluid[ao]s? en el|"
    r"perteneciente al|que forma parte del)\s+"
    r"(?:album|disco|lp|elepe|trabajo|placa|disco de estudio)\b"
)


def _norm_view(body: str) -> tuple[str, list[int]]:
    """Body normalizado (minúsculas, sin acentos, puntuación→espacio, espacios
    colapsados) + mapa índice-normalizado → índice-original, para recuperar el
    substring original de cualquier coincidencia."""
    src = _strip_accents((body or "").translate(_QUOTES)).lower()
    chars: list[str] = []
    imap: list[int] = []
    prev_space = False
    for i, ch in enumerate(src):
        c = ch if re.match(r"[a-z0-9ñ ]", ch) else " "
        if c == " ":
            if prev_space:
                continue
            prev_space = True
        else:
            prev_space = False
        chars.append(c)
        imap.append(i)
    return "".join(chars), imap


def _catalog_occ(norm: str, keys: list[str]) -> list[tuple[int, int, str]]:
    """Ocurrencias (inicio, fin, clave) de títulos del catálogo en el texto
    normalizado, del más largo al más corto para no casar uno dentro de otro."""
    occ: list[tuple[int, int, str]] = []
    for t in sorted(set(keys), key=len, reverse=True):
        if len(t) < 3:
            continue
        for m in re.finditer(r"(?<![a-z0-9ñ])" + re.escape(t) + r"(?![a-z0-9ñ])", norm):
            occ.append((m.start(), m.end(), t))
    return occ


def extract_catalog_claims(body_md: str, index: CatalogIndex) -> list[Claim]:
    """Extractor DETERMINISTA de atribuciones canción→álbum explícitas, para no
    depender de que el LLM pesque el error (caso real: «Ama, ama y ensancha el
    alma», del álbum «¿Dónde están mis amigos?» — es de «Deltoya»).

    Alta precisión: se ancla en la frase de atribución ('del álbum …'), coge el
    álbum del catálogo que la sigue y la canción ENTRECOMILLADA que la precede,
    resuelve la canción de forma fuzzy y emite un claim solo si el álbum afirmado
    NO es el real (ni un directo/recopilatorio donde también aparece)."""
    norm, imap = _norm_view(body_md)
    albums_occ = _catalog_occ(norm, list(index.album_titles))
    claims: list[Claim] = []
    seen: set[tuple[str, str]] = set()
    for m in _ATTRIB_ALBUM_RE.finditer(norm):
        alb = next(((a0, a1, ak) for (a0, a1, ak) in albums_occ
                    if m.end() <= a0 <= m.end() + 40), None)
        if not alb:
            continue
        a0, a1, akey = alb
        # Canción: entrecomillado más cercano ANTES de la frase de atribución.
        back = body_md[max(0, imap[m.start()] - 130):imap[m.start()]].translate(_QUOTES)
        qs = re.findall(r'"([^"\n]{3,80})"', back)
        if not qs:
            continue
        song_txt = qs[-1].strip()
        skey = index._fuzzy_song_key(_norm(song_txt))
        if not skey:
            continue
        refs = index.songs.get(skey) or []
        if any(_title_matches(akey, r.album_title) for r in refs):
            continue  # atribución correcta
        if index.is_live_album(akey):
            continue  # directo/recopilatorio: no es error
        # Título canónico (con signos ¿?/¡!) para que el reemplazo case entero y
        # no deje restos ("¿Deltoya?"); si no está, el substring recuperado.
        alb_orig = index.album_display.get(akey) or body_md[imap[a0]:imap[a1 - 1] + 1]
        key = (skey, akey)
        if key in seen:
            continue
        seen.add(key)
        claims.append(Claim(
            text=f'"{song_txt}" pertenece al álbum "{alb_orig}"',
            type="song_album", quote=song_txt, subject=song_txt,
            object=alb_orig, risk="high",
        ))
    return claims


# --------------------------------------------------------------------------- #
# 3. check_body / correct_body
# --------------------------------------------------------------------------- #
def check_body(
    db: Session,
    body_md: str,
    *,
    material: str = "",
    max_claims: int = 12,
    index: CatalogIndex | None = None,
    client: OpenAI | None = None,
    use_web: bool = True,
) -> FactCheckReport:
    """Extrae las afirmaciones del texto y las resuelve en cascada.

    Combina DOS extractores: el LLM (amplio) y uno DETERMINISTA de atribuciones
    canción→álbum (`extract_catalog_claims`), para que un error de disco no
    dependa de que el LLM lo pesque. Se deduplica por (tipo, canción, álbum)."""
    idx = index or build_catalog_index(db)
    claims = extract_claims(body_md, max_claims=max_claims, client=client)
    det = extract_catalog_claims(body_md, idx)
    seen = {(c.type, _norm(c.subject), _norm(c.object)) for c in claims}
    for c in det:
        key = (c.type, _norm(c.subject), _norm(c.object))
        if key not in seen:
            claims.append(c)
            seen.add(key)
    if not claims:
        return FactCheckReport(verdicts=[])
    verdicts = [resolve_claim(db, c, index=idx, use_web=use_web) for c in claims]
    return FactCheckReport(verdicts=verdicts)


def _enforce_album_year(body_md: str, album_title: str, year: str) -> str:
    """Corrige un año equivocado pegado al título de un álbum (tras reescribir la
    atribución de una canción). Tolera un enlace markdown `](url)` entre el título
    y el año ("[Album](url) de 1996"). Solo toca un año contiguo; no reescribe."""
    # Tolera, entre el título y el año: cierre de enlace markdown `](url)` y/o
    # marcas de cursiva/negrita `*`/`_` ("*[Album](url)* de 1996").
    pat = re.compile(
        re.escape(album_title)
        + r"((?:\]\([^)]*\))?[*_]{0,2})(\s+de\s+|\s*\(\s*)((?:18|19|20)\d{2})"
    )

    def _sub(m: re.Match) -> str:
        if m.group(3) == year:
            return m.group(0)
        return album_title + (m.group(1) or "") + m.group(2) + year

    return pat.sub(_sub, body_md)


def _anchor_positions(body: str, anchor: str) -> list[int]:
    if not anchor:
        return [0]
    pos = [m.start() for m in re.finditer(re.escape(anchor), body, re.IGNORECASE)]
    return pos or [0]


def _replace_album_near(
    body: str, song: str, wrong_album: str, right_album: str,
    right_url: str | None, right_year: str | None, window: int = 240,
) -> tuple[str, bool]:
    """Reemplaza QUIRÚRGICAMENTE la mención al álbum equivocado por el correcto, en
    la ocurrencia más cercana al nombre de la canción. Maneja enlace markdown
    `[álbum](url)`, cursiva `*álbum*` y texto plano. No reescribe nada más.
    Devuelve (body, aplicado)."""
    if not wrong_album:
        return body, False
    occ = [(m.start(), m.end()) for m in re.finditer(re.escape(wrong_album), body, re.IGNORECASE)]
    if not occ:
        return body, False
    # SALVAGUARDA de ambigüedad: si el álbum afirmado aparece varias veces Y la
    # canción también, no se puede saber con certeza qué ocurrencia corregir sin
    # romper una mención legítima (caso el-abismo: "La ley innata" sale 3 veces,
    # unas erróneas y otras válidas). Mejor a revisión humana que romper.
    n_song = len(re.findall(re.escape(song), body, re.IGNORECASE)) if song else 1
    if len(occ) >= 2 and n_song >= 2:
        return body, False
    anchors = _anchor_positions(body, song)
    occ.sort(key=lambda o: min(abs(o[0] - a) for a in anchors))
    s, e = occ[0]
    if min(abs(s - a) for a in anchors) > window:
        return body, False  # demasiado lejos de la canción → no fiable, a revisión
    # ¿está dentro de un enlace [texto](url)?
    for m in re.finditer(r"\[([^\]]*)\]\(([^)]*)\)", body):
        if m.start() <= s and e <= m.end():
            new_link = f"[{right_album}]({right_url})" if right_url else f"[{right_album}]({m.group(2)})"
            body = body[:m.start()] + new_link + body[m.end():]
            if right_year:
                body = _enforce_album_year(body, right_album, right_year)
            return body, True
    # texto plano o cursiva (los asteriscos quedan fuera de s..e)
    body = body[:s] + right_album + body[e:]
    if right_year:
        body = _enforce_album_year(body, right_album, right_year)
    return body, True


def _replace_year_near(
    body: str, anchor: str, old_year: str, new_year: str, window: int = 140,
) -> tuple[str, bool]:
    """Reemplaza el año erróneo por el correcto en la ocurrencia más cercana al
    título. Devuelve (body, aplicado)."""
    anchors = _anchor_positions(body, anchor)
    occ = [m.start() for m in re.finditer(r"\b" + re.escape(old_year) + r"\b", body)]
    if not occ:
        return body, False
    occ.sort(key=lambda p: min(abs(p - a) for a in anchors))
    p = occ[0]
    if anchors != [0] and min(abs(p - a) for a in anchors) > window:
        return body, False
    return body[:p] + new_year + body[p + len(old_year):], True


def correct_body(
    db: Session,
    body_md: str,
    report: FactCheckReport,
    *,
    index: CatalogIndex | None = None,
    material: str = "",      # aceptado por compatibilidad; el corrector no reescribe
    client: OpenAI | None = None,
) -> tuple[str, list[Verdict]]:
    """Corrección QUIRÚRGICA y 100% determinista: cambia SOLO el dato erróneo
    (texto y URL de enlaces markdown incluidos), acotado al contexto de la
    canción/título, y NUNCA reescribe la frase. Lo que no pueda corregir así de
    limpio NO se toca: se devuelve en `skipped` para revisión humana.

    Devuelve (body_corregido, skipped)."""
    idx = index or build_catalog_index(db)
    skipped: list[Verdict] = []
    for v in report.autofixes:
        c = v.claim
        applied = False
        if c.type == "song_album" and v.correct_value:
            url = idx.url_for_album(v.correct_value)
            body_md, applied = _replace_album_near(
                body_md, c.subject, c.object, v.correct_value, url, v.correct_year
            )
        elif c.type in ("song_year", "album_year") and v.correct_value:
            old = _year_in(c.object) or _year_in(c.text)
            if old is not None:
                body_md, applied = _replace_year_near(
                    body_md, c.subject, str(old), str(v.correct_value)
                )
        if not applied:
            skipped.append(v)
    return body_md, skipped


def check_and_correct(
    db: Session,
    body_md: str,
    *,
    material: str = "",
    index: CatalogIndex | None = None,
    client: OpenAI | None = None,
    use_web: bool = True,
) -> tuple[str, FactCheckReport]:
    """Conveniencia: verifica y auto-corrige lo canónico. Devuelve (body, report).

    Solo aplica los `autofixes` (BD). Los `to_review` (web) quedan en el report
    para que el caller decida (gate → revisión humana)."""
    report = check_body(db, body_md, material=material, index=index, client=client, use_web=use_web)
    if not report.autofixes:
        return body_md, report
    fixed, _skipped = correct_body(db, body_md, report, index=index, material=material, client=client)
    return fixed, report
