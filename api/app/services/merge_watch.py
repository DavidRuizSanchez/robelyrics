"""¿Le costó algo a la página la fusión? Se mira a las 4 semanas de aplicarla.

`ranking_guard` impide la causa que está en nuestra mano (que la página deje de
decir lo que la hacía aparecer), pero el ranking lo decide Google. Así que se
comparan las 4 semanas de DESPUÉS de aplicar con las 4 de ANTES, en la misma
página.

Hasta el 23-11-2026 el «después» era el volcado semanal de GSC: 12 semanas que
acababan hoy, de las que casi dos tercios eran de ANTES de la fusión. Una caída
quedaba diluida en los datos viejos. Y una búsqueda que desaparecía del todo, o
bajaba de 10 impresiones, se saltaba sin decir nada. Ahora:

  - **Ventanas simétricas de 28 días**, sin el día del cambio (las fechas de la BD
    van en UTC y las de GSC en hora del Pacífico). Las baja la Mac, que es donde
    vive el token de GSC (`scripts.seo.merge_watch`), igual que el seguimiento de
    headings.
  - **Protegidas, con la vara de `ranking_guard`**: las que en el «antes» tenían
    clics o posición ≤ 20. Se avisa de las que caen más de `CAIDA_POSICIONES`
    puestos y de las que DESAPARECEN.
  - **Si la página se volvió a tocar** dentro de la ventana, se dice: la medición
    mezcla los dos cambios.

Solo AVISA. Revertir es un botón del panel (`content_revisions`) y lo pulsa una
persona: una caída de posiciones tiene muchas causas posibles (un core update,
la estacionalidad) y deshacer a ciegas podría tirar una mejora buena.
"""
from __future__ import annotations

import html as _html
import logging
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger(__name__)

DIAS = 28                    # largo de cada ventana
LAG_GSC = 3                  # GSC no tiene los últimos ~3 días
VENTANA = timedelta(days=90)  # más allá ya no se mira
CAIDA_POSICIONES = 5.0
MIN_IMPRESIONES_PROTEGIDA = 5   # en el «antes», para contar como protegida
MIN_IMPRESIONES_DESPUES = 3     # en el «después», para fiarse de su posición
MIN_IMPRESIONES_DESAPARECE = 10  # en el «antes», para avisar de que desaparece
TOP_PIERDEN = 3


def _d(x) -> date:
    return x if isinstance(x, date) and not isinstance(x, datetime) else (
        x.date() if isinstance(x, datetime) else date.fromisoformat(str(x)[:10]))


def ventanas(aplicada) -> tuple[tuple[date, date], tuple[date, date]]:
    """(antes, después) como pares de fechas inclusivas. El día del cambio no cuenta."""
    d0 = _d(aplicada)
    return ((d0 - timedelta(days=DIAS), d0 - timedelta(days=1)),
            (d0 + timedelta(days=1), d0 + timedelta(days=DIAS)))


def lista_para_medir(aplicada, hoy: date | None = None) -> bool:
    """GSC ya tiene las 4 semanas de después enteras."""
    hoy = hoy or datetime.now(UTC).date()
    return ventanas(aplicada)[1][1] <= hoy - timedelta(days=LAG_GSC)


def pendientes(db, hoy: date | None = None) -> list[dict]:
    """Las fusiones aplicadas con las 4 semanas de después completas y sin mirar.

    Es lo que exporta prod para que la Mac sepa qué bajar de GSC.
    """
    from app.db.models import SeoOpportunity

    hoy = hoy or datetime.now(UTC).date()
    filas = (db.query(SeoOpportunity)
             .filter(SeoOpportunity.action == "merge", SeoOpportunity.status == "applied",
                     SeoOpportunity.applied_at.isnot(None))
             .order_by(SeoOpportunity.applied_at).all())
    out = []
    for o in filas:
        if (o.draft_notes or {}).get("watch"):
            continue
        if _d(o.applied_at) < hoy - VENTANA or not lista_para_medir(o.applied_at, hoy):
            continue
        antes, despues = ventanas(o.applied_at)
        out.append({"id": o.id, "path": o.path, "aplicada": _d(o.applied_at).isoformat(),
                    "antes": [antes[0].isoformat(), antes[1].isoformat()],
                    "despues": [despues[0].isoformat(), despues[1].isoformat()]})
    return out


