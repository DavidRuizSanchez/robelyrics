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


def test_sin_tres_historias_afirmables_no_hay_post():
    """#399: sin material no se cae al motor de fichas; no hay post."""
    album = type("A", (), {"title": "Bienvenidos al temporal", "id": 1})()
    flojas = [hd.Historia("g", "dato", "hechos duros", "x" * 30, "hechos", True),
              hd.Historia("g", "contexto", "P1", "x" * 30, "tercero", False)]
    assert hd.escribir(None, None, album, flojas, hechos_duros="") is None


def test_el_redactor_por_historias_esta_apagado_por_defecto():
    from app.services import draft_generator as dg

    assert dg.POR_HISTORIAS.get() is False


def test_la_muletilla_no_es_una_pregunta_del_periodista():
    """Rueda de prensa de Destrozares (19-11-2026): «¿no?» es de Robe."""
    from app.services.instagram.clip_picker import habla_el_protagonista

    ok, _ = habla_el_protagonista("da un poco de miedo, ¿no? Sí, a mí sí, da mucho miedo",
                                  usar_llm=False)
    assert ok
    no, motivo = habla_el_protagonista("¿Y cómo se compuso el disco?", usar_llm=False)
    assert not no and "pregunta" in motivo


def test_una_cita_recortada_o_parafraseada_no_pasa():
    fuente = ("Yo creo que forman un todo. Podría haber diferencias. La mayor es que las "
              "canciones de este último disco están compuestas en un tiempo más corto.")
    bien = "Robe lo dijo claro: «Yo creo que forman un todo. Podría haber diferencias.»"
    assert hd.citas_que_fallan(bien, fuente, []) == []
    # 368-2: el arranque de la cita se perdió y el final quedó en boca del narrador.
    roto = "Podría haber diferencias. La mayor es que las canciones de este último disco.»"
    assert hd.citas_que_fallan(roto, fuente, [])
    inventada = "Robe dijo: «no veía ninguna diferencia entre los dos discos»"
    assert hd.citas_que_fallan(inventada, fuente, [])
    # Un título largo entre comillas no es una cita.
    titulo = "Destrozares, canciones para el final de los tiempos"
    assert hd.citas_que_fallan(f"En «{titulo}» hay diez canciones.", fuente, [titulo]) == []


def test_la_trayectoria_sale_de_la_discografia(monkeypatch):
    from types import SimpleNamespace

    from app.services import robe_facts
    L = robe_facts.Lanzamiento
    monkeypatch.setattr(robe_facts, "discography", lambda db: [
        L("Mayéutica", 2021, "studio", "robe"),
        L("Se nos lleva el aire", 2023, "studio", "robe"),
        L("Grandes éxitos y fracasos", 2024, "compilation", "robe"),
    ])
    t = hd.trayectoria(None, SimpleNamespace(title="Se nos lleva el aire"))
    assert "«Mayéutica» (2021, Robe)" in t
    assert "ÚLTIMO disco de estudio" in t          # el recopilatorio no cuenta
    assert "10 de diciembre de 2025" in t


def test_sin_historias_no_cae_al_generador_clasico(monkeypatch):
    """19-11-2026: el clásico escribió «19 de noviembre de 2023» sin material."""
    from types import SimpleNamespace

    from app.services import draft_generator as dg

    album = SimpleNamespace(id=1, title="X", artist_id=1, release_date=None, year=2023)

    class _Db:
        def get(self, model, ident):
            return album

        def execute(self, *a, **k):
            return SimpleNamespace(all=lambda: [])

    monkeypatch.setattr(dg, "_deep_body", lambda *a, **k: None)
    monkeypatch.setattr(dg, "generate_album_anniversary",
                        lambda **k: (_ for _ in ()).throw(AssertionError("clásico")))
    p = SimpleNamespace(kind="album-anniversary", source_type="album", source_id=1,
                        quality_tier="standard", target_keyword="", title="X")
    monkeypatch.setattr("app.services.catalog_ideas.entidad_de", lambda st: None)
    tok = dg.POR_HISTORIAS.set(True)
    try:
        assert dg.generate_body(_Db(), p) is None
    finally:
        dg.POR_HISTORIAS.reset(tok)


def test_quitar_una_frase_no_parte_la_cita():
    from app.services import source_guard

    t = ("Juancares lo resume así: «Pero no solo cambia eso. El violín es otro instrumento "
         "más». Robe toca la guitarra.")
    limpio, quitadas = source_guard.limpiar(t, ["Juancares"])
    assert "»" not in limpio and "violín" not in limpio
    assert limpio == "Robe toca la guitarra."


def test_robe_con_su_medio_se_cita():
    from app.services import source_guard

    t = "Robe contó a Diario de Noticias de Navarra: «Yo creo que forman un todo. Podría haber diferencias»."
    assert source_guard.limpiar(t, [])[0] == t


