"""Backtest su serie costruite a mano, con il risultato calcolabile prima di eseguire.

Ogni atteso e' scritto per esteso: se il motore cambia, il test dice di quanto e dove,
invece di limitarsi a "e' cambiato".

Nota: i costi di detenzione (0,2% annuo, cioe' l'imposta di bollo) si passano ora
esplicitamente come `annual_costs_rate=0.00202`; fino al #73 il motore li applicava da
solo anche con `annual_costs_rate=0`, e questo file lo fotografava. Gli attesi qui sotto
includono il fattore giornaliero `1 - 0.002/252` perche' quel costo viene chiesto.
"""
import pandas as pd
import pytest

from backtester import backtest

COSTO_DETENZIONE_GIORNALIERO = 1 - 0.002 / 252


def scrivi_csv(tmp_path, colonne):
    """colonne: nome asset -> lista di prezzi (tutte della stessa lunghezza)."""
    n = len(next(iter(colonne.values())))
    date = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame({"Date": [d.strftime("%d/%m/%Y") for d in date], **colonne})
    p = tmp_path / "serie.csv"
    df.to_csv(p, sep=";", index=False)
    return str(p)


def test_buy_and_hold_con_i_soli_costi_di_detenzione(tmp_path):
    path = scrivi_csv(tmp_path, {"A": [100.0, 110.0, 121.0]})
    _, _, s = backtest(1000, {"A": 1.0}, data_path=path, brokerage_fee_rate=0.0,
                       annual_costs_rate=0.002, tax_rate=0.0, save_outputs=False)
    # 10 quote a 100, prezzo finale 121, due applicazioni del costo annuo (giorni 1 e 2)
    atteso = 10 * 121 * COSTO_DETENZIONE_GIORNALIERO ** 2
    assert s["final_broker"] == pytest.approx(atteso, rel=1e-12)


def test_buy_and_hold_con_commissioni(tmp_path):
    path = scrivi_csv(tmp_path, {"A": [100.0, 110.0, 121.0]})
    _, _, s = backtest(1000, {"A": 1.0}, data_path=path, brokerage_fee_rate=0.01,
                       annual_costs_rate=0.002, tax_rate=0.0, save_outputs=False)
    # le quote si comprano al lordo della commissione: 1000 / (100 * 1,01)
    atteso = 1000 / (100 * 1.01) * 121 * COSTO_DETENZIONE_GIORNALIERO ** 2
    assert s["final_broker"] == pytest.approx(atteso, rel=1e-12)


def test_i_costi_annui_riducono_il_valore_dello_0_2_per_anno(tmp_path):
    # un anno di simulazione (~252 giorni feriali) sul 2 per mille
    n = 253
    prezzi = [100.0] * n
    path = scrivi_csv(tmp_path, {"A": prezzi})
    _, _, s = backtest(1000, {"A": 1.0}, data_path=path, brokerage_fee_rate=0.0,
                       annual_costs_rate=0.002, tax_rate=0.0, save_outputs=False)
    riduzione = 1 - s["final_broker"] / 1000.0
    assert riduzione == pytest.approx(0.002, rel=5e-3), f"riduzione: {riduzione:.6f}"


def test_due_asset_senza_ribilanciamento(tmp_path):
    path = scrivi_csv(tmp_path, {"A": [100.0, 110.0, 130.0], "B": [100.0, 100.0, 95.0]})
    _, _, s = backtest(1000, {"A": 0.5, "B": 0.5}, data_path=path, brokerage_fee_rate=0.0,
                       annual_costs_rate=0.002, tax_rate=0.0, rebalance_threshold=1.0,
                       save_outputs=False)
    # 5 quote per asset, due applicazioni del costo annuo: (5*130 + 5*95) * f^2
    assert s["final_broker"] == pytest.approx(1125.0 * COSTO_DETENZIONE_GIORNALIERO ** 2, rel=1e-12)


