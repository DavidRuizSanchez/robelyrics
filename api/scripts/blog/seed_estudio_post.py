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
    "El setlist de un concierto que no existió: once canciones que Extremoduro "
    "publicó y de las que no consta que llegaran a sonar nunca. Las contamos una "
    "a una, con sus letras."
)

BODY_MD = """\
Si alguna vez te has acercado al escenario cuando ya se encendían las luces, sabes
lo que es un setlist: un folio pegado al suelo con cinta, los títulos en mayúsculas
y la letra de alguien que escribía con prisa. Siempre hay alguien que se lo lleva
de recuerdo.

Esto es el setlist de un concierto que no existió. **Once canciones que Extremoduro
publicó en disco y de las que no consta que llegaran a sonar nunca delante de
nadie.**

**Roberto Iniesta murió el 10 de diciembre de 2025**, a los 63 años. Esto no va de
lo que dejó sin hacer, que sería una forma barata de contarlo. Va de once canciones
que están ahí, publicadas, y que se quedaron esperando su turno.

Antes de seguir, una precisión que importa: **no es lo mismo decir que no sonaron
nunca que decir que no hay registro de que sonaran.** Un archivo de conciertos lo
rellenamos personas, y lo que nadie apuntó no existe en él. Lo que sí podemos
decir es que en **591 conciertos documentados** no aparece ninguna de las once, y
que dos búsquedas independientes llegaron casi a la misma lista.

## Las once, una a una

### Volando solo — «nunca estoy solo con nadie»
*Deltoya, 1992*

> ¿Dónde me escondo?, si no va a salir el sol
> Quizá mañana tal vez me sienta mejor
> Nunca estoy solo con nadie
> Y ahora me cuelgo del aire

Ese tercer verso es de los que te paran en seco. Y la canción acaba convertida en
un cántico que repite que el planeta está contaminado, en 1992, cuando eso no
tocaba todavía.

### Estoy muy bien — la que dice que está bien y se va deshaciendo
*¿Dónde están mis amigos?, 1993*

Empieza firme:

> Estoy muy bien
> Cada vez que pasas a mi lado
> Sin mirar puedo oler
> Tu calor y tu amor resudado

Y termina tartamudeando: «Estoy aquí, estoy, estoy, es». El título insiste en que
todo va bien mientras la propia canción se le va de las manos. Está entera en ese
contraste.

### Islero, shirlero o ladrón — tres maneras de salir adelante
*¿Dónde están mis amigos?, 1993*

El islero es el toro que cogió a Manolete. El shirlero es quien te vacía los
bolsillos. Y el ladrón es el ladrón. Tres oficios para lo mismo, y una letra que
lo resume así:

> Para ceder si te has equivocado
> Hay que comerse los cojones a bocados

Al final lo dice sin anestesia: «he aprendido a ser shirlero / ayudando a los demás
a quedarse sin dinero».

### Sin dios ni amo — la que se marcha sin despedirse
*¿Dónde están mis amigos?, 1993*

> Voy a dejar esta ciudad
> No me pienso despedir
> De la gente, hace ya tiempo estoy ausente

De las once, esta es la que más suena a Extremoduro: libertad, rabia y ganas de
largarse. Y es también la única con una prueba a favor de que sí sonó, que
contamos más abajo.

### Adiós abanico, que llegó el aire — dos versos que valen un disco
*Rock Transgresivo, 1994*

> Voy caminando, y pienso en no pisar ni una amapola;
> Ella, entretanto, duerme casi, casi siempre sola

Con eso se cierra la canción, repitiéndolo. No hace falta nada más.

### Caballero andante — la que lleva cuatro voces prestadas
*Rock Transgresivo, 1994*

«Caballero andante» arranca con un cartel absurdo y un hombre defendiéndose de
algo que nadie le ha dicho:

> ¿Acaso no has visto el cartel?
> "Prohibida la entrada de ranas"

Y dentro de sus cuatro minutos caben, según documentó Jot Down, **cuatro voces que
no son la suya**: un fragmento de Marcos Ana de *Las soledades del muro*, una
estrofa de Antonio Machado casi literal, Cervantes en el título y en el molino, y
una cuarta alusión a Manolillo Chinato. Cuatro poetas en una canción, y ninguno
llegó a un escenario por esta puerta.

### Érase una vez — un cuento que te deja a ti el final
*Canciones prohibidas, 1998*

Así empieza «Érase una vez»:

> Érase una vez dentro de un mundo gris
> Luchando por salir una mijita de color

Vuelve siete veces a la misma pregunta —«¿Mi alma en un cajón tan negro?»— y se
despide con una orden preciosa: **«Sigue tú inventando el cuento.»** Para una
canción que nadie ha oído en directo, cuesta encontrar una última frase mejor.

### Buitre no come alpiste — el humor negro de la casa
*Yo, minoría absoluta, 2002*

El título ya te avisa de por dónde va. Y luego remata:

> Que estás más loca que yo
> Que necesito ver amanecer cuando no toca

De las once es la que más se ríe, y la risa va por dentro.

### Cerca del suelo — «y esta sí que salió bien»
*Yo, minoría absoluta, 2002*

El estribillo se lo sabe cualquiera que haya puesto el disco:

> Quedamos cerca del suelo
> A la altura de tu cintura

Y la canción se despide diciendo **«Y esta sí que salió bien…»**. Razón no le
falta: es un temazo. Y aun así no nos consta que llegara a sonar en un escenario.

Hay quien jura haberla escuchado en directo. Si eres de esos, escríbenos — nos
encantaría quitarla de esta lista.

### Luce la oscuridad — la pregunta que lleva ahí desde 2002
*Yo, minoría absoluta, 2002*

El estribillo es de los que se te quedan pegados: «Luce la oscuridad; luz de las
velas». Y en medio, sin avisar, esto:

> ¿Quién va a meterse por el culo mi libertad de expresión cuando diga que me cago en la constitución?

Más de veinte años después suena igual de clara. Nunca se cantó en un escenario, y
no sabemos por qué.

### Manué IV — la que es una conversación entre colegas
*Para todos los públicos, 2013*

No es una canción, es una escena:

> - Manué
> - ¿Qué pasa?
> - Qué pena que nadie nos fusile al alba.
> - Puto revolucionario de los cojones...

Esto es Robe de arriba abajo: colar en un disco una conversación que podría haber
pasado en cualquier bar, con su gracia y su mala leche, y dejarla ahí sin explicar
nada. Está en el último disco que publicó Extremoduro. En el disco sigue intacta, y
sigue haciendo gracia.

## Por qué nos fiamos de una ausencia

Una lista de lo que falta solo vale si el archivo sabe registrar lo raro. Y sabe.

Hubo tres canciones que sonaron **una única vez** en toda la historia del grupo.
«¡Qué sonrisa tan rara!» y «Tomás», en una prueba en la sala Neptuno de Granada
antes de publicar *Agila*. «Te juzgarán sólo por tus errores», en la presentación
de *Pedrá* en Madrid, en 1995. Las fechas y los sitios los cuenta
[Juancares](https://www.youtube.com/watch?v=fbAKGSeQGy4), que lleva años
reconstruyendo esta historia; el recuento sale de
[setlist.fm](https://www.setlist.fm/stats/extremoduro-13d68da1.html), que registra
**exactamente un toque de cada una**. Dos sitios que no se hablan, coincidiendo en
tres noches de hace treinta años.

Y hay más. Ese mismo trabajo de Juancares, hecho por su cuenta y sin saber nada de
esto, dedicó dos programas a preguntarse qué canciones no había llevado nunca
Extremoduro al escenario. Nombró **diez de estas once**. La única que no sale en
sus listas es «Manué IV».

## La única prueba en contra, y la contamos igual

De «Sin dios ni amo» hay un indicio de que sí sonó: un setlist publicado en la
revista *Heavy Rock* en el que figuraba. Pero en las cintas grabadas en conciertos
de aquella época no aparece. Es la única de las once con algo a favor, y es de
papel.

## Si tienes una prueba, queremos verla

Cualquiera de estas once se cae de la lista con un solo documento: una grabación,
una entrada, la foto de un setlist pegado al suelo, el recuerdo fechado de alguien
que estuvo allí. Y sería la mejor noticia que puede dar este trabajo, porque
querría decir que hay una canción menos que se quedó sin sonar.

Si tienes algo, escríbenos. Lo corregimos y decimos de dónde salió la corrección.

---

«Caballero andante» acaba con un fragmento recitado. Lo dejamos aquí, sin añadir
nada:

> Pasado mañana, brotes de esperanza, y yo no he muerto, si tengo frío me caliento, si tengo miedo, que no lo tengo, susurro y pienso, y para mañana ya he comido mi pequeña ración de esperanza

## Método y fuentes

El catálogo de este sitio tiene 153 fichas de canción, pero no son 153
composiciones: 21 son regrabaciones o versiones en directo de un tema que ya
estaba. Las distintas son **132**. Contra eso se puso el repertorio en directo:
**459 conciertos documentados de Extremoduro** entre 1987 y 2014 y **132 de Robe**
entre 2017 y 2024. De los 137 títulos que aparecen en esos setlists, 121 casan con
una composición del catálogo; el resto son versiones de otros, medleys y temas
inéditos. La resta deja estas once, todas publicadas en disco de estudio o EP.

- **Catálogo, letras y versos**: base de datos propia de Entre Interiores.
- **Repertorio en directo**: páginas públicas de estadísticas de
  [setlist.fm](https://www.setlist.fm/stats/robe-63c74607.html), consultadas el 6 de
  octubre de 2026. Es un archivo colaborativo: 459 setlists no son todos los
  conciertos de Extremoduro, son los que alguien subió.
- **Verificación de tracklists**: [MusicBrainz](https://musicbrainz.org/).
- **Contraste de las ausencias**: el consultorio de Juancares,
  [capítulo 1x04](https://www.youtube.com/watch?v=fbAKGSeQGy4) y
  [capítulo 1x05](https://www.youtube.com/watch?v=ReX6OLBnT90).

Este artículo forma parte de un estudio más amplio sobre el repertorio en directo
de Extremoduro y Robe —591 conciertos entre 1987 y 2024— que publicaremos completo
en diciembre, al cumplirse un año de su muerte.
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

        # Si el post YA estaba publicado, `auto_publish_post` avisa de que está
        # «en estado terminal» y los gates pierden los dientes: el 06-10-2026
        # `lyric_guard` marcó una cita mal atribuida, quiso retener la pieza y el
        # cuerpo nuevo se publicó igual. Volver a borrador antes de republicar es
        # lo que hace que las guardas sigan mandando en cada reedición.
        if row.status == "published":
            logger.info("estaba publicado: vuelve a borrador para que los gates actúen")
            row.status = "draft"
            db.commit()
            db.refresh(row)

        # `PublishResult` es un TypedDict, o sea un dict: con getattr() el motivo
        # salía siempre «?» y había que ir al log a buscarlo, que es justo el
        # fallo que PR #27 arregló en el panel.
        res = auto_publish_post(db, row, factcheck=False, rigor=False)
        # La clave es `action` ("published" | "scheduled"), no `published`: con
        # `res.get("published")` el script decía que no se había publicado un post
        # que SÍ estaba publicado, que es el mismo tipo de mentira que PR #27
        # arregló en la pantalla del panel.
        if res.get("action") not in ("published", "scheduled"):
            logger.error("NO publicado. Retenido por %s: %s",
                         res.get("blocked_by") or "?", res.get("reason") or "sin motivo")
            return 1
        logger.info("publicado: /blog/%s", SLUG)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
