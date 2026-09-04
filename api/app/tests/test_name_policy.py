"""«Robe Iniesta» no se escribe nunca; «Roberto Iniesta» sí.

Regla dura del proyecto: a él no le gustaba esa forma. La transformación
canónica vive en `text_sanitizer.enforce_name_policy` y se aplica en tres capas
(sanitizer, listener de ORM + trigger `trg_robe_name`, y el barrido
`scripts.seo.audit_name_policy`). Estos tests fijan el contrato de la primera,
que es la que definen las otras dos.
"""
from app.services.text_sanitizer import enforce_name_policy


def test_sustituye_la_forma_vetada():
    assert enforce_name_policy("Un disco de Robe Iniesta") == "Un disco de Robe"


def test_no_toca_roberto_iniesta():
    """«Roberto Iniesta» es la forma larga permitida."""
    t = "Biografía de Roberto Iniesta, nacido en Plasencia."
    assert enforce_name_policy(t) == t


def test_no_muerde_dentro_de_roberto():
    """El patrón exige frontera de palabra: «Robe» de «Roberto» no cuenta."""
    assert enforce_name_policy("Roberto Iniesta y Robe Iniesta") == "Roberto Iniesta y Robe"


def test_es_insensible_a_mayusculas_y_espacios():
    assert enforce_name_policy("ROBE INIESTA") == "Robe"
    assert enforce_name_policy("robe  iniesta") == "Robe"


def test_aguanta_el_vacio():
    assert enforce_name_policy("") == ""
    assert enforce_name_policy(None) is None


def test_las_tablas_de_texto_ajeno_estan_declaradas():
    """El barrido no puede reescribir una fuente: eso sería falsear el dato.

    Si alguien añade una tabla de contenido de terceros y no la declara aquí,
    `--fix` le reescribiría los títulos y las transcripciones.
    """
    from scripts.seo.audit_name_policy import AJENAS

    for t in ("interpretation_sources", "news_items", "songs", "verification_records",
              "related_videos"):
        assert t in AJENAS, f"{t} guarda texto ajeno y debe estar exenta"
