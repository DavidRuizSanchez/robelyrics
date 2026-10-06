"""Crea el post del estudio del repertorio: las once canciones sin registro en directo.

Idempotente por slug. Se crea en BORRADOR a propósito: el texto está escrito a
mano, pero cita un verso, y `lyric_guard` es la guarda que comprueba que los
versos citados existen de verdad y pertenecen a la canción que se dice. Pasar por
ella no es opcional ni aunque el autor sea humano.

    docker compose exec api python -m scripts.blog.seed_estudio_post            # borrador
    docker compose exec api python -m scripts.blog.seed_estudio_post --publish   # pasa las guardas

Con `--publish` va por `auto_publish_post(factcheck=False, rigor=False)`: el admin
ya ha leído la pieza, así que se le ahorra el juez de rigor y el fact-check, pero
siguen corriendo `guard_internal_links`, **`lyric_guard`**, `sensitive_topics` y
`hero_guard`, que son las que no se evaden.

Sobre los enlaces internos: la tabla de las once va SIN enlazar a propósito. El
autolinker tiene un tope de 4 enlaces por página (la regla del Moat) y el cron del
domingo desnuda y re-enlaza, así que once enlaces escritos a mano se quedarían en
cuatro elegidos por la máquina. Mejor que elija ella los cuatro y la tabla se lea
entera.
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SLUG = "canciones-extremoduro-sin-registro-en-directo"

TITLE = "Once canciones de Extremoduro sin un solo registro en directo"

META_TITLE = "Once canciones de Extremoduro sin un solo registro en directo"

META_DESCRIPTION = (
    "De las 132 composiciones del catálogo, once no aparecen en ningún setlist "
    "documentado. Descubre cuáles son y cómo lo hemos comprobado, una a una."
)

EXCERPT = (
    "Cruzamos las 132 composiciones publicadas con los 591 conciertos "
    "documentados de Extremoduro y Robe. Once canciones no aparecen en ninguno. "
    "Una de ellas repite doce veces un verso que nadie ha podido documentar "
    "cantado."
)

BODY_MD = """\
Hay canciones que se publican, se escuchan en casa durante treinta años y no
llegan nunca a un escenario. En la obra de Extremoduro son **once**, y de ninguna
de ellas existe un solo registro de que haya sonado en directo.

Conviene decir con precisión lo que eso significa, porque no es lo mismo que
afirmar que no sonaron nunca. Un archivo de conciertos lo rellenan personas, y lo
que nadie apuntó no existe en él. Lo que se puede afirmar es más modesto y más
comprobable: **en 591 conciertos documentados no aparece ninguna de las once**, y
dos búsquedas independientes llegaron casi a la misma lista.

## Cómo se ha medido

El catálogo de este sitio tiene 153 fichas de canción, pero no son 153
composiciones: 21 son regrabaciones o versiones en directo de un tema que ya
estaba. Las composiciones distintas son **132**.

Contra eso se puso el repertorio en directo: **459 conciertos documentados de
Extremoduro** entre 1987 y 2014, y **132 de Robe** entre 2017 y 2024, con un total
de 5.581 interpretaciones contadas. De los 137 títulos que aparecen en esos
setlists, 121 casan con una composición del catálogo. Los dieciséis restantes son
versiones de otros, medleys y temas inéditos.

La resta deja once canciones, todas publicadas en disco de estudio o EP. Un corte
que solo existe en un disco en directo no puede figurar aquí, por razones
evidentes.

## Las once

| Canción | Disco | Año |
|---|---|---|
| Volando Solo | Deltoya | 1992 |
| Estoy Muy Bien | ¿Dónde están mis amigos? | 1993 |
| Islero, shirlero o ladrón | ¿Dónde están mis amigos? | 1993 |
| Sin Dios Ni Amo | ¿Dónde están mis amigos? | 1993 |
| Adiós Abanico, Que Llegó el Aire | Rock Transgresivo | 1994 |
| Caballero andante | Rock Transgresivo | 1994 |
| Érase una Vez | Canciones prohibidas | 1998 |
| Buitre No Come Alpiste | Yo, minoría absoluta | 2002 |
| Cerca del Suelo | Yo, minoría absoluta | 2002 |
| Luce la Oscuridad | Yo, minoría absoluta | 2002 |
| Manué IV | Para todos los públicos | 2013 |

