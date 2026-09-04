"""Monta el visor HTML del keyword research (un solo fichero, sin dependencias).

    python -m scripts.seo.kw_artifact --run ola1-discos-v2

Lee el entregable ya fusionado y genera `artifact.html`: selector de disco,
clusters ordenados por volumen, tabla filtrable y el detalle de procedencia de
cada keyword. Los datos van embebidos como JSON — no hace ninguna petición.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("/app/kw_out")

HTML = """<!doctype html>
<meta charset="utf-8">
<title>Keyword research — universo Extremoduro / Robe</title>
<style>
 :root{--gr:#a83a3a;--bg:#0d0b0a;--pa:#ede4d3;--di:rgba(237,228,211,.10)}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--pa);
   font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;line-height:1.5}
 header{padding:28px 32px;border-bottom:1px solid var(--di)}
 h1{margin:0 0 6px;font-size:23px;font-weight:600;letter-spacing:-.01em}
 .sub{opacity:.62;font-size:13px}
 .kpis{display:flex;flex-wrap:wrap;gap:26px;margin-top:18px}
 .kpi b{display:block;font-size:25px;color:var(--gr);font-variant-numeric:tabular-nums}
 .kpi span{font-size:10.5px;text-transform:uppercase;letter-spacing:2px;opacity:.55}
 main{padding:22px 32px 60px}
 .bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:20px}
 select,input{background:#171312;color:var(--pa);border:1px solid var(--di);
   border-radius:7px;padding:9px 11px;font:inherit;font-size:13.5px}
 input{flex:1;min-width:190px}
 table{width:100%;border-collapse:collapse;font-size:13.5px}
 th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--di);
   vertical-align:top}
 th{font-size:10.5px;text-transform:uppercase;letter-spacing:1.6px;opacity:.55;
   cursor:pointer;user-select:none;white-space:nowrap}
 td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
 .wrap{overflow-x:auto;border:1px solid var(--di);border-radius:10px}
 .tag{display:inline-block;font-size:10px;letter-spacing:1.2px;text-transform:uppercase;
   padding:2px 7px;border-radius:99px;border:1px solid var(--di);opacity:.8}
 .head{color:var(--gr);font-weight:600}
 .cl{margin:0 0 16px;display:flex;flex-wrap:wrap;gap:7px}
 .cl button{background:#171312;color:var(--pa);border:1px solid var(--di);
   border-radius:99px;padding:6px 13px;font:inherit;font-size:12.5px;cursor:pointer}
 .cl button.on{background:var(--gr);border-color:var(--gr)}
 .empty{opacity:.5;padding:26px;text-align:center}
 .note{opacity:.55;font-size:12px;margin-top:14px}
</style>
<header>
  <h1>Keyword research — universo Extremoduro / Robe</h1>
  <div class="sub" id="sub"></div>
  <div class="kpis" id="kpis"></div>
</header>
<main>
  <div class="bar">
    <select id="asset"></select>
    <input id="q" placeholder="filtrar keywords…">
    <label style="font-size:13px;opacity:.7">
      <input type="checkbox" id="conv" style="width:auto;min-width:0"> solo con volumen
    </label>
  </div>
  <div class="cl" id="cl"></div>
  <div class="wrap"><table>
    <thead><tr>
      <th data-k="keyword">Keyword</th>
      <th data-k="cluster_label">Cluster</th>
      <th data-k="volume_best" class="n">Vol. mejor</th>
      <th data-k="volume_dataforseo" class="n">DataForSEO</th>
      <th data-k="volume_ahrefs" class="n">Ahrefs</th>
      <th data-k="difficulty" class="n">KD</th>
      <th data-k="intent_lex">Intención</th>
      <th data-k="volume_sources">Fuentes</th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table></div>
  <div class="note">Celda vacía = sin dato en esa fuente. Nunca es un cero
    estimado. «Vol. mejor» es un derivado: el mayor de las dos fuentes.</div>
</main>
<script>
const DATA = __DATA__;
let sortK = "volume_best", sortDir = -1, cluster = null;
const $ = id => document.getElementById(id);
const num = v => (v === "" || v === null || v === undefined) ? null : +v;

$("sub").textContent = DATA.meta.sub;
$("kpis").innerHTML = DATA.meta.kpis
  .map(k => `<div class="kpi"><b>${k[1]}</b><span>${k[0]}</span></div>`).join("");
$("asset").innerHTML = DATA.assets
  .map((a,i) => `<option value="${i}">${a.title} — ${a.rows.length} kws</option>`).join("");

function clusters(a){
  const m = new Map();
  a.rows.forEach(r => {
    if(!r.cluster_label) return;
    const c = m.get(r.cluster_label) || {n:0,v:0};
    c.n++; c.v += num(r.volume_best) || 0; m.set(r.cluster_label, c);
  });
  return [...m.entries()].sort((x,y) => y[1].v - x[1].v);
}

