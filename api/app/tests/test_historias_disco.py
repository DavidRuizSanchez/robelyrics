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


def test_una_cifra_corta_con_unidad_es_clave():
    from app.services.corpus_for_queries import claves_de, tramos_con

    c = "El sello dedicado a Robe tiene un valor postal de 5 euros."
    assert "5 euros" in claves_de(c)
    assert tramos_con("Correos dedica un sello a Robe, con un valor postal de 5 euros.", c)


def test_robe_murio_en_barakaldo():
    from app.services import robe_facts

    assert "Barakaldo" in robe_facts.DEATH_PLACE
    assert any("Barakaldo" in x for x in robe_facts.must_facts_lines())


def test_una_noticia_solo_tiene_historias_de_su_articulo(monkeypatch):
    articulo = ("Correos lanza un sello dedicado a Robe. La emisión llegará el 23 de noviembre "
                "de 2026 con un valor postal de 5 euros y una tirada de 65.000 ejemplares.")
    monkeypatch.setattr("app.services.news_research._json", lambda *a, **k: {"historias": [
        {"gancho": "Sale el 23 de noviembre", "ancla": "dato", "quien": "hechos",
         "tramo": "La emisión llegará el 23 de noviembre de 2026 con un valor postal de 5 euros"},
        {"gancho": "Inspirado en Deltoya", "ancla": "dato", "quien": "hechos",
         "tramo": "El diseño se inspira en los discos Deltoya y Mayéutica"},   # no está
    ]})
    monkeypatch.setattr(hd, "gancho_fiel", lambda h: h)
    hs = hd.inventario_noticia("Correos dedica un sello a Robe", articulo)
    assert [h.gancho for h in hs] == ["Sale el 23 de noviembre"]


def test_el_redactor_de_noticias_por_historias_esta_apagado_por_defecto():
    from app.services import news_research
    assert news_research.NOTICIAS_POR_HISTORIAS.get() is False


def test_un_ancla_descriptiva_no_tira_la_historia(monkeypatch):
    articulo = "En los primeros cinco días el capítulo ha superado las 66.000 visualizaciones."
    monkeypatch.setattr("app.services.news_research._json", lambda *a, **k: {"historias": [
        {"gancho": "66.000 visualizaciones", "ancla": "Dato de audiencia del documental",
         "quien": "hechos", "tramo": articulo}]})
    monkeypatch.setattr(hd, "gancho_fiel", lambda h: h)
    hs = hd.inventario_noticia("x", articulo)
    assert len(hs) == 1 and hs[0].ancla == "dato"


# --------------------------------------------------------------------------- #
# Noticias por historias: citas, títulos ajenos, contexto y modo breve (20-11-2026)
# --------------------------------------------------------------------------- #
ARTICULO_CUADRO = (
    "El pintor Juan Pérez ha ganado el certamen Rasgo Extremeño con el cuadro El rey de "
    "Extremadura, un retrato inspirado en Robe. El consejero Laureano León entregó el "
    "premio en Badalona el 14 de noviembre de 2026. «Robe es parte de lo que somos», dijo "
    "el consejero durante el acto.")
CASA = ("### Noticias que ya hemos publicado (titular. entradilla)\n"
        "- Leiva publica «Caída libre» con Robe. La canción sale con su vídeo.\n"
        "- Plasencia prepara Flores Amarillas 2027. El festival vuelve en junio.")


def _editor(historias, titulos=()):
    return lambda *a, **k: {"historias": historias, "titulos": list(titulos)}


