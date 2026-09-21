# DAM Paper Package (Independent Folder)

This folder is a standalone paper-development package for:

**When to Adjust, Not How Much: A Trigger-Gated Alternative to Continuous FIDIC 13.8 Price Escalation**

It is intentionally separated from the main pipeline codebase and contains:
- a full manuscript draft,
- method and governance design notes,
- figure specifications,
- an implementation runbook,
- production-grade code scaffolding for DAM simulation.

## Folder map

- manuscript/
  - `DAM_paper_draft.md`
  - `figure_specifications.md`
- methods/
  - `design_spec.md`
  - `calibration_protocol.md`
- implementation/
  - `vscode_execution_workflow.md`
- code/
  - `src/contract/dam_engine.py`
  - `src/contract/wmvi.py`
  - `src/contract/calibrate.py`
  - `src/contract/backtest.py`
  - `src/contract/real_project.py` — real-project retrofit, currency-split, and sensitivity-sweep functions (§6.7–§6.8)
  - `tests/test_dam_engine.py`
  - `tests/test_real_project.py`
  - `real_project_experiment.py` — regenerates the §6.7 tables/figures from `data/inputs/real_project_ipc_series.csv`
  - `real_project_robustness.py` — regenerates the §6.8 basket-tuning sensitivity tables/figures
  - `real_project_frontier.py` — regenerates the §6.9 composite-objective and shock-adaptive tables/figures
  - `real_project_inference.py` — regenerates the §6.7 moving-block bootstrap confidence intervals

## Data inputs expected

Primary source artefacts from the main workspace:
- `cio_pipeline-2/data/processed/panel_v1.0.csv`
- `cio_pipeline-2/p6_sensitivity_vector.json`
- `cio_pipeline-2/config/series_map.yaml`
- CIPI basket share table: `data/inputs/cipi_basket_shares.csv` (populated).
- Real-project validation series: `data/inputs/real_project_ipc_series.csv` — derived from the 38-certificate
  Sub-Clause 13.8 price-adjustment record of a real UNRA-procured design-and-build road contract (2019-2024),
  used in manuscript §6.7. See Appendix C of the manuscript for the derivation.

## Reproducibility policy

- Calibration window is fixed to **2015-01 to 2021-12**.
- Evaluation window is fixed to **2022-01 to 2025-12**.
- Code is structured to prevent look-ahead.
- The §6.7 real-project retrofit reuses the globally-calibrated DAM parameters as-is (no re-fitting to the real
  contract), so it functions as an out-of-sample triangulation check rather than a second calibration exercise.

## Executed experiment outputs

The end-to-end DAM experiment has been executed from `code/run_experiment.py` and writes:

Current run status (2026-08-12):
- Second-pass global multi-objective tuning executed.
- Persistent level-tracking DAM parameters (`lambda_share`, `deadband`, `cap_up`, `cap_down`) selected and exported in `results/tables/selected_parameters.csv`.
- Calibration search log exported in `results/tables/calibration_manifest.csv`.
- WMVI macro channels expanded to include exchange rate, CPI, central bank rate, lending rate, and private credit.

- Tables: `results/tables/`
  - `backtest_summary.csv`
  - `calibration_manifest.csv`
  - `monte_carlo_metrics.csv`
  - `monte_carlo_summary.csv`
  - `monte_carlo_outperformance.csv`
  - `monthly_ledger.csv`
  - `selected_parameters.csv`
  - `wmvi_macro_weights.csv`
  - `wmvi_series.csv`
  - `real_project_backtest_summary.csv` — regime comparison for the §6.7 real-contract retrofit
  - `real_project_headline_metrics.csv` — headline event/compensation/risk-reduction ratios
  - `real_project_ledger.csv` — full 38-certificate x 3-regime simulated ledger
  - `real_project_admin_lag.csv` — per-certificate submission-to-approval lag
  - `real_project_deadband_sensitivity.csv` — §6.8(a) deadband sweep
  - `real_project_currency_split_comparison.csv` — §6.8(b) blended vs. currency-split DAM
  - `real_project_capdown_sensitivity.csv` — §6.8(c) downside-cap sweep
  - `real_project_composite_curvature_sweep.csv` — §6.9(b) preferred-regime share vs. risk-aversion curvature
  - `real_project_composite_ternary_linear.csv` / `_quadratic.csv` — §6.9(b) full weight-simplex grids (p=1, p=2)
  - `real_project_composite_dam_vs_fidic_pairwise.csv` — §6.9(b) DAM-vs-FIDIC-only pairwise simplex
  - `real_project_adaptive_fast_trigger.csv` — §6.9(c) shock-adaptive DAM grid (negative result)
  - `real_project_bootstrap_ci.csv` — §6.7 moving-block bootstrap confidence intervals
- Figures: `results/figures/` (manuscript figure numbers below match `manuscript/DAM_paper_draft.md` exactly)
  - `dam_formula.png` — Figure 1 (§6.1)
  - `risk_exposure_comparison.png` — Figure 2 (§6.4)
  - `trigger_cap_surface.png` — sensitivity-surface exhibit (not individually numbered in-text)
  - `admin_burden_frontier.png` — administrative-burden-frontier exhibit (not individually numbered in-text)
  - `stress_cap_behavior.png` — stress-scenario exhibit (not individually numbered in-text)
  - `wmvi_timeline.png` — WMVI timeline exhibit (not individually numbered in-text)
  - `variance_comparison_bars.png` — variance-comparison exhibit (not individually numbered in-text)
  - `adjustment_event_counts.png` — event-count exhibit (not individually numbered in-text)
  - `project_margin_paths.png` — project margin-path exhibit (not individually numbered in-text)
  - `mc_reduction_distributions.png` — Figure 4 (§6.5)
  - `mc_outperformance_probabilities.png` — Figure 3 (§6.5)
  - `mc_exposure_ecdf.png` — Figure 5 (§6.5)
  - `applied_factor_paths.png` — Figure 6 (§6.5)
  - `compensation_burden_tradeoff.png` — Figure 7 (§6.5)
  - `real_project_applied_factor_path.png` — Figure 8 (§6.7)
  - `real_project_cumulative_exposure.png` — Figure 9 (§6.7)
  - `real_project_variance_comparison.png` — Figure 10 (§6.7)
  - `real_project_admin_lag.png` — Figure 11 (§6.7)
  - `real_project_deadband_sensitivity.png` — Figure 12 (§6.8a)
  - `real_project_capdown_sensitivity.png` — Figure 13 (§6.8c)
  - `real_project_composite_ternary_p1.png` / `_p2.png` — Figure 14 (§6.9b)
  - `real_project_composite_curvature_sweep.png` — Figure 15 (§6.9b)