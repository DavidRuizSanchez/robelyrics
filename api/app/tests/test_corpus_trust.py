"""Clasificador de confianza del corpus.

Lo que se blinda: que solo entre SOLO lo que es la voz de alguien de casa en un
canal fiable, y que un nombre corto («Fito», «Leiva», «Robe») no identifique a
nadie sin contexto — los casos Fito Páez y Guardiola.
"""
from __future__ import annotations

import pytest

from app.services.corpus_trust import (
    ROBE,
    MediosCorpus,
    Video,
    Voz,
    clasificar,
    voces_de_yaml,
    voces_en,
)

UOHO = Voz(slug="inaki-anton", nombre="Uoho", relacion="miembro",
           alias=("Uoho", "Iñaki Antón"))
LEIVA = Voz(slug="leiva", nombre="Leiva", relacion="amigo",
            alias=("Leiva", "José Miguel Conejo Torres"))
VOCES = [ROBE, UOHO, LEIVA]
MEDIOS = MediosCorpus(canales={"UC_RTVE": "RTVE"})


def _video(title, channel="juancaraes", channel_id=None, desc="", dur=900.0, relevante=True):
    return Video(video_id="x", title=title, channel_title=channel, channel_id=channel_id,
                 description=desc, duration_s=dur, relevante=relevante)


def test_robe_entrevistado_en_un_medio_es_nivel_a():
    v = clasificar(_video("Entrevista a Robe Iniesta en La Hora del Rock", "RTVE", "UC_RTVE"),
                   VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == "robe_interview" and v.voces == ["robe-iniesta"]


def test_un_miembro_es_voz_propia_pero_no_robe():
    v = clasificar(_video("Iñaki Antón, Uoho, nos cuenta cómo se grabó Agila", "RTVE", "UC_RTVE"),
                   VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == "entorno_interview"


def test_el_canal_oficial_cuenta_como_fiable():
    v = clasificar(_video("Robe - Charla con el público (Extremoduro)", "Robe"), VOCES, MEDIOS)
    assert v.nivel == "A"


@pytest.mark.parametrize("titulo", [
    "Fito Páez - entrevista completa",           # «Fito» a secas no es nadie
    "Leiva habla de su nuevo disco",             # un apellido corto sin contexto
    "Bath robe review: the best of 2026",        # «robe» en inglés
])
def test_un_nombre_corto_sin_contexto_no_identifica_a_nadie(titulo):
    assert voces_en(titulo, VOCES) == []


def test_un_nombre_corto_con_robe_al_lado_si():
    assert [v.slug for v in voces_en("Leiva recuerda a Robe en la SER", VOCES)] == ["leiva"]


def test_un_medio_sin_voz_es_fondo():
    v = clasificar(_video("Especial Extremoduro: 30 años de Agila", "RTVE", "UC_RTVE"),
                   VOCES, MEDIOS)
    assert v.nivel == "B" and v.kind == "media_report"


def test_la_voz_en_un_canal_de_fan_espera_el_clic():
    v = clasificar(_video("Entrevista a Robe Iniesta (1996) subida por un fan", "Rockero88"),
                   VOCES, MEDIOS)
    assert v.nivel == "C" and v.voces == ["robe-iniesta"]


def test_una_cancion_no_entra_ni_en_un_medio():
    # Un directo en un medio NO es Robe hablando: es Robe cantando, y la letra
    # ya está en la BD.
    v = clasificar(_video("Robe Iniesta - Ama, ama y ensancha el alma (directo)", "RTVE",
                          "UC_RTVE"), VOCES, MEDIOS)
    assert v.nivel == "descartado"


# Títulos y canales REALES de la primera muestra (24-10-2026).

def test_el_canal_oficial_sin_charla_es_musica():
    v = clasificar(_video("Robe - Nada que perder", "Robe", dur=420.0), VOCES, MEDIOS)
    assert v.nivel == "descartado"


def test_robe_a_secas_basta_en_su_canal():
    v = clasificar(_video("ROBE RUEDA DE PRENSA", "Robe", dur=6600.0), VOCES, MEDIOS)
    assert v.nivel == "A" and v.voces == ["robe-iniesta"]


def test_el_canal_de_un_miembro_es_fiable():
    woody = Voz(slug="woody-amores", nombre="Woody Amores", relacion="miembro",
                alias=("Woody Amores",))
    v = clasificar(_video("ENTREVISTA A ROBE EN CANAL EXTREMADURA RADIO", "Woody Amores",
                          dur=1860.0), [*VOCES, woody], MEDIOS)
    assert v.nivel == "A" and v.kind == "robe_interview"


def test_un_alias_corto_sigue_sin_contar_en_un_canal_de_fan():
    v = clasificar(_video("ROBE RUEDA DE PRENSA", "Rockero88"), VOCES, MEDIOS)
    assert v.nivel == "C" and v.voces == []


@pytest.mark.parametrize("canal,dur", [
    ("Leo Reaccion", 900.0),       # reacción
    ("Pedrá Tributo", 900.0),      # banda tributo
    ("RTVE", 40.0),                # short
    ("RTVE", 5 * 3600.0),          # streaming de horas
])
def test_descartes_duros(canal, dur):
    v = clasificar(_video("Entrevista a Robe Iniesta", canal, "UC_RTVE", dur=dur), VOCES, MEDIOS)
    assert v.nivel == "descartado"


def test_lo_irrelevante_se_descarta():
    v = clasificar(_video("Tutorial de violonchelo", "Tesônica", relevante=False), VOCES, MEDIOS)
    assert v.nivel == "descartado"


def test_un_amigo_sin_evidencia_no_entra_aunque_este_en_el_fichero(tmp_path):
    f = tmp_path / "voces.yaml"
    f.write_text(
        "voces:\n"
        "  - slug: con-prueba\n    nombre: Con Prueba\n"
        "    evidencia:\n      - url: https://ejemplo.org\n        cita: amigo de Robe\n"
        "  - slug: sin-prueba\n    nombre: Sin Prueba\n    evidencia: []\n",
        encoding="utf-8",
    )
    assert [v.slug for v in voces_de_yaml(f)] == ["con-prueba"]


def test_el_fichero_real_de_voces_tiene_evidencia_en_cada_entrada():
    from pathlib import Path

    import yaml

    ruta = Path(__file__).resolve().parents[3] / "data" / "corpus_voices.yaml"
    if not ruta.exists():
        ruta = Path("/app/data/corpus_voices.yaml")
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    for v in datos["voces"]:
        assert v["evidencia"], v["slug"]
        for e in v["evidencia"]:
            assert e["url"].startswith("https://") and e["cita"] and e["comprobado"], v["slug"]


def test_el_fichero_real_de_medios_carga_sin_ids_repetidos():
    from pathlib import Path

    import yaml

    ruta = Path(__file__).resolve().parents[3] / "data" / "corpus_media.yaml"
    if not ruta.exists():
        ruta = Path("/app/data/corpus_media.yaml")
    medios = MediosCorpus.desde_yaml(ruta)
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))["medios"]
    ids = [c["channel_id"] for m in datos for c in m.get("youtube") or []]
    assert len(ids) == len(set(ids)) == len(medios.canales)
    assert all(i.startswith("UC") and len(i) == 24 for i in ids)
    # Los tres medios del veto levantado el 23-10-2026 están dentro.
    assert {"mondosonoro.com", "efeeme.com", "rockdelux.com"} <= set(medios.dominios)


