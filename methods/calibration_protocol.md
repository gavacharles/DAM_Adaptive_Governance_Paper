# Calibration and Back-Test Protocol

## Fixed windows (hard-coded policy)
- Calibration: 2015-01 to 2021-12
- Evaluation: 2022-01 to 2025-12

## Parameter grid
Candidate tuple:
- Trigger(s): $L,U$ or symmetric threshold $T$
- Sensitivity: $\gamma$
- Cap/collar: $C^+,C^-$ (monthly and annual)
- Frequency: monthly, bi-monthly, quarterly

## Objective and constraints
Primary objective:
- minimize contractor margin variance.

Subject to:
- annual employer exposure cap never breached,
- max event count per year,
- symmetry and implementability constraints.

## Comparator fairness policy
- Fixed-price: true no-adjustment baseline.
- FIDIC 13.8 baseline: best plausible Ugandan indexation implementation with explicit assumptions documented in manifest.
- DAM: trigger-based, capped, symmetric.

## Reporting requirements
For each regime and archetype:
- margin variance,
- budget variance,
- event count,
- max monthly loss,
- max annual exposure,
- cap hit rate,
- out-of-sample score.

## Stress tests
- synthetic inflation/FX shocks beyond observed maxima,
- publication lag injection,
- data revision perturbation.

## Anti-overfitting controls
- no parameter tuning on evaluation years,
- immutable manifest per run,
- run-level timestamp and git commit capture.