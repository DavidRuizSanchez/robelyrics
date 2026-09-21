"""Los dos correos del circuito de aprobación SEO.

Fase 1 (`send_detected`): qué le falta a cada URL y un botón que autoriza a
PREPARAR el borrador. Fase 2 (`send_drafted`): el antes/después de lo preparado y
el botón que lo publica.

Dos decisiones que conviene no deshacer:

- **El correo enseña el diagnóstico, no una orden.** Por cada URL van sus
  consultas con impresiones, clics y posición reales, de un volcado fechado de
  GSC. Sin eso, aprobar es firmar a ciegas.
- **Se cuenta también lo que NO se va a tocar.** Las consultas ya cubiertas en
  cuerpo y metadata son el grupo más grande (12.176 impresiones el 21-09-2026) y
  no admiten acción de contenido. Callarlas haría parecer que el sitio tiene
  menos margen del que tiene; fabricarles una tarea sería inventarse trabajo.
"""
from __future__ import annotations

import html as _html
import logging

logger = logging.getLogger(__name__)

_ACCENT = "#a83a3a"
_PAPEL = "#ede4d3"
_MONO = "'Courier New',monospace"


def _site() -> str:
    from app.config import get_settings

    return get_settings().site_url.rstrip("/")


def _cta(url: str, label: str, *, principal: bool = True) -> str:
    color = _ACCENT if principal else "rgba(237,228,211,0.45)"
    return (
        f'<a href="{url}" style="display:inline-block;padding:12px 24px;'
        f'border:1px solid {color};color:{color};text-decoration:none;'
        f'font-family:{_MONO};font-size:11px;letter-spacing:3px;'
        f'text-transform:uppercase;margin:0 6px 8px 0;">{label}</a>'
    )


def _link_accion(ids: list[int], accion: str) -> str:
    from app.services.auth import create_seo_opportunity_token

    token = create_seo_opportunity_token(ids, accion)
    return f"{_site()}/api/public/seo-opportunity?token={token}"


def _etiqueta(texto: str) -> str:
    return (
        f'<p style="font-family:{_MONO};font-size:11px;letter-spacing:3px;'
        f'text-transform:uppercase;color:{_ACCENT};margin:28px 0 10px;">{texto}</p>'
    )


def _marco(titulo: str, subtitulo: str, cuerpo: str, pie: str = "") -> str:
    return f"""\
<!doctype html>
<html lang="es">
<body style="margin:0;padding:32px;background:#0d0b0a;color:{_PAPEL};font-family:Georgia,serif;">
  <div style="max-width:660px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:{_MONO};font-size:10px;letter-spacing:3px;text-transform:uppercase;color:{_ACCENT};margin:0 0 12px;">
      entre interiores · oportunidades seo
    </p>
    <h1 style="font-family:Georgia,serif;font-size:25px;color:{_PAPEL};margin:0 0 8px;line-height:1.25;">{titulo}</h1>
    <p style="font-family:Georgia,serif;font-style:italic;color:rgba(237,228,211,0.6);font-size:14px;margin:0 0 8px;line-height:1.6;">{subtitulo}</p>
    {cuerpo}
    {pie}
  </div>
</body>
</html>"""


def _fila_queries(queries: list[dict], n: int = 4) -> str:
    lis = "".join(
        f'<li style="font-family:Georgia,serif;font-size:14px;color:rgba(237,228,211,0.8);margin:0 0 4px;">'
        f'«{_html.escape(str(q.get("query", "")))}» '
        f'<span style="font-family:{_MONO};font-size:11px;color:rgba(237,228,211,0.45);">'
        f'pos {float(q.get("position") or 0):.1f} · {int(q.get("impressions") or 0)} imp · '
        f'{int(q.get("clicks") or 0)} clic</span></li>'
        for q in (queries or [])[:n]
    )
    return f'<ul style="list-style:none;padding:0;margin:6px 0 0;">{lis}</ul>'


