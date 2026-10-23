"""Cuánto nos fiamos de un vídeo antes de meterlo en el corpus.

El detector solo vigilaba dos canales de análisis y el corpus llevaba desde el
29-07-2026 sin recibir un vídeo. Para buscar fuera hace falta decidir, sin una
persona delante, qué entra solo, qué espera un clic y qué no entra nunca:

    A  voz        habla Robe, un miembro o un amigo autorizado, en un canal
                  oficial o de un medio reconocido, y es una entrevista o charla
    B  medio      un medio reconocido habla del universo Robe, sin voz identificada
    C  fan        canal no reconocido pero relevante: correo de aprobación
    descartado    canal vetado para el corpus, demasiado corto o largo, o no relevante

Esto solo mira título, descripción y canal. Lo que se dice DENTRO del vídeo lo
comprueba un juez después de transcribir, y ese juez solo puede bajar de nivel.

Las VOCES salen de la BD (Robe y `band_memberships`) y de
`data/corpus_voices.yaml` (amigos, cada uno con su evidencia). Las personas sin
formación de `persons.yaml` NO cuentan como amigos: ahí están también Frank
Zappa o Camarón, que salen en las letras.

Un alias de una sola palabra («Robe», «Salo», «Leiva», «Uoho») no basta: tiene
que ir con Robe o Extremoduro al lado, o con el nombre completo. Es la lección
de Fito Páez y de Guardiola: un nombre corto casa con cualquiera.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.services.channel_policy import canal_vetado, es_canal_oficial

VOICES_PATH = Path("/app/data/corpus_voices.yaml")
MEDIA_PATH = Path("/app/data/corpus_media.yaml")

MIN_DURACION_S = 60          # un short no trae una entrevista
MAX_DURACION_S = 4 * 3600    # más de 4 h son directos de streaming o recopilatorios

# Lo que dice que alguien HABLA, no que suena una canción suya.
_SENAL_CHARLA = (
    "entrevista", "entrevistamos", "charla", "conversacion", "conversamos",
    "rueda de prensa", "habla", "hablamos", "nos cuenta", "cuenta como",
    "podcast", "coloquio", "encuentro con", "testimonio", "declaraciones",
    "documental",
)

# Contexto que desambigua un alias de una palabra.
_CONTEXTO_UNIVERSO = ("extremoduro", "robe iniesta", "roberto iniesta")


def normaliza(texto: str | None) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes.casefold()).strip()


def _contiene(texto_norm: str, termino: str) -> bool:
    t = normaliza(termino)
    return bool(t) and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", texto_norm) is not None


@dataclass(frozen=True)
class Voz:
    slug: str
    nombre: str
    relacion: str                      # robe | miembro | amigo | biografo
    alias: tuple[str, ...] = ()
    alias_ambiguos: tuple[str, ...] = ()

    def nombrada_en(self, texto_norm: str) -> bool:
        """¿El texto nombra a esta voz sin ambigüedad?"""
        if any(_contiene(texto_norm, a) for a in self.alias if len(a.split()) > 1):
            return True
        cortos = [a for a in self.alias if len(a.split()) == 1] + list(self.alias_ambiguos)
        if not any(_contiene(texto_norm, a) for a in cortos):
            return False
        # Un alias de una palabra solo vale con el universo al lado. Para Robe,
        # «Robe» y «Extremoduro» juntos ya son contexto suficiente.
        return any(_contiene(texto_norm, c) for c in _CONTEXTO_UNIVERSO) or (
            self.relacion != "robe" and _contiene(texto_norm, "robe")
        )

    @property
    def kind(self) -> str:
        return "robe_interview" if self.relacion == "robe" else "entorno_interview"


ROBE = Voz(slug="robe-iniesta", nombre="Robe", relacion="robe",
           alias=("Robe", "Robe Iniesta", "Roberto Iniesta"))


def voces_de_yaml(path: Path = VOICES_PATH) -> list[Voz]:
    """Amigos autorizados. Sin evidencia no entra nadie, aunque esté en el fichero."""
    if not path.exists():
        return []
    datos = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    voces = []
    for v in datos.get("voces") or []:
        if not any((e or {}).get("url") and (e or {}).get("cita") for e in v.get("evidencia") or []):
            continue
        voces.append(Voz(
            slug=v["slug"], nombre=v["nombre"], relacion=v.get("relacion", "amigo"),
            # `alias: []` explícito = el nombre solo vale con contexto (está en
            # `alias_ambiguos`); no se rellena con el nombre.
            alias=tuple(v.get("alias", [v["nombre"]]) or ()),
            alias_ambiguos=tuple(v.get("alias_ambiguos") or []),
        ))
    return voces


def voces_de_bd(db) -> list[Voz]:
    """Robe y quien haya tocado con él (`band_memberships`)."""
    from sqlalchemy import select

    from app.db.models import BandMembership, Person

    personas = db.execute(
        select(Person).where(Person.id.in_(select(BandMembership.person_id)))
    ).scalars().all()
    voces = [ROBE]
    for p in personas:
        if p.slug == ROBE.slug:
            continue
        alias = tuple(a for a in (p.stage_name, p.full_name) if a)
        voces.append(Voz(slug=p.slug, nombre=p.stage_name or p.full_name,
                         relacion="miembro", alias=alias))
    return voces


def cargar_voces(db) -> list[Voz]:
    return voces_de_bd(db) + voces_de_yaml()


def voces_en(texto: str, voces: list[Voz]) -> list[Voz]:
    t = normaliza(texto)
    return [v for v in voces if v.nombrada_en(t)]


@dataclass
class MediosCorpus:
    """Medios reconocidos: canales por `channel_id` y dominios para el texto."""
    canales: dict[str, str] = field(default_factory=dict)    # channel_id → nombre
    dominios: dict[str, str] = field(default_factory=dict)   # dominio → nombre

    @classmethod
    def desde_yaml(cls, path: Path = MEDIA_PATH) -> MediosCorpus:
        if not path.exists():
            return cls()
        datos = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        canales, dominios = {}, {}
        for m in datos.get("medios") or []:
            for c in m.get("youtube") or []:
                if c.get("channel_id"):
                    canales[c["channel_id"]] = m["nombre"]
            for d in m.get("dominios") or []:
                dominios[d.casefold()] = m["nombre"]
        return cls(canales=canales, dominios=dominios)

    def canal(self, channel_id: str | None) -> str | None:
        return self.canales.get(channel_id or "")


@dataclass
class Video:
    video_id: str
    title: str
    channel_title: str
    channel_id: str | None = None
    description: str = ""
    duration_s: float | None = None
    relevante: bool = False          # `youtube_relevance.is_relevant`, ya calculado


@dataclass
class Veredicto:
    nivel: str                       # A | B | C | descartado
    kind: str | None
    voces: list[str] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)

    @property
    def entra_solo(self) -> bool:
        return self.nivel in ("A", "B")


def clasificar(video: Video, voces: list[Voz], medios: MediosCorpus) -> Veredicto:
    motivos: list[str] = []
    veto = canal_vetado(video.channel_title, modo="corpus")
    if veto:
        return Veredicto("descartado", None, motivos=[f"canal vetado ({veto})"])
    if video.duration_s is not None and video.duration_s < MIN_DURACION_S:
        return Veredicto("descartado", None, motivos=[f"dura {video.duration_s:.0f} s"])
    if video.duration_s is not None and video.duration_s > MAX_DURACION_S:
        return Veredicto("descartado", None, motivos=[f"dura {video.duration_s / 3600:.1f} h"])

    texto = f"{video.title}\n{video.description}"
    texto_norm = normaliza(texto)
    oficial = es_canal_oficial(video.channel_title)
    medio = medios.canal(video.channel_id)
    if oficial:
        motivos.append(f"canal oficial («{video.channel_title}»)")
    elif medio:
        motivos.append(f"medio reconocido ({medio})")

    nombradas = voces_en(texto, voces)
    charla = next((s for s in _SENAL_CHARLA if _contiene(texto_norm, s)), None)
    if nombradas and (oficial or medio) and charla:
        # Si hay varias, manda Robe: es la única voz que se cita.
        principal = next((v for v in nombradas if v.relacion == "robe"), nombradas[0])
        motivos.append(f"voz: {', '.join(v.nombre for v in nombradas)} · «{charla}»")
        return Veredicto("A", principal.kind, [v.slug for v in nombradas], motivos)

    if not video.relevante and not nombradas:
        return Veredicto("descartado", None, motivos=motivos + ["no trata del universo Robe"])
    if nombradas:
        motivos.append(f"nombra a {', '.join(v.nombre for v in nombradas)} "
                       f"{'sin señal de charla' if not charla else 'en un canal sin reconocer'}")
    if medio or oficial:
        return Veredicto("B", "media_report", [v.slug for v in nombradas], motivos)
    return Veredicto("C", "youtube_transcript", [v.slug for v in nombradas],
                     motivos + ["canal sin reconocer"])
