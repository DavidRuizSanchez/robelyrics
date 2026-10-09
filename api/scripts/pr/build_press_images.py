"""Genera las imágenes de prensa del estudio de repertorio en directo.

Corre en el HOST (necesita Playwright con Chromium):

    python3 -I api/scripts/pr/build_press_images.py            # todas
    python3 -I api/scripts/pr/build_press_images.py ranking    # solo las que contengan «ranking»

Las cifras se leen de los MISMOS ficheros que pinta la página del estudio
(`web/components/estudio/datos-repertorio.ts`, `datos-por-pagina.ts`, `mapa-provincias.ts`):
una sola fuente por métrica, así que una imagen de prensa no puede decir otra cosa que la web.
Todas llevan el crédito de setlist.fm, que es condición de uso de su dato (y el mapa de la
primera tanda no lo llevaba).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ESTUDIO = REPO / "web/components/estudio"
SALIDA = REPO / "data/estudio/prensa"

FONDO, PAPEL, TENUE, DIVISOR = "#0d0b0a", "#ede4d3", "rgba(237,228,211,.58)", "rgba(237,228,211,.10)"
GRANATE, OCRE, TEXTO_ACENTO = "#a83a3a", "#b08a2a", "#e85050"
RAMPA = ["#3a1a18", "#5c2320", "#7d2c2a", "#9c3634", "#b8443f", "#cf5f55"]
CREDITO = "ENTRE INTERIORES · ENTREINTERIORES.COM &nbsp;·&nbsp; DATOS: SETLIST.FM (CONSULTADO EL 6 Y 7-OCT-2026)"


# --------------------------------------------------------------------------- #
# Datos: se parsean los literales de los .ts que genera el estudio
# --------------------------------------------------------------------------- #
def _literal(fichero: str, nombre: str):
    texto = (ESTUDIO / fichero).read_text(encoding="utf-8")
    m = re.search(rf"export const {nombre}[^=]*=\s*(.*?);\s*\n(?:export|$)", texto + "\nexport", re.S)
    if not m:
        sys.exit(f"no encuentro {nombre} en {fichero}")
    crudo = re.sub(r"([{,]\s*)(\d{4})\s*:", r'\1"\2":', m.group(1))  # {1987:1} → {"1987":1}
    crudo = re.sub(r",(\s*[\]}])", r"\1", crudo)  # coma final de TS antes de ] o }
    return json.loads(crudo)


PROV = _literal("datos-repertorio.ts", "PROV")
CIUDADES = _literal("datos-repertorio.ts", "CIUDADES")
TOP = _literal("datos-repertorio.ts", "TOP")
ONCE = _literal("datos-repertorio.ts", "ONCE")
ANIOS_E = {int(k): v for k, v in _literal("datos-repertorio.ts", "ANIOS_E").items()}
ANIOS_R = {int(k): v for k, v in _literal("datos-repertorio.ts", "ANIOS_R").items()}
ARTISTAS = _literal("datos-por-pagina.ts", "DATOS")["artistas"]
MAPA_PATHS = _literal("mapa-provincias.ts", "MAPA_PATHS")
MAPA_INSET = _literal("mapa-provincias.ts", "MAPA_INSET")

TOTAL_CONCIERTOS = ARTISTAS["extremoduro"]["setlists"] + ARTISTAS["robe"]["setlists"]
MAX_PROV = max(p["n"] for p in PROV.values())


def coma(x) -> str:
    return str(x).replace(".", ",")


def color_prov(n: int) -> str:
    return RAMPA[min(len(RAMPA) - 1, int((n / MAX_PROV) ** 0.5 * len(RAMPA)))]


# --------------------------------------------------------------------------- #
# Plantilla común
# --------------------------------------------------------------------------- #
def pagina(ancho: int, alto: int, antetitulo: str, titulo: str, cuerpo: str, pie: str = "",
           solo_mapa: bool = False) -> str:
    cabecera = "" if solo_mapa else f"""
      <div class="ante">{html.escape(antetitulo)}</div>
      <h1>{titulo}</h1>"""
    nota = f'<p class="pie">{pie}</p>' if pie else ""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=JetBrains+Mono:wght@400;500&display=block" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ width: {ancho}px; height: {alto}px; background: {FONDO}; color: {PAPEL};
         font-family: 'Cormorant Garamond', Georgia, serif; font-variant-numeric: lining-nums; padding: 84px 96px 72px;
         display: flex; flex-direction: column; }}
  .ante {{ font-family: 'JetBrains Mono', monospace; font-size: 24px; letter-spacing: 6px;
          text-transform: uppercase; color: {TENUE}; margin-bottom: 22px; }}
  h1 {{ font-weight: 600; font-size: 86px; line-height: 1.02; max-width: 1700px; }}
  h1 em {{ font-style: italic; color: {TEXTO_ACENTO}; font-weight: 500; }}
  .cuerpo {{ flex: 1; display: flex; flex-direction: column; justify-content: center; min-height: 0; }}
  .pie {{ font-size: 34px; line-height: 1.3; color: {TENUE}; max-width: 1750px; margin-top: 26px; }}
  .credito {{ font-family: 'JetBrains Mono', monospace; font-size: 19px; letter-spacing: 3px;
             color: {TEXTO_ACENTO}; margin-top: 28px; padding-top: 22px; border-top: 1px solid {DIVISOR}; }}
  .mono {{ font-family: 'JetBrains Mono', monospace; }}
  .barra {{ display: grid; align-items: center; column-gap: 28px; }}
  .etq {{ font-size: 38px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .val {{ font-family: 'JetBrains Mono', monospace; font-size: 28px; color: {PAPEL}; white-space: nowrap; }}
  .pista {{ height: 100%; display: flex; align-items: center; }}
  .rel {{ height: 34px; border-radius: 0 4px 4px 0; }}
  .leyenda {{ display: flex; gap: 44px; font-family: 'JetBrains Mono', monospace; font-size: 24px;
             letter-spacing: 2px; color: {TENUE}; margin-bottom: 26px; }}
  .leyenda i {{ display: inline-block; width: 28px; height: 18px; border-radius: 3px; margin-right: 12px;
               vertical-align: -2px; }}
</style></head><body>
  {cabecera}
  <div class="cuerpo">{cuerpo}</div>
  {nota}
  <div class="credito">{CREDITO}</div>
</body></html>"""


