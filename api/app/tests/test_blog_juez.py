"""Que lo aprobado pase el juez (plan del blog, 18-11-2026).

El aniversario de «Destrozares» (#368) murió el día de publicar: el encargo pedía «el
sello» (que no estaba en ninguna parte), el verificador se comía la fecha que sí estaba
y el juez lo descartó sin reintento. Estos tests fijan cada pieza del arreglo.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services import album_facts, piece_checklist
from app.services.blog_gates import Juicio, motivos_de_dato

DESTROZARES_WIKI = """{{Ficha de álbum
|nombre          = Destrozares, canciones para el final de los tiempos
|artista         = [[Roberto Iniesta|Robe]]
|publicación     = 18 de noviembre de 2016
|grabación       = 2016
|discográfica    = [[El Dromedario Records]]
|productor       = José Luis Crespo
|posicionamiento =*N.º 5<ref name="x">{{cita web |url=http://a}}</ref>
|misceláneo   = {{Ficha de álbum/Sencillos
|single 1        = Por encima del bien y del mal
|single 1 fecha  = 28 de octubre de 2016
}}
}}
'''''Destrozares''''' es el segundo álbum…"""


# --------------------------------------------------------------------------- #
# El listón: solo se pide lo que hay, y lo buscable se busca antes
# --------------------------------------------------------------------------- #
HECHOS = ("Fecha de publicación: 2016-11-18.\nSello: El Dromedario Records.\n"
          "Tracklist (10 cortes): 1. Hoy al mundo renuncio.\nDiscografía: A (2015); B (2016).")


def test_lo_que_no_consta_no_se_pide_y_el_juez_lo_sabe():
    lst = piece_checklist.liston("album-anniversary", "Fecha de publicación: 2016-11-18.")
    claves = {p.clave for p in lst.exigibles}
    assert "fecha" in claves and "sello" not in claves
    assert "el sello que lo editó" not in lst.encargo()
    assert "el sello que lo editó" in lst.para_el_juez()


def test_lo_buscable_se_busca_antes_y_solo_cuenta_si_aparece():
    pend = {p.clave for p in piece_checklist.pendientes("album-anniversary", HECHOS)}
    assert pend == {"grabacion", "sonido", "curiosidades"}
    sin = piece_checklist.liston("album-anniversary", HECHOS)
    con = piece_checklist.liston("album-anniversary", HECHOS, {"grabacion"})
    assert "grabacion" not in {p.clave for p in sin.exigibles}
    assert "grabacion" in {p.clave for p in con.exigibles}


def test_el_foco_no_recorta_lo_que_pide_el_encargo():
    lst = piece_checklist.liston("album-anniversary", HECHOS)
    assert "trayectoria" in lst.enfoque() and "no se recortan" in lst.enfoque()


def test_un_tipo_sin_lista_no_cambia_nada():
    assert piece_checklist.liston("evergreen", HECHOS) is None


# --------------------------------------------------------------------------- #
# Datos de edición del disco
# --------------------------------------------------------------------------- #
def test_ficha_de_wikipedia():
    f = album_facts.ficha_wikipedia(DESTROZARES_WIKI)
    assert f["discografica"] == "El Dromedario Records"
    assert f["productor"] == "José Luis Crespo"
    assert f["sencillo"] == "Por encima del bien y del mal"
    assert f["artista"] == "Robe"


class _Http:
    """MusicBrainz falso: dos ediciones, la reedición posterior con otro sello."""

    def __init__(self, releases, sellos):
        self.releases, self.sellos = releases, sellos

    def get(self, url, params=None):
        if "/release-group/" in url:
            return SimpleNamespace(status_code=200, json=lambda: {"releases": self.releases})
        rid = url.rsplit("/", 1)[-1]
        return SimpleNamespace(status_code=200, json=lambda: {"label-info": [
            {"label": {"name": n}} for n in self.sellos.get(rid, [])]})


def test_el_sello_es_el_de_la_primera_edicion(monkeypatch):
    # «Agila» salía con DRO y con Warner Music Spain (reedición).
    monkeypatch.setattr(album_facts.time, "sleep", lambda s: None)
    http = _Http([{"id": "a", "date": "1996-04-10"}, {"id": "b", "date": "2011-01-01"},
                  {"id": "c", "date": "1996-04-10"}],
                 {"a": ["DRO"], "b": ["Warner Music Spain"], "c": []})
    assert album_facts.sellos_musicbrainz(http, "rg") == ["DRO"]


class _DbCanciones:
    def execute(self, _stmt):
        return self

    def scalars(self):
        return ["Por encima del bien y del mal", "Destrozares"]


def test_productor_sin_corpus_no_entra(monkeypatch):
    monkeypatch.setattr(album_facts, "corroborado_en_corpus", lambda *a, **k: None)
    album = SimpleNamespace(id=29, title="Destrozares, canciones para el final de los tiempos")
    datos = album_facts.datos_corroborados(
        _DbCanciones(), album, release_group="rg", sellos_mb=["El Dromedario Records"],
        wiki=("Destrozares", DESTROZARES_WIKI))
    campos = [d.campo for d in datos]
    assert "productor" not in campos and "estudio" not in campos
    assert campos[0] == "sello"
    assert len(datos[0].fuentes) == 2  # MusicBrainz y Wikipedia coinciden
    # La grabación de la ficha sí entra (David, 19-11-2026: vale como dato).
    assert all(c in ("sello", "grabacion", "seccion", "listas") for c in campos)


def test_productor_corroborado_se_dice_como_participacion(monkeypatch):
    llamadas = []

    def falso(db, titulo, valor, contexto=None):
        llamadas.append((valor, contexto))
        return {"kind": "corpus", "tier": "T2", "url": "x", "cita": "rueda de prensa"} \
            if valor == "José Luis Crespo" else None

    monkeypatch.setattr(album_facts, "corroborado_en_corpus", falso)
    album = SimpleNamespace(id=29, title="Destrozares")
    datos = album_facts.datos_corroborados(_DbCanciones(), album, release_group=None, sellos_mb=[],
                                           wiki=("Destrozares", DESTROZARES_WIKI))
    prod = next(d for d in datos if d.campo == "productor")
    assert prod.linea() == "Producción: participó José Luis Crespo."
    # Que el nombre salga cerca del disco no basta: tiene que ir junto a «produc…».
    assert ("José Luis Crespo", "produc") in llamadas


# --------------------------------------------------------------------------- #
# Una caída del buscador no es «no encontrado»
# --------------------------------------------------------------------------- #
def test_una_busqueda_fallida_no_se_cachea(monkeypatch):
    from app.services import web_verify

    guardado = {}
    monkeypatch.setattr(web_verify, "_load_cache", lambda: dict(guardado))
    monkeypatch.setattr(web_verify, "_save_cache", lambda c: guardado.update(c))

    def caida(query, wiki, estado=None):
        estado["fallo"] = True
        return ""

    monkeypatch.setattr(web_verify, "_gather_evidence", caida)
    r = web_verify.classify_fact("Destrozares se grabó en Berriz", query="x")
    assert r["verdict"] == "not_found" and r.get("sin_red") is True
    assert guardado == {}


# --------------------------------------------------------------------------- #
# Motivos que piden un dato vs motivos de estilo
# --------------------------------------------------------------------------- #
def test_motivos_de_dato():
    motivos = ["No identifica el sello ni da la fecha.", "Repite «violín» en tres secciones."]
    assert motivos_de_dato(motivos) == ["No identifica el sello ni da la fecha."]


# --------------------------------------------------------------------------- #
# El juicio al preparar: reescribe con los motivos y se queda la mejor
# --------------------------------------------------------------------------- #
import pytest


@pytest.fixture(autouse=True)
def _sin_minimo_de_material(monkeypatch):
    """Los borradores de juguete («v0») son cortos: el mínimo se prueba aparte."""
    from app.services import draft_generator as dg
    monkeypatch.setattr(dg, "MIN_CUERPO_CON_LISTON", 0)


def _propuesta(**kw):
    base = dict(id=1, kind="album-anniversary", title="10 años", target_keyword="Destrozares",
                body_md="v0", excerpt=None, meta_title=None, meta_description=None,
                entities=[], review_verdict=None, review_score=None, review_reasons=None,
                reviewed_at=None, review_attempts=0, source_type="album", source_id=29)
    base.update(kw)
    return SimpleNamespace(**base)


def test_reescribe_con_los_motivos_y_guarda_el_veredicto(monkeypatch):
    from app.services import draft_generator as dg

    veredictos = iter([Juicio(False, "rigor", ["repite violín"], 58, "v0"),
                       Juicio(True, None, [], 76, "v1 tensado")])
    vistos = []

    def regenera(db, p, persist=True, juzgar=True):
        vistos.append(dg._CORRECCIONES.get())
        p.body_md = "v1"
        return True

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: next(veredictos))
    monkeypatch.setattr(dg, "generate_proposal_draft", regenera)
    p = _propuesta()
    dg.juzgar_borrador(None, p)
    assert vistos == ["repite violín"]          # el redactor vio el motivo
    assert dg._CORRECCIONES.get() == ""          # y no se queda pegado
    assert p.review_verdict == "pasa" and p.review_score == 76
    assert p.body_md == "v1 tensado" and p.review_attempts == 2


def test_si_no_mejora_se_queda_la_version_anterior_y_retenida(monkeypatch):
    from app.services import draft_generator as dg

    veredictos = iter([Juicio(False, "rigor", ["genérica"], 60, "v0"),
                       Juicio(False, "rigor", ["peor"], 40, "v1"),
                       Juicio(False, "rigor", ["peor aún"], 30, "v2")])

    def regenera(db, p, persist=True, juzgar=True):
        p.body_md = "nuevo"
        return True

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: next(veredictos))
    monkeypatch.setattr(dg, "generate_proposal_draft", regenera)
    p = _propuesta()
    dg.juzgar_borrador(None, p)
    # Aniversario de disco (central) en la frontera: a la lectura de David, no se tira.
    assert p.body_md == "v0" and p.review_verdict == "para_tu_lectura" and p.review_score == 60
    assert p.review_reasons["motivos"] == ["genérica"]


def test_las_noticias_no_pasan_por_aqui():
    from app.services import draft_generator as dg

    assert dg.juzgar_borrador(None, _propuesta(kind="news")) is None


# --------------------------------------------------------------------------- #
# Dos fuentes del corpus: juntos en un tramo, no sueltos por el documento
# --------------------------------------------------------------------------- #
def test_las_claves_tienen_que_salir_juntas():
    from app.services.corpus_for_queries import _juntos

    cerca = "Grabamos Destrozares en Lorentzo Records, en Berriz, con Aitor."
    lejos = "Destrozares salió en 2016. " + "relleno " * 200 + "Lorentzo Records está en Berriz."
    claves = ["Destrozares", "Lorentzo", "Berriz"]
    assert _juntos(cerca, claves)
    assert not _juntos(lejos, claves)


def test_la_localizacion_no_distingue_tildes():
    """Caso del #553 (20-11-2026): ¡HOLA! escribe «Alen» y la casa «Alén»."""
    from app.services.corpus_for_queries import _juntos, _plegar, tramos_con

    articulo = ("La reina Letizia entregó en Toledo la Medalla de Oro al Mérito en las "
                "Bellas Artes, que recogió Alen Ayerdi, viuda de Robe.")
    hecho = "Alén Ayerdi recogió en Toledo la Medalla de Oro."
    assert _juntos(articulo, ["Alén", "Toledo"])
    trozo = tramos_con(articulo, hecho)
    assert "Alen Ayerdi" in trozo                 # recorta el ORIGINAL, no el plegado
    # Al revés también: la fuente con tilde y el hecho sin ella.
    assert tramos_con(articulo.replace("Alen", "Alén"), hecho.replace("Alén", "Alen"))
    # La ñ no se pliega, y el plegado conserva la longitud (las posiciones valen).
    assert _plegar("Peña Ángel") == "peña angel"
    assert len(_plegar("İstanbul Áéü")) == len("İstanbul Áéü")


class _DbFuentes:
    def __init__(self, filas):
        self.filas = filas

    def execute(self, *_a, **_k):
        return self

    def all(self):
        return self.filas


def test_dos_autores_distintos_y_juntos():
    from app.services.corpus_for_queries import en_dos_fuentes

    texto = "Destrozares se grabó en Lorentzo Records, en Berriz."
    dos = _DbFuentes([("Robe", "rueda de prensa", texto), ("Mondo Sonoro", "crítica", texto)])
    uno = _DbFuentes([("Robe", "rueda", texto), ("Robe", "otra", texto)])
    h = "Destrozares se grabó en Lorentzo Records, en Berriz."
    assert en_dos_fuentes(dos, h) == ["rueda de prensa", "crítica"]
    assert en_dos_fuentes(uno, h) == []          # el mismo autor no se corrobora a sí mismo
    assert en_dos_fuentes(dos, "Destrozares se grabó en cinco conciertos.") == []  # una clave


def test_con_la_web_caida_una_obra_no_se_refuta(monkeypatch):
    from app.services import fact_check

    monkeypatch.setattr("app.services.web_verify.classify_fact",
                        lambda text, **k: {"verdict": "not_found", "evidence": "", "source": "",
                                           "sin_red": True})
    claim = fact_check.Claim(type="work_exists", subject="Destrozares", text="Robe publicó Destrozares",
                             risk="high")
    v = fact_check._resolve_web(claim)
    assert v.status == "unverifiable" and v.source == "sin_red"
    rep = fact_check.FactCheckReport(verdicts=[v])
    assert rep.to_review == []


def test_el_aniversario_enlaza_la_ficha_del_disco_y_no_la_cancion():
    from app.services.draft_generator import enlazar_ficha_del_disco

    titulo = "Destrozares, Canciones para el Final de los Tiempos"
    body = ("## Destrozares cumple diez años\n\n«Destrozares, canciones para el final de los "
            "tiempos» salió en 2016. Cierra con «Destrozares».")
    out = enlazar_ficha_del_disco(body, titulo, "/robe/destrozares")
    assert "[Destrozares, canciones para el final de los tiempos](/robe/destrozares)" in out
    assert out.startswith("## Destrozares cumple")       # el heading no se toca
    assert out.count("](/robe/destrozares)") == 1
    assert enlazar_ficha_del_disco(out, titulo, "/robe/destrozares") == out  # idempotente


def test_el_material_propio_confirma_sin_ir_a_la_web(monkeypatch):
    from app.services import fact_check

    claim = fact_check.Claim(type="other", subject="Destrozares",
                             text="«Hoy al mundo renuncio» abre «Destrozares».", risk="high")
    monkeypatch.setattr(fact_check, "extract_claims", lambda body, **k: [claim])
    monkeypatch.setattr(fact_check, "extract_catalog_claims", lambda body, idx: [])
    monkeypatch.setattr(fact_check, "build_catalog_index", lambda db: None)
    monkeypatch.setattr(fact_check, "_resolve_db", lambda idx, c: None)
    llamadas = []
    monkeypatch.setattr(fact_check, "resolve_claim",
                        lambda *a, **k: llamadas.append(1) or fact_check.Verdict(
                            claim, "unverifiable", evidence="", source="web"))
    monkeypatch.setattr("app.services.web_verify.classify_with_evidence",
                        lambda claim, ev: "supported")
    material = "«Destrozares» (Robe, 2016). Tracklist (10 cortes): 1. Hoy al mundo renuncio; 2. …"
    rep = fact_check.check_body(None, "x", material=material)
    assert rep.verdicts[0].status == "confirmed" and rep.verdicts[0].source == "material"
    assert llamadas == [] and rep.to_review == []
    # Sin material, va a la web como siempre.
    rep = fact_check.check_body(None, "x")
    assert llamadas == [1]


def test_posicion_en_el_disco_contra_el_tracklist():
    from app.services.fact_check import posicion_confirmada

    mat = ("Tracklist (10 cortes): 1. Hoy al mundo renuncio; 2. El cielo cambió de forma; "
           "3. Querré lo prohibido; 9. La canción más triste; 10. Destrozares.")
    assert posicion_confirmada(mat, "«Hoy al mundo renuncio» abre el disco.")
    assert posicion_confirmada(mat, "«El cielo cambió de forma» ocupa el segundo lugar del disco.")
    assert posicion_confirmada(mat, "«Destrozares» cierra el disco.")
    assert posicion_confirmada(mat, "«La canción más triste» es el penúltimo corte.")
    assert not posicion_confirmada(mat, "«Querré lo prohibido» ocupa el quinto lugar del disco.")
    assert not posicion_confirmada(mat, "«Canción inventada» abre el disco.")


def test_nombres_juntos_no_bastan_decide_el_juez(monkeypatch):
    """«José Luis Crespo fundó El Dromedario Records»: los dos nombres están juntos en los
    hechos duros, pero el material no dice eso. Sin el «sí» del juez, no se confirma."""
    from app.services import fact_check
    from app.services.corpus_for_queries import tramos_con

    material = "Sello: El Dromedario Records.\nProducción: participó José Luis Crespo."
    falso = "José Luis Crespo fundó El Dromedario Records."
    assert tramos_con(material, falso)            # localiza…
    claim = fact_check.Claim(type="person_fact", subject="Crespo", text=falso, risk="medium")
    monkeypatch.setattr("app.services.web_verify.classify_with_evidence",
                        lambda c, ev: "not_found")
    monkeypatch.setattr(fact_check, "_resolve_db", lambda idx, c: None)
    monkeypatch.setattr(fact_check, "resolve_claim", lambda *a, **k: fact_check.Verdict(
        claim, "unverifiable", evidence="", source="web"))
    v = fact_check._resolver_con_material(None, claim, None, material, True)
    assert v.status != "confirmed"                # …pero no confirma


def test_un_campo_vacio_no_se_traga_el_siguiente():
    f = album_facts.ficha_wikipedia("|calificación    = \n|posicionamiento =*N.º 5<ref>x</ref>\n")
    assert "calificacion" not in f and f["posicionamiento"].startswith("*N.º 5")


def test_pieza_central_en_la_frontera_va_a_tu_lectura(monkeypatch):
    from app.services import draft_generator as dg

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: Juicio(False, "rigor", ["falta grabación"], 58, "v0"))
    p = _propuesta()
    dg.juzgar_borrador(None, p, reescribir=False)
    assert p.review_verdict == "para_tu_lectura"


def test_lo_que_no_es_central_o_cae_por_otro_filtro_se_retiene(monkeypatch):
    from app.services import draft_generator as dg

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: Juicio(False, "rigor", ["x"], 58, "v0"))
    p = _propuesta(kind="spotlight")
    dg.juzgar_borrador(None, p, reescribir=False)
    assert p.review_verdict == "retenida"
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: Juicio(False, "lyrics", ["verso"], 80, "v0"))
    p = _propuesta()
    dg.juzgar_borrador(None, p, reescribir=False)
    assert p.review_verdict == "retenida"


