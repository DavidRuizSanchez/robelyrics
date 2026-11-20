"""Licencia de las cabeceras del blog. Los créditos son los REALES de producción
(consulta a `posts`, 20-11-2026): si una guarda deja de entenderlos, está mal la guarda."""
from __future__ import annotations

from app.services.image_license import autores, derechos_de_imagen, pagina_de_commons

DERIVADA = ("*Foto: File:Extremoduro - Gira 2014 - 7.jpg : Ruben Ortega derivative work: "
            "Alonso de Mendoza · CC BY-SA 4.0 · vía [Wikimedia Commons]"
            "(https://commons.wikimedia.org/wiki/File:Robe_Iniesta_en_Valladolid_en_2014.jpg)*")
FILE_ROBE = "https://commons.wikimedia.org/wiki/File:Robe_Iniesta_en_Valladolid_en_2014.jpg"


def test_obra_derivada_con_sus_dos_autores():
    d = derechos_de_imagen(DERIVADA, "CC BY-SA 4.0", FILE_ROBE)
    assert d == {
        "license_name": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "creators": ["Ruben Ortega", "Alonso de Mendoza"],
        "copyright_notice": "© Ruben Ortega, Alonso de Mendoza (CC BY-SA 4.0)",
        "acquire_license_page": FILE_ROBE,
    }


def test_autor_con_su_web_pegada():
    credito = ("*Foto: Alterna2 http://www.alterna2.com · CC BY 2.0 · vía [Wikimedia Commons]"
               "(https://commons.wikimedia.org/wiki/File:Fito_cabrales.jpg)*")
    d = derechos_de_imagen(credito, "CC BY 2.0",
                           "https://commons.wikimedia.org/wiki/File:Fito_cabrales.jpg")
    assert d["creators"] == ["Alterna2"]
    assert d["license_url"] == "https://creativecommons.org/licenses/by/2.0/"


def test_la_pagina_de_commons_sale_del_credito_si_no_hay_fuente():
    credito = ("*Foto: Ruben Ortega · CC BY-SA 2.0 · vía [Wikimedia Commons]"
               "(https://commons.wikimedia.org/wiki/File:Extremoduro_-_Gira_2014_Robe_Iniesta.jpg)*")
    d = derechos_de_imagen(credito, "CC BY-SA 2.0", None)
    assert d["acquire_license_page"].endswith("File:Extremoduro_-_Gira_2014_Robe_Iniesta.jpg")
    assert d["creators"] == ["Ruben Ortega"]


def test_licencia_solo_en_el_credito_y_sin_pagina():
    # El campo dice «CC» a secas: la versión está en el crédito. Sin fuente, no hay
    # página de licencia que dar y no se inventa.
    d = derechos_de_imagen("elchicogris · Wikimedia Commons (CC BY-SA 2.0)", "CC", None)
    assert d["license_name"] == "CC BY-SA 2.0"
    assert d["creators"] == ["elchicogris"]
    assert "acquire_license_page" not in d


def test_miniatura_de_commons_lleva_a_su_pagina_file():
    mini = ("https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/"
            "Extremoduro_-_Gira_2014_-_4.jpg/1280px-Extremoduro_-_Gira_2014_-_4.jpg")
    d = derechos_de_imagen("Ruben Ortega · Wikimedia Commons (CC BY-SA 4.0)", None, mini)
    assert d["acquire_license_page"] == (
        "https://commons.wikimedia.org/wiki/File:Extremoduro_-_Gira_2014_-_4.jpg")
    assert pagina_de_commons(
        "https://upload.wikimedia.org/wikipedia/commons/a/a9/Robe%20en%20directo.jpg"
    ) == "https://commons.wikimedia.org/wiki/File:Robe en directo.jpg"


def test_portada_cartel_y_foto_de_prensa_no_declaran_licencia():
    assert derechos_de_imagen("Portada de «Agila»", None, None) is None
    assert derechos_de_imagen(
        "Cartel oficial del Festival Flores Amarillas 2027 (Junta de Extremadura, "
        "Diputación de Cáceres y Ayuntamiento de Plasencia)", None,
        "https://img.europapress.es/fotoweb/fotonoticia_20261112122510_1200.jpg") is None
    assert derechos_de_imagen("Foto: Junta de Extremadura",
                              "Foto de prensa de la Junta de Extremadura",
                              "https://www.juntaex.es/w/x") is None
    assert derechos_de_imagen(None, None, None) is None


def test_autores_sin_credito():
    assert autores(None) == []
    assert autores("") == []