def test_ribilanciamento_conserva_il_valore_e_tassa_solo_la_plusvalenza(tmp_path):
    path = scrivi_csv(tmp_path, {"A": [100.0, 140.0, 140.0], "B": [100.0, 95.0, 95.0]})
    df_log, _, s = backtest(1000, {"A": 0.5, "B": 0.5}, data_path=path,
                            brokerage_fee_rate=0.0, annual_costs_rate=0.002, tax_rate=0.26,
                            rebalance_threshold=0.05, save_outputs=False)

    giorno0, giorno1, ultimo = df_log.iloc[0], df_log.iloc[1], df_log.iloc[-1]

    # quote effettive: quelle del giorno 0, ridotte dal bollo prima del ribilanciamento
    quote_iniziali = giorno0["Broker_A"] / giorno0["Price_A"]
    quote_pre = quote_iniziali * COSTO_DETENZIONE_GIORNALIERO
    valore_pre = quote_pre * 140.0 + quote_pre * 95.0          # pesi 59,6/40,4 -> scatta

    # 1) conservazione: la riga del giorno 1 e' registrata dopo il ribilanciamento,
    #    quindi vale "prima + imposte" (le imposte sono negative)
    imposte = float(df_log["Tax_A"].sum() + df_log["Tax_B"].sum())
    assert imposte < 0
    valore_post = giorno1["Broker_A"] + giorno1["Broker_B"]
    # tolleranza 1e-8: il ciclo di ribilanciamento converge su V' = V - imposte - costi
    # con criterio 1e-8, quindi l'identita' vale a meno di quel residuo
    assert valore_post == pytest.approx(valore_pre + imposte, rel=1e-8)
    # e il giorno 2 applica solo il costo annuo
    assert ultimo["Broker_A"] + ultimo["Broker_B"] == pytest.approx(valore_post * COSTO_DETENZIONE_GIORNALIERO, rel=1e-12)

    # 2) i pesi sono esattamente al target dopo il ribilanciamento
    assert giorno1["Broker_A"] / valore_post == pytest.approx(0.5, abs=1e-12)

    # 3) l'imposta e' il 26% della plusvalenza sulle sole quote vendute
    quote_post_a = giorno1["Broker_A"] / giorno1["Price_A"]
    quantita_venduta = quote_pre - quote_post_a
    plusvalenza = quantita_venduta * (140.0 - 100.0)
    assert -imposte == pytest.approx(0.26 * plusvalenza, rel=1e-8)

    # 4) PMC: invariato su A (solo vendite), ricalcolato su B (acquisto a 95)
    quote_post_b = giorno1["Broker_B"] / giorno1["Price_B"]
    quote_comprate = quote_post_b - quote_pre
    pmc_b_atteso = (100.0 * quote_pre + 95.0 * quote_comprate) / quote_post_b
    assert giorno1["PMC_A"] == pytest.approx(100.0, rel=1e-12)
    assert giorno1["PMC_B"] == pytest.approx(pmc_b_atteso, rel=1e-12)


def test_aliquota_zero_nessuna_imposta(tmp_path):
    path = scrivi_csv(tmp_path, {"A": [100.0, 140.0, 140.0], "B": [100.0, 95.0, 95.0]})
    df_log, _, s = backtest(1000, {"A": 0.5, "B": 0.5}, data_path=path,
                            brokerage_fee_rate=0.0, annual_costs_rate=0.002, tax_rate=0.0,
                            rebalance_threshold=0.05, save_outputs=False)
    assert float(df_log["Tax_A"].sum()) == 0.0
    ultimo = df_log.iloc[-1]
    quote_pre = 5.0 * COSTO_DETENZIONE_GIORNALIERO      # dopo il costo annuo del giorno 1
    atteso_giorno1 = quote_pre * 140.0 + quote_pre * 95.0
    # e il giorno 2 applica un'altra volta il bollo
    assert ultimo["Broker_A"] + ultimo["Broker_B"] == pytest.approx(
        atteso_giorno1 * COSTO_DETENZIONE_GIORNALIERO, rel=1e-12)
