# Design Specification: WMVI + DAM Artefact

## 1. Objective
Define a contract-embeddable dynamic adjustment artefact that is:
- data-driven,
- auditable,
- symmetric,
- bounded by explicit exposure controls.

## 2. WMVI component design
- Inputs: macro series + CIPI-aligned material series.
- Weighting source hierarchy:
  1. P6 estimated transmission sensitivities,
  2. CIPI basket shares,
  3. normalisation to unit-sum nonnegative vector.
- Update frequency: monthly.

## 3. Trigger and adjustment logic
- Trigger: activate only outside band $[L,U]$.
- Scaling: proportional to breach magnitude $B_t$.
- Bounds: hard cap/collar per month and cumulative annual cap.
- Optional inertia: minimum interval between successive adjustments.

## 4. Ledger outputs
For each month and regime output:
- baseline payment,
- adjustment,
- adjusted payment,
- cap-hit indicator,
- cumulative exposure,
- contractor margin and employer cost deltas.

## 5. Compliance and audit fields
- data release timestamps,
- revision flags,
- deterministic run hash,
- parameter manifest ID,
- decision log entry IDs.

## 6. Explicit non-goals
- no claim to full equilibrium bidding model,
- no direct legal drafting replacement,
- no identification of specific real contracts.