"""Moving-block bootstrap confidence intervals for the Section 6.7 real-project headline
metrics -- risk reduction, event count, and compensation, for Fixed-price, FIDIC 13.8
(as applied), and DAM (retrofit).

    python real_project_inference.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from contract.real_project import RetrofitParams, moving_block_bootstrap_ci


def main() -> None:
    code_root = Path(__file__).resolve().parent
    paper_root = code_root.parent
    in_path = paper_root / "data" / "inputs" / "real_project_ipc_series.csv"
    params_path = paper_root / "results" / "tables" / "selected_parameters.csv"
    out_tables = paper_root / "results" / "tables"

    df = pd.read_csv(in_path, parse_dates=["period_from", "period_to", "submission_date", "approved_date"])
    df = df.sort_values("period_to").reset_index(drop=True)

    sel = pd.read_csv(params_path).iloc[0]
    base_params = RetrofitParams(
        lambda_share=float(sel["lambda_share"]),
        deadband=float(sel["deadband"]),
        cap_up=float(sel["cap_up"]),
        cap_down=float(sel["cap_down"]),
    )

    ci = moving_block_bootstrap_ci(df, base_params, n_boot=2000, block_len=6, seed=42)
    ci.to_csv(out_tables / "real_project_bootstrap_ci.csv", index=False)
    print(ci.to_string(index=False))
    print("\nSaved to", out_tables / "real_project_bootstrap_ci.csv")


if __name__ == "__main__":
    main()
