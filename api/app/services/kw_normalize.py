"""Normalización de keywords y guarda de PERTENENCIA al universo Robe/Extremoduro.

Dos trabajos distintos que conviene no mezclar:

1. **Normalizar** para poder deduplicar. Solo colapsa lo que es literalmente la
   misma cadena (`kw_norm`). Las variantes por orden de palabras
   («agila extremoduro» vs «extremoduro agila») NO se colapsan: DataForSEO les da
   volúmenes distintos y elegir uno obligaría a inventar cuál es el bueno. Se
   agrupan en `variant_group` y se muestran juntas.

2. **Decidir si una keyword es del universo.** Esto NO es un filtro de volumen.
   Se midió (01-08-2026) que `keyword_ideas` declara 954.756 keywords para un
   disco y que solo el 3,4% tocan a Extremoduro: el resto es ruido de categoría
   («1212 significado espiritual»). Sin esta guarda, «descargar todo» es
   descargar un vertedero.

El vocabulario sale de la BD, no de una lista a mano: un disco nuevo se reconoce
solo. Mismo criterio que `youtube_relevance.py`, incluida su cautela medida: los
títulos CORTOS solo casan como palabra completa, porque «salir» o «puta» dentro
de prosa arrastran medio diccionario.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Person, Song

# Umbral por debajo del cual un título solo casa como palabra completa.
# 10 caracteres porque «la ley innata» normaliza a «ley innata», que son
# exactamente 10 — el mismo número que ya usa youtube_relevance.
SHORT_TITLE_CHARS = 10

# Marca y alias del universo. Esto sí es fijo: son los nombres propios del
# proyecto, no catálogo que pueda crecer.
BRAND_TOKENS: frozenset[str] = frozenset({
    "extremoduro",
    "robe",
    "iniesta",
    "uoho",
    "extremoduros",  # error de tecleo frecuente en búsquedas reales
})

STOPWORDS_ES: frozenset[str] = frozenset({
    "a", "al", "ante", "con", "contra", "de", "del", "desde", "el", "en", "entre",
    "hacia", "hasta", "la", "las", "lo", "los", "para", "por", "que", "se", "sin",
    "sobre", "su", "sus", "tras", "un", "una", "unas", "unos", "y", "o", "e", "u",
})

# Intenciones que nos interesan para clasificar la cola larga.
INTENT_MARKERS: dict[str, tuple[str, ...]] = {
    "letra": ("letra", "letras", "lyrics"),
    "significado": ("significado", "significa", "interpretacion", "sentido", "explicacion"),
    "escucha": ("escuchar", "youtube", "spotify", "video", "online"),
    "compra": ("comprar", "vinilo", "cd", "camiseta", "merch", "precio", "disco fisico"),
    "acordes": ("acordes", "tabs", "guitarra", "bajo", "tablatura", "partitura"),
}


def kw_norm(s: str) -> str:
    """Forma canónica para deduplicar: sin acentos, minúsculas, sin puntuación."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9ñ\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def kw_tokens(s: str) -> list[str]:
    return [t for t in kw_norm(s).split() if t]


def kw_sorted_key(s: str) -> str:
    """Clave insensible al orden y a las stopwords. Agrupa variantes, no las colapsa."""
    toks = sorted(t for t in kw_tokens(s) if t not in STOPWORDS_ES)
    return " ".join(toks)


def variant_group(s: str) -> str:
    return hashlib.sha1(kw_sorted_key(s).encode()).hexdigest()[:16]


