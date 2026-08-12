"""Cashflow simulation engine for Dynamic Adjustment Mechanism (DAM).

This module is intentionally framework-light and deterministic for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class RegimeConfig:
    name: str
    lower_trigger: float
    upper_trigger: float
    gamma: float
    monthly_cap_up: float
    monthly_cap_down: float


@dataclass(frozen=True)
class PaymentRow:
    month: str
    base_payment: float
    wmvi: float


@dataclass(frozen=True)
class LedgerRow:
    month: str
    base_payment: float
    wmvi: float
    breach: float
    adjustment: float
    adjusted_payment: float
    cap_hit: bool


def _clip(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def breach_from_wmvi(wmvi: float, lower_trigger: float, upper_trigger: float) -> float:
    """Return breach magnitude relative to trigger band."""
    if wmvi > upper_trigger:
        return wmvi - upper_trigger
    if wmvi < lower_trigger:
        return wmvi - lower_trigger
    return 0.0


def dam_adjustment(base_payment: float, breach: float, gamma: float, cap_up: float, cap_down: float) -> float:
    """Return bounded adjustment amount for one payment row."""
    raw = gamma * breach * base_payment
    return _clip(raw, -abs(cap_down), abs(cap_up))


def simulate_monthly_ledger(rows: List[PaymentRow], regime: RegimeConfig) -> List[LedgerRow]:
    """Simulate a monthly ledger for DAM-like regimes.

    For fixed-price comparator, set triggers wide and `gamma=0`.
    """
    out: List[LedgerRow] = []
    for row in rows:
        breach = breach_from_wmvi(row.wmvi, regime.lower_trigger, regime.upper_trigger)
        adjustment = dam_adjustment(
            base_payment=row.base_payment,
            breach=breach,
            gamma=regime.gamma,
            cap_up=regime.monthly_cap_up,
            cap_down=regime.monthly_cap_down,
        )
        adjusted = row.base_payment + adjustment
        cap_hit = abs(adjustment) in {abs(regime.monthly_cap_up), abs(regime.monthly_cap_down)} and adjustment != 0
        out.append(
            LedgerRow(
                month=row.month,
                base_payment=row.base_payment,
                wmvi=row.wmvi,
                breach=breach,
                adjustment=adjustment,
                adjusted_payment=adjusted,
                cap_hit=cap_hit,
            )
        )
    return out


def summarize_risk(ledger: List[LedgerRow]) -> Dict[str, float]:
    """Compute minimal risk summary metrics for paper tables."""
    if not ledger:
        return {
            "adjustment_variance": 0.0,
            "event_count": 0.0,
            "max_abs_adjustment": 0.0,
        }

    adjustments = [r.adjustment for r in ledger]
    mean = sum(adjustments) / len(adjustments)
    var = sum((x - mean) ** 2 for x in adjustments) / len(adjustments)
    return {
        "adjustment_variance": var,
        "event_count": float(sum(1 for x in adjustments if x != 0.0)),
        "max_abs_adjustment": max(abs(x) for x in adjustments),
    }
