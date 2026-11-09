"""Cliente de GA4 (Data API v1beta + Admin API) para entreinteriores.com.

Usa el MISMO token OAuth que `gsc_client` (`~/.config/entreinteriores/gsc-token.json`,
que ya trae `analytics.readonly`) y su mismo refresco. Así no se crea un segundo token
que caduque por su lado: el viejo `~/.config/davidruizsanchez/ga4-admin-token.json`
daba `invalid_grant` el 29-10-2026 y nadie se enteró. Si este falla, se reautoriza con
`python -m scripts.seo.gsc_reauth` y se arreglan GSC y GA4 a la vez.

Como `gsc_client`: httpx puro y sin google-api-python-client. A diferencia de él, aquí
los errores SÍ suben: un informe de tráfico vacío por un token caducado es justo el
fallo silencioso que hay que evitar.
"""
from __future__ import annotations

import os

import httpx

from app.services import gsc_client

_DATA = "https://analyticsdata.googleapis.com/v1beta"
_ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
MEASUREMENT_ID = os.environ.get("GA4_MEASUREMENT_ID", "G-1EQFBSDR2P")


class GA4Error(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    at = gsc_client._access_token()
    if not at:
        raise GA4Error(
            f"sin token válido en {gsc_client._token_path()}: "
            "reautoriza con `PYTHONPATH=api python3 -m scripts.seo.gsc_reauth`"
        )
    return {"Authorization": f"Bearer {at}"}


def _get(url: str, headers: dict, params: dict | None = None) -> dict:
    r = httpx.get(url, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        raise GA4Error(f"{r.status_code} en {url}: {r.text[:300]}")
    return r.json()


def property_id() -> str:
    """`GA4_PROPERTY_ID` del entorno o, si falta, la propiedad cuyo stream web es
    `MEASUREMENT_ID`. Se busca por el stream y no por el nombre: el nombre lo puede
    cambiar cualquiera desde la interfaz, el ID de medición es el que lleva la web."""
    if os.environ.get("GA4_PROPERTY_ID"):
        return os.environ["GA4_PROPERTY_ID"]
    headers = _headers()
    resumen = _get(f"{_ADMIN}/accountSummaries", headers, {"pageSize": 200})
    for cuenta in resumen.get("accountSummaries", []):
        for prop in cuenta.get("propertySummaries", []):
            streams = _get(f"{_ADMIN}/{prop['property']}/dataStreams", headers)
            for s in streams.get("dataStreams", []):
                if (s.get("webStreamData") or {}).get("measurementId") == MEASUREMENT_ID:
                    return prop["property"].split("/")[-1]
    raise GA4Error(f"ninguna propiedad accesible tiene el stream {MEASUREMENT_ID}")


def run_report(body: dict, prop: str | None = None) -> list[dict]:
    """`runReport` crudo → lista de filas como dicts {dimensión/métrica: valor}."""
    prop = prop or property_id()
    r = httpx.post(f"{_DATA}/properties/{prop}:runReport", headers=_headers(), json=body,
                   timeout=60)
    if r.status_code != 200:
        raise GA4Error(f"{r.status_code} en runReport: {r.text[:300]}")
    data = r.json()
    dims = [d["name"] for d in data.get("dimensionHeaders", [])]
    mets = [m["name"] for m in data.get("metricHeaders", [])]
    return [
        dict(zip(dims, [v["value"] for v in row["dimensionValues"]], strict=True))
        | dict(zip(mets, [v["value"] for v in row["metricValues"]], strict=True))
        for row in data.get("rows", [])
    ]
