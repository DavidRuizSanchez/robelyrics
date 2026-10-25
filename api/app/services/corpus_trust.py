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
    "documental", "responde", "explica", "se sincera", "confiesa", "reflexiona",
    "opina",
)

# Lo que delata una CANCIÓN, no a alguien hablando. Transcribir una canción no
# añade nada al corpus: la letra ya está en la BD. Salió en la primera muestra
# real (24-10-2026): «Robe - Nada que perder», del canal oficial, entraba como
# reportaje.
_SENAL_MUSICA = (
    "directo", "en vivo", "live", "concierto", "videoclip", "video oficial",
    "official video", "lyric", "letra", "audio", "acustico", "cover", "version",
    "canta", "cantando", "interpreta", "actuacion", "music video",
)

# «Leiva: "No había podido escuchar a Robe…"»: una cita introducida por dos
# puntos o por una barra es alguien hablando, aunque el título no diga
# «entrevista». Solo tras «:» o «|», para no confundirla con el título de una
# canción entre comillas. Y solo si lo que va delante es el NOMBRE de quien
# habla: «Las voces de la radio despiden a Robe Iniesta: "Sus canciones…"» es
# una cita de los locutores (24-10-2026, primer backfill real).
_CITA_EN_TITULO = re.compile(r"([^:|]*)[:|]\s*[\"“«']")

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

    def nombrada_en(self, texto_norm: str, canal_fiable: bool = False) -> bool:
        """¿El texto nombra a esta voz sin ambigüedad?

        En un canal fiable (oficial, de un medio o de una voz de casa) el alias
        corto basta: «ROBE RUEDA DE PRENSA» en el canal de Robe es él. No se usa
        `relevante` como contexto porque «robe» a secas ya lo hace relevante.
        """
        if any(_contiene(texto_norm, a) for a in self.alias if len(a.split()) > 1):
            return True
        cortos = [a for a in self.alias if len(a.split()) == 1] + list(self.alias_ambiguos)
        if not any(_contiene(texto_norm, a) for a in cortos):
            return False
        if canal_fiable:
            return True
        # Un alias de una palabra solo vale con el universo al lado. Para Robe,
        # «Robe» y «Extremoduro» juntos ya son contexto suficiente.
        return any(_contiene(texto_norm, c) for c in _CONTEXTO_UNIVERSO) or (
            self.relacion != "robe" and _contiene(texto_norm, "robe")
        )

    def es_su_canal(self, canal: str | None) -> bool:
        c = normaliza(canal)
        return bool(c) and c in {normaliza(a) for a in (self.nombre, *self.alias)}

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


def voces_en(texto: str, voces: list[Voz], canal_fiable: bool = False) -> list[Voz]:
    t = normaliza(texto)
    return [v for v in voces if v.nombrada_en(t, canal_fiable)]


def _palabras(texto: str) -> list[str]:
    return re.findall(r"\w+", normaliza(texto))