def test_en_una_noticia_solo_robe_es_citable(monkeypatch):
    articulo = ARTICULO_CUADRO + " Robe dijo en 2008: «Yo hago canciones, no himnos»."
    assert hd.habla_robe("Yo hago canciones, no himnos", articulo)
    monkeypatch.setattr("app.services.news_research._json", _editor([
        {"gancho": "El consejero habló de Robe", "ancla": "declaracion", "quien": "tercero",
         "tramo": "«Robe es parte de lo que somos», dijo el consejero durante el acto"},
        {"gancho": "Robe sobre sus canciones", "ancla": "declaracion", "quien": "robe",
         "tramo": "Robe dijo en 2008: «Yo hago canciones, no himnos»"},
        {"gancho": "El premio se entregó en Badalona", "ancla": "dato", "quien": "cualquiera",
         "tramo": "entregó el premio en Badalona el 14 de noviembre de 2026"}]))
    monkeypatch.setattr(hd, "gancho_fiel", lambda h: h)
    hs = hd.inventario_noticia("Un cuadro de Robe gana en Badalona", articulo)
    assert [(h.quien, h.citable) for h in hs] == [("tercero", False), ("robe", True),
                                                  ("hechos", False)]
    assert {h.fuente for h in hs} == {hd.FUENTE_NOTICIA}


def test_las_palabras_de_un_tercero_no_se_entrecomillan():
    sec = "## El acto\n\nEl consejero dijo: «Robe es parte de lo que somos»."
    fallos = hd.citas_que_fallan(sec, ARTICULO_CUADRO, [], no_citable=ARTICULO_CUADRO)
    assert fallos and "SIN comillas" in fallos[0]
    contado = "## El acto\n\nEl consejero Laureano León dijo que Robe es parte de lo que son."
    assert hd.citas_que_fallan(contado, ARTICULO_CUADRO, [], no_citable=ARTICULO_CUADRO) == []


def test_el_titulo_de_una_obra_ajena_no_es_una_cita(monkeypatch):
    """Un documental o un libro van entre «» y nadie «lo dice». Sin el título en la lista,
    la sección caía por «va sin decir antes quién lo dice»."""
    articulo = (ARTICULO_CUADRO
                + " El acto cerró con el documental La vida que nos dieron las canciones.")
    sec = "## El acto\n\nSe proyectó «La vida que nos dieron las canciones»."
    assert hd.citas_que_fallan(sec, articulo, [], no_citable=articulo)
    monkeypatch.setattr("app.services.news_research._json", _editor(
        [], ["La vida que nos dieron las canciones", "Rasgo Extremeño", "La vida es bella",
             "Robe es parte de lo que somos. Y lo será siempre"]))
    _, titulos, _homenaje = hd.inventario_de_noticia("x", articulo)
    # Solo los que están literales en el artículo, y ninguna frase.
    assert titulos == ("La vida que nos dieron las canciones", "Rasgo Extremeño")
    assert hd.citas_que_fallan(sec, articulo, list(titulos), no_citable=articulo) == []


def test_el_contexto_sale_literal_del_material_de_casa(monkeypatch):
    monkeypatch.setattr("app.services.news_research._json", _editor([
        {"gancho": "En mayo Leiva publicó una canción con Robe",
         "tramo": "Leiva publica «Caída libre» con Robe. La canción sale"},
        {"gancho": "Robe ganó un Grammy", "tramo": "Robe ganó un Grammy en 2020"},   # no está
        {"gancho": "El premio fue en Badalona",                      # es la noticia
         "tramo": "entregó el premio en Badalona el 14 de noviembre de 2026"}]))
    monkeypatch.setattr(hd, "gancho_fiel", lambda h: h)
    hs = hd.inventario_contexto("x", ARTICULO_CUADRO, CASA + "\n" + ARTICULO_CUADRO, [])
    assert [h.tramo for h in hs] == ["Leiva publica «Caída libre» con Robe. La canción sale"]
    assert hs[0].fuente == hd.FUENTE_CASA and hs[0].ancla == "contexto" and hs[0].afirmable
    assert hd.inventario_contexto("x", ARTICULO_CUADRO, "", []) == []


CUERPO = ("El pintor Juan Pérez ha ganado el certamen Rasgo Extremeño con un retrato "
          "inspirado en Robe. " * 4).strip()


SECCION = "## Antes\n\n" + ("Un hecho nuestro que sitúa la noticia. " * 8).strip()