def barras(filas: list[tuple[str, float, str, str]], ancho_etq: int = 520, alto_fila: int = 64,
           maximo: float | None = None) -> str:
    """filas: (etiqueta, valor, color, texto del valor). Barra fina, extremo redondeado
    anclado a la base, valor en tinta de texto (nunca en el color de la serie)."""
    maximo = maximo or max(v for _, v, _, _ in filas)
    out = []
    for etq, v, color, txt in filas:
        pct = 100 * v / maximo
        out.append(f"""<div class="barra" style="grid-template-columns:{ancho_etq}px 1fr;height:{alto_fila}px">
          <div class="etq">{html.escape(etq)}</div>
          <div class="pista"><div class="rel" style="width:calc((100% - 140px) * {pct / 100:.4f});min-width:6px;background:{color}"></div>
          <span class="val" style="margin-left:18px">{txt}</span></div></div>""")
    return "".join(out)


# --------------------------------------------------------------------------- #
# Piezas
# --------------------------------------------------------------------------- #
def _svg_mapa(alto_px: int) -> str:
    caminos = []
    for prov, d in MAPA_PATHS.items():
        p = PROV.get(prov)
        fill = color_prov(p["n"]) if p else "rgba(237,228,211,.07)"
        caminos.append(f'<path d="{d}" fill="{fill}" stroke="{FONDO}" stroke-width="1.2"/>')
    i = MAPA_INSET
    return f"""<svg viewBox="0 0 1000 720" style="height:{alto_px}px;width:auto;display:block;margin:0 auto">
      <rect x="{i['x']}" y="{i['y']}" width="{i['w']}" height="{i['h']}" fill="none"
            stroke="rgba(237,228,211,.25)" stroke-dasharray="4 4"/>{''.join(caminos)}</svg>"""


