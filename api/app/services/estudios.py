"""Registro de los estudios de datos, lado backend.

**Esto es una COPIA deliberada.** El registro con todo (metadatos, resumen,
qué mide, el componente que lo pinta) vive en `web/lib/estudios.ts`, porque un
estudio es una página del frontend. Pero dos cosas del backend necesitan saber
que existe:

- `url_resolver.resolve_path`, o `guard_internal_links` da el enlace al estudio
  por inventado y lo DESENLAZA en silencio (medido el 07-10-2026);
- la newsletter, para que un estudio nuevo salga en el digest del domingo. El
  digest solo llevaba posts, así que el estudio solo viajaba como un enlace
  dentro del cuerpo de un post, que el correo no manda.

No se puede leer el fichero TS en caliente: la imagen del api se construye con
contexto `./api` y la del web con `./web`, así que ninguna de las dos ve la otra
ni `data/` del raíz. Lo que impide que divergan es el paso «estudios
sincronizados» de `.github/workflows/tests.yml`, que corre en el runner con el
repo entero delante y compara slug, título y fecha.

Al añadir un estudio: aquí y en `web/lib/estudios.ts`. Y **solo cuando la página
esté desplegada**: la newsletter lo anuncia por fecha, y anunciar un 404 es peor
que anunciarlo tarde.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class Estudio:
    slug: str
    titulo: str
    resumen: str
    publicado: date

    @property
    def ruta(self) -> str:
        return f"/estudios/{self.slug}"

    @property
    def publicado_utc(self) -> datetime:
        """La fecha a medianoche UTC, para comparar contra `last_sent_at`.

        Con la fecha a 00:00 un estudio entra en el primer envío posterior a su
        día y no vuelve a entrar en el siguiente, que es lo que se quiere. Si se
        publicara un domingo después del envío de las 12:00, saldría en ese mismo
        correo: de ahí la regla de dar de alta la entrada solo con la página ya
        desplegada.
        """
        return datetime.combine(self.publicado, datetime.min.time(), tzinfo=timezone.utc)


ESTUDIOS: tuple[Estudio, ...] = (
    Estudio(
        slug="repertorio-en-directo-extremoduro-robe",
        titulo="Las 11 canciones de Extremoduro que nunca has escuchado en directo",
        resumen=(
            "591 conciertos documentados entre 1987 y 2024, 5.581 interpretaciones "
            "contadas y 132 composiciones del catálogo. Del cruce salen once canciones "
            "sin un solo registro en directo, un mapa con las cincuenta provincias y el "
            "reparto real del repertorio entre Extremoduro y Robe."
        ),
        publicado=date(2026, 10, 7),
    ),
)

ESTUDIO_SLUGS: frozenset[str] = frozenset(e.slug for e in ESTUDIOS)


def pendientes_desde(desde: datetime | None) -> list[Estudio]:
    """Estudios publicados después de `desde`, los más nuevos primero.

    `desde` a None (suscriptor recién confirmado) devuelve todos: alguien que
    acaba de llegar no se ha perdido nada todavía, y el estudio es lo mejor que
    tenemos para enseñarle.
    """
    if desde is None:
        elegidos = list(ESTUDIOS)
    else:
        elegidos = [e for e in ESTUDIOS if e.publicado_utc > desde]
    return sorted(elegidos, key=lambda e: e.publicado, reverse=True)