Cada una está verificada como corte real de su disco contra
[MusicBrainz](https://musicbrainz.org/), con su posición en el tracklist. No hay
ninguna canción fantasma en la lista.

## Por qué nos fiamos de una ausencia

Una lista de lo que falta solo vale si el archivo es capaz de registrar lo raro.
Lo es, y se puede demostrar.

Tres canciones de Extremoduro sonaron **una única vez** en toda su historia.
«¡Qué sonrisa tan rara!» y «Tomás», en una prueba en la sala Neptuno de Granada
antes de publicar *Agila*. «Te juzgarán sólo por tus errores», en la presentación
de *Pedrá* en Madrid, en 1995. Las fechas y los sitios los cuenta
[Juancares](https://www.youtube.com/watch?v=fbAKGSeQGy4) en su historia de la
banda; el recuento sale de
[setlist.fm](https://www.setlist.fm/stats/extremoduro-13d68da1.html), que registra
**exactamente un toque de cada una**. Dos fuentes que no se hablan, coincidiendo
en actuaciones únicas de hace treinta años.

Y hay algo más. Ese mismo trabajo de Juancares, hecho por su cuenta y sin conocer
este estudio, dedicó dos programas a preguntarse qué canciones no había llevado
Extremoduro nunca al escenario. Nombró **diez de estas once**. La única que no
aparece en sus listas es «Manué IV».

## La única prueba en contra, y se publica

De «Sin Dios Ni Amo» hay una prueba a favor de que sí sonó: un setlist publicado
en la revista *Heavy Rock* en el que figuraba. Pero en las cintas grabadas en
conciertos de aquella época no aparece. Es la única de las once con evidencia en
contra, y es de papel.

## El estribillo que nadie llegó a cantar

Entre las once hay una que duele más que las otras. En «Luce la Oscuridad», de
*Yo, minoría absoluta*, el verso **«Luce la oscuridad;»** se repite **doce veces**,
repartidas de principio a fin de la canción. No es una letanía de entrada ni un
estribillo que aparece y desaparece: vuelve una y otra vez, de las primeras líneas
a las últimas.

Medido sobre las 132 composiciones, solo 70 tienen un estribillo identificable con
ese criterio. El de «Luce la Oscuridad» es uno de los más insistentes del catálogo
entero. Y no consta que se cantara nunca delante de nadie.

## Si tienes una prueba, queremos verla

Cualquiera de estas once se cae de la lista con un solo documento: una grabación,
una entrada, la foto de un setlist pegado al suelo del escenario, el recuerdo
fechado de alguien que estuvo. Y esa sería la mejor noticia que puede dar este
trabajo, porque significaría que hay una canción menos que se quedó sin sonar.

Si tienes algo, escríbenos. La lista se corregirá y se dirá de dónde salió la
corrección.

## Fuentes y método

- **Catálogo, letras y versos**: base de datos propia de Entre Interiores, 132
  composiciones con su letra completa.
- **Repertorio en directo**: páginas públicas de estadísticas de
  [setlist.fm](https://www.setlist.fm/stats/robe-63c74607.html), consultadas el 6
  de octubre de 2026. Es un archivo colaborativo: 459 setlists no son todos los
  conciertos de Extremoduro, son los que alguien subió.
- **Verificación de tracklists**: [MusicBrainz](https://musicbrainz.org/).
- **Contraste de las ausencias**: el consultorio de Juancares,
  [capítulo 1x04](https://www.youtube.com/watch?v=fbAKGSeQGy4) y
  [capítulo 1x05](https://www.youtube.com/watch?v=ReX6OLBnT90). Es trabajo de un
  tercero y se cita como tal.

Este artículo forma parte de un estudio más amplio sobre el repertorio en directo
de Extremoduro y Robe que se publicará completo en diciembre.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--publish", action="store_true",
                    help="publica pasando por las guardas no evadibles")
    args = ap.parse_args()

    with SessionLocal() as db:
        row = db.execute(select(Post).where(Post.slug == SLUG)).scalar_one_or_none()
        if row is None:
            row = Post(
                slug=SLUG, kind="editorial", status="draft", title=TITLE,
                excerpt=EXCERPT, body_md=BODY_MD,
                meta_title=META_TITLE, meta_description=META_DESCRIPTION,
                target_keyword="canciones de Extremoduro nunca tocadas en directo",
            )
            db.add(row)
            logger.info("creado en borrador: %s", SLUG)
        else:
            row.title = TITLE
            row.excerpt = EXCERPT
            row.body_md = BODY_MD
            row.meta_title = META_TITLE
            row.meta_description = META_DESCRIPTION
            # Tocar el cuerpo invalida el motivo de bloqueo anterior: describiría
            # el texto de ayer.
            row.review_blocked_at = None
            row.review_blocked_reason = None
            logger.info("actualizado: %s (estado %s)", SLUG, row.status)
        db.commit()
        db.refresh(row)

        if not args.publish:
            logger.info("en borrador. Revísalo en /biblioteca/admin/posts y publícalo "
                        "desde ahí, o vuelve a lanzar esto con --publish.")
            return 0

        from app.services.publishing import auto_publish_post

        res = auto_publish_post(db, row, factcheck=False, rigor=False)
        ok = getattr(res, "published", None)
        if ok is False or (ok is None and row.status != "published"):
            logger.error("NO publicado. Retenido por: %s — %s",
                         getattr(res, "blocked_by", "?"), getattr(res, "reason", "?"))
            return 1
        logger.info("publicado: /blog/%s", SLUG)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
