"""Genera posts de GIRAS de Extremoduro/Robe como propuestas (pending_review).

Crea ContentProposal (kind='evergreen', status pending_review) — NO publica.
El admin las revisa/edita y publica desde /biblioteca/admin. Grounded con datos
verificables de los libros (ver data/reference/*.md): no inventar.

Idempotente: salta si ya existe una propuesta con el mismo título.

Uso: python -m scripts.blog.generate_tour_posts
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import ContentProposal
from app.services.content_generator import generate_seo_article
from scripts.research.common import get_session, log

# Datos verificables por gira (de De Profundis + research). El generador
# parafrasea con la voz megafan punki; estos hechos son su materia prima.
TOURS = [
    {
        "title": "Pedrá en directo (1995): media hora de una sola canción",
        "angle": "La gira de Pedrá, el disco de una sola canción de casi media hora.",
        "context": "Pedrá (proyecto de 1993, editado feb 1995 por DRO). Banda Pedrá: "
        "Selu (saxo, ex Reincidentes, ideólogo), Robe, Iñaki Uoho Antón (entonces "
        "en Platero y Tú), Diego Garay 'Dieguillo' (bajo), Gari (batería), con Fito "
        "Cabrales. Ensayaron en comuna cerca de Durango (Vizcaya). La gira arrancó en "
        "el Pabellón de Deportes del Real Madrid el 5 de mayo de 1995 ante más de "
        "5.000 personas; en directo tocaban Pedrá dos veces.",
    },
    {
        "title": "La gira de Extremoduro y Platero y Tú (1995)",
        "angle": "La gira conjunta con Platero y Tú, hermandad y cartel circense.",
        "context": "Verano-noviembre de 1995. Extremoduro y Platero y Tú (la banda de "
        "Uoho y Fito Cabrales) de gira conjunta, cartel circense. Cierre en el Palacio "
        "de los Deportes de Madrid los días 8 y 9 de noviembre de 1995, de donde salió "
        "el directo 'Iros todos a tomar por culo' (1997).",
    },
    {
        "title": "Moñigos, morid (1999): la gira de Canciones prohibidas",
        "angle": "La gira de Canciones prohibidas con Fito & Fitipaldis de teloneros.",
        "context": "Gira de 1999 tras Canciones prohibidas (1998). Fito & Fitipaldis "
        "debutaban como teloneros (con 'A puerta cerrada'). Formación con Uoho a la "
        "guitarra y Cantera a la batería ya oficiales.",
    },
    {
        "title": "Gira 2002: Yo, minoría absoluta sobre los escenarios",
        "angle": "La gira de Yo, minoría absoluta, con llenos históricos.",
        "context": "Gira 2002 de Yo, minoría absoluta (2002). Dos noches en La Cubierta "
        "de Leganés ante más de 20.000 personas; agotaron el Recinto Hípico de Cáceres. "
        "Quedó documentada en el DVD 'Gira 2002'. Formación Robe, Uoho, Cantera, Miguel "
        "Colino + Aiert Erkoreka (teclados) y Félix Landa (guitarra).",
    },
    {
        "title": "Grandes éxitos y fracasos (2004): la gira de la regrabación",
        "angle": "La gira de 2004 alrededor de los Grandes éxitos y fracasos.",
        "context": "Gira de 2004: arrancó en Lleida el 14 de mayo y terminó en Salamanca "
        "el 13 de noviembre, 40 ciudades. Coincidió con los recopilatorios 'Grandes "
        "éxitos y fracasos' (Episodios primero y segundo), donde regrabaron los primeros "
        "discos.",
    },
    {
        "title": "Robando perchas del hotel (2012): la última gran gira de Extremoduro",
        "angle": "La gira de 2012, el salto a América y el cierre en Cáceres.",
        "context": "Gira 'Robando perchas del hotel' (2012; nombre inspirado en un "
        "artículo de Juan José Millás). Cerca de 150.000 entradas. En 2012 Extremoduro "
        "cruzó por primera vez el charco (Argentina, Chile, Uruguay), 25 años después de "
        "fundarse. Cierre en el Recinto Hípico de Cáceres el 13 de octubre de 2012 ante "
        "15.000 personas, con despedida emotiva de Robe.",
    },
    {
        "title": "Para todos los públicos (2014): el último adiós de Extremoduro",
        "angle": "La gira de despedida de Extremoduro antes de su disolución.",
        "context": "Gira de 'Para todos los públicos' (2013), organizada por El "
        "Dromedario Records, por España y Latinoamérica. Fue la última etapa de "
        "Extremoduro; el grupo anunció su disolución el 18 de diciembre de 2019.",
    },
    {
        "title": "Robe en solitario: de Lo que aletea a Ni santos ni inocentes",
        "angle": "Las giras de la etapa en solitario de Robe con su banda extremeña.",
        "context": "Tras Extremoduro, Robe giró en solitario con su banda (Álvaro "
        "Rodríguez Barroso, Carlitos Pérez, Alber Fuentes, David Lerman, Lorenzo "
        "González y, desde 2019, Woody Amores). Giras de 'Lo que aletea en nuestras "
        "cabezas' (2015, directo 'Bienvenidos al temporal' en el Teatro Romano de "
        "Mérida, Palau de la Música y WiZink), 'Mayéutica' ('Ahora es cuando', 2021-22) "
        "y 'Se nos lleva el aire' ('Ni santos ni inocentes', 2024), gira en la que "
        "sufrió un tromboembolismo en noviembre de 2024. Robe falleció el 10 de "
        "diciembre de 2025.",
    },
]


def main() -> None:
    created = skipped = failed = 0
    with get_session() as db:
        for t in TOURS:
            exists = db.execute(
                select(ContentProposal).where(ContentProposal.title == t["title"])
            ).scalar_one_or_none()
            if exists:
                skipped += 1
                continue
            try:
                out = generate_seo_article(
                    title=t["title"], angle=t["angle"], keywords=[],
                    context=t["context"],
                )
            except TypeError:
                # por si esta versión de generate_seo_article no acepta context
                out = generate_seo_article(
                    title=t["title"], angle=t["angle"] + "\n\nDatos: " + t["context"],
                    keywords=[],
                )
            except Exception as exc:  # noqa: BLE001
                log(f"  fallo generando '{t['title']}': {exc}", "warn")
                failed += 1
                continue
            prop = ContentProposal(
                kind="evergreen",
                source_type=None,
                source_id=None,
                title=(out.get("title") or t["title"])[:240],
                angle=t["angle"],
                body_md=out.get("body_md"),
                excerpt=out.get("excerpt"),
                meta_title=out.get("meta_title"),
                meta_description=out.get("meta_description"),
                entities=out.get("entities") or [],
                keywords=[],
                status="pending_review",
            )
            db.add(prop)
            created += 1
            log(f"  ✓ propuesta de gira: {t['title']}", "ok")
        db.commit()
    log(f"Giras: {created} propuestas creadas · {skipped} ya existían · {failed} fallos", "ok")


if __name__ == "__main__":
    main()
