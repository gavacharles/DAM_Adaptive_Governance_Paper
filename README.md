# DAM Paper Package (Independent Folder)

This folder is a standalone paper-development package for:

**From Rigid Escalation to Adaptive Governance: A Data-Driven Dynamic Price Adjustment Mechanism for Construction Contracts in Volatile Markets**

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
  - `tests/test_dam_engine.py`

## Data inputs expected

Primary source artefacts from the main workspace:
- `cio_pipeline-2/data/processed/panel_v1.0.csv`
- `cio_pipeline-2/p6_sensitivity_vector.json`
- `cio_pipeline-2/config/series_map.yaml`
- CIPI basket share table (to be stored as a versioned CSV in this folder under `data/inputs/`)

## Reproducibility policy

- Calibration window is fixed to **2015-01 to 2021-12**.
- Evaluation window is fixed to **2022-01 to 2025-12**.
- Code is structured to prevent look-ahead.

## Next action

Populate `data/inputs/` with the CIPI basket shares file and copy/link the required panel and sensitivity artefacts.

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
- Figures: `results/figures/`
  - `dam_formula.png`
  - `risk_exposure_comparison.png`
  - `trigger_cap_surface.png`
  - `admin_burden_frontier.png`
  - `stress_cap_behavior.png`
  - `wmvi_timeline.png`
  - `variance_comparison_bars.png`
  - `adjustment_event_counts.png`
  - `project_margin_paths.png`
  - `mc_reduction_distributions.png`
  - `mc_outperformance_probabilities.png`
  - `mc_exposure_ecdf.png`
  - `applied_factor_paths.png`
  - `compensation_burden_tradeoff.png`