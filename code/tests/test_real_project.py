import numpy as np
import pandas as pd

from contract.real_project import (
    RetrofitParams,
    capdown_sensitivity_sweep,
    composite_weight_simplex,
    deadband_sensitivity_sweep,
    minmax_normalize,
    moving_block_bootstrap_ci,
    shock_proxy_zscore,
    simulate_real_regime,
    simulate_real_regime_adaptive,
    simulate_real_regime_split,
)


def _series() -> pd.DataFrame:
    return pd.DataFrame({
        "base_amount_ugx": [1000.0, 1000.0, 1000.0],
        "cost_ratio": [1.00, 1.02, 1.05],
    })


def test_fixed_price_never_adjusts():
    out = simulate_real_regime(_series(), "fixed", RetrofitParams(0.6, 0.01, 0.5, 0.02))
    assert (out["applied_factor"] == 0.0).all()
    assert out["event"].sum() == 0


def test_fidic_real_has_zero_residual_gap():
    df = _series()
    df["a_fidic_real"] = df["cost_ratio"] - 1.0
    out = simulate_real_regime(df, "fidic_real", RetrofitParams(0.6, 0.01, 0.5, 0.02))
    assert (out["residual_gap"].abs() < 1e-12).all()


def test_dam_deadband_suppresses_small_moves():
    df = _series()
    df["a_fidic_real"] = df["cost_ratio"] - 1.0
    out = simulate_real_regime(df, "dam", RetrofitParams(lambda_share=0.6, deadband=0.5, cap_up=0.5, cap_down=0.5))
    # entitlement never exceeds the (deliberately huge) deadband, so DAM never updates.
    assert out["event"].sum() == 0
    assert (out["applied_factor"] == 0.0).all()


def test_dam_cap_bounds_target_factor():
    df = pd.DataFrame({"base_amount_ugx": [1000.0], "cost_ratio": [3.0]})
    out = simulate_real_regime(df, "dam", RetrofitParams(lambda_share=1.0, deadband=0.0, cap_up=0.2, cap_down=0.2))
    assert out["applied_factor"].iloc[0] == 0.2


def _split_series() -> pd.DataFrame:
    return pd.DataFrame({
        "base_amount_ugx": [4718.75, 4718.75],
        "base_amount_local_ugx": [1000.0, 1000.0],
        "base_amount_foreign_usd": [1.0, 1.0],
        "pn_local": [1.00, 1.05],
        "pn_foreign": [1.00, 0.90],
        "cost_ratio": [1.00, 1.0, ],
    })


def test_split_event_fires_if_either_leg_updates():
    # base_amount_ugx = local + foreign * FX, with FX implied as 3718.75 here.
    params = RetrofitParams(lambda_share=1.0, deadband=0.01, cap_up=0.5, cap_down=0.5)
    out = simulate_real_regime_split(_split_series(), params)
    assert out["event"].iloc[0] == False  # first certificate: no prior state to move from (a_prev=0, target=0)
    assert out["event"].iloc[1] == True  # both legs moved past the deadband


def test_deadband_sweep_events_decrease_with_larger_delta():
    df = pd.DataFrame({
        "base_amount_ugx": [1000.0] * 6,
        "cost_ratio": [1.00, 1.02, 1.05, 1.03, 1.08, 1.10],
        "a_fidic_real": [0.00, 0.02, 0.05, 0.03, 0.08, 0.10],
    })
    base = RetrofitParams(lambda_share=1.0, deadband=0.0, cap_up=0.5, cap_down=0.5)
    sweep = deadband_sensitivity_sweep(df, base, np.array([0.01, 0.05, 0.10]))
    assert sweep["events"].is_monotonic_decreasing


