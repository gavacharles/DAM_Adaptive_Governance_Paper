from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.dpi": 140,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
})


CAL_START = pd.Timestamp("2015-01-01")
CAL_END = pd.Timestamp("2021-12-01")
EVAL_START = pd.Timestamp("2022-01-01")
EVAL_END = pd.Timestamp("2025-12-01")

MC_SIMULATIONS = 1200
MC_SEED = 42
MC_SHOCK_PROB = 0.08
MC_SHOCK_SCALE = 1.8

EXTRA_MACRO_CHANNELS = ["central_bank_rate", "lending_rate", "private_credit"]


PROJECTS = {
    "road": {
        "duration_months": 24,
        "weights": {"AGG": 0.20, "CEM": 0.15, "DIESEL": 0.18, "STEEL": 0.10, "LABOUR": 0.37},
    },
    "building": {
        "duration_months": 18,
        "weights": {"CEM": 0.20, "IRONSTEEL": 0.20, "SAND": 0.10, "TIMBER": 0.10, "PAINT": 0.05, "LABOUR": 0.35},
    },
    "water": {
        "duration_months": 20,
        "weights": {"CEM": 0.15, "IRONSTEEL": 0.20, "PIPES": 0.30, "DIESEL": 0.10, "LABOUR": 0.25},
    },
}


@dataclass(frozen=True)
class Params:
    trigger: float
    gamma_up: float
    gamma_down: float
    cap_up: float
    cap_down: float


@dataclass(frozen=True)
class Regime:
    name: str
    mode: str
    trigger: float
    gamma_up: float
    gamma_down: float
    cap_up: float
    cap_down: float


def _s_curve(n: int) -> np.ndarray:
    x = np.linspace(-3.0, 3.0, n)
    y = 1.0 / (1.0 + np.exp(-x))
    inc = np.diff(np.r_[0, y])
    return inc / inc.sum()


def _zscore(s: pd.Series) -> pd.Series:
    std = s.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / std


def load_inputs(root: Path) -> Tuple[pd.DataFrame, Dict[str, float]]:
    panel_path = root / "cio_pipeline-2" / "data" / "processed" / "panel_v1.0.csv"
    sens_path = root / "cio_pipeline-2" / "p6_sensitivity_vector.json"
    panel = pd.read_csv(panel_path)
    panel.columns = [c.strip() for c in panel.columns]
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.sort_values("date").set_index("date")

    with sens_path.open("r", encoding="utf-8") as f:
        sens = json.load(f)

    fx_anchor = float(np.sqrt(abs(sens.get("exchange_rate_sensitivity", 1.0))))
    cpi_anchor = float(np.sqrt(abs(sens.get("cpi_sensitivity", 1.0))))
    structural_anchor = float(np.mean([fx_anchor, cpi_anchor]) * 0.75)

    raw_weights = {
        "exchange_rate": fx_anchor,
        "cpi": cpi_anchor,
        **{k: structural_anchor for k in EXTRA_MACRO_CHANNELS},
    }

    macro_weights = {k: v for k, v in raw_weights.items() if k in panel.columns and v > 0}
    denom = sum(macro_weights.values())
    if denom <= 0:
        raise ValueError("No valid macro weights available for WMVI construction.")
    macro_weights = {k: v / denom for k, v in macro_weights.items()}
    return panel, macro_weights


def build_cipi_basket_shares(projects: dict) -> Dict[str, float]:
    aggregate: Dict[str, float] = {}
    for cfg in projects.values():
        for k, v in cfg["weights"].items():
            aggregate[k] = aggregate.get(k, 0.0) + v
    total = sum(aggregate.values())
    return {k: v / total for k, v in aggregate.items()}


def build_wmvi(panel: pd.DataFrame, macro_weights: Dict[str, float], basket_weights: Dict[str, float]) -> pd.Series:
    macro_part = 0.0
    for col, w in macro_weights.items():
        r = np.log(pd.to_numeric(panel[col], errors="coerce")).diff().fillna(0.0)
        macro_part = macro_part + w * _zscore(r)

    mat_vol = 0.0
    for col, w in basket_weights.items():
        if col in panel.columns:
            r = np.log(pd.to_numeric(panel[col], errors="coerce")).diff().fillna(0.0)
            vol = r.rolling(6, min_periods=3).std().fillna(0.0)
            mat_vol = mat_vol + w * vol

    wmvi = 0.6 * _zscore(macro_part) + 0.4 * _zscore(mat_vol)
    return wmvi.fillna(0.0)


