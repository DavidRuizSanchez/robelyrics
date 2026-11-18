"""Consultas de GSC que nombran a la muestra (volcado del repo data/gsc_page_queries.json).
Uso: python gsc_muestra.py <repo_root> <salida.json>"""
import json, re, sys, unicodedata
from pathlib import Path
root = Path(sys.argv[1])
def n(s): return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
PAT = {"E-020": r"\belia\b", "E-028": r"jose luis diaz|alcalde", "E-037": r"\bjuano\b|dosis letal",
       "E-039": r"doniga", "E-040": r"angel lorenzo|primer bateria", "E-049/E-050": r"timon|corista|\bcoros?\b|\bbelen\b",
       "E-055": r"susi|buitre|portada", "E-048": r"genesis|tertulia", "E-047": r"paramio|cuadra",
       "E-068": r"mural|mateos|brea"}
pq = json.load(open(root / "data/gsc_page_queries.json"))
out = {"site": pq["site"], "period": pq["period"], "por_persona": {}}
for eid, pat in PAT.items():
    filas = []
    for page, info in pq["pages"].items():
        for r in (info.get("queries") if isinstance(info, dict) else info) or []:
            if re.search(pat, n(r["query"])):
                filas.append({"page": page, **r})
    filas.sort(key=lambda r: -r["impressions"])
    out["por_persona"][eid] = filas
json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
print(out["period"])
for eid, f in out["por_persona"].items():
    print(eid, len(f), [(r["query"], r["impressions"], r.get("position"), r["page"]) for r in f[:6]])
