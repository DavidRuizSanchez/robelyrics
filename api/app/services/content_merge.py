"""Fundir una propuesta del blog con una página que ya existe.

Elegir «ampliar /extremoduro» en el panel o en el correo NO escribe nada: crea una
`SeoOpportunity` con `action="merge"` ya aprobada y la manda a preparar. A partir de
ahí es el circuito de dos fases de siempre (`seo_opportunities`): el borrador llega
con su antes/después y solo un segundo clic lo publica.

El motor que escribe el borrador es `scripts/seo/merge_deep.py`.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.services import content_placement

logger = logging.getLogger(__name__)


class MergeError(Exception):
    """Algo impide fundir; el mensaje se enseña tal cual en el panel y el correo."""


def _kw_dicts(proposal) -> list[dict]:
    return [dict(k) for k in (proposal.keywords or []) if isinstance(k, dict)]


def recalcular_objetivo(proposal) -> None:
    """La keyword objetivo pasa a la ACTIVA de más volumen, con su huella.

    Al fundir una parte de la propuesta o desactivar keywords, lo que queda es otra
    propuesta: si su keyword objetivo era la que se ha ido, el dedup (`content_key`)
    y el panel tienen que hablar de la que se queda.
    """
    from app.services.keyword_research import kw_slug

    activas = [k for k in _kw_dicts(proposal) if not k.get("excluded")]
    if not activas:
        return
    actual = (proposal.target_keyword or "").lower()
    if any((k.get("keyword") or "").lower() == actual for k in activas):
        return
    mejor = max(activas, key=lambda k: int(k.get("volume") or 0))
    proposal.target_keyword = (mejor.get("keyword") or "")[:160]
    proposal.target_keyword_slug = kw_slug(proposal.target_keyword)
    proposal.search_volume = int(mejor.get("volume") or 0)
    if proposal.kind == "evergreen":
        proposal.content_key = f"evergreen:{proposal.target_keyword_slug}"


def excluir_keywords(proposal, excluidas: list[str]) -> None:
    """Marca como desactivadas estas keywords (y reactiva el resto). No borra nada.

    Petición de David (19-10-2026): «canción de amor» es demasiado genérica y tiene
    que poder quitarse a mano. Queda en la propuesta, tachada, y `keyword_research`
    no la vuelve a proponer.
    """
    fuera = {k.lower() for k in excluidas}
    kws = _kw_dicts(proposal)
    # Las que se fueron a otra página por una fusión siguen fuera pase lo que pase.
    activas_tras = [k for k in kws if not k.get("merged")
                    and (k.get("keyword") or "").lower() not in fuera]
    if not activas_tras:
        raise MergeError("no se pueden desactivar todas las keywords: rechaza la propuesta")
    for k in kws:
        if k.get("merged"):
            continue
        if (k.get("keyword") or "").lower() in fuera:
            k["excluded"] = True
        else:
            k.pop("excluded", None)
    proposal.keywords = kws
    recalcular_objetivo(proposal)


def start_merge(db, proposal, target: str, keywords: list[str] | None = None):
    """Deja la oportunidad `approved` y saca esas keywords de la propuesta.

    Si quedan keywords activas, la propuesta sigue `proposed` con ellas (son otro
    grupo: otra página o contenido nuevo). Si no queda ninguna, pasa a `merged`.
    No lanza la preparación: eso lo hace quien llama (en segundo plano), porque un
    borrador tarda minutos y Cloudflare corta a los 100 s.
    """
    from app.db.models import SeoContent, SeoOpportunity

    if proposal.status not in ("proposed", "approved"):
        raise MergeError(f"la propuesta está en estado «{proposal.status}»")
    cand = content_placement.candidate_for_target(db, target)
    if cand is None:
        raise MergeError("esa página ya no está publicada o no admite ampliación")

    viva = (
        db.query(SeoOpportunity)
        .filter(SeoOpportunity.path == cand.path, SeoOpportunity.action == "merge",
                SeoOpportunity.status.in_(["detected", "approved", "drafted", "failed"]))
        .first()
    )
    if viva:
        # Dos borradores sobre la misma página parten del mismo «antes»: aplicar uno
        # invalidaría el otro. Se encadenan, no se cruzan.
        raise MergeError(f"ya hay una ampliación en curso de {cand.path} "
                         f"(#{viva.id}, {viva.status}); termina esa primero")

    activas = content_placement.proposal_keywords(proposal)
    elegidas = [k for k in (keywords or activas) if k.lower() in {a.lower() for a in activas}]
    if not elegidas:
        raise MergeError("ninguna de esas keywords está activa en la propuesta")

    # La evidencia que viaja con la oportunidad: las keywords con su dato GSC sobre
    # ESA página si lo tiene, y si no, su volumen de búsqueda.
    placement = proposal.placement or {}
    previo = next((c for g in content_placement.grupos(placement)
                   for c in g.get("candidates") or [] if c.get("target") == target), {})
    gsc_por_query = {q["query"]: q for q in previo.get("gsc_queries") or []}
    vol = {(k.get("keyword") or "").lower(): int(k.get("volume") or 0)
           for k in _kw_dicts(proposal)}
    queries = []
    for kw in elegidas:
        g = gsc_por_query.get(kw) or {}
        queries.append({"query": kw, "impressions": int(g.get("impressions") or 0),
                        "position": g.get("position"), "volume": vol.get(kw.lower(), 0)})

    seo_content_id = None
    if target.startswith("ficha:"):
        sc = db.get(SeoContent, int(target.split(":", 1)[1]))
        seo_content_id = sc.id if sc else None

    ahora = datetime.now(UTC)
    opp = SeoOpportunity(
        path=cand.path, action="merge", status="approved",
        entity_type=cand.entity_type or "page", entity_id=cand.entity_id or 0,
        seo_content_id=seo_content_id, proposal_id=proposal.id,
        queries=queries, impressions=int(previo.get("gsc_impressions") or 0),
        period=placement.get("period"),
        gap_hint=f"{proposal.title}. {proposal.angle or ''}".strip()[:1000],
        approved_at=ahora,
    )
    db.add(opp)
    db.flush()

    elegidas_l = {k.lower() for k in elegidas}
    kws = _kw_dicts(proposal)
    for k in kws:
        if (k.get("keyword") or "").lower() in elegidas_l:
            k["excluded"] = True
            k["merged"] = cand.path
            k["merge_opportunity_id"] = opp.id
    proposal.keywords = kws
    proposal.merge_target = target
    proposal.merge_opportunity_id = opp.id
    if content_placement.proposal_keywords(proposal):
        recalcular_objetivo(proposal)
    else:
        proposal.status = "merged"
        proposal.scheduled_for = None
    db.commit()
    logger.info("[merge] propuesta #%s → %s con %s (oportunidad #%s)", proposal.id,
                cand.path, elegidas, opp.id)
    return opp


def aplicar_plan(db, proposal, elecciones: list[dict]) -> list:
    """Ejecuta el reparto elegido: [{keywords, target}] con target «ficha:N» /
    «post:N» (fundir), «new» (se quedan para un post) o «skip» (se omiten).

    Devuelve las oportunidades creadas, para prepararlas en segundo plano.
    """
    opps = []
    omitidas = [kw for e in elecciones if e.get("target") == "skip"
                for kw in e.get("keywords") or []]
    for e in elecciones:
        t = e.get("target")
        if t and t not in ("new", "skip"):
            opps.append(start_merge(db, proposal, t, e.get("keywords") or None))
    if omitidas:
        restantes = content_placement.proposal_keywords(proposal)
        quedan = [k for k in restantes if k.lower() not in {o.lower() for o in omitidas}]
        if quedan:
            excluir_keywords(proposal, [k.get("keyword") for k in _kw_dicts(proposal)
                                        if k.get("excluded") and not k.get("merged")]
                             + omitidas)
        elif opps:
            # Todo lo demás se fundió y esto se omite: la idea está resuelta.
            kws = _kw_dicts(proposal)
            for k in kws:
                if (k.get("keyword") or "").lower() in {o.lower() for o in omitidas}:
                    k["excluded"] = True
            proposal.keywords = kws
            proposal.status = "merged"
        else:
            raise MergeError("omitir todas las keywords es rechazar la propuesta")
    db.commit()
    return opps


def release_proposal(db, opp) -> None:
    """Si la fusión se descarta o no sale, sus keywords vuelven a la propuesta.

    Una idea no se pierde porque la página elegida no admitiera lo nuevo: vuelve a
    «por validar» con el motivo, y se puede elegir otro destino o escribirla aparte.
    """
    from app.db.models import ContentProposal

    if not getattr(opp, "proposal_id", None):
        return
    prop = db.get(ContentProposal, opp.proposal_id)
    if prop is None:
        return
    kws = _kw_dicts(prop)
    devueltas = False
    for k in kws:
        if k.get("merge_opportunity_id") == opp.id:
            k.pop("excluded", None)
            k.pop("merged", None)
            k.pop("merge_opportunity_id", None)
            devueltas = True
    legado = prop.merge_opportunity_id == opp.id   # fusiones de antes de los grupos
    if not (devueltas or legado):
        return
    prop.keywords = kws
    if prop.status == "merged":
        prop.status = "proposed"
    if prop.merge_opportunity_id == opp.id:
        prop.merge_target = None
        prop.merge_opportunity_id = None
    pl = dict(prop.placement or {})
    pl["last_merge"] = {"path": opp.path, "status": opp.status,
                        "error": (opp.error or "")[:300]}
    prop.placement = pl
