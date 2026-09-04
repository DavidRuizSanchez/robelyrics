"""Tests del resolvedor de URLs internas (sin BD, sin red, sin LLM).

Blindan el incidente real: `/extremoduro/pedra/ama-ama-ama-y-ensancha-el-alma-en-directo`
devolvía **200** y pintaba la canción de «Iros todos a tomar por culo» con el
tracklist, el prev/next y el JSON-LD de «Pedrá». El invariante que se prueba aquí
es que esa ruta NUNCA puede salir `ok`.
"""
from __future__ import annotations

from app.services import url_resolver as ur
from app.services.url_resolver import MemoryCatalog, SongRow

AMA = "ama-ama-ama-y-ensancha-el-alma"
AMA_LIVE = f"{AMA}-en-directo"


def _catalogo() -> MemoryCatalog:
    """Trocito real del catálogo: los discos y canciones del incidente."""
    return MemoryCatalog(
        artists={"extremoduro": 1, "robe": 2},
        albums=[
            (10, "deltoya", "extremoduro", True),
            (11, "iros-todos-a-tomar-por-culo", "extremoduro", True),
            (12, "pedra", "extremoduro", True),
            (13, "agila", "extremoduro", True),
            (14, "la-ley-innata", "extremoduro", True),
            (15, "mayeutica", "robe", True),
        ],
        songs=[
            SongRow(100, AMA, "Ama, Ama, Ama y Ensancha el Alma",
                    "deltoya", "extremoduro"),
            SongRow(101, AMA_LIVE, "Ama, ama, ama y ensancha el alma (En Directo)",
                    "iros-todos-a-tomar-por-culo", "extremoduro"),
            SongRow(102, "pedra", "Pedrá", "pedra", "extremoduro"),
            SongRow(103, "abreme-el-pecho-y-registra", "Ábreme el pecho y registra",
                    "agila", "extremoduro"),
        ],
        sections={
            ("personas", "robe-iniesta"): (200, True),
            ("temas", "libertad"): (201, True),
            ("sellos", "el-dromedario-records"): (202, True),
            ("blog", "un-post-cualquiera"): (203, True),
            ("blog", "borrador-sin-publicar"): (204, False),
        },
    )


# --------------------------------------------------------------------------- #
# El incidente
# --------------------------------------------------------------------------- #
def test_cross_album_nunca_devuelve_ok():
    """LA prueba del incidente: el disco de la URL no es el de la canción."""
    res = ur.resolve_song(_catalogo(), "extremoduro", "pedra", AMA_LIVE)
    assert res.status == "redirect"
    assert res.reason == "cross_album"
    assert res.canonical_path == f"/extremoduro/iros-todos-a-tomar-por-culo/{AMA_LIVE}"


def test_la_ruta_canonica_si_resuelve():
    res = ur.resolve_song(
        _catalogo(), "extremoduro", "iros-todos-a-tomar-por-culo", AMA_LIVE
    )
    assert res.status == "ok"
    assert res.entity_id == 101


def test_artista_inventado_no_devuelve_ok():
    res = ur.resolve_path(_catalogo(), f"/loquesea/loquesea/{AMA_LIVE}")
    assert res.status == "redirect"
    assert res.canonical_path == f"/extremoduro/iros-todos-a-tomar-por-culo/{AMA_LIVE}"


def test_album_de_otro_artista_redirige():
    """`/robe/la-ley-innata` es de Extremoduro, no de Robe."""
    res = ur.resolve_album(_catalogo(), "robe", "la-ley-innata")
    assert res.status == "redirect"
    assert res.reason == "wrong_artist"
    assert res.canonical_path == "/extremoduro/la-ley-innata"


# --------------------------------------------------------------------------- #
# Estudio vs directo: el desempate no puede ser `.first()`
# --------------------------------------------------------------------------- #
def test_slug_homonimo_prefiere_estudio():
    cat = _catalogo()
    cat.songs.append(
        SongRow(104, "so-payaso", "So Payaso", "agila", "extremoduro")
    )
    cat.songs.append(
        SongRow(105, "so-payaso", "So Payaso (En Directo)",
                "iros-todos-a-tomar-por-culo", "extremoduro")
    )
    res = ur.resolve_song(cat, "extremoduro", "pedra", "so-payaso")
    assert res.status == "redirect"
    assert res.entity_id == 104          # la de estudio, no la primera por PK


def test_homonimo_ambiguo_no_elige_al_azar():
    """Dos de estudio con el mismo slug: no hay respuesta correcta → 404."""
    cat = _catalogo()
    cat.songs.append(SongRow(104, "x", "X", "agila", "extremoduro"))
    cat.songs.append(SongRow(105, "x", "X", "deltoya", "extremoduro"))
    res = ur.resolve_song(cat, "extremoduro", "pedra", "x")
    assert res.status == "not_found"
    assert res.reason == "ambiguous"


