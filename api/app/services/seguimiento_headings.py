"""¿Qué les ha pasado en Google a las páginas con los headings humanizados?

Petición de David (11-11-2026): medir cómo rinden los cambios de headings a 1, 2, 3
y 4 semanas y recibirlo por correo. Los cambios los aplicó `humanize_headings`
(10 y 11-11-2026) y cada uno dejó su copia en `content_revisions` con
`reason='headings humanos…'`: esa tabla es la única fuente de QUÉ se tocó y CUÁNDO.

Cómo se mide, y por qué así:

  - **Ventanas simétricas de semanas enteras.** Para la semana k, el «después» son
    los 7·k días siguientes al ÚLTIMO cambio de la página y el «antes», los 7·k
    días previos al PRIMERO. Los días del cambio no cuentan en ningún lado (las
    fechas de la BD van en UTC y las de GSC en hora del Pacífico). Al ser semanas
    enteras, el «antes» y el «después» tienen el mismo número de lunes, martes…
  - **Grupo de control.** Casi todo el sitio se tocó, pero no todo (blog, hubs,
    páginas en código). Sus mismas ventanas dan la tendencia de fondo
    (estacionalidad, un core update), y la diferencia entre los dos grupos es lo
    más cerca de un efecto que permite el dato. Aun así es `[HIPÓTESIS]`: el
    control no es aleatorio y es pequeño.
  - **¿Lo ha visto Google?** Un cambio que Google no ha rastreado no puede haber
    movido nada. La inspección de URL dice cuándo rastreó cada página por última
    vez; las que no se han rastreado tras el cambio se cuentan aparte.
  - **Consultas protegidas**, con la misma vara que `ranking_guard`: las que
    tenían clics o posición ≤ 20 en el «antes». Se avisa de las que caen más de
    `CAIDA_POSICIONES` puestos, como `merge_watch`. Solo AVISA: revertir es un
    botón y lo pulsa una persona.

Todo determinista y sin red: los datos los baja la Mac (el token de GSC vive allí)
y aquí solo se calcula.
"""
from __future__ import annotations

import html as _html
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

SEMANAS = (1, 2, 3, 4)
CAIDA_POSICIONES = 5.0
MIN_IMPRESIONES_QUERY = 3
MIN_IMPRESIONES_PAGINA = 20
TOP_PAGINAS = 10


def _d(x: str | date) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


@dataclass
class Totales:
    clics: int = 0
    impresiones: int = 0
    _pos_x_imp: float = 0.0

    def sumar(self, clics: int, impresiones: int, posicion: float) -> None:
        self.clics += int(clics)
        self.impresiones += int(impresiones)
        self._pos_x_imp += float(posicion) * int(impresiones)

    @property
    def ctr(self) -> float | None:
        return self.clics / self.impresiones if self.impresiones else None

    @property
    def posicion(self) -> float | None:
        return self._pos_x_imp / self.impresiones if self.impresiones else None


@dataclass
class Comparacion:
    antes: Totales = field(default_factory=Totales)
    despues: Totales = field(default_factory=Totales)
    paginas: int = 0

    @staticmethod
    def _pct(a: float, b: float) -> float | None:
        return (b - a) / a * 100 if a else None

    @property
    def d_clics(self) -> float | None:
        return self._pct(self.antes.clics, self.despues.clics)

    @property
    def d_impresiones(self) -> float | None:
        return self._pct(self.antes.impresiones, self.despues.impresiones)

    @property
    def d_posicion(self) -> float | None:
        a, b = self.antes.posicion, self.despues.posicion
        return b - a if a is not None and b is not None else None


def ventanas(primero: str | date, ultimo: str | date, semanas: int
             ) -> tuple[tuple[date, date], tuple[date, date]]:
    """(antes, después) como intervalos cerrados de 7·semanas días."""
    n = 7 * semanas
    p, u = _d(primero), _d(ultimo)
    return (p - timedelta(days=n), p - timedelta(days=1)), \
           (u + timedelta(days=1), u + timedelta(days=n))


def semana_cubierta(cambios: dict, fin_datos: str | date, semanas: int) -> bool:
    """¿Llegan los datos de GSC al final del «después» de TODAS las páginas?"""
    ultimo = max(_d(c["ultimo"]) for c in cambios.values())
    return _d(fin_datos) >= ultimo + timedelta(days=7 * semanas)