def project_cost_ratio(panel: pd.DataFrame, project_weights: Dict[str, float]) -> pd.Series:
    w = {k: v for k, v in project_weights.items() if k in panel.columns}
    ws = pd.Series(w, dtype=float)
    ws = ws / ws.sum()
    level = pd.DataFrame({k: pd.to_numeric(panel[k], errors="coerce") for k in ws.index})
    idx = (level * ws).sum(axis=1)
    idx = idx.ffill().bfill()
    base = idx.iloc[0]
    return idx / base


def choose_window(panel: pd.DataFrame, wmvi: pd.Series, duration_months: int) -> pd.DatetimeIndex:
    eligible = panel.loc[(panel.index >= CAL_START) & (panel.index <= EVAL_END)].index
    wmvi_e = wmvi.reindex(eligible)
    score = wmvi_e.abs().rolling(duration_months, min_periods=duration_months).mean()
    end = score.idxmax()
    end_loc = eligible.get_loc(end)
    start_loc = end_loc - duration_months + 1
    return eligible[start_loc : end_loc + 1]


def simulate_regime(
    months: pd.DatetimeIndex,
    payment_shares: np.ndarray,
    cost_ratio: pd.Series,
    wmvi: pd.Series,
    regime: Regime,
) -> pd.DataFrame:
    base_total = 1.0
    baseline = pd.Series(payment_shares * base_total, index=months)

    fixed_cost = baseline * cost_ratio.reindex(months).values
    revenue = baseline.copy()
    adjustments = pd.Series(0.0, index=months)

    for i, dt in enumerate(months):
        p = float(baseline.loc[dt])
        w = float(wmvi.loc[dt])

        if regime.mode == "fixed":
            adj = 0.0
        elif regime.mode == "fidic":
            inflation = float(cost_ratio.loc[dt] - cost_ratio.shift(1).loc[dt]) if i > 0 else 0.0
            adj = 0.60 * inflation * p
        else:  # dam
            if abs(w) > regime.trigger:
                breach = abs(w) - regime.trigger
                direction = 1.0 if (cost_ratio.loc[dt] >= cost_ratio.shift(1).loc[dt] if i > 0 else True) else -1.0
                gamma = regime.gamma_up if direction > 0 else regime.gamma_down
                adj = direction * gamma * breach * p
            else:
                adj = 0.0

        adj = float(np.clip(adj, -regime.cap_down * p, regime.cap_up * p))
        adjustments.loc[dt] = adj
        revenue.loc[dt] += adj

    margin = revenue - fixed_cost
    employer_exposure = adjustments.cumsum()

    out = pd.DataFrame(
        {
            "month": months,
            "base_payment": baseline.values,
            "cost": fixed_cost.values,
            "revenue": revenue.values,
            "adjustment": adjustments.values,
            "margin": margin.values,
            "wmvi": wmvi.reindex(months).values,
            "employer_exposure": employer_exposure.values,
            "regime": regime.name,
        }
    )
    out["event"] = out["adjustment"].abs() > 1e-12
    signed_caps = np.where(out["adjustment"] >= 0, regime.cap_up * out["base_payment"], regime.cap_down * out["base_payment"])
    out["cap_hit"] = (out["adjustment"].abs() >= (np.abs(signed_caps) - 1e-12)) & out["event"]
    return out


def summarize(df: pd.DataFrame, project: str, regime: str) -> dict:
    var_margin = float(df["margin"].var(ddof=0))
    var_budget = float(df["revenue"].var(ddof=0))
    worst_margin = float(df["margin"].min())
    worst_exposure = float(df["employer_exposure"].max())
    return {
        "project": project,
        "regime": regime,
        "margin_variance": var_margin,
        "budget_variance": var_budget,
        "adjustment_count": int(df["event"].sum()),
        "cap_hit_count": int(df["cap_hit"].sum()),
        "worst_margin": worst_margin,
        "max_employer_exposure": worst_exposure,
    }


