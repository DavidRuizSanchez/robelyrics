"""Genera CSV + MD de entidades y valida cada minuto citado contra source_segments (volcado)."""
import csv
import re
import sys
import unicodedata
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from entidades import E_  # noqa: E402

OUT = Path(sys.argv[1])
SEG = OUT / "segments.tsv"


def norm(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", texto)
    sin_acentos = "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")
    return sin_acentos.lower()


def hms(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


segmentos = []
for linea in SEG.read_text(encoding="utf-8").splitlines():
    idx, ini, fin, texto = linea.split("\t", 3)
    segmentos.append((int(idx), float(ini), hms(float(ini)), norm(texto)))
por_hms = {}
for pos, seg in enumerate(segmentos):
    por_hms.setdefault(seg[2], pos)

filas, fallos = [], []
for n, (tipo, nombre, transcrito, patron, minutos, resumen, slug, nota) in enumerate(E_, 1):
    rx = re.compile(patron)
    tramos = [s for s in segmentos if rx.search(s[3])]
    verificados = []
    for m in minutos:
        pos = por_hms.get(m)
        ventana = segmentos[pos:pos + 3] if pos is not None else []
        ok = any(rx.search(s[3]) for s in ventana)
        verificados.append(ok)
        if not ok:
            fallos.append((n, nombre, m, "sin tramo con ese inicio" if pos is None else "el patrón no aparece"))
    filas.append(OrderedDict(
        id=f"E-{n:03d}", tipo=tipo, entidad=nombre, como_lo_transcribe_whisper=transcrito,
        minutos=" · ".join(minutos), minutos_verificados=f"{sum(verificados)}/{len(minutos)}",
        tramos_que_casan=len(tramos),
        primera_aparicion=tramos[0][2] if tramos else "", ultima_aparicion=tramos[-1][2] if tramos else "",
        que_dice_el_video=resumen, en_bd="sí" if slug else "no", slug_bd=slug, nota_cruce_bd=nota,
    ))

with open(OUT / "entidades_cap64.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
    w.writeheader()
    w.writerows(filas)

orden = ["Persona", "Grupo", "Disco", "Canción", "Lugar", "Organización", "Evento", "Medio/obra"]
titulos = {"Persona": "Personas", "Grupo": "Grupos", "Disco": "Discos y maquetas", "Canción": "Canciones",
           "Lugar": "Lugares", "Organización": "Organizaciones", "Evento": "Eventos", "Medio/obra": "Objetos y obras"}
md = ["# Entidades del capítulo 64 de «La historia de Extremoduro»: «Plasencia y Robe»", "",
      "Vídeo: «¡ESTRENO! PLASENCIA Y ROBE. CAPÍTULO 64 DE LA HISTORIA DE EXTREMODURO» (Juancares, 07-11-2026), "
      "https://www.youtube.com/watch?v=cwUsXq54KvA · 3 h 29 min.", "",
      "Sale de la transcripción de Whisper guardada en prod (`interpretation_sources.id = 1756`, 2.698 tramos con tiempo) "
      "y se cruza con la BD de prod. **Lo que va en «qué dice» es lo que dice el vídeo, no un hecho verificado**: "
      "el material es de un tercero y la transcripción trae erratas. Los minutos marcan dónde se puede comprobar cada cosa.", "",
      f"**{len(filas)} entidades** · {sum(1 for f in filas if f['en_bd'] == 'sí')} ya tienen ficha en la BD · "
      f"{sum(1 for f in filas if f['en_bd'] == 'no')} no la tienen.", ""]
md.append("| Tipo | Entidades | Con ficha en la BD |")
md.append("|---|---|---|")
for t in orden:
    del_tipo = [f for f in filas if f["tipo"] == t]
    md.append(f"| {titulos[t]} | {len(del_tipo)} | {sum(1 for f in del_tipo if f['en_bd'] == 'sí')} |")
md.append("")
for t in orden:
    md += [f"## {titulos[t]}", ""]
    for f in [f for f in filas if f["tipo"] == t]:
        bd = f"ficha `{f['slug_bd']}`" if f["slug_bd"] else "sin ficha"
        md.append(f"- **{f['entidad']}** ({f['id']}) · {f['minutos']} · {bd}  ")
        md.append(f"  {f['que_dice_el_video']}" + (f"  \n  _{f['nota_cruce_bd']}_" if f["nota_cruce_bd"] else ""))
    md.append("")
(OUT / "entidades_cap64.md").write_text("\n".join(md), encoding="utf-8")

ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
val = [f"# Validación de minutos ({ahora}, hora local)", "",
       f"Minutos citados: {sum(len(e[4]) for e in E_)} · comprobados con texto en el tramo: "
       f"{sum(len(e[4]) for e in E_) - len(fallos)} · fallos: {len(fallos)}", ""]
val += [f"- E-{n:03d} {nombre} @ {m}: {motivo}" for n, nombre, m, motivo in fallos]
(OUT / "validacion_minutos.md").write_text("\n".join(val), encoding="utf-8")
print("\n".join(val))
