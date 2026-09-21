"""Three follow-up checks on whether DAM can be made to outperform the real contract's
as-applied FIDIC 13.8 clause, using only this project's own data:

  (1) Framing: quantify how DAM performs against the realistic "rigid escalation" baseline
      this paper is actually about (Fixed-price), not just this unusually well-designed
      real clause -- reuses results already computed in real_project_experiment.py.
  (2) Composite objective: does DAM dominate FIDIC (and Fixed-price) once administrative
      burden and employer exposure are weighed alongside pure risk reduction, rather than
      risk reduction alone? Sweeps the full weight simplex, at several risk-aversion
      curvatures, and reports where each regime is preferred.
  (3) Shock-adaptive DAM: does re-enabling the existing fast-trigger channel (already part
      of the paper's calibration grid; not a new parameter fit to this contract) close any
      of the risk gap versus full FIDIC indexation?

    python real_project_frontier.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from contract.real_project import (
    RetrofitParams,
    composite_weight_simplex,
    shock_proxy_zscore,
    simulate_real_regime,
    simulate_real_regime_adaptive,
    summarize_real_regime,
)

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.dpi": 140,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
})


def ternary_xy(w_burden: np.ndarray, w_exposure: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Barycentric (w_risk, w_burden, w_exposure) -> Cartesian, risk at origin,
    burden at (1,0), exposure at (0.5, sqrt(3)/2)."""
    x = w_burden + 0.5 * w_exposure
    y = (np.sqrt(3) / 2) * w_exposure
    return x, y


