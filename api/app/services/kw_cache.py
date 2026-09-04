"""Caché en disco y contabilidad de gasto para el keyword research.

Dos motivos por los que esto existe:

- **No repagar.** Hoy `generate_proposals` re-pide sugerencias para 100+ semillas
  en cada ejecución y `regenerate_deep` re-pide volúmenes ya conocidos. Un cierre
  transitivo sin caché re-consultaría la misma semilla una vez por cada asset que
  la comparta.
- **Saber lo que se gasta de verdad.** El coste que se apunta es el campo `cost`
  que devuelve DataForSEO en cada respuesta, y las unidades medidas de Ahrefs.
  Nunca una estimación: la estimación solo se usa para el `--dry-run` y para el
  gate previo, y se reconcilia contra lo medido al cerrar el run.

La salida vive bajo `api/data/keyword_research/` y NO bajo `data/`, porque
`./data` está montado read-only en el contenedor (docker-compose.yml).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# (coste por petición, coste por resultado) — precios REALES de la cuenta,
# leídos de /v3/appendix/user_data el 2026-08-01.
COST_MODEL: dict[str, tuple[float, float]] = {
    "labs": (0.012, 0.00012),
    "labs_intent": (0.0012, 0.000012),
    "ads_volume": (0.09, 0.0),
    "serp_organic": (0.002, 0.0),
}

# Unidades por fila MEDIDAS en Ahrefs el 2026-08-01 (keywords-explorer-matching-terms).
AHREFS_UNITS_PER_ROW = {"minimal": 11, "wide": 33}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def forecast_cost(family: str, n_results: int, n_requests: int = 1) -> float:
    per_req, per_res = COST_MODEL[family]
    return n_requests * per_req + n_results * per_res


class BudgetExceeded(RuntimeError):
    """El gate cortó el run. El estado queda reanudable: caché y ledger intactos."""


@dataclass
class CallResult:
    payload: dict
    from_cache: bool
    cost_usd: float | None
    n_results: int
    params_hash: str
    raw_path: str | None = None


@dataclass
class RunPaths:
    root: Path
    run_id: str

    @property
    def run_dir(self) -> Path:
        return self.root / self.run_id

    @property
    def raw_dir(self) -> Path:
        return self.root / "_raw"

    @property
    def ledger_path(self) -> Path:
        return self.run_dir / "costs.jsonl"

    def ensure(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)


class CacheStore:
    """Caché de respuestas crudas, indexada por (proveedor, endpoint, params).

    Los ficheros crudos son inmutables y compartidos entre runs: son la evidencia
    a la que apunta `evidence_ref` en el CSV entregado.
    """

    def __init__(self, paths: RunPaths, *, max_age_days: int = 30) -> None:
        self.paths = paths
        self.max_age_seconds = max_age_days * 86400
        self.paths.ensure()

    @staticmethod
    def key(provider: str, endpoint: str, params: dict) -> str:
        blob = json.dumps(
            {"provider": provider, "endpoint": endpoint, "params": params},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def _path(self, key: str) -> Path:
        return self.paths.raw_dir / f"{key}.json"

    def get(self, provider: str, endpoint: str, params: dict) -> dict | None:
        path = self._path(self.key(provider, endpoint, params))
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > self.max_age_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, provider: str, endpoint: str, params: dict, payload: dict) -> str:
        key = self.key(provider, endpoint, params)
        path = self._path(key)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=None), encoding="utf-8"
        )
        return str(path)


@dataclass
class SpendLedger:
    """Una línea por llamada pagada. De aquí sale COSTS.md y parte de SOURCES.md."""

    paths: RunPaths
    max_spend_usd: float
    max_ahrefs_units: int
    max_calls_per_day: int = 1000
    rehidratar: bool = True
    _spent_usd: float = 0.0
    _spent_units: int = 0
    _calls: int = 0
    _rows: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Recupera lo YA gastado en este run de `costs.jsonl`.

        Sin esto los contadores arrancaban a cero en cada proceso y el tope era
        decorativo: una ola troceada en cinco tandas con `--max-spend 40` podía
        gastar $200 sin que nada saltara, porque cada tanda se creía la primera.
        El ledger se append-ea a disco, así que la cuenta real estaba ahí desde
        el principio; solo faltaba leerla.

        Las filas servidas de caché no suman: no costaron nada.
        """
        if not self.rehidratar:
            return
        ledger_path = self.paths.ledger_path
        if not ledger_path.exists():
            return
        gasto, unidades, llamadas = 0.0, 0, 0
        for linea in ledger_path.read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError:
                continue          # una línea a medias no invalida la cuenta
            if fila.get("from_cache"):
                continue
            gasto += float(fila.get("cost_usd") or 0)
            unidades += int(fila.get("units") or 0)
            llamadas += 1
        self._spent_usd, self._spent_units, self._calls = gasto, unidades, llamadas
        if llamadas:
            print(f"[ledger] este run ya llevaba ${gasto:.4f} en {llamadas} "
                  f"llamadas: el tope de ${self.max_spend_usd:.2f} cuenta desde ahí")

    def gate(self, *, est_cost_usd: float = 0.0, est_units: int = 0) -> None:
        if self._spent_usd + est_cost_usd > self.max_spend_usd:
            raise BudgetExceeded(
                f"tope de gasto: llevo ${self._spent_usd:.4f} y la siguiente "
                f"llamada suma ~${est_cost_usd:.4f} (tope ${self.max_spend_usd:.2f})"
            )
        if self._spent_units + est_units > self.max_ahrefs_units:
            raise BudgetExceeded(
                f"tope de unidades Ahrefs: llevo {self._spent_units} y la "
                f"siguiente suma ~{est_units} (tope {self.max_ahrefs_units})"
            )
        if self._calls >= self.max_calls_per_day:
            raise BudgetExceeded(
                f"límite diario de la cuenta alcanzado ({self.max_calls_per_day} "
                "llamadas). Reanudar mañana: la caché conserva todo lo hecho."
            )

    def record(
        self,
        *,
        provider: str,
        endpoint: str,
        params_hash: str,
        params: dict | None = None,
        cost_usd: float | None = None,
        units: int | None = None,
        units_attribution: str = "measured",
        n_results: int = 0,
        asset: str | None = None,
        round_no: int | None = None,
        seed: str | None = None,
        status: str = "ok",
        status_message: str | None = None,
        from_cache: bool = False,
    ) -> None:
        if not from_cache:
            self._calls += 1
            self._spent_usd += cost_usd or 0.0
            self._spent_units += units or 0
        row = {
            "ts": utcnow(),
            "provider": provider,
            "endpoint": endpoint,
            "params_hash": params_hash,
            "asset": asset,
            "round": round_no,
            "seed": seed,
            "n_results": n_results,
            "cost_usd": cost_usd,
            "units": units,
            "units_attribution": units_attribution if units else None,
            "status": status,
            "status_message": status_message,
            "from_cache": from_cache,
        }
        if params is not None:
            row["params"] = params
        self._rows.append(row)
        with self.paths.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    @property
    def spent_usd(self) -> float:
        return self._spent_usd

    @property
    def spent_units(self) -> int:
        return self._spent_units

    @property
    def calls(self) -> int:
        return self._calls

    def summary(self) -> dict[str, Any]:
        by_endpoint: dict[str, dict[str, Any]] = {}
        for r in self._rows:
            if r["from_cache"]:
                continue
            slot = by_endpoint.setdefault(
                r["endpoint"], {"calls": 0, "cost_usd": 0.0, "units": 0, "results": 0}
            )
            slot["calls"] += 1
            slot["cost_usd"] += r["cost_usd"] or 0.0
            slot["units"] += r["units"] or 0
            slot["results"] += r["n_results"]
        return {
            "total_cost_usd": round(self._spent_usd, 6),
            "total_ahrefs_units": self._spent_units,
            "paid_calls": self._calls,
            "cached_hits": sum(1 for r in self._rows if r["from_cache"]),
            "by_endpoint": by_endpoint,
        }