def _escribir(monkeypatch, del_articulo, contexto, *, cuerpo=CUERPO, seccion=SECCION):
    """`escribir_noticia` sin red: devuelve el texto y los prompts que recibió el redactor."""
    prompts = []

    def _sec(client, prompt, fuente, titulos, **k):
        prompts.append({"prompt": prompt, "fuente": fuente, "titulos": titulos, **k})
        return (cuerpo if "CUERPO de la noticia" in prompt else seccion), []

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr("openai.OpenAI", lambda **k: object())
    monkeypatch.setattr("app.services.robe_facts.must_facts_lines", lambda db=None: ["Robe."])
    monkeypatch.setattr(hd, "inventario_de_noticia",
                        lambda t, a: (del_articulo, ("Obra",), False))
    monkeypatch.setattr(hd, "inventario_contexto", lambda t, a, casa, ya, **k: contexto)
    monkeypatch.setattr(hd, "_seccion", _sec)
    return hd.escribir_noticia(None, "Titular", ARTICULO_CUADRO, casa=CASA,
                               fecha="noviembre de 2026"), prompts


def _h(fuente, tramo="un tramo cualquiera del artículo", **k):
    return hd.Historia("g", "dato", fuente, tramo, k.pop("quien", "hechos"), True, **k)


def test_la_noticia_es_un_cuerpo_sin_encabezados_y_una_seccion_de_contexto(monkeypatch):
    """La forma de las dos noticias que David aprobó a mano. Con una sección por historia
    salían cinco apartados repitiendo el mismo premio (muestra del 20-11-2026)."""
    texto, prompts = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA, "tramo uno del artículo"),
                                             _h(hd.FUENTE_NOTICIA, "tramo dos del artículo")],
                               [_h(hd.FUENTE_CASA, "tramo de casa")],
                               cuerpo="## Un encabezado que sobra\n" + CUERPO)
    assert texto == CUERPO + "\n\n" + SECCION
    assert len(prompts) == 2                       # un cuerpo y un contexto, no una por historia
    del_cuerpo, del_contexto = prompts
    assert "«tramo uno del artículo»" in del_cuerpo["prompt"]
    assert "«tramo dos del artículo»" in del_cuerpo["prompt"]
    assert "noviembre de 2026" in del_cuerpo["prompt"]
    assert "Obra" in del_cuerpo["titulos"]         # el título ajeno no cuenta como cita
    # El contexto se comprueba contra el material de casa, no contra el artículo.
    assert "«tramo de casa»" in del_contexto["prompt"]
    assert ARTICULO_CUADRO not in del_contexto["fuente"]


def test_solo_se_puede_entrecomillar_lo_que_dijo_robe(monkeypatch):
    carta = "Tiembla alcalde, porque no conseguirás evitar que en cada calle suene"
    _, prompts = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA, "entregó el premio en Badalona"),
                                         _h(hd.FUENTE_NOTICIA, carta, quien="robe", citable=True)],
                           [])
    comprobar = prompts[0]["extra_check"]
    assert "A Robe se le puede citar" in prompts[0]["prompt"]
    # Robe, aunque la cita sea más larga o más corta que el tramo del inventario.
    assert comprobar(f"Robe escribió: «{carta} una guitarra».") == []
    assert comprobar("Robe escribió: «Tiembla alcalde, porque no conseguirás evitar».") == []
    # Otra persona: sin comillas. El título de una obra no es una cita.
    fallo = comprobar("El consejero dijo: «Robe es parte de lo que somos».")
    assert fallo and "no lo dice Robe" in fallo[0]
    assert comprobar("Ganó con el cuadro «Obra».") == []
    _, prompts = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA), _h(hd.FUENTE_NOTICIA, "otro")], [])
    assert "A Robe se le puede citar" not in prompts[0]["prompt"]