def comparar(antes: list[dict], despues: list[dict]) -> dict:
    """Protegidas que caen y protegidas que desaparecen, con la vara de `ranking_guard`."""
    por_query = {q.get("query"): q for q in despues or []}
    caidas, desaparecen = [], []
    for b in antes or []:
        imp_antes = int(b.get("impressions") or 0)
        protegida = (int(b.get("clicks") or 0) > 0
                     or float(b.get("position") or 100) <= 20)
        if not protegida or imp_antes < MIN_IMPRESIONES_PROTEGIDA:
            continue
        actual = por_query.get(b.get("query"))
        if not actual or int(actual.get("impressions") or 0) == 0:
            if imp_antes >= MIN_IMPRESIONES_DESAPARECE:
                desaparecen.append({"query": b["query"], "antes": b.get("position"),
                                    "impressions_antes": imp_antes})
            continue
        if int(actual.get("impressions") or 0) < MIN_IMPRESIONES_DESPUES:
            continue
        delta = float(actual.get("position") or 0) - float(b.get("position") or 0)
        if delta > CAIDA_POSICIONES:
            caidas.append({"query": b["query"], "antes": b.get("position"),
                           "ahora": actual.get("position"), "delta": round(delta, 1),
                           "impressions": actual.get("impressions")})
    # Las que más impresiones pierden, con su posición: dicen si la página bajó
    # (cambia la posición) o si esas búsquedas se hacen menos (no cambia). En
    # /extremoduro, -37 % de impresiones con «de dónde son» en la 10 antes y después.
    idx_a = {q.get("query"): q for q in antes or []}
    perdidas = []
    for query in set(idx_a) | set(por_query):
        a, d = idx_a.get(query) or {}, por_query.get(query) or {}
        delta = int(d.get("impressions") or 0) - int(a.get("impressions") or 0)
        if delta < 0:
            perdidas.append({"query": query, "delta": delta,
                             "antes": a.get("position"), "ahora": d.get("position")})
    perdidas.sort(key=lambda x: (x["delta"], x["query"]))
    return {"caidas": caidas, "desaparecen": desaparecen, "pierden": perdidas[:TOP_PIERDEN]}


def _retoques(db, opp, despues: tuple[date, date]) -> list[str]:
    """Otros cambios en la MISMA página dentro de la ventana de después."""
    from sqlalchemy import text

    filas = db.execute(text(
        "select created_at, reason from content_revisions "
        "where path = :p and created_at::date between :a and :b order by created_at"),
        {"p": opp.path, "a": despues[0], "b": despues[1]}).fetchall()
    return [f"{_d(c):%d-%m-%Y} ({(r or 'sin motivo')[:60]})" for c, r in filas]


def _totales(pagina: dict | None) -> tuple[int, int]:
    pagina = pagina or {}
    return int(pagina.get("clicks") or 0), int(pagina.get("impressions") or 0)


def revisar(db, gsc: dict, *, notify: bool = True, hoy: date | None = None) -> list[dict]:
    """Mide las fusiones pendientes con las ventanas que bajó la Mac.

    `gsc`: {str(id): {"antes": {"consultas": [...], "pagina": {...}}, "despues": {...}}}.
    Lo que no trae ventanas no se marca como mirado: se mirará cuando las traiga.
    """
    from app.db.models import SeoOpportunity

    informes = []
    for p in pendientes(db, hoy):
        datos = (gsc or {}).get(str(p["id"]))
        if not datos:
            logger.info("[merge-watch] %s: sin ventanas de GSC (las baja la Mac)", p["path"])
            continue
        opp = db.get(SeoOpportunity, p["id"])
        antes_q = (datos.get("antes") or {}).get("consultas") or []
        despues_q = (datos.get("despues") or {}).get("consultas") or []
        res = comparar(antes_q, despues_q)
        propias = {(q.get("query") or "") for q in opp.queries or []}
        idx_a = {q.get("query"): q for q in antes_q}
        idx_d = {q.get("query"): q for q in despues_q}
        objetivo = [{"query": q, "antes": idx_a.get(q), "despues": idx_d.get(q)}
                    for q in sorted(propias) if q]
        _, (d_ini, d_fin) = ventanas(opp.applied_at)
        retoques = _retoques(db, opp, (d_ini, d_fin))
        pagina = {"antes": _totales((datos.get("antes") or {}).get("pagina")),
                  "despues": _totales((datos.get("despues") or {}).get("pagina")),
                  "sitio_antes": _totales((datos.get("antes") or {}).get("sitio")),
                  "sitio_despues": _totales((datos.get("despues") or {}).get("sitio"))}
        notas = dict(opp.draft_notes or {})
        notas["watch"] = {"checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
                          "antes": p["antes"], "despues": p["despues"], **res,
                          "objetivo": objetivo, "pagina": pagina, "retoques": retoques}
        opp.draft_notes = notas
        informes.append({"opp": opp, "ventanas": p, **res, "objetivo": objetivo,
                         "pagina": pagina, "retoques": retoques})
    db.commit()
    if notify and informes:
        _avisar(informes)
    return informes