def test_el_cierre_no_llama_ultimo_a_otro_disco():
    malo = "«Mayéutica» (2021) fue el último disco de estudio de Robe. Robe falleció en 2025."
    assert hd.cierre_falso(malo, "Se nos lleva el aire", True)
    bueno = ("Llegó después de «Mayéutica» (2021) y es el último disco de estudio de Robe, "
             "«[Se nos lleva el aire](/robe/se-nos-lleva-el-aire)».")
    assert not hd.cierre_falso(bueno, "Se nos lleva el aire", True)
    assert hd.cierre_falso("Fue su último disco.", "Destrozares", False)


def test_una_entrevista_de_youtube_no_se_entrecomilla():
    p = {"kind": "robe_interview", "title": "Rueda de prensa de Robe",
         "url": "https://www.youtube.com/watch?v=x"}
    assert hd.es_transcrita(p)
    assert not hd.es_transcrita({"kind": "robe_interview", "title": "Entrevista a Robe",
                                 "url": "https://www.rocksesion.com/x"})
    pasaje = "para entender lo que significa Destrozares hay que oír la canción"
    fallos = hd.citas_que_fallan(f"Robe lo dijo: «{pasaje}».", pasaje, [], no_citable=pasaje)
    assert fallos and "SIN comillas" in fallos[0]


def test_cita_sin_quien_lo_dice_y_subtitulo():
    fuente = "Y tristes... pienso que hay toques esperanzadores en las canciones del disco"
    assert hd.citas_que_fallan("«Y tristes. pienso que hay toques esperanzadores en las "
                               "canciones del disco»", fuente, [])        # sin quién
    assert hd.citas_que_fallan("Robe lo dijo: «Y tristes. pienso que hay toques "
                               "esperanzadores en las canciones del disco»", fuente, []) == []
    titulo = "Destrozares, canciones para el final de los tiempos"
    assert hd.citas_que_fallan("El subtítulo, «canciones para el final de los tiempos», "
                               "pesa.", fuente, [titulo], no_citable="x") == []


def test_frases_de_proceso():
    for f in ("En la entrevista transcrita, Robe explicó que…",
              "Robe vinculó el título con esa reflexión, pero no explicó que el aire se lleve "
              "las cosas.", "El material identifica esos temas."):
        assert hd._PROCESO.search(f), f
    assert not hd._PROCESO.search("Robe explicó que la dejó cuando le pareció redonda.")


def test_secciones_de_edicion_de_wikipedia():
    from app.services.album_facts import Dato, secciones_de_edicion

    wikitexto = (
        "{{Ficha de álbum}}\n== Historia ==\nTexto.\n== Grabación y producción ==\n"
        "El disco fue grabado en los estudios [[MuxikOn]] por Iñigo Etxebarrieta"
        "<ref>x</ref>, y producido por José Luis Crespo.\n{{cita|una valoración}}\n"
        "== Lista de canciones ==\n# Uno\n")
    secs = secciones_de_edicion(wikitexto)
    assert secs == [("Grabación y producción", "El disco fue grabado en los estudios "
                     "MuxikOn por Iñigo Etxebarrieta, y producido por José Luis Crespo.")]
    linea = Dato("seccion", f"{secs[0][0]}: {secs[0][1]}").linea()
    assert linea.startswith("Grabación y producción: El disco") and "Wikipedia" not in linea


def test_mas_frases_de_proceso():
    for f in ("El título no viene acompañado aquí de una explicación de Robe.",
              "Robe no detalló qué canciones habría recortado."):
        assert hd._PROCESO.search(f), f


def test_cierre_con_encabezado_y_salto():
    cierre = ("## El último disco de estudio de Robe\n«Se nos lleva el aire» fue el último "
              "disco de estudio de Robe. Antes publicó «Mayéutica» (2021).")
    assert not hd.cierre_falso(cierre, "Se nos lleva el aire", True)


def test_robe_advirtio_con_su_medio_se_cita():
    from app.services import source_guard

    t = "En una entrevista de 2016 con Diario de Noticias de Navarra, Robe advirtió que no era triste."
    assert source_guard.limpiar(t, [])[0] == t
    assert hd._PROCESO.search("La transcripción menciona también «A la orilla del río».")


def test_la_grabacion_entra_siempre_si_hay_datos():
    hechos = ("Sello: El Dromedario Records.\nGrabación: Las canciones estaban compuestas "
              "desde el confinamiento. El bajo y la batería se grabaron en Estudio Uno.")
    h = hd.historia_de_grabacion(hechos)
    assert h and h.afirmable and h.ancla == "grabacion" and "Estudio Uno" in h.tramo
    assert hd.historia_de_grabacion("Sello: X.") is None