def test_el_redactor_lee_los_parrafos_de_sus_tramos_no_el_articulo_entero():
    """Con la nota de prensa pegada, un artículo pasa de 17.000 caracteres y lo que se
    comprueba se corta a 6.000: lo de más abajo se daba por «no dicho»."""
    relleno = "Párrafo de relleno que no viene a cuento. " * 60
    articulo = "\n\n".join([
        "Correos lanza un sello dedicado a Robe el 23 de noviembre de 2026.", relleno, relleno,
        relleno, "La tirada será de 65.000 ejemplares y el valor postal, de 5 euros.", relleno])
    assert len(articulo) > 9000
    pasaje = hd.pasajes_de(articulo, ["Correos lanza un sello dedicado a Robe",
                                      "La tirada será de 65.000 ejemplares"])
    assert "65.000 ejemplares" in pasaje and "23 de noviembre" in pasaje
    assert "relleno" not in pasaje and len(pasaje) < 400
    # Un artículo en un solo bloque: ventana alrededor del tramo.
    bloque = relleno * 3 + "La tirada será de 65.000 ejemplares y vale 5 euros. " + relleno * 3
    corto = hd.pasajes_de(bloque, ["La tirada será de 65.000 ejemplares"])
    assert "65.000 ejemplares" in corto and len(corto) < 700


def test_un_articulo_fino_da_una_noticia_breve_si_hay_contexto(monkeypatch):
    texto, prompts = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA)], [_h(hd.FUENTE_CASA)])
    assert texto.endswith(SECCION) and len(prompts) == 2


def test_un_articulo_fino_sin_contexto_limpio_no_da_para_un_post(monkeypatch):
    texto, _ = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA)], [_h(hd.FUENTE_CASA)], seccion="")
    assert texto is None
    texto, prompts = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA)], [])
    assert texto is None and prompts == []


def test_sin_historia_del_articulo_no_hay_noticia_aunque_haya_contexto(monkeypatch):
    texto, prompts = _escribir(monkeypatch, [], [_h(hd.FUENTE_CASA), _h(hd.FUENTE_CASA)])
    assert texto is None and prompts == []


def test_si_el_cuerpo_no_sale_limpio_no_hay_noticia(monkeypatch):
    texto, _ = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA), _h(hd.FUENTE_NOTICIA, "otro")],
                         [_h(hd.FUENTE_CASA)], cuerpo="")
    assert texto is None


def test_dos_historias_del_articulo_bastan_sin_contexto(monkeypatch):
    texto, prompts = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA), _h(hd.FUENTE_NOTICIA, "otro")],
                               [])
    assert texto == CUERPO and len(prompts) == 1


def test_la_vara_de_una_noticia_que_no_es_un_concierto(monkeypatch):
    """La rúbrica solo conocía la crónica y el anuncio de un evento: un sello o un premio
    se medían con la vara de un concierto."""
    from app.services import editorial_review as er

    vistos = []

    class _Resp:
        choices = [type("C", (), {"message": type("M", (), {
            "content": '{"verdict": "pass", "score": 80, "reasons": []}'})()})()]

    class _Cliente:
        def __init__(self, **k):
            self.chat = type("X", (), {"completions": type("Y", (), {
                "create": lambda *a, **kw: (vistos.append(kw), _Resp())[1]})()})()

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr("openai.OpenAI", _Cliente)
    monkeypatch.setattr(er, "discografia_real", lambda: "")
    er.review("Correos emite un sello de Robe el 23 de noviembre.", kind="news", subject="sello")
    er.review("El sello sale el 23.", kind="news", subject="x", event_when="future")
    er.review("Un disco.", kind="album", subject="x")
    textos = [str(v) for v in vistos]
    # También con fecha: al sello se le reprochaba «no decir dónde se celebra».
    assert "NOTICIA BREVE" in textos[0] and "NOTICIA BREVE" in textos[1]
    assert "ANUNCIO de un evento FUTURO" in textos[1]
    assert "NOTICIA BREVE" not in textos[2]


