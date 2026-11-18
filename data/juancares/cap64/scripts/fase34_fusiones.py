"""Fases 3-4: lanza las fusiones que el reparto recomienda para las ideas #529 y #528.

Es lo mismo que pulsar «ampliar» en el panel: `content_merge.aplicar_plan` crea las
oportunidades `merge` (aprobadas para PREPARAR) y `run_prepare` escribe el borrador con
`merge_deep`. NO publica: el borrador llega por correo y al panel con su antes/después,
y publicarlo es el segundo clic de David.

- #529 → ficha 15 (/extremoduro) con su grupo principal, y ficha 374 (/lugares/plasencia)
  con «concierto extremoduro plasencia». «robe alcalde plasencia» (nuevo) se queda en la idea.
- #528 → ficha 17 (/robe), Dosis Letal.
- #527 (Robe y Plasencia) NO: el reparto la manda, con confianza baja, a un post del
  festival y a otro de los Premios de la Música. Decide David en el panel.

Uso: ssh robelyrics 'docker exec -i robelyrics-api python -' < fase34_fusiones.py
"""
import json

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services import content_merge
from app.services.seo_opportunities import run_prepare

PLAN = {
    529: [{"target": "ficha:15", "keywords": [
              "extremoduro plasencia", "historia de extremoduro", "fundadores de extremoduro",
              "extremoduro en plasencia", "origen de extremoduro", "formacion original extremoduro",
              "extremoduro plasencia 1995", "extremoduro plasencia 2008"]},
          {"target": "ficha:374", "keywords": ["concierto extremoduro plasencia"]}],
    528: [{"target": "ficha:17", "keywords": [
              "dosis letal", "dosis letal robe", "dosis letal extremoduro", "primer grupo de robe"]}],
}

ids = []
with SessionLocal() as db:
    for pid, elecciones in PLAN.items():
        p = db.get(ContentProposal, pid)
        opps = content_merge.aplicar_plan(db, p, elecciones)
        ids += [o.id for o in opps]
        print(json.dumps({"propuesta": pid, "oportunidades": [(o.id, o.path) for o in opps]},
                         ensure_ascii=False), flush=True)
print(json.dumps({"preparar": ids}), flush=True)
print(json.dumps(run_prepare(ids, limit=len(ids)), ensure_ascii=False), flush=True)
