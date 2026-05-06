"""Rate limiting con slowapi.

Detrás de Caddy (reverse proxy), el `request.client.host` que ve FastAPI es la
IP del proxy (172.18.0.x en la red docker), no la del cliente real. Si dejamos
que slowapi use `get_remote_address` por defecto, el límite se aplica
globalmente — un atacante distribuye su brute-force entre IPs y nosotros vemos
una sola "IP" que es Caddy.

Por eso definimos un `key_func` propio que prefiere `X-Forwarded-For`
(primer IP, que es la del cliente original que vió Caddy) y cae al
remote_address solo si el header falta.

Storage: memoria del proceso. Suficiente para single instance Hetzner CAX21.
Si en algún momento se escala a multi-instancia, mover a Redis (slowapi
soporta Redis storage transparentemente).
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def client_ip(request: Request) -> str:
    """Devuelve la IP del cliente respetando X-Forwarded-For si está.

    Solo confía en X-Forwarded-For si el request viene desde un proxy
    interno conocido (en nuestro caso, cualquier IP de la red docker
    interna). En la práctica con Caddy delante siempre vendrá set; si
    falta, fallback al remote address.
    """
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        # X-Forwarded-For: <client>, <proxy1>, <proxy2>...
        return fwd.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip, storage_uri="memory://")