def test_un_dia_sin_ano_se_devuelve_al_redactor():
    assert hd.fechas_sin_anio("Actuará el sábado 14 de noviembre en La Bohemia.") == [
        "«14 de noviembre» va sin año: escríbelo con su año"]
    assert hd.fechas_sin_anio("Actuará el 14 de noviembre de 2026; volvió el 31 de mayo de "
                              "2008.") == []


def test_hablar_de_donde_sale_el_dato_es_hablar_del_proceso():
    for frase in ("La información fecha la carta el 11 de mayo de 2000.",
                  "Según la información del material, la carta era de mayo.",
                  "Según el artículo, el premio fue en Badalona.",
                  "El artículo señala que acudieron miles de personas."):
        assert hd._PROCESO.search(frase), frase
    assert not hd._PROCESO.search("Robe fechó la carta el 11 de mayo de 2000.")


def test_un_parrafo_con_almohadillas_no_se_borra():
    """La noticia del sello perdió su entradilla: el modelo la escribió con «## » delante
    y se borró como si fuera un encabezado."""
    entradilla = ("Correos dedicará a Robe un sello que se emitirá el 23 de noviembre de "
                  "2026, dentro de la serie Música de su programa filatélico.")
    texto = hd.sin_encabezados(f"## {entradilla}\n\n## Un encabezado\n\nLas medidas.")
    assert texto == f"{entradilla}\n\nLas medidas."


def test_lo_que_repite_la_noticia_no_es_contexto():
    articulo = ("Correos emite un sello dedicado a Robe con un valor postal de 5 euros y una "
                "tirada de 65.000 ejemplares dentro de la serie Música.")
    assert hd.repite_la_noticia("el 23 de noviembre Correos pondrá en circulación un sello "
                                "con un valor postal de 5 euros y una tirada de 65.000", articulo)
    assert not hd.repite_la_noticia("El 26 de mayo, «Caída libre» ganó el premio a la mejor "
                                    "canción pop-rock", articulo)


def test_un_contexto_de_una_frase_no_entra(monkeypatch):
    texto, _ = _escribir(monkeypatch, [_h(hd.FUENTE_NOTICIA), _h(hd.FUENTE_NOTICIA, "otro")],
                         [_h(hd.FUENTE_CASA)], seccion="## Un título\n\nUna sola frase.")
    assert texto == CUERPO


def test_una_frase_no_es_de_robe_si_el_articulo_no_lo_nombra_al_lado(monkeypatch):
    """Entrevista a Uoho: el editor marcó como de Robe «vendimos cuatrocientas y pico mil
    entradas» y salió entrecomillada."""
    articulo = ("Robe fundó Extremoduro en Plasencia en 1987 y el grupo se disolvió en 2019. "
                + "El guitarrista repasa en esta entrevista su etapa más reciente con calma. " * 4
                + "Uoho recuerda: «vendimos cuatrocientas y pico mil entradas en 2020, cuando "
                "llegó la pandemia». Robe escribió entonces: «Tiembla alcalde, porque no "
                "conseguirás evitar que la gente disfrute».")
    monkeypatch.setattr("app.services.news_research._json", _editor([
        {"gancho": "Las entradas", "ancla": "declaracion", "quien": "robe",
         "tramo": "vendimos cuatrocientas y pico mil entradas en 2020"},
        {"gancho": "La carta", "ancla": "declaracion", "quien": "robe",
         "tramo": "Tiembla alcalde, porque no conseguirás evitar que la gente disfrute"}]))
    hs = hd.inventario_noticia("x", articulo)
    assert [(h.quien, h.citable) for h in hs] == [("tercero", False), ("robe", True)]