def quien_cita(titulo: str | None, voces: list[Voz]) -> Voz | None:
    """La voz que firma una cita del título: su nombre es TODO lo que va antes.

    Vale un alias completo («Iñaki Antón: …», «Leiva: …») o una mezcla de sus
    palabras que lleve un alias propio de una sola palabra: «Iñaki 'Uoho': «Ahora
    estoy sintiendo…»» (ABC) es Uoho porque dice «uoho». Un nombre de pila suelto
    no basta: «Iñaki: …» o «José Miguel: …» puede ser cualquiera, y un alias
    ambiguo («Fito», que también es Páez) nunca firma solo. «Las voces de la radio
    despiden a Robe: "…"» sigue sin ser de Robe: esas palabras no son nombres suyos.
    """
    for m in _CITA_EN_TITULO.finditer(titulo or ""):
        antes = _palabras(m.group(1))
        if not antes:
            continue
        for v in voces:
            propios = [_palabras(a) for a in (v.nombre, *v.alias)]
            if antes in propios:
                return v
            sueltos = {a[0] for a in propios if len(a) == 1}
            suyas = {p for a in (v.nombre, *v.alias, *v.alias_ambiguos) for p in _palabras(a)}
            if len(antes) > 1 and set(antes) <= suyas and sueltos & set(antes):
                return v
    return None


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
    # Si lo relevante sale del TÍTULO. None = no se sabe (se toma `relevante`).
    relevante_en_titulo: bool | None = None


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
    oficial = es_canal_oficial(video.channel_title)
    medio = medios.canal(video.channel_id)
    # El canal de un miembro o amigo (Woody Amores sube entrevistas de Robe).
    dueno = next((v for v in voces if v.es_su_canal(video.channel_title)), None)
    fiable = bool(oficial or medio or dueno)
    if oficial:
        motivos.append(f"canal oficial («{video.channel_title}»)")
    elif medio:
        motivos.append(f"medio reconocido ({medio})")
    elif dueno:
        motivos.append(f"canal de {dueno.nombre}")

    # En un canal sin reconocer solo cuenta el TÍTULO. El 25-10-2026 entraron como
    # C un documental de Tarragona, sesiones de DJ y trap de «Templario 3.0» y
    # «RKL REMEMBER SOUNDS»: rellenan la descripción con «Robe Iniesta, Leiva,
    # Fito Cabrales…» para salir en las búsquedas, y eso bastaba.
    nombradas = voces_en(texto if fiable else video.title, voces, canal_fiable=fiable)
    if not fiable and not nombradas:
        en_titulo = (video.relevante if video.relevante_en_titulo is None
                     else video.relevante_en_titulo)
        if video.relevante and not en_titulo:
            return Veredicto("descartado", None, motivos=[
                "canal sin reconocer que solo nos nombra en la descripción (relleno de etiquetas)"])
    # Solo el título: las descripciones de los vídeos musicales hablan a veces
    # de entrevistas o de otras cosas que no son el vídeo.
    titulo_norm = normaliza(video.title)
    charla = next((s for s in _SENAL_CHARLA if _contiene(titulo_norm, s)), None)
    hablante = quien_cita(video.title, voces)
    if not charla and hablante:
        charla = "cita en el título"
    musica = next((s for s in _SENAL_MUSICA if _contiene(titulo_norm, s)), None)
    if not charla and (musica or oficial or dueno):
        # Sin señal de charla, el canal oficial o el de un músico sube música
        # aunque el título no lo diga («Robe - Nada que perder»).
        return Veredicto("descartado", None, motivos=motivos + [
            f"es música («{musica}»)" if musica else "canal de músico sin señal de charla: música"])
    if nombradas and fiable and charla:
        # Robe solo si es la ÚNICA voz nombrada. Desde su muerte casi todos los
        # títulos le nombran como TEMA: «Iñaki "Uoho": su verdad sobre Robe» es
        # Uoho hablando, y tomarlo por Robe metería sus palabras en la voz de
        # Robe (robe_voice_v1), que el consultorio usa para hablar como él.
        principal = hablante or next((v for v in nombradas if v.relacion != "robe"),
                                     nombradas[0])
        motivos.append(f"voz: {', '.join(v.nombre for v in nombradas)} · «{charla}»")
        return Veredicto("A", principal.kind, [v.slug for v in nombradas], motivos)

    if not video.relevante and not nombradas:
        return Veredicto("descartado", None, motivos=motivos + ["no trata del universo Robe"])
    if nombradas:
        motivos.append(f"nombra a {', '.join(v.nombre for v in nombradas)} "
                       f"{'sin señal de charla' if not charla else 'en un canal sin reconocer'}")
    if medio or dueno:
        return Veredicto("B", "media_report", [v.slug for v in nombradas], motivos)
    return Veredicto("C", "youtube_transcript", [v.slug for v in nombradas],
                     motivos + ["canal sin reconocer"])