def test_numero_de_canciones_contra_el_tracklist():
    from app.services.fact_check import posicion_confirmada

    mat = "Tracklist (10 cortes): 1. Hoy al mundo renuncio; 10. Destrozares."
    assert posicion_confirmada(mat, "«Destrozares» contiene diez canciones.")
    assert posicion_confirmada(mat, "El álbum reúne 10 cortes.")
    assert not posicion_confirmada(mat, "«Destrozares» contiene doce canciones.")


def test_sin_saber_la_busqueda_lo_buscable_no_se_declara_inexistente():
    lst = piece_checklist.liston("album-anniversary", HECHOS)       # el juez: sin con_material
    assert "el sonido y la formación que lo toca" not in lst.para_el_juez()
    lst2 = piece_checklist.liston("album-anniversary", HECHOS, set())  # el redactor: nada hallado
    assert "el sonido y la formación que lo toca" in lst2.para_el_juez()


def test_un_fragmento_con_el_numero_no_confirma_la_frase():
    from app.services.fact_check import posicion_confirmada

    mat = "Tracklist (10 cortes): 1. Hoy al mundo renuncio; 10. Destrozares."
    assert not posicion_confirmada(mat, "Las diez canciones se grabaron en Berriz.")


class _DbPersonas:
    def __init__(self, filas):
        self.filas = filas

    def query(self, *_a):
        return self.filas