def run_monte_carlo(project_inputs: Dict[str, dict], best: Params, n_sims: int = MC_SIMULATIONS) -> pd.DataFrame:
    rng = np.random.default_rng(MC_SEED)
    rows: List[dict] = []

    for project, cfg in project_inputs.items():
        months = cfg["months"]
        payment_shares = cfg["payment_shares"]
        cost_ratio_hist = cfg["cost_ratio"].reindex(months).ffill().bfill()
        wmvi_hist = cfg["wmvi"].reindex(months).ffill().bfill()

        ret = np.log(cost_ratio_hist).diff().dropna()
        wmvi_lag = wmvi_hist.iloc[1:]
        empirical = pd.DataFrame({"cost_ret": ret.values, "wmvi": wmvi_lag.values}).dropna()
        if empirical.empty:
            continue

        fixed = Regime("Fixed-price", "fixed", trigger=9.0, gamma_up=0.0, gamma_down=0.0, cap_up=0.0, cap_down=0.0)
        fidic = Regime("FIDIC 13.8", "fidic", trigger=0.0, gamma_up=0.0, gamma_down=0.0, cap_up=0.05, cap_down=0.05)
        dam = Regime(
            "DAM",
            "dam",
            trigger=best.trigger,
            gamma_up=best.gamma_up,
            gamma_down=best.gamma_down,
            cap_up=best.cap_up,
            cap_down=best.cap_down,
        )
        regimes = [fixed, fidic, dam]

        for sim_id in range(1, n_sims + 1):
            sampled_ix = rng.integers(0, len(empirical), size=len(months) - 1)
            sampled = empirical.iloc[sampled_ix].reset_index(drop=True)

            shock_mask = rng.random(len(sampled)) < MC_SHOCK_PROB
            sampled.loc[shock_mask, "cost_ret"] = sampled.loc[shock_mask, "cost_ret"] * MC_SHOCK_SCALE
            sampled.loc[shock_mask, "wmvi"] = sampled.loc[shock_mask, "wmvi"] * MC_SHOCK_SCALE

            cost_path = np.empty(len(months))
            wmvi_path = np.empty(len(months))
            cost_path[0] = 1.0
            wmvi_path[0] = float(wmvi_hist.iloc[0])
            for t in range(1, len(months)):
                cost_path[t] = cost_path[t - 1] * np.exp(float(sampled.loc[t - 1, "cost_ret"]))
                wmvi_path[t] = float(sampled.loc[t - 1, "wmvi"]) + rng.normal(0.0, 0.08)

            sim_cost = pd.Series(cost_path, index=months)
            sim_wmvi = pd.Series(wmvi_path, index=months)

            for rg in regimes:
                ledger = simulate_regime(months, payment_shares, sim_cost, sim_wmvi, rg)
                metrics = summarize(ledger, project=project, regime=rg.name)
                metrics["sim_id"] = sim_id
                rows.append(metrics)

    return pd.DataFrame(rows)


