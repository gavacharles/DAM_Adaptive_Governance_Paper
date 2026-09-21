"""Retrofit DAM / FIDIC-as-applied / Fixed-price onto a real certificate record.

Used for the manuscript's Section 6.7 real-project validation (see Appendix C for the
derivation of the input series from the underlying contract IPC workbook). Kept separate
from dam_engine.py because the real record carries its own realised cost-index ratio and
as-applied FIDIC factor per certificate, rather than a simulated WMVI/cost path.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RetrofitParams:
    lambda_share: float
    deadband: float
    cap_up: float
    cap_down: float


def simulate_real_regime(df: pd.DataFrame, mode: str, params: RetrofitParams) -> pd.DataFrame:
    """Simulate one regime over a real certificate series.

    `df` must carry, per certificate row (already sorted chronologically):
      - base_amount_ugx: certified base amount subject to adjustment.
      - cost_ratio: realised cumulative cost-index ratio R_t for that certificate.
      - a_fidic_real: the contract's actual as-applied Sub-Clause 13.8 factor (R_t - 1).

    mode: "fixed" | "fidic_real" | "dam".
    """
    a_prev = 0.0
    a_list, adj_list, event_list = [], [], []
    for _, row in df.iterrows():
        base = row["base_amount_ugx"]
        rt = row["cost_ratio"]
        entitlement = params.lambda_share * (rt - 1.0)
        target = float(np.clip(entitlement, -params.cap_down, params.cap_up))

        if mode == "fixed":
            a_t = 0.0
        elif mode == "fidic_real":
            a_t = float(row["a_fidic_real"])
        elif mode == "dam":
            a_t = target if abs(target - a_prev) >= params.deadband else a_prev
        else:
            raise ValueError(f"Unknown mode: {mode}")

        adj = a_t * base
        event_list.append(abs(a_t - a_prev) > 1e-12)
        a_list.append(a_t)
        adj_list.append(adj)
        a_prev = a_t

    out = df.copy()
    out["applied_factor"] = a_list
    out["adjustment"] = adj_list
    out["event"] = event_list
    # Residual (uncompensated) cost-index exposure left with the contractor. Non-circular:
    # it is exactly zero for fidic_real only because that clause is defined as full,
    # uncapped, undead-banded pass-through of the same R_t -- a real property of this
    # contract's clause, not an estimation artefact.
    out["residual_gap"] = (out["cost_ratio"] - 1.0) - out["applied_factor"]
    out["residual_exposure_ugx"] = out["residual_gap"] * out["base_amount_ugx"]
    out["revenue"] = out["base_amount_ugx"] + out["adjustment"]
    out["employer_exposure"] = out["adjustment"].cumsum()
    out["regime"] = mode
    return out


def summarize_real_regime(g: pd.DataFrame) -> dict:
    return {
        "residual_exposure_variance_ugx2": float(g["residual_exposure_ugx"].var(ddof=0)),
        "residual_exposure_std_ugx": float(g["residual_exposure_ugx"].std(ddof=0)),
        "worst_residual_exposure_ugx": float(g["residual_exposure_ugx"].abs().max()),
        "adjustment_events": int(g["event"].sum()),
        "total_compensation_ugx": float(g["adjustment"].clip(lower=0).sum()),
        "max_employer_exposure_ugx": float(g["employer_exposure"].max()),
        "final_employer_exposure_ugx": float(g["employer_exposure"].iloc[-1]),
    }


def _dam_leg(cost_ratio: np.ndarray, base: np.ndarray, params: RetrofitParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run the DAM entitlement/deadband/cap rule over one currency leg."""
    a_prev = 0.0
    a_list, adj_list, event_list = [], [], []
    for rt, b in zip(cost_ratio, base):
        entitlement = params.lambda_share * (rt - 1.0)
        target = float(np.clip(entitlement, -params.cap_down, params.cap_up))
        a_t = target if abs(target - a_prev) >= params.deadband else a_prev
        event_list.append(abs(a_t - a_prev) > 1e-12)
        a_list.append(a_t)
        adj_list.append(a_t * b)
        a_prev = a_t
    return np.array(a_list), np.array(adj_list), np.array(event_list, dtype=bool)


