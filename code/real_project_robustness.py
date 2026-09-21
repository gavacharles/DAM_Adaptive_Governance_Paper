"""Basket-specific tuning and robustness checks for the Section 6.7 real-project retrofit.

Reads the same frozen input as real_project_experiment.py (data/inputs/real_project_ipc_series.csv)
and the same globally-calibrated DAM parameters (results/tables/selected_parameters.csv), then:
  (A) sweeps the deadband only, to quantify basket-specific tuning of delta (manuscript Sec 6.8a);
  (B) compares the blended-currency retrofit against an independent local/foreign-leg retrofit
      that matches how this contract's clause is actually administered (Sec 6.8b);
  (C) sweeps the downside cap only, to isolate how much residual risk is attributable to the
      cap_down asymmetry vs. the deadband (Sec 6.8c).

None of these change the paper's core calibrated parameters (lambda=0.60, delta=0.010,
cap_up=0.50, cap_down=0.02) -- they characterise how sensitive the real-project retrofit
is to each one, using only this project's own data.

    python real_project_robustness.py
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
    capdown_sensitivity_sweep,
    deadband_sensitivity_sweep,
    simulate_real_regime,
    simulate_real_regime_split,
    summarize_real_regime,
)

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.dpi": 140,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
})


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

    # --- (A) Deadband sensitivity sweep ---
    deltas = np.round(np.arange(0.002, 0.041, 0.002), 4)
    sweep_df = deadband_sensitivity_sweep(df, base_params, deltas)
    sweep_df.to_csv(out_tables / "real_project_deadband_sensitivity.csv", index=False)

    feasible = sweep_df[sweep_df["event_ratio_vs_fidic_pct"] <= 35.0]
    tuned = (feasible.sort_values("delta").iloc[0] if not feasible.empty
             else sweep_df.sort_values("event_ratio_vs_fidic_pct").iloc[0])
    baseline_row = sweep_df.loc[np.isclose(sweep_df["delta"], base_params.deadband)].iloc[0]

    # "Free" improvement: largest delta that changes risk-reduction by < 1pp vs the global value.
    free_zone = sweep_df[(baseline_row["risk_reduction_vs_fixed_pct"] - sweep_df["risk_reduction_vs_fixed_pct"]).abs() < 1.0]
    free_pick = free_zone.sort_values("delta", ascending=False).iloc[0]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(sweep_df["delta"], sweep_df["event_ratio_vs_fidic_pct"], marker="o", color="tab:red", label="Event ratio vs FIDIC (%)")
    ax1.set_xlabel("Deadband $\\delta$")
    ax1.set_ylabel("Event ratio vs FIDIC (%)", color="tab:red")
    ax1.tick_params(axis="y", labelcolor="tab:red")
    ax2 = ax1.twinx()
    ax2.plot(sweep_df["delta"], sweep_df["risk_reduction_vs_fixed_pct"], marker="s", color="tab:blue", label="Risk reduction vs Fixed (%)")
    ax2.set_ylabel("Risk reduction vs Fixed-price (%)", color="tab:blue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")
    ax1.axvline(base_params.deadband, color="gray", linestyle="--", linewidth=1.2, label="Global $\\delta$=0.010")
    ax1.axvline(free_pick["delta"], color="green", linestyle=":", linewidth=1.6, label=f"Low-cost pick $\\delta$={free_pick['delta']:.3f}")
    ax1.scatter([tuned["delta"]], [tuned["event_ratio_vs_fidic_pct"]], color="black", zorder=5, marker="*", s=180,
                label=f"Burden-matched pick $\\delta$={tuned['delta']:.3f}")
    ax1.set_title("Real Project: Deadband Sensitivity\n(basket-specific tuning of the retrofit, this contract only)")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_deadband_sensitivity.png", dpi=180)
    plt.close(fig)

    # --- (B) Currency-split vs blended DAM ---
    blended = simulate_real_regime(df, "dam", base_params)
    split = simulate_real_regime_split(df, base_params)
    fidic = simulate_real_regime(df, "fidic_real", base_params)
    fidic_s = summarize_real_regime(fidic)
    blended_s = summarize_real_regime(blended)
    split_s = summarize_real_regime(split)

    def _row(name, s):
        return {
            "variant": name,
            "events": s["adjustment_events"],
            "event_ratio_vs_fidic_pct": s["adjustment_events"] / fidic_s["adjustment_events"] * 100,
            "total_compensation_ugx_bn": s["total_compensation_ugx"] / 1e9,
            "compensation_ratio_vs_fidic_pct": s["total_compensation_ugx"] / fidic_s["total_compensation_ugx"] * 100,
            "residual_std_ugx_bn": s["residual_exposure_std_ugx"] / 1e9,
        }

    split_vs_blend = pd.DataFrame([
        _row("DAM (blended, global params)", blended_s),
        _row("DAM (currency-split, global params)", split_s),
    ])
    split_vs_blend.to_csv(out_tables / "real_project_currency_split_comparison.csv", index=False)

    # --- (C) Cap-down sensitivity sweep ---
    cap_downs = np.round(np.arange(0.02, 0.31, 0.02), 3)
    cap_df = capdown_sensitivity_sweep(df, base_params, cap_downs)
    cap_df.to_csv(out_tables / "real_project_capdown_sensitivity.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(cap_df["cap_down"], cap_df["risk_reduction_vs_fixed_pct"], marker="o", color="tab:blue")
    ax.axvline(base_params.cap_down, color="gray", linestyle="--", linewidth=1.2, label=f"Global $A^-$={base_params.cap_down}")
    ax.set_xlabel("Downside cap $A^-$")
    ax.set_ylabel("Risk reduction vs Fixed-price (%)")
    ax.set_title("Real Project: Downside-Cap Sensitivity\n(compensation ratio unaffected -- relaxing $A^-$ only widens permitted downward correction)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_capdown_sensitivity.png", dpi=180)
    plt.close(fig)

    print("Deadband sweep (excerpt):")
    print(sweep_df.to_string(index=False))
    print("\nLow-cost pick:", dict(free_pick))
    print("\nBurden-matched pick:", dict(tuned))
    print("\nCurrency-split vs blended:")
    print(split_vs_blend.to_string(index=False))
    print("\nCap-down sweep (excerpt):")
    print(cap_df.to_string(index=False))
    print("\nDONE. Tables ->", out_tables, " Figures ->", out_figs)


if __name__ == "__main__":
    main()
