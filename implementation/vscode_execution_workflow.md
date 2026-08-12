# VS Code Execution Workflow

## Step 1 — Build DAM simulator in `src/contract/`
- Implement documented cashflow engine.
- Input: project profile, price path, regime spec.
- Output: monthly ledger.
- Add unit tests before scenario runs.

## Step 2 — Implement WMVI constructor
- Consume `p6_sensitivity_vector.json` and CIPI basket shares.
- Produce versioned WMVI series with metadata.

## Step 3 — Run calibration experiment
- Enforce strict calibration/evaluation split in code.
- Run grid search and write complete manifest.

## Step 4 — Produce headline exhibits
- DAM formula figure with symbol table.
- Risk-exposure comparison with shock shading.

## Step 5 — Draft governance chapter
- Workflow, verification protocol, dispute-avoidance process,
- procurement compatibility narrative.

## Step 6 — Reviewer-proof package
- parameter-sensitivity surfaces,
- stress scenarios,
- explicit limitations on behavioural response.

## Deliverable set
- manuscript draft,
- reproducible metrics tables,
- figure files,
- appendices with assumptions and manifests.