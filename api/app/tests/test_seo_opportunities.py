"""Tests del circuito de aprobación SEO.

Lo que se blinda aquí es lo que decidió el diseño, no el detalle de la redacción:

  - **Qué se considera una oportunidad.** La clasificación se mide contra el
    contenido publicado. El informe viejo clasificaba por posición y ponía arriba
    tres URLs cuya metadata ya era impecable: lo que les faltaba era posición.
  - **Qué NO puede colarse.** Un dato que no esté en la página (una cifra, un
    nombre propio) no se publica en la metadata; y una palabra común tampoco puede
    tumbar una propuesta buena, porque una guarda que rechaza lo correcto acaba
    apagada.
  - **Que las dos fases sean dos de verdad.** El token que autoriza a preparar un
    borrador no puede publicarlo.
  - **Que aplicar no pise trabajo ajeno.** Si el cuerpo cambió entre el borrador y
    el clic, no se aplica.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services import seo_opportunities as svc


# --------------------------------------------------------------------------- #
# Clasificación
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _sin_enfriamiento(monkeypatch):
    """Los dobles de BD de este fichero no saben de `page_changes`. El enfriamiento
    tiene sus tests en `test_cambios_recientes.py`; aquí, salvo que un test lo ponga,
    ninguna página está en él."""
    monkeypatch.setattr(svc, "_enfriamiento", lambda db, path: None)


def _q(query: str, impressions: int = 100, clicks: int = 0, position: float = 7.0) -> dict:
    return {"query": query, "impressions": impressions, "clicks": clicks,
            "position": position, "ctr": clicks / impressions if impressions else 0}


CUERPO = (
    "## Desarraigo\n\nLa letra de «Desarraigo», de Extremoduro, habla del "
    "significado de marcharse. Incluida en Material defectuoso (1996).\n"
)


def test_lo_cubierto_en_cuerpo_y_metadata_no_genera_trabajo():
    """El grupo más grande de consultas no admite acción: no se le inventa una.

    Medido el 21-09-2026 sobre 12 semanas: 266 consultas y 12.176 impresiones ya
    respondidas en el cuerpo y prometidas en la metadata.
    """
    rep = svc.classify_queries(
        [_q("desarraigo extremoduro")],
        body_md=CUERPO,
        meta_title="Desarraigo de Extremoduro: letra y significado",
        meta_description="Qué cuenta «Desarraigo» de Extremoduro y de dónde sale.",
    )
    assert rep["covered"] and not rep["meta"] and not rep["body"]


def test_el_cuerpo_responde_pero_la_metadata_no_lo_promete():
    rep = svc.classify_queries(
        [_q("desarraigo significado")],
        body_md=CUERPO,
        meta_title="Desarraigo de Extremoduro",
        meta_description="Una canción de Extremoduro.",
    )
    assert [q["query"] for q in rep["meta"]] == ["desarraigo significado"]


def test_lo_que_la_pagina_no_cubre_pide_contenido():
    rep = svc.classify_queries(
        [_q("desarraigo directo benicassim")],
        body_md=CUERPO, meta_title="Desarraigo", meta_description="",
    )
    assert rep["body"] and not rep["meta"]


def test_buscar_la_letra_no_es_un_hueco_de_contenido():
    """«letras de extremoduro X» en la página de X no es un ángulo que escribir.

    El cuerpo elegido aquí NO contiene la palabra «letra» por ningún lado, así que
    lo único que impide tratarlo como hueco es la lista de modificadores: con la
    palabra buscada dentro del cuerpo, el cotejo por prefijo lo salvaría igual y
    este test estaría verde sin vigilar nada.
    """
    cuerpo_sin_la_palabra = (
        "## Entre interiores\n\nUna canción de Extremoduro incluida en Para todos "
        "los públicos (2013), escrita en Extremadura.\n"
    )
    rep = svc.classify_queries(
        [_q("letras de extremoduro entre interiores")],
        body_md=cuerpo_sin_la_palabra,
        meta_title="Entre interiores de Extremoduro",
        meta_description="Qué cuenta «Entre interiores» de Extremoduro.",
    )
    assert "letra" not in cuerpo_sin_la_palabra
    assert rep["covered"], f"debería estar cubierta, salió en {rep}"


def test_una_consulta_sin_contenido_propio_se_ignora():
    assert svc.classify_queries([_q("letras")], body_md=CUERPO, meta_title="x",
                                meta_description="y") == {"body": [], "meta": [], "covered": []}


def test_las_consultas_de_paja_no_llegan_al_suelo():
    rep = svc.classify_queries([_q("desarraigo rareza", impressions=1)],
                               body_md=CUERPO, meta_title="", meta_description="")
    assert not any(rep.values())


# --------------------------------------------------------------------------- #
# Guarda anti-invención
# --------------------------------------------------------------------------- #
def test_un_dato_que_no_esta_en_la_pagina_no_se_publica():
    permitidos = svc._tokens_permitidos(CUERPO, "Desarraigo", "")
    fuera = svc.verify_no_invention(
        "Desarraigo, el single de Extremoduro grabado en 1989 con Rosendo.", permitidos
    )
    assert "1989" in fuera and "Rosendo" in fuera


def test_una_palabra_comun_no_tumba_una_propuesta_correcta():
    """El primer intento de esta guarda descartó una description buena por «cuenta».

    Una guarda que rechaza lo correcto acaba desactivada, y entonces no guarda nada.
    """
    permitidos = svc._tokens_permitidos(CUERPO, "Desarraigo", "")
    assert svc.verify_no_invention(
        "Desarraigo cuenta qué significa marcharse, y refleja ese sentimiento.",
        permitidos,
    ) == []


def test_los_datos_que_si_estan_en_la_pagina_pasan():
    permitidos = svc._tokens_permitidos(CUERPO, "Desarraigo", "")
    assert svc.verify_no_invention(
        "Desarraigo, de Extremoduro, está en Material defectuoso (1996).", permitidos
    ) == []


def test_capitalizacion_espanola():
    """GPT devuelve Title Case inglés; en español solo van los nombres propios."""
    assert svc.spanish_case("Agila de Extremoduro: Significado y Canciones Clave",
                            "Agila Extremoduro") == \
        "Agila de Extremoduro: Significado y canciones clave"


# --------------------------------------------------------------------------- #
# propose_meta
# --------------------------------------------------------------------------- #
class _FakeClient:
    pass


def test_una_propuesta_que_no_cubre_la_consulta_se_descarta(monkeypatch):
    """Si el texto nuevo no menciona lo que se buscaba, no arregla nada."""
    monkeypatch.setattr(
        "scripts.seo.generate_deep._chat",
        lambda *a, **kw: {
            "title": "Desarraigo de Extremoduro, una canción del grupo",
            "description": ("Desarraigo, de Extremoduro, está incluida en Material "
                            "defectuoso y habla de marcharse de casa muy lejos."),
        },
    )
    out = svc.propose_meta(
        _FakeClient(), subject="Desarraigo", body_md=CUERPO,
        meta_title="Desarraigo", meta_description="Una canción.",
        queries=[_q("desarraigo significado")],
    )
    assert "title" not in out and "description" not in out
    assert any("sigue sin cubrir" in r for r in out["rechazos"])


def test_una_propuesta_con_un_dato_inventado_se_descarta(monkeypatch):
    monkeypatch.setattr(
        "scripts.seo.generate_deep._chat",
        lambda *a, **kw: {"title": "Desarraigo (1989): significado de la letra",
                          "description": ""},
    )
    out = svc.propose_meta(
        _FakeClient(), subject="Desarraigo", body_md=CUERPO,
        meta_title="Desarraigo", meta_description="Una canción.",
        queries=[_q("desarraigo significado")],
    )
    assert "title" not in out
    assert any("1989" in r for r in out["rechazos"])


# --------------------------------------------------------------------------- #
# Las dos fases, y que aplicar no pise nada
# --------------------------------------------------------------------------- #
def test_el_token_de_aprobar_no_publica():
    """La separación de fases vive en el token: sin esto, un reenvío del primer
    correo podría publicar sin que nadie viera el antes/después."""
    from app.services.auth import create_seo_opportunity_token, decode_seo_opportunity_token

    data = decode_seo_opportunity_token(create_seo_opportunity_token([7], "approve"))
    assert data["action"] == "approve"
    assert data["action"] != "apply"


def test_un_token_de_otro_proposito_no_vale():
    from app.services.auth import create_youtube_ingest_token, decode_seo_opportunity_token

    assert decode_seo_opportunity_token(create_youtube_ingest_token([1])) is None


def test_no_se_puede_firmar_una_accion_inventada():
    from app.services.auth import create_seo_opportunity_token

    with pytest.raises(ValueError):
        create_seo_opportunity_token([1], "publicar_todo_sin_mirar")


class _SeoContent:
    def __init__(self, body: str):
        self.id = 1
        self.body_md = body
        self.meta_title = "Desarraigo"
        self.meta_description = "Una canción."
        self.reviewed_at = None


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._row


class _FakeDb:
    def __init__(self, row):
        self._row = row
        self.commits = 0
        self.added: list = []

    def query(self, *a, **kw):
        return _FakeQuery(self._row)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


class _Opp:
    def __init__(self, **kw):
        self.id = 1
        self.path = "/extremoduro/material-defectuoso/desarraigo"
        self.action = "body"
        self.status = "drafted"
        self.seo_content_id = 1
        self.before_body = CUERPO
        self.draft_body = CUERPO + "\n## Lo nuevo\n\nMaterial verificado.\n"
        self.draft_title = self.draft_description = None
        self.before_title = self.before_description = None
        self.error = None
        self.applied_at = None
        self.__dict__.update(kw)


def test_aplicar_no_pisa_un_cuerpo_que_cambio_despues(monkeypatch):
    """Entre preparar y publicar pueden pasar días. Si alguien (o un cron) tocó la
    ficha, aplicar a ciegas se cargaría ese trabajo."""
    db = _FakeDb(_SeoContent(CUERPO + "\n## Lo que escribió otro\n\nAlgo nuevo.\n"))
    opp = _Opp()
    assert svc.apply_draft(db, opp) is False
    assert opp.status == "failed" and "cambió" in (opp.error or "")


def test_aplicar_escribe_y_revalida(monkeypatch):
    revalidadas: list[list[str]] = []
    monkeypatch.setattr("app.services.publishing.revalidate_paths",
                        lambda paths, **kw: revalidadas.append(paths))
    sc = _SeoContent(CUERPO)
    db = _FakeDb(sc)
    opp = _Opp()
    assert svc.apply_draft(db, opp) is True
    assert sc.body_md == opp.draft_body
    assert opp.status == "applied" and isinstance(opp.applied_at, datetime)
    assert revalidadas == [[opp.path]]
    # La copia de ANTES se guarda una vez, al aplicar: es lo que permite revertir.
    (rev,) = db.added
    assert rev.body_md == CUERPO and rev.opportunity_id == opp.id


def test_solo_se_aplica_un_borrador():
    db = _FakeDb(_SeoContent(CUERPO))
    assert svc.apply_draft(db, _Opp(status="detected")) is False


def test_aplicar_una_meta_no_toca_el_cuerpo(monkeypatch):
    monkeypatch.setattr("app.services.publishing.revalidate_paths", lambda *a, **kw: None)
    sc = _SeoContent(CUERPO)
    db = _FakeDb(sc)
    opp = _Opp(action="meta", draft_title="Desarraigo: letra y significado",
               draft_body=None, before_body="otra cosa distinta")
    assert svc.apply_draft(db, opp) is True
    assert sc.body_md == CUERPO
    assert sc.meta_title == "Desarraigo: letra y significado"
    assert isinstance(sc.reviewed_at, datetime)
    assert sc.reviewed_at.tzinfo is UTC


# --------------------------------------------------------------------------- #
# El endpoint del correo
# --------------------------------------------------------------------------- #
class _FakeBackground:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **kw):
        self.tasks.append((fn, a, kw))


class _FakeQueryLista:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **kw):
        return self

    def all(self):
        return self._rows


class _FakeDbLista:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0

    def query(self, *a, **kw):
        return _FakeQueryLista(self._rows)

    def commit(self):
        self.commits += 1


def _accion(token_action: str, opp, monkeypatch):
    """Llama al endpoint como lo haría el clic del correo."""
    from app.routers import public as pub
    from app.services.auth import create_seo_opportunity_token

    aplicadas: list = []
    monkeypatch.setattr("app.services.seo_opportunities.apply_draft",
                        lambda db, o: (aplicadas.append(o), True)[1])
    bg = _FakeBackground()
    resp = pub.seo_opportunity_action(
        create_seo_opportunity_token([opp.id], token_action), bg,
        db=_FakeDbLista([opp]),
    )
    return resp, bg, aplicadas


def test_el_clic_de_aprobar_no_publica_un_borrador(monkeypatch):
    """La garantía del circuito: el primer correo NUNCA puede publicar, ni aunque
    alguien lo reenvíe o lo pulse cuando el borrador ya está hecho."""
    opp = _Opp(status="drafted")
    resp, bg, aplicadas = _accion("approve", opp, monkeypatch)
    assert aplicadas == []
    assert opp.status == "drafted"
    assert resp.status_code == 200


def test_el_clic_de_aprobar_encola_el_borrador_sin_tocar_el_sitio(monkeypatch):
    opp = _Opp(status="detected")
    resp, bg, aplicadas = _accion("approve", opp, monkeypatch)
    assert opp.status == "approved"
    assert aplicadas == []
    # El borrador se prepara fuera de la petición: Cloudflare corta a los 100 s.
    assert len(bg.tasks) == 1 and bg.tasks[0][1] == ([opp.id],)


def test_el_clic_de_publicar_aplica(monkeypatch):
    opp = _Opp(status="drafted")
    _resp, _bg, aplicadas = _accion("apply", opp, monkeypatch)
    assert aplicadas == [opp]


def test_pulsar_dos_veces_no_rompe(monkeypatch):
    """Los correos se reenvían y se pulsan dos veces; eso no puede dar un error."""
    opp = _Opp(status="applied")
    resp, _bg, aplicadas = _accion("apply", opp, monkeypatch)
    assert aplicadas == []
    assert resp.status_code == 200


def test_un_token_manipulado_no_hace_nada(monkeypatch):
    from app.routers import public as pub

    opp = _Opp(status="drafted")
    resp = pub.seo_opportunity_action("no-es-un-token", _FakeBackground(),
                                      db=_FakeDbLista([opp]))
    assert resp.status_code == 400
    assert opp.status == "drafted"


# --------------------------------------------------------------------------- #
# Enfriamiento: una página cambiada hace poco no se vuelve a tocar (20-11-2026)
# --------------------------------------------------------------------------- #
def _frio(monkeypatch):
    from app.services.cambios_recientes import Enfriamiento

    frio = Enfriamiento("/extremoduro/material-defectuoso/desarraigo", "title",
                        datetime(2026, 11, 12, tzinfo=UTC))
    monkeypatch.setattr(svc, "_enfriamiento", lambda db, path: frio)
    return frio


def test_un_borrador_de_meta_espera_en_una_pagina_en_enfriamiento(monkeypatch):
    """«Golfa» tuvo cuatro titles en seis días y perdió su consulta. El borrador no se
    aplica, pero tampoco se descarta: sigue `drafted` y dice hasta cuándo espera."""
    _frio(monkeypatch)
    sc = _SeoContent(CUERPO)
    db = _FakeDb(sc)
    opp = _Opp(action="meta", draft_title="Desarraigo: letra y significado", draft_body=None)
    assert svc.apply_draft(db, opp) is False
    assert opp.status == "drafted"
    assert sc.meta_title == "Desarraigo" and db.added == []
    assert "en enfriamiento" in opp.error and "10-12-2026" in opp.error


def test_una_fusion_entra_en_una_pagina_en_enfriamiento_sin_tocarle_el_title(monkeypatch):
    monkeypatch.setattr("app.services.publishing.revalidate_paths", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_metadatos_de_fusion", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_registrar_videos", lambda *a, **kw: None)
    monkeypatch.setattr(svc, "_aplicar_enlaces_entrantes", lambda *a, **kw: [])
    _frio(monkeypatch)
    sc = _SeoContent(CUERPO)
    opp = _Opp(action="merge", entity_type="song", proposal_id=None,
               draft_title="Otro title", draft_description="Otra description.")
    assert svc.apply_draft(_FakeDb(sc), opp) is True
    assert sc.body_md == opp.draft_body
    assert (sc.meta_title, sc.meta_description) == ("Desarraigo", "Una canción.")


def test_preparar_una_meta_en_enfriamiento_no_gasta_intento_ni_la_descarta(monkeypatch):
    _frio(monkeypatch)
    opp = _Opp(action="meta", status="approved", attempts=0)
    assert svc.prepare_draft(_FakeDb(_SeoContent(CUERPO)), opp) == "en_espera"
    assert opp.status == "approved" and opp.attempts == 0
    assert "en enfriamiento" in opp.error


def test_el_cuerpo_no_espera(monkeypatch):
    """El enfriamiento es de title, description, H1 y headings: ampliar el cuerpo de
    una página cambiada hace poco sigue pudiéndose."""
    monkeypatch.setattr("app.services.publishing.revalidate_paths", lambda *a, **kw: None)
    _frio(monkeypatch)
    sc = _SeoContent(CUERPO)
    assert svc.apply_draft(_FakeDb(sc), _Opp()) is True


# --- El detector pregunta si la página RESPONDE, no si repite la palabra (23-11-2026) ---
# Textos reales de prod: la ficha de Marea respondía a las cuatro búsquedas del correo
# y el detector las daba por hueco porque no decía «dónde», «componentes»…

from app.services import seo_style  # noqa: E402

MAREA = ("## Cómo se formó Marea y quiénes son sus miembros\n\nMarea, la banda española de "
         "rock, se formó en Berriozar, Navarra en 1997. Kutxi contactó con Alén Ayerdi, "
         "batería en Begira, y César Ramallo completó la formación.")


@pytest.mark.parametrize("query", ["de donde es marea", "de dónde es el grupo marea",
                                   "componentes de marea", "marea integrantes",
                                   "integrante de marea"])
def test_la_ficha_de_marea_responde_sin_repetir_la_pregunta(query):
    assert seo_style.responde(seo_style.flatten(MAREA), query)
    assert not seo_style.cubre(seo_style.flatten(MAREA), query)  # la guarda literal no cambia


def test_lo_que_la_ficha_no_dice_sigue_siendo_hueco():
    plano = seo_style.flatten(MAREA)
    assert not seo_style.responde(plano, "cantante de marea")
    assert not seo_style.responde(plano, "eduardo beaumont piñas wikipedia")
    assert not seo_style.responde(plano, "marea gira 2026")


@pytest.mark.parametrize("texto, query", [
    ("La letra de «Extremaydura» abre el disco.", "extrema y dura letra"),
    ("«Bri bri bli bli» suena en el disco.", "bribriblibli"),
    ("«Calle Esperanza S/N» cierra el disco.", "calle esperanza sn"),
])
def test_la_misma_cosa_escrita_con_otros_espacios(texto, query):
    assert seo_style.responde(seo_style.flatten(texto), query)


def test_una_palabra_corta_no_casa_dentro_de_otra():
    # «portada» no es «contraportada»
    assert not seo_style.responde(seo_style.flatten("La contraportada es negra."),
                                  "material defectuoso portada")


def test_nacer_y_fundar_llevan_su_anio_cerca():
    con = seo_style.flatten("Robe, nacido como Roberto Iniesta en Plasencia el 16 de mayo de "
                            "1962, fue músico.")
    sin = seo_style.flatten("Robe, nacido como Roberto Iniesta en Plasencia, fue músico.")
    assert seo_style.responde(con, "roberto iniesta nacimiento")
    assert not seo_style.responde(sin, "roberto iniesta nacimiento")
    # «fundamental» no es «fundó» (casaba en la ficha de /extremoduro)
    fund = seo_style.flatten("Esta etapa fue fundamental para Extremoduro en 1989.")
    assert not seo_style.responde(fund, "cuando se fundo extremoduro")
    assert seo_style.responde(seo_style.flatten("Extremoduro se formó en 1987 en Plasencia."),
                              "cuando se fundo extremoduro")


def test_un_mensaje_politico_no_explica_un_significado():
    plano = seo_style.flatten("Reincidentes combina su mensaje político con rock.")
    assert not seo_style.responde(plano, "reincidentes significado")


def test_el_verso_esta_en_la_letra_aunque_no_en_el_cuerpo():
    q = [_q("voy a tatuarme azul una casita", 42)]
    sin = svc.classify_queries(q, body_md="## A fuego\n\nUna canción de 2002.",
                               meta_title="A fuego", meta_description="")
    con = svc.classify_queries(q, body_md="## A fuego\n\nUna canción de 2002.",
                               meta_title="A fuego", meta_description="",
                               letra="Voy a tatuarme azul una casita en el corazón")
    assert sin["body"] and not con["body"]


def test_una_busqueda_de_descarga_no_es_hueco():
    rep = svc.classify_queries([_q("discografia marea megaupload", 10)], body_md=MAREA,
                               meta_title="Marea", meta_description="")
    assert not any(rep.values())
