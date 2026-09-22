"""Elegir el vídeo y el tramo de un clip, que era lo único que seguía a mano.

Todo lo demás del camino ya funcionaba: el montaje 9:16 con fondo desenfocado,
el veto de canales, la atribución quemada, la retirada en un paso y el daemon
de la Mac que baja el tramo y lo sube a Cloudinary. Lo que no existía era una
sola línea de heurística para decidir QUÉ vídeo y QUÉ segundos.

Cómo se elige:

  1. Solo vídeos de `video_assets` no vetados y con transcripción. El canal ya
     está comprobado contra la Data API, así que no se quema una descarga en
     algo que no se va a poder publicar.
  2. Se construyen ventanas de 20 a 45 segundos sobre los tramos con tiempo
     (`source_segments`) y se puntúan: densidad de habla, que mencione algo del
     catálogo, afinidad con el tema del día y cómo de limpio es el corte.
  3. Nunca se corta a mitad de palabra, y se prefiere cortar donde hay una
     PAUSA real del habla.

Sobre las fronteras, que es lo delicado: los subtítulos de YouTube llegan
troceados cada 3-5 segundos, solapados y **sin puntuación** («en octubre de 1992
corrió el rumor de / que Roberto Iniesta había fallecido en / un accidente de»).
Con ese material no hay forma honesta de afirmar que un corte cae en un punto y
seguido, así que la frontera se clasifica y VIAJA con el candidato
(`frontera`): quien aprueba el clip ve si el corte es limpio o aproximado. No
se disfraza de exacto lo que no lo es.

Y una regla de fondo: lo que dice el tramo sirve para ELEGIRLO, no para
afirmarlo. Las transcripciones automáticas traen erratas conocidas (Whisper
escribe «Robben y Niesta»), así que el caption de un clip presenta la fuente y
no parafrasea su contenido como dato.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SourceSegment, VideoAsset, VideoClip

logger = logging.getLogger(__name__)

# Duración del clip. Dentro de lo que admite `video_clips` (3-60 s), pero más
# estrecho: menos de 20 s no da para una idea, y más de 45 pierde a la gente.
MIN_S = 20.0
MAX_S = 45.0
# Caracteres por segundo de habla normal. Por debajo hay música o silencio; por
# encima, la transcripción está pegando frases de otro sitio.
DENSIDAD_MIN = 7.0
DENSIDAD_MAX = 28.0
# Con menos texto que esto, el tramo no dice nada aunque dure 30 segundos.
MIN_CHARS = 150
# Hueco entre un tramo y el siguiente que se considera una pausa del habla.
PAUSA_S = 0.45
# Margen alrededor de un clip ya publicado del mismo vídeo.
MARGEN_REPETICION_S = 15.0
# El principio y el final de un vídeo son de quien lo sube, no de quien habla:
# presentación del canal, saludo, créditos, despedida. Medido en la primera
# pasada real: dos de los cinco mejores candidatos eran «bienvenidos al canal».
# En vídeos cortos el recorte es proporcional, o se quedarían sin candidatos.
INTRO_S = 45.0
OUTRO_S = 30.0
PROPORCION_BORDE = 0.12

# Lo que delata que habla el CANAL y no el entrevistado. Descarte duro: un clip
# que abre con la presentación de otro youtuber no es material de esta cuenta,
# por muy bien que puntúe lo demás.
MARCAS_DE_CANAL = (
    r"bienvenid[oa]s? al canal", r"bienvenid[oa]s? a\b[^.]{0,30}\breacci[oó]n",
    r"suscr[ií]b", r"dale al? like", r"activa la campanita", r"comenta",
    r"en el v[ií]deo de hoy", r"hoy (os|les) traigo", r"mi canal",
    r"antes de empezar", r"no olvides", r"link en la descripci[oó]n",
    r"patrocina", r"este v[ií]deo es", r"nos vemos en el pr[oó]ximo",
)

# Señales de que habla alguien en primera persona (una entrevista, no un
# narrador contando lo que pasó).
_PRIMERA_PERSONA = re.compile(
    r"\b(yo|me|mi|m[ií]o|conmigo|creo|pienso|siento|quer[ií]a|hice|hago)\b", re.I
)


@dataclass
class Candidato:
    """Un tramo concreto de un vídeo concreto, con por qué se ha elegido."""

    asset: VideoAsset
    start_s: float
    end_s: float
    texto: str
    score: float = 0.0
    frontera: str = "aproximada"
    motivos: list[str] = field(default_factory=list)

    @property
    def duracion_s(self) -> float:
        return round(self.end_s - self.start_s, 2)

    def resumen(self) -> str:
        return (
            f"{self.asset.youtube_id} · {self.start_s:.0f}-{self.end_s:.0f}s "
            f"({self.duracion_s:.0f}s) · corte {self.frontera} · "
            f"score {self.score:.2f} · {', '.join(self.motivos)}"
        )


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ\s]", " ", s)).strip()


def _tokens(s: str) -> set[str]:
    return {w for w in _norm(s).split() if len(w) > 3}


def _es_del_canal(texto: str) -> str | None:
    """Si el tramo lo dice el canal y no el protagonista, devuelve la marca."""
    plano = _norm(texto)
    for pat in MARCAS_DE_CANAL:
        m = re.search(pat, plano)
        if m:
            return m.group(0)
    return None


def _bordes(duracion_total: float | None) -> tuple[float, float]:
    """Cuánto se ignora del principio y del final de un vídeo."""
    if not duracion_total or duracion_total <= 0:
        return INTRO_S, OUTRO_S
    intro = min(INTRO_S, duracion_total * PROPORCION_BORDE)
    outro = min(OUTRO_S, duracion_total * PROPORCION_BORDE)
    return intro, outro


def _hits_catalogo(texto: str, vocab) -> list[str]:
    """Qué del catálogo menciona este tramo.

    `allow_short=False` no es un detalle: los títulos cortos («Mama», «Golfa»,
    «La Carrera») casan dentro de cualquier prosa, y eso ya metió un vídeo sobre
    otra cantante que hablaba de «su carrera». Aquí el texto es prosa hablada,
    justo el caso donde esa señal miente.
    """
    if vocab is None:
        return []
    try:
        from app.services.youtube_relevance import _hits, norm_title

        return _hits(norm_title(texto), vocab, where="tramo", allow_short=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[clips] vocabulario no utilizable: %s", exc)
        return []


def _tramos_usados(db: Session, video_id: str) -> list[tuple[float, float]]:
    """Lo que ya se publicó de este vídeo: no se repite ni se solapa."""
    filas = db.execute(
        select(VideoClip.start_s, VideoClip.end_s).where(
            VideoClip.video_id == video_id,
            VideoClip.status.in_(("requested", "downloading", "ready", "published")),
        )
    ).all()
    return [(float(a), float(b)) for a, b in filas]


def _solapa(a: float, b: float, usados: list[tuple[float, float]]) -> bool:
    for ini, fin in usados:
        if a < fin + MARGEN_REPETICION_S and ini - MARGEN_REPETICION_S < b:
            return True
    return False


def _frontera(segmentos: list[SourceSegment], i: int, j: int) -> str:
    """Cómo de limpio es el corte: por puntuación, por pausa o aproximado.

    La puntuación solo existe cuando la transcripción viene de Whisper. Con
    subtítulos automáticos de YouTube no la hay, y decir que un corte es limpio
    porque «no encontré un punto» sería justo al revés.
    """
    anterior = segmentos[i - 1].text.strip() if i > 0 else ""
    ultimo = segmentos[j].text.strip()
    if (not anterior or anterior.endswith((".", "!", "?", "…"))) and ultimo.endswith(
        (".", "!", "?", "…")
    ):
        return "puntuacion"
    hueco_antes = (
        segmentos[i].start_s - segmentos[i - 1].end_s if i > 0 else PAUSA_S
    )
    hueco_despues = (
        segmentos[j + 1].start_s - segmentos[j].end_s
        if j + 1 < len(segmentos)
        else PAUSA_S
    )
    if hueco_antes >= PAUSA_S and hueco_despues >= PAUSA_S:
        return "pausa"
    return "aproximada"


def _ventanas(segmentos: list[SourceSegment]) -> list[tuple[int, int, float, float]]:
    """Todas las ventanas de duración admisible: (i, j, inicio, fin)."""
    fuera: list[tuple[int, int, float, float]] = []
    n = len(segmentos)
    j = 0
    for i in range(n):
        inicio = segmentos[i].start_s
        j = max(j, i)
        while j + 1 < n and segmentos[j].end_s - inicio < MIN_S:
            j += 1
        k = j
        while k < n and segmentos[k].end_s - inicio <= MAX_S:
            fin = segmentos[k].end_s
            if fin - inicio >= MIN_S:
                fuera.append((i, k, inicio, fin))
            k += 1
    return fuera


def _puntuar(
    texto: str, duracion: float, frontera: str, vocab_hits: int, tema_hits: int,
) -> tuple[float, list[str]]:
    """Cuánto vale este tramo. Determinista: mismo tramo, misma nota."""
    motivos: list[str] = []
    score = 0.0

    densidad = len(texto) / max(duracion, 1.0)
    # Una campana sencilla: lo ideal son ~16 caracteres por segundo.
    score += max(0.0, 1.0 - abs(densidad - 16.0) / 16.0)

    if vocab_hits:
        score += min(vocab_hits, 3) * 0.5
        motivos.append(f"menciona {vocab_hits} cosa(s) del catálogo")
    if tema_hits:
        score += min(tema_hits, 4) * 0.4
        motivos.append(f"encaja con el tema ({tema_hits} coincidencias)")

    score += {"puntuacion": 1.0, "pausa": 0.6, "aproximada": 0.0}[frontera]
    if frontera != "aproximada":
        motivos.append(f"corte por {frontera}")

    # Una idea suele necesitar más de media frase.
    if len(texto) >= 300:
        score += 0.3

    # Alguien hablando de sí mismo, no un narrador contando lo que pasó. Es la
    # diferencia entre una entrevista y la voz en off de un documental.
    if len(_PRIMERA_PERSONA.findall(texto)) >= 2:
        score += 0.5
        motivos.append("habla en primera persona")
    return score, motivos


def candidatos_de(
    db: Session, asset: VideoAsset, *, vocab=None, tema: str = "",
) -> list[Candidato]:
    """Los mejores tramos de UN vídeo, de mejor a peor."""
    if asset.vetado or asset.source_id is None:
        return []
    segmentos = list(db.execute(
        select(SourceSegment)
        .where(SourceSegment.source_id == asset.source_id)
        .order_by(SourceSegment.idx)
    ).scalars().all())
    if len(segmentos) < 2:
        return []

    usados = _tramos_usados(db, asset.youtube_id)
    tema_tokens = _tokens(tema)
    fuera: list[Candidato] = []
    duracion_total = float(asset.duration_s or segmentos[-1].end_s or 0)
    intro, outro = _bordes(duracion_total)

    for i, j, inicio, fin in _ventanas(segmentos):
        if inicio < intro:
            continue
        if duracion_total and fin > duracion_total - outro:
            continue
        if _solapa(inicio, fin, usados):
            continue
        texto = " ".join(s.text.strip() for s in segmentos[i : j + 1]).strip()
        texto = re.sub(r"\s+", " ", texto)
        if len(texto) < MIN_CHARS:
            continue
        marca = _es_del_canal(texto)
        if marca:
            logger.debug("[clips] descartado (habla el canal: «%s»)", marca)
            continue
        duracion = fin - inicio
        densidad = len(texto) / max(duracion, 1.0)
        if not (DENSIDAD_MIN <= densidad <= DENSIDAD_MAX):
            continue

        vocab_hits = len(_hits_catalogo(texto, vocab))
        tema_hits = len(tema_tokens & _tokens(texto)) if tema_tokens else 0

        frontera = _frontera(segmentos, i, j)
        score, motivos = _puntuar(texto, duracion, frontera, vocab_hits, tema_hits)
        fuera.append(Candidato(
            asset=asset, start_s=round(inicio, 2), end_s=round(fin, 2),
            texto=texto, score=score, frontera=frontera, motivos=motivos,
        ))

    fuera.sort(key=lambda c: -c.score)
    return fuera


def elegir(
    db: Session, *, tema: str = "", limite: int = 3, por_video: int = 1,
) -> list[Candidato]:
    """Los mejores tramos del catálogo entero, repartidos entre vídeos.

    `por_video=1` a propósito: tres clips seguidos de la misma entrevista se
    leen como tres trozos de lo mismo, no como tres publicaciones.
    """
    assets = list(db.execute(
        select(VideoAsset).where(
            VideoAsset.vetado.is_(False), VideoAsset.source_id.is_not(None)
        )
    ).scalars().all())
    if not assets:
        return []

    vocab = None
    try:
        from app.services.youtube_relevance import build_vocab
        vocab = build_vocab(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[clips] sin vocabulario de catálogo: %s", exc)

    fuera: list[Candidato] = []
    for asset in assets:
        cands = candidatos_de(db, asset, vocab=vocab, tema=tema)
        fuera.extend(cands[:por_video])
    fuera.sort(key=lambda c: -c.score)
    return fuera[:limite]
