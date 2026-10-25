"""La prensa con cuerpo pasa al corpus antes de purgarse (Fase 4.1).

Lo que se blinda: que solo entre lo de un medio de `corpus_media` y del universo
Robe, que una entrevista sea de quien habla (no de quien sale en el titular), y que
en modo sombra NADA entre como voz.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import corpus_for_queries as cfq
from app.services import corpus_prensa as cp
from app.services.corpus_trust import ROBE, MediosCorpus, Voz

UOHO = Voz(slug="inaki-anton", nombre="Uoho", relacion="miembro", alias=("Uoho", "Iñaki Antón"))
VOCES = [ROBE, UOHO]
MEDIOS = MediosCorpus(dominios={"hoy.es": "HOY", "elperiodicoextremadura.com": "El Periódico"})
CUERPO_ENTREVISTA = (
    "Iñaki Antón repasa su etapa en Extremoduro. «Robe me llamó una noche y me dijo que "
    "fuera a Iruña a grabar Agila», recuerda. «No me sabía ni las canciones, pero él "
    "insistió y allí me quedé dieciocho años». " * 6
)
CUERPO_REPORTAJE = ("Plasencia rinde homenaje a Robe Iniesta con un mural en la calle del "
                    "Rey. El Ayuntamiento ha aprobado la propuesta. " * 12)


def test_medio_por_dominio_y_subdominio():
    assert cp.medio_de("https://www.hoy.es/cultura/x.html", MEDIOS) == "HOY"
    assert cp.medio_de("https://extremadura.hoy.es/x", MEDIOS) == "HOY"
    assert cp.medio_de("https://nohoy.es/x", MEDIOS) is None


def test_una_entrevista_a_una_voz_de_casa_es_a():
    v = cp.clasificar_texto("Uoho: «Robe me llamó una noche para grabar Agila»",
                            CUERPO_ENTREVISTA, "https://www.hoy.es/a", VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == "press_interview" and "Uoho" in v.motivo


def test_un_reportaje_sin_voz_es_fondo():
    v = cp.clasificar_texto("Plasencia pinta un mural de Robe", CUERPO_REPORTAJE,
                            "https://www.hoy.es/b", VOCES, MEDIOS)
    assert v.nivel == "B" and v.kind == "press"


@pytest.mark.parametrize("url,cuerpo,motivo", [
    ("https://blogfan.test/x", CUERPO_REPORTAJE, "corpus_media"),        # medio no reconocido
    ("https://www.hoy.es/c", "Robe. " * 20, "chars"),                     # teletipo
    ("https://www.hoy.es/d", "La Junta aprueba los presupuestos. " * 40, "no nombra"),
])
def test_lo_que_no_entra(url, cuerpo, motivo):
    v = cp.clasificar_texto("Noticia", cuerpo, url, VOCES, MEDIOS)
    assert v.nivel == "fuera" and motivo in v.motivo


def _news(**kw):
    base = dict(title="Uoho: «Robe me llamó una noche para grabar Agila»",
                body_text=CUERPO_ENTREVISTA, body_url="https://www.hoy.es/a",
                url="https://news.google.com/x", published_at=None, body_status="ok")
    return SimpleNamespace(**{**base, **kw})


class _DB:
    def __init__(self, noticias, prensa_existente=()):
        self.noticias, self.prensa = noticias, set(prensa_existente)

    def query(self, modelo):
        db = self

        class Q:
            def filter(self, *a, **k):
                return self

            def filter_by(self, kind, url):
                self.hit = kind == "press" and url in db.prensa
                return self

            def first(self):
                return 1 if self.hit else None

            def all(self):
                return db.noticias
        return Q()

    def commit(self):
        pass


@pytest.fixture
def subidas(monkeypatch):
    from app.services import corpus_trust
    from scripts.research import common

    out = []
    monkeypatch.setattr(corpus_trust, "cargar_voces", lambda db: VOCES)
    monkeypatch.setattr(cp.MediosCorpus, "desde_yaml", classmethod(lambda cls: MEDIOS))
    monkeypatch.setattr(common, "upsert_source", lambda db, **kw: out.append(kw) or 1)
    return out


def test_en_modo_sombra_nada_entra_como_voz(subidas):
    cuenta = cp.promover(_DB([_news()]), auto_entry=False)
    assert cuenta["A"] == 1 and [s["kind"] for s in subidas] == ["press"]


def test_con_entrada_automatica_la_entrevista_es_propia(subidas):
    cp.promover(_DB([_news()]), auto_entry=True)
    assert subidas[0]["kind"] == "press_interview" and subidas[0]["author"] == "HOY"
    assert subidas[0]["url"] == "https://www.hoy.es/a"       # la del medio, no la de Google News


def test_lo_que_entro_como_fondo_no_se_duplica_al_encender(subidas):
    cp.promover(_DB([_news()], prensa_existente={"https://www.hoy.es/a"}), auto_entry=True)
    assert subidas == []


def test_la_entrevista_en_texto_es_propia_y_tiene_atribucion():
    assert cfq.atribucion({"kind": "press_interview", "author": "HOY"})
    propio, fondo = cfq.separar_material("[press_interview · HOY]\nGrabamos Agila…\n\n----\n\n"
                                         "[press · HOY]\nEl mural…")
    assert "Grabamos Agila" in propio and "El mural" in fondo