def test_nombre_con_errata_de_transcripcion():
    from app.services.blog_gates import nombres_dudosos

    db = _DbPersonas([("Alber Fuentes", "Alber Fuentes"), ("Carlitos Pérez", "Carlos Pérez"),
                      ("Álvaro Rodríguez", "Álvaro Rodríguez Barroso"), ("José Rodríguez", "José Rodríguez")])
    texto = ("Álvaro Fuentes le presentó a los músicos. Carlitos Pérez tocó el violín y "
             "Álvaro Rodríguez el piano. Juan Rodríguez estaba allí.")
    assert nombres_dudosos(db, texto) == [("Álvaro Fuentes", "Alber Fuentes")]


def test_extraccion_fallida_no_es_limpio(monkeypatch):
    from app.services import fact_check

    def falla(*a, **k):
        raise fact_check.ExtraccionFallida("x")

    monkeypatch.setattr(fact_check, "extract_claims", falla)
    monkeypatch.setattr(fact_check, "extract_catalog_claims", lambda body, idx: [])
    monkeypatch.setattr(fact_check, "build_catalog_index", lambda db: None)
    rep = fact_check.check_body(None, "texto")
    assert rep.extraccion_fallida and rep.verdicts == []


def test_variantes_y_familiares_no_son_erratas():
    from app.services.blog_gates import nombres_dudosos

    db = _DbPersonas([("Manolo Chinato", "Manuel Muñoz"), ("Fermín Muguruza", "Fermín Muguruza"),
                      ("Fito", "Adolfo Cabrales")])
    texto = "Manolillo Chinato recitó. Iñigo Muguruza tocó con su hermano. Fito Cabrales cantó."
    assert nombres_dudosos(db, texto) == []