def test_capdown_sweep_relaxes_downside_clip():
    df = pd.DataFrame({
        "base_amount_ugx": [1000.0, 1000.0, 1000.0],
        "cost_ratio": [1.00, 1.10, 0.80],
        "a_fidic_real": [0.00, 0.10, -0.20],
    })
    base = RetrofitParams(lambda_share=1.0, deadband=0.0, cap_up=0.5, cap_down=0.02)
    sweep = capdown_sensitivity_sweep(df, base, np.array([0.02, 0.20]))
    # a looser cap_down should never increase residual std (it can only track the real
    # downside move more closely).
    assert sweep.loc[sweep["cap_down"] == 0.20, "residual_std_ugx_bn"].iloc[0] <= sweep.loc[sweep["cap_down"] == 0.02, "residual_std_ugx_bn"].iloc[0]


def test_shock_proxy_zscore_has_zero_mean_unit_std():
    proxy = shock_proxy_zscore(np.array([1.00, 1.02, 1.05, 1.03, 1.08, 1.10]))
    assert abs(proxy.mean()) < 1e-9
    assert abs(proxy.std(ddof=0) - 1.0) < 1e-9


def test_adaptive_fast_trigger_forces_update_even_inside_deadband():
    df = pd.DataFrame({"base_amount_ugx": [1000.0, 1000.0], "cost_ratio": [1.00, 1.01]})
    params = RetrofitParams(lambda_share=1.0, deadband=0.5, cap_up=0.5, cap_down=0.5)  # deadband never crossed alone
    proxy = np.array([0.0, 5.0])  # second point is an extreme shock reading
    out = simulate_real_regime_adaptive(df, params, proxy, fast_trigger=1.5)
    assert out["event"].iloc[1] == True
    out_no_trigger = simulate_real_regime_adaptive(df, params, proxy, fast_trigger=10.0)
    assert out_no_trigger["event"].iloc[1] == False


def test_minmax_normalize_endpoints():
    x = np.array([5.0, 10.0, 0.0])
    n = minmax_normalize(x)
    assert n.min() == 0.0
    assert n.max() == 1.0


def test_bootstrap_ci_contains_point_estimate_and_is_ordered():
    n = 24
    rng = np.random.default_rng(1)
    cost_ratio = 1.0 + np.cumsum(rng.normal(0.01, 0.02, n))
    df = pd.DataFrame({
        "base_amount_ugx": np.full(n, 1000.0),
        "cost_ratio": cost_ratio,
        "a_fidic_real": cost_ratio - 1.0,
    })
    base = RetrofitParams(lambda_share=0.6, deadband=0.01, cap_up=0.5, cap_down=0.02)
    ci = moving_block_bootstrap_ci(df, base, n_boot=200, block_len=6, seed=7)
    dam_row = ci[ci["regime"] == "dam"].iloc[0]
    assert dam_row["risk_reduction_vs_fixed_pct_lo"] <= dam_row["risk_reduction_vs_fixed_pct_median"] <= dam_row["risk_reduction_vs_fixed_pct_hi"]
    assert dam_row["events_lo"] <= dam_row["events_median"] <= dam_row["events_hi"]


def test_composite_two_regime_threshold_is_curvature_independent():
    # A regime that is exactly best on risk and worst on the other two axes, vs. one that
    # is the mirror image, should split the simplex at w_risk = 0.5 regardless of power.
    metrics = {
        "A": {"risk": 0.0, "burden": 10.0, "exposure": 10.0},
        "B": {"risk": 10.0, "burden": 0.0, "exposure": 0.0},
    }
    for power in (1.0, 2.0, 3.0):
        grid = composite_weight_simplex(metrics, step=0.05, power=power)
        # A is best on risk only; B is best on burden+exposure. Low risk-weight => the
        # burden/exposure axes (where B wins) dominate, so B wins; high risk-weight => A wins.
        low = grid[np.isclose(grid["w_risk"], 0.1)]
        high = grid[np.isclose(grid["w_risk"], 0.9)]
        assert (low["winner"] == "B").all()
        assert (high["winner"] == "A").all()
