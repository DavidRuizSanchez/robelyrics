"""Fotos de terceros con crédito y fotos dentro del cuerpo (10-11-2026)."""
from app.services import body_images, image_guard

CLOUD = "https://res.cloudinary.com/x/image/upload/v1/mural.jpg"


def _v(**kw):
    base = dict(entity_name="Jesús Mateos Brea", image_url=CLOUD,
                source_url="https://www.plasencia.es/web/noticias/3386",
                attribution="Foto: Ayuntamiento de Plasencia",
                license_=image_guard.LICENCIA_TERCEROS)
    return image_guard.verify_provenance(**{**base, **kw})


def test_tercero_con_credito_y_fuente_se_publica_sin_errata():
    v = _v()
    assert v.status == "third_party_credited" and v.publishable and not v.needs_human


def test_sin_fuente_o_sin_marca_de_licencia_no_es_tercero():
    assert _v(source_url=None).status != "third_party_credited"
    assert _v(license_="").status != "third_party_credited"


def test_agencias_vetadas_nunca():
    assert _v(source_url="https://www.europapress.es/foto.html").status != "third_party_credited"
    assert _v(attribution="Foto: EFE").status != "third_party_credited"


def test_sin_alojar_en_casa_no_vale():
    assert _v(image_url="https://www.plasencia.es/foto.jpg").status != "third_party_credited"


def test_la_foto_va_bajo_su_heading_y_es_idempotente():
    body = "intro\n\n## El mural de Robe y Manolo Chinato\n\nTexto del mural.\n\n## Otro\n\nmás"
    e = {"target": "person:jesus-mateos-brea", "section": "El mural de Robe y Manolo Chinato",
         "url": "https://www.plasencia.es/foto.jpg", "alt": "Bodegón del mural",
         "attribution": "Foto: Ayuntamiento de Plasencia",
         "source_url": "https://www.plasencia.es/web/noticias/3386",
         "license": image_guard.LICENCIA_TERCEROS, "identity": "Mateos Brea"}
    r = body_images.preparar(e, body, rehost=lambda u: CLOUD, verificar_fuente=lambda f, n: None)
    assert r.estado == "insertada"
    assert r.body_nuevo == body.replace(
        "## El mural de Robe y Manolo Chinato\n",
        f'## El mural de Robe y Manolo Chinato\n\n![Bodegón del mural]({CLOUD} "Foto: Ayuntamiento de Plasencia")\n')
    otra = body_images.preparar({**e, "rehosted_url": CLOUD}, r.body_nuevo,
                                rehost=lambda u: CLOUD, verificar_fuente=lambda f, n: None)
    assert otra.estado == "ya_estaba"


def test_si_la_fuente_no_nombra_al_retratado_no_entra():
    e = {"target": "person:x", "section": "S", "url": "https://a.es/f.jpg", "alt": "x",
         "attribution": "Foto: A", "source_url": "https://a.es/n",
         "license": image_guard.LICENCIA_TERCEROS}
    r = body_images.preparar(e, "## S\n\ntexto", rehost=lambda u: CLOUD,
                             verificar_fuente=lambda f, n: "la fuente no nombra a 'x'")
    assert r.estado == "rechazada"


def test_sin_su_heading_no_se_inserta_en_otro_sitio():
    e = {"target": "person:x", "section": "No existe", "url": "https://a.es/f.jpg", "alt": "x",
         "attribution": "Foto: A", "source_url": "https://a.es/n",
         "license": image_guard.LICENCIA_TERCEROS}
    r = body_images.preparar(e, "## S\n\ntexto", rehost=lambda u: CLOUD,
                             verificar_fuente=lambda f, n: None)
    assert r.estado == "sin_seccion"


def test_la_busqueda_de_personas_exige_que_sea_alguien_de_la_musica():
    """Los 15 falsos del 10-11-2026 y la buena (Leiva), con sus categorías reales."""
    from scripts.seo.fetch_entity_images import es_de_la_musica

    falsos = [
        (["Category:Salo", "Category:Pernio", "Category:Hydroelectric power stations in Finland"], ""),
        (["Category:Aitor Ariño", "Category:Handball-Bundesliga 2025/26"], "Aitor Arino (14, Füchse Berlin)"),
        (["Category:Fawzi Selu", "Category:Adib Shishakli"], "Syrian officers in Damascus, 1951"),
        (["Category:Jaime Moreno", "Category:D.C. United players"], ""),
        (["Category:Lower Manhattan skyline"], "NYC Downtown Manhattan Skyline"),
    ]
    for cats, desc in falsos:
        assert not es_de_la_musica(cats, desc), cats
    assert es_de_la_musica(["Category:Leiva (vocalist)", "Category:Premios Goya 2026"],
                           "Leyva at Red Carpet of Goya Awards 2026 in Barcelona")
