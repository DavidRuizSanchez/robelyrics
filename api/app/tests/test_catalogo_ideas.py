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
