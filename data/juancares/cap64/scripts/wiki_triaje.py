"""Triaje en Wikipedia ES (fuente oficial de grafía, criterio de David del 10-11-2026) de las 13
candidatas restantes y los 5 nombres dudosos: ¿artículo propio? ¿las nombran los artículos de
contexto (Extremoduro, Roberto Iniesta, Plasencia, Elía María Blanco, discos)?
Uso: python wiki_triaje.py <salida.json>"""
import json, re, sys, time
sys.path.insert(0, __import__("os").path.dirname(__file__))
from wiki_check import get, extract  # noqa: E402

BUSCAR = {  # id → (consulta de búsqueda de artículo propio, patrón para los artículos de contexto)
    "E-018": ("José Luis Mariño alcalde Plasencia", r"Mari[ñn]o"),
    "E-019": ("Cándido Cabrera Plasencia", r"Cándido Cabrera|Cabrera"),
    "E-029": ("Fernando Pizarro alcalde Plasencia", r"Fernando Pizarro"),
    "E-030": ("José Antonio Hernández Plasencia concejal", r"José Antonio Hernández"),
    "E-031": ("Enrique Tornero Plasencia", r"Tornero"),
    "E-032": ("Virgilio Consejo de la Juventud Plasencia", r"Virgilio"),
    "E-046": ("Cholo Colectivo de Músicos Plasencia", r"\bCholo\b"),
    "E-051": ("Marcos Peral músico", r"Marcos Peral"),
    "E-052": ("Bar Simetría Plasencia", r"Simetría"),
    "E-053": ("Orquesta Escarlata", r"Escarlata|Félix"),
    "E-056": ("buitre portada Extremoduro Gustavo", r"Gustavo"),
    "E-057": ("Miguel Ángel Corisco", r"Corisco"),
    "E-060": ("mánager Extremoduro 1995", r"Raúl"),
    "E-023": ("teniente de alcalde Plasencia 1989", r"Ventura"),
    "E-038": ("Luisma Beltrán Zósimo Pascual Dosis Letal", r"Luisma|Zósimo|Zosi"),
    "E-054": ("Dosis Letal Plasencia Luis", r"Luis Ba"),
    "E-059": ("Los 40 Principales concurso Yamaha Extremoduro", r"Yamaha|Rever"),
    "E-067": ("fotógrafo portada disco Robe Valcorchero", r"Valcorchero|Armest"),
}
CONTEXTO = ["Extremoduro", "Roberto Iniesta", "Plasencia", "Elía María Blanco Barbero",
            "Tú en tu casa, nosotros en la hoguera", "Rock transgresivo", "Somos unos animales",
            "Mayéutica", "Destrozares, canciones para el final de los tiempos", "Se nos lleva el aire",
            "Ayuntamiento de Plasencia"]
out = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "busquedas": {}, "contexto": [], "articulos_contexto": {}}
for eid, (q, _) in BUSCAR.items():
    d = get({"action": "query", "list": "search", "srsearch": q, "srlimit": 5})
    if "query" not in d:
        out["busquedas"][eid] = {"error": d.get("error")}
        continue
    out["busquedas"][eid] = [r["title"] for r in d["query"]["search"]]
    time.sleep(0.4)
for titulo in CONTEXTO:
    try:
        texto, qid, url = extract(titulo)
    except RuntimeError as e:  # 429 persistente de Wikimedia: se apunta, no se inventa
        out["articulos_contexto"][titulo] = {"error": str(e)[-80:]}
        continue
    out["articulos_contexto"][titulo] = {"url": url, "chars": len(texto)}
    for eid, (_, pat) in BUSCAR.items():
        for m in re.finditer(pat, texto):
            out["contexto"].append({"id": eid, "articulo": titulo, "url": url,
                                    "fragmento": texto[max(0, m.start() - 160):m.end() + 160].replace("\n", " ")})
    time.sleep(0.6)
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for eid, r in out["busquedas"].items(): print(eid, "búsqueda →", r)
print({k: v.get("chars", v.get("error")) for k, v in out["articulos_contexto"].items()})
for m in out["contexto"]: print(m["id"], "·", m["articulo"], "→", m["fragmento"][:300])
