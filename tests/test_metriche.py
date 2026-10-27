"""Metriche di rischio (issue #17, #18): formule, convenzioni e casi limite."""
import math
import pandas as pd
import pytest

from backtester import backtest
from metrics import (daily_returns, max_drawdown, periods_per_year, risk_metrics)

W = {"VTSIM": 0.6, "GLDSIM": 0.1, "ZROZSIM": 0.25, "DBMFSIM": 0.05}


def test_max_drawdown_valori_noti():
    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    dd = max_drawdown(pd.Series([100.0, 120.0, 90.0, 110.0], index=idx))
    assert dd["max_drawdown"] == pytest.approx(-0.25)          # da 120 a 90
    assert dd["peak_date"] == idx[1] and dd["trough_date"] == idx[2]
    assert dd["amount"] == pytest.approx(-30.0)


def test_max_drawdown_serie_crescente_e_zero():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    assert max_drawdown(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx))["max_drawdown"] == pytest.approx(0.0)


def test_periodi_per_anno_su_serie_giornaliera_di_borsa():
    # 3 anni di giorni feriali: ~252 osservazioni/anno, non 365
    idx = pd.bdate_range("2020-01-01", "2022-12-30")
    ppy = periods_per_year(idx)
    assert 245 <= ppy <= 262, ppy


def test_periodi_per_anno_su_serie_mensile():
    idx = pd.date_range("2020-01-31", periods=36, freq="ME")
    assert 11 <= periods_per_year(idx) <= 13


def test_rendimenti_senza_interpolazione():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    r = daily_returns(pd.Series([100.0, float("nan"), 121.0], index=idx))
    assert len(r) == 0, "un NaN non deve essere trascinato in avanti"


def test_sharpe_e_sortino_contro_calcolo_manuale():
    idx = pd.bdate_range("2020-01-01", periods=253)
    rets = pd.Series([0.01 if i % 2 == 0 else -0.004 for i in range(252)])
    values = pd.Series([1000.0])
    for r in rets:
        values = pd.concat([values, pd.Series([values.iloc[-1] * (1 + r)])])
    values.index = idx[: len(values)]

    m = risk_metrics(values, risk_free_rate=0.0)
    ppy = m["periods_per_year"]
    vol_attesa = rets.std(ddof=1) * math.sqrt(ppy)
    sharpe_atteso = (rets.mean() * ppy) / vol_attesa
    dd_attesa = float((rets.clip(upper=0.0) ** 2).mean() ** 0.5) * math.sqrt(ppy)
    sortino_atteso = (rets.mean() * ppy) / dd_attesa

    assert m["volatility"] == pytest.approx(vol_attesa, rel=1e-9)
    assert m["sharpe"] == pytest.approx(sharpe_atteso, rel=1e-9)
    assert m["sortino"] == pytest.approx(sortino_atteso, rel=1e-9)


def test_tasso_privo_di_rischio_riduce_lo_sharpe():
    idx = pd.bdate_range("2020-01-01", periods=253)
    rets = [0.01 if i % 2 == 0 else -0.004 for i in range(252)]
    values = pd.Series([1000.0])
    for r in rets:
        values = pd.concat([values, pd.Series([values.iloc[-1] * (1 + r)])])
    values.index = idx[: len(values)]
    assert risk_metrics(values, 0.03)["sharpe"] < risk_metrics(values, 0.0)["sharpe"]


def test_serie_troppo_corta_restituisce_none():
    idx = pd.date_range("2020-01-01", periods=2, freq="D")
    m = risk_metrics(pd.Series([100.0, 101.0], index=idx))
    assert m["sharpe"] is None and m["sortino"] is None and m["volatility"] is None


def test_volatilita_zero_non_divide_per_zero():
    idx = pd.date_range("2020-01-01", periods=300, freq="D")
    m = risk_metrics(pd.Series([100.0] * 300, index=idx))
    assert m["sharpe"] is None and m["max_drawdown"] == pytest.approx(0.0)


def test_backtest_espone_le_metriche_per_le_tre_serie():
    _, _, s = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                       end_date=pd.Timestamp("2022-01-04"), save_outputs=False)
    assert set(s["risk_metrics"]) == {"gross", "broker", "net"}
    net = s["risk_metrics"]["net"]
    assert net["max_drawdown"] < 0 and net["volatility"] > 0
    assert net["sharpe"] is not None and net["sortino"] is not None


def test_max_drawdown_coerente_con_la_curva_di_valore():
    df_log, _, s = backtest(10000, W, begin_date=pd.Timestamp("2020-01-02"),
                            end_date=pd.Timestamp("2022-01-04"), save_outputs=False)
    curva = df_log["Net"]
    atteso = float((curva / curva.cummax() - 1).min())
    assert s["risk_metrics"]["net"]["max_drawdown"] == pytest.approx(atteso, rel=1e-12)
