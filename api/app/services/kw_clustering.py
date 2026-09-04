"""Agrupación semántica de keywords por k-means determinista.

PROCEDENCIA: port del k-means de
`~/.claude/skills/site-centroid/lib/clustering.py` (numpy puro sobre vectores
unitarios, sin sklearn/scipy por decisión de aquel repo tras un histórico de
OOM). Se mantiene la semántica bit a bit para que los números coincidan.

Determinista a propósito: la primera semilla es el punto de mayor peso (aquí,
mayor volumen de búsqueda) y las siguientes el punto más lejano a las ya
elegidas. Un rerun sobre los mismos datos da el mismo mapa, que es lo que
permite comparar dos runs y decir «esto es nuevo».
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from app.services.kw_normalize import STOPWORDS_ES, kw_tokens


def to_unit_matrix(vectors: list[list[float]]) -> np.ndarray:
    """Matriz de vectores unitarios. Con norma 1, el producto escalar ES el coseno."""
    m = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def auto_k(n: int, *, target_per_cluster: int = 12, max_k: int = 40) -> int:
    if n <= target_per_cluster:
        return 1
    return max(1, min(max_k, int(math.ceil(n / target_per_cluster))))


def kmeans(
    unit: np.ndarray, weights: np.ndarray, k: int, iters: int = 12
) -> tuple[np.ndarray, np.ndarray]:
    """k-means esférico. Devuelve (labels, centroides unitarios)."""
    n = unit.shape[0]
    k = max(1, min(k, n))

    # Semillas deterministas: la de mayor peso, luego la más lejana a las ya elegidas.
    seeds = [int(np.argmax(weights))]
    if k > 1:
        sims = unit @ unit[seeds[0]]
        for _ in range(1, k):
            nxt = int(np.argmin(sims))
            if nxt in seeds:
                restantes = [i for i in range(n) if i not in seeds]
                if not restantes:
                    break
                nxt = restantes[0]
            seeds.append(nxt)
            sims = np.maximum(sims, unit @ unit[nxt])

    centroids = unit[seeds].copy()
    labels = np.zeros(n, dtype=np.int32)
    for _ in range(iters):
        labels = np.argmax(unit @ centroids.T, axis=1).astype(np.int32)
        nuevos = []
        for c in range(centroids.shape[0]):
            miembros = unit[labels == c]
            if miembros.shape[0] == 0:
                nuevos.append(centroids[c])
                continue
            w = weights[labels == c][:, None]
            centro = (miembros * w).sum(axis=0)
            norma = np.linalg.norm(centro)
            nuevos.append(centro / norma if norma else centroids[c])
        actualizados = np.vstack(nuevos)
        if np.allclose(actualizados, centroids, atol=1e-6):
            centroids = actualizados
            break
        centroids = actualizados
    return labels, centroids


@dataclass
class Cluster:
    id: int
    label: str
    head: str
    size: int
    total_volume: int
    members: list[int]


def pick_head(
    unit: np.ndarray, idxs: list[int], centroid: np.ndarray, volumes: list[int]
) -> int:
    """Cabeza del cluster: entre las semánticamente centrales, la de más volumen.

    No vale con «la más cercana al centroide»: esa suele ser una variante rara.
    Se filtra por centralidad (>= mediana) y dentro de esas manda el volumen,
    que es lo que hace útil a una cabeza.
    """
    sims = unit[idxs] @ centroid
    corte = float(np.median(sims))
    candidatos = [i for i, s in zip(idxs, sims) if s >= corte] or idxs
    return max(candidatos, key=lambda i: (volumes[i], -len(kw_tokens_cached(i))))


_TOKENS_CACHE: dict[int, list[str]] = {}


def kw_tokens_cached(i: int) -> list[str]:
    return _TOKENS_CACHE.get(i, [])


def label_from_ngram(keywords: list[str], *, min_share: float = 0.55) -> str | None:
    """Nombre determinista: el n-grama no-stopword compartido por la mayoría."""
    if not keywords:
        return None
    conteo: dict[str, int] = {}
    for kw in keywords:
        toks = [t for t in kw_tokens(kw) if t not in STOPWORDS_ES]
        vistos = set()
        for size in (3, 2):
            for i in range(len(toks) - size + 1):
                g = " ".join(toks[i : i + size])
                if g not in vistos:
                    vistos.add(g)
                    conteo[g] = conteo.get(g, 0) + 1
    if not conteo:
        return None
    suelo = max(2, int(len(keywords) * min_share))
    validos = {g: c for g, c in conteo.items() if c >= suelo}
    if not validos:
        return None
    return max(validos.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def cluster_keywords(
    keywords: list[str],
    volumes: list[int],
    vectors: list[list[float]],
    *,
    target_per_cluster: int = 12,
    max_k: int = 40,
) -> list[Cluster]:
    if not keywords:
        return []

    _TOKENS_CACHE.clear()
    for i, kw in enumerate(keywords):
        _TOKENS_CACHE[i] = kw_tokens(kw)

    unit = to_unit_matrix(vectors)
    # Peso = log1p(volumen) para que un head term de 50.000 no aplaste la cola
    # larga, que es justo donde vive lo interesante.
    weights = np.asarray([math.log1p(max(0, v)) + 0.1 for v in volumes], dtype=np.float32)
    k = auto_k(len(keywords), target_per_cluster=target_per_cluster, max_k=max_k)
    labels, centroids = kmeans(unit, weights, k)

    out: list[Cluster] = []
    for c in range(centroids.shape[0]):
        idxs = [i for i, lab in enumerate(labels) if lab == c]
        if not idxs:
            continue
        head_i = pick_head(unit, idxs, centroids[c], volumes)
        miembros = [keywords[i] for i in idxs]
        etiqueta = label_from_ngram(miembros) or keywords[head_i]
        out.append(Cluster(
            id=c,
            label=etiqueta,
            head=keywords[head_i],
            size=len(idxs),
            total_volume=sum(volumes[i] for i in idxs),
            members=idxs,
        ))
    out.sort(key=lambda cl: -cl.total_volume)
    for nuevo_id, cl in enumerate(out):
        cl.id = nuevo_id
    return out
