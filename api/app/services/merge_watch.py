"""¿Le costó algo a la página la fusión? Se mira a las 4 semanas de aplicarla.

`ranking_guard` impide la causa que está en nuestra mano (que la página deje de
decir lo que la hacía aparecer), pero el ranking lo decide Google. Así que cada
fusión aplicada guarda su línea base —las consultas protegidas con su posición—
y, cuando llega un volcado de GSC con 4 semanas de recorrido, se compara.

Solo AVISA. Revertir es un botón del panel (`content_revisions`) y lo pulsa una
persona: una caída de posiciones tiene muchas causas posibles (un core update,
la estacionalidad) y deshacer a ciegas podría tirar una mejora buena.
"""
from __future__ import annotations

import html as _html
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

ESPERA = timedelta(days=28)
VENTANA = timedelta(days=90)
CAIDA_POSICIONES = 5.0
MIN_IMPRESIONES = 10


def comparar(base: list[dict], ahora: list[dict]) -> list[dict]:
    """Las consultas protegidas que han caído más de CAIDA_POSICIONES puestos."""
    por_query = {q.get("query"): q for q in ahora or []}
    caidas = []
    for b in base or []:
        actual = por_query.get(b.get("query"))
        if not actual or b.get("position") is None:
            continue
        if int(actual.get("impressions") or 0) < MIN_IMPRESIONES:
            continue
        delta = float(actual.get("position") or 0) - float(b["position"])
        if delta > CAIDA_POSICIONES:
            caidas.append({"query": b["query"], "antes": b["position"],
                           "ahora": actual.get("position"), "delta": round(delta, 1),
                           "impressions": actual.get("impressions")})
    return caidas


def revisar(db, pages: dict, period: str | None, *, notify: bool = True) -> list[dict]:
    """Revisa las fusiones aplicadas hace 4–13 semanas que aún no se han mirado."""
    from app.db.models import SeoOpportunity

    ahora = datetime.now(UTC)
    filas = (db.query(SeoOpportunity)
             .filter(SeoOpportunity.action == "merge", SeoOpportunity.status == "applied",
                     SeoOpportunity.applied_at <= ahora - ESPERA,
                     SeoOpportunity.applied_at >= ahora - VENTANA).all())
    informes = []
    for opp in filas:
        notas = dict(opp.draft_notes or {})
        if notas.get("watch"):
            continue
        actuales = pages.get(opp.path) or []
        caidas = comparar(notas.get("protegidas_detalle") or [], actuales)
        propias = {(c.get("query") or "") for c in opp.queries or []}
        nuevas = [{"query": q.get("query"), "position": q.get("position"),
                   "impressions": q.get("impressions")}
                  for q in actuales if (q.get("query") or "") in propias]
        notas["watch"] = {"checked_at": ahora.isoformat(timespec="seconds"),
                          "period": period, "caidas": caidas, "nuevas": nuevas}
        opp.draft_notes = notas
        informes.append({"opp": opp, "caidas": caidas, "nuevas": nuevas})
    db.commit()
    if notify and informes:
        _avisar(informes, period)
    return informes


def _avisar(informes: list[dict], period: str | None) -> None:
    from app.config import get_settings
    from app.services.email import EmailError, send_email

    to = get_settings().admin_email
    if not to:
        return
    site = get_settings().site_url.rstrip("/")
    lineas = [f"Fusiones aplicadas hace 4+ semanas, contra el volcado GSC {period or ''}:", ""]
    hay_caidas = False
    for inf in informes:
        o = inf["opp"]
        lineas.append(f"· {site}{o.path} (aplicada {o.applied_at:%d-%m-%Y})")
        if inf["caidas"]:
            hay_caidas = True
            for c in inf["caidas"]:
                lineas.append(f"    ⚠ «{c['query']}»: pos {c['antes']} → {c['ahora']} "
                              f"({c['impressions']} impr.)")
        else:
            lineas.append("    ninguna búsqueda protegida ha caído más de "
                          f"{CAIDA_POSICIONES:g} puestos")
        for n in inf["nuevas"]:
            lineas.append(f"    + «{n['query']}»: pos {n['position']} "
                          f"({n['impressions']} impr.)")
    lineas += ["", "Revertir (si hiciera falta) es un botón en "
               f"{site}/biblioteca/admin/seo/oportunidades. Nada se ha tocado solo."]
    asunto = ("⚠️ Una fusión SEO ha perdido posiciones" if hay_caidas
              else "📈 Cómo van las fusiones SEO a las 4 semanas")
    texto = "\n".join(lineas)
    try:
        send_email(to=to, subject=asunto, html=f"<pre>{_html.escape(texto)}</pre>",
                   text=texto)
    except EmailError as exc:
        logger.error("[merge-watch] no se pudo avisar: %s", exc)
