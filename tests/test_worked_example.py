"""End-to-end check of examples/worked_example.csv against numbers computed by hand.

Settings: holdout 2, ordering cost 30 per order, holding rate 25% a year,
12 periods a year, service level 95% (z = 1.644854), review period 1.

W-1 demand: 10 12 8 10 14 6 10 14 (sum 84, mean 10.5), unit cost 2, one observed lead time 2.
  Population variance = 54 / 8 = 6.75, so CV = sqrt(6.75) / 10.5 = 0.24744 -> X.
  Every period has demand: ADI 1, CV2 = 6.75 / 10.5^2 = 0.061224 -> smooth.
  Backtest (train 10 12 8 10 14 6, naive scale (2+4+2+4+8)/5 = 4):
    naive  forecasts 6, 10   vs 10, 14 -> errors -4, -4  MAE 4  MASE 1.0
    MA(3)  forecasts 10, 10  vs 10, 14 -> errors  0, -4  MAE 2  MASE 0.5   <- picked
    SES(0.2) level 10, 10.4, 9.92, 9.936, 10.7488, 9.79904 -> forecast 9.79904,
             then 9.839232: errors -0.20096, -4.160768  MAE 2.180864  MASE 0.545216
  Forecast = mean(6, 10, 14) = 10. Sample variance = 54 / 7.
  SS = 1.644854 * sqrt((2 + 1) * 54 / 7) = 7.912901; ROP = 10 * (2 + 1) + SS = 37.912901.
  EOQ = sqrt(2 * (10 * 12) * 30 / (0.25 * 2)) = sqrt(14400) = 120.
  Replay: starts at s + Q = 157.912901; cumulative demand never brings it to s, so no
  orders, no stockouts, and average on hand = 157.912901 - (10+22+30+40+54+60+70+84)/8
  = 157.912901 - 46.25 = 111.662901.

W-2 demand: 0 0 6 0 0 0 9 0 (sum 15, mean 1.875), unit cost 1, default lead time 1.
  ADI = 8 / 2 = 4; sizes 6, 9: CV = 1.5 / 7.5 = 0.2, CV2 = 0.04 -> intermittent.
  Population variance = (36 + 81) / 8 - 1.875^2 = 11.109375; CV = 3.333073 / 1.875 -> Z.
  Backtest (train 0 0 6 0 0 0, naive scale (0+6+6+0+0)/5 = 2.4):
    SES      forecasts 0.6144, 2.29152       MAE 5.33856    MASE 2.2244
    Croston  forecasts 6/3 = 2, 6.3/3.1      MAE 4.516129   MASE 1.881720
    SBA      forecasts 1.9, 0.95 * 6.3/3.1   MAE 4.515323   MASE 1.881384  <- picked
  Forecast = 0.95 * 6.3 / 3.1 = 1.930645.

ABC (by value): W-1 10.5 * 12 * 2 = 252, W-2 1.875 * 12 * 1 = 22.5, total 274.5.
  W-1 has 0% before it -> A; W-2 has 252 / 274.5 = 91.8% before it -> B.
"""

from __future__ import annotations

import math

import pytest
from conftest import EXAMPLES

from inventory_policy_lab import Config, analyze_file

CONFIG = Config(holdout=2, ordering_cost=30, holding_rate=0.25)


def test_worked_example_matches_the_hand_calculation() -> None:
    report = analyze_file(EXAMPLES / "worked_example.csv", CONFIG)
    w1, w2 = report.skus
    assert report.abc_basis == "value"

    assert w1.annual_value == pytest.approx(252)
    assert (w1.abc, w1.xyz) == ("A", "X")
    assert w1.cv == pytest.approx(0.247436, abs=1e-6)
    assert w1.profile.category == "smooth"
    assert w1.profile.cv2 == pytest.approx(0.061224, abs=1e-6)
    scores = {b.method: b for b in w1.backtests}
    assert scores["naive"].mase == pytest.approx(1.0)
    assert scores["moving_average"].mase == pytest.approx(0.5)
    assert scores["ses"].mase == pytest.approx(0.545216)
    assert scores["ses"].mae == pytest.approx(2.180864)
    assert w1.method == "moving_average"
    assert w1.forecast == pytest.approx(10)
    assert w1.policy.sigma_demand == pytest.approx(math.sqrt(54 / 7))
    assert w1.policy.lead_time == 2
    assert w1.policy.safety_stock == pytest.approx(7.912901, abs=1e-6)
    assert w1.policy.reorder_point == pytest.approx(37.912901, abs=1e-6)
    assert w1.policy.eoq == pytest.approx(120)
    assert w1.order_quantity_source == "eoq"
    assert w1.simulation.orders_placed == 0
    assert w1.simulation.fill_rate == 1
    assert w1.simulation.average_on_hand == pytest.approx(111.662901, abs=1e-6)

    assert w2.annual_value == pytest.approx(22.5)
    assert (w2.abc, w2.xyz) == ("B", "Z")
    assert w2.profile.adi == 4
    assert w2.profile.cv2 == pytest.approx(0.04)
    assert w2.profile.category == "intermittent"
    scores = {b.method: b for b in w2.backtests}
    assert list(scores) == ["ses", "croston", "sba"]
    assert scores["ses"].mase == pytest.approx(2.2244)
    assert scores["croston"].mase == pytest.approx(1.881720, abs=1e-6)
    assert scores["sba"].mase == pytest.approx(1.881384, abs=1e-6)
    assert w2.method == "sba"
    assert w2.forecast == pytest.approx(1.930645, abs=1e-6)
    assert w2.policy.lead_time == 1
    assert w2.notes == ("no observed lead times: default lead time used",)

    assert report.matrix()["A"]["X"] == 1
    assert report.matrix()["B"]["Z"] == 1
    assert report.overall_fill_rate() == 1
