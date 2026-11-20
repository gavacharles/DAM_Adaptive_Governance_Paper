# DAM_Adaptive_Governance_Paper

Manuscript, method notes and Python code for DAM, a trigger-gated alternative to continuous FIDIC Sub-Clause 13.8 price escalation: construction of a weighted macro-volatility index (WMVI), DAM ledger simulation, calibration, back-testing and a retrofit to a real contract's price-adjustment record.

## Layout

| Path | What it is |
|---|---|
| `methods/` | Design specification and calibration protocol |
| `implementation/` | Execution runbook |
| `code/src/contract/` | Core modules: `dam_engine.py`, `wmvi.py`, `calibrate.py`, `backtest.py`, `real_project.py` |
| `code/tests/` | Unit tests for the engine and the real-project functions |
| `code/run_experiment.py` | End-to-end experiment (calibration, back-test, Monte Carlo) |
| `code/real_project_*.py` | Real-contract retrofit, robustness, frontier and bootstrap scripts |
| `data/inputs/` | CIPI basket shares; anonymised real-contract price-adjustment series |
| `results/tables/`, `results/figures/` | Generated tables and figures |

## Setup and running

```bash
pip install -r code/requirements.txt
cd code
pytest
python run_experiment.py
python real_project_experiment.py      # also: real_project_robustness.py, real_project_frontier.py, real_project_inference.py
```

The experiment reads the data panel and sensitivity vector built by [cio_pipeline-2](https://github.com/gavacharles/cio_pipeline-2) (`data/processed/panel_v1.0.csv`, `p6_sensitivity_vector.json`, `config/series_map.yaml`). The calibration window (2015-01 to 2021-12) and evaluation window (2022-01 to 2025-12) are fixed in `calibrate.py` so results stay out of sample.