def plot_ternary(grid: pd.DataFrame, title: str, out_path: Path, colors: dict[str, str]) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 7))
    x, y = ternary_xy(grid["w_burden"].values, grid["w_exposure"].values)
    for name, color in colors.items():
        mask = grid["winner"] == name
        ax.scatter(x[mask], y[mask], s=6, color=color, label=name, marker="s")
    ax.plot([0, 1, 0.5, 0], [0, 0, np.sqrt(3) / 2, 0], color="black", linewidth=1.2)
    ax.text(-0.03, -0.03, "w_risk=1\n(risk)", ha="right", va="top", fontsize=9)
    ax.text(1.03, -0.03, "w_burden=1\n(burden)", ha="left", va="top", fontsize=9)
    ax.text(0.5, np.sqrt(3) / 2 + 0.03, "w_exposure=1\n(exposure)", ha="center", va="bottom", fontsize=9)
    ax.set_xlim(-0.15, 1.15)
    ax.set_ylim(-0.15, 1.0)
    ax.axis("off")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> None:
    code_root = Path(__file__).resolve().parent
    paper_root = code_root.parent
    in_path = paper_root / "data" / "inputs" / "real_project_ipc_series.csv"
    params_path = paper_root / "results" / "tables" / "selected_parameters.csv"
    out_tables = paper_root / "results" / "tables"
    out_figs = paper_root / "results" / "figures"

    df = pd.read_csv(in_path, parse_dates=["period_from", "period_to", "submission_date", "approved_date"])
    df = df.sort_values("period_to").reset_index(drop=True)

    sel = pd.read_csv(params_path).iloc[0]
    base_params = RetrofitParams(
        lambda_share=float(sel["lambda_share"]),
        deadband=float(sel["deadband"]),
        cap_up=float(sel["cap_up"]),
        cap_down=float(sel["cap_down"]),
    )

    fixed = summarize_real_regime(simulate_real_regime(df, "fixed", base_params))
    fidic = summarize_real_regime(simulate_real_regime(df, "fidic_real", base_params))
    dam = summarize_real_regime(simulate_real_regime(df, "dam", base_params))

    metrics = {
        "Fixed-price": {
            "risk": fixed["residual_exposure_std_ugx"] / 1e9,
            "burden": fixed["adjustment_events"],
            "exposure": fixed["max_employer_exposure_ugx"] / 1e9,
        },
        "FIDIC 13.8 (as applied)": {
            "risk": fidic["residual_exposure_std_ugx"] / 1e9,
            "burden": fidic["adjustment_events"],
            "exposure": fidic["max_employer_exposure_ugx"] / 1e9,
        },
        "DAM (retrofit)": {
            "risk": dam["residual_exposure_std_ugx"] / 1e9,
            "burden": dam["adjustment_events"],
            "exposure": dam["max_employer_exposure_ugx"] / 1e9,
        },
    }

    # --- (2) Composite objective: curvature sweep + two ternary plots (p=1, p=2) ---
    curvature_rows = []
    for p in [1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]:
        grid = composite_weight_simplex(metrics, step=0.01, power=p)
        shares = (grid["winner"].value_counts(normalize=True) * 100).to_dict()
        row = {"power": p}
        for name in metrics:
            row[name] = shares.get(name, 0.0)
        curvature_rows.append(row)
    curvature_df = pd.DataFrame(curvature_rows)
    curvature_df.to_csv(out_tables / "real_project_composite_curvature_sweep.csv", index=False)

    # DAM-vs-FIDIC-only pairwise threshold (curvature-independent; excludes Fixed-price,
    # which is the null "no escalation" baseline, not a competing clause design).
    pair_metrics = {"FIDIC 13.8 (as applied)": metrics["FIDIC 13.8 (as applied)"], "DAM (retrofit)": metrics["DAM (retrofit)"]}
    pair_grid = composite_weight_simplex(pair_metrics, step=0.005, power=1.0)
    dam_share_pairwise = float((pair_grid["winner"] == "DAM (retrofit)").mean() * 100)
    pair_grid.to_csv(out_tables / "real_project_composite_dam_vs_fidic_pairwise.csv", index=False)

    colors = {"Fixed-price": "tab:gray", "FIDIC 13.8 (as applied)": "tab:orange", "DAM (retrofit)": "tab:blue"}
    grid_p1 = composite_weight_simplex(metrics, step=0.01, power=1.0)
    grid_p2 = composite_weight_simplex(metrics, step=0.01, power=2.0)
    grid_p1.to_csv(out_tables / "real_project_composite_ternary_linear.csv", index=False)
    grid_p2.to_csv(out_tables / "real_project_composite_ternary_quadratic.csv", index=False)

    plot_ternary(grid_p1, "Preferred Regime Across Priority Weightings\n(linear scoring, $p$=1 -- no risk aversion)",
                 out_figs / "real_project_composite_ternary_p1.png", colors)
    plot_ternary(grid_p2, "Preferred Regime Across Priority Weightings\n(quadratic scoring, $p$=2 -- standard risk aversion)",
                 out_figs / "real_project_composite_ternary_p2.png", colors)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for name, color in colors.items():
        ax.plot(curvature_df["power"], curvature_df[name], marker="o", color=color, label=name)
    ax.set_xlabel("Curvature $p$ (1 = linear/risk-neutral, higher = more risk-averse)")
    ax.set_ylabel("Share of weight-simplex where regime is preferred (%)")
    ax.set_title("Real Project: Preferred-Regime Share vs. Decision-Maker Risk Aversion")
    ax.legend(loc="center right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_composite_curvature_sweep.png", dpi=180)
    plt.close(fig)

    # --- (3) Shock-adaptive DAM: fast-trigger re-enabled, two proxy designs ---
    fidic_events = fidic["adjustment_events"]
    fidic_paid = fidic["total_compensation_ugx"]
    fixed_resid_var = fixed["residual_exposure_variance_ugx2"]

    proxy_step = shock_proxy_zscore(df["cost_ratio"].values, window=None)
    proxy_roll = shock_proxy_zscore(df["cost_ratio"].values, window=3)

    adaptive_rows = []
    for proxy_name, proxy in [("single-step z-score", proxy_step), ("rolling-3 volatility z-score", proxy_roll)]:
        for delta in [base_params.deadband, 0.020]:
            for ft in [np.inf, 1.50, 1.25]:
                p = RetrofitParams(base_params.lambda_share, delta, base_params.cap_up, base_params.cap_down)
                out = simulate_real_regime_adaptive(df, p, proxy, fast_trigger=ft)
                s = summarize_real_regime(out)
                adaptive_rows.append({
                    "proxy": proxy_name,
                    "delta": delta,
                    "fast_trigger": ft,
                    "events": s["adjustment_events"],
                    "event_ratio_vs_fidic_pct": s["adjustment_events"] / fidic_events * 100,
                    "compensation_ratio_vs_fidic_pct": s["total_compensation_ugx"] / fidic_paid * 100,
                    "residual_std_ugx_bn": s["residual_exposure_std_ugx"] / 1e9,
                    "risk_reduction_vs_fixed_pct": (1 - s["residual_exposure_variance_ugx2"] / fixed_resid_var) * 100,
                })
    adaptive_df = pd.DataFrame(adaptive_rows)
    adaptive_df.to_csv(out_tables / "real_project_adaptive_fast_trigger.csv", index=False)

    print("Composite curvature sweep:")
    print(curvature_df.to_string(index=False))
    print(f"\nDAM-vs-FIDIC pairwise (curvature-independent): DAM preferred on {dam_share_pairwise:.1f}% of that 2-way simplex")
    print("(DAM wins whenever combined weight on burden+exposure exceeds 50%.)")
    print("\nAdaptive fast-trigger grid:")
    print(adaptive_df.to_string(index=False))
    print("\nDONE. Tables ->", out_tables, " Figures ->", out_figs)


if __name__ == "__main__":
    main()
