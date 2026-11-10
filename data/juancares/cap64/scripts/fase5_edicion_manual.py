"""Edición quirúrgica de los BORRADORES de Paco Doniga y Mateos Brea (10-11-2026).

Solo toca filas `seo_content` de persona NO publicadas, con reemplazos exactos (si
un fragmento no está tal cual, falla y no escribe nada). Cada cambio corrige un
dato contra su fuente (fuentes_web_personas.md). Después vuelve a pasar el editor
jefe y lo imprime. No publica.
"""
import json

from app.db.models import Person, SeoContent
from app.db.session import SessionLocal
from app.services.editorial_review import review

CAMBIOS = {
    "paco-doniga": [
        ("Paco Doniga tocaba el bajo en Indecisión Momentánea, junto a",
         "Paco Doniga militaba en Indecisión Momentánea, junto a"),   # W-10: «militaba»
        ("Doniga se aprendió los temas y tocó cuatro o cinco, entre ellos algunas versiones de "
         "Rory Gallagher. Otra fuente concreta que el repertorio incluyó dos de las primeras "
         "composiciones de Robe y dos versiones del músico irlandés.",
         "Doniga se aprendió los temas para la ocasión. Tocaron dos de las primeras canciones "
         "escritas por Robe y dos versiones de Rory Gallagher; él lo recuerda como «cuatro o "
         "cinco» temas."),                                             # W-10 + T-05
    ],
    "jesus-mateos-brea": [
        ("En 2024, Mateos Brea pintó en Salorino «La matanza rural extremeña»",
         "En Salorino, Mateos Brea pintó «La matanza rural extremeña»"),  # W-04: marcador de 2023
        ("Ese año también creó en Arroyo de la Luz",
         "En 2024 creó en Arroyo de la Luz"),                             # W-05
        ("Tampoco explicaron cómo estaban hechas sus obras: querían que Mateos Brea hiciera su "
         "propia lectura.",
         "Según cuenta el artista, tampoco quisieron explicarle cómo estaban hechas sus obras, "
         "para que el mural fuera su propia lectura."),                   # T-14: es testimonio
        ("una obra de 600 metros cuadrados en la plaza Puerto de Béjar",
         "una obra de unos 600 metros cuadrados en la plaza Puerto de Béjar"),  # W-07/W-08
    ],
}

with SessionLocal() as db:
    for slug, cambios in CAMBIOS.items():
        p = db.query(Person).filter(Person.slug == slug).one()
        sc = db.query(SeoContent).filter(SeoContent.entity_type == "person",
                                         SeoContent.entity_id == p.id).one()
        assert not sc.published, f"{slug} está publicada: no se edita aquí"
        body = sc.body_md
        for viejo, nuevo in cambios:
            assert body.count(viejo) == 1, f"{slug}: no encuentro «{viejo[:60]}»"
            body = body.replace(viejo, nuevo)
        sc.body_md = body
        db.commit()
        v = review(body, kind="person", subject=p.stage_name or p.full_name)
        print(json.dumps({"slug": slug, "verdict": v.verdict, "score": v.score,
                          "reasons": v.reasons}, ensure_ascii=False), flush=True)