# --------------------------------------------------------------------------- #
# Corta tras verificar: falta material, no estilo (#399, 18-11-2026)
# --------------------------------------------------------------------------- #
def test_corta_busca_material_amplio_antes_de_juzgar(monkeypatch):
    from app.services import draft_generator as dg

    monkeypatch.setattr(dg, "MIN_CUERPO_CON_LISTON", 50)
    amplia = []

    def regenera(db, p, persist=True, juzgar=True):
        amplia.append(dg._BUSQUEDA_AMPLIA.get())
        p.body_md = "x" * 80
        return True

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: Juicio(True, None, [], 70, p.body_md))
    monkeypatch.setattr(dg, "generate_proposal_draft", regenera)
    p = _propuesta(body_md="corto")
    dg.juzgar_borrador(None, p)
    assert amplia == [True] and dg._BUSQUEDA_AMPLIA.get() is False
    assert p.review_verdict == "pasa" and p.body_md == "x" * 80


def test_si_sigue_corta_se_retiene_por_material_sin_reescrituras_a_ciegas(monkeypatch):
    from app.services import draft_generator as dg

    monkeypatch.setattr(dg, "MIN_CUERPO_CON_LISTON", 50)
    llamadas = []

    def regenera(db, p, persist=True, juzgar=True):
        llamadas.append(dg._CORRECCIONES.get())
        p.body_md = "igual"
        return True

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar", lambda db, p, hard: Juicio(True, None, [], 70, p.body_md))
    monkeypatch.setattr(dg, "generate_proposal_draft", regenera)
    p = _propuesta(body_md="corto")
    dg.juzgar_borrador(None, p)
    assert llamadas == [""]                      # solo la búsqueda amplia, sin estilo
    assert p.body_md == "corto"                  # la amplia no mejoró: se queda la previa
    assert p.review_verdict == "retenida" and p.review_reasons["bloquea"] == "material"