# --------------------------------------------------------------------------- #
# Fase 1 — el diagnóstico
# --------------------------------------------------------------------------- #
def send_detected(opps: list, *, covered: dict | None = None) -> bool:
    """Correo con lo detectado. Cada URL trae su botón de «preparar borrador»."""
    from app.config import get_settings
    from app.services.email import EmailError, send_email

    to = get_settings().admin_email
    if not to or not opps:
        return False
    site = _site()

    def bloque(o) -> str:
        etiqueta = ("el cuerpo ya lo responde, el title y la description no lo prometen"
                    if o.action == "meta"
                    else "la página no lo cubre; se ampliará sin tocar lo que ya dice")
        return (
            f'<div style="margin:0 0 20px;padding:0 0 16px;border-bottom:1px solid rgba(237,228,211,0.06);">'
            f'<a href="{site}{o.path}" style="font-family:Georgia,serif;font-size:17px;color:{_PAPEL};text-decoration:none;">{_html.escape(o.path)}</a> '
            f'<span style="font-family:{_MONO};font-size:11px;color:rgba(237,228,211,0.45);">{o.impressions} imp</span>'
            f'<div style="font-family:Georgia,serif;font-style:italic;font-size:13px;color:rgba(237,228,211,0.5);margin:4px 0 0;">{etiqueta}</div>'
            f"{_fila_queries(o.queries or [])}"
            f'<div style="margin:10px 0 0;">'
            f'<a href="{_link_accion([o.id], "approve")}" style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:{_ACCENT};text-decoration:none;">→ preparar borrador</a>'
            f'<a href="{_link_accion([o.id], "discard")}" style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(237,228,211,0.35);text-decoration:none;margin-left:18px;">descartar</a>'
            f"</div></div>"
        )

    metas = [o for o in opps if o.action == "meta"]
    cuerpos = [o for o in opps if o.action == "body"]
    partes = []
    if metas:
        partes.append(_etiqueta(f"falta promesa · solo title y description ({len(metas)})"))
        partes += [bloque(o) for o in metas]
    if cuerpos:
        partes.append(_etiqueta(f"falta contenido · se amplía con material del corpus ({len(cuerpos)})"))
        partes += [bloque(o) for o in cuerpos]

    nota = ""
    if covered and covered.get("queries"):
        nota = (
            f'<p style="font-family:Georgia,serif;font-size:13px;font-style:italic;'
            f'color:rgba(237,228,211,0.45);margin:24px 0 0;line-height:1.6;">'
            f'Otras {covered["queries"]} consultas ({covered["impressions"]} impresiones) '
            f'ya están respondidas en el cuerpo Y prometidas en la metadata. Ahí no falta '
            f'contenido: falta posición, y no hay nada honesto que escribir.</p>'
        )

    todos = _link_accion([o.id for o in opps], "approve")
    pie = (
        f'<div style="margin:28px 0 0;padding:18px 0 0;border-top:1px solid rgba(237,228,211,0.08);text-align:center;">'
        f'{_cta(todos, "preparar todos los borradores")}'
        f'{_cta(f"{site}/biblioteca/admin/seo/oportunidades", "ver la cola", principal=False)}'
        f"</div>{nota}"
    )
    periodo = next((o.period for o in opps if o.period), None)
    html = _marco(
        f"{len(opps)} oportunidad{'es' if len(opps) != 1 else ''} SEO con evidencia",
        "Ningún clic de aquí publica nada: prepara el borrador y te llega un segundo "
        f"correo con el antes/después. Datos de Search Console{f', {periodo}' if periodo else ''}.",
        "".join(partes), pie,
    )
    texto = [f"{len(opps)} oportunidad{'es' if len(opps) != 1 else ''} SEO "
             f"detectada{'s' if len(opps) != 1 else ''}.", ""]
    for o in opps:
        texto.append(f"· {o.path} [{o.action}] {o.impressions} imp")
        for q in (o.queries or [])[:3]:
            texto.append(f"    «{q.get('query')}» pos {q.get('position')} · "
                         f"{q.get('impressions')} imp · {q.get('clicks')} clic")
    texto += ["", f"Preparar todos los borradores: {todos}"]
    try:
        send_email(to=to,
                   subject=f"🔍 {len(opps)} oportunidades SEO listas para aprobar",
                   html=html, text="\n".join(texto))
        return True
    except EmailError as exc:
        logger.error("[seo-opp] fallo enviando el correo de detección: %s", exc)
        return False


