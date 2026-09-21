"""Regenerate the Section 6.7 real-project validation tables and figures.

Reads the frozen, derived certificate series at data/inputs/real_project_ipc_series.csv
(see manuscript Appendix C for its derivation from the underlying contract IPC workbook)
and reproduces results/tables/real_project_*.csv and results/figures/real_project_*.png
using the same globally-calibrated DAM parameters selected in run_experiment.py
(results/tables/selected_parameters.csv), without re-fitting them.

    python real_project_experiment.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from contract.real_project import RetrofitParams, simulate_real_regime, summarize_real_regime

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.dpi": 140,
    "axes.titlesize": 13,
    "axes.labelsize": 11,
    "legend.fontsize": 9,
})

REGIME_LABELS = {
    "fixed": "Fixed-price",
    "fidic_real": "FIDIC 13.8 (as applied)",
    "dam": "DAM (retrofit)",
}
COVID = (pd.Timestamp("2020-03-01"), pd.Timestamp("2021-06-01"))
SHOCK22 = (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-01"))


def main() -> None:
    code_root = Path(__file__).resolve().parent
    paper_root = code_root.parent

    in_path = paper_root / "data" / "inputs" / "real_project_ipc_series.csv"
    params_path = paper_root / "results" / "tables" / "selected_parameters.csv"
    out_tables = paper_root / "results" / "tables"
    out_figs = paper_root / "results" / "figures"
    out_tables.mkdir(parents=True, exist_ok=True)
    out_figs.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(in_path, parse_dates=["period_from", "period_to", "submission_date", "approved_date"])
    df = df.sort_values("period_to").reset_index(drop=True)

    sel = pd.read_csv(params_path).iloc[0]
    params = RetrofitParams(
        lambda_share=float(sel["lambda_share"]),
        deadband=float(sel["deadband"]),
        cap_up=float(sel["cap_up"]),
        cap_down=float(sel["cap_down"]),
    )

    ledgers = {mode: simulate_real_regime(df, mode, params) for mode in REGIME_LABELS}
    ledger = pd.concat(ledgers.values(), ignore_index=True)
    ledger["regime_label"] = ledger["regime"].map(REGIME_LABELS)

    summary_rows = []
    for mode, label in REGIME_LABELS.items():
        row = {"regime": label}
        row.update(summarize_real_regime(ledgers[mode]))
        summary_rows.append(row)
    summary_df = pd.DataFrame(summary_rows)

    fixed_var = summary_df.loc[summary_df["regime"] == "Fixed-price", "residual_exposure_variance_ugx2"].iloc[0]
    summary_df["risk_reduction_vs_fixed_pct"] = (1 - summary_df["residual_exposure_variance_ugx2"] / fixed_var) * 100

    fidic_events = int(ledgers["fidic_real"]["event"].sum())
    dam_events = int(ledgers["dam"]["event"].sum())
    dam_paid = float(ledgers["dam"]["adjustment"].clip(lower=0).sum())
    fidic_paid = float(ledgers["fidic_real"]["adjustment"].clip(lower=0).sum())

    admin = df[["t", "period_from", "period_to", "submission_date", "approved_date", "approval_lag_days"]].copy()

    headline = pd.DataFrame([{
        "n_certificates": len(df),
        "window_start": str(df["period_from"].min())[:10],
        "window_end": str(df["period_to"].max())[:10],
        "fidic_events": fidic_events,
        "dam_events": dam_events,
        "event_ratio_dam_over_fidic_pct": dam_events / fidic_events * 100,
        "compensation_ratio_dam_over_fidic_pct": dam_paid / fidic_paid * 100,
        "mean_approval_lag_days": admin["approval_lag_days"].mean(),
        "median_approval_lag_days": admin["approval_lag_days"].median(),
        "dam_risk_reduction_vs_fixed_pct": summary_df.loc[summary_df["regime"] == "DAM (retrofit)", "risk_reduction_vs_fixed_pct"].iloc[0],
        "fidic_risk_reduction_vs_fixed_pct": summary_df.loc[summary_df["regime"] == "FIDIC 13.8 (as applied)", "risk_reduction_vs_fixed_pct"].iloc[0],
    }])

    ledger.to_csv(out_tables / "real_project_ledger.csv", index=False)
    summary_df.to_csv(out_tables / "real_project_backtest_summary.csv", index=False)
    admin.to_csv(out_tables / "real_project_admin_lag.csv", index=False)
    headline.to_csv(out_tables / "real_project_headline_metrics.csv", index=False)

    # --- Figures ---
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for mode, style in [
        ("fixed", {"linestyle": "--", "linewidth": 1.8, "color": "tab:gray"}),
        ("fidic_real", {"linestyle": "-.", "linewidth": 2.0, "color": "tab:orange"}),
        ("dam", {"linestyle": "-", "linewidth": 2.4, "color": "tab:blue"}),
    ]:
        g = ledgers[mode].sort_values("period_to")
        ax.step(g["period_to"], g["applied_factor"] * 100, where="post", label=REGIME_LABELS[mode], **style)
    ax.axvspan(*COVID, color="gray", alpha=0.15, label="COVID window")
    ax.axvspan(*SHOCK22, color="orange", alpha=0.15, label="2022 shock")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_title("Real Project: Applied Price-Adjustment Factor by Regime\n"
                 f"(UNRA Design-and-Build Road Package, {len(df)} IPCs, 2019-2024)")
    ax.set_ylabel("Applied adjustment factor (%)")
    ax.set_xlabel("Certificate period end")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_applied_factor_path.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 5.5))
    for mode, color in [("fixed", "tab:gray"), ("fidic_real", "tab:orange"), ("dam", "tab:blue")]:
        g = ledgers[mode].sort_values("period_to")
        ax.plot(g["period_to"], g["employer_exposure"] / 1e9, label=REGIME_LABELS[mode], linewidth=2.2, color=color)
    ax.axvspan(*COVID, color="gray", alpha=0.15)
    ax.axvspan(*SHOCK22, color="orange", alpha=0.15)
    ax.set_title("Real Project: Cumulative Employer Exposure (Escalation Paid) by Regime")
    ax.set_ylabel("Cumulative adjustment paid (UGX billions)")
    ax.set_xlabel("Certificate period end")
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_cumulative_exposure.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6))
    regimes_order = ["Fixed-price", "FIDIC 13.8 (as applied)", "DAM (retrofit)"]
    sd = summary_df.set_index("regime").reindex(regimes_order)
    colors = ["tab:gray", "tab:orange", "tab:blue"]

    axes[0].bar(regimes_order, sd["residual_exposure_std_ugx"] / 1e9, color=colors)
    axes[0].set_title("Residual (uncompensated) exposure\nstd. dev.")
    axes[0].set_ylabel("UGX billions")
    axes[0].tick_params(axis="x", rotation=20)

    axes[1].bar(regimes_order, sd["adjustment_events"], color=colors)
    axes[1].set_title(f"Adjustment events (of {len(df)} certificates)")
    axes[1].set_ylabel("Count")
    axes[1].tick_params(axis="x", rotation=20)

    axes[2].bar(regimes_order, sd["max_employer_exposure_ugx"] / 1e9, color=colors)
    axes[2].set_title("Max cumulative employer\nexposure")
    axes[2].set_ylabel("UGX billions")
    axes[2].tick_params(axis="x", rotation=20)

    fig.suptitle("Real Project Validation: Regime Comparison (UNRA Road Package, 2019-2024)")
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_variance_comparison.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 5))
    valid = admin.dropna(subset=["approval_lag_days"])
    ax.bar(valid["t"], valid["approval_lag_days"], color="tab:red", alpha=0.75)
    ax.axhline(valid["approval_lag_days"].mean(), color="black", linestyle="--", linewidth=1.2,
               label=f"Mean lag = {valid['approval_lag_days'].mean():.0f} days")
    ax.set_title("Real Project: Certificate Submission-to-Approval Lag\n"
                 "(Administrative burden under actual FIDIC 13.8 practice)")
    ax.set_xlabel("Certificate sequence (t)")
    ax.set_ylabel("Approval lag (days)")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_figs / "real_project_admin_lag.png", dpi=180)
    plt.close(fig)

    print("Real-project experiment complete.")
    print(headline.T)
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