def test_la_nota_del_editor_sobrevive_al_juicio():
    from app.services.draft_generator import con_nota

    previas = {"nota": "Enfoque: el primer aniversario de la muerte de Robe"}
    assert con_nota({"pasa": False}, previas)["nota"].startswith("Enfoque")
    assert "nota" not in con_nota({"pasa": True}, {"pasa": False, "motivos": []})
    # Y la siguiente vuelta la conserva también.
    v2 = con_nota({"pasa": True}, con_nota({"pasa": False}, previas))
    assert v2["nota"] == previas["nota"]


def test_la_grabacion_de_la_entradilla_de_wikipedia():
    from app.services.album_facts import frases_de_edicion_en_entradilla

    wt = ("{{Ficha de álbum\n|nombre = Bienvenidos al temporal\n|grabación = 2017\n}}\n"
          "'''Bienvenidos al temporal''' es el único álbum en directo de Robe.\n\n"
          "Los escenarios elegidos para la grabación del disco fueron el [[Teatro romano de "
          "Mérida]] y el [[WiZink Center]] de Madrid.\nLa gira repasaba sus discos.\n"
          "== Lista de canciones ==\n")
    t = frases_de_edicion_en_entradilla(wt)
    assert t == ("Los escenarios elegidos para la grabación del disco fueron el Teatro romano "
                 "de Mérida y el WiZink Center de Madrid.")


def test_album_de_estudio_no_es_dato_de_grabacion():
    from app.services.album_facts import frases_de_edicion_en_entradilla

    wt = "'''Destrozares''' es el segundo álbum de estudio de Robe, publicado en 2016.\n== X ==\n"
    assert frases_de_edicion_en_entradilla(wt) == ""


def test_las_guardas_no_tocan_los_puntos_suspensivos():
    """«Y tristes... pienso» salía «Y tristes. pienso» en una cita de Robe (19-11-2026)."""
    from app.services import source_guard

    t = ("Robe contó a RockFM: «Y tristes... pienso que hay toques esperanzadores, lo fácil "
         "es quedarte con lo primero que te dan... Y lo primero es la portada, el título... "
         "pero el disco hay que oírlo». ¿Y ahora?! Pues eso…")
    assert source_guard.limpiar(t, [])[0] == t
    assert source_guard.quitar_confesiones(t)[0] == t
    # Trocear y juntar devuelve la línea tal cual.
    assert "".join(source_guard._FRASE.findall(t)) == t


def test_la_entradilla_no_repite_cifras_de_las_secciones():
    from datetime import date
    from types import SimpleNamespace

    album = SimpleNamespace(release_date=date(2023, 12, 15))
    resto = "## Listas\nAlcanzó el número uno y estuvo 132 semanas. Entró el 24 de diciembre."
    malo = "Salió el 15 de diciembre de 2023, llegó al número uno y estuvo 132 semanas."
    assert {"repite «132», que ya va en una sección",
            "repite «n.º 1», que ya va en una sección"} <= set(
                hd.cifras_repetidas(malo, resto, album))
    assert hd.cifras_repetidas("Salió el 15 de diciembre de 2023 con El Dromedario.",
                               resto + " Publicado el 15 de diciembre de 2023.", album) == []


def test_una_seccion_solo_lleva_las_cifras_de_su_historia():
    from types import SimpleNamespace

    pieza = SimpleNamespace(fechas_propias=("10", "2025", "63"), release_date=None)
    contexto = "El vídeo se publicó el 11 de diciembre de 2025; el disco, el 30 de enero de 2026."
    bien = "El vídeo salió el 11 de diciembre de 2025, y el disco el 30 de enero de 2026."
    assert hd.cifras_ajenas(bien, contexto, pieza) == []
    mal = bien + " Robe murió el 10 de diciembre de 2025, a los 63 años."
    # La muerte es de la entradilla: ni el día ni la edad caben en otra sección.
    assert hd.cifras_ajenas(mal, contexto, pieza) == ["«10» no es de esta historia: quítalo",
                                                      "«63» no es de esta historia: quítalo"]


def test_numero_uno_es_numero_1_y_un_nombre_no_es_cita():
    from types import SimpleNamespace

    pieza = SimpleNamespace(release_date=None)
    assert hd.cifras_ajenas("Fue número uno.", "fue número 1 sus dos semanas", pieza) == []
    assert hd.citas_que_fallan("Plasencia celebró el festival «Primeras Flores Amarillas».",
                               "el festival «Primeras Flores Amarillas»", []) == []


def test_un_titulo_entre_comillas_es_una_clave():
    from app.services.corpus_for_queries import claves_de, tramos_con

    c = "«Se nos lleva el aire» fue número uno de la lista de álbumes de España."
    assert claves_de(c)[:2] == ["Se nos lleva el aire", "España"]
    material = ("«Se nos lleva el aire» salió el 15 de diciembre de 2023 y fue número 1 de "
                "la lista de álbumes de España sus dos primeras semanas.")
    assert "dos primeras semanas" in tramos_con(material, c)