def test_un_nombre_comun_solo_cuenta_con_contexto(tmp_path):
    f = tmp_path / "voces.yaml"
    f.write_text(
        "voces:\n"
        "  - slug: tomas-rodriguez\n    nombre: Tomás Rodríguez\n    alias: []\n"
        "    alias_ambiguos: [Tomás Rodríguez]\n"
        "    evidencia:\n      - url: https://ejemplo.org\n        cita: mánager\n",
        encoding="utf-8",
    )
    voces = voces_de_yaml(f)
    assert voces_en("Tomás Rodríguez, nuevo fichaje del Betis", voces) == []
    assert [v.slug for v in voces_en("Tomás Rodríguez recuerda los inicios de Extremoduro",
                                     voces)] == ["tomas-rodriguez"]


def test_si_habla_otro_de_robe_no_es_la_voz_de_robe():
    v = clasificar(_video("ENTREVISTA | Iñaki “Uoho”: su verdad sobre Robe, Extremoduro y el "
                          "dolor que no superó", "Diario ABC", "UC_RTVE", dur=1500.0),
                   VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == "entorno_interview"


@pytest.mark.parametrize("titulo,kind", [
    ("Leiva: \"No había podido escuchar a Robe hasta ahora\"", "entorno_interview"),
    ("Robe: \"No le veo el sentido ir a los conciertos con teléfonos móviles", "robe_interview"),
])
def test_una_cita_en_el_titulo_es_alguien_hablando(titulo, kind):
    v = clasificar(_video(titulo, "RTVE", "UC_RTVE", dur=130.0), VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == kind


def test_una_cita_de_otros_sobre_robe_no_es_su_voz():
    # Primer backfill real (24-10-2026): la cita es de los locutores.
    v = clasificar(_video("Las voces de la radio despiden a Robe Iniesta: \"Sus canciones "
                          "deberían estudiarse en Selectividad\"", "RTVE", "UC_RTVE",
                          dur=300.0), VOCES, MEDIOS)
    assert v.nivel == "B" and v.kind == "media_report"


def test_quien_firma_la_cita_es_la_voz_principal():
    v = clasificar(_video("Robe Iniesta: \"Uoho y yo empezamos juntos\"", "RTVE", "UC_RTVE"),
                   VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == "robe_interview"


def test_cantar_en_un_homenaje_es_musica():
    v = clasificar(_video("Leiva canta 'El hombre pájaro' en el Sonorama en homenaje a Robe "
                          "Iniesta | EL PAÍS", "RTVE", "UC_RTVE", dur=180.0), VOCES, MEDIOS)
    assert v.nivel == "descartado"


def test_el_canal_de_un_musico_sin_charla_es_musica():
    sucio = Voz(slug="carlos-el-sucio", nombre="el Sucio", relacion="miembro",
                alias=("el Sucio",))
    v = clasificar(_video("El Sucio: En el Cosmos (Official Music Video)", "EL SUCIO ",
                          dur=200.0), [*VOCES, sucio], MEDIOS)
    assert v.nivel == "descartado"


def test_responder_es_hablar():
    v = clasificar(_video("¿Volverá Extremoduro? Iñaki \"Uoho\" responde", "RTVE", "UC_RTVE",
                          dur=70.0), VOCES, MEDIOS)
    assert v.nivel == "A" and v.kind == "entorno_interview"


# Spam REAL del 25-10-2026: canales que rellenan la descripción con nuestros
# nombres para salir en las búsquedas. Se aprobaron en lote y entraron al corpus.
_RELLENO = "#robeiniesta #extremoduro Robe Iniesta, Leiva, Fito Cabrales, Platero y Tú"


@pytest.mark.parametrize("titulo,canal", [
    ("Un Pais Magico - Tarragona #documentalesinteresantes #tarragona", "Templario 3.0"),
    ("THE FIRST REBIRTH - JONES & STEPHENSON #remembermusic #djs #session",
     "RKL REMEMBER SOUNDS"),
    ("The Tyets - LÈPIC FINAL DE GIRA #trap #pop #regueton", "Templario 3.0"),
])
def test_un_canal_de_fan_que_solo_nos_nombra_en_la_descripcion_no_entra(titulo, canal):
    v = clasificar(Video(video_id="x", title=titulo, channel_title=canal, description=_RELLENO,
                         duration_s=2973.0, relevante=True, relevante_en_titulo=False),
                   VOCES, MEDIOS)
    assert v.nivel == "descartado" and "descripción" in v.motivos[0]


def test_en_un_canal_de_fan_el_titulo_si_cuenta():
    v = clasificar(Video(video_id="x", title="El Kanka sobre Robe: su voz, su libertad",
                         channel_title="Cadena Fan", description=_RELLENO, duration_s=300.0,
                         relevante=True, relevante_en_titulo=True), VOCES, MEDIOS)
    assert v.nivel == "C"


def test_en_un_medio_la_descripcion_sigue_valiendo():
    v = clasificar(Video(video_id="x", title="Especial: 40 años de rock en Extremadura",
                         channel_title="RTVE", channel_id="UC_RTVE",
                         description="Con Robe Iniesta y Extremoduro", duration_s=1800.0,
                         relevante=True, relevante_en_titulo=False), VOCES, MEDIOS)
    assert v.nivel == "B"


def test_la_cita_firmada_con_nombre_y_mote_es_de_esa_voz():
    # ABC, 25-10-2026: ni «Iñaki 'Uoho'» ni «Iñaki “Uoho”» son un alias literal.
    from app.services.corpus_trust import quien_cita

    for titulo in ("Iñaki 'Uoho': «Ahora estoy sintiendo las mismas cosas»",
                   "Iñaki “Uoho”: «Robe era así»"):
        assert quien_cita(titulo, VOCES) is UOHO, titulo
    assert quien_cita("Las voces de la radio despiden a Robe: «Un genio»", VOCES) is None
