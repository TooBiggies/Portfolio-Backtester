"""Il file scaricabile non deve contenere le serie di prezzo.

Il permesso di testfol.io autorizza l'uso dei dati e la pubblicazione degli output
derivati, non la ridistribuzione. Un export giornaliero dei controvalori per asset
permette di ricostruire il prezzo: fra due ribilanciamenti le quote restano ferme,
quindi il rapporto fra due valori consecutivi è il rapporto fra due prezzi.

Questi test difendono quella regola: se qualcuno rimette una colonna `Broker_*` o
toglie il filtro sulle righe, la suite se ne accorge.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from esportazione import (
    GIORNI_INTORNO,
    colonne_esportabili,
    date_ribilanciamento,
    righe_da_esportare,
    to_excel_bytes,
)


def log_finto(giorni: int = 40) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Un log con la stessa forma di quello vero: totali, colonne per asset, prezzi."""
    date = pd.date_range("2020-01-01", periods=giorni, freq="B")
    dati = {
        "BrokerPortfolioValue": [10000.0 + i for i in range(giorni)],
        "Net": [9800.0 + i for i in range(giorni)],
        "Price_VTSIM": [100.0 + i for i in range(giorni)],
        "PMC_VTSIM": [95.0] * giorni,
        "Broker_VTSIM": [6000.0 + i for i in range(giorni)],
        "Net_VTSIM": [5900.0 + i for i in range(giorni)],
        "HoldingCost_VTSIM": [0.02] * giorni,
        "Tax_VTSIM": [0.0] * giorni,
        "TradeCost_VTSIM": [0.0] * giorni,
    }
    log = pd.DataFrame(dati, index=date)
    delta = pd.DataFrame({"VTSIM": [0.0] * giorni}, index=date)
    delta.iloc[10, 0] = 250.0   # un ribilanciamento
    delta.iloc[30, 0] = -120.0  # un altro
    return log, delta


def test_le_colonne_dei_prezzi_non_escono():
    log, _ = log_finto()
    colonne = colonne_esportabili(log)
    for vietata in ("Price_", "PMC_", "Broker_", "Net_", "Gross_", "HoldingCost_"):
        assert not [c for c in colonne if c.startswith(vietata)], (
            f"la colonna {vietata}* non deve essere esportabile"
        )
    # i totali restano: sono il risultato della simulazione
    assert "BrokerPortfolioValue" in colonne
    assert "Net" in colonne


def test_le_date_di_ribilanciamento_sono_solo_quelle_con_movimenti():
    _, delta = log_finto()
    date = date_ribilanciamento(delta)
    assert len(date) == 2


def test_si_tengono_solo_le_finestre_intorno_ai_ribilanciamenti():
    log, delta = log_finto(giorni=60)
    righe = righe_da_esportare(log, delta)

    # prima e ultima sempre presenti
    assert righe.index[0] == log.index[0]
    assert righe.index[-1] == log.index[-1]
    # due finestre da 5 righe (2 prima, il giorno, 2 dopo) più gli estremi
    attese = 2 * (2 * GIORNI_INTORNO + 1) + 2
    assert len(righe) == attese
    assert len(righe) < len(log) / 2, "il filtro deve ridurre davvero il numero di righe"


def test_il_file_excel_ha_due_fogli_poche_righe_e_nessun_prezzo():
    log, delta = log_finto(giorni=60)
    contenuto = to_excel_bytes(log, delta)

    libro = pd.read_excel(BytesIO(contenuto), sheet_name=None)
    assert set(libro) == {"Portfolio", "Rebalancing"}

    portfolio = libro["Portfolio"]
    assert len(portfolio) < len(log)
    assert not [c for c in portfolio.columns if c.startswith(("Price_", "PMC_", "Broker_"))]

    # il foglio dei ribilanciamenti contiene solo i giorni con movimenti
    assert len(libro["Rebalancing"]) == 2


def test_senza_ribilanciamenti_restano_prima_e_ultima_riga():
    log, delta = log_finto(giorni=20)
    delta[:] = 0.0
    righe = righe_da_esportare(log, delta)
    assert len(righe) == 2