# --------------------------------------------------------------------------- #
# Typos: el resolver tolerante solo actúa si es inequívoco
# --------------------------------------------------------------------------- #
def test_typo_de_cancion_dentro_del_disco_correcto():
    res = ur.resolve_song(
        _catalogo(), "extremoduro", "agila", "abre-el-pecho-y-registra"
    )
    assert res.status == "redirect"
    assert res.reason == "typo_slug"
    assert res.canonical_path == "/extremoduro/agila/abreme-el-pecho-y-registra"


def test_cancion_inexistente_en_disco_correcto_es_404():
    res = ur.resolve_song(_catalogo(), "extremoduro", "agila", "cancion-fantasma")
    assert res.status == "not_found"
    assert res.reason == "ghost_song"


def test_los_tres_casos_que_hubo_que_arreglar_a_mano():
    """`fix_internal_links_manual.py` existía porque el resolver no llegaba.

    Si estos tres salen solos, ese script deja de hacer falta.
    """
    cat = _catalogo()
    cat.songs += [
        SongRow(110, "bri-bri-bli-bli-en-el-mas-sucio-rincon-de-mi-negro-corazon"
                "-en-directo", "Bri bri bli bli… (En Directo)",
                "iros-todos-a-tomar-por-culo", "extremoduro"),
        SongRow(111, "primer-movimiento-despues-de-la-catarsis",
                "Primer movimiento: después de la catarsis",
                "mayeutica", "robe"),
    ]
    esperado = {
        ("extremoduro", "agila", "abre-el-pecho-y-registra"):
            "/extremoduro/agila/abreme-el-pecho-y-registra",
        ("extremoduro", "iros-todos-a-tomar-por-culo", "bri-bri-bli-bli-en-directo"):
            "/extremoduro/iros-todos-a-tomar-por-culo/bri-bri-bli-bli-en-el-mas"
            "-sucio-rincon-de-mi-negro-corazon-en-directo",
        ("robe", "mayeutica", "despues-de-la-catarsis"):
            "/robe/mayeutica/primer-movimiento-despues-de-la-catarsis",
    }
    for (art, alb, cancion), destino in esperado.items():
        res = ur.resolve_song(cat, art, alb, cancion)
        assert res.status == "redirect", (art, alb, cancion, res)
        assert res.canonical_path == destino, (cancion, res.canonical_path)


def test_parecido_ambiguo_no_inventa_destino():
    """Dos candidatos igual de parecidos: mejor un 404 que un enlace al azar."""
    cat = _catalogo()
    cat.songs += [
        SongRow(120, "canto-primero", "Canto primero", "agila", "extremoduro"),
        SongRow(121, "canto-tercero", "Canto tercero", "agila", "extremoduro"),
    ]
    res = ur.resolve_song(cat, "extremoduro", "agila", "canto-cuarto")
    assert res.status == "not_found"


# --------------------------------------------------------------------------- #
# Secciones fuera del árbol del catálogo: antes eran invisibles
# --------------------------------------------------------------------------- #
def test_seccion_valida():
    res = ur.resolve_path(_catalogo(), "/personas/robe-iniesta")
    assert res.status == "ok"
    assert res.entity_type == "person"


def test_persona_inventada_se_detecta():
    """`check_url` daba por buena cualquier URL fuera de /artista/*."""
    res = ur.resolve_path(_catalogo(), "/personas/quien-sea")
    assert res.status == "not_found"
    assert res.reason == "ghost_entity"


def test_sello_enlazado_como_grupo_se_manda_a_sellos():
    """Caso real en prod: 14 enlaces a /grupos/{avispa,warner,pasion,…}.

    Los sellos comparten tabla con los grupos (`bands.kind`) pero se sirven bajo
    /sellos, así que esos enlaces daban 404. Se sabe dónde viven: se redirige.
    """
    res = ur.resolve_path(_catalogo(), "/grupos/el-dromedario-records")
    assert res.status == "redirect"
    assert res.reason == "wrong_section"
    assert res.canonical_path == "/sellos/el-dromedario-records"


def test_grupo_enlazado_como_sello_tambien():
    cat = _catalogo()
    cat.sections[("grupos", "marea")] = (205, True)
    res = ur.resolve_path(cat, "/sellos/marea")
    assert res.status == "redirect"
    assert res.canonical_path == "/grupos/marea"


def test_post_sin_publicar_existe_pero_se_marca():
    res = ur.resolve_path(_catalogo(), "/blog/borrador-sin-publicar")
    assert res.status == "ok"
    assert res.reason == "unpublished"


def test_rutas_estaticas_no_se_validan():
    for ruta in ("/", "/blog", "/discografia", "/buscar", "/legal"):
        assert ur.resolve_path(_catalogo(), ruta).status == "not_catalog"


def test_ruta_de_cuatro_segmentos_es_fantasma():
    res = ur.resolve_path(_catalogo(), "/extremoduro/deltoya/ama/extra")
    assert res.status == "not_found"


