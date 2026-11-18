"""Volumen (Google Ads vía DataForSEO, ES/es) del tema «Robe/Extremoduro y Plasencia» y de los temas
que podrían ser hub (fase 0 del plan aprobado el 10-11-2026). Corre dentro del api de prod; no escribe.
`search_volume: null` se conserva (n/d).
Uso: ssh robelyrics 'docker exec -i robelyrics-api python -' < volumenes_plasencia.py > volumenes_plasencia.json"""
import base64, json, os, time
import httpx
KEYWORDS = {
    "plasencia": ["extremoduro plasencia", "robe plasencia", "robe iniesta plasencia", "extremoduro en plasencia",
                  "historia de extremoduro", "origen de extremoduro", "donde nacio robe", "casa de robe plasencia",
                  "casa de la salud plasencia", "concierto extremoduro plasencia", "extremoduro plasencia 1995",
                  "extremoduro plasencia 2008", "calle robe plasencia", "avenida robe plasencia",
                  "robe hijo predilecto plasencia", "homenaje robe plasencia", "ruta robe plasencia",
                  "primeras flores amarillas", "primeras flores amarillas plasencia", "festival robe plasencia"],
    "murales": ["mural robe plasencia", "mural robe", "murales robe", "mural extremoduro", "mural robe chinato",
                "primo mural robe", "mural plaza san martin plasencia"],
    "grupos_escena": ["dosis letal", "dosis letal robe", "dosis letal extremoduro", "indecision momentanea",
                      "orquesta escarlata", "colectivo de musicos plasencia", "primer grupo de robe"],
    "formacion": ["primer bateria de extremoduro", "miembros de extremoduro", "integrantes de extremoduro",
                  "coristas de extremoduro", "formacion original extremoduro", "fundadores de extremoduro"],
    "politica": ["extremoduro vetado plasencia", "carta de robe al alcalde", "robe alcalde plasencia",
                 "extremoduro censura"],
}
tok = base64.b64encode(f"{os.environ['DATAFORSEO_LOGIN']}:{os.environ['DATAFORSEO_PASSWORD']}".encode()).decode()
todas = [k for ks in KEYWORDS.values() for k in ks]
r = httpx.post("https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live",
               headers={"Authorization": f"Basic {tok}"},
               json=[{"keywords": todas, "location_code": 2724, "language_code": "es"}], timeout=120)
r.raise_for_status()
task = r.json()["tasks"][0]
filas = {row["keyword"]: row for row in (task.get("result") or [])}
print(json.dumps({"extraido": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                  "endpoint": "keywords_data/google_ads/search_volume/live", "location_code": 2724,
                  "language_code": "es", "status": [task["status_code"], task["status_message"]],
                  "coste_usd": task.get("cost"),
                  "por_tema": {t: {k: {"search_volume": (filas.get(k) or {}).get("search_volume"), "monthly": (filas.get(k) or {}).get("monthly_searches")} for k in ks}
                               for t, ks in KEYWORDS.items()}}, ensure_ascii=False, indent=1))