def semana_pendiente(cambios: dict, fin_datos: str | date, enviadas) -> int | None:
    """La primera semana con datos que aún no se ha mandado."""
    hechas = {int(k) for k in enviadas or ()}
    for k in SEMANAS:
        if k not in hechas and semana_cubierta(cambios, fin_datos, k):
            return k
    return None


def _en(dia: date, intervalo: tuple[date, date]) -> bool:
    return intervalo[0] <= dia <= intervalo[1]


def apartadas_por_title(cambios: dict, titles: dict | None, semanas: int) -> tuple[set, set]:
    """Páginas cuyo TITLE cambió antes de que acabe su ventana «después».

    Decisión de David (11-11-2026): los titles se rehacen por tandas semanales y el
    seguimiento es conjunto. Una página con title nuevo ya no mide solo los
    headings, y tampoco sirve de control: se aparta y se cuenta. Las de las tandas
    siguientes siguen midiendo headings limpios hasta que les toque.
    """
    if not titles:
        return set(), set()
    primero_global = min(_d(c["primero"]) for c in cambios.values())
    ultimo_global = max(_d(c["ultimo"]) for c in cambios.values())
    fin_control = ventanas(primero_global, ultimo_global, semanas)[1][1]
    cam, con = set(), set()
    for path, cuando in titles.items():
        dia = _d(cuando)
        if path in cambios:
            if dia <= ventanas(cambios[path]["primero"], cambios[path]["ultimo"],
                               semanas)[1][1]:
                cam.add(path)
        elif dia <= fin_control:
            con.add(path)
    return cam, con


