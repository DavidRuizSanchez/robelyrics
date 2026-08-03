"""Da a cada versión de un tema gemelo su propio término, para que dejen de
competir entre ellas.

Medido el 03-08-2026: 7 de 8 familias tenían el MISMO `target_keyword` en todas
sus versiones, y las tres «Jesucristo García» se disputaban «jesucristo garcía
significado» —el directo en la posición 9,1 y el debut en la 6,9— repartiéndose
las impresiones en vez de sumarlas.

No se pone `canonical` entre ellas a propósito: son grabaciones DISTINTAS y el
propio material de referencia del proyecto dice que esa diferencia es lo que hay
que contar en cada ficha (data/reference/rock_transgresivo_y_tu_en_tu_casa.md).
Un canonical las borraría de Google, y con ellas las 44 impresiones que hoy tiene
el directo.

El reparto va por INTENCIÓN, no por tracción bruta: la ficha que mejor responde
«qué significa» es la del tema original, y la que mejor responde «en directo» es
la del disco en vivo. Cada una se queda con lo suyo.

Solo toca metadatos. El cuerpo no se toca, así que no hay gate de no-pérdida que
pasar.
"""
import sys

sys.path.insert(0, "/app")
from sqlalchemy import select, update  # noqa: E402

from app.db.models import SeoContent, Song  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

# slug -> (target_keyword, meta_title, meta_description)
# Escritos a mano: son nueve y tienen que ser exactos.
PLAN = {
    # --- Jesucristo García: tres versiones, tres intenciones
    "jesucristo-garcia": (
        "Jesucristo García significado",
        "Jesucristo García: significado de la letra de Extremoduro",
        "Qué significa «Jesucristo García» de Extremoduro: la figura de "
        "Evaristo, la crítica religiosa y de dónde sale la canción del debut.",
    ),
    "jesucristo-garcia-en-directo": (
        "Jesucristo García en directo",
        "Jesucristo García en directo: Iros todos a tomar por culo",
        "La versión en directo de «Jesucristo García» que Extremoduro grabó para "
        "«Iros todos a tomar por culo» (1997): cómo suena y en qué se distingue.",
    ),
    "jesucristo-garcia-rock-transgresivo": (
        "Jesucristo García Rock Transgresivo",
        "Jesucristo García en Rock Transgresivo: la versión de 1994",
        "La «Jesucristo García» de Rock Transgresivo (1994) sale de la maqueta de "
        "1989 remezclada por Uoho, no de la grabación del debut. Qué cambia.",
    ),
    # --- La hoguera
    "la-hoguera-en-directo": (
        "La hoguera en directo",
        "La hoguera en directo: Iros todos a tomar por culo (1997)",
        "La versión en vivo de «La hoguera» en «Iros todos a tomar por culo», el "
        "primer disco en directo de Extremoduro.",
    ),
    "la-hoguera-rock-transgresivo": (
        "La hoguera Rock Transgresivo",
        "La hoguera en Rock Transgresivo: la versión de 1994",
        "«La hoguera» de Rock Transgresivo (1994) viene de la maqueta de 1989 "
        "remezclada, con tomas nuevas de Uoho. En qué se diferencia del debut.",
    ),
    # --- Resto de gemelas del 94: el debut se queda lo genérico
    "extremaydura-rock-transgresivo": (
        "Extremaydura Rock Transgresivo",
        "Extremaydura en Rock Transgresivo: la versión de 1994",
        "La «Extremaydura» de Rock Transgresivo (1994) procede de la maqueta de "
        "1989 remezclada por Uoho, no de la toma que publicó Avispa en 1990.",
    ),
    "romperas-rock-transgresivo": (
        "Romperás Rock Transgresivo",
        "Romperás en Rock Transgresivo: la versión de 1994",
        "«Romperás» en Rock Transgresivo (1994): la toma de la maqueta de 1989 "
        "remezclada, frente a la que grabaron en los estudios M-20 para el debut.",
    ),
    "decidi-rock-transgresivo": (
        "Decidí Rock Transgresivo",
        "Decidí en Rock Transgresivo: la versión de 1994",
        "«Decidí» en Rock Transgresivo (1994) sale de la maqueta de 1989 "
        "remezclada con capas nuevas de Uoho. Qué la distingue de la del debut.",
    ),
    "emparedado-rock-transgresivo": (
        "Emparedado Rock Transgresivo",
        "Emparedado en Rock Transgresivo: la versión de 1994",
        "«Emparedado» en Rock Transgresivo (1994): la toma que viene de la maqueta "
        "de 1989 remezclada, distinta de la que publicó Avispa en el debut.",
    ),
    "arrebato-rock-transgresivo": (
        "Arrebato Rock Transgresivo",
        "Arrebato en Rock Transgresivo: la versión de 1994",
        "«Arrebato» en Rock Transgresivo (1994) procede de la maqueta de 1989 "
        "remezclada por Uoho, no de la grabación de los estudios M-20.",
    ),
    # --- Amor castúo: solo existe en el debut y en el directo
    "amor-castuo-en-directo": (
        "Amor castúo en directo",
        "Amor castúo en directo: la única versión que circuló",
        "«Amor castúo» se quedó fuera de Rock Transgresivo, así que durante años "
        "la única versión al alcance fue esta, la del directo de 1997.",
    ),
}

aplicar = "--apply" in sys.argv
db = SessionLocal()
cambios = 0
for slug, (kw, title, desc) in PLAN.items():
    song = db.execute(select(Song).where(Song.slug == slug)).scalar_one_or_none()
    if song is None:
        print(f"  ✗ no existe la canción {slug}")
        continue
    c = db.execute(select(SeoContent).where(
        SeoContent.entity_type == "song", SeoContent.entity_id == song.id
    )).scalar_one_or_none()
    if c is None:
        print(f"  ✗ sin ficha SEO: {slug}")
        continue
    if len(title) > 60 or len(desc) > 155:
        print(f"  ✗ ABORTA {slug}: title {len(title)}c, desc {len(desc)}c")
        continue
    print(f"  {slug}")
    print(f"     kw    : {c.target_keyword or '—'}  →  {kw}")
    print(f"     title : {(c.meta_title or '—')[:52]}  →  {title[:52]}")
    if aplicar:
        db.execute(update(SeoContent).where(
            SeoContent.entity_type == "song", SeoContent.entity_id == song.id
        ).values(target_keyword=kw, meta_title=title, meta_description=desc))
        cambios += 1

if aplicar:
    db.commit()
    print(f"\nAPLICADO a {cambios} fichas.")
else:
    print("\ndry-run: no se ha escrito nada (--apply para aplicar)")
