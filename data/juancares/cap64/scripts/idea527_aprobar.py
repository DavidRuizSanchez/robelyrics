"""#527 «Robe y Plasencia»: opción A de David (10-11-2026), pieza nueva.

Ajusta el ángulo al material verificado (data/reference/personas_cap64_web.md y
fuentes_web_personas.md), quita las dos búsquedas que el reparto da por cubiertas en otra
página (no canibalizar) y la aprueba. El borrador lo escribe el cron
`generate_approved_drafts` y el post queda en revisión: NO se publica solo.
"""
import json

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.content_merge import excluir_keywords

ANGULO = ("Pieza evergreen sobre la relación de Robe con Plasencia, dueña de las búsquedas «robe "
          "plasencia» y «mural robe plasencia». Con lo verificado: Hijo Predilecto (aprobado el 8 de "
          "abril de 2026 por unanimidad); los DOS murales de Robe en la ciudad, el macromural de Jesús "
          "Mateos Brea con Manolo Chinato en la plaza Puerto de Béjar (encargo municipal, bodegones que "
          "reinterpretan canciones y poemas, interior inaugurado en mayo de 2026 y exterior terminado en "
          "agosto) y el de Primo en la plaza de San Martín (Robe con tres buitres); el festival Primeras "
          "Flores Amarillas. Enlaza a /lugares/plasencia (los orígenes del grupo ya están allí) sin "
          "repetirlos. Nada de lo que no esté verificado.")

with SessionLocal() as db:
    p = db.get(ContentProposal, 527)
    assert p.status == "proposed", p.status
    p.angle = ANGULO
    excluir_keywords(p, ["primeras flores amarillas", "donde nacio robe"])
    p.status = "approved"
    p.scheduled_for = None
    db.commit()
    activas = [k["keyword"] for k in p.keywords if not k.get("excluded")]
    print(json.dumps({"id": p.id, "status": p.status, "target": p.target_keyword,
                      "activas": activas}, ensure_ascii=False))
