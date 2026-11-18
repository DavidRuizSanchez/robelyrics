"""El inventario de historias de un disco (18-11-2026)."""
from __future__ import annotations

from app.services import historias_disco as hd


def test_el_tramo_tiene_que_estar_literal_en_su_fuente():
    fuente = ("para la gira pasada queríamos meter algo nuevo y estuvimos viendo y al final "
              "pues hicimos dos canciones")
    assert hd.tramo_literal("queríamos meter algo nuevo y estuvimos viendo", fuente)
    assert not hd.tramo_literal("quisimos meter algo nuevo para la gira", fuente)  # paráfrasis
    assert not hd.tramo_literal("dos canciones", fuente)                            # corto


def test_una_historia_sin_ancla_valida_no_entra():
    assert hd._validar(None, {"ancla": "letra", "tramo": "x" * 40, "fuente": "P1"},
                       {}, "", usar_web=False) is None


def test_la_pregunta_del_locutor_no_es_robe(monkeypatch):
    """1559: «después de doce años casi todos juntos» era la pregunta, no Robe."""
    monkeypatch.setattr("app.services.instagram.clip_picker.habla_el_protagonista",
                        lambda t, **k: (False, "es una pregunta: la hace quien entrevista"))
    tramo = "Que ha cambiado de esos inicios De Robe como banda Después de doce años"
    por_id = {"P1": {"kind": "robe_interview", "title": "El Francotirarock",
                     "fragmento": f"Oye {tramo} casi todos juntos"}}
    h = hd._validar(None, {"ancla": "declaracion", "tramo": tramo, "fuente": "P1",
                           "quien": "robe"}, por_id, "", usar_web=False)
    assert h is not None and not h.afirmable and h.quien == "tercero"


def test_un_hecho_duro_es_afirmable():
    hechos = "Listas: n.º 1 en la lista oficial de álbumes de España, 132 semanas en lista."
    h = hd._validar(None, {"ancla": "listas", "fuente": "hechos duros",
                           "tramo": "n.º 1 en la lista oficial de álbumes de España"},
                    {}, hechos, usar_web=False)
    assert h.afirmable and h.quien == "hechos"


def test_en_una_entrevista_escrita_la_etiqueta_robe_es_robe():
    tramo = "Robe: Yo creo que forman un todo. Podría haber diferencias."
    por_id = {"P7": {"kind": "robe_interview", "title": "Diario de Noticias de Navarra",
                     "fragmento": f"¿Qué diferencia hay? {tramo} Y más."}}
    h = hd._validar(None, {"ancla": "declaracion", "tramo": tramo, "fuente": "P7"},
                    por_id, "", usar_web=False)
    assert h.afirmable and h.quien == "robe" and h.tramo.startswith("Yo creo")
