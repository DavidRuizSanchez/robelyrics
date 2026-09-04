"""Tests del extractor DETERMINISTA de atribuciones canción→álbum (sin LLM/BD).

Blindan el caso real del incidente: «Ama, ama y ensancha el alma» (2 «ama»)
atribuida a «¿Dónde están mis amigos?» cuando es de «Deltoya» — con la variante
de título que rompía el lookup exacto y dejó pasar el error.
"""
from __future__ import annotations

from app.services import fact_check as fc


def _index() -> fc.CatalogIndex:
    """Índice de catálogo mínimo construido a mano (sin BD)."""
    songs = {
        fc._norm("Ama, Ama, Ama y Ensancha el Alma"): [
            fc._SongRef("Deltoya", 1992, "Extremoduro", "studio"),
            fc._SongRef("Iros todos a tomar por culo", 1997, "Extremoduro", "live"),
        ],
        fc._norm("So Payaso"): [fc._SongRef("Agila", 1996, "Extremoduro", "studio")],
    }
    def n(t):
        return fc._norm(t)
    album_titles = {n("Deltoya"), n("¿Dónde están mis amigos?"), n("Agila"),
                    n("Iros todos a tomar por culo")}
    return fc.CatalogIndex(
        songs=songs,
        albums={n("Deltoya"): 1992, n("¿Dónde están mis amigos?"): 1993,
                n("Agila"): 1996, n("Iros todos a tomar por culo"): 1997},
        album_titles=album_titles,
        album_kind={n("Deltoya"): "studio", n("¿Dónde están mis amigos?"): "studio",
                    n("Agila"): "studio", n("Iros todos a tomar por culo"): "live"},
        album_url={n("Deltoya"): "/extremoduro/deltoya"},
        album_display={n("Deltoya"): "Deltoya",
                       n("¿Dónde están mis amigos?"): "¿Dónde están mis amigos?",
                       n("Agila"): "Agila",
                       n("Iros todos a tomar por culo"): "Iros todos a tomar por culo"},
        book_titles=set(),
    )


def test_fuzzy_resuelve_titulo_con_ama_de_menos():
    idx = _index()
    refs = idx.refs_for_song("Ama, ama y ensancha el alma")  # 2 «ama»
    assert refs and refs[0].album_title == "Deltoya"


def test_extrae_atribucion_album_erronea():
    idx = _index()
    body = ('No se puede hablar de amor sin mencionar "Ama, ama y ensancha el alma". '
            'Esta canción, del álbum ¿Dónde están mis amigos? (1993), es una joya.')
    claims = fc.extract_catalog_claims(body, idx)
    assert len(claims) == 1
    assert claims[0].type == "song_album"
    assert fc._norm(claims[0].object) == fc._norm("¿Dónde están mis amigos?")


def test_refuta_y_corrige_album_y_anio():
    idx = _index()
    body = ('"Ama, ama y ensancha el alma", del álbum ¿Dónde están mis amigos? (1993), '
            'es una declaración.')
    claims = fc.extract_catalog_claims(body, idx)
    verdicts = [fc.resolve_claim(None, c, index=idx, use_web=False) for c in claims]
    rep = fc.FactCheckReport(verdicts=verdicts)
    assert rep.autofixes and rep.autofixes[0].correct_value == "Deltoya"
    fixed, skipped = fc.correct_body(None, body, rep, index=idx)
    assert "Deltoya (1992)" in fixed
    assert "¿Dónde están mis amigos?" not in fixed
    assert not skipped


def test_atribucion_correcta_no_genera_claim():
    idx = _index()
    body = '"So payaso", del álbum Agila (1996), abre el disco.'
    assert fc.extract_catalog_claims(body, idx) == []


def test_disco_en_directo_no_refuta():
    # La canción también sale en el directo "Iros todos…": no es error.
    idx = _index()
    body = ('"Ama, ama y ensancha el alma", del disco Iros todos a tomar por culo, '
            'en directo.')
    assert fc.extract_catalog_claims(body, idx) == []


# --------------------------------------------------------------------------- #
# Regresión: canciones homónimas en varios discos (los dos discos gemelos)
# --------------------------------------------------------------------------- #
# El catálogo distingue la misma canción en distintos discos con un sufijo entre
# paréntesis: «Emparedado» (Tú en tu casa…, 1990) y «Emparedado (Rock
# Transgresivo)» (Rock Transgresivo, 1994). Como el índice solo guardaba el
# título literal, preguntar por «Emparedado» encontraba una sola de las dos
# apariciones y decir que está en el otro disco se refutaba como si fuese falso.
# El fact_check llegó a reescribir un texto CORRECTO dejándolo contradictorio:
#   «Jesucristo García (Tú en tu casa…)» · Extremoduro · Rock Transgresivo (1994)
# Afectaba a 32 de las 152 filas de canción del catálogo.

def _index_gemelos() -> fc.CatalogIndex:
    def n(t):
        return fc._norm(t)
    ref_1990 = fc._SongRef("Tú en tu casa, nosotros en la hoguera", 1990,
                           "Extremoduro", "studio")
    ref_1994 = fc._SongRef("Rock Transgresivo", 1994, "Extremoduro", "studio")
    songs = {
        n("Emparedado"): [ref_1990, ref_1994],          # base: ambas apariciones
        n("Emparedado (Rock Transgresivo)"): [ref_1994],
    }
    titulos = {n("Tú en tu casa, nosotros en la hoguera"), n("Rock Transgresivo"),
               n("Deltoya")}
    return fc.CatalogIndex(
        songs=songs,
        albums={n("Tú en tu casa, nosotros en la hoguera"): 1990,
                n("Rock Transgresivo"): 1994, n("Deltoya"): 1992},
        album_titles=titulos,
        album_kind={t: "studio" for t in titulos},
        album_url={},
        album_display={n("Tú en tu casa, nosotros en la hoguera"):
                       "Tú en tu casa, nosotros en la hoguera",
                       n("Rock Transgresivo"): "Rock Transgresivo",
                       n("Deltoya"): "Deltoya"},
        book_titles=set(),
    )


def test_base_song_title_recorta_solo_el_sufijo():
    assert fc._base_song_title("Emparedado (Rock Transgresivo)") == "Emparedado"
    assert fc._base_song_title("Deltoya (En Directo)") == "Deltoya"
    assert fc._base_song_title("So Payaso") == "So Payaso"
    assert fc._base_song_title("") == ""


def test_cancion_gemela_no_se_refuta_en_ninguno_de_sus_dos_discos():
    idx = _index_gemelos()
    for album in ("Rock Transgresivo", "Tú en tu casa, nosotros en la hoguera"):
        claim = fc.Claim(
            text=f"«Emparedado» pertenece al disco «{album}».",
            type="song_album", quote="", subject="Emparedado", object=album,
            risk="high",
        )
        v = fc._resolve_db(idx, claim)
        assert v is None or v.status == "confirmed", (
            f"«Emparedado» SÍ está en «{album}», no puede refutarse: {v}"
        )


def test_disco_ajeno_si_se_sigue_refutando():
    """El arreglo no puede desactivar la protección de verdad."""
    idx = _index_gemelos()
    claim = fc.Claim(
        text="«Emparedado» pertenece al disco «Deltoya».",
        type="song_album", quote="", subject="Emparedado", object="Deltoya",
        risk="high",
    )
    v = fc._resolve_db(idx, claim)
    assert v is not None and v.status == "refuted"
