"""Back-test scaffold for project archetypes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .dam_engine import PaymentRow, RegimeConfig, simulate_monthly_ledger, summarize_risk


@dataclass(frozen=True)
class Archetype:
    name: str
    rows: List[PaymentRow]


def evaluate_regimes(archetype: Archetype, regimes: List[RegimeConfig]) -> Dict[str, Dict[str, float]]:
    results: Dict[str, Dict[str, float]] = {}
    for regime in regimes:
        ledger = simulate_monthly_ledger(archetype.rows, regime)
        results[regime.name] = summarize_risk(ledger)
    return results
