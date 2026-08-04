"""Todos los versos de un motivo, en orden cronológico, desde las letras reales.

Para las páginas de CONCEPTO y TEMA —«la amapola», «el espejo», «la lucha»—, que
tratan un motivo del cancionero. Es la herramienta que las arregla, y funciona
porque el fallo de esas fichas siempre es el mismo: las escribió el motor sin
consultar el corpus de letras, así que citan cuatro o cinco apariciones cuando
hay siete, y las repiten en dos o tres secciones que dicen lo mismo.

    python /tmp/versos_del_motivo.py 'amapola'
    python /tmp/versos_del_motivo.py 'luch(a|ar|ando|ador)|batalla'

La receta, medida el 04-08-2026 en tres fichas (45→85, 57→85, 45→85):

  1. Sacar TODAS las apariciones con este script. Salen del campo `lyrics_raw`,
     que es la fuente autoritativa: ni el corpus ni el motor.
  2. Ordenarlas CRONOLÓGICAMENTE. Deja de ser una lista y pasa a contar algo —
     casi siempre que el motivo cruza de Extremoduro a la etapa en solitario.
  3. Citar cada verso UNA vez. La redundancia entre secciones es el motivo por
     el que estas fichas suspenden.
  4. Añadir las que la ficha no menciona, que suelen ser las de los discos
     últimos. En «la lucha» faltaban tres, dos de ellas del disco final.
  5. Conservar cada verso, enlace y canción del original: el gate lo exige, y
     una mención perdida se ve con `que_falta.py`.
"""
import sys, re
sys.path.insert(0, "/app")
from sqlalchemy import text
from app.db.session import SessionLocal
db = SessionLocal()
patron = sys.argv[1]
rows = db.execute(text("""SELECT s.slug, s.title, a.slug ab, a.title at, a.year, ar.slug ar,
       s.lyrics_raw FROM songs s JOIN albums a ON a.id=s.album_id
       JOIN artists ar ON ar.id=a.artist_id
       WHERE s.lyrics_raw ~* :p ORDER BY a.year, s.title"""), {"p": patron}).fetchall()
vistos = set()
print(f"canciones con /{patron}/: {len(rows)}\n")
for r in rows:
    if (r.at, r.title) in vistos:
        continue
    vistos.add((r.at, r.title))
    ms = {m.group(0).strip() for m in re.finditer(rf"[^\n]*{patron}[^\n]*", r.lyrics_raw or "", re.I)}
    print(f"{r.year} · {r.at} · {r.title}   (/{r.ar}/{r.ab}/{r.slug})")
    for v in list(ms)[:3]:
        print(f"      «{v}»")
