"""Las noticias con cuerpo de un medio reconocido pasan al corpus antes de purgarse.

Fase 4.1 del plan del corpus. El agregador guarda el cuerpo de cada noticia desde
el 22-09-2026, pero `news_items` se purga a los 7 días y nada lo llevaba al
corpus: una entrevista a Uoho en HOY o un reportaje de RTVE se leían para escribir
un post y se tiraban. Aquí se promueven las que vienen de un dominio de
`data/corpus_media.yaml` (el mismo registro de medios que el vídeo).

    A  press_interview  una voz de casa nombrada en el título, con señal de
                        entrevista o cita, y citas de verdad en el cuerpo: fuente
                        PROPIA que no se cita (solo se cita a Robe)
    B  press            el resto: FONDO, se corrobora y no se nombra

Con `CORPUS_AUTO_ENTRY` apagado (modo sombra) un A entra también como `press`: nada
llega como voz sin el OK de David, y el texto no se pierde con la purga. Al
encenderlo, `ascender_sombra` vuelve a clasificar lo que entró así y sube los A en
su sitio. Sin eso la puerta era de un solo sentido: la noticia ya no existe (se
purga a los 7 días), la búsqueda salta las URLs conocidas y `guardar` no duplicaba,
así que toda entrevista vista en sombra se quedaba de fondo para siempre.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.services.corpus_trust import (
    _SENAL_CHARLA,
    MediosCorpus,
    Voz,
    _contiene,
    normaliza,
    quien_cita,
    voces_en,
)

logger = logging.getLogger(__name__)

MIN_CHARS = 800              # por debajo es un teletipo o un cuerpo mal extraído
_CITAS = re.compile(r"[«\"“][^«»\"“”]{25,}[»\"”]")
_PREGUNTA_RESPUESTA = re.compile(r"^\s*[—–-]\s*¿", re.M)
_DEL_UNIVERSO = re.compile(r"\b(robe|extremoduro|roberto iniesta)\b", re.I)


@dataclass(frozen=True)
class VeredictoTexto:
    nivel: str               # A | B | fuera
    kind: str | None
    medio: str | None
    voces: tuple[str, ...] = ()
    motivo: str = ""


def medio_de(url: str | None, medios: MediosCorpus) -> str | None:
    """El medio de `corpus_media` al que pertenece una URL, por dominio exacto o subdominio."""
    host = (urlparse(url or "").hostname or "").casefold().removeprefix("www.")
    for dominio, nombre in medios.dominios.items():
        d = dominio.removeprefix("www.")
        if host == d or host.endswith("." + d):
            return nombre
    return None


def clasificar_texto(titulo: str, cuerpo: str, url: str, voces: list[Voz],
                     medios: MediosCorpus) -> VeredictoTexto:
    medio = medio_de(url, medios)
    if not medio:
        return VeredictoTexto("fuera", None, None, motivo="no es de un medio de corpus_media")
    if len(cuerpo or "") < MIN_CHARS:
        return VeredictoTexto("fuera", None, medio, motivo=f"cuerpo de {len(cuerpo or '')} chars")
    if not _DEL_UNIVERSO.search(cuerpo):
        return VeredictoTexto("fuera", None, medio, motivo="el cuerpo no nombra a Robe ni a Extremoduro")

    nombradas = voces_en(titulo, voces, canal_fiable=True)
    titulo_norm = normaliza(titulo)
    charla = next((s for s in _SENAL_CHARLA if _contiene(titulo_norm, s)), None)
    hablante = quien_cita(titulo, voces)
    citas = len(_CITAS.findall(cuerpo)) + len(_PREGUNTA_RESPUESTA.findall(cuerpo))
    if nombradas and (charla or hablante) and citas >= 2:
        # La misma regla que en vídeo: Robe solo si es la única voz nombrada.
        principal = hablante or next((v for v in nombradas if v.relacion != "robe"),
                                     nombradas[0])
        return VeredictoTexto("A", "press_interview", medio, tuple(v.slug for v in nombradas),
                              f"habla {principal.nombre} en {medio} · «{charla or 'cita'}» · "
                              f"{citas} citas")
    return VeredictoTexto("B", "press", medio, tuple(v.slug for v in nombradas),
                          f"reportaje de {medio}")


def promover(db, *, auto_entry: bool | None = None, dry_run: bool = False) -> dict[str, int]:
    """Pasa al corpus las noticias con cuerpo de un medio reconocido. Idempotente
    (upsert por kind+url, y `upsert_source` no re-sella lo que no cambia)."""
    from app.config import get_settings
    from app.db.models import NewsItem
    from app.services.corpus_trust import cargar_voces

    if auto_entry is None:
        auto_entry = get_settings().corpus_auto_entry
    voces, medios = cargar_voces(db), MediosCorpus.desde_yaml()
    cuenta = {"A": 0, "B": 0, "fuera": 0}
    if auto_entry and not dry_run:
        cuenta["ascendidas"] = ascender_sombra(db, voces, medios)
    for n in db.query(NewsItem).filter(NewsItem.body_status == "ok").all():
        url = n.body_url or n.url
        v = clasificar_texto(n.title, n.body_text or "", url, voces, medios)
        cuenta[v.nivel] += 1
        if v.nivel == "fuera" or dry_run:
            continue
        guardar(db, v, titulo=n.title, texto=n.body_text or "", url=url,
                published_at=n.published_at, auto_entry=auto_entry)
    if not dry_run:
        db.commit()
    return cuenta


def guardar(db, v: VeredictoTexto, *, titulo: str, texto: str, url: str,
            published_at=None, auto_entry: bool = False) -> int | None:
    """Mete en el corpus un texto ya clasificado. En modo sombra, un A va como fondo."""
    from app.db.models import InterpretationSource
    from scripts.research.common import clean_text, upsert_source

    if v.nivel not in ("A", "B"):
        return None
    kind = v.kind if auto_entry else "press"
    if kind == "press_interview":
        fondo = db.query(InterpretationSource).filter_by(kind="press", url=url).first()
        if fondo is not None:
            return _ascender(fondo, v)   # entró en sombra como fondo: se sube, no se duplica
    return upsert_source(db, kind=kind, url=url, title=titulo, author=v.medio,
                         published_at=published_at, content_raw=texto,
                         content_clean=clean_text(texto),
                         quality_score=0.75 if kind == "press_interview" else 0.6)


def _ascender(fuente, v: VeredictoTexto) -> int:
    """`press` → `press_interview` en la misma fila (la unicidad es kind+url). El
    embebido semanal reescribe el `kind` del payload en Qdrant."""
    fuente.kind, fuente.author, fuente.quality_score = "press_interview", v.medio, 0.75
    return fuente.id


def ascender_sombra(db, voces: list[Voz], medios: MediosCorpus) -> int:
    """Sube a `press_interview` lo que entró como `press` y hoy se clasifica como A.

    Se clasifica con `content_raw`: `clean_text` aplana los saltos de línea y con
    ellos el formato pregunta-respuesta que cuenta como cita.
    """
    from app.db.models import InterpretationSource

    subidas = 0
    for f in db.query(InterpretationSource).filter_by(kind="press").all():
        v = clasificar_texto(f.title or "", f.content_raw or f.content_clean or "", f.url,
                             voces, medios)
        if v.nivel != "A" or db.query(InterpretationSource.id).filter_by(
                kind="press_interview", url=f.url).first():
            continue
        _ascender(f, v)
        subidas += 1
        logger.info("[corpus_prensa] sube a entrevista: %s · %s", f.url, v.motivo)
    return subidas
