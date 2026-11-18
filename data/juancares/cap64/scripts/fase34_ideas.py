"""Fases 3-4 (plan del 10-11-2026): tres ideas con búsquedas MEDIDAS para el reparto.

No escribe contenido: crea `content_proposals` en estado `proposed` (como las del
motor de keywords) para que `content_placement` decida, con GSC y la SERP, qué
página es dueña de cada búsqueda: ampliar una existente (fusión, dos fases) o
contenido nuevo. Idempotente por `content_key`.

Volúmenes: DataForSEO, ES/es, 10-11-2026 (analisis_personas/volumenes_plasencia.json).
Solo entran keywords con volumen medido (las n/d se quedan fuera).
El ángulo dirige la MIRADA del redactor a lo corroborado; no es material.

Uso: ssh robelyrics 'docker exec -i robelyrics-api python -' < fase34_ideas.py
"""
import json

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.keyword_research import kw_slug

IDEAS = [
    {
        "content_key": "evergreen:extremoduro-plasencia-origenes",  # la #359 (agosto, genérica) está descartada
        "title": "Extremoduro y Plasencia: de Dosis Letal a la Casa de la Salud",
        "angle": ("Los orígenes del grupo en Plasencia, con lo corroborado: Dosis Letal, el primer "
                  "grupo de Robe (1983); la primera formación de 1987 con Kaíto y Ángel Lorenzo antes "
                  "de William; los ensayos en la Casa de la Salud (testimonio de Ángel Lorenzo); el "
                  "veto del alcalde José Luis Díaz y la carta de Robe; la final del Yamaha Band "
                  "Explosion de 1989."),
        "keywords": [("extremoduro plasencia", 110), ("historia de extremoduro", 90),
                     ("fundadores de extremoduro", 20), ("extremoduro en plasencia", 20),
                     ("concierto extremoduro plasencia", 20), ("origen de extremoduro", 10),
                     ("formacion original extremoduro", 10), ("extremoduro plasencia 1995", 10),
                     ("extremoduro plasencia 2008", 10), ("robe alcalde plasencia", 10)],
    },
    {
        "content_key": "evergreen:robe-plasencia",
        "title": "Robe y Plasencia: la ciudad, los homenajes y los murales",
        "angle": ("La relación de Robe con Plasencia tras su muerte, con lo corroborado: Hijo "
                  "Predilecto a título póstumo y la avenida; los DOS murales (el de Jesús Mateos Brea, "
                  "que une su obra con la poesía de Manolo Chinato, y el de Primo en la plaza de San "
                  "Martín, con Robe y tres buitres); el festival Primeras Flores Amarillas."),
        "keywords": [("homenaje robe plasencia", 2400), ("robe plasencia", 720),
                     ("robe iniesta plasencia", 260), ("primeras flores amarillas", 260),
                     ("mural robe plasencia", 170), ("donde nacio robe", 50),
                     ("primeras flores amarillas plasencia", 30), ("robe hijo predilecto plasencia", 20),
                     ("festival robe plasencia", 20), ("ruta robe plasencia", 10),
                     ("mural robe", 10), ("mural extremoduro", 10)],
    },
    {
        "content_key": "evergreen:dosis-letal",
        "title": "Dosis Letal, el primer grupo de Robe",
        "angle": ("El grupo de 1983 según Wikipedia: Luisma Beltrán (guitarra), Juano (voz), Zósimo "
                  "«Zosi» Pascual (batería) y Paco Doniga (bajo puntual); y lo que cuenta en primera "
                  "persona Paco Doniga (testimonios aprobados)."),
        "keywords": [("dosis letal", 170), ("dosis letal robe", 70), ("dosis letal extremoduro", 10),
                     ("primer grupo de robe", 10)],
    },
]

with SessionLocal() as db:
    out = []
    for idea in IDEAS:
        p = db.query(ContentProposal).filter(ContentProposal.content_key == idea["content_key"]).first()
        if p is None:
            kws = [{"keyword": k, "volume": v, "cpc": None, "competition": None} for k, v in idea["keywords"]]
            objetivo, vol = max(idea["keywords"], key=lambda kv: kv[1])
            p = ContentProposal(
                kind="evergreen", source_type="seo", title=idea["title"], angle=idea["angle"],
                keywords=kws, target_keyword=objetivo, target_keyword_slug=kw_slug(objetivo),
                search_volume=vol, signal_source="dataforseo", status="proposed",
                content_key=idea["content_key"], entities=[],
            )
            db.add(p)
            db.flush()
            estado = "creada"
        else:
            estado = f"ya existía ({p.status})"
        out.append({"id": p.id, "content_key": idea["content_key"], "estado": estado})
    db.commit()
    print(json.dumps(out, ensure_ascii=False))