def test_los_videos_no_cuentan_para_el_minimo(monkeypatch):
    from app.services import draft_generator as dg

    monkeypatch.setattr(dg, "MIN_CUERPO_CON_LISTON", 30)
    p = _propuesta(body_md="texto corto\n\nhttps://www.youtube.com/watch?v=OcXZqMVb6lU" * 1)
    assert dg._corta(p)
    assert not dg._corta(_propuesta(kind="evergreen", source_type="seo", body_md="x"))


def test_lo_que_se_guarda_es_lo_que_se_juzgo_aunque_no_pase(monkeypatch):
    """#417: el foco recortó dos secciones, el juez leyó el recorte y se guardó el texto
    entero, con cinco menciones a un medio. «Para tu lectura» tiene que enseñar lo
    juzgado."""
    from app.services import draft_generator as dg

    monkeypatch.setattr(dg, "hechos_de_propuesta", lambda db, p: "")
    monkeypatch.setattr(dg, "_juzgar",
                        lambda db, p, hard: Juicio(False, "rigor", ["x"], 58, "recortado"))
    monkeypatch.setattr(dg, "generate_proposal_draft", lambda db, p, **k: False)
    p = _propuesta(body_md="entero con secciones fuera de foco")
    dg.juzgar_borrador(None, p)
    assert p.body_md == "recortado" and p.review_verdict == "para_tu_lectura"


