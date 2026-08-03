"""Motor de keyword research por asset: cierre transitivo hasta saturación.

No hay top-N ni un número fijo de pasadas. Se parte de las semillas del asset y
cada keyword nueva que pertenece al universo se convierte en semilla de la ronda
siguiente, hasta que deja de aparecer nada nuevo. La parada la marca la
convergencia, no una cifra elegida a dedo — eso es lo que hace que el research
sea «completo» en un sentido comprobable.

Converge porque el universo es finito, y está medido (01-08-2026):
`keyword_suggestions("agila extremoduro", limit=1000)` devuelve 53 keywords y se
agota sin tocar el límite; «deltoya extremoduro» devuelve 31; y el solapamiento
entre ambos discos es del 1,2%.

Dos reglas que no se tocan:

- **No se filtra por volumen.** La cola larga de volumen 0 entra entera: es donde
  vive el tráfico de letras y significados. El corte se aplica al exportar.
- **Lo que no pertenece al universo se marca, no se esconde.** Va a `offtopic.csv`
  con el motivo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services import seo_research as dfs
from app.services.kw_cache import CacheStore, SpendLedger, forecast_cost
from app.services.kw_normalize import (
    UniverseVocab,
    detect_intent,
    is_brand,
    kw_clean_for_api,
    kw_norm,
    n_words,
    variant_group,
)

logger = logging.getLogger(__name__)

LOCATION_SPAIN = 2724
LANG_ES = "es"

# Tope de seguridad: si un asset supera esto, algo se ha desmadrado (una semilla
# demasiado genérica) y prefiero parar y mirarlo a quemar presupuesto en silencio.
MAX_ROUNDS = 6
MAX_SEEDS_PER_ROUND = 400

# Hashes de peticiones que han fallado en ESTA pasada. Vive en memoria, no en
# disco: un error no debe sobrevivir al proceso (mañana la API puede responder),
# pero repetirlo dentro de la misma pasada es tirar dinero.
_FALLOS_DE_ESTA_PASADA: set[str] = set()


@dataclass
class Asset:
    asset_type: str          # album | song | artist
    slug: str
    title: str
    artist_slug: str
    artist_name: str
    url_path: str
    extra_seeds: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        return f"{self.asset_type}:{self.slug}"


@dataclass
class KwRow:
    keyword: str
    keyword_norm: str
    variant_group: str
    volume: int | None = None
    cpc: float | None = None
    competition: float | None = None
    difficulty: int | None = None
    intent_api: str | None = None
    intent_lex: str | None = None
    providers: set[str] = field(default_factory=set)
    endpoints: set[str] = field(default_factory=set)
    evidence: set[str] = field(default_factory=set)
    discovered_round: int = 0
    discovered_from: str | None = None
    belongs_reason: str | None = None
    belongs_kind: str | None = None   # brand | title_strong | title_weak | None
    off_topic: bool = False
    volume_source: str | None = None
    fetched_at: str | None = None

    def merge(self, other: "KwRow") -> None:
        """Fusiona dos observaciones de la misma keyword.

        Una métrica ya presente no se pisa con None, y no se promedia nada:
        si dos proveedores dan volúmenes distintos se conserva el primero con su
        `volume_source` y la divergencia se reporta aparte.
        """
        for attr in ("volume", "cpc", "competition", "difficulty", "intent_api"):
            if getattr(self, attr) is None and getattr(other, attr) is not None:
                setattr(self, attr, getattr(other, attr))
                if attr == "volume":
                    self.volume_source = other.volume_source
                    self.fetched_at = other.fetched_at
        self.providers |= other.providers
        self.endpoints |= other.endpoints
        self.evidence |= other.evidence
        if other.discovered_round < self.discovered_round:
            self.discovered_round = other.discovered_round
            self.discovered_from = other.discovered_from
        if self.belongs_reason is None:
            self.belongs_reason = other.belongs_reason


def build_seeds(asset: Asset) -> list[str]:
    """Semillas iniciales del asset. TODAS cualificadas con la marca.

    El título pelado NO se usa nunca como semilla. Medido en el piloto: sembrar
    con «Agila» trae el rey visigodo y el Opel Agila; con «Tomás», a José Tomás
    el torero, Santo Tomás de Aquino y Tomás Roncero — 3.107 keywords de ruido en
    una sola ronda. Anclar cada semilla al artista cuesta lo mismo y devuelve el
    universo de verdad.

    La cualificación usa el artista REAL del asset. `keyword_planner` hardcodea
    «extremoduro» también para los discos de Robe (línea 157); aquí no.
    """
    title = kw_clean_for_api(asset.title)
    artist = kw_clean_for_api(asset.artist_name)
    seeds = [f"{title} {artist}", f"{artist} {title}"]

    if asset.asset_type == "album":
        seeds += [
            f"{title} {artist} disco",
            f"{title} {artist} canciones",
            f"{title} {artist} letras",
        ]
    elif asset.asset_type == "song":
        seeds += [
            f"{title} {artist} letra",
            f"letra {title} {artist}",
            f"{title} {artist} significado",
        ]
    elif asset.asset_type == "artist":
        seeds += [
            f"{title} canciones", f"{title} discografia",
            f"{title} letras", f"{title} discos",
        ]

    # Los títulos de canciones del disco entran SIEMPRE cualificados.
    for extra in asset.extra_seeds:
        clean = kw_clean_for_api(extra)
        if clean:
            seeds.append(f"{clean} {artist}")

    seen: set[str] = set()
    out: list[str] = []
    for s in seeds:
        k = kw_norm(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _row_from_labs_item(
    item: dict, *, endpoint: str, round_no: int, seed: str, evidence: str
) -> KwRow | None:
    kd = item.get("keyword_data") or item
    keyword = kd.get("keyword") or item.get("keyword")
    if not keyword:
        return None
    ki = kd.get("keyword_info") or {}
    props = kd.get("keyword_properties") or {}
    intent_block = kd.get("search_intent_info") or {}
    return KwRow(
        keyword=keyword,
        keyword_norm=kw_norm(keyword),
        variant_group=variant_group(keyword),
        volume=ki.get("search_volume"),
        cpc=ki.get("cpc"),
        competition=ki.get("competition"),
        difficulty=props.get("keyword_difficulty"),
        intent_api=intent_block.get("main_intent"),
        intent_lex=detect_intent(keyword),
        providers={"dataforseo"},
        endpoints={endpoint},
        evidence={evidence},
        discovered_round=round_no,
        discovered_from=seed,
        volume_source="dataforseo_labs" if ki.get("search_volume") is not None else None,
        fetched_at=ki.get("last_updated_time"),
    )


def _call_labs(
    endpoint: str,
    payload: dict,
    *,
    cache: CacheStore,
    ledger: SpendLedger,
    asset: str,
    round_no: int,
    seed: str,
    family: str = "labs",
    est_results: int = 300,
) -> tuple[list[dict], str]:
    """Una llamada a Labs, con caché y gasto medido. Devuelve (items, evidence_ref)."""
    params_hash = CacheStore.key("dataforseo", endpoint, payload)
    # Un fallo NO se cachea en disco a propósito: escribir `{"items": []}`
    # envenenaría el universo con un vacío que parecería un resultado legítimo y
    # se arrastraría 30 días. Pero dentro de una misma pasada sí se recuerda, o
    # el cierre transitivo vuelve a pedir la misma semilla rota una y otra vez.
    # Medido en la ola 1: 294 de 1.144 llamadas pagadas (26%) devolvieron «sin
    # respuesta», y cada reintento cuesta dinero y cupo.
    if params_hash in _FALLOS_DE_ESTA_PASADA:
        return [], params_hash
    cached = cache.get("dataforseo", endpoint, payload)
    if cached is not None:
        ledger.record(
            provider="dataforseo", endpoint=endpoint, params_hash=params_hash,
            n_results=len(cached.get("items") or []), asset=asset,
            round_no=round_no, seed=seed, from_cache=True,
        )
        return cached.get("items") or [], params_hash

    ledger.gate(est_cost_usd=forecast_cost(family, est_results))
    task = dfs._post(endpoint, [payload])
    if not task:
        _FALLOS_DE_ESTA_PASADA.add(params_hash)
        ledger.record(
            provider="dataforseo", endpoint=endpoint, params_hash=params_hash,
            params=payload, asset=asset, round_no=round_no, seed=seed,
            status="error", status_message="sin respuesta",
        )
        return [], params_hash

    result = (task.get("result") or [{}])[0] or {}
    items = result.get("items") or []
    cache.put("dataforseo", endpoint, payload, {"items": items,
                                                "total_count": result.get("total_count")})
    ledger.record(
        provider="dataforseo", endpoint=endpoint, params_hash=params_hash,
        params=payload, cost_usd=task.get("cost"), n_results=len(items),
        asset=asset, round_no=round_no, seed=seed,
    )
    return items, params_hash


def harvest_seed(
    seed: str,
    *,
    asset: Asset,
    round_no: int,
    cache: CacheStore,
    ledger: SpendLedger,
    limit: int = 1000,
) -> list[KwRow]:
    """Recolecta todo lo que dan los endpoints de descubrimiento para una semilla.

    `keyword_ideas` NO entra aquí: se midió que devuelve 96,6% de ruido de
    categoría. Solo `keyword_suggestions` (full-text de la semilla, se agota solo)
    y `related_keywords` (eje «también buscan», barato).
    """
    rows: list[KwRow] = []
    clean = kw_clean_for_api(seed)
    if not clean:
        return rows

    items, ev = _call_labs(
        "dataforseo_labs/google/keyword_suggestions/live",
        {
            "keyword": clean,
            "location_code": LOCATION_SPAIN,
            "language_code": LANG_ES,
            "limit": limit,
            "include_serp_info": False,
            "order_by": ["keyword_info.search_volume,desc"],
        },
        cache=cache, ledger=ledger, asset=asset.ref, round_no=round_no, seed=seed,
        est_results=60,
    )
    for it in items:
        r = _row_from_labs_item(
            it, endpoint="keyword_suggestions", round_no=round_no, seed=seed, evidence=ev
        )
        if r:
            rows.append(r)

    items, ev = _call_labs(
        "dataforseo_labs/google/related_keywords/live",
        {
            "keyword": clean,
            "location_code": LOCATION_SPAIN,
            "language_code": LANG_ES,
            "depth": 3,
            "limit": limit,
            "include_serp_info": False,
        },
        cache=cache, ledger=ledger, asset=asset.ref, round_no=round_no, seed=seed,
        est_results=20,
    )
    for it in items:
        r = _row_from_labs_item(
            it, endpoint="related_keywords", round_no=round_no, seed=seed, evidence=ev
        )
        if r:
            rows.append(r)

    return rows


def close_universe(
    asset: Asset,
    *,
    vocab: UniverseVocab,
    cache: CacheStore,
    ledger: SpendLedger,
    max_rounds: int = MAX_ROUNDS,
    max_seeds_per_round: int = MAX_SEEDS_PER_ROUND,
    on_progress: Any = None,
) -> tuple[dict[str, KwRow], list[dict]]:
    """Cierre transitivo del universo de keywords de un asset.

    Devuelve (universo, trazas_por_ronda). El universo incluye las off-topic
    marcadas: se exportan aparte, no se tiran.

    `max_seeds_per_round` es el freno de gasto y conviene bajarlo cuando la ola
    es grande: cada semilla son dos llamadas de pago. En la ola 1 el tope de 400
    se alcanzó en las rondas 3 y 4 de casi todos los discos, o sea que el cierre
    **se truncó por tope, no por convergencia** — y ahí es donde se fue el
    dinero.
    """
    universe: dict[str, KwRow] = {}
    consulted: set[str] = set()
    frontier = build_seeds(asset)
    rounds: list[dict] = []

    for round_no in range(1, max_rounds + 1):
        pending = [s for s in frontier if kw_norm(s) not in consulted][:max_seeds_per_round]
        if not pending:
            break

        fresh: list[KwRow] = []
        for seed in pending:
            consulted.add(kw_norm(seed))
            try:
                fresh += harvest_seed(
                    seed, asset=asset, round_no=round_no, cache=cache, ledger=ledger
                )
            except Exception as exc:  # noqa: BLE001 — un fallo puntual no tumba el asset
                logger.warning("semilla %r falló: %s", seed, exc)

        nuevas_fuertes: list[str] = []
        nuevas_debiles = 0
        for row in fresh:
            key = row.keyword_norm
            if not key:
                continue
            if key in universe:
                universe[key].merge(row)
                continue
            m = vocab.matches(row.keyword)
            row.belongs_reason = m.reason if m else None
            row.belongs_kind = m.kind if m else None
            row.off_topic = m is None
            universe[key] = row
            if m and m.strong:
                nuevas_fuertes.append(key)
            elif m:
                nuevas_debiles += 1

        rounds.append({
            "round": round_no,
            "seeds_consultadas": len(pending),
            "keywords_vistas": len(fresh),
            "nuevas_fuertes": len(nuevas_fuertes),
            "nuevas_ambiguas": nuevas_debiles,
            "universo_acumulado": sum(1 for r in universe.values() if not r.off_topic),
            "offtopic_acumulado": sum(1 for r in universe.values() if r.off_topic),
        })
        if on_progress:
            on_progress(asset, rounds[-1])

        if not nuevas_fuertes:
            break

        # Solo lo INEQUÍVOCO siembra la ronda siguiente. Las ambiguas por
        # homonimia se recolectan y se etiquetan, pero no propagan: en el piloto,
        # sembrar con «prometeo» traía la librería de Málaga y el mito griego
        # entero, y de ahí el cierre no converge nunca.
        frontier = [universe[k].keyword for k in nuevas_fuertes]

    return universe, rounds


def enrich_missing(
    rows: list[KwRow],
    *,
    cache: CacheStore,
    ledger: SpendLedger,
    asset: str,
    batch: int = 700,
) -> None:
    """Completa métricas de las keywords que llegaron sin volumen.

    `keyword_overview` trae volumen + dificultad + intención de una tacada, y a
    $0.012 + 700×$0.00012 = $0.096 por lote de 700 sale más barato que pedir cada
    métrica por separado. Lo que siga sin dato se queda en NULL: no se rellena.
    """
    pendientes = [r for r in rows if r.volume is None and not r.off_topic]
    for i in range(0, len(pendientes), batch):
        chunk = pendientes[i : i + batch]
        payload = {
            "keywords": [r.keyword for r in chunk],
            "location_code": LOCATION_SPAIN,
            "language_code": LANG_ES,
        }
        items, ev = _call_labs(
            "dataforseo_labs/google/keyword_overview/live",
            payload, cache=cache, ledger=ledger, asset=asset,
            round_no=0, seed="<enriquecimiento>", est_results=len(chunk),
        )
        by_kw = {kw_norm(it.get("keyword", "")): it for it in items}
        for r in chunk:
            it = by_kw.get(r.keyword_norm)
            if not it:
                continue
            ki = it.get("keyword_info") or {}
            props = it.get("keyword_properties") or {}
            intent_block = it.get("search_intent_info") or {}
            if r.volume is None and ki.get("search_volume") is not None:
                r.volume = ki.get("search_volume")
                r.volume_source = "dataforseo_labs:keyword_overview"
                r.fetched_at = ki.get("last_updated_time")
            if r.cpc is None:
                r.cpc = ki.get("cpc")
            if r.competition is None:
                r.competition = ki.get("competition")
            if r.difficulty is None:
                r.difficulty = props.get("keyword_difficulty")
            if r.intent_api is None:
                r.intent_api = intent_block.get("main_intent")
            r.endpoints.add("keyword_overview")
            r.evidence.add(ev)


def row_to_dict(row: KwRow, asset: Asset) -> dict[str, Any]:
    return {
        "asset_type": asset.asset_type,
        "asset_slug": asset.slug,
        "asset_title": asset.title,
        "asset_url": asset.url_path,
        "keyword": row.keyword,
        "keyword_norm": row.keyword_norm,
        "variant_group": row.variant_group,
        "volume": row.volume,
        "volume_source": row.volume_source,
        "volume_fetched_at": row.fetched_at,
        "difficulty": row.difficulty,
        "cpc": row.cpc,
        "competition": row.competition,
        "intent_api": row.intent_api,
        "intent_lex": row.intent_lex,
        "n_words": n_words(row.keyword),
        "is_brand": is_brand(row.keyword),
        "belongs_reason": row.belongs_reason,
        "belongs_kind": row.belongs_kind,
        "off_topic": row.off_topic,
        "discovered_round": row.discovered_round,
        "discovered_from": row.discovered_from,
        "providers": "|".join(sorted(row.providers)),
        "endpoints": "|".join(sorted(row.endpoints)),
        "evidence_ref": "|".join(sorted(row.evidence)),
    }
