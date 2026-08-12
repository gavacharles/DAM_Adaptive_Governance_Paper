from contract.dam_engine import PaymentRow, RegimeConfig, breach_from_wmvi, simulate_monthly_ledger


def test_breach_inside_band_is_zero():
    assert breach_from_wmvi(0.05, -0.10, 0.10) == 0.0


def test_breach_above_upper_band_positive():
    assert breach_from_wmvi(0.25, -0.10, 0.10) == 0.15


def test_dam_ledger_applies_cap():
    rows = [PaymentRow(month="2022-01", base_payment=1000.0, wmvi=0.30)]
    regime = RegimeConfig(
        name="DAM",
        lower_trigger=-0.10,
        upper_trigger=0.10,
        gamma=1.0,
        monthly_cap_up=50.0,
        monthly_cap_down=50.0,
    )
    ledger = simulate_monthly_ledger(rows, regime)
    assert len(ledger) == 1
    assert ledger[0].adjustment == 50.0
    assert ledger[0].cap_hit is True
