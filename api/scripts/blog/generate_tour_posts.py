"""Genera posts de GIRAS de Extremoduro/Robe como Post en pending_review.

Crea un `Post` (kind='evergreen', status pending_review) por gira — NO publica.
El admin los revisa/edita y publica desde /biblioteca/admin/posts. Grounded con
datos verificables de los libros (ver data/reference/*.md): no inventar.

Idempotente: salta si ya existe un Post con el mismo slug.

Uso:
    python -m scripts.blog.generate_tour_posts
    python -m scripts.blog.generate_tour_posts --dry-run
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.content_generator import generate_seo_article
from app.services.publishing import propose_for_review
from scripts.blog.context_builder import tour_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Datos verificables por gira (de De Profundis + research). El generador
# parafrasea con la voz del sitio; estos hechos son su materia prima.
# `slug` es estable y legible — define la URL del post y la idempotencia.
TOURS = [
    {
        "slug": "gira-pedra-1995",
        "album_slug": "pedra",
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
        "slug": "gira-extremoduro-platero-1995",
        "album_slug": "iros-todos-a-tomar-por-culo",
        "title": "La gira de Extremoduro y Platero y Tú (1995)",
        "angle": "La gira conjunta con Platero y Tú, hermandad y cartel circense.",
        "context": "Verano-noviembre de 1995. Extremoduro y Platero y Tú (la banda de "
        "Uoho y Fito Cabrales) de gira conjunta, cartel circense. Cierre en el Palacio "
        "de los Deportes de Madrid los días 8 y 9 de noviembre de 1995, de donde salió "
        "el directo 'Iros todos a tomar por culo' (1997).",
    },
    {
        "slug": "gira-canciones-prohibidas-1999",
        "album_slug": "canciones-prohibidas",
        "title": "Moñigos, morid (1999): la gira de Canciones prohibidas",
        "angle": "La gira de Canciones prohibidas con Fito & Fitipaldis de teloneros.",
        "context": "Gira de 1999 tras Canciones prohibidas (1998). Fito & Fitipaldis "
        "debutaban como teloneros (con 'A puerta cerrada'). Formación con Uoho a la "
        "guitarra y Cantera a la batería ya oficiales.",
    },
    {
        "slug": "gira-yo-minoria-absoluta-2002",
        "album_slug": "yo-minoria-absoluta",
        "title": "Gira 2002: Yo, minoría absoluta sobre los escenarios",
        "angle": "La gira de Yo, minoría absoluta, con llenos históricos.",
        "context": "Gira 2002 de Yo, minoría absoluta (2002). Dos noches en La Cubierta "
        "de Leganés ante más de 20.000 personas; agotaron el Recinto Hípico de Cáceres. "
        "Quedó documentada en el DVD 'Gira 2002'. Formación Robe, Uoho, Cantera, Miguel "
        "Colino + Aiert Erkoreka (teclados) y Félix Landa (guitarra).",
    },
    {
        "slug": "gira-grandes-exitos-fracasos-2004",
        "title": "Grandes éxitos y fracasos (2004): la gira de la regrabación",
        "angle": "La gira de 2004 alrededor de los Grandes éxitos y fracasos.",
        "context": "Gira de 2004: arrancó en Lleida el 14 de mayo y terminó en Salamanca "
        "el 13 de noviembre, 40 ciudades. Coincidió con los recopilatorios 'Grandes "
        "éxitos y fracasos' (Episodios primero y segundo), donde regrabaron los primeros "
        "discos.",
    },
    {
        "slug": "gira-la-ley-innata-2008",
        "album_slug": "la-ley-innata",
        "title": "La ley innata en directo (2008): una sinfonía en cuatro movimientos",
        "angle": "La gira de La ley innata, el disco de un solo tema que Extremoduro llevó entero al escenario.",
        "context": "Gira de 'La ley innata' (del 17 de mayo al 15 de noviembre de 2008). "
        "'La ley innata' (2008) es un disco conceptual de un solo tema dividido en cuatro "
        "movimientos, con un enfoque sinfónico que al principio desconcertó al público en "
        "directo. Anécdota documentada de aquella gira: en un concierto de 2008 se detuvo "
        "la actuación porque había personas viéndola desde fuera del recinto sin pagar, y "
        "se reanudó tras resolver la situación.",
    },
    {
        "slug": "gira-robando-perchas-2012",
        "album_slug": "material-defectuoso",
        "title": "Robando perchas del hotel (2012): la última gran gira de Extremoduro",
        "angle": "La gira de 2012, el salto a América y el cierre en Cáceres.",
        "context": "Gira 'Robando perchas del hotel' (2012; nombre inspirado en un "
        "artículo de Juan José Millás). Cerca de 150.000 entradas. En 2012 Extremoduro "
        "cruzó por primera vez el charco (Argentina, Chile, Uruguay), 25 años después de "
        "fundarse. Cierre en el Recinto Hípico de Cáceres el 13 de octubre de 2012 ante "
        "15.000 personas, con despedida emotiva de Robe.",
    },
    {
        "slug": "gira-para-todos-los-publicos-2014",
        "album_slug": "para-todos-los-publicos",
        "title": "Para todos los públicos (2014): el último adiós de Extremoduro",
        "angle": "La gira de despedida de Extremoduro antes de su disolución.",
        "context": "Gira de 'Para todos los públicos' (2013), organizada por El "
        "Dromedario Records, por España y Latinoamérica. Fue la última etapa de "
        "Extremoduro; el grupo anunció su disolución el 18 de diciembre de 2019.",
    },
    {
        "slug": "giras-robe-solitario",
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-slug", help="Genera solo la gira con este slug.")
    parser.add_argument(
        "--force", action="store_true",
        help="Regenera (actualiza en sitio) los posts que ya existan.",
    )
    args = parser.parse_args()

    tours = TOURS
    if args.only_slug:
        tours = [t for t in TOURS if t["slug"] == args.only_slug]
        if not tours:
            logger.error("No hay gira con slug '%s'", args.only_slug)
            return

    created = skipped = failed = 0
    with SessionLocal() as db:
        for t in tours:
            existing = db.execute(
                select(Post).where(Post.slug == t["slug"])
            ).scalar_one_or_none()
            if existing is not None and not args.force:
                logger.info("Post %s ya existe (status=%s), skip", t["slug"], existing.status)
                skipped += 1
                continue
            try:
                # Grounding RAG: entrevistas/citas reales de Robe + consenso fan
                # del disco + hechos de los libros (no el resumen a mano).
                ctx = tour_context(db, t)
                out = generate_seo_article(
                    title=t["title"], angle=t["angle"], keywords=[],
                    context=ctx or t["context"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("fallo generando '%s': %s", t["title"], exc)
                failed += 1
                continue

            title = (out.get("title") or t["title"])[:240]
            body_md = out.get("body_md") or ""
            if not body_md.strip():
                logger.warning("'%s' sin body, skip", t["title"])
                failed += 1
                continue

            if args.dry_run:
                print(f"\n=== DRY RUN — gira {t['slug']} ===")
                print("slug:", t["slug"])
                print("title:", title)
                print("excerpt:", out.get("excerpt"))
                print("---BODY---")
                print(body_md)
                continue

            # --force sobre un post existente: se actualiza en sitio (conserva
            # su estado y su URL), no se duplica.
            if existing is not None:
                existing.title = title
                existing.excerpt = out.get("excerpt")
                existing.body_md = body_md
                existing.meta_title = out.get("meta_title")
                existing.meta_description = out.get("meta_description")
                existing.entities = out.get("entities") or []
                db.commit()
                logger.info(
                    "✓ gira regenerada (status=%s): %s", existing.status, t["slug"]
                )
                created += 1
                continue

            post = Post(
                slug=t["slug"],
                kind="evergreen",
                status="draft",
                title=title,
                excerpt=out.get("excerpt"),
                body_md=body_md,
                meta_title=out.get("meta_title"),
                meta_description=out.get("meta_description"),
                entities=out.get("entities") or [],
            )
            db.add(post)
            db.commit()
            db.refresh(post)
            # notify=False: generamos varios de golpe; el admin los revisa en
            # /biblioteca/admin/posts sin recibir 8 emails.
            propose_for_review(db, post, notify=False)
            logger.info("✓ post de gira en pending_review: %s", t["slug"])
            created += 1

    logger.info(
        "Giras: %d posts creados · %d ya existían · %d fallos",
        created, skipped, failed,
    )


if __name__ == "__main__":
    main()