def test_hablar_del_material_es_una_confesion():
    from app.services.source_guard import quitar_confesiones

    texto = ("El comunicado planteó tocar una vez más. El material confirma que el plan "
             "se anunció, no que la gira llegara a celebrarse.")
    limpio, quitadas = quitar_confesiones(texto)
    assert limpio == "El comunicado planteó tocar una vez más." and len(quitadas) == 1
    # Un disco que se llama así, entre comillas, no es confesión.
    assert quitar_confesiones("Salió «Material defectuoso» en 2011.")[1] == []


def test_el_encargo_del_disco_no_pide_un_verso_por_cancion():
    """David (18-11-2026): «enumerar canciones y decir los versos que tienen cansa»; varias
    sí, pero de forma dinámica y aportando valor. El encargo busca anécdotas."""
    from app.services.draft_generator import ESTILO_DISCO

    con = piece_checklist.liston("album-anniversary", HECHOS, {"curiosidades"})
    assert "NO un repaso del tracklist" in con.encargo()
    assert "anécdotas" in con.encargo()
    assert "canción-verso" in ESTILO_DISCO


def test_sin_red_no_manda_a_revision_pero_al_preparar_si_para():
    from app.services import fact_check

    claim = fact_check.Claim(type="other", subject="Se nos lleva el aire",
                             text="Se grabó en El Cielo, Madrid", risk="high")
    v = fact_check.Verdict(claim, "unverifiable", evidence="sin comprobar", source="sin_red")
    rep = fact_check.FactCheckReport(verdicts=[v])
    assert rep.to_review == [] and rep.sin_comprobar == [v]