def summarize_monte_carlo(mc_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    agg = (
        mc_df.groupby(["project", "regime"], as_index=False)
        .agg(
            mean_margin_variance=("margin_variance", "mean"),
            p95_margin_variance=("margin_variance", lambda s: float(np.quantile(s, 0.95))),
            mean_adjustment_count=("adjustment_count", "mean"),
            p95_adjustment_count=("adjustment_count", lambda s: float(np.quantile(s, 0.95))),
            mean_max_exposure=("max_employer_exposure", "mean"),
            p95_max_exposure=("max_employer_exposure", lambda s: float(np.quantile(s, 0.95))),
        )
    )

    pivot = mc_df.pivot_table(index=["project", "sim_id"], columns="regime", values="margin_variance", aggfunc="first").reset_index()
    out_rows = []
    for project, g in pivot.groupby("project"):
        dam_better_fixed = float((g["DAM"] < g["Fixed-price"]).mean())
        dam_better_fidic = float((g["DAM"] < g["FIDIC 13.8"]).mean())
        reduction_vs_fixed = (g["Fixed-price"] - g["DAM"]) / g["Fixed-price"]
        reduction_vs_fidic = (g["FIDIC 13.8"] - g["DAM"]) / g["FIDIC 13.8"]
        out_rows.append(
            {
                "project": project,
                "p_dam_beats_fixed": dam_better_fixed,
                "p_dam_beats_fidic": dam_better_fidic,
                "mean_reduction_vs_fixed": float(reduction_vs_fixed.mean()),
                "p05_reduction_vs_fixed": float(np.quantile(reduction_vs_fixed, 0.05)),
                "mean_reduction_vs_fidic": float(reduction_vs_fidic.mean()),
                "p05_reduction_vs_fidic": float(np.quantile(reduction_vs_fidic, 0.05)),
            }
        )

    return agg, pd.DataFrame(out_rows)


def _train_slice(months: pd.DatetimeIndex) -> pd.DatetimeIndex:
    train_months = months[(months >= CAL_START) & (months <= CAL_END)]
    if len(train_months) < 12:
        train_months = months[: max(12, len(months) // 2)]
    return train_months


def calibrate_globally(project_inputs: Dict[str, dict]) -> Tuple[Params, pd.DataFrame]:
    candidates = []
    triggers = np.round(np.arange(0.65, 1.201, 0.05), 3)
    gammas_up = np.round(np.arange(0.03, 0.101, 0.01), 3)
    gammas_down = np.round(np.arange(0.015, 0.051, 0.005), 3)
    caps_up = np.round(np.array([0.008, 0.010, 0.012, 0.015, 0.020, 0.025]), 3)
    caps_down = np.round(np.array([0.008, 0.010, 0.012, 0.015]), 3)

    for trigger in triggers:
        for gamma_up in gammas_up:
            for gamma_down in gammas_down:
                for cap_up in caps_up:
                    for cap_down in caps_down:
                        candidates.append((trigger, gamma_up, gamma_down, cap_up, cap_down))

    rows = []
    for trigger, gamma_up, gamma_down, cap_up, cap_down in candidates:
        dam_regime = Regime("DAM", "dam", trigger, gamma_up, gamma_down, cap_up, cap_down)
        fixed_regime = Regime("Fixed-price", "fixed", 9.0, 0.0, 0.0, 0.0, 0.0)
        fidic_regime = Regime("FIDIC 13.8", "fidic", 0.0, 0.0, 0.0, 0.05, 0.05)

        ratios_fixed = []
        ratios_fidic = []
        improvements_fixed = []
        events = []
        exposures = []
        dom_fidic = 0

        for project, cfg in project_inputs.items():
            months = cfg["months"]
            train_months = _train_slice(months)
            n = len(train_months)
            payment = cfg["payment_shares"][:n]
            cost_ratio = cfg["cost_ratio"]
            wmvi = cfg["wmvi"]

            dam_df = simulate_regime(train_months, payment, cost_ratio, wmvi, dam_regime)
            fix_df = simulate_regime(train_months, payment, cost_ratio, wmvi, fixed_regime)
            fid_df = simulate_regime(train_months, payment, cost_ratio, wmvi, fidic_regime)

            var_dam = float(dam_df["margin"].var(ddof=0))
            var_fix = float(fix_df["margin"].var(ddof=0))
            var_fid = float(fid_df["margin"].var(ddof=0))
            ratio_fix = var_dam / max(var_fix, 1e-12)
            ratio_fid = var_dam / max(var_fid, 1e-12)

            ratios_fixed.append(ratio_fix)
            ratios_fidic.append(ratio_fid)
            improvements_fixed.append(1.0 - ratio_fix)
            events.append(int(dam_df["event"].sum()))
            exposures.append(float(dam_df["employer_exposure"].max()))
            if var_dam <= var_fid:
                dom_fidic += 1

        feasible = (
            float(np.mean(ratios_fixed)) <= 1.0
            and float(np.max(ratios_fixed)) <= 1.05
            and float(np.mean(ratios_fidic)) <= 1.08
            and int(np.max(events)) <= 8
            and float(np.max(exposures)) <= 0.02
        )

        score = (
            0.50 * float(np.mean(ratios_fixed))
            + 0.35 * float(np.mean(ratios_fidic))
            + 0.15 * float(np.max(ratios_fixed))
            - 0.10 * float(np.min(improvements_fixed))
        )

        if not feasible:
            score += 10.0

        rows.append(
            {
                "trigger": trigger,
                "gamma_up": gamma_up,
                "gamma_down": gamma_down,
                "cap_up": cap_up,
                "cap_down": cap_down,
                "objective": score,
                "feasible": int(feasible),
                "mean_ratio_fixed": float(np.mean(ratios_fixed)),
                "mean_ratio_fidic": float(np.mean(ratios_fidic)),
                "max_ratio_fixed": float(np.max(ratios_fixed)),
                "min_improvement_fixed": float(np.min(improvements_fixed)),
                "mean_events": float(np.mean(events)),
                "max_events": int(np.max(events)),
                "max_exposure": float(np.max(exposures)),
                "dom_fidic_count": int(dom_fidic),
            }
        )

    grid_df = pd.DataFrame(rows).sort_values(["feasible", "objective"], ascending=[False, True]).reset_index(drop=True)
    best = grid_df.iloc[0]
    return Params(
        trigger=float(best["trigger"]),
        gamma_up=float(best["gamma_up"]),
        gamma_down=float(best["gamma_down"]),
        cap_up=float(best["cap_up"]),
        cap_down=float(best["cap_down"]),
    ), grid_df


def plot_formula(out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis("off")
    formula_text = "\n\n".join(
        [
            r"$\mathrm{WMVI}_t = \sum_{k=1}^{K} w_k z_{k,t}$",
            r"$B_t = \max(\mathrm{WMVI}_t-U,0) + \min(\mathrm{WMVI}_t-L,0)$",
            r"$\Delta P_t = \mathrm{clip}(\gamma_{up} B_t^+ P_t - \gamma_{down} B_t^- P_t, -C^-_t, C^+_t)$",
        ]
    )
    ax.text(0.05, 0.70, formula_text, fontsize=18, va="top")
    ax.text(
        0.05,
        0.16,
        "Terms: P_t = eligible interim payment; B_t^+, B_t^- = positive/negative breaches; "
        "gamma_up, gamma_down = asymmetric responsiveness; C^+, C^- = cap/collar bounds.",
        fontsize=12,
    )
    fig.suptitle("Dynamic Adjustment Mechanism (DAM) — Updated Clause Formula", fontsize=16)
    fig.tight_layout()
    fig.savefig(out_dir / "dam_formula.png", dpi=180)
    plt.close(fig)


def plot_risk_exposure(ledger: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    style_map = {
        "Fixed-price": {"linestyle": "--", "linewidth": 2.2},
        "FIDIC 13.8": {"linestyle": "-.", "linewidth": 2.0},
        "DAM": {"linestyle": "-", "linewidth": 2.8},
    }
    for regime, g in ledger.groupby("regime"):
        s = g.groupby("month")["margin"].mean()
        ax.plot(s.index, s.values, label=regime, **style_map.get(regime, {"linewidth": 2.0}))

    ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2021-06-01"), color="gray", alpha=0.2, label="COVID window")
    ax.axvspan(pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-01"), color="orange", alpha=0.2, label="2022 shock")
    ax.set_title("Risk Exposure Comparison: Margin Path by Contract Regime (Updated)")
    ax.set_ylabel("Margin (normalised)")
    ax.set_xlabel("Month")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_dir / "risk_exposure_comparison.png", dpi=180)
    plt.close(fig)


def plot_sensitivity_surface(calib: pd.DataFrame, out_dir: Path) -> None:
    p = calib.copy()
    p["trigger_label"] = p["trigger"].map(lambda x: f"{x:.2f}")
    p["cap_label"] = p["cap_up"].map(lambda x: f"{x:.3f}")
    piv = p.pivot_table(index="trigger_label", columns="cap_label", values="objective", aggfunc="mean")

    fig, ax = plt.subplots(figsize=(8, 5))
    m = ax.imshow(piv.values, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels(piv.index)
    ax.set_xlabel("Cap fraction")
    ax.set_ylabel("Trigger")
    ax.set_title("Parameter Surface (Lower is better)")
    fig.colorbar(m, ax=ax, label="Objective")
    fig.tight_layout()
    fig.savefig(out_dir / "trigger_cap_surface.png", dpi=180)
    plt.close(fig)


def plot_admin_frontier(calib: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    sc = ax.scatter(calib["mean_events"], calib["mean_ratio_fixed"], c=calib["objective"], cmap="plasma", alpha=0.8)
    ax.set_xlabel("Mean adjustment event count")
    ax.set_ylabel("Mean DAM/Fixed margin-variance ratio")
    ax.set_title("Administrative Burden Frontier")
    fig.colorbar(sc, ax=ax, label="Objective")
    fig.tight_layout()
    fig.savefig(out_dir / "admin_burden_frontier.png", dpi=180)
    plt.close(fig)


def plot_stress_caps(base_df: pd.DataFrame, regime: Regime, out_dir: Path) -> None:
    shocked = base_df.copy()
    shocked["wmvi"] = shocked["wmvi"] * 1.8
    shocked["base_payment"] = shocked["base_payment"]

    p = shocked["base_payment"].values
    w = shocked["wmvi"].values
    upward = regime.gamma_up * np.maximum(np.abs(w) - regime.trigger, 0.0) * p
    downward = regime.gamma_down * np.maximum(np.abs(w) - regime.trigger, 0.0) * p
    uncapped = np.where(w >= 0, upward, -downward)
    capped = np.clip(uncapped, -regime.cap_down * p, regime.cap_up * p)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(shocked["month"], uncapped, label="Uncapped adjustment", linewidth=1.8)
    ax.plot(shocked["month"], capped, label="Capped DAM adjustment", linewidth=2.2)
    ax.set_title("Stress Scenario: Cap Behaviour Under Tail Shock")
    ax.set_xlabel("Month")
    ax.set_ylabel("Adjustment")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_dir / "stress_cap_behavior.png", dpi=180)
    plt.close(fig)


def plot_wmvi_timeline(wmvi: pd.Series, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(wmvi.index, wmvi.values, color="tab:blue", linewidth=1.6)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2021-06-01"), color="gray", alpha=0.2)
    ax.axvspan(pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-01"), color="orange", alpha=0.2)
    ax.set_title("WMVI Timeline with Shock Windows")
    ax.set_xlabel("Month")
    ax.set_ylabel("WMVI (z-score)")
    fig.tight_layout()
    fig.savefig(out_dir / "wmvi_timeline.png", dpi=180)
    plt.close(fig)


def plot_summary_bars(summary_df: pd.DataFrame, out_dir: Path) -> None:
    regimes = ["Fixed-price", "FIDIC 13.8", "DAM"]
    projects = ["road", "building", "water"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    width = 0.25
    x = np.arange(len(projects))

    for i, regime in enumerate(regimes):
        subset = (
            summary_df[summary_df["regime"] == regime]
            .set_index("project")
            .reindex(projects)
        )
        axes[0].bar(x + (i - 1) * width, subset["margin_variance"].values, width=width, label=regime)
        axes[1].bar(x + (i - 1) * width, subset["budget_variance"].values, width=width, label=regime)

    for ax, ttl, ylbl in [
        (axes[0], "Margin Variance by Regime", "Variance"),
        (axes[1], "Budget Variance by Regime", "Variance"),
    ]:
        ax.set_xticks(x)
        ax.set_xticklabels(projects)
        ax.set_title(ttl)
        ax.set_ylabel(ylbl)
        ax.legend(fontsize=8)

    for ax in axes:
        for p in ax.patches:
            h = p.get_height()
            ax.annotate(f"{h:.1e}", (p.get_x() + p.get_width() / 2.0, h), ha="center", va="bottom", fontsize=7, rotation=90)

    fig.tight_layout()
    fig.savefig(out_dir / "variance_comparison_bars.png", dpi=180)
    plt.close(fig)


def plot_event_counts(summary_df: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    d = summary_df.copy()
    x_labels = [f"{p}\n{r}" for p, r in zip(d["project"], d["regime"])]
    ax.bar(np.arange(len(d)), d["adjustment_count"].values, color="tab:green")
    ax.set_xticks(np.arange(len(d)))
    ax.set_xticklabels(x_labels, rotation=30, ha="right")
    ax.set_title("Adjustment Event Counts Across All Results")
    ax.set_ylabel("Count")
    fig.tight_layout()
    fig.savefig(out_dir / "adjustment_event_counts.png", dpi=180)
    plt.close(fig)


def plot_project_margin_paths(ledger: pd.DataFrame, out_dir: Path) -> None:
    projects = ["road", "building", "water"]
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    for ax, project in zip(axes, projects):
        g = ledger[ledger["project"] == project]
        for regime, rg in g.groupby("regime"):
            s = rg.groupby("month")["margin"].mean()
            ax.plot(s.index, s.values, label=regime, linewidth=1.8)
        ax.set_title(f"{project.title()} project margin path")
        ax.set_ylabel("Margin")
        ax.legend(fontsize=8)
    axes[-1].set_xlabel("Month")
    fig.tight_layout()
    fig.savefig(out_dir / "project_margin_paths.png", dpi=180)
    plt.close(fig)


def plot_mc_reduction_distribution(mc_df: pd.DataFrame, out_dir: Path) -> None:
    p = mc_df.pivot_table(index=["project", "sim_id"], columns="regime", values="margin_variance", aggfunc="first").reset_index()
    p["reduction_vs_fixed"] = (p["Fixed-price"] - p["DAM"]) / p["Fixed-price"]
    p["reduction_vs_fidic"] = (p["FIDIC 13.8"] - p["DAM"]) / p["FIDIC 13.8"]

    projects = ["road", "building", "water"]
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharex="col")
    for i, proj in enumerate(projects):
        gp = p[p["project"] == proj]
        axes[i, 0].hist(gp["reduction_vs_fixed"], bins=30, color="tab:blue", alpha=0.85)
        axes[i, 1].hist(gp["reduction_vs_fidic"], bins=30, color="tab:purple", alpha=0.85)
        axes[i, 0].axvline(0, color="black", linewidth=1)
        axes[i, 1].axvline(0, color="black", linewidth=1)
        axes[i, 0].set_ylabel(f"{proj.title()}\ncount")
    axes[0, 0].set_title("DAM reduction vs Fixed")
    axes[0, 1].set_title("DAM reduction vs FIDIC 13.8")
    axes[-1, 0].set_xlabel("Fractional reduction")
    axes[-1, 1].set_xlabel("Fractional reduction")
    fig.tight_layout()
    fig.savefig(out_dir / "mc_reduction_distributions.png", dpi=180)
    plt.close(fig)


def plot_mc_outperformance_prob(mc_out: pd.DataFrame, out_dir: Path) -> None:
    x = np.arange(len(mc_out))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - width / 2, mc_out["p_dam_beats_fixed"], width=width, label="P(DAM beats Fixed)")
    ax.bar(x + width / 2, mc_out["p_dam_beats_fidic"], width=width, label="P(DAM beats FIDIC)")
    ax.set_xticks(x)
    ax.set_xticklabels(mc_out["project"].str.title())
    ax.set_ylim(0, 1)
    ax.set_ylabel("Probability")
    ax.set_title("Monte Carlo Outperformance Probabilities")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_dir / "mc_outperformance_probabilities.png", dpi=180)
    plt.close(fig)


def plot_mc_exposure_ecdf(mc_df: pd.DataFrame, out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for regime, g in mc_df.groupby("regime"):
        x = np.sort(g["max_employer_exposure"].values)
        y = np.arange(1, len(x) + 1) / len(x)
        ax.plot(x, y, linewidth=2.0, label=regime)
    ax.set_xlabel("Max employer exposure")
    ax.set_ylabel("Empirical CDF")
    ax.set_title("Monte Carlo Exposure Distribution by Regime")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_dir / "mc_exposure_ecdf.png", dpi=180)
    plt.close(fig)


def main() -> None:
    code_root = Path(__file__).resolve().parent
    paper_root = code_root.parent
    workspace_root = paper_root.parent.parent

    out_data = paper_root / "results" / "tables"
    out_fig = paper_root / "results" / "figures"
    out_input = paper_root / "data" / "inputs"
    out_data.mkdir(parents=True, exist_ok=True)
    out_fig.mkdir(parents=True, exist_ok=True)
    out_input.mkdir(parents=True, exist_ok=True)

    panel, macro_weights = load_inputs(workspace_root)
    pd.DataFrame({"macro_component": list(macro_weights.keys()), "weight": list(macro_weights.values())}).to_csv(
        out_data / "wmvi_macro_weights.csv", index=False
    )
    basket_shares = build_cipi_basket_shares(PROJECTS)
    pd.DataFrame({"component": list(basket_shares.keys()), "share": list(basket_shares.values())}).to_csv(
        out_input / "cipi_basket_shares.csv", index=False
    )

    wmvi = build_wmvi(panel, macro_weights, basket_shares)
    wmvi.to_frame("wmvi").reset_index().rename(columns={"index": "date"}).to_csv(out_data / "wmvi_series.csv", index=False)

    all_ledgers: List[pd.DataFrame] = []
    summary_rows: List[dict] = []
    project_inputs: Dict[str, dict] = {}

    for project, cfg in PROJECTS.items():
        cost_ratio = project_cost_ratio(panel, cfg["weights"])
        months = choose_window(panel, wmvi, cfg["duration_months"])
        payment_shares = _s_curve(len(months))
        project_inputs[project] = {
            "months": months,
            "payment_shares": payment_shares,
            "cost_ratio": cost_ratio,
            "wmvi": wmvi,
        }

    best, calib_df = calibrate_globally(project_inputs)

    for project, cfg in PROJECTS.items():
        months = project_inputs[project]["months"]
        payment_shares = project_inputs[project]["payment_shares"]
        cost_ratio = project_inputs[project]["cost_ratio"]

        regimes = [
            Regime("Fixed-price", "fixed", trigger=9.0, gamma_up=0.0, gamma_down=0.0, cap_up=0.0, cap_down=0.0),
            Regime("FIDIC 13.8", "fidic", trigger=0.0, gamma_up=0.0, gamma_down=0.0, cap_up=0.05, cap_down=0.05),
            Regime(
                "DAM",
                "dam",
                trigger=best.trigger,
                gamma_up=best.gamma_up,
                gamma_down=best.gamma_down,
                cap_up=best.cap_up,
                cap_down=best.cap_down,
            ),
        ]

        for rg in regimes:
            ledger = simulate_regime(months, payment_shares, cost_ratio, wmvi, rg)
            ledger["project"] = project
            all_ledgers.append(ledger)
            summary_rows.append(summarize(ledger, project=project, regime=rg.name))

    ledger_all = pd.concat(all_ledgers, ignore_index=True)
    summary_df = pd.DataFrame(summary_rows)

    summary_df.to_csv(out_data / "backtest_summary.csv", index=False)
    ledger_all.to_csv(out_data / "monthly_ledger.csv", index=False)
    calib_df.to_csv(out_data / "calibration_manifest.csv", index=False)
    pd.DataFrame(
        [
            {
                "parameter_scope": "global",
                "trigger": best.trigger,
                "gamma_up": best.gamma_up,
                "gamma_down": best.gamma_down,
                "cap_up": best.cap_up,
                "cap_down": best.cap_down,
            }
        ]
    ).to_csv(out_data / "selected_parameters.csv", index=False)

    mc_df = run_monte_carlo(project_inputs, best, n_sims=MC_SIMULATIONS)
    mc_summary_df, mc_outperf_df = summarize_monte_carlo(mc_df)
    mc_df.to_csv(out_data / "monte_carlo_metrics.csv", index=False)
    mc_summary_df.to_csv(out_data / "monte_carlo_summary.csv", index=False)
    mc_outperf_df.to_csv(out_data / "monte_carlo_outperformance.csv", index=False)

    plot_formula(out_fig)
    plot_wmvi_timeline(wmvi, out_fig)
    plot_risk_exposure(ledger_all, out_fig)
    plot_sensitivity_surface(calib_df, out_fig)
    plot_admin_frontier(calib_df, out_fig)
    plot_summary_bars(summary_df, out_fig)
    plot_event_counts(summary_df, out_fig)
    plot_project_margin_paths(ledger_all, out_fig)
    plot_mc_reduction_distribution(mc_df, out_fig)
    plot_mc_outperformance_prob(mc_outperf_df, out_fig)
    plot_mc_exposure_ecdf(mc_df, out_fig)
    dam_first = ledger_all[(ledger_all["project"] == "road") & (ledger_all["regime"] == "DAM")].copy()
    stress_regime = Regime(
        "DAM",
        "dam",
        trigger=best.trigger,
        gamma_up=best.gamma_up,
        gamma_down=best.gamma_down,
        cap_up=best.cap_up,
        cap_down=best.cap_down,
    )
    plot_stress_caps(dam_first, stress_regime, out_fig)

    print("Experiment complete.")
    print(f"Tables: {out_data}")
    print(f"Figures: {out_fig}")
    print(f"Monte Carlo simulations: {MC_SIMULATIONS}")


if __name__ == "__main__":
    main()