function render(){
  const a = DATA.assets[+$("asset").value];
  const q = $("q").value.toLowerCase().trim();
  const solo = $("conv").checked;

  $("cl").innerHTML = `<button class="${cluster?"":"on"}" data-c="">todos</button>` +
    clusters(a).map(([lab,c]) =>
      `<button class="${cluster===lab?"on":""}" data-c="${lab.replace(/"/g,"&quot;")}">${lab} · ${c.n}</button>`
    ).join("");
  $("cl").querySelectorAll("button").forEach(b =>
    b.onclick = () => { cluster = b.dataset.c || null; render(); });

  let rows = a.rows.filter(r =>
    (!q || r.keyword.toLowerCase().includes(q)) &&
    (!cluster || r.cluster_label === cluster) &&
    (!solo || (num(r.volume_best) || 0) > 0));

  rows.sort((x,y) => {
    const A = x[sortK], B = y[sortK];
    const na = num(A), nb = num(B);
    if(na !== null && nb !== null) return (na - nb) * sortDir;
    return String(A||"").localeCompare(String(B||"")) * sortDir;
  });

  $("tb").innerHTML = rows.length ? rows.slice(0, 3000).map(r => `<tr>
    <td class="${r.is_head==="True"?"head":""}">${r.keyword}${r.is_head==="True"?' <span class="tag">cabeza</span>':""}</td>
    <td style="opacity:.72">${r.cluster_label||""}</td>
    <td class="n">${r.volume_best||""}</td>
    <td class="n">${r.volume_dataforseo||""}</td>
    <td class="n">${r.volume_ahrefs||""}</td>
    <td class="n">${r.difficulty||""}</td>
    <td>${r.intent_lex||""}</td>
    <td style="opacity:.6;font-size:12px">${(r.volume_sources||"").replace(/\\|/g," + ")}</td>
  </tr>`).join("") : `<tr><td colspan="8" class="empty">Nada casa con el filtro.</td></tr>`;
}

document.querySelectorAll("th").forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  if(sortK === k) sortDir = -sortDir; else { sortK = k; sortDir = -1; }
  render();
});
$("asset").onchange = () => { cluster = null; render(); };
$("q").oninput = render;
$("conv").onchange = render;
render();
</script>
"""

COLS = ["keyword", "cluster_label", "is_head", "volume_best", "volume_dataforseo",
        "volume_ahrefs", "difficulty", "intent_lex", "volume_sources"]

TIPO = {"artist": "Artista", "album": "Disco", "song": "Canción"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    # Se lee el fichero ATRIBUIDO, no el fusionado: es el que tiene cada keyword
    # con un solo dueño. El fusionado repite la misma keyword en los 16 discos.
    out_dir = ROOT / args.run / "atribuido"
    master = out_dir / "master.csv"
    if not master.exists():
        print(f"No existe {master}. Lanza antes kw_merge y kw_attribute.")
        return 1

    por_asset: dict[tuple[str, str], list[dict]] = defaultdict(list)
    titulos: dict[tuple[str, str], str] = {}
    total_vol = 0
    con_ahrefs = 0
    for r in csv.DictReader(master.open(encoding="utf-8")):
        key = (r["owner_type"], r["owner_slug"])
        por_asset[key].append({c: r.get(c, "") for c in COLS})
        titulos[key] = f"{TIPO.get(r['owner_type'], r['owner_type'])} · {r['owner_title']}"
        total_vol += int(r["volume_best"] or 0)
        if r.get("volume_ahrefs"):
            con_ahrefs += 1

    assets = [
        {"slug": k[1], "title": titulos[k],
         "rows": sorted(v, key=lambda r: -int(r["volume_best"] or 0))}
        for k, v in sorted(
            por_asset.items(),
            key=lambda kv: -sum(int(r["volume_best"] or 0) for r in kv[1]),
        )
    ]
    total_kw = sum(len(a["rows"]) for a in assets)
    clusters = len({(a["slug"], r["cluster_label"]) for a in assets for r in a["rows"]
                    if r["cluster_label"]})

    data = {
        "meta": {
            "sub": f"Run {args.run} · cierre transitivo hasta saturación · "
                   "DataForSEO + Ahrefs · sin filtro de volumen · "
                   "cada keyword atribuida a un solo asset",
            "kpis": [
                ["assets", len(assets)],
                ["keywords únicas", f"{total_kw:,}".replace(",", ".")],
                ["clusters", clusters],
                ["volumen/mes", f"{total_vol:,}".replace(",", ".")],
                ["con dato de ahrefs", f"{con_ahrefs:,}".replace(",", ".")],
            ],
        },
        "assets": assets,
    }
    path = out_dir / "artifact.html"
    path.write_text(HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)),
                    encoding="utf-8")
    print(f"Visor: {path} ({total_kw} keywords, {len(assets)} discos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