def test_la_consulta_va_sin_los_signos_que_rompen_dataforseo():
    from app.services.news_research import limpiar_consulta

    assert limpiar_consulta('"El poder del arte" dura nueve minutos.') == \
        "El poder del arte dura nueve minutos"
    assert limpiar_consulta("10º aniversario de «Destrozares»") == "10 aniversario de Destrozares"


def test_listas_se_confirman_con_los_datos_del_disco():
    from app.services.fact_check import listas_confirmadas

    material = ("«Se nos lleva el aire» (Robe, 2023), tipo studio.\n"
                "Listas: n.º 1 en la lista oficial de álbumes de España, 132 semanas en lista "
                "(entró el 24-12-2023).")
    assert listas_confirmadas(material, "«Se nos lleva el aire» alcanzó el número uno de la "
                                        "lista oficial de álbumes de España.")
    assert listas_confirmadas(material, "El álbum, publicado el 15 de diciembre de 2023, llegó "
                                        "al n.º 1 de la lista y permaneció 132 semanas.")
    assert listas_confirmadas(material, "Entró en la lista el 24 de diciembre de 2023.")
    assert not listas_confirmadas(material, "Alcanzó el número cinco de la lista oficial.")
    assert not listas_confirmadas(material, "Estuvo 48 semanas en la lista.")
    assert not listas_confirmadas(material, "«Mayéutica» alcanzó el número uno de la lista.")
    assert not listas_confirmadas(material, "Entró en la lista el 27 de noviembre.")
    d = ("«Destrozares, canciones para el final de los tiempos» (Robe, 2016), tipo studio.\n"
         "Listas: n.º 5 en la lista oficial de álbumes de España, 48 semanas en lista "
         "(entró el 27-11-2016).")
    assert listas_confirmadas(d, "Alcanzó el quinto puesto de la lista y entró el 27 de noviembre.")