def simulate_real_regime_split(df: pd.DataFrame, params: RetrofitParams) -> pd.DataFrame:
    """DAM applied independently to the local and foreign currency legs.

    Matches how this contract's own Sub-Clause 13.8 worksheets are actually administered
    (a separate local-currency and foreign-currency price-adjustment factor each
    certificate), rather than the single blended factor used by `simulate_real_regime`.
    `df` must carry base_amount_local_ugx, base_amount_foreign_usd, pn_local, pn_foreign,
    base_amount_ugx, cost_ratio, and the contractual FX rate baked into base_amount_ugx.
    A certificate counts as an "event" if either leg updates.
    """
    a_local, adj_local, ev_local = _dam_leg(df["pn_local"].values, df["base_amount_local_ugx"].values, params)
    fx = float(df["base_amount_ugx"].iloc[0] - df["base_amount_local_ugx"].iloc[0]) / float(df["base_amount_foreign_usd"].iloc[0])
    a_foreign, adj_foreign_usd, ev_foreign = _dam_leg(df["pn_foreign"].values, df["base_amount_foreign_usd"].values, params)
    adj_foreign_ugx = adj_foreign_usd * fx
    adjustment = adj_local + adj_foreign_ugx
    event = ev_local | ev_foreign

    out = df.copy()
    out["applied_factor"] = adjustment / out["base_amount_ugx"]
    out["adjustment"] = adjustment
    out["event"] = event
    out["residual_gap"] = (out["cost_ratio"] - 1.0) - out["applied_factor"]
    out["residual_exposure_ugx"] = out["residual_gap"] * out["base_amount_ugx"]
    out["revenue"] = out["base_amount_ugx"] + out["adjustment"]
    out["employer_exposure"] = out["adjustment"].cumsum()
    out["regime"] = "dam_split"
    return out


def deadband_sensitivity_sweep(df: pd.DataFrame, base_params: RetrofitParams, deltas: np.ndarray) -> pd.DataFrame:
    """Sweep the deadband only (lambda/caps held at base_params) to test basket-specific
    tuning of the real-project retrofit, isolating the parameter the manuscript's own
    calibration flags as basket-sensitive."""
    fidic = simulate_real_regime(df, "fidic_real", base_params)
    fidic_summary = summarize_real_regime(fidic)
    fixed = simulate_real_regime(df, "fixed", base_params)
    fixed_var = summarize_real_regime(fixed)["residual_exposure_variance_ugx2"]

    rows = []
    for delta in deltas:
        p = RetrofitParams(base_params.lambda_share, float(delta), base_params.cap_up, base_params.cap_down)
        dam = simulate_real_regime(df, "dam", p)
        s = summarize_real_regime(dam)
        rows.append({
            "delta": float(delta),
            "events": s["adjustment_events"],
            "event_ratio_vs_fidic_pct": s["adjustment_events"] / fidic_summary["adjustment_events"] * 100,
            "compensation_ratio_vs_fidic_pct": s["total_compensation_ugx"] / fidic_summary["total_compensation_ugx"] * 100,
            "residual_std_ugx_bn": s["residual_exposure_std_ugx"] / 1e9,
            "risk_reduction_vs_fixed_pct": (1 - s["residual_exposure_variance_ugx2"] / fixed_var) * 100,
        })
    return pd.DataFrame(rows)