def test_la_lista_de_reconocimientos_es_material_de_casa():
    """El «año de homenajes» que en el sello y el cuadro se pegó a mano. Cada hecho va con
    su año y tiene fuente; sin fuente no viaja."""
    from pathlib import Path

    import yaml

    from app.services import news_research as nr
    from app.services.jsonld_audit import ruta_data

    texto = nr.reconocimientos_de_casa()
    assert texto.startswith(nr.CABECERA_RECONOCIMIENTOS)
    hechos = [x[2:] for x in texto.splitlines()[1:]]
    datos = yaml.safe_load(Path(ruta_data("reconocimientos_robe.yaml")).read_text("utf-8"))
    assert len(hechos) == len(datos["reconocimientos"]) >= 4
    for r in datos["reconocimientos"]:
        assert r["fuentes"] and all(f["url"].startswith("https://") and f["extracto"]
                                    for f in r["fuentes"]), r["hecho"]
        assert r["fecha"][:4] in r["hecho"], r["hecho"]       # el año, en la frase
        assert "Robe Iniesta" not in r["hecho"] and "—" not in r["hecho"]
    # Sirve de tramo literal para el contexto, y el propio hecho de la noticia no entra.
    sello = next(h for h in hechos if "Correos" in h)
    articulo = ("Correos emite un sello dedicado a Robe en la serie Música con un valor postal "
                "de 5 euros y una tirada de 65.000 ejemplares.")
    assert hd.repite_la_noticia(sello, articulo)
    medalla = next(h for h in hechos if "Medalla" in h)
    assert hd.tramo_literal(medalla, texto) and not hd.repite_la_noticia(medalla, articulo)


RECONOCIMIENTOS = (
    "El 26 de mayo de 2026, «Caída libre», la canción de Leiva con Robe, ganó el premio a "
    "la mejor canción pop-rock en los III Premios de la Academia de la Música de España.",
    "El 27 de mayo de 2026, en el Teatro de Rojas de Toledo, Alén Ayerdi recogió la Medalla "
    "de Oro al Mérito en las Bellas Artes concedida a Robe.",
    "Correos pone en circulación el 23 de noviembre de 2026 un sello dedicado a Robe, con un "
    "valor postal de 5 euros y una tirada de 65.000 ejemplares.")
ARTICULO_SELLO = ("Correos emite un sello dedicado a Robe en la serie Música con un valor "
                  "postal de 5 euros y una tirada de 65.000 ejemplares.")


def test_el_contexto_de_un_homenaje_son_los_otros_reconocimientos(monkeypatch):
    """Sin preguntar al editor: dejárselo dio una Medalla de 2026 como contexto de una
    carta del año 2000 y ningún reconocimiento para el sello."""
    def _no_se_llama(*a, **k):
        raise AssertionError("un homenaje no pregunta al editor")

    monkeypatch.setattr("app.services.news_research._json", _no_se_llama)
    hs = hd.inventario_contexto("Correos dedica un sello a Robe", ARTICULO_SELLO, "casa", [],
                                homenaje=True, reconocimientos=RECONOCIMIENTOS)
    assert [h.tramo for h in hs] == list(RECONOCIMIENTOS[:2])     # el sello es la noticia
    assert all(h.fuente == hd.FUENTE_CASA and h.afirmable for h in hs)


def test_lo_que_no_es_un_homenaje_no_ve_la_lista_de_reconocimientos(monkeypatch):
    vistos = []
    monkeypatch.setattr("app.services.news_research._json",
                        lambda sistema, usuario, **k: (vistos.append(usuario), {})[1])
    casa = ("RECONOCIMIENTOS:\n" + "\n".join(f"- {h}" for h in RECONOCIMIENTOS)
            + "\n\nFICHA NUESTRA de Plasencia:\nPlasencia es una ciudad de Cáceres.")
    assert hd.inventario_contexto("La carta de Robe al alcalde", "Robe escribió una carta.",
                                  casa, [], reconocimientos=RECONOCIMIENTOS) == []
    assert "Medalla" not in vistos[0] and "FICHA NUESTRA de Plasencia" in vistos[0]


