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


def test_la_voz_sin_senal_de_charla_no_entra_sola():
    # Un directo en un medio NO es Robe hablando: es Robe cantando.
    v = clasificar(_video("Robe Iniesta - Ama, ama y ensancha el alma (directo)", "RTVE",
                          "UC_RTVE"), VOCES, MEDIOS)
    assert v.nivel == "B"


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