def _leyenda_rampa() -> str:
    tramos = "".join(f'<i style="background:{c};width:44px;height:22px;margin:0 2px 0 0"></i>' for c in RAMPA)
    return f"""<div class="leyenda" style="justify-content:center;margin:24px 0 0">
      <span>1 CONCIERTO</span><span>{tramos}</span><span>{MAX_PROV}</span>
      <span style="margin-left:30px">RECUADRO: CANARIAS</span></div>"""


def mapa_prensa() -> str:
    caceres, barcelona = PROV["Cáceres"]["n"], PROV["Barcelona"]["n"]
    segunda = sorted(PROV.items(), key=lambda kv: -kv[1]["n"])[1][0]
    assert segunda == "Cáceres", f"la segunda provincia ya no es Cáceres sino {segunda}"
    return pagina(2000, 2000, "Estudio del repertorio en directo",
                  f"Extremoduro y Robe tocaron en las {len(PROV)} provincias de España",
                  _svg_mapa(1250) + _leyenda_rampa(),
                  f"{TOTAL_CONCIERTOS} conciertos documentados entre {ARTISTAS['extremoduro']['desde']} y "
                  f"{ARTISTAS['robe']['hasta']}. Cáceres es la segunda provincia de España, con {caceres}, "
                  f"por delante de Barcelona ({barcelona}).")


def mapa_limpio() -> str:
    return pagina(2000, 1560, "", "", _svg_mapa(1300) + _leyenda_rampa(), solo_mapa=True)


def ranking_provincias() -> str:
    top = sorted(PROV.items(), key=lambda kv: -kv[1]["n"])[:10]
    filas = [(prov, p["n"], GRANATE if prov == "Cáceres" else "rgba(237,228,211,.28)", str(p["n"]))
             for prov, p in top]
    return pagina(2000, 1500, "Conciertos documentados por provincia",
                  "Cáceres, <em>la segunda provincia</em> de España en conciertos de Extremoduro y Robe",
                  barras(filas, ancho_etq=430, alto_fila=78),
                  f"Las diez provincias con más conciertos documentados, 1987-2024. "
                  f"Cuenta la provincia del recinto; {TOTAL_CONCIERTOS} conciertos en total.")


def extremadura() -> str:
    cac, bad = PROV["Cáceres"], PROV["Badajoz"]
    filas = [(c["c"], c["n"], GRANATE, str(c["n"])) for c in cac["ciudades"]]
    filas += [(c["c"], c["n"], OCRE, str(c["n"])) for c in bad["ciudades"]]
    total = cac["n"] + bad["n"]
    leyenda = (f'<div class="leyenda"><span><i style="background:{GRANATE}"></i>PROVINCIA DE CÁCERES · '
               f'{cac["n"]} CONCIERTOS EN {cac["n_ciudades"]} LOCALIDADES</span>'
               f'<span><i style="background:{OCRE}"></i>PROVINCIA DE BADAJOZ · {bad["n"]} EN '
               f'{bad["n_ciudades"]}</span></div>')
    return pagina(2000, 1400, "Extremadura en el directo de Extremoduro y Robe",
                  f"<em>{total} conciertos</em> en Extremadura, {cac['n']} de ellos en la provincia de Cáceres",
                  leyenda + barras(filas, ancho_etq=360, alto_fila=82),
                  f"Las tres localidades con más conciertos de cada provincia. Cáceres: de "
                  f"{cac['primer']} a {cac['ultimo']}; Badajoz: de {bad['primer']} a {bad['ultimo']}.")