def test_si_el_redactor_se_empena_en_citar_a_un_tercero_se_escribe_sin_su_frase(monkeypatch):
    llamadas = []

    def _sec(client, prompt, fuente, titulos, **k):
        llamadas.append(prompt)
        return ("" if "lo que dijo el consejero" in prompt else CUERPO), []

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr("openai.OpenAI", lambda **k: object())
    monkeypatch.setattr("app.services.robe_facts.must_facts_lines", lambda db=None: ["Robe."])
    monkeypatch.setattr(hd, "inventario_de_noticia", lambda t, a: ([
        _h(hd.FUENTE_NOTICIA, "entregó el premio en Badalona el 14 de noviembre"),
        _h(hd.FUENTE_NOTICIA, "ganó el certamen Rasgo Extremeño con el cuadro"),
        _h(hd.FUENTE_NOTICIA, "lo que dijo el consejero durante el acto", quien="tercero")],
        (), False))
    monkeypatch.setattr(hd, "inventario_contexto", lambda *a, **k: [])
    monkeypatch.setattr(hd, "_seccion", _sec)
    assert hd.escribir_noticia(None, "Titular", ARTICULO_CUADRO) == CUERPO
    assert len(llamadas) == 2 and "lo que dijo el consejero" not in llamadas[1]


def test_el_inventario_une_dos_pasadas_sin_repetir(monkeypatch):
    respuestas = iter([
        {"historias": [{"gancho": "a", "ancla": "dato", "quien": "hechos",
                        "tramo": "entregó el premio en Badalona el 14 de noviembre de 2026"}],
         "titulos": ["Rasgo Extremeño"], "homenaje": False},
        {"historias": [{"gancho": "a", "ancla": "dato", "quien": "hechos",
                        "tramo": "entregó el premio en Badalona el 14 de noviembre de 2026"},
                       {"gancho": "b", "ancla": "dato", "quien": "hechos",
                        "tramo": "ha ganado el certamen Rasgo Extremeño con el cuadro"}],
         "titulos": ["El rey de Extremadura"], "homenaje": True}])
    monkeypatch.setattr("app.services.news_research._json", lambda *a, **k: next(respuestas))
    hs, titulos, homenaje = hd.inventario_de_noticia("x", ARTICULO_CUADRO)
    assert [h.gancho for h in hs] == ["a", "b"]
    assert titulos == ("Rasgo Extremeño", "El rey de Extremadura") and homenaje is True


def test_lo_que_el_articulo_recuerda_de_pasada_si_puede_ser_contexto():
    """El artículo del sello nombraba la Medalla; el cuerpo no la contaba, y aun así se
    quedaba fuera del contexto por «repetir la noticia»."""
    articulo = ARTICULO_SELLO + " " + RECONOCIMIENTOS[1]
    ya = [hd.Historia("g", "dato", hd.FUENTE_NOTICIA, ARTICULO_SELLO, "hechos", True)]
    hs = hd.inventario_contexto("Correos dedica un sello a Robe", articulo, "casa", ya,
                                homenaje=True, reconocimientos=RECONOCIMIENTOS)
    assert [h.tramo for h in hs] == list(RECONOCIMIENTOS[:2])


def test_los_reconocimientos_van_tal_cual_sin_pasar_por_el_redactor(monkeypatch):
    llamadas = []

    def _sec(client, prompt, fuente, titulos, **k):
        llamadas.append(prompt)
        return CUERPO, []

    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr("openai.OpenAI", lambda **k: object())
    monkeypatch.setattr("app.services.robe_facts.must_facts_lines", lambda db=None: ["Robe."])
    monkeypatch.setattr(hd, "inventario_de_noticia", lambda t, a: (
        [_h(hd.FUENTE_NOTICIA, ARTICULO_SELLO)], (), True))
    monkeypatch.setattr(hd, "_seccion", _sec)
    texto = hd.escribir_noticia(None, "Correos dedica un sello a Robe", ARTICULO_SELLO,
                                reconocimientos=RECONOCIMIENTOS)
    assert len(llamadas) == 1                      # solo el cuerpo
    assert texto == (f"{CUERPO}\n\n## {hd.ENCABEZADO_RECONOCIMIENTOS}\n\n"
                     f"{RECONOCIMIENTOS[0]}\n\n{RECONOCIMIENTOS[1]}")
