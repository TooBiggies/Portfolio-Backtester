"""Il portafoglio "lordo" non deve pagare il bollo: deve essere un benchmark a costo zero."""
import pandas as pd
from backtester import backtest
from engine import Portfolio


def test_portafoglio_ideale_senza_bollo():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.0, bollo_rate=0.0)
    assert float(pf.daily_annual_costs.sum()) == 0.0
    h = pf.holdings.copy()
    pf.apply_holding_costs()
    assert (pf.holdings == h).all(), "senza bollo ne TER le quote non devono cambiare"


def test_bollo_default_resta_0_2_per_anno():
    pf, _ = Portfolio.from_weights(pd.Series({"A": 1.0}), 10000, {"A": 1.0}, 0.0, 0.0)
    quota = float(pf.daily_annual_costs.sum()) / pf.broker_assets_value * 252
    assert abs(quota - 0.002) < 1e-9, f"bollo annuo: {quota}"


def test_lordo_uguale_a_buy_and_hold_senza_costi():
    _, _, s = backtest(10000, {"VTSIM": 1.0}, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2021-01-04"), brokerage_fee_rate=0.0,
                       annual_costs_rate=0.0, tax_rate=0.0, save_outputs=False)
    df = pd.read_csv("./Timeseries.csv", sep=";")
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)
    df = df[(df["Date"] >= pd.Timestamp("2020-01-02")) & (df["Date"] <= pd.Timestamp("2021-01-04"))]
    atteso = 10000 * df["VTSIM"].iloc[-1] / df["VTSIM"].iloc[0]
    assert abs(s["final_gross"] - atteso) / atteso < 1e-9, f"lordo {s['final_gross']} vs buy&hold {atteso}"
