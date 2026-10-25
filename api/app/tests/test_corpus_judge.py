"""El juez post-transcripción solo puede bajar de nivel, y ante la duda baja.

Lo que se blinda: que un A que no supera al juez NUNCA acabe en un kind de
`embed_robe_voice.VOICE_KINDS` (la voz de Robe que usa el consultorio), y que un
juez caído no deje pasar nada como voz.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routers import ingest
from app.services import corpus_judge
from app.services.corpus_judge import Juicio, extracto, juzgar, revisar
from app.services.corpus_trust import ROBE, Voz
from scripts.research.embed_robe_voice import VOICE_KINDS

UOHO = Voz(slug="inaki-anton", nombre="Uoho", relacion="miembro", alias=("Uoho",))


@pytest.fixture(autouse=True)
def _voces(monkeypatch):
    from app.services import corpus_trust
    monkeypatch.setattr(corpus_trust, "cargar_voces", lambda db: [ROBE, UOHO])


def _fila(kind="robe_interview", nivel="A", voces=("robe-iniesta",)):
    return SimpleNamespace(kind=kind, nivel=nivel, voces=list(voces), motivos=["voz: Robe"],
                           title="ENTREVISTA A ROBE EN CANAL EXTREMADURA RADIO",
                           channel="Woody Amores", url="https://youtu.be/x", author=None,
                           published_at=None, status="processing", error=None, done_at=None)


def _llm(respuesta):
    llamadas = []

    def f(system, user):
        llamadas.append((system, user))
        return respuesta
    f.llamadas = llamadas
    return f


def test_si_habla_y_de_robe_se_queda_como_voz():
    fila = _fila()
    j = revisar(None, fila, "Yo escribí Agila en una casa…",
                llm=_llm({"habla": "sí", "de_robe": "si", "motivo": "responde en 1ª persona"}))
    assert j.pasa and fila.kind == "robe_interview" and fila.nivel == "A"
    assert "pasa" in fila.motivos[-1]


@pytest.mark.parametrize("respuesta", [
    {"habla": "no", "de_robe": "si", "motivo": "es un locutor hablando de Robe"},
    {"habla": "si", "de_robe": "no", "motivo": "Uoho habla de Inconscientes"},
    {"habla": "duda", "de_robe": "si"},
    {},                                    # juez caído o sin clave
    {"habla": "quizá", "de_robe": "si"},   # respuesta fuera de contrato
])
def test_lo_que_no_pasa_baja_a_fondo_y_nunca_a_la_voz_de_robe(respuesta):
    fila = _fila()
    revisar(None, fila, "texto de la transcripción", llm=_llm(respuesta))
    assert fila.kind == corpus_judge.DESTINO_SI_NO_PASA and fila.nivel == "B"
    assert fila.kind not in VOICE_KINDS
    assert any("baja de A" in m for m in fila.motivos)


def test_el_testimonio_del_entorno_se_juzga_por_su_voz_no_por_robe():
    fila = _fila(kind="entorno_interview", voces=("robe-iniesta", "inaki-anton"))
    llm = _llm({"habla": "si", "de_robe": "si"})
    revisar(None, fila, "Con Robe grabamos…", llm=llm)
    system, user = llm.llamadas[0]
    assert "VOZ: Uoho" in user and "¿Uoho habla en primera persona" in system
    assert fila.kind == "entorno_interview"


@pytest.mark.parametrize("nivel", ["B", "C", None])
def test_solo_se_juzga_el_nivel_a(nivel):
    fila = _fila(kind="media_report", nivel=nivel)

    def no_llamar(*_):
        raise AssertionError("solo se juzga el A")

    assert revisar(None, fila, "texto", llm=no_llamar) is None
    assert fila.kind == "media_report"


def test_una_excepcion_del_juez_cuenta_como_duda_sin_juzgar():
    def roto(*_):
        raise TimeoutError("openai")

    assert juzgar("Robe", "t", "c", "texto", llm=roto) == Juicio(
        "duda", "duda", "no se ha podido consultar al juez", juzgado=False)


def test_el_extracto_no_se_queda_con_la_presentacion():
    texto = "BIENVENIDOS" + "P" * 4500 + "MITAD" + "Q" * 5000
    ex = extracto(texto)
    assert len(ex) < 3200 and "MITAD" in ex and "BIENVENIDOS" not in ex


def test_complete_guarda_con_el_kind_que_deja_el_juez(monkeypatch):
    from scripts.research import common

    guardado = {}
    monkeypatch.setattr(common, "upsert_source", lambda db, **kw: guardado.update(kw) or 9)
    monkeypatch.setattr(corpus_judge, "_llm_por_defecto",
                        lambda s, u: {"habla": "no", "de_robe": "si"})

    class _DB:
        def __init__(self, row):
            self.row = row

        def get(self, *_):
            return self.row

        def commit(self):
            pass

    fila = _fila()
    payload = ingest.CompleteIn.model_validate({"content_clean": "Bienvenidos al programa " * 4})
    assert ingest.complete(51, payload, _DB(fila)).status == "done"
    assert guardado["kind"] == "media_report" and fila.nivel == "B"


def test_el_extracto_lleva_las_menciones_que_las_ventanas_no_ven():
    # Caso real: Uoho en ABC. Sus menciones de Robe caían fuera de las ventanas.
    texto = ("x" * 2000 + " nos quedamos Robe Cantera y yo solos " + "y" * 6000
             + " no aterricé en extremo duro, me aterrizaron " + "z" * 6000)
    ex = extracto(texto)
    assert "Robe Cantera" in ex and "extremo duro" in ex
    assert len(ex) < 3 * 1000 + 3 * 500 + 40


def test_un_juez_caido_baja_pero_queda_pendiente_y_uno_que_dice_no_no():
    caido, negado = _fila(), _fila()
    revisar(None, caido, "Yo escribí Agila…", llm=_llm({}))
    revisar(None, negado, "Yo escribí Agila…", llm=_llm({"habla": "no", "de_robe": "si"}))
    assert caido.kind == negado.kind == corpus_judge.DESTINO_SI_NO_PASA
    assert corpus_judge._pendiente(caido) == "robe_interview"
    assert corpus_judge._pendiente(negado) is None


class _BD:
    """Lo justo de una sesión: la cola en `done` y sus fuentes por (kind, url)."""

    def __init__(self, filas, fuentes):
        self.filas, self.fuentes, self.commits = filas, fuentes, 0

    def query(self, *modelo):
        bd = self

        class Q:
            clave = None

            def filter(self, *a):
                return self

            def filter_by(self, kind, url):
                self.clave = (kind, url)
                return self

            def all(self):
                return bd.filas

            def one_or_none(self):
                return next((f for f in bd.fuentes if (f.kind, f.url) == self.clave), None)

            first = one_or_none
        return Q()

    def commit(self):
        self.commits += 1


def _pendiente_en_bd():
    fila = _fila()
    revisar(None, fila, "x", llm=_llm({}))
    fila.status = "done"
    fuente = SimpleNamespace(kind=fila.kind, url=fila.url, content_clean="Yo escribí Agila…")
    return fila, fuente, _BD([fila], [fuente])


def test_rejuzgar_devuelve_su_voz_a_quien_si_hablaba():
    fila, fuente, bd = _pendiente_en_bd()
    cuenta = corpus_judge.rejuzgar_pendientes(bd, llm=_llm({"habla": "si", "de_robe": "si"}))
    assert cuenta["pasa"] == 1
    assert fila.kind == fuente.kind == "robe_interview" and fila.nivel == "A"
    # Ya resuelto: una segunda pasada no lo vuelve a tocar.
    assert corpus_judge._pendiente(fila) is None


@pytest.mark.parametrize("respuesta,pendiente", [({}, True), ({"habla": "no", "de_robe": "si"}, False)])
def test_rejuzgar_no_sube_a_nadie_sin_veredicto(respuesta, pendiente):
    fila, fuente, bd = _pendiente_en_bd()
    corpus_judge.rejuzgar_pendientes(bd, llm=_llm(respuesta))
    assert fila.kind == fuente.kind == corpus_judge.DESTINO_SI_NO_PASA and fila.nivel == "B"
    assert (corpus_judge._pendiente(fila) is not None) is pendiente
