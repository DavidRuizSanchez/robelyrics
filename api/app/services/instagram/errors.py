"""Qué dice Meta cuando algo falla, y de quién es la culpa.

Un error de la Graph API puede ser de DOS tipos, y confundirlos sale caro:

  - GLOBAL: la cuenta está restringida, el token caducó, se agotó la cuota. Le
    pasaría igual a cualquier post de la cola. Gastarle un intento a ESTE post
    por algo que no es suyo condena a la cola entera.
  - DEL ITEM: su caption pasa de 2200 caracteres, su imagen no cumple el aspect
    ratio, su media no se puede descargar. Ese sí se queda sin intentos, porque
    si no se reintentaría cada 15 minutos para siempre.

En agosto de 2026 no se distinguían. Meta restringió la cuenta
(`code 25 / subcode 2207050`) y `_create_media` serializaba el error a texto
plano, así que `publisher` no tenía con qué decidir y quemaba intento siempre:
47 posts murieron por un bloqueo que no era suyo y que se levantó solo.

Códigos: https://developers.facebook.com/docs/instagram-api/reference/error-codes/
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# --------------------------------------------------------------------------- #
# Los dos cubos
# --------------------------------------------------------------------------- #
# El SUBCÓDIGO manda sobre el código: es lo específico. Un `100` a secas suele
# ser un parámetro malo (del item), pero `100/33` es el enlace IG↔Página roto,
# que es global y ya tuvo el sistema caído en silencio una vez.
SUBCODIGOS_GLOBALES = {
    2207050,  # la cuenta de Instagram está restringida  ← el incidente de agosto
    2207051,  # actividad restringida para proteger a la comunidad (antispam)
    2207042,  # límite de 25 publicaciones en 24 h
    2207001,  # error de servidor de Meta
    2207053,  # error desconocido de subida (lado de Meta)
    33,       # el IG ya no es alcanzable desde esta Página
}

SUBCODIGOS_DEL_ITEM = {
    2207003,  # timeout descargando SU media
    2207004,  # imagen de más de 8 MiB
    2207005,  # formato de imagen no soportado
    2207006,  # media no encontrado
    2207008,  # su container caducó
    2207009,  # aspect ratio fuera de 4:5 – 1.91:1
    2207010,  # caption de más de 2200 caracteres
    2207023,  # media type desconocido
    2207026,  # formato de vídeo no soportado
    2207027,  # el vídeo no se pudo procesar
    2207028,  # un carrusel admite entre 2 y 10 elementos
    2207032,  # falló la creación del container
    2207052,  # no se pudo descargar el media de la URI
    2207057,  # thumbnail offset fuera de rango
}

CODIGOS_GLOBALES = {
    1,    # API desconocida (lado de Meta)
    2,    # servicio de la API caído
    4,    # límite de peticiones de la aplicación
    9,    # límite de publicaciones alcanzado
    10,   # permiso no concedido
    17,   # límite de peticiones del usuario
    25,   # acceso restringido
    32,   # límite de peticiones de la Página
    190,  # token inválido o caducado
    341,  # límite de la aplicación
    368,  # bloqueado temporalmente por incumplir políticas
    613,  # demasiadas llamadas por segundo
}

CODIGOS_DEL_ITEM = {
    -2,     # error subiendo SU media
    24,     # su container no existe o caducó
    506,    # publicación duplicada
    9004,   # su media no se pudo descargar
    9007,   # su vídeo no se puede publicar
    36000,  # imagen demasiado grande
    36001,  # formato de imagen inválido
    36003,  # aspect ratio inválido
    36004,  # caption demasiado largo
}

# Los códigos de permisos van todos juntos: falta un scope en la app, no es el
# post el que está mal.
RANGO_PERMISOS = range(200, 300)


@dataclass(frozen=True)
class MetaError:
    """Lo que devolvió Meta, sin perder de qué código venía.

    Es una dataclass y no una subclase de `str` a propósito: un `str` disfrazado
    sobrevive a `motivo[:2000]` pero se pierde en silencio en cuanto alguien
    escriba `f"...{msg}..."` en el camino, y ese fallo no lo caza ningún test.
    Aquí, si alguien reformatea, el que se pierde es visible. Para reetiquetar
    conservando el código está `con_prefijo`.
    """

    mensaje: str
    code: int | None = None
    subcode: int | None = None
    transient: bool = False

    def __str__(self) -> str:
        return self.mensaje

    @classmethod
    def desde(cls, data: dict) -> MetaError:
        """Construye desde la respuesta JSON de la Graph API.

        Acepta tanto el sobre entero (`{"error": {...}}`) como el error suelto,
        porque `_create_media` recibe lo uno y `publish` lo otro.
        """
        err = data.get("error", data) if isinstance(data, dict) else {}
        if not isinstance(err, dict):
            err = {}
        mensaje = err.get("message") or str(data)
        return cls(
            mensaje=mensaje,
            code=_entero(err.get("code")),
            subcode=_entero(err.get("error_subcode")),
            transient=bool(err.get("is_transient", False)),
        )

    def con_prefijo(self, prefijo: str) -> MetaError:
        """«hijo 3/5: …» sin tirar el código a la basura.

        `post_carousel` reetiquetaba el error del hijo con un f-string, y ahí se
        perdía el 25 que decía que la cuenta estaba restringida.
        """
        return replace(self, mensaje=f"{prefijo}: {self.mensaje}")

    @property
    def etiqueta(self) -> str | None:
        """`"25/2207050"` para guardar en BD y enseñar en el panel."""
        if self.code is None and self.subcode is None:
            return None
        if self.subcode is None:
            return str(self.code)
        return f"{self.code}/{self.subcode}"


def _entero(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def es_global(motivo) -> bool:
    """¿Este fallo le pasaría igual a cualquier post de la cola?

    Lo explícito manda sobre lo heurístico: primero el subcódigo (lo más
    específico), luego `is_transient` —que es Meta diciéndonos que reintentar
    tiene sentido—, y solo después el código a secas.
    """
    if not isinstance(motivo, MetaError):
        # Un fallo sin código no viene de Meta: es nuestro (Cloudinary, un
        # fichero que falta). Eso es material del item.
        return False
    if motivo.subcode is not None:
        if motivo.subcode in SUBCODIGOS_GLOBALES:
            return True
        if motivo.subcode in SUBCODIGOS_DEL_ITEM:
            return False
    if motivo.transient:
        return True
    return motivo.code in CODIGOS_GLOBALES or motivo.code in RANGO_PERMISOS


def quema_intento(motivo) -> bool:
    """¿Le gastamos un intento a este post por este fallo?

    Un código DESCONOCIDO gasta intento. Es la decisión incómoda, así que queda
    escrita: no gastarlo deja la cola parada para siempre detrás del mismo item
    —`next_pending` ordena por `position` y reelige siempre el primero—, y ese
    es el fallo silencioso. Gastarlo es ruidoso y reversible: salta la alerta,
    y `recover_failed` lo devuelve a la cola. Además el cortacircuitos de
    `publisher.publicacion_bloqueada` detecta las caídas globales por RACHA, sin
    mirar el código, así que un global nuevo tampoco vacía la cola.
    """
    return not es_global(motivo)
