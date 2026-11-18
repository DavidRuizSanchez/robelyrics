"""Volumen de búsqueda (Google Ads vía DataForSEO, España, español) de las variantes
de nombre de la muestra de 10. Corre DENTRO del contenedor api de prod (allí están
las credenciales) y no escribe nada: imprime el JSON crudo de la respuesta.
`search_volume: null` se conserva como null (n/d), NO como 0.

Uso: ssh robelyrics 'docker exec -i robelyrics-api python -' < volumenes_muestra.py > volumenes_muestra.json
"""
import base64
import json
import os
import time

import httpx

KEYWORDS = {
    "E-020": ["elia blanco", "elia blanco extremoduro", "elia blanco robe", "elia maria blanco"],
    "E-028": ["jose luis diaz plasencia", "jose luis diaz extremoduro", "alcalde plasencia extremoduro"],
    "E-037": ["juano dosis letal", "juano extremoduro", "dosis letal", "dosis letal robe", "dosis letal extremoduro"],
    "E-039": ["paco doniga", "paco doniga extremoduro", "paco doniga robe"],
    "E-040": ["angel lorenzo extremoduro", "angel lorenzo bateria", "primer bateria de extremoduro"],
    "E-049/E-050": ["maria timon", "maria timon extremoduro", "coristas de extremoduro", "belen extremoduro"],
    "E-055": ["susi iglesias", "susi iglesias extremoduro", "portada rock transgresivo"],
    "E-048": ["bar genesis plasencia", "javi genesis plasencia"],
    "E-047": ["paramio extremoduro", "la cuadra plasencia"],
    "E-068": ["jesus mateos brea", "mateos brea", "mural robe plasencia", "mural extremoduro plasencia"],
}
token = base64.b64encode(f"{os.environ['DATAFORSEO_LOGIN']}:{os.environ['DATAFORSEO_PASSWORD']}".encode()).decode()
todas = [k for ks in KEYWORDS.values() for k in ks]
r = httpx.post(
    "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
    headers={"Authorization": f"Basic {token}"},
    json=[{"keywords": todas, "location_code": 2724, "language_code": "es"}],
    timeout=120,
)
r.raise_for_status()
task = r.json()["tasks"][0]
filas = {row["keyword"]: row for row in (task.get("result") or [])}
print(json.dumps({
    "extraido": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
    "endpoint": "keywords_data/google_ads/search_volume/live",
    "location_code": 2724, "language_code": "es",
    "status": [task["status_code"], task["status_message"]], "coste_usd": task.get("cost"),
    "por_persona": {eid: {k: {"search_volume": (filas.get(k) or {}).get("search_volume"),
                              "monthly": (filas.get(k) or {}).get("monthly_searches")}
                          for k in ks} for eid, ks in KEYWORDS.items()},
}, ensure_ascii=False, indent=1))
