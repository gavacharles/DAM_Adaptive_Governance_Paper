"""Parameter calibration scaffold with strict train/eval split."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Iterable, List, Tuple

from .dam_engine import PaymentRow, RegimeConfig, simulate_monthly_ledger, summarize_risk


CALIBRATION_END = "2021-12"
EVAL_START = "2022-01"


@dataclass(frozen=True)
class Candidate:
    lower_trigger: float
    upper_trigger: float
    gamma: float
    cap_up: float
    cap_down: float


def _is_in_calibration(month: str) -> bool:
    return month <= CALIBRATION_END


def split_rows(rows: List[PaymentRow]) -> Tuple[List[PaymentRow], List[PaymentRow]]:
    train = [r for r in rows if _is_in_calibration(r.month)]
    test = [r for r in rows if r.month >= EVAL_START]
    return train, test


def grid_candidates(
    trigger_pairs: Iterable[tuple[float, float]],
    gammas: Iterable[float],
    cap_ups: Iterable[float],
    cap_downs: Iterable[float],
) -> List[Candidate]:
    return [
        Candidate(l, u, g, cu, cd)
        for (l, u), g, cu, cd in product(trigger_pairs, gammas, cap_ups, cap_downs)
        if l < u
    ]


def select_best(rows: List[PaymentRow], candidates: List[Candidate]) -> tuple[Candidate, dict, dict]:
    train_rows, test_rows = split_rows(rows)
    if not train_rows:
        raise ValueError("No calibration rows found.")

    best = None
    best_score = float("inf")
    best_train_metrics = {}
    best_test_metrics = {}

    for c in candidates:
        regime = RegimeConfig(
            name="DAM",
            lower_trigger=c.lower_trigger,
            upper_trigger=c.upper_trigger,
            gamma=c.gamma,
            monthly_cap_up=c.cap_up,
            monthly_cap_down=c.cap_down,
        )
        train_ledger = simulate_monthly_ledger(train_rows, regime)
        train_metrics = summarize_risk(train_ledger)
        score = train_metrics["adjustment_variance"]

        if score < best_score:
            best_score = score
            best = c
            best_train_metrics = train_metrics
            test_ledger = simulate_monthly_ledger(test_rows, regime)
            best_test_metrics = summarize_risk(test_ledger)

    assert best is not None
    return best, best_train_metrics, best_test_metrics