def analizar(cambios: dict, gsc: dict, semanas: int, titles: dict | None = None) -> dict:
    """Todas las cifras del informe de la semana `semanas`, desde las filas crudas.

    `cambios`: {path: {"primero", "ultimo", "tipo"}} (de `content_revisions`).
    `titles`: {path: fecha del primer cambio de title} (reason «titles humanos»).
    `gsc`: {"page_daily": [[path, fecha, clics, imp, pos]],
            "page_query_daily": [[path, query, fecha, clics, imp, pos]],
            "inspeccion": {path: {"lastCrawlTime": iso|None, ...}}, "fin": fecha}.
    """
    primero_global = min(_d(c["primero"]) for c in cambios.values())
    ultimo_global = max(_d(c["ultimo"]) for c in cambios.values())
    v_control = ventanas(primero_global, ultimo_global, semanas)
    v_pag = {p: ventanas(c["primero"], c["ultimo"], semanas) for p, c in cambios.items()}

    inspeccion = gsc.get("inspeccion") or {}
    fuera_cam, fuera_con = apartadas_por_title(cambios, titles, semanas)
    fuera = fuera_cam | fuera_con

    def rastreada(path: str) -> bool | None:
        info = inspeccion.get(path)
        if not info or not info.get("lastCrawlTime"):
            return None if not info else False
        return _d(info["lastCrawlTime"]) > _d(cambios[path]["ultimo"])

    grupos = {"cambiadas": Comparacion(), "control": Comparacion(),
              "rastreadas": Comparacion(), "sin_rastrear": Comparacion()}
    por_tipo: dict[str, Comparacion] = defaultdict(Comparacion)
    por_pagina: dict[str, Comparacion] = defaultdict(Comparacion)
    vistas: dict[str, set[str]] = defaultdict(set)

    for path, fecha, clics, imp, pos in gsc.get("page_daily") or []:
        if path in fuera:
            continue
        dia = _d(fecha)
        if path in cambios:
            antes, despues = v_pag[path]
            destinos = [grupos["cambiadas"], por_tipo[cambios[path].get("tipo") or "—"],
                        por_pagina[path]]
            r = rastreada(path)
            if r is True:
                destinos.append(grupos["rastreadas"])
            elif r is False:
                destinos.append(grupos["sin_rastrear"])
            clave = "cambiadas"
        else:
            antes, despues = v_control
            destinos = [grupos["control"]]
            clave = "control"
        lado = "antes" if _en(dia, antes) else "despues" if _en(dia, despues) else None
        if not lado:
            continue
        vistas[clave].add(path)
        for c in destinos:
            getattr(c, lado).sumar(clics, imp, pos)

    for c in por_pagina.values():
        c.paginas = 1
    grupos["cambiadas"].paginas = len(vistas["cambiadas"])
    grupos["control"].paginas = len(vistas["control"])
    for nombre in ("rastreadas", "sin_rastrear"):
        grupos[nombre].paginas = sum(1 for p in vistas["cambiadas"]
                                     if rastreada(p) is (nombre == "rastreadas"))
    for tipo in por_tipo:
        por_tipo[tipo].paginas = sum(1 for p in vistas["cambiadas"]
                                     if (cambios[p].get("tipo") or "—") == tipo)

    # Consultas protegidas de las páginas cambiadas.
    q_antes: dict[tuple[str, str], Totales] = defaultdict(Totales)
    q_despues: dict[tuple[str, str], Totales] = defaultdict(Totales)
    for path, query, fecha, clics, imp, pos in gsc.get("page_query_daily") or []:
        if path not in cambios or path in fuera:
            continue
        antes, despues = v_pag[path]
        dia = _d(fecha)
        if _en(dia, antes):
            q_antes[(path, query)].sumar(clics, imp, pos)
        elif _en(dia, despues):
            q_despues[(path, query)].sumar(clics, imp, pos)

    protegidas = []
    for key, a in q_antes.items():
        if a.impresiones < MIN_IMPRESIONES_QUERY and not a.clics:
            continue
        if not (a.clics > 0 or (a.posicion or 100) <= 20):
            continue
        d = q_despues.get(key)
        fila = {"path": key[0], "query": key[1], "imp_antes": a.impresiones,
                "clics_antes": a.clics, "pos_antes": round(a.posicion or 0, 1),
                "imp_despues": d.impresiones if d else 0,
                "clics_despues": d.clics if d else 0,
                "pos_despues": round(d.posicion, 1) if d and d.posicion is not None else None}
        if not d or d.impresiones < MIN_IMPRESIONES_QUERY:
            fila["estado"] = "sin datos después"
        else:
            delta = (d.posicion or 0) - (a.posicion or 0)
            fila["delta"] = round(delta, 1)
            fila["estado"] = ("cae" if delta > CAIDA_POSICIONES
                              else "mejora" if delta < -CAIDA_POSICIONES else "estable")
        protegidas.append(fila)
    protegidas.sort(key=lambda f: (-f["clics_antes"], -f["imp_antes"]))

    filas_pagina = []
    for path, c in por_pagina.items():
        if max(c.antes.impresiones, c.despues.impresiones) < MIN_IMPRESIONES_PAGINA:
            continue
        filas_pagina.append({
            "path": path, "tipo": cambios[path].get("tipo") or "—",
            "clics_antes": c.antes.clics, "clics_despues": c.despues.clics,
            "imp_antes": c.antes.impresiones, "imp_despues": c.despues.impresiones,
            "pos_antes": c.antes.posicion, "pos_despues": c.despues.posicion,
            "rastreada": rastreada(path),
        })
    filas_pagina.sort(key=lambda f: f["clics_despues"] - f["clics_antes"])

    total_rastreables = sum(1 for p in cambios if p in inspeccion)
    return {
        "semanas": semanas,
        "ventana_control": v_control,
        "grupos": grupos,
        "por_tipo": dict(sorted(por_tipo.items(), key=lambda kv: -kv[1].antes.impresiones)),
        "protegidas": protegidas,
        "paginas": filas_pagina,
        "n_cambios": len(cambios),
        "apartadas_title": {"cambiadas": len(fuera_cam), "control": len(fuera_con)},
        "rastreo": {
            "inspeccionadas": total_rastreables,
            "tras_el_cambio": sum(1 for p in cambios if rastreada(p) is True),
            "antes_del_cambio": sum(1 for p in cambios if rastreada(p) is False),
        },
    }


# ---------------------------------------------------------------- presentación

def _n(x) -> str:
    return "—" if x is None else f"{x:,.0f}".replace(",", ".")


