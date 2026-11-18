"""Ideas del blog desde el catálogo (plan del blog, 18-11-2026, bloque B)."""
from __future__ import annotations

from app.services import catalog_ideas as ci


def test_source_type_ida_y_vuelta():
    st = ci.source_type_de("album", "historia")
    assert st == "cat-alb-his" and len(st) <= 16
    assert ci.entidad_de(st) == ("album", "historia")
    assert ci.entidad_de("seo") is None and ci.entidad_de(None) is None


def test_una_senal_del_propio_nombre_no_cuenta_y_las_letras_tampoco():
    idea = ci.Idea("song", 1, "Historias prohibidas", "/extremoduro/x/historias-prohibidas",
                   "historia", "La historia de «Historias prohibidas»", "…", "historias prohibidas historia")
    paginas = {idea.ruta: [
        {"query": "letras de extremoduro historias prohibidas", "impressions": 300, "position": 8.6},
        {"query": "historias prohibidas extremoduro", "impressions": 50, "position": 5}]}
    ci.medir_demanda([idea], paginas)
    assert idea.canibaliza is None and idea.gsc_impresiones == 0


def test_la_ficha_que_ya_posiciona_el_angulo_canibaliza():
    idea = ci.Idea("person", 2, "Rosendo", "/personas/rosendo-mercado", "con-robe",
                   "Rosendo y Robe", "…", "rosendo robe")
    ci.medir_demanda([idea], {idea.ruta: [{"query": "robe y rosendo", "impressions": 80,
                                           "position": 7.4}]})
    assert idea.canibaliza and "ampliar la ficha" in idea.canibaliza


def test_temas_vetados():
    assert ci._VETO.search("La pareja de Robe")
    assert ci._VETO.search("descargar discografía extremoduro")
    assert not ci._VETO.search("Cómo se hizo «Mayéutica»")


def test_cómo_se_hizo_un_disco_usa_el_liston_del_aniversario():
    from app.services.piece_checklist import LISTAS
    assert LISTAS["album-historia"] is LISTAS["album-anniversary"]


def test_nombrar_es_palabra_completa_y_los_titulos_cortos_van_citados():
    assert not ci.nombra("Reseña de Tú en tu casa, nosotros en la hoguera", "La hoguera")
    assert ci.nombra("En «La hoguera» Robe canta…", "La hoguera")
    assert not ci.nombra("Iba a salir de casa", "Salir")            # corto y sin citar
    assert ci.nombra("La canción Salir es de 1998", "Salir")
    assert ci.nombra("Mayéutica se grabó en 2019", "Mayéutica")    # ≥ 10: basta la palabra


def test_lo_que_ya_paso_por_el_banco_no_vuelve():
    class _Q:
        def __init__(self, filas):
            self.filas = filas

        def filter(self, *a):
            return self

        def __iter__(self):
            return iter(self.filas)

    class _Db:
        def query(self, *a):
            return _Q([("cat-alb-his", 7)])

        def execute(self, *a, **k):
            return []

    a = ci.Idea("album", 7, "Mayéutica", "/robe/mayeutica", "historia", "Cómo se hizo «Mayéutica»",
                "…", "mayeutica historia")
    b = ci.Idea("album", 8, "Destrozares", "/robe/destrozares", "historia", "Cómo se hizo «Destrozares»",
                "…", "destrozares historia")
    ci.filtrar(_Db(), [a, b])
    assert a.descarte and "ya pasó por el banco" in a.descarte
    assert b.descarte is None
