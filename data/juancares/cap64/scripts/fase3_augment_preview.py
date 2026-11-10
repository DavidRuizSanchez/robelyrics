"""Fase 3 (plan del 10-11-2026): PREVISUALIZA la ampliación de las páginas existentes.

Llama a `augment_deep.augment_entity`, que NO persiste nada, con una pista
(`gap_hint`) por página. Las pistas solo apuntan a lo corroborado (Wikipedia, nuestra
referencia) o a testimonios aprobados (`data/reference/testimonios_plasencia_1987.md`).
Si el material no lo respalda, el motor no lo escribe (noop).

Corre dentro del api de prod e imprime un JSON por línea con before/after:
  ssh robelyrics 'docker exec -i robelyrics-api python -' < fase3_augment_preview.py > fase3_preview.jsonl
Aplicar es OTRO paso (fase3_aplicar.py), después de que David lo revise.
"""
import json
import sys

from openai import OpenAI

from app.config import get_settings
from app.db.models import Album, Artist, Person
from app.db.session import SessionLocal
from app.services.entity_resolver import build_corpus_index, load_link_stats
from scripts.seo.augment_deep import augment_entity

OBJETIVOS = [
    ("artist", Artist, "extremoduro",
     "Los orígenes en Plasencia: Dosis Letal, el primer grupo de Robe (1983, con Luisma Beltrán, "
     "Juano, Zósimo «Zosi» Pascual y Paco Doniga al bajo), y la primera formación de 1987 con Kaíto "
     "al bajo y Ángel Lorenzo a la batería, que duró unos cuatro meses antes de que entrara William; "
     "los ensayos en la Casa de la Salud"),
    ("person", Person, "robe-iniesta",
     "Antes de Extremoduro: Dosis Letal, su primer grupo (1983), con Luisma Beltrán, Juano, Zósimo "
     "«Zosi» Pascual y Paco Doniga; y los primeros ensayos de 1987 con Kaíto y Ángel Lorenzo en la "
     "Casa de la Salud de Plasencia"),
    ("person", Person, "kaito",
     "La primera formación de Extremoduro en 1987: Robe, Kaíto y Ángel Lorenzo a la batería, los "
     "ensayos en la Casa de la Salud y la reunión con el alcalde José Luis Mariño para poder ensayar"),
    ("person", Person, "william-extremoduro",
     "William entró a la batería en 1987 sustituyendo a Ángel Lorenzo, el primer batería, que estuvo "
     "unos cuatro meses"),
    ("person", Person, "luis-von-fanta",
     "El Jazz, el bar de Luis «von Fanta» en Plasencia, donde se hacían jams y donde Robe propuso a "
     "Ángel Lorenzo formar el grupo en 1987"),
    ("person", Person, "rafael-gallego",
     "La portada de «Tú en tu casa, nosotros en la hoguera» y el buitre del libreto: la propuesta de "
     "carátula de Susi Iglesias y Gustavo, llegada a través de Miguel Ángel Corisco, frente a la "
     "portada final de Rafa Gallego"),
    ("person", Person, "manolo-chinato",
     "El macromural de Jesús Mateos Brea en Plasencia, que une la poesía de Manolo Chinato con la obra "
     "de Robe"),
    ("album", Album, "tu-en-tu-casa-nosotros-en-la-hoguera",
     "La carátula: el buitre, la bellota explosiva y el lema «Buitre no come alpiste» (propuesta de "
     "Susi Iglesias y Gustavo, que acabó en el libreto) frente a la portada de Rafa Gallego"),
    ("album", Album, "somos-unos-animales",
     "Los coros de María Timón y Belén en «Tu corazón», «Quemando tus recuerdos» y «Desidia»"),
    ("album", Album, "deltoya",
     "Las voces de María Timón y Belén en «Sol de invierno», «Con un latido del reloj», «Papel "
     "secante» y «Ama, ama, ama y ensancha el alma»"),
]

solo = set(sys.argv[1:])  # opcional: slugs concretos
client = OpenAI(api_key=get_settings().openai_api_key)
with SessionLocal() as db:
    indice = build_corpus_index(db)
    stats = load_link_stats()
    for et, modelo, slug, pista in OBJETIVOS:
        if solo and slug not in solo:
            continue
        ent = db.query(modelo).filter(modelo.slug == slug).first()
        if ent is None:
            print(json.dumps({"entity_type": et, "slug": slug, "error": "no existe"}), flush=True)
            continue
        try:
            res = augment_entity(db, client, et, ent, corpus_index=indice, link_stats=stats,
                                 gap_hint=pista)
        except Exception as exc:  # noqa: BLE001 — se informa y se sigue con la siguiente
            print(json.dumps({"entity_type": et, "slug": slug, "error": repr(exc)[:500]}), flush=True)
            continue
        if not res:
            print(json.dumps({"entity_type": et, "slug": slug, "error": "sin ficha"}), flush=True)
            continue
        print(json.dumps({"entity_type": et, "slug": slug, "entity_id": ent.id, "pista": pista,
                          **{k: v for k, v in res.items() if k in (
                              "seo_id", "before", "after", "noop", "grew", "before_len",
                              "after_len", "added_headings", "rigor", "noop_reason",
                              "descartados")}},
                         ensure_ascii=False, default=str), flush=True)
