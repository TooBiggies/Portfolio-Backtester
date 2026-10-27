"""Metriche di rischio calcolate sulle serie di portafoglio (issue #17, #18).

Convenzioni dichiarate, perché ognuna cambia il numero:

- rendimenti giornalieri: ``v_t / v_{t-1} - 1`` (nessun fill: un NaN resta un NaN
  e la riga viene scartata, invece di essere trascinata in avanti);
- periodi per anno: dedotti dall'intervallo mediano tra le date (serie giornaliere
  di borsa -> 252), non cablati, così una serie settimanale o mensile resta corretta;
- volatilità: deviazione standard campionaria (ddof=1) dei rendimenti, annualizzata
  con ``sqrt(periodi)``;
- Sharpe: **rendimento medio aritmetico** annualizzato meno il tasso privo di rischio,
  diviso la volatilità annualizzata. Non si usa il rendimento geometrico al numeratore:
  è una scelta diversa, non un errore, ma va dichiarata perché dà numeri più alti;
- Sortino: come lo Sharpe, ma al denominatore la *downside deviation* calcolata su
  **tutte** le osservazioni (``mean(min(r - target, 0)^2)``), non solo su quelle
  negative: la variante "solo negative" gonfia il denominatore e abbassa il rapporto;
- max drawdown: ``min(v / max(v fino a t) - 1)``, riportato in negativo, con date di
  picco e di minimo e gli importi in valuta.

Un valore non calcolabile (serie troppo corta, volatilità zero) restituisce ``None``
invece di un numero inventato.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def periods_per_year(index: pd.Index, default: int = 252) -> int:
    """Periodi per anno contati sullo span della serie.

    Non si usa l'intervallo **mediano** tra le date: una serie giornaliera di borsa
    ha intervallo mediano 1 giorno (i weekend sono la minoranza dei salti), quindi
    il mediano darebbe 365 invece di ~252 e gonfierebbe volatilità e Sharpe di 1,20x.
    Contando osservazioni fratto anni di calendario il risultato resta corretto anche
    per serie settimanali, mensili o con giorni mancanti.
    """
    try:
        idx = pd.to_datetime(pd.Index(index))
        if len(idx) < 2:
            return default
        span_anni = (idx[-1] - idx[0]).days / 365.25
        if span_anni <= 0:
            return default
        return int(round((len(idx) - 1) / span_anni)) or default
    except Exception:
        return default


def daily_returns(values: pd.Series) -> pd.Series:
    """Rendimenti semplici giornalieri, senza interpolazione."""
    v = pd.Series(values).astype(float)
    return (v / v.shift(1) - 1.0).dropna()


def max_drawdown(values: pd.Series) -> dict:
    """Drawdown massimo: in percentuale, con date e importi in valuta."""
    v = pd.Series(values).astype(float).dropna()
    if len(v) < 2:
        return {"max_drawdown": None, "peak_date": None, "trough_date": None,
                "peak_value": None, "trough_value": None, "amount": None}
    running_max = v.cummax()
    dd = v / running_max - 1.0
    trough = dd.idxmin()
    peak = v.loc[:trough].idxmax()
    return {
        "max_drawdown": float(dd.min()),
        "peak_date": peak,
        "trough_date": trough,
        "peak_value": float(v.loc[peak]),
        "trough_value": float(v.loc[trough]),
        "amount": float(v.loc[trough] - v.loc[peak]),
    }


def risk_metrics(values: pd.Series, risk_free_rate: float = 0.0) -> dict:
    """Volatilità, Sharpe, Sortino e max drawdown di una serie di valori.

    ``risk_free_rate`` è annuo (0.02 = 2%).
    """
    v = pd.Series(values).astype(float).dropna()
    rets = daily_returns(v)
    ppy = periods_per_year(v.index)
    dd = max_drawdown(v)

    out = {
        "periods_per_year": ppy,
        "observations": int(len(rets)),
        "volatility": None,
        "sharpe": None,
        "sortino": None,
        **{k: dd[k] for k in ("max_drawdown", "peak_date", "trough_date",
                              "peak_value", "trough_value", "amount")},
    }
    if len(rets) < 2:
        return out

    vol_daily = float(rets.std(ddof=1))
    vol_ann = vol_daily * math.sqrt(ppy)
    out["volatility"] = vol_ann if vol_ann > 0 else None

    excess_ann = float(rets.mean()) * ppy - risk_free_rate
    if vol_ann > 0:
        out["sharpe"] = excess_ann / vol_ann

    target_daily = risk_free_rate / ppy
    downside = pd.Series(rets - target_daily)
    downside_dev = float((downside.clip(upper=0.0) ** 2).mean() ** 0.5) * math.sqrt(ppy)
    if downside_dev > 0:
        out["sortino"] = excess_ann / downside_dev

    return out
