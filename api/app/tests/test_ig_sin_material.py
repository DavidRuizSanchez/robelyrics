"""Sin artículo, no hay post.

El 22-09-2026 se midió sobre la cola de producción que **177 de 212 noticias
(83,5%) se escribieron sin extracto**: solo con el titular, porque los feeds de
Google News repiten el titular en la descripción y el agregador lo vacía. Con
ese material el modelo rellenaba los huecos, y así salió publicado el item 348:
una noticia sobre la presidenta de la Junta de Extremadura ilustrada con fotos
del entrenador de fútbol y con una afinidad que ninguna fuente mencionaba.

Reproducido en vivo con el artículo real como fixture: pidiéndole al mismo
modelo la query de la foto SOLO con el titular devuelve «Guardiola entrenador de
fútbol»; con el artículo delante devuelve «María Guardiola presidenta Junta
Extremadura». El cuerpo del artículo era la diferencia entre escribir e inventar.

De ahí la regla, que se aplica en los dos sitios porque el alta manual del panel
no pasa por la selección.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, NewsItem
from app.services.instagram import editorial, publisher, topics

FIXTURES = Path(__file__).parent / "fixtures" / "caso_guardiola"
ARTICULO = (FIXTURES / "noticia.txt").read_text()

TITULAR = "Guardiola reivindica el talento y el lema inspirado en Robe en el Día de Extremadura"


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    NewsItem.__table__.create(engine)
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _noticia(db, *, titulo=TITULAR, status="ok", cuerpo=ARTICULO, **kw) -> NewsItem:
    ahora = datetime.now(UTC)
    base = dict(
        title=titulo,
        url=f"https://news.google.com/rss/articles/{abs(hash(titulo + status))}",
        source_key="gn_robe", source_name="Google News · Robe",
        source_medium="Canal Extremadura", summary="", category="Actualidad",
        policy="ig-only", relevance_score=9.0,
        published_at=ahora - timedelta(hours=2), fetched_at=ahora,
        body_status=status, body_text=cuerpo if status == "ok" else None,
        body_chars=len(cuerpo or ""), body_url="https://www.canalextremadura.es/x",
    )
    base.update(kw)
    n = NewsItem(**base)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _titulos(temas) -> list[str]:
    return [t["title"] for t in temas]


# --- La selección --------------------------------------------------------- #
def test_una_noticia_con_articulo_si_entra(db):
    _noticia(db)
    assert TITULAR in _titulos(topics.select(db, count=3))


@pytest.mark.parametrize(
    "status",
    ["blocked", "paywall_or_short", "unresolved", "unreachable", "pending"],
)
def test_sin_articulo_la_noticia_no_compite_por_un_slot(db, status):
    """`blocked` es deia.eus respondiendo 406 al bot; `unresolved`, un enlace de
    Google News que no se traduce. En ninguno de los casos hay nada que leer."""
    _noticia(db, status=status)
    assert TITULAR not in _titulos(topics.select(db, count=3))


def test_un_ok_con_el_cuerpo_vacio_tampoco_cuela(db):
    """Defensa: el estado dice `ok` pero no hay texto. Fiarse solo del estado
    dejaría pasar una fila a medio escribir."""
    _noticia(db, status="ok", cuerpo="")
    assert TITULAR not in _titulos(topics.select(db, count=3))


def test_el_tema_lleva_el_articulo_y_la_url_del_medio(db):
    """`url` es el enlace de Google News; el panel necesita el del medio para que
    su «fuente ↗» abra el artículo, que es el clic con el que se caza un post
    dudoso."""
    _noticia(db)
    tema = next(t for t in topics.select(db, count=3) if t["title"] == TITULAR)
    assert "María Guardiola" in tema["material"]
    assert tema["url_medio"] == "https://www.canalextremadura.es/x"
    assert "news.google.com" not in tema["url_medio"]


# --- La preparación (cubre el alta MANUAL, que no pasa por la selección) --- #
def _item(db, **kw) -> InstagramQueueItem:
    base = dict(
        day=date.today(), slot=1, position=0, content_type="news", title=TITULAR,
        status="proposed", attempts=0, media_type="IMAGE", media_locked=False,
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


def test_preparar_sin_material_no_llama_al_modelo(db, monkeypatch):
    """La guarda va ANTES de escribir: si saltara después, ya se habría pagado el
    token y, peor, existiría un texto inventado que alguien podría aprobar."""
    def _explota(*a, **k):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("no se escribe sin material")

    monkeypatch.setattr(editorial, "enrich", _explota)
    with pytest.raises(publisher.SinMaterial):
        publisher.prepare(db, _item(db))


def test_el_aviso_dice_como_salir_del_paso(db):
    """Un medio con WAF es un no definitivo: el UA no se disfraza (política del
    proyecto). La salida es pegar el texto, y el mensaje tiene que decirlo."""
    with pytest.raises(publisher.SinMaterial) as exc:
        publisher.prepare(db, _item(db))
    assert "pégalo" in str(exc.value)


def test_un_post_del_blog_no_necesita_cuerpo_de_articulo(db, monkeypatch):
    """El material de un post NUESTRO está en la BD, no en una descarga.

    Medido en producción el 23-09-2026: `#370` («Pedrá en directo (1995)»)
    quedó en `failed` con «no hay cuerpo del artículo» teniendo 2.102
    caracteres escritos en su post del blog. No era un caso raro: 18 de los 20
    items de la cola que vienen del blog están encolados con
    `content_type='news'`, así que desde que existe la guarda ninguno podía
    salir — y como las noticias van primero, el roto se reelegía cada 15
    minutos sin gastar intentos, porque revienta antes de publicar.
    """
    # Se corta justo después de la guarda: lo que se comprueba es que NO salta
    # `SinMaterial`, no el resto del camino (que pide red y tablas de
    # contenido). Mismo criterio que el test del clip aprobado.
    monkeypatch.setattr(publisher, "_redactar_con_corpus", lambda *a, **k: None)
    monkeypatch.setattr(publisher, "_corpus_context", lambda *a, **k: {})
    monkeypatch.setattr(publisher.robe_quote, "find_verse", lambda *a, **k: {})
    monkeypatch.setattr(publisher, "captions", type("C", (), {
        "build": staticmethod(lambda db, topic: "caption de prueba"),
    }))

    item = _item(db, category="Blog", blog_post_id=None)
    try:
        publisher.prepare(db, item)
    except publisher.SinMaterial:  # pragma: no cover - es lo que se prueba
        pytest.fail("a un post del blog no se le pide un artículo ajeno")
    except Exception:  # noqa: BLE001
        pass  # cualquier otro tropiezo es de pasos posteriores a la guarda


def test_una_noticia_ajena_sigue_necesitando_su_articulo(db, monkeypatch):
    """El arreglo de arriba no puede abrir la puerta de atrás: sin `category`
    de blog, la exigencia se mantiene intacta."""
    monkeypatch.setattr(publisher, "_corpus_context", lambda *a, **k: {})
    with pytest.raises(publisher.SinMaterial):
        publisher.prepare(db, _item(db, category="Música"))


def test_sin_material_es_distinto_de_material_pendiente(db):
    """`MaterialPendiente` significa «espera, que viene»; esto significa «no hay».
    Confundirlos dejaría un post esperando para siempre un artículo que nunca
    llegará, o descartaría un clip que solo tardaba tres minutos."""
    assert not issubclass(publisher.SinMaterial, publisher.MaterialPendiente)
    assert not issubclass(publisher.MaterialPendiente, publisher.SinMaterial)


class _RespuestaFalsa:
    """Imita la forma de la respuesta de OpenAI: `.choices[0].message.content`.

    Devuelve JSON válido a propósito. Un doble que lanzase una excepción sería
    más permisivo que la realidad: no probaría que el resto de `_generate`
    (parseo, limpieza de hashtags) sigue funcionando con el material dentro.
    """

    def __init__(self, contenido: str):
        msg = type("M", (), {"content": contenido})
        self.choices = [type("C", (), {"message": msg})]


def _openai_espia(capturado: dict):
    """Fábrica de un cliente falso que anota el prompt que sale hacia el modelo."""
    class _FakeOpenAI:
        def __init__(self, **kw):  # noqa: ANN003
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, **kw):  # noqa: ANN003
            capturado["system"] = kw["messages"][0]["content"]
            capturado["user"] = kw["messages"][1]["content"]
            return _RespuestaFalsa(
                '{"comentario": "c", "titular": "t", "image_query": "q", '
                '"image_search": "s", "hashtags": ["#X"], '
                '"slides": [{"kicker": "1997", "text": "x"}], "cierre": "z"}'
            )

    return _FakeOpenAI


# --- Que el artículo LLEGUE al modelo ------------------------------------- #
def test_el_articulo_viaja_al_prompt_entero(monkeypatch):
    """No basta con tenerlo en el topic: el fallo era que el prompt solo veía el
    titular y un extracto vacío."""
    visto = {}

    def _fake(title, summary, category, tone="neutral", *, material="", corpus="",
              content_type="news", texto_base="", entidades=None,
              correcciones=None):  # noqa: ANN001
        visto["material"] = material
        visto["title"] = title
        # El esquema es `strict` y `pregunta` va en `required`, así que la
        # respuesta real SIEMPRE trae la clave: un doble al que le faltara
        # sería más pobre que la realidad y probaría otro camino.
        return {"comentario": "cuerpo", "titular": "titular", "slides": [],
                "cierre": "", "pregunta": "", "image_query": "q",
                "image_search": "s", "hashtags": ["#X"]}

    monkeypatch.setattr(editorial, "_generate", _fake)
    editorial.enrich({
        "title": TITULAR, "summary": "", "category": "Actualidad",
        "material": ARTICULO,
    })
    assert "María Guardiola" in visto["material"]
    assert "presidenta de la Junta de Extremadura" in visto["material"]


def test_el_cuerpo_va_dentro_del_mensaje_que_recibe_el_modelo(monkeypatch):
    """Comprobación de cableado: que `_generate` reciba el material no prueba que
    acabe en el prompt. Se afirma sobre el texto REAL que sale hacia OpenAI."""
    capturado: dict = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(editorial, "OpenAI", _openai_espia(capturado))

    datos = editorial._generate(TITULAR, "", "Actualidad", material=ARTICULO)

    assert datos["comentario"] == "c", "el resto de _generate tiene que seguir funcionando"
    assert "María Guardiola" in capturado["user"]
    assert "presidenta de la Junta de Extremadura" in capturado["user"]


def test_sin_material_el_prompt_lo_dice_en_vez_de_callarselo(monkeypatch):
    """Si algún día se llama sin material, el modelo tiene que ver que NO hay
    artículo. Callárselo es invitarle a rellenar con lo que sepa de memoria."""
    capturado: dict = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(editorial, "OpenAI", _openai_espia(capturado))

    editorial._generate(TITULAR, "", "Actualidad", material="")
    assert "(no disponible)" in capturado["user"]


def test_el_articulo_se_capa_para_no_pagar_el_pie_de_foto(monkeypatch):
    capturado: dict = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(editorial, "OpenAI", _openai_espia(capturado))

    editorial._generate("t", "", "c", material="x" * 99_999)
    assert "x" * (editorial.MAX_MATERIAL_CHARS + 1) not in capturado["user"]


def test_prepare_recupera_el_articulo_de_la_noticia(db, monkeypatch):
    """El fallo que solo se vio corriendo el pipeline entero en producción.

    `topics.select` elige los temas CON material, pero `prepare` reconstruye el
    topic desde la fila de la cola, que no lo guarda: los dos temas del día se
    eligieron bien y se descartaron acto seguido por «no hay cuerpo del
    artículo». El único hilo entre la cola y el texto es `news_item_id`, y hay
    que tirar de él aquí — también porque re-preparar desde el panel ocurre
    cuando de aquel tema ya no queda nada.
    """
    noticia = _noticia(db)
    item = _item(db, news_item_id=noticia.id)

    visto = {}

    def _espia(topic):
        visto["material"] = topic.get("material", "")
        raise RuntimeError("corta aquí: ya tengo el topic")

    monkeypatch.setattr(editorial, "enrich", _espia)
    with pytest.raises(RuntimeError):
        publisher.prepare(db, item)

    assert "María Guardiola" in visto["material"], "el artículo no llegó a prepare"
