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
    # Solo en directos: qué momento es y de qué canción. `verso` sale de la
    # letra de la BD, nunca de la transcripción (que está garbleada).
    tipo: str = "habla"
    cancion: str | None = None
    verso: str | None = None

    @property
    def duracion_s(self) -> float:
        return round(self.end_s - self.start_s, 2)

    def resumen(self) -> str:
        de = f" · {self.cancion}" if self.cancion else ""
        return (
            f"{self.asset.youtube_id} · {self.start_s:.0f}-{self.end_s:.0f}s "
            f"({self.duracion_s:.0f}s) · {self.tipo}{de} · corte {self.frontera} · "
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
        # Y que hable el entrevistado, no quien le entrevista. Aquí sin juez
        # (sería una llamada por ventana); el finalista sí pasa por él.
        del_sujeto, motivo_voz = habla_el_protagonista(texto, usar_llm=False)
        if not del_sujeto:
            logger.debug("[clips] descartado (%s)", motivo_voz)
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


# --------------------------------------------------------------------------- #
# Directos: aquí manda lo que PASA en el escenario, no cuánto se habla
# --------------------------------------------------------------------------- #
# Lo que vale un momento por sí mismo. El estribillo primero porque es lo que
# la gente reconoce y canta; el solo va detrás del habla porque acertar dónde
# empieza de verdad es lo más difícil de todo esto.
PESO_TIPO = {
    "estribillo": 3.0,
    "habla": 2.0,
    "arranque": 1.6,
    "solo": 1.4,
    "canto": 1.0,
}
# Un clip de directo dura lo que dura el momento. Este mínimo ya no rellena:
# solo evita clips tan cortos que no se entiendan, y se estira únicamente con
# momentos de la MISMA canción.
#
# Estaba en 18 s y rellenaba con lo que viniera detrás. Eso publicó «El
# estribillo de "Por encima del bien y del mal"» cerrando en el segundo 294,
# UNO ANTES de que sonara el gancho (295-302). Criterio de David: mejor corto y
# exacto. `video_clips.MIN_CLIP_S` admite desde 3 s.
MIN_S_DIRECTO = 10.0


def _mismo_momento(a, b) -> bool:
    """¿Estos dos tramos son el mismo momento, seguido?"""
    return a.tipo == b.tipo and a.cancion == b.cancion


def abre_bloque(momentos_todos: list, idx: int) -> bool:
    """¿Este es el primer tramo de su bloque?

    Solo se construye un candidato por bloque. Antes se construía uno por cada
    tramo, salían tres versiones del mismo trozo cortadas por sitios distintos,
    y el filtro anti-solape decidía entre ellas por orden de aparición.
    """
    return idx == 0 or not _mismo_momento(momentos_todos[idx - 1], momentos_todos[idx])


def _bloque_del_momento(
    momentos_todos: list, idx: int, duracion_total: float | None,
) -> tuple[float, float, str, int]:
    """El bloque entero: tramos seguidos del mismo tipo y la misma canción.

    El clip dura lo que dura el momento, ni más ni menos. Solo si el bloque se
    queda por debajo de `MIN_S_DIRECTO` se estira, y únicamente con tramos de la
    MISMA canción: rellenar con lo que venga detrás es lo que cortó un estribillo
    un segundo antes de su gancho.

    Devuelve (inicio, fin, frontera, cuántos tramos cubre).
    """
    m = momentos_todos[idx]
    inicio, fin = m.start_s, m.end_s
    cubiertos = 1

    j = idx
    while j + 1 < len(momentos_todos):
        siguiente = momentos_todos[j + 1]
        if not _mismo_momento(m, siguiente):
            break
        if siguiente.end_s - inicio > MAX_S:
            break
        j += 1
        fin = siguiente.end_s
        cubiertos += 1

    # El bloque se queda corto: se completa con lo que siga sonando de la misma
    # canción (la estrofa que viene después, el cierre), nunca con otra cosa.
    while fin - inicio < MIN_S_DIRECTO and j + 1 < len(momentos_todos):
        siguiente = momentos_todos[j + 1]
        if m.cancion and siguiente.cancion and siguiente.cancion != m.cancion:
            break
        if siguiente.end_s - inicio > MAX_S:
            break
        j += 1
        fin = siguiente.end_s

    if duracion_total:
        fin = min(fin, duracion_total)
    # La frontera es de tramo de transcripción, nunca «por puntuación»: en un
    # directo no hay puntuación fiable y decir lo contrario sería mentir.
    return inicio, fin, "pausa" if idx > 0 else "aproximada", cubiertos


def candidatos_directo(
    db: Session, asset: VideoAsset, *, catalogo=None,
) -> list[Candidato]:
    """Los mejores momentos de UN concierto, de mejor a peor.

    Nada que ver con el camino de entrevistas: aquí no se mide densidad de
    habla (eso descartaría justo los solos), se mira QUÉ está pasando.
    """
    from app.services.instagram import momentos as mom

    if asset.vetado or asset.source_id is None:
        return []
    segmentos = list(db.execute(
        select(SourceSegment)
        .where(SourceSegment.source_id == asset.source_id)
        .order_by(SourceSegment.idx)
    ).scalars().all())
    if len(segmentos) < 2:
        return []

    catalogo = catalogo or mom.cargar_catalogo(db)
    clasificados = mom.clasificar(segmentos, catalogo)
    if not clasificados:
        return []

    usados = _tramos_usados(db, asset.youtube_id)
    duracion_total = float(asset.duration_s or segmentos[-1].end_s or 0)
    intro, outro = _bordes(duracion_total)
    fuera: list[Candidato] = []
    aceptadas: list[tuple[float, float]] = []

    # Un candidato por BLOQUE, no por tramo: si no, salen tres versiones del
    # mismo momento cortadas por sitios distintos y hay que elegir entre ellas.
    bloques = [
        i for i in range(len(clasificados))
        if abre_bloque(clasificados, i)
        and clasificados[i].tipo in PESO_TIPO
        and clasificados[i].tipo != "canto"
    ]
    # De mejor a peor ANTES de recortar solapes, y con la COBERTURA como
    # desempate: las dos ventanas del caso de Barcelona empataban a 4,00 exacto
    # y ganó la peor por orden de aparición. Ahora gana la que trae más momento.
    medidos = []
    for idx in bloques:
        inicio, fin, frontera, cubiertos = _bloque_del_momento(
            clasificados, idx, duracion_total
        )
        medidos.append((idx, inicio, fin, frontera, cubiertos))
    medidos.sort(
        key=lambda t: (
            -(PESO_TIPO.get(clasificados[t[0]].tipo, 0) + clasificados[t[0]].confianza),
            -t[4],
        )
    )

    for idx, inicio, fin, frontera, cubiertos in medidos:
        m = clasificados[idx]
        if fin - inicio < MIN_S_DIRECTO or fin - inicio > MAX_S:
            continue
        if inicio < intro or (duracion_total and fin > duracion_total - outro):
            continue
        if _solapa(inicio, fin, usados):
            continue
        if any(inicio < f and i < fin for i, f in aceptadas):
            continue
        aceptadas.append((inicio, fin))

        score = PESO_TIPO[m.tipo] + m.confianza
        motivos = list(m.motivos)
        if cubiertos > 1:
            motivos.append(f"el momento dura {cubiertos} tramos seguidos")
        if m.cancion:
            score += 0.4
            motivos.append(f"canción identificada: {m.cancion}")
        if asset.event_date or asset.event_place:
            score += 0.3
            motivos.append("el concierto tiene fecha o lugar")
        if asset.imagen_fija:
            # No se excluye —David quiere verlos y decidir— pero baja al fondo:
            # solo sale si no hay material con imágenes de verdad.
            score -= 2.0
            motivos.append("OJO: el vídeo es una imagen fija con el audio")
        texto = " ".join(
            (getattr(s, "text", "") or "").strip() for s in segmentos
            if inicio <= s.start_s <= fin
        ).strip()

        fuera.append(Candidato(
            asset=asset, start_s=round(inicio, 2), end_s=round(fin, 2),
            texto=texto, score=score, frontera=frontera, motivos=motivos,
            tipo=m.tipo, cancion=m.cancion, verso=m.verso,
        ))

    fuera.sort(key=lambda c: -c.score)
    return fuera


def elegir_directo(
    db: Session, *, limite: int = 3, por_video: int = 1,
) -> list[Candidato]:
    """Los mejores momentos del catálogo de conciertos."""
    from app.services.instagram import momentos as mom

    assets = list(db.execute(
        select(VideoAsset).where(
            VideoAsset.vetado.is_(False),
            VideoAsset.source_id.is_not(None),
            VideoAsset.kind == "live_fan",
        )
    ).scalars().all())
    if not assets:
        return []
    catalogo = mom.cargar_catalogo(db)
    fuera: list[Candidato] = []
    for asset in assets:
        cands = candidatos_directo(db, asset, catalogo=catalogo)
        fuera.extend(_variados(cands, por_video))
    fuera.sort(key=lambda c: -c.score)
    return fuera[:limite]


def _variados(candidatos: list[Candidato], cuantos: int) -> list[Candidato]:
    """Los mejores de un mismo concierto, pero de momentos DISTINTOS.

    Sin esto salían seis estribillos del mismo bolo, porque el estribillo pesa
    más que lo demás: seis clips del mismo concierto cantando se leen como uno
    repetido. Primero el mejor de cada tipo; si aún falta cupo, se completa con
    los siguientes mejores.
    """
    elegidos: list[Candidato] = []
    tipos_usados: set[str] = set()
    for c in candidatos:
        if len(elegidos) >= cuantos:
            break
        if c.tipo not in tipos_usados:
            elegidos.append(c)
            tipos_usados.add(c.tipo)
    for c in candidatos:
        if len(elegidos) >= cuantos:
            break
        if c not in elegidos:
            elegidos.append(c)
    return elegidos


# --------------------------------------------------------------------------- #
# ¿Quién habla? (el fallo del primer clip que se propuso)
# --------------------------------------------------------------------------- #
# El primer clip automático que llegó al correo era de una entrevista en la
# Cadena SER, y en el tramo elegido hablaba el LOCUTOR presentando la canción,
# no Robe. El picker premiaba «habla en primera persona» sin preguntarse de
# quién era esa primera persona.
#
# Dos señales deterministas primero, que son gratis y cazan la mayoría:
_PREGUNTA = re.compile(r"[¿?]")
# Quien nombra a Robe está hablando DE él: es quien presenta o entrevista. Robe
# no se nombra a sí mismo en tercera persona.
_NOMBRA_AL_SUJETO = re.compile(r"\b(robe|roberto iniesta|extremoduro)\b", re.I)
# Fórmulas de quien conduce un programa.
_DE_PROGRAMA = re.compile(
    r"\b(nos (ha |había )?(dejado|acompaña|visita)|est[aá] con nosotros|"
    r"bienvenid[oa]s?|vamos a escuchar|escuchamos|a continuaci[oó]n|"
    r"les? (cuento|presento)|nuestro invitado|en antena|en directo desde)\b", re.I
)

_SYS_QUIEN_HABLA = (
    "Te dan un fragmento transcrito de una entrevista. Dices quién habla: el "
    "ENTREVISTADO (la persona sobre la que va la entrevista) o el PRESENTADOR "
    "(quien conduce, pregunta o presenta). Si no se puede saber, di 'dudoso'.\n"
    'Devuelve JSON: {"quien": "entrevistado"|"presentador"|"dudoso"}'
)


def habla_el_protagonista(texto: str, *, usar_llm: bool = True) -> tuple[bool, str]:
    """¿Este tramo lo dice el entrevistado? → (sí/no, motivo).

    Ante la duda responde que NO: publicar al locutor de una radio en una cuenta
    sobre Robe es peor que quedarse sin clip.
    """
    t = (texto or "").strip()
    if not t:
        return False, "sin texto"
    if _PREGUNTA.search(t):
        return False, "es una pregunta: la hace quien entrevista"
    if _NOMBRA_AL_SUJETO.search(t):
        return False, "nombra al sujeto: habla DE él, no es él"
    if _DE_PROGRAMA.search(t):
        return False, "fórmula de quien conduce el programa"
    if not usar_llm:
        return True, "no lo contradice ninguna señal"

    try:
        from app.services.news_research import _json

        data = _json(_SYS_QUIEN_HABLA, f'TEXTO:\n"""\n{t[:900]}\n"""',
                     max_tokens=40, temperature=0)
        quien = (data or {}).get("quien", "dudoso")
    except Exception as exc:  # noqa: BLE001
        # Sin juez no se da por bueno: las señales de arriba ya han pasado, pero
        # el caso del locutor de la SER las pasaba todas.
        logger.warning("[clips] no se pudo comprobar quién habla: %s", exc)
        return False, "no se ha podido comprobar quién habla"
    if quien == "entrevistado":
        return True, "lo dice el entrevistado"
    return False, f"lo dice el {quien}"