# --------------------------------------------------------------------------- #
# Fase 2 — el antes/después
# --------------------------------------------------------------------------- #
def _diff_cuerpo(o) -> str:
    """Lo que la ampliación AÑADE. `augment_entity` añade al final sin reescribir,
    así que la cola del texto nuevo es exactamente lo que hay que revisar."""
    antes, despues = o.before_body or "", o.draft_body or ""
    if despues.startswith(antes[: max(0, len(antes) - 200)]) and len(despues) > len(antes):
        nuevo = despues[len(antes):].strip()
    else:
        nuevo = despues[-2500:]
    notas = o.draft_notes or {}
    heads = ", ".join(notas.get("added_headings") or []) or "—"
    rigor = notas.get("rigor") or {}
    sello = ""
    if rigor:
        sello = (f'<div style="font-family:{_MONO};font-size:10px;color:rgba(237,228,211,0.4);'
                 f'margin:6px 0 0;">rigor {rigor.get("before_score")} → {rigor.get("score")} '
                 f'({rigor.get("verdict")}) · {len(antes)} → {len(despues)} caracteres</div>')
    return (
        f'<div style="font-family:{_MONO};font-size:10px;letter-spacing:2px;'
        f'text-transform:uppercase;color:rgba(237,228,211,0.45);margin:8px 0 4px;">'
        f'secciones nuevas: {_html.escape(heads)}</div>{sello}'
        f'<div style="font-family:Georgia,serif;font-size:14px;line-height:1.6;'
        f'color:rgba(237,228,211,0.85);background:rgba(237,228,211,0.03);'
        f'padding:14px;margin:8px 0 0;white-space:pre-wrap;">{_html.escape(nuevo[:2200])}</div>'
    )


def _diff_meta(o) -> str:
    filas = []
    for etiqueta, antes, despues in (
        ("title", o.before_title, o.draft_title),
        ("description", o.before_description, o.draft_description),
    ):
        if not despues:
            continue
        filas.append(
            f'<div style="margin:0 0 12px;">'
            f'<div style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(237,228,211,0.4);">{etiqueta}</div>'
            f'<div style="font-family:Georgia,serif;font-size:14px;color:rgba(237,228,211,0.45);text-decoration:line-through;margin:2px 0;">{_html.escape(antes or "(vacío)")}</div>'
            f'<div style="font-family:Georgia,serif;font-size:15px;color:{_PAPEL};margin:2px 0;">{_html.escape(despues)} '
            f'<span style="font-family:{_MONO};font-size:10px;color:rgba(237,228,211,0.4);">{len(despues)}c</span></div>'
            f"</div>"
        )
    return "".join(filas)