def ciudades() -> str:
    cac = next(c for c in CIUDADES if c[0] == "Cáceres")[2]
    pla = next(c for c in CIUDADES if c[0] == "Plasencia")[2]
    bcn = next(c for c in CIUDADES if c[0] == "Barcelona")[2]
    filas = [(c[0], c[2], GRANATE if c[0] in ("Cáceres", "Plasencia") else "rgba(237,228,211,.28)", str(c[2]))
             for c in CIUDADES]
    return pagina(2000, 1700, "Las ciudades con más conciertos",
                  f"Cáceres y Plasencia suman <em>{cac + pla}</em>: más que Barcelona ({bcn})",
                  barras(filas, ancho_etq=400, alto_fila=62),
                  "Conciertos documentados por municipio, 1987-2024. Cuenta el municipio del recinto, no el "
                  "área metropolitana (Leganés o Rivas no suman a Madrid).")


def por_anio() -> str:
    anios = list(range(1987, 2025))
    maximo = max(list(ANIOS_E.values()) + list(ANIOS_R.values()))
    cols = []
    for a in anios:
        v, color = (ANIOS_E[a], GRANATE) if a in ANIOS_E else (ANIOS_R[a], OCRE) if a in ANIOS_R else (0, "")
        alto = 760 * v / maximo
        barra = (f'<div style="height:{alto:.0f}px;width:100%;background:{color};border-radius:4px 4px 0 0"></div>'
                 if v else "")
        num = f'<div class="mono" style="font-size:20px;color:{PAPEL};margin-bottom:8px">{v}</div>' if v else ""
        cols.append(f'<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;'
                    f'align-items:center;margin:0 3px">{num}{barra}</div>')
    ejes = "".join(
        f'<div style="flex:1;margin:0 3px" class="mono"><div style="font-size:19px;color:{TENUE};'
        f'text-align:center">{str(a)[2:] if (a in ANIOS_E or a in ANIOS_R) else ""}</div></div>' for a in anios)
    leyenda = (f'<div class="leyenda"><span><i style="background:{GRANATE}"></i>EXTREMODURO · '
               f'{ARTISTAS["extremoduro"]["setlists"]} CONCIERTOS</span><span><i style="background:{OCRE}">'
               f'</i>ROBE · {ARTISTAS["robe"]["setlists"]}</span></div>')
    cuerpo = (leyenda + f'<div style="display:flex;height:820px;border-bottom:1px solid {DIVISOR}">'
              f'{"".join(cols)}</div><div style="display:flex;margin-top:10px">{ejes}</div>')
    return pagina(2000, 1500, "Conciertos documentados por año",
                  "Treinta y siete años de directos, de <em>1987</em> a <em>2024</em>", cuerpo,
                  "Un año sin barra es un año sin conciertos registrados en setlist.fm, no un año sin conciertos: "
                  "el archivo lo rellenan personas. De la primera gira de Robe (2015-2016) no consta ninguno.")


def mas_tocadas() -> str:
    filas, maximo = [], max(e + r for _, _, e, r in TOP)
    for cancion, disco, e, r in TOP[:12]:
        we, wr = 100 * e / maximo, 100 * r / maximo
        filas.append(f"""<div class="barra" style="grid-template-columns:640px 1fr;height:92px">
          <div class="etq" style="font-size:36px;line-height:1.05">{html.escape(cancion)}<br>
            <span class="mono" style="font-size:18px;color:{TENUE};letter-spacing:1px">{html.escape(disco)}</span></div>
          <div class="pista"><div style="width:calc({we:.2f}% * .82);height:34px;background:{GRANATE}"></div>
            <div style="width:calc({wr:.2f}% * .82);height:34px;background:{OCRE};margin-left:2px;
                 border-radius:0 4px 4px 0"></div>
            <span class="val" style="margin-left:18px">{e + r}</span></div></div>""")
    leyenda = (f'<div class="leyenda"><span><i style="background:{GRANATE}"></i>CON EXTREMODURO</span>'
               f'<span><i style="background:{OCRE}"></i>CON ROBE</span></div>')
    return pagina(2000, 1800, "Las canciones más tocadas en directo",
                  "«Ama, ama, ama y ensancha el alma», <em>la que más sonó</em>",
                  leyenda + "".join(filas),
                  f"Veces que suena cada canción en los {TOTAL_CONCIERTOS} conciertos documentados, sumando "
                  f"las dos etapas.")


