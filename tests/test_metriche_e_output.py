"""Le metriche che si leggono sono quelle che il motore ha calcolato.

Due buchi trovati guardando la #79:

1. **Le tre serie non erano confrontate fra loro.** `summary["risk_metrics"]` contiene
   lordo, broker e netto, ma nessun test verificava che ciascuno fosse coerente con la
   propria colonna del log: un parametro applicato a una sola serie (o un dizionario
   scritto sulla serie sbagliata) passava inosservato.
2. **L'output del terminale non era coperto da niente.** Le righe stampate sono quelle
   che le persone leggono davvero quando lanciano il backtest, e cambiarle non faceva
   fallire alcun test.
"""
import pandas as pd
import pytest

from backtester import backtest
from metrics import risk_metrics

PESI = {"VTSIM": 0.60, "GLDSIM": 0.10, "ZROZSIM": 0.25, "DBMFSIM": 0.05}
INIZIO = pd.Timestamp("2020-01-02")
FINE = pd.Timestamp("2021-01-04")

SERIE = {"gross": "GrossPortfolioValue", "broker": "BrokerPortfolioValue", "net": "Net"}
METRICHE = ("volatility", "sharpe", "sortino", "ulcer_index", "calmar", "max_drawdown")


def esegui(**kwargs):
    return backtest(10000, PESI, begin_date=INIZIO, end_date=FINE, save_outputs=False, **kwargs)


# ------------------------------------------------- metriche coerenti con il log

def test_le_metriche_di_ogni_serie_coincidono_con_la_propria_colonna():
    """Per ognuna delle tre curve, il riepilogo deve essere esattamente il risultato di
    `risk_metrics` sulla colonna corrispondente del log. Se un giorno un parametro
    venisse applicato solo all'ultima serie calcolata, questo test lo direbbe."""
    df, _, s = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    rf_usato = s.get("risk_free_rate", 0.0)
    for nome, colonna in SERIE.items():
        atteso = risk_metrics(df[colonna], risk_free_rate=rf_usato)
        ottenuto = s["risk_metrics"][nome]
        for chiave in METRICHE:
            assert ottenuto[chiave] == pytest.approx(atteso[chiave], rel=1e-12), f"{nome}.{chiave}"


def test_le_tre_serie_hanno_metriche_presenti_e_distinte():
    """Tre portafogli diversi non possono avere lo stesso Sharpe: se coincidono, una
    delle tre serie sta leggendo i dati di un'altra."""
    _, _, s = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    for nome in SERIE:
        for chiave in METRICHE:
            assert s["risk_metrics"][nome][chiave] is not None, f"{nome}.{chiave} assente"
    for chiave in ("sharpe", "sortino", "volatility", "max_drawdown"):
        valori = {round(s["risk_metrics"][n][chiave], 8) for n in SERIE}
        assert len(valori) == 3, f"{chiave} identico su serie diverse: {valori}"


def test_il_lordo_ha_rendimento_migliore_ma_il_netto_meno_rischio_di_percorso():
    """Le relazioni che ci si aspetta fra le tre curve: il lordo rende più del netto,
    il netto vale meno del broker. Sulla volatilità non si asserisce nulla: il #76 ha
    mostrato che può muoversi in modo non monotono, perché sono tre simulazioni e non
    una curva ricalata."""
    _, _, s = esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    assert s["cagr_gross"] > s["cagr_broker"] > s["cagr_net"]
    assert s["final_gross"] > s["final_broker"] > s["final_net"]


# ------------------------------------------------------- output del terminale

def test_l_output_riporta_tutte_le_metriche_e_il_tasso_usato(capsys):
    esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    uscita = capsys.readouterr().out

    for etichetta in ("Capitale finale", "Volatilità annua (netta)", "Max drawdown (netto)",
                      "Sharpe", "Sortino (netto)", "Ulcer index (netto)", "Calmar (netto)"):
        assert etichetta in uscita, f"manca la riga {etichetta!r}"

    riga_sharpe = next(r for r in uscita.splitlines() if r.startswith("Sharpe"))
    assert "rf" in riga_sharpe, f"lo Sharpe stampato non dichiara il tasso: {riga_sharpe!r}"
    assert "%" in riga_sharpe

    # nessuna metrica inventata: con una finestra normale non devono comparire "n.d."
    assert "n.d." not in uscita


def test_l_output_del_drawdown_riporta_le_date_e_l_importo(capsys):
    """La riga sotto il max drawdown è quella che dice quando è successo e quanto è
    costato: se spariscono le date o l'unità, il numero resta ma non si sa più leggere."""
    esegui(brokerage_fee_rate=0.0029, annual_costs_rate=0.002, tax_rate=0.26)
    righe = capsys.readouterr().out.splitlines()
    riga = next((r for r in righe if r.startswith("  da ")), None)
    assert riga is not None, "manca la riga con le date del drawdown"
    assert " a " in riga and "(" in riga and ")" in riga
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", riga), f"date assenti: {riga!r}"
    assert re.search(r"-?[\d.]+", riga.split("(")[-1]), f"importo assente: {riga!r}"


def test_con_una_finestra_troppo_corta_l_output_dice_n_d_invece_di_un_numero(capsys):
    """Due soli giorni non bastano per un rendimento significativo: il terminale deve
    scrivere n.d., non zero (che si legge come «rischio nullo»)."""
    backtest(10000, PESI, begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2020-01-03"),
             save_outputs=False)
    uscita = capsys.readouterr().out
    assert "n.d." in uscita
