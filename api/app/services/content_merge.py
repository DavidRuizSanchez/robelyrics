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


def start_merge(db, proposal, target: str):
    """Deja la oportunidad `approved` y la propuesta `merged`. Devuelve la oportunidad.

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

    # La evidencia que viaja con la oportunidad: las consultas de la propuesta con
    # su dato GSC sobre ESA página si lo tiene, y si no, su volumen de búsqueda.
    placement = proposal.placement or {}
    previo = next((c for c in placement.get("candidates") or [] if c.get("target") == target),
                  {})
    gsc_por_query = {q["query"]: q for q in previo.get("gsc_queries") or []}
    queries = []
    for kw in content_placement.proposal_keywords(proposal):
        vol = next((int(k.get("volume") or 0) for k in proposal.keywords or []
                    if isinstance(k, dict) and k.get("keyword") == kw), 0)
        g = gsc_por_query.get(kw) or {}
        queries.append({"query": kw, "impressions": int(g.get("impressions") or 0),
                        "position": g.get("position"), "volume": vol})

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
    proposal.status = "merged"
    proposal.merge_target = target
    proposal.merge_opportunity_id = opp.id
    proposal.scheduled_for = None
    db.commit()
    logger.info("[merge] propuesta #%s → %s (oportunidad #%s)", proposal.id, cand.path, opp.id)
    return opp


def release_proposal(db, opp) -> None:
    """Si la fusión se descarta o no sale, la propuesta vuelve al banco.

    Una idea no se pierde porque la página elegida no admitiera lo nuevo: vuelve a
    «por validar» con el motivo, y se puede elegir otro destino o escribirla aparte.
    """
    from app.db.models import ContentProposal

    if not getattr(opp, "proposal_id", None):
        return
    prop = db.get(ContentProposal, opp.proposal_id)
    if prop and prop.status == "merged" and prop.merge_opportunity_id == opp.id:
        prop.status = "proposed"
        prop.merge_target = None
        prop.merge_opportunity_id = None
        pl = dict(prop.placement or {})
        pl["last_merge"] = {"path": opp.path, "status": opp.status,
                            "error": (opp.error or "")[:300]}
        prop.placement = pl
