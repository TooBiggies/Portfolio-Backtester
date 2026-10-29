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


def ulcer_index(values: pd.Series):
    """Ulcer Index (Martin): radice della media dei drawdown al quadrato.

    A differenza del max drawdown misura *quanto a lungo* si sta sotto il massimo,
    non solo la profondità del punto peggiore. Valore positivo (0,0592 = 5,92%).
    """
    v = pd.Series(values).astype(float).dropna()
    if len(v) < 2:
        return None
    dd = v / v.cummax() - 1.0
    return float(((dd ** 2).mean()) ** 0.5)


def risk_free_daily(risk_free_rate, index, ppy: int = 252) -> pd.Series:
    """Tasso privo di rischio in forma giornaliera, allineato alle date dei rendimenti.

    Accetta due forme:

    - **scalare annuo** (0.02 = 2%), il comportamento storico: viene diviso per i periodi
      dell'anno e replicato su ogni data;
    - **Series di rendimenti giornalieri** già calcolati sulla stessa frequenza del
      portafoglio (0.0002 = 0,02% al giorno), come quella che si ottiene dalla colonna
      ``CASHX`` del dataset. Un giorno assente vale 0: il tasso non si trascina avanti.

    Il default è 0, quindi chi non passa niente continua ad avere lo Sharpe a tasso zero.
    """
    if risk_free_rate is None:
        risk_free_rate = 0.0
    if isinstance(risk_free_rate, pd.Series):
        return risk_free_rate.astype(float).reindex(index).fillna(0.0)
    return pd.Series(float(risk_free_rate) / ppy, index=index, dtype="float64")


def risk_metrics(values: pd.Series, risk_free_rate=0.0) -> dict:
    """Volatilità, Sharpe, Sortino e max drawdown di una serie di valori.

    ``risk_free_rate`` è annuo se scalare (0.02 = 2%) oppure una Series di rendimenti
    giornalieri; vedi ``risk_free_daily``. Con lo scalare i numeri sono identici a
    quelli prodotti prima che esistesse la forma per serie.

    Due cose sono dichiarate perché ognuna cambia un decimale:

    - ``volatility`` è la volatilità **dei rendimenti del portafoglio**, non quella dei
      rendimenti in eccesso: è una proprietà della serie, non del confronto col tasso;
    - ``sharpe`` usa al denominatore la deviazione standard dei **rendimenti in eccesso**
      (definizione standard). Con un tasso costante le due coincidono, con un tasso che
      varia differiscono di ~0,002 punti su una volatilità del 9% — misurato, non stimato.
    """
    v = pd.Series(values).astype(float).dropna()
    rets = daily_returns(v)
    ppy = periods_per_year(v.index)
    dd = max_drawdown(v)

    # Il tasso privo di rischio si calcola prima dell'uscita anticipata: cosi'
    # `risk_free_mean` esiste sempre, anche su una serie troppo corta per calcolare le
    # metriche. Senza questo, una finestra di due giorni faceva fallire la stampa del
    # motore con KeyError invece di riportare "n.d." (trovato da un test sull'output).
    rf = risk_free_daily(risk_free_rate, rets.index, ppy)

    out = {
        "periods_per_year": ppy,
        "observations": int(len(rets)),
        "volatility": None,
        "sharpe": None,
        "sortino": None,
        "risk_free_mean": float(rf.mean()) * ppy if len(rf) else 0.0,
        "ulcer_index": ulcer_index(v),
        "calmar": None,
        **{k: dd[k] for k in ("max_drawdown", "peak_date", "trough_date",
                              "peak_value", "trough_value", "amount")},
    }
    if len(rets) < 2:
        return out

    vol_ann = float(rets.std(ddof=1)) * math.sqrt(ppy)
    out["volatility"] = vol_ann if vol_ann > 0 else None

    # Rendimento in eccesso periodo per periodo: e' ciò che serve quando il tasso privo
    # di rischio varia (CASHX). Con un tasso costante coincide con la vecchia formula.
    eccesso = pd.Series(rets.to_numpy() - rf.to_numpy(), index=rets.index)

    excess_ann = float(eccesso.mean()) * ppy
    vol_eccesso = float(eccesso.std(ddof=1)) * math.sqrt(ppy)
    if vol_eccesso > 0:
        out["sharpe"] = excess_ann / vol_eccesso

    # Sortino: stesso tasso come MAR, altrimenti due metriche della stessa tabella
    # userebbero due definizioni diverse di "eccesso".
    downside_dev = float((eccesso.clip(upper=0.0) ** 2).mean() ** 0.5) * math.sqrt(ppy)
    if downside_dev > 0:
        out["sortino"] = excess_ann / downside_dev

    # Calmar: rendimento annualizzato **geometrico** (lo stesso CAGR del report)
    # diviso il valore assoluto del max drawdown. Senza drawdown non è definito.
    try:
        anni = len(rets) / ppy
        cagr = float((1.0 + rets).prod()) ** (1.0 / anni) - 1.0 if anni > 0 else None
    except Exception:
        cagr = None
    if cagr is not None and out["max_drawdown"] not in (None, 0.0):
        out["calmar"] = cagr / abs(out["max_drawdown"])

    return out
