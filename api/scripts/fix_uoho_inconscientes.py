"""Corrige el dato falso sobre Inconscientes en la ficha de Uoho.

El motor lo generó a partir de la `bio_short` truncada, que se cortó en
«vocalista principa» justo detrás de nombrar a Inconscientes. La ficha de la
banda dice lo correcto —Jon Calvo, de Memoria de Pez, era el vocalista— así que
las dos páginas del propio sitio se contradecían.
"""
import sys

sys.path.insert(0, "/app")
from sqlalchemy import select

from app.db.models import Person, SeoContent
from app.db.session import SessionLocal
from app.services.content_guard import find_especulacion, no_loss_verdict

VIEJO = ("Otro proyecto destacado fue **Inconscientes**, donde Uoho asumió un papel "
         "prominente como guitarrista y vocalista principal.")
NUEVO = ("Otro proyecto destacado fue **Inconscientes**, que montó en 2006 con Miguel "
         "Colino al bajo y José Ignacio Cantera a la batería, ambos de "
         "Extremoduro, y con Jon Calvo —vocalista y guitarrista de Memoria de "
         "Pez— al frente del micrófono. Uoho puso la guitarra; la voz la llevó "
         "Calvo.")

db = SessionLocal()
p = db.execute(select(Person).where(Person.slug == "inaki-uoho-anton")).scalar_one()
c = db.execute(select(SeoContent).where(
    SeoContent.entity_type == "person", SeoContent.entity_id == p.id)).scalar_one()

if VIEJO not in c.body_md:
    print("✗ no encuentro la frase exacta; abortando para no tocar a ciegas")
    print("  buscaba:", VIEJO[:80])
    raise SystemExit(1)

nuevo_body = c.body_md.replace(VIEJO, NUEVO, 1)
v = no_loss_verdict(c.body_md, nuevo_body)
print("gate no-pérdida:", v.resumen())
esp = find_especulacion(nuevo_body)
print("especulación:", esp or "(vacío)")
if not v.ok or esp:
    print("ABORTADO")
    raise SystemExit(1)

if "--apply" in sys.argv:
    with open("/tmp/uoho_backup.md", "w", encoding="utf-8") as fh:
        fh.write(c.body_md)
    c.body_md = nuevo_body
    db.commit()
    print("APLICADO · backup en /tmp/uoho_backup.md")
else:
    print("\ndry-run. Quedaría:")
    print(" ", NUEVO)
