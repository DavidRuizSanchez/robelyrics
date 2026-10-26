"""Monitor de cambios: lo que tiene que saltar y lo que no (26-10-2026)."""
from __future__ import annotations

from app.services import page_monitor as pm

PATH = "/robe/mayeutica/interludio"


def _html(*, title="Interludio · Entre Interiores", desc="Letra y significado.",
          robots=None, canonical=f"https://entreinteriores.com{PATH}", h2="La letra",
          parrafo="Dejo las ventanas sin cerrar.", relacionados="Post A · Post B",
          enlace="/robe/mayeutica") -> str:
    meta_robots = f'<meta name="robots" content="{robots}"/>' if robots else ""
    return f"""<html><head><title>{title}</title>
<meta name="description" content="{desc}"/>{meta_robots}
<link rel="canonical" href="{canonical}"/>
<script type="application/ld+json">{{"@graph":[{{"@type":"MusicComposition"}},{{"@type":"BreadcrumbList"}}]}}</script>
</head><body><header>Menú que cambia</header><main>
<h1>Interludio</h1><h2>{h2}</h2><p>{parrafo}</p><a href="{enlace}">Mayéutica</a>
<section data-monitor="ignore"><h3>Relacionados</h3><p>{relacionados}</p></section>
<script>var x = Math.random();</script>
</main><footer>© 2026</footer></body></html>"""


def _foto(html: str, *, status=200, final_url=None, ms=200, path=PATH) -> dict:
    return {"status": status, "final_url": final_url or f"https://entreinteriores.com{path}",
            "cadena": [], "ms": ms, "campos": pm.parse(html, path=path)}


def _cambios(antes: dict, despues: dict, path=PATH) -> dict[str, pm.Cambio]:
    return {c.campo: c for c in pm.diff(antes, despues, path=path)}


def test_saca_los_campos_que_se_vigilan():
    c = pm.parse(_html(), path=PATH)
    assert c["title"] == "Interludio · Entre Interiores"
    assert c["canonical"] == f"https://entreinteriores.com{PATH}"
    assert c["h1"] == "Interludio"
    assert c["headings"] == ["h1: Interludio", "h2: La letra"]
    assert c["jsonld"] == ["BreadcrumbList", "MusicComposition"]
    assert c["enlaces"] == ["/robe/mayeutica"]
    assert "Menú" not in c["contenido"] and "Relacionados" not in c["contenido"]
    assert c["v"] == pm.VERSION_PARSER     # una foto de otra versión no se compara


def test_la_misma_pagina_no_cambia():
    assert pm.diff(_foto(_html()), _foto(_html()), path=PATH) == []


def test_lo_que_depende_de_otras_paginas_no_cuenta():
    assert pm.diff(_foto(_html()), _foto(_html(relacionados="Post C · Post D")),
                   path=PATH) == []


def test_un_title_cambiado_es_importante():
    c = _cambios(_foto(_html()), _foto(_html(title="Otro title")))
    assert c["title"].severidad == "estructural"
    assert (c["title"].antes, c["title"].despues) == ("Interludio · Entre Interiores",
                                                      "Otro title")


def test_un_noindex_nuevo_es_critico():
    assert _cambios(_foto(_html()), _foto(_html(robots="noindex, follow")))[
        "robots"].severidad == "critico"


def test_quitar_un_noindex_no_es_critico():
    assert _cambios(_foto(_html(robots="noindex")), _foto(_html()))[
        "robots"].severidad == "estructural"


def test_un_canonical_a_otra_pagina_es_critico():
    c = _cambios(_foto(_html()), _foto(_html(canonical="https://entreinteriores.com/robe")))
    assert c["canonical"].severidad == "critico"


def test_un_301_a_otra_url_es_critico_y_no_compara_lo_demas():
    c = _cambios(_foto(_html()),
                 _foto(_html(title="x"), final_url="https://entreinteriores.com/robe"))
    assert c["redireccion"].severidad == "critico"


def test_una_pagina_caida_es_critica_y_no_trae_title():
    c = _cambios(_foto(_html()), _foto("", status=404))
    assert c["status"].severidad == "critico"
    assert "title" not in c


def test_un_parrafo_editado_dice_que_entra_y_que_sale():
    c = _cambios(_foto(_html()), _foto(_html(parrafo="Se cae la casa desde que se marchó.")))
    assert c["contenido"].severidad == "contenido"
    assert c["contenido"].detalle["salen"] == ["Dejo las ventanas sin cerrar."]
    assert c["contenido"].detalle["entran"] == ["Se cae la casa desde que se marchó."]


def test_un_heading_movido_se_ve():
    c = _cambios(_foto(_html()), _foto(_html(h2="El significado")))
    assert c["headings"].detalle == {"salen": ["h2: La letra"], "entran": ["h2: El significado"]}


def test_un_enlace_interno_que_desaparece_se_ve():
    c = _cambios(_foto(_html()), _foto(_html(enlace="https://otra.web/x")))
    assert c["enlaces"].detalle["salen"] == ["/robe/mayeutica"]


def test_en_un_listado_solo_cuentan_h1_e_intro():
    a = _foto(_html(parrafo="Intro del blog.", h2="Post 1"), path="/blog")
    b = _foto(_html(parrafo="Intro del blog.", h2="Post 2", enlace="/blog/otro"), path="/blog")
    c = _cambios(a, b, path="/blog")
    assert "contenido" not in c and "enlaces" not in c


def test_mas_lento_solo_avisa_si_se_dispara():
    assert "tiempo" not in _cambios(_foto(_html(), ms=200), _foto(_html(), ms=500))
    assert _cambios(_foto(_html(), ms=400), _foto(_html(), ms=2000))["tiempo"].severidad == "aviso"