def capdown_sensitivity_sweep(df: pd.DataFrame, base_params: RetrofitParams, cap_downs: np.ndarray) -> pd.DataFrame:
    """Sweep the downside cap only (lambda/deadband/cap_up held at base_params)."""
    fidic = simulate_real_regime(df, "fidic_real", base_params)
    fidic_paid = summarize_real_regime(fidic)["total_compensation_ugx"]
    fixed = simulate_real_regime(df, "fixed", base_params)
    fixed_var = summarize_real_regime(fixed)["residual_exposure_variance_ugx2"]

    rows = []
    for cd in cap_downs:
        p = RetrofitParams(base_params.lambda_share, base_params.deadband, base_params.cap_up, float(cd))
        dam = simulate_real_regime(df, "dam", p)
        s = summarize_real_regime(dam)
        rows.append({
            "cap_down": float(cd),
            "events": s["adjustment_events"],
            "compensation_ratio_vs_fidic_pct": s["total_compensation_ugx"] / fidic_paid * 100,
            "residual_std_ugx_bn": s["residual_exposure_std_ugx"] / 1e9,
            "risk_reduction_vs_fixed_pct": (1 - s["residual_exposure_variance_ugx2"] / fixed_var) * 100,
        })
    return pd.DataFrame(rows)


def shock_proxy_zscore(cost_ratio: np.ndarray, window: int | None = None) -> np.ndarray:
    """Certificate-level shock-detection proxy, built the same way build_wmvi() in
    run_experiment.py builds volatility (z-scored log/level changes, optionally
    rolling). window=None uses the single-step change; window=k uses a rolling
    k-certificate standard deviation of that change (matches build_wmvi()'s
    rolling(6, min_periods=3) pattern, shortened for this record's 38 points)."""
    delta = np.diff(cost_ratio, prepend=cost_ratio[0])
    if window is None:
        signal = delta
    else:
        signal = pd.Series(delta).rolling(window, min_periods=max(2, window - 1)).std().fillna(0.0).values
    std = signal.std(ddof=0)
    if std == 0:
        return np.zeros_like(signal)
    return (signal - signal.mean()) / std


def simulate_real_regime_adaptive(df: pd.DataFrame, params: RetrofitParams, proxy: np.ndarray, fast_trigger: float) -> pd.DataFrame:
    """DAM with the fast-trigger channel re-enabled: bypasses the deadband whenever the
    shock proxy exceeds `fast_trigger`, using the SAME candidate thresholds (1.25, 1.50)
    already in the paper's own global calibration grid (calibrate_globally() in
    run_experiment.py), not a value newly fit to this one contract."""
    a_prev = 0.0
    a_list, adj_list, event_list = [], [], []
    for (_, row), z in zip(df.iterrows(), proxy):
        base = row["base_amount_ugx"]
        rt = row["cost_ratio"]
        entitlement = params.lambda_share * (rt - 1.0)
        target = float(np.clip(entitlement, -params.cap_down, params.cap_up))
        fast_gate = abs(z) >= fast_trigger
        a_t = target if (abs(target - a_prev) >= params.deadband or fast_gate) else a_prev
        event_list.append(abs(a_t - a_prev) > 1e-12)
        a_list.append(a_t)
        adj_list.append(a_t * base)
        a_prev = a_t

    out = df.copy()
    out["applied_factor"] = a_list
    out["adjustment"] = adj_list
    out["event"] = event_list
    out["residual_gap"] = (out["cost_ratio"] - 1.0) - out["applied_factor"]
    out["residual_exposure_ugx"] = out["residual_gap"] * out["base_amount_ugx"]
    out["revenue"] = out["base_amount_ugx"] + out["adjustment"]
    out["employer_exposure"] = out["adjustment"].cumsum()
    out["regime"] = "dam_adaptive"
    return out