DISCOGRAFIA_ROBE = ("Discografía: Lo que aletea en nuestras cabezas (2015, studio); Destrozares, "
                    "canciones para el final de los tiempos (2016, studio); Bienvenidos al "
                    "temporal (2018, live); Mayéutica (2021, studio); Se nos lleva el aire "
                    "(2023, studio) ← ESTE DISCO.")


def test_el_orden_en_la_discografia_sale_de_los_hechos_duros():
    """#425 (18-11-2026): «cuarto álbum de estudio» retenía la pieza; la web no lo veía y
    nuestra discografía lo dice (el directo no cuenta como disco de estudio)."""
    from app.services.fact_check import orden_en_discografia_confirmado as ok

    assert ok(DISCOGRAFIA_ROBE, "«Se nos lleva el aire» fue el cuarto álbum de estudio en "
              "solitario de Robe.")
    assert ok(DISCOGRAFIA_ROBE, "«Se nos lleva el aire» fue el último disco de estudio de Robe.")
    assert not ok(DISCOGRAFIA_ROBE, "«Se nos lleva el aire» fue el tercer álbum de estudio.")
    assert ok(DISCOGRAFIA_ROBE, "«Mayéutica» fue el cuarto disco de Robe.")   # contando el directo
    assert not ok(DISCOGRAFIA_ROBE, "«Mayéutica» se grabó en cuarto lugar.")


def test_el_anio_de_un_disco_se_corrige_con_el_catalogo(monkeypatch):
    from app.services import fact_check

    monkeypatch.setattr(fact_check, "_anios_falsos",
                        lambda db, t: [("Yo, minoría absoluta", 2001, 2002)])
    texto, cambios = fact_check.corregir_anios_de_disco(
        None, "Colino entró para «Yo, minoría absoluta» (2001), y se grabó en 2001.")
    assert texto == "Colino entró para «Yo, minoría absoluta» (2002), y se grabó en 2001."
    assert cambios == ["«Yo, minoría absoluta» (2001) → 2002"]


def test_un_borrador_que_no_sale_se_retiene_al_segundo_fallo():
    import sys
    from types import SimpleNamespace

    sys.path.insert(0, "/app")
    from scripts.blog.generate_approved_drafts import anotar_fallo

    p = SimpleNamespace(id=1, review_reasons={"nota": "eje: el aniversario"}, review_verdict=None)
    anotar_fallo(p)
    assert p.review_verdict is None and p.review_reasons["fallos_borrador"] == 1
    anotar_fallo(p)
    assert p.review_verdict == "retenida" and p.review_reasons["bloquea"] == "material"
    assert p.review_reasons["nota"] == "eje: el aniversario"
