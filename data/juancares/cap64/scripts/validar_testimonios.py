"""Cada cita de testimonios_borrador.md tiene que estar LITERAL en la transcripción, dentro de su
rango de minutos (los «…» separan trozos; cada trozo se busca por separado).
Uso: python validar_testimonios.py <dir_cap64>"""
import re, sys
from pathlib import Path
B = Path(sys.argv[1])
segs = [l.split("\t", 3) for l in (B / "segments.tsv").read_text(encoding="utf-8").splitlines()]
def s(hms): h, m, x = map(int, hms.split(":")); return h * 3600 + m * 60 + x
md = (B / "analisis_personas/testimonios_borrador.md").read_text(encoding="utf-8")
ok = fallos = 0
for m in re.finditer(r"^\| (T-\d+) \| ([\d:]+)(?:-([\d:]+))? \| «(.+?)» \|", md, re.M):
    tid, a, b, cita = m.groups()
    ini, fin = s(a), s(b or a)
    texto = " ".join(x[3] for x in segs if ini - 1 <= float(x[1]) <= fin + 1)
    trozos = [t.strip(" ,.") for t in cita.split("…") if t.strip(" ,.")]
    faltan = [t for t in trozos if t not in texto]
    if faltan: fallos += 1; print("FALLO", tid, a, "→", faltan)
    else: ok += 1
print(f"testimonios: {ok} ok, {fallos} fallos")