def moving_block_bootstrap_ci(
    df: pd.DataFrame,
    base_params: RetrofitParams,
    n_boot: int = 2000,
    block_len: int = 6,
    seed: int = 42,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Moving-block bootstrap confidence intervals for the §6.7 headline metrics.

    Plain iid resampling of certificates is invalid here because DAM's deadband/cap
    rule is path-dependent (a_t depends on a_{t-1}) and the cost-ratio series is
    serially correlated -- resampling would break both. Instead this draws overlapping
    blocks of `block_len` consecutive certificates (with replacement) from the real
    chronological record and concatenates them into a resampled path of the same
    length, preserving local time-dependence within each block (Kunsch, 1989 moving-block
    bootstrap), then re-runs the exact same regime simulation on each resampled path.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    starts = np.arange(0, n - block_len + 1)

    rows = {"fixed": [], "fidic_real": [], "dam": []}
    for _ in range(n_boot):
        n_blocks = int(np.ceil(n / block_len))
        chosen = rng.choice(starts, size=n_blocks, replace=True)
        idx = np.concatenate([np.arange(s, s + block_len) for s in chosen])[:n]
        resampled = df.iloc[idx].reset_index(drop=True)
        for mode in rows:
            s = summarize_real_regime(simulate_real_regime(resampled, mode, base_params))
            rows[mode].append(s)

    out_rows = []
    fixed_var_point = np.array([r["residual_exposure_variance_ugx2"] for r in rows["fixed"]])
    for mode in rows:
        recs = rows[mode]
        risk_reduction = 1 - np.array([r["residual_exposure_variance_ugx2"] for r in recs]) / np.maximum(fixed_var_point, 1e-12)
        events = np.array([r["adjustment_events"] for r in recs])
        comp = np.array([r["total_compensation_ugx"] for r in recs])
        lo, hi = alpha / 2 * 100, (1 - alpha / 2) * 100
        out_rows.append({
            "regime": mode,
            "risk_reduction_vs_fixed_pct_median": float(np.median(risk_reduction) * 100),
            "risk_reduction_vs_fixed_pct_lo": float(np.percentile(risk_reduction, lo) * 100),
            "risk_reduction_vs_fixed_pct_hi": float(np.percentile(risk_reduction, hi) * 100),
            "events_median": float(np.median(events)),
            "events_lo": float(np.percentile(events, lo)),
            "events_hi": float(np.percentile(events, hi)),
            "compensation_ugx_bn_median": float(np.median(comp) / 1e9),
            "compensation_ugx_bn_lo": float(np.percentile(comp, lo) / 1e9),
            "compensation_ugx_bn_hi": float(np.percentile(comp, hi) / 1e9),
        })
    return pd.DataFrame(out_rows)


def minmax_normalize(x: np.ndarray) -> np.ndarray:
    """0 = best (lowest), 1 = worst (highest); constant series maps to all-zero."""
    lo, hi = x.min(), x.max()
    if hi - lo == 0:
        return np.zeros_like(x, dtype=float)
    return (x - lo) / (hi - lo)


def composite_weight_simplex(
    metrics: dict[str, dict[str, float]],
    step: float = 0.01,
    power: float = 1.0,
) -> pd.DataFrame:
    """Sweep the full weight simplex (w_risk + w_burden + w_exposure = 1) and record which
    regime achieves the lowest composite score at each weight combination.

    `metrics`: {regime_name: {"risk": ..., "burden": ..., "exposure": ...}} (lower=better
    on the raw scale for every metric). Each dimension is min-max normalised across the
    regimes first (0=best,1=worst), then raised to `power` before weighting -- power=1.0
    is a standard linear multi-criteria score; power>1.0 models risk-averse (convex)
    preferences over extreme outcomes, a standard device in decision theory.
    """
    names = list(metrics.keys())
    risk = np.array([metrics[n]["risk"] for n in names])
    burden = np.array([metrics[n]["burden"] for n in names])
    exposure = np.array([metrics[n]["exposure"] for n in names])

    nr = minmax_normalize(risk) ** power
    nb = minmax_normalize(burden) ** power
    ne = minmax_normalize(exposure) ** power

    rows = []
    w1 = 0.0
    while w1 <= 1.0 + 1e-9:
        w2 = 0.0
        while w2 <= 1.0 - w1 + 1e-9:
            w3 = 1.0 - w1 - w2
            scores = w1 * nr + w2 * nb + w3 * ne
            winner = names[int(np.argmin(scores))]
            rows.append({"w_risk": w1, "w_burden": w2, "w_exposure": w3, "winner": winner})
            w2 += step
        w1 += step
    return pd.DataFrame(rows)
