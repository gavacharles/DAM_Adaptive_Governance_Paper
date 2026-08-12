# DAM Code Scaffold

Minimal production-oriented scaffold for:
- WMVI construction,
- DAM ledger simulation,
- parameter calibration,
- regime back-testing.

## Quick start
1. Create and activate a Python environment.
2. Install dependencies from `requirements.txt`.
3. Run tests with `pytest`.

## Package layout
- `src/contract/` core modules
- `tests/` unit tests

The calibration/evaluation split is hard-coded in `calibrate.py` to preserve out-of-sample integrity.