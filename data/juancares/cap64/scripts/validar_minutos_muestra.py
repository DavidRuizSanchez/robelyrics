"""Comprueba por texto cada minuto citado en la propuesta de la muestra: en ese tramo o
en los dos siguientes tiene que estar lo que se le atribuye.  Uso: python validar_minutos_muestra.py <dir_cap64>"""
import json, re, sys, unicodedata
from pathlib import Path
B = Path(sys.argv[1])
def n(s): return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
segs = [l.split("\t", 3) for l in (B / "segments.tsv").read_text(encoding="utf-8").splitlines()]
ESPERADO = {  # minuto → patrón que debe estar en el tramo o los dos siguientes
    "1:38:30": r"amiga|repuestos", "1:35:47": r"elia blanco.*concejala", "2:42:44": r"elia|extrem",
    "2:31:49": r"dover", "2:32:01": r"censura previa", "2:17:37": r"diaz|alcalde|up plasencia|union",
    "0:38:48": r"bajista", "0:39:06": r"rory gallagher", "0:39:20": r"campo de futbol", "0:39:37": r"dosis.*letal|dedicatoria",
    "0:39:56": r"convencio", "1:02:09": r"tesorer", "1:26:42": r"tecnico de sonido", "0:39:47": r"juano",
    "0:54:44": r"fanta|jazz|robert", "0:55:19": r"casa de la salud", "1:10:38": r"belen y maria",
    "1:10:50": r"maria y yo", "2:21:56": r"belen", "1:58:35": r"gustavo|dibujos|casualidad",
    "1:57:53": r"bellota|buitre", "1:07:40": r"paramio|cuadra", "1:10:12": r"genesis|tertulia|javi",
    "3:24:28": r"mural|brea|bejar",
}
def seg(hms):
    h, m, s = map(int, hms.split(":")); t = h * 3600 + m * 60 + s
    return next(i for i, x in enumerate(segs) if float(x[2]) > t)
data = json.loads((B / "analisis_personas/muestra_evidencia.json").read_text())
citados = {f.split("@")[1] for p in data["muestra"] for _, fs in p["hechos"] for f in fs if "@" in f}
citados |= {"0:54:44", "1:58:35", "3:24:28", "0:55:19"}  # los de la matriz de relaciones
ok, fallos = [], []
for mnt in sorted(citados):
    i = seg(mnt); texto = n(" ".join(x[3] for x in segs[i:i + 3]))
    (ok if re.search(ESPERADO[mnt], texto) else fallos).append((mnt, segs[i][3][:90]))
out = f"# Validación de minutos de la muestra\n\nMinutos citados: {len(citados)} · comprueban: {len(ok)} · fallos: {len(fallos)}\n\n"
out += "".join(f"- FALLO {m}: «{t}»\n" for m, t in fallos)
(B / "analisis_personas/validacion_minutos_muestra.md").write_text(out)
print(out)