def kw_clean_for_api(s: str) -> str:
    """Saneado de lo que DataForSEO rechaza (mismo criterio que keyword_planner._clean)."""
    s = re.sub(r"[\[\](){}¿?¡!\"'`´]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_title_suffix(s: str) -> str:
    """Quita el sufijo desambiguador del catálogo: «Jesucristo García (Rock
    Transgresivo)» → «Jesucristo García».

    Como semilla, el título verboso es inservible: nadie busca así, y medido en
    la ola 1 dejó a Rock Transgresivo en 21 keywords cuando «Tú en tu casa» sacó
    2.263. Es el mismo alias que `entity_resolver._clean_title` añade al índice
    del autolinker por exactamente el mismo motivo.
    """
    base = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*", " ", s)
    base = re.sub(r"\s+", " ", base).strip(" -–—,")
    return base or s.strip()


def n_words(s: str) -> int:
    return len(kw_tokens(s))


def is_brand(s: str) -> bool:
    return bool(BRAND_TOKENS & set(kw_tokens(s)))


def detect_intent(s: str) -> str | None:
    """Intención léxica. Es una señal barata; la de DataForSEO manda si existe."""
    toks = set(kw_tokens(s))
    norm = kw_norm(s)
    for intent, markers in INTENT_MARKERS.items():
        for m in markers:
            if (" " in m and m in norm) or m in toks:
                return intent
    return None


# Un título sin marca solo acredita por sí solo si es inequívoco. Medido en el
# piloto de Agila: «prometeo» (canción de Yo, minoría absoluta) arrastraba
# «prometeo librería», «prometeo malaga», «prometeo fp opiniones» y el mito
# griego entero — y encima los usaba de semilla, disparando el cierre transitivo
# a 3.514 keywords y $2,99 en UN disco.
STRONG_TITLE_CHARS = 12
STRONG_TITLE_WORDS = 3


@dataclass
class Match:
    """Resultado de la guarda. `strong` decide si la keyword puede SEMBRAR.

    Tres grados, y los tres se exportan — no se tira nada:
      - `brand`        lleva marca del universo. Certeza alta.
      - `title_strong` título largo y distintivo sin marca. Certeza alta.
      - `title_weak`   título corto sin marca («prometeo», «salir», «agila»).
                       Ambigua por homonimia: se recolecta, se etiqueta, pero
                       NO propaga el cierre transitivo.
    """

    reason: str
    kind: str

    @property
    def strong(self) -> bool:
        return self.kind in ("brand", "title_strong")


@dataclass
class UniverseVocab:
    """Vocabulario del universo, derivado de la BD."""

    brand: frozenset[str] = field(default_factory=lambda: BRAND_TOKENS)
    strong_titles: tuple[str, ...] = ()
    weak_titles: frozenset[str] = frozenset()
    people: tuple[str, ...] = ()

    def matches(self, keyword: str) -> Match | None:
        """Devuelve el motivo Y su grado, o None. El motivo viaja al CSV: si el
        filtro es generoso, quiero poder auditar por qué entró cada keyword."""
        norm = kw_norm(keyword)
        toks = set(norm.split())

        hit = self.brand & toks
        if hit:
            return Match(f"marca:{sorted(hit)[0]}", "brand")

        for title in self.strong_titles:
            if title in norm:
                return Match(f"titulo:{title}", "title_strong")

        for person in self.people:
            if person in norm:
                return Match(f"persona:{person}", "title_strong")

        hit = self.weak_titles & toks
        if hit:
            return Match(f"titulo_ambiguo:{sorted(hit)[0]}", "title_weak")

        return None


@lru_cache(maxsize=1)
def _noop_cache_guard() -> None:  # pragma: no cover - marcador de intención
    return None


def build_vocab(db: Session) -> UniverseVocab:
    """Construye el vocabulario desde la BD. Un disco nuevo entra sin tocar código."""
    strong_titles: set[str] = set()
    weak_titles: set[str] = set()

    def add_title(raw: str | None) -> None:
        if not raw:
            return
        # Los títulos verbosos del catálogo llevan sufijos «(Rock Transgresivo)»
        # o «[En Directo]». El alias sin sufijo es el que busca la gente.
        base = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", raw)
        for candidate in (raw, base):
            norm = kw_norm(candidate)
            if not norm:
                continue
            words = len(norm.split())
            if len(norm) >= STRONG_TITLE_CHARS or words >= STRONG_TITLE_WORDS:
                strong_titles.add(norm)
            else:
                weak_titles.add(norm)

    for (title,) in db.execute(select(Album.title)).all():
        add_title(title)
    for (title,) in db.execute(select(Song.title)).all():
        add_title(title)

    people: set[str] = set()
    for stage, full in db.execute(select(Person.stage_name, Person.full_name)).all():
        # Person NO tiene campo `name`: leerlo mal ya dejó en blanco todos los
        # nombres una vez y marcó como falsas TODAS las fotos de personas.
        variantes = [stage or "", full or ""]

        # La gente no busca por el nombre de pila ni por el nombre civil
        # completo, sino por la combinación de ambos. Medido: Fito está en la BD
        # como stage_name «Fito» + full_name «Adolfo Cabrales Mato», y la keyword
        # real es «fito cabrales» — 18.100 búsquedas/mes que se caían del
        # vocabulario porque esa forma no vive en ningún campo.
        s, f = kw_norm(stage or ""), (full or "").split()
        if s and len(f) >= 2:
            for apellido in f[1:]:
                variantes.append(f"{s} {apellido}")

        for raw in variantes:
            norm = kw_norm(raw)
            # Un nombre de pila suelto («Robe», «Fito») es homónimo puro; solo
            # acredita el nombre con al menos dos componentes.
            if len(norm.split()) >= 2 and len(norm) >= STRONG_TITLE_CHARS:
                people.add(norm)

    for (name,) in db.execute(select(Artist.name)).all():
        norm = kw_norm(name or "")
        if norm:
            strong_titles.add(norm)

    # Un título débil que además es stopword o demasiado corto se cae del todo:
    # ya entrará por la vía de la marca si de verdad es del universo.
    weak_titles = {
        t for t in weak_titles
        if t not in STOPWORDS_ES and len(t) >= 4 and t not in strong_titles
    }

    return UniverseVocab(
        strong_titles=tuple(sorted(strong_titles, key=len, reverse=True)),
        weak_titles=frozenset(weak_titles),
        people=tuple(sorted(people, key=len, reverse=True)),
    )