def _pct(a: int, b: int) -> str:
    return f"{(b - a) / a * 100:+.0f} %" if a else "n/d"


def _q(q: dict | None) -> str:
    if not q:
        return "no aparece"
    return f"pos {q.get('position')} · {q.get('impressions')} impr. · {q.get('clicks', 0)} clics"


def texto_informe(informes: list[dict], site: str) -> tuple[str, str]:
    """(asunto, cuerpo). Aparte para poder probarlo sin mandar nada."""
    lineas = [f"Cada fusión, sus {DIAS} días de después frente a sus {DIAS} de antes "
              "(Search Console, misma página, sin el día del cambio).", ""]
    hay_problema = False
    for inf in informes:
        o, v = inf["opp"], inf["ventanas"]
        lineas.append(f"· {site}{o.path} (aplicada {_d(o.applied_at):%d-%m-%Y})")
        lineas.append(f"    antes {v['antes'][0]}..{v['antes'][1]} · "
                      f"después {v['despues'][0]}..{v['despues'][1]}")
        (c0, i0), (c1, i1) = inf["pagina"]["antes"], inf["pagina"]["despues"]
        lineas.append(f"    página: {c0} → {c1} clics ({_pct(c0, c1)}), "
                      f"{i0} → {i1} impresiones ({_pct(i0, i1)})")
        if inf["pagina"].get("sitio_antes"):
            (sc0, si0), (sc1, si1) = inf["pagina"]["sitio_antes"], inf["pagina"]["sitio_despues"]
            lineas.append(f"    todo el sitio, mismas fechas: {sc0} → {sc1} clics "
                          f"({_pct(sc0, sc1)}), {si0} → {si1} impresiones ({_pct(si0, si1)})")
        if inf["caidas"] or inf["desaparecen"]:
            hay_problema = True
            for c in inf["caidas"]:
                lineas.append(f"    ⚠ cae «{c['query']}»: pos {c['antes']} → {c['ahora']} "
                              f"({c['impressions']} impr. después)")
            for c in inf["desaparecen"]:
                lineas.append(f"    ⚠ desaparece «{c['query']}»: estaba en pos {c['antes']} "
                              f"con {c['impressions_antes']} impr.")
        else:
            lineas.append(f"    ninguna búsqueda protegida cae más de {CAIDA_POSICIONES:g} "
                          "puestos ni desaparece")
        if inf.get("pierden"):
            lineas.append("    las que más impresiones pierden: " + "; ".join(
                f"«{x['query']}» {x['delta']:+d} (pos {x['antes'] or '—'} → "
                f"{x['ahora'] or 'no aparece'})" for x in inf["pierden"]))
        if inf["objetivo"]:
            lineas.append("    lo que la fusión quería ganar:")
            for ob in inf["objetivo"]:
                lineas.append(f"      «{ob['query']}»: antes {_q(ob['antes'])}; "
                              f"después {_q(ob['despues'])}")
        if inf["retoques"]:
            lineas.append("    ojo: la página se volvió a tocar dentro de la ventana ("
                          + "; ".join(inf["retoques"][:3])
                          + "), así que la medición mezcla los cambios")
        lineas.append("")
    lineas += ["Revertir (si hiciera falta) es un botón en "
               f"{site}/biblioteca/admin/seo/oportunidades. Nada se ha tocado solo."]
    asunto = ("⚠️ Una fusión SEO ha perdido posiciones" if hay_problema
              else "📈 Cómo van las fusiones SEO a las 4 semanas")
    return asunto, "\n".join(lineas)


def _avisar(informes: list[dict]) -> None:
    from app.config import get_settings
    from app.services.email import EmailError, send_email

    to = get_settings().admin_email
    if not to:
        return
    asunto, texto = texto_informe(informes, get_settings().site_url.rstrip("/"))
    try:
        send_email(to=to, subject=asunto, html=f"<pre>{_html.escape(texto)}</pre>",
                   text=texto)
    except EmailError as exc:
        logger.error("[merge-watch] no se pudo avisar: %s", exc)
