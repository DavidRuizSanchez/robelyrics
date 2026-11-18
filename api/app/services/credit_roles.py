"""Roles de `song_credits`: autoría frente a interpretación.

La tabla nació para la AUTORÍA (letra, música, poema original…) y varios caminos
lo dan por hecho. Desde el 10-11-2026 guarda también quién canta coros o voces
en la grabación (créditos de Wikipedia, `scripts/seed_vocal_credits.py`), y eso
no es autoría: un crédito de coros no puede cerrar una errata de autoría ni hacer
que el consenso dé por «ya acreditado» a nadie.
"""
from __future__ import annotations

ROLES_INTERPRETACION = ("coros", "voces")
