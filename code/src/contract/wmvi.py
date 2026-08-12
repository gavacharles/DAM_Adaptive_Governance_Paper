"""WMVI constructor utilities."""

from __future__ import annotations

from typing import Dict, Iterable


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(v, 0.0) for v in weights.values())
    if total == 0:
        raise ValueError("At least one positive weight is required.")
    return {k: max(v, 0.0) / total for k, v in weights.items()}


def wmvi_at_t(z_scores: Dict[str, float], weights: Dict[str, float]) -> float:
    w = normalize_weights(weights)
    missing = set(w).difference(z_scores)
    if missing:
        raise KeyError(f"Missing z-score components: {sorted(missing)}")
    return sum(w[k] * z_scores[k] for k in w)


def wmvi_series(rows: Iterable[Dict[str, float]], weights: Dict[str, float]) -> list[float]:
    return [wmvi_at_t(row, weights) for row in rows]