def material_ajeno() -> str:
    e, r = ARTISTAS["extremoduro"]["pct_ajeno"], ARTISTAS["robe"]["pct_ajeno"]

    def tile(cifra, quien, color):
        return f"""<div style="flex:1;border-top:6px solid {color};padding-top:40px">
          <div style="font-size:260px;font-weight:600;line-height:1;font-variant-numeric:lining-nums">{coma(cifra)}<span style="font-size:120px"> %</span></div>
          <div class="mono" style="font-size:30px;letter-spacing:4px;color:{TENUE};margin-top:40px">{quien}</div></div>"""
    cuerpo = f'<div style="display:flex;gap:120px">{tile(e, "EXTREMODURO", GRANATE)}{tile(r, "ROBE", OCRE)}</div>'
    return pagina(2000, 1250, "Qué parte del concierto no era de sus propios discos",
                  "Casi <em>un tercio</em> de lo que tocaba Robe no era de sus discos", cuerpo,
                  "Porcentaje de las canciones tocadas que no son de los discos de estudio de cada etapa. "
                  "En Robe incluye los temas de Extremoduro que llevaba al directo y las versiones.")


def once_canciones() -> str:
    filas = "".join(
        f"""<div style="display:grid;grid-template-columns:70px 1fr auto;align-items:baseline;
             padding:16px 0;border-bottom:1px dotted rgba(13,11,10,.35)">
          <span class="mono" style="font-size:22px;color:rgba(13,11,10,.55)">{i:02d}</span>
          <span style="font-size:44px;letter-spacing:2px;text-transform:uppercase">{html.escape(c)}</span>
          <span class="mono" style="font-size:22px;color:rgba(13,11,10,.55)">’{d.rsplit('· ', 1)[-1][2:]}</span></div>"""
        for i, (c, d, _) in enumerate(ONCE, 1))
    hoja = f"""<div style="background:#efe7d6;color:#1a1614;width:1040px;margin:0 auto;padding:70px 64px 50px;
         transform:rotate(-1.2deg);box-shadow:0 30px 80px rgba(0,0,0,.6)">
      <div style="font-size:70px;font-weight:600;text-align:center;line-height:1.05">Once canciones<br>sin registro en directo</div>
      <div class="mono" style="font-size:20px;letter-spacing:8px;text-align:center;color:rgba(13,11,10,.6);
           margin:26px 0 30px;padding-bottom:26px;border-bottom:3px solid #1a1614">EXTREMODURO · 1992-2013</div>
      {filas}
      <div style="font-size:30px;font-style:italic;margin-top:30px;color:rgba(13,11,10,.75)">No consta que ninguna sonara en directo.</div></div>"""
    return pagina(2000, 2100, "", "", hoja,
                  f"Ninguna aparece en los {TOTAL_CONCIERTOS} conciertos documentados. Ausencia de registro, "
                  f"no prueba de que nunca sonaran.", solo_mapa=True)


PIEZAS = {
    "mapa-provincias-prensa": mapa_prensa,
    "mapa-provincias": mapa_limpio,
    "ranking-provincias": ranking_provincias,
    "extremadura-provincias": extremadura,
    "ciudades-caceres-plasencia": ciudades,
    "conciertos-por-anio": por_anio,
    "canciones-mas-tocadas": mas_tocadas,
    "material-ajeno": material_ajeno,
    "once-canciones-sin-registro": once_canciones,
}


def main() -> int:
    from playwright.sync_api import sync_playwright

    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    SALIDA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        for nombre, fn in PIEZAS.items():
            if filtro and filtro not in nombre:
                continue
            doc = fn()
            ancho, alto = (int(x) for x in re.search(r"width: (\d+)px; height: (\d+)px", doc).groups())
            pag = nav.new_page(viewport={"width": ancho, "height": alto})
            pag.set_content(doc, wait_until="networkidle")
            pag.evaluate("document.fonts.ready")
            destino = SALIDA / f"{nombre}.png"
            pag.screenshot(path=str(destino), full_page=False)
            pag.close()
            print(f"{destino.relative_to(REPO)}  {ancho}×{alto}")
        nav.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