# --------------------------------------------------------------------------- #
# Normalización y extracción
# --------------------------------------------------------------------------- #
def test_normalize_path():
    assert ur.normalize_path("/temas/libertad#versos") == "/temas/libertad"
    assert ur.normalize_path("/temas/libertad?x=1") == "/temas/libertad"
    assert ur.normalize_path("/temas/libertad/") == "/temas/libertad"
    assert ur.normalize_path("https://entreinteriores.com/temas/x") == "/temas/x"
    assert ur.normalize_path("https://genius.com/algo") is None
    assert ur.normalize_path("mailto:hola@ejemplo.com") is None
    assert ur.normalize_path("#ancla") is None


def test_extract_internal_links_coge_markdown_y_html():
    body = (
        "Ver [Deltoya](/extremoduro/deltoya) y "
        '<a href="/personas/robe-iniesta">Robe</a>, '
        "más [fuera](https://genius.com/x) y [repe](/extremoduro/deltoya)."
    )
    assert ur.extract_internal_links(body) == [
        "/extremoduro/deltoya", "/personas/robe-iniesta",
    ]


# --------------------------------------------------------------------------- #
# Guard de escritura
# --------------------------------------------------------------------------- #
def test_guard_reescribe_el_enlace_cruzado(monkeypatch):
    cat = _catalogo()
    monkeypatch.setattr(ur, "DbCatalog", lambda db: cat)
    body = f"Suena en [Pedrá](/extremoduro/pedra/{AMA_LIVE}) desde el 97."
    res = ur.guard_internal_links(None, body)
    assert f"/extremoduro/iros-todos-a-tomar-por-culo/{AMA_LIVE}" in res.body_md
    assert res.fixed and not res.unlinked


def test_guard_desenlaza_el_fantasma_conservando_el_texto(monkeypatch):
    cat = _catalogo()
    monkeypatch.setattr(ur, "DbCatalog", lambda db: cat)
    body = "Lo contó [Fulano de Tal](/personas/fulano-de-tal) en una entrevista."
    res = ur.guard_internal_links(None, body)
    assert res.body_md == "Lo contó Fulano de Tal en una entrevista."
    assert res.unlinked == ["/personas/fulano-de-tal"]


def test_guard_arregla_tambien_el_enlace_ABSOLUTO(monkeypatch):
    """Caso real de prod: el LLM escribe la URL con dominio y todo.

    El extractor la normalizaba a la ruta y el reescritor buscaba solo la forma
    relativa, así que salían 14 hallazgos y «0 cambios». Además el destino se
    escribe relativo: un enlace interno no necesita el dominio.
    """
    cat = _catalogo()
    monkeypatch.setattr(ur, "DbCatalog", lambda db: cat)
    body = (
        "Reflejando su [pasión](https://entreinteriores.com/sellos/no-existe) "
        "y [otra](https://entreinteriores.com/extremoduro/pedra/" + AMA_LIVE + ")."
    )
    res = ur.guard_internal_links(None, body)
    assert "entreinteriores.com" not in res.body_md
    assert f"/extremoduro/iros-todos-a-tomar-por-culo/{AMA_LIVE}" in res.body_md
    assert "Reflejando su pasión" in res.body_md      # el texto se queda


def test_guard_con_barra_final_y_ancla(monkeypatch):
    cat = _catalogo()
    monkeypatch.setattr(ur, "DbCatalog", lambda db: cat)
    body = "Mira [esto](/extremoduro/pedra/" + AMA_LIVE + "/#versos)."
    res = ur.guard_internal_links(None, body)
    assert f"/extremoduro/iros-todos-a-tomar-por-culo/{AMA_LIVE}#versos" in res.body_md


def test_guard_arregla_el_enlace_en_HTML(monkeypatch):
    cat = _catalogo()
    monkeypatch.setattr(ur, "DbCatalog", lambda db: cat)
    body = f'Ver <a href="/extremoduro/pedra/{AMA_LIVE}">la canción</a>.'
    res = ur.guard_internal_links(None, body)
    assert f'href="/extremoduro/iros-todos-a-tomar-por-culo/{AMA_LIVE}"' in res.body_md


def test_guard_no_toca_lo_que_esta_bien(monkeypatch):
    cat = _catalogo()
    monkeypatch.setattr(ur, "DbCatalog", lambda db: cat)
    body = "Está en [Deltoya](/extremoduro/deltoya) y en [/temas](/temas/libertad)."
    res = ur.guard_internal_links(None, body)
    assert res.body_md == body
    assert not res.changed


def test_guard_nunca_lanza(monkeypatch):
    def explota(_db):
        raise RuntimeError("la BD se cayó")

    monkeypatch.setattr(ur, "DbCatalog", explota)
    body = "Un cuerpo con [algo](/lo-que-sea)."
    assert ur.guard_internal_links(None, body).body_md == body
