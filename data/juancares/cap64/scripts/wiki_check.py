"""Comprueba en Wikipedia ES si una persona tiene artículo propio y si la nombran
los artículos de Robe/Extremoduro y de sus discos. Solo lectura (API pública).

Uso: python wiki_check.py <salida.json>
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "RobeLyrics-research/1.0 (entity research)"}
API = "https://es.wikipedia.org/w/api.php?"


def get(params: dict) -> dict:
    url = API + urllib.parse.urlencode({**params, "format": "json"})
    ultimo = None
    for intento in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:  # red o 429 de Wikimedia: reintento con espera creciente
            ultimo = e
            print(f"  reintento {intento + 1}: {e!r}", file=sys.stderr)
            time.sleep(3 * (intento + 1))
    raise RuntimeError(f"{url}: {ultimo!r}")


def extract(title: str) -> tuple[str, str | None, str]:
    d = get({"action": "query", "prop": "extracts|pageprops|info", "inprop": "url",
             "explaintext": 1, "redirects": 1, "titles": title})
    p = next(iter(d["query"]["pages"].values()))
    return p.get("extract", ""), p.get("pageprops", {}).get("wikibase_item"), p.get("fullurl", "")



def main() -> None:
    ARTICULO_PROPIO = {"E-020": "Elía María Blanco Barbero"}
    CONTEXTO = ["Roberto Iniesta", "Extremoduro", "Rock transgresivo", "Somos unos animales",
                "Deltoya", "¿Dónde están mis amigos?", "Agila", "Iros todos a tomar por culo",
                "Grandes éxitos y fracasos"]  # «Plasencia» no responde a tiempo por la API (10-11-2026)
    PATRONES = {
        "E-020": r"Elía|Elia (María )?Blanco", "E-028": r"José Luis Díaz",
        "E-037": r"\bJuano\b", "E-039": r"D[óo]niga", "E-040": r"Ángel Lorenzo|Ángel",
        "E-047": r"Paramio", "E-048": r"Génesis|Javi Gómez", "E-049": r"Belén",
        "E-055": r"Susi", "E-068": r"Mateos Brea|mural",
    }

    out = {"fecha": time.strftime("%Y-%m-%d %H:%M"), "propios": {}, "menciones": []}
    for eid, titulo in ARTICULO_PROPIO.items():
        texto, qid, url = extract(titulo)
        out["propios"][eid] = {"titulo": titulo, "qid": qid, "url": url, "extracto": texto[:2500]}
    for titulo in CONTEXTO:
        texto, qid, url = extract(titulo)
        for eid, pat in PATRONES.items():
            for m in re.finditer(pat, texto):
                out["menciones"].append({"id": eid, "articulo": titulo, "url": url,
                                         "fragmento": texto[max(0, m.start() - 160):m.end() + 160].replace("\n", " ")})
        time.sleep(0.5)
    json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: (v["qid"], v["url"]) for k, v in out["propios"].items()}, ensure_ascii=False))
    for m in out["menciones"]:
        print(m["id"], "·", m["articulo"], "→", m["fragmento"][:330])


if __name__ == "__main__":
    main()
