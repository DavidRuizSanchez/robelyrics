"""Crea (o actualiza) la entrada inaugural del blog: el primer cumpleaños
de Robe sin él, marcado por el festival 'Primeras Flores Amarillas' de
Plasencia (16 de mayo de 2026), pistoletazo de salida de un homenaje
recurrente anual a su legado.

Idempotente: si la entrada ya existe (por slug), la actualiza.

Uso:
    docker compose exec api python -m scripts.blog.seed_inaugural_post
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal

SLUG = "primeras-flores-amarillas-plasencia-cumple-robe-2026"

TITLE = (
    "Primeras Flores Amarillas: crónica del primer cumpleaños de Robe en "
    "Plasencia"
)

EXCERPT = (
    "El 16 de mayo de 2026 Plasencia inaugura un festival que vuelve cada "
    "año: Primeras Flores Amarillas. Crónica del primer cumple sin él, con "
    "miles de personas, murales desbordados y mucho amarillo."
)

BODY_MD = """\
El **16 de mayo de 2026** habría sido un cumpleaños como cualquier otro de
**Roberto Iniesta**. Plasencia, su ciudad, decidió hace meses que esta
fecha no podía pasar en silencio nunca más. De esa decisión sale
**[Primeras Flores Amarillas](https://culturaplasencia.es/event/festival-primeras-flores-amarillas/)**,
un festival que nace con vocación de quedarse: un homenaje que se
celebrará **cada año, en cada cumpleaños**, mientras Plasencia exista.

Es el primer 16 de mayo sin Robe. Y se siente. No hay dramatismo en
decirlo: hay melancolía y hay agradecimiento, que es como se quiere él
en estas tierras. Lo que pasó este sábado merece contarse despacio.

## Empezó plantando flores

A las **diez de la mañana**, en la **plaza Puerto de Béjar**, la gente
empezó a llegar con plantas y flores amarillas debajo del brazo. La
organización había habilitado personal para enterrarlas allí mismo: una
plantación colectiva, manual, en el centro de la ciudad. Jóvenes,
mayores, familias enteras pasaron a dejar la suya. No había escenario,
no había foto oficial: solo gente arrodillada en la tierra con una
flor amarilla en la mano, en el día que era. Cuesta encontrar
arranques más bonitos para un homenaje.

## Los murales que se desbordaron

A continuación tocaba la **visita guiada a los murales de Jesús
Mateos Brea**, muralista placentino que está pintando piezas
dedicadas a Robe y a **Manolillo Chinato**. Brea contaba que esperaba
unas veinte personas. Aparecieron **más de trescientas**. Tuvo que
pedir un micrófono prestado porque su voz no llegaba al fondo de la
plaza. Quien quiera tomarse este dato como termómetro lo tiene fácil:
*veinte que esperabas, trescientos que vinieron*.

## Pulseras agotadas a la una

Las **5.000 pulseras** para acceder al recinto de Torre Lucía se
empezaron a repartir a las once en la plaza Mayor. **A las trece menos
poco ya no quedaba ninguna.** Y aforo, encima, solo para 2.000
personas, así que iba a haber más gente fuera que dentro. La que se
quedó sin pulsera lo dijo claro, recogido por la prensa local: *"lo
importante es vivir la experiencia y estar aquí este día"*. Eso era,
exactamente, lo que iba.

## Camisetas amarillas viniendo de todos lados

En la plaza se concentró gente llegada desde **Valencia, Alicante,
Asturias, Madrid, Salamanca, Granada**… Un valenciano dejó la frase
que probablemente resume mejor lo que estaba pasando: *"estuvimos en el
homenaje a Robe cuando falleció y no hemos querido faltar tampoco a
este"*. Camisetas amarillas, camisetas de Robe, camisetas del propio
festival, flores enganchadas al cuello y al pelo, paraguas amarillos.
El centro de Plasencia entero pintado del color que da nombre al día.

## Conciertos improvisados por toda la ciudad

Mientras tanto, por las calles del centro fueron apareciendo
**escenarios improvisados**: la plaza de la **catedral Vieja** —un
grupo del País Vasco tocando con la fachada de la catedral de fondo—,
la plaza de **San Martín**, la **plaza Quemada** en la calle del Sol,
la **Puerta del Sol**. Música acústica saliendo de cuatro o cinco
sitios al mismo tiempo, sin un cartel rígido que mandara, dejando que
la participación ciudadana llevara el ritmo. Es muy de Robe, esto.

## A las 19:50, todo el mundo a la vez

A las **19:50**, antes de que arrancaran los conciertos oficiales, la
organización propuso algo precioso: **abrir el canal de YouTube de
Robe en el dispositivo que tuvieras a mano y poner *El poder del
arte*** a la vez que todos los demás. Quien estuviera en Plasencia,
quien estuviera en Madrid, quien estuviera trabajando en una cocina
en Berlín. Sonar todos al mismo tiempo. Sin escenario.

Eso, lo de elegir *El poder del arte* para que sonara colectivamente
en su cumpleaños, es de las decisiones más exactas que se podrían
tomar. Una canción que dice lo que dice, sonando en miles de
auriculares y cocinas, a la misma hora, por él.

## Y a las 20:00, Torre Lucía

A las 18:30 abrieron las puertas. A las 20:00 arrancaron los
conciertos. **Chula** abrió, banda madrileña; les siguieron
**Aljamia**, **Carameloraro**, **Oxygen** e **Illo Brown!**. Bandas
emergentes, no tributos: voces nuevas alejadas de las versiones. El
planteamiento del festival está claro y es bonito: celebrar el legado
de Robe **abriendo paso a quien viene detrás**, no congelando el
recuerdo en un loop de greatest hits. Los conciertos se alargaron
hasta las dos de la madrugada.

## Lo que queda

Habrá un segundo año de **Primeras Flores Amarillas**. Y un tercero.
Y si hay suerte, muchos más. Plasencia se acaba de inventar un
**rito anual** que sostiene la memoria de Robe sin convertirla en
museo: con flores que se plantan, con gente que viene desde lejos
solo por estar, con conciertos de bandas nuevas que cogen el testigo.

Las flores amarillas que cubren Plasencia cada mayo no son una
metáfora inventada para la ocasión. Son **literalmente** lo que pasa
en la ciudad por estas fechas: la primavera estalla amarilla en muros,
balcones y callejuelas. Que el primer homenaje recurrente a Robe lleve
ese nombre dice algo importante. **Las flores estaban ya, y él también
estaba ya, y eso se reconoce.**

Esta entrada inaugura el **diario de Entre Interiores**, y no se nos
ocurría mejor manera de abrirlo que contándolo.

Felicidades, Robe.

— *Entre Interiores · 16 de mayo de 2026*

> *Datos y citas verificados con la
> [crónica de El Periódico Extremadura](https://www.elperiodicoextremadura.com/plasencia/2026/05/16/arranca-festival-primeras-flores-amarillas-130292975.html)
> y la
> [ficha oficial del festival en Cultura Plasencia](https://culturaplasencia.es/event/festival-primeras-flores-amarillas/).*
"""

META_TITLE = (
    "Primeras Flores Amarillas Plasencia 2026: el primer cumple de Robe "
    "sin él · Entre Interiores"
)
META_DESCRIPTION = (
    "Crónica del festival Primeras Flores Amarillas de Plasencia, homenaje "
    "anual a Roberto Iniesta que arranca el 16 de mayo de 2026, primer "
    "cumpleaños de Robe sin él. Cómo es, dónde y por qué importa."
)


def main() -> None:
    with SessionLocal() as db:
        # Borrar la entrada inaugural anterior si existía (slug antiguo) para
        # que el feed quede limpio. Idempotente.
        old = db.execute(
            select(Post).where(
                Post.slug == "lo-que-habria-sido-su-cumpleanos-flores-amarillas-plasencia"
            )
        ).scalar_one_or_none()
        if old:
            db.delete(old)

        row = db.execute(select(Post).where(Post.slug == SLUG)).scalar_one_or_none()
        published_at = datetime(2026, 5, 16, 9, 0, 0, tzinfo=timezone.utc)

        if row:
            row.title = TITLE
            row.excerpt = EXCERPT
            row.body_md = BODY_MD
            row.meta_title = META_TITLE
            row.meta_description = META_DESCRIPTION
            row.status = "published"
            row.published_at = published_at
            action = "actualizada"
        else:
            row = Post(
                slug=SLUG,
                kind="editorial",
                status="published",
                title=TITLE,
                excerpt=EXCERPT,
                body_md=BODY_MD,
                meta_title=META_TITLE,
                meta_description=META_DESCRIPTION,
                published_at=published_at,
            )
            db.add(row)
            action = "creada"

        db.commit()
        print(f"Entrada inaugural {action}: /blog/{SLUG}")


if __name__ == "__main__":
    main()
