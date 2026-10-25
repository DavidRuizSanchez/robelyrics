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
    """Las noticias del agregador y las fuentes ya guardadas, filtrables por campo."""

    def __init__(self, noticias, fuentes=()):
        self.noticias, self.fuentes = noticias, list(fuentes)

    def query(self, modelo):
        db = self
        es_noticia = getattr(modelo, "__name__", "") == "NewsItem"

        class Q:
            filtros: dict = {}

            def filter(self, *a, **k):
                return self

            def filter_by(self, **kw):
                self.filtros = kw
                return self

            def all(self):
                if es_noticia:
                    return db.noticias
                return [f for f in db.fuentes
                        if all(getattr(f, k) == v for k, v in self.filtros.items())]

            def first(self):
                return next(iter(self.all()), None)
        return Q()

    def commit(self):
        pass


def _fuente(kind, url, title, cuerpo):
    return SimpleNamespace(id=7, kind=kind, url=url, title=title, content_raw=cuerpo,
                           content_clean=cuerpo, author="HOY", quality_score=0.6)


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


def test_lo_que_entro_como_fondo_sube_al_encender_sin_duplicarse(subidas):
    """La noticia se purga a los 7 días: si al encender no se sube lo visto en
    sombra, esa entrevista se queda de fondo para siempre."""
    fondo = _fuente("press", "https://www.hoy.es/a", _news().title, CUERPO_ENTREVISTA)
    cuenta = cp.promover(_DB([], fuentes=[fondo]), auto_entry=True)
    assert cuenta["ascendidas"] == 1 and subidas == []
    assert fondo.kind == "press_interview" and fondo.quality_score == 0.75


def test_al_encender_un_reportaje_sigue_siendo_fondo(subidas):
    fondo = _fuente("press", "https://www.hoy.es/b", "Plasencia pinta un mural de Robe",
                    CUERPO_REPORTAJE)
    cp.promover(_DB([], fuentes=[fondo]), auto_entry=True)
    assert fondo.kind == "press"


def test_en_sombra_no_se_asciende_nada(subidas):
    fondo = _fuente("press", "https://www.hoy.es/a", _news().title, CUERPO_ENTREVISTA)
    cp.promover(_DB([], fuentes=[fondo]), auto_entry=False)
    assert fondo.kind == "press"


def test_guardar_sube_en_sitio_lo_que_ya_era_fondo():
    fondo = _fuente("press", "https://www.hoy.es/a", _news().title, CUERPO_ENTREVISTA)
    v = cp.clasificar_texto(fondo.title, CUERPO_ENTREVISTA, fondo.url, VOCES, MEDIOS)
    assert cp.guardar(_DB([], fuentes=[fondo]), v, titulo=fondo.title, texto=CUERPO_ENTREVISTA,
                      url=fondo.url, auto_entry=True) == 7
    assert fondo.kind == "press_interview"


def test_la_entrevista_en_texto_es_propia_y_tiene_atribucion():
    assert cfq.atribucion({"kind": "press_interview", "author": "HOY"})
    propio, fondo = cfq.separar_material("[press_interview · HOY]\nGrabamos Agila…\n\n----\n\n"
                                         "[press · HOY]\nEl mural…")
    assert "Grabamos Agila" in propio and "El mural" in fondo


def test_las_consultas_rotan_y_robe_va_siempre():
    from scripts.research.fetch_press_interviews import consultas

    otros = [Voz(slug=f"v{i}", nombre=f"Voz{i}", relacion="amigo") for i in range(10)]
    s1, s2 = consultas([ROBE, *otros], 1, 3), consultas([ROBE, *otros], 2, 3)
    assert s1[0] == s2[0] == "entrevista Robe Iniesta"
    assert len(s1) == 4 and set(s1[1:]).isdisjoint(s2[1:])
