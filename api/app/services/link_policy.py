"""Política de enlazado interno: una sola fuente de verdad.

Hasta el 11-11-2026 cada camino comparaba los enlaces a su manera
(`entity_resolver._url_path`, `relink_existing._path`, `link_stats._to_path`) y
el autolinker comparaba las URLs EN CRUDO: el índice del corpus las da absolutas
(`https://entreinteriores.com/...`) y `url_resolver._reenlazar` las reescribe
relativas (`/sellos/...`). El autolinker no veía el enlace que ya existía, no lo
contaba en el tope y enlazaba la siguiente mención. Así `/personas/alen-ayerdi`
llegó a enlazar 6 veces a El Dromedario Records: uno más por pasada del cron.

Aquí vive la normalización de rutas. Las reglas de David del 11-11 (1 enlace
por destino, 3 en el cuerpo, solo entidades relacionadas, anchors variados)
llegan a este módulo en un PR aparte.
"""
from __future__ import annotations

import re

SITE_HOSTS = ("entreinteriores.com", "www.entreinteriores.com")

_ABSOLUTA = re.compile(r"^(?:https?:)?//([^/?#]+)(.*)$", re.IGNORECASE)
_NO_NAVEGABLE = ("mailto:", "tel:", "javascript:", "#")


def norm_path(url: str | None) -> str | None:
    """Ruta interna comparable (`/a/b`, sin dominio, query, fragmento ni barra
    final), o `None` si el enlace no es interno.

    Dos enlaces apuntan a la misma página si y solo si dan la misma ruta aquí.
    """
    u = (url or "").strip()
    if not u or u.lower().startswith(_NO_NAVEGABLE):
        return None
    m = _ABSOLUTA.match(u)
    if m:
        host = m.group(1).lower().split(":", 1)[0]
        if host not in SITE_HOSTS:
            return None
        u = m.group(2)
    elif not u.startswith("/"):
        return None
    u = re.split(r"[?#]", u, maxsplit=1)[0]
    return "/" + u.strip("/")