def _pct(x) -> str:
    return "—" if x is None else f"{x:+.1f} %".replace(".", ",")


def _pos(x) -> str:
    return "—" if x is None else f"{x:.1f}".replace(".", ",")


def _dpos(x) -> str:
    # Posición: bajar el número es subir en Google.
    return "—" if x is None else f"{x:+.1f}".replace(".", ",")


def _fecha(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def lectura(res: dict) -> list[str]:
    """Frases de diagnóstico, solo con lo que dicen las cifras."""
    g = res["grupos"]
    cam, con = g["cambiadas"], g["control"]
    out = []
    if cam.d_clics is not None and con.d_clics is not None:
        dif = cam.d_clics - con.d_clics
        quien = ("sin diferencia" if abs(dif) < 0.05 else
                 f"diferencia de {abs(dif):.1f} puntos a favor ".replace(".", ",")
                 + ("de las cambiadas" if dif > 0 else "del control"))
        out.append(
            f"Clics: las páginas cambiadas van {_pct(cam.d_clics)} y el control "
            f"{_pct(con.d_clics)}; {quien}. [HIPÓTESIS] sobre la causa: el control no "
            "es aleatorio y es pequeño.")
    if cam.d_posicion is not None and con.d_posicion is not None:
        out.append(
            f"Posición media: cambiadas {_dpos(cam.d_posicion)} y control "
            f"{_dpos(con.d_posicion)} (negativo = suben en Google).")
    r = res["rastreo"]
    if r["inspeccionadas"]:
        out.append(
            f"Google ha rastreado {r['tras_el_cambio']} de {r['inspeccionadas']} páginas "
            f"inspeccionadas después del cambio; {r['antes_del_cambio']} siguen con un "
            "rastreo anterior, así que en esas el cambio aún no puede haber hecho nada.")
    caen = [p for p in res["protegidas"] if p["estado"] == "cae"]
    sin = sum(1 for p in res["protegidas"] if p["estado"] == "sin datos después")
    mejoran = sum(1 for p in res["protegidas"] if p["estado"] == "mejora")
    out.append(f"Consultas protegidas: {len(res['protegidas'])}. Caen más de "
               f"{CAIDA_POSICIONES:.0f} puestos {len(caen)}, mejoran más de "
               f"{CAIDA_POSICIONES:.0f} {mejoran} y {sin} no tienen impresiones suficientes "
               "en el «después» para compararlas.")
    ap = res.get("apartadas_title") or {}
    if ap.get("cambiadas") or ap.get("control"):
        out.append(
            f"Apartadas por tener el title nuevo dentro de la ventana: {ap['cambiadas']} "
            f"páginas con headings y {ap['control']} del control. Ya no miden solo los "
            "headings; los titles llevan su propio seguimiento.")
    if res["semanas"] == 1:
        out.append("Una semana es muy poco para concluir nada: es la foto de partida.")
    return out


def informe_texto(res: dict, meta: dict) -> str:
    g = res["grupos"]
    k = res["semanas"]
    vc_antes, vc_despues = res["ventana_control"]
    L = [f"HEADINGS HUMANOS · SEMANA {k} DE 4", ""]
    L += [f"- {x}" for x in lectura(res)]
    L += ["", "GRUPOS (clics · impresiones · CTR · posición media; antes → después)"]
    for nombre, etiqueta in (("cambiadas", "Páginas cambiadas"), ("control", "Control"),
                             ("rastreadas", "Cambiadas y ya rastreadas"),
                             ("sin_rastrear", "Cambiadas sin rastrear aún")):
        c = g[nombre]
        if not c.paginas:
            continue
        L.append(
            f"{etiqueta} ({c.paginas} pág.): clics {_n(c.antes.clics)} → "
            f"{_n(c.despues.clics)} ({_pct(c.d_clics)}) · imp. {_n(c.antes.impresiones)} → "
            f"{_n(c.despues.impresiones)} ({_pct(c.d_impresiones)}) · pos. "
            f"{_pos(c.antes.posicion)} → {_pos(c.despues.posicion)} ({_dpos(c.d_posicion)})")
    L += ["", "POR TIPO DE PÁGINA (solo cambiadas)"]
    for tipo, c in res["por_tipo"].items():
        L.append(f"{tipo} ({c.paginas}): clics {_n(c.antes.clics)} → {_n(c.despues.clics)} "
                 f"({_pct(c.d_clics)}) · pos. {_pos(c.antes.posicion)} → "
                 f"{_pos(c.despues.posicion)}")
    caen = [p for p in res["protegidas"] if p["estado"] == "cae"]
    L += ["", f"CONSULTAS PROTEGIDAS QUE CAEN MÁS DE {CAIDA_POSICIONES:.0f} PUESTOS ({len(caen)})"]
    for p in caen[:25]:
        L.append(f"{p['path']} · «{p['query']}»: pos. {_pos(p['pos_antes'])} → "
                 f"{_pos(p['pos_despues'])} (imp. {p['imp_antes']} → {p['imp_despues']})")
    if not caen:
        L.append("Ninguna.")
    pags = res["paginas"]
    L += ["", f"PÁGINAS QUE MÁS PIERDEN CLICS (≥ {MIN_IMPRESIONES_PAGINA} impresiones)"]
    for f in [x for x in pags if x["clics_despues"] < x["clics_antes"]][:TOP_PAGINAS]:
        L.append(_linea_pagina(f))
    L += ["", "PÁGINAS QUE MÁS GANAN CLICS"]
    for f in [x for x in reversed(pags) if x["clics_despues"] > x["clics_antes"]][:TOP_PAGINAS]:
        L.append(_linea_pagina(f))
    L += ["", "FUENTES Y VALIDACIÓN"]
    L += [
        f"- Qué se cambió y cuándo: content_revisions (reason 'headings humanos…'), "
        f"{res['n_cambios']} páginas, del {meta.get('primer_cambio')} al "
        f"{meta.get('ultimo_cambio')}.",
        f"- Métricas: API de Search Analytics de GSC, {meta.get('site')}, dataState final, "
        f"dimensiones page+date (totales) y page+query+date (consultas). Datos hasta el "
        f"{meta.get('fin')}, descargados el {meta.get('fetched_at')}.",
        f"- Ventanas: {7 * k} días antes del primer cambio de cada página y {7 * k} días "
        f"después del último. Control: {_fecha(vc_antes[0])}–{_fecha(vc_antes[1])} frente a "
        f"{_fecha(vc_despues[0])}–{_fecha(vc_despues[1])}.",
        "- Rastreo: API de inspección de URL de GSC (lastCrawlTime), misma descarga.",
        "- Las consultas anónimas no salen por consulta: los totales por página son mayores "
        "que la suma de sus consultas. Por eso los totales salen de page+date.",
    ]
    val = meta.get("validacion")
    if val:
        L.append(f"- Validación: suma de clics por página {_n(val['suma_paginas'])} frente a "
                 f"total del sitio por fecha {_n(val['total_sitio'])} en el mismo periodo "
                 f"({val['periodo']}). La API cuenta el total del sitio por propiedad y el de "
                 "página por URL, así que no tienen que coincidir.")
    return "\n".join(L)


def _linea_pagina(f: dict) -> str:
    rastreo = {True: "rastreada", False: "sin rastrear", None: "rastreo ?"}[f["rastreada"]]
    return (f"{f['path']} ({f['tipo']}, {rastreo}): clics {f['clics_antes']} → "
            f"{f['clics_despues']} · imp. {f['imp_antes']} → {f['imp_despues']} · pos. "
            f"{_pos(f['pos_antes'])} → {_pos(f['pos_despues'])}")


def informe_html(texto: str) -> str:
    return ("<div style=\"font-family:-apple-system,Helvetica,Arial,sans-serif;"
            "font-size:14px;line-height:1.5\"><pre style=\"white-space:pre-wrap;"
            f"font-family:inherit\">{_html.escape(texto)}</pre></div>")


def asunto(res: dict) -> str:
    cam, con = res["grupos"]["cambiadas"], res["grupos"]["control"]
    caen = sum(1 for p in res["protegidas"] if p["estado"] == "cae")
    return (f"Headings humanos · semana {res['semanas']}/4: clics {_pct(cam.d_clics)} "
            f"(control {_pct(con.d_clics)}) · {caen} consultas caen")
