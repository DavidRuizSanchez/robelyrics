"""Renderiza tarjetas de muestra del nuevo diseño (para revisión). No publica.

Demuestra: foto por ENTIDAD (Wikimedia/Openverse) + PORTADA de disco + arte
de respaldo. No toca la BD: las fotos por entidad se buscan en vivo y la
portada se pasa por URL directa.
"""
import os
import sys

sys.path.insert(0, "/app")
from app.services.instagram import config, imaging, photo_finder

OUT = "/tmp/cards"
os.makedirs(OUT, exist_ok=True)
imaging.config.IMAGES_DIR = OUT


def _foto(query: str) -> dict:
    f = photo_finder.find({"title": query, "image_query": query}) or {}
    print(f"  query={query!r} -> {f.get('credit', 'SIN FOTO')}")
    return f


print("Buscando fotos por entidad…")
leiva = _foto("Leiva músico cantante")
plasencia = _foto("Plasencia")

cards = [
    {  # 1) Entidad PERSONA: foto de Leiva (no de Robe) — variedad
        "category": "Actualidad", "tone": "sober",
        "headline": "Leiva: «Le echo mucho de menos»",
        "image_hint": leiva.get("url", ""), "image_credit": leiva.get("credit", ""),
        "image_kind": "photo",
        "verse": {"line": "Si tú te vas, se va contigo el mundo entero",
                  "artist": "Extremoduro", "song": "Standby", "year": 1996},
    },
    {  # 2) Entidad LUGAR: foto de Plasencia — variedad
        "category": "Actualidad", "tone": "neutral",
        "headline": "El macromural que Plasencia dedica a Robe Iniesta",
        "image_hint": plasencia.get("url", ""), "image_credit": plasencia.get("credit", ""),
        "image_kind": "photo",
        "verse": {"line": "Mira por donde va Robe", "artist": "Extremoduro",
                  "song": "Bri, bri, bli, bli", "year": 1993},
    },
    {  # 3) PORTADA de disco (nuestra, auto-alojada)
        "category": "Efemérides", "tone": "neutral",
        "headline": "«Material defectuoso» cumple 15 años",
        "image_hint": config.SITE_URL + "/album-covers/material-defectuoso.jpg",
        "image_credit": "", "image_kind": "cover",
        "verse": {"line": "Cuando te de lo mismo, serás Extremoduro",
                  "artist": "Extremoduro", "song": "La Hoguera", "year": 1997},
    },
]

for i, c in enumerate(cards):
    path, real = imaging.generate(c, slot=i)
    print(f"card {i} ({c['image_kind']}): foto={real} -> {path}")