def send_drafted(opps: list, *, sin_material: list | None = None) -> bool:
    """Correo con el antes/después de cada borrador y el botón que publica.

    `sin_material` son las que se intentaron y no dieron nada (el corpus no
    respaldaba la ampliación, la metadata propuesta no pasó las guardas). Van al
    pie a propósito: si se aprueban cinco y llega un correo con una, lo que no se
    cuenta parece perdido, y a las otras cuatro no las mira nadie nunca más.
    """
    from app.config import get_settings
    from app.services.email import EmailError, send_email

    to = get_settings().admin_email
    # Aunque no salga ningún borrador hay que escribir: si se aprueban cinco y no
    # llega nada, el circuito parece roto y lo intentado se pierde de vista.
    if not to or (not opps and not sin_material):
        return False
    site = _site()

    def bloque(o) -> str:
        cuerpo = _diff_meta(o) if o.action == "meta" else _diff_cuerpo(o)
        return (
            f'<div style="margin:0 0 24px;padding:0 0 18px;border-bottom:1px solid rgba(237,228,211,0.06);">'
            f'<a href="{site}{o.path}" style="font-family:Georgia,serif;font-size:17px;color:{_PAPEL};text-decoration:none;">{_html.escape(o.path)}</a>'
            f'<div style="font-family:Georgia,serif;font-style:italic;font-size:13px;color:rgba(237,228,211,0.5);margin:4px 0 8px;">'
            f'por: {_html.escape(o.gap_hint or "")}</div>'
            f"{cuerpo}"
            f'<div style="margin:12px 0 0;">'
            f'<a href="{_link_accion([o.id], "apply")}" style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:{_ACCENT};text-decoration:none;">→ publicar este</a>'
            f'<a href="{_link_accion([o.id], "discard")}" style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(237,228,211,0.35);text-decoration:none;margin-left:18px;">descartar</a>'
            f"</div></div>"
        )

    todos = _link_accion([o.id for o in opps], "apply") if opps else ""
    pie = "" if not opps else (
        f'<div style="margin:28px 0 0;padding:18px 0 0;border-top:1px solid rgba(237,228,211,0.08);text-align:center;">'
        f'{_cta(todos, "publicar todos")}'
        f'{_cta(f"{site}/biblioteca/admin/seo/oportunidades", "revisar en el panel", principal=False)}'
        f"</div>"
    )
    nota = ""
    if sin_material:
        lis = "".join(
            f'<li style="font-family:Georgia,serif;font-size:13px;color:rgba(237,228,211,0.5);margin:0 0 4px;">'
            f'{_html.escape(o.path)} — {_html.escape((o.error or "sin material")[:150])}</li>'
            for o in sin_material
        )
        nota = (
            f'<div style="margin:24px 0 0;padding:16px 0 0;border-top:1px solid rgba(237,228,211,0.08);">'
            f'<p style="font-family:{_MONO};font-size:10px;letter-spacing:2px;text-transform:uppercase;'
            f'color:rgba(237,228,211,0.4);margin:0 0 8px;">se intentaron y no salió nada ({len(sin_material)})</p>'
            f'<ul style="list-style:none;padding:0;margin:0;">{lis}</ul>'
            f'<p style="font-family:Georgia,serif;font-style:italic;font-size:13px;'
            f'color:rgba(237,228,211,0.4);margin:8px 0 0;">No se ha tocado nada en el sitio. '
            f'Escribirlas igualmente sería rellenar con generalidades.</p></div>'
        )
    titulo = (
        f"{len(opps)} borrador{'es' if len(opps) != 1 else ''} SEO esperando el visto bueno"
        if opps else "Ningún borrador SEO ha salido adelante"
    )
    subtitulo = (
        "Esto es lo que se publicaría, tal cual. Nada está en el sitio todavía."
        if opps else
        "Se intentaron, pero no había material que sostuviera el cambio. Nada se ha tocado."
    )
    html = _marco(
        titulo, subtitulo,
        "".join(bloque(o) for o in opps), pie + nota,
    )
    texto = [f"{len(opps)} borrador{'es' if len(opps) != 1 else ''} SEO preparado"
             f"{'s' if len(opps) != 1 else ''}.", ""]
    for o in opps:
        texto.append(f"· {o.path} [{o.action}]")
        if o.action == "meta":
            texto.append(f"    title: {o.before_title} → {o.draft_title or '(sin cambio)'}")
            texto.append(f"    desc:  {o.before_description} → {o.draft_description or '(sin cambio)'}")
        else:
            heads = ", ".join((o.draft_notes or {}).get("added_headings") or [])
            texto.append(f"    secciones nuevas: {heads}")
    for o in sin_material or []:
        texto.append(f"· (sin material) {o.path}: {(o.error or '')[:150]}")
    if todos:
        texto += ["", f"Publicar todos: {todos}"]
    try:
        send_email(to=to,
                   subject=(f"✍️ {len(opps)} borrador{'es' if len(opps) != 1 else ''} SEO para publicar"
                            if opps else "✍️ Ningún borrador SEO ha salido adelante"),
                   html=html, text="\n".join(texto))
        return True
    except EmailError as exc:
        logger.error("[seo-opp] fallo enviando el correo de borradores: %s", exc)
        return False
