import matplotlib.pyplot as plt
import pandas as pd

from engine import Portfolio, PortfolioTracker, Rebalancer
from metrics import risk_metrics

def prepare_price_dataframe(df, begin_date=None, end_date=None, asset_columns=None, date_column='Date'):
    """
    Convert loaded CSV into price DataFrame with Date as index.

    Parameters:
    -----------
    df_raw : pd.DataFrame
        Output from load_data() + preprocess_data()
    asset_columns : list
        Which columns to use as asset prices (exclude Date, etc.)
    date_column : str
        Name of the date column

    Returns:
    --------
    df_prices : pd.DataFrame
        DataFrame with Date as index and assets as columns
    """

    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column], dayfirst=True, errors="coerce")

    if asset_columns is None:
        asset_columns = [c for c in df.columns if c != date_column]

    # La finestra di default si calcola sulle date GIA' interpretate e sulle sole righe
    # in cui TUTTI gli asset selezionati hanno un prezzo: sul formato gg/mm/aaaa il
    # minimo e il massimo alfabetici non coincidono con quelli cronologici
    # ("31/01/2020" > "01/02/2020"), e una riga con date valida ma prezzi mancanti
    # allargherebbe la finestra oltre i dati realmente disponibili (issue #8: la data
    # iniziale deve essere la meno recente fra quelle in comune a tutti gli asset).
    righe_complete = df.dropna(subset=asset_columns)
    if begin_date is None or end_date is None:
        date_valide = righe_complete[date_column].dropna()
        if date_valide.empty:
            # senza questo, un CSV con date illeggibili restituiva un DataFrame vuoto:
            # indistinguibile da un risultato legittimo.
            raise ValueError(f"Nessuna data valida nella colonna '{date_column}'")
        if begin_date is None:
            begin_date = date_valide.min()
        if end_date is None:
            end_date = date_valide.max()

    df = df[(df[date_column] >= pd.to_datetime(begin_date))].copy()
    df = df[(df[date_column] <= pd.to_datetime(end_date))].copy()
    df = df.reset_index(drop=True)

    # Set Date as index
    df_prices = df.set_index(date_column)[asset_columns]

    return df_prices, begin_date, end_date


def backtest(initial_value, weights, begin_date=None, end_date=None, brokerage_fee_rate=0., rebalance_threshold=0.1, tax_rate=0., annual_costs_rate=0., plot=False, save_outputs=True, risk_free_rate=0.0, data_path="./Timeseries.csv"):
    """
    Performs a backtest of a portfolio over a given time horizon with periodic rebalancing,
    accounting for brokerage fees, taxes, and annual costs.

    Parameters
    ----------
    initial_value : float
        The initial amount of capital invested in the portfolio.

    begin_date : str
        The start date of the backtest in 'YYYY-MM-DD' format.

    end_date : str
        The end date of the backtest in 'YYYY-MM-DD' format.

    weights : dict
        Dictionary of target weights for each asset. Keys are asset names, values are weights
        as decimals (sum should typically equal 1).

    brokerage_fee_rate : float, optional, default=0.0029
        Fractional cost of executing trades (per transaction), applied at rebalancing.

    rebalance_threshold : float, optional, default=0.1
        Maximum deviation from target weights before triggering a rebalance.
        Example: 0.1 triggers a rebalance if an asset weight differs by ±10% from its target.

    tax_rate : float, optional, default=0.26
        Capital gains tax rate applied on realized gains during rebalancing.

    Returns
    -------
    None
        - Outputs are saved to Excel files ('output_ptf.xlsx' and 'output_ptf_delta.xlsx') and a PNG plot ('plot.png').
        - Saves a semilogarithmic plot of the compound return over time.
        - Prints summary statistics to the console:
    """

    # --- validazione degli ingressi, prima di leggere i dati ---
    # Pesi che non sommano a 1 non sono un errore innocuo: il ribilanciamento porta il
    # portafoglio ai pesi target vendendo la quota non investita, e il ricavato sparisce
    # (non esiste un conto liquidita'). Il capitale decade verso zero senza alcun errore:
    # con pesi che sommano a 0,5 ogni ribilanciamento dimezza il valore (issue #62).
    if not weights:
        raise ValueError("weights e' vuoto: nessun asset da simulare")
    negativi = {a: w for a, w in weights.items() if float(w or 0.0) < 0.0}
    if negativi:
        raise ValueError(f"I pesi non possono essere negativi: {negativi}")
    somma_pesi = sum(float(w or 0.0) for w in weights.values())
    if abs(somma_pesi - 1.0) > 1e-6:
        raise ValueError(
            f"I pesi devono sommare a 1.0, la somma e' {somma_pesi:.6f}. "
            f"Pesi ricevuti: {dict(weights)}")

    # Capitale non positivo: con initial_value=0 il ciclo di convergenza del
    # ribilanciamento calcola 0/0 = NaN, e `NaN < 1e-8` e' sempre falso: non termina
    # piu' (issue #66). Con capitale negativo il primo riacquisto non e' finanziabile.
    try:
        capitale = float(initial_value)
    except (TypeError, ValueError):
        raise ValueError(f"Il capitale iniziale deve essere un numero, ricevuto {initial_value!r}")
    if not capitale > 0:      # cattura anche NaN
        raise ValueError(f"Il capitale iniziale deve essere positivo, ricevuto {initial_value!r}")
    # La docstring dichiara begin_date/end_date come str 'YYYY-MM-DD', ma il resto del
    # modulo lavora con Timestamp: normalizziamo qui una volta sola.
    if begin_date is not None and not isinstance(begin_date, pd.Timestamp):
        begin_date = pd.to_datetime(begin_date)
    if end_date is not None and not isinstance(end_date, pd.Timestamp):
        end_date = pd.to_datetime(end_date)

    asset_columns=list(weights.keys())
    prices, begin_date, end_date = prepare_price_dataframe(pd.read_csv(data_path, sep=";"), begin_date=begin_date, end_date=end_date, asset_columns=asset_columns)
    # Ogni asset con peso > 0 deve avere un prezzo per tutta la finestra richiesta.
    # Un NaN (asset che parte dopo, o che finisce prima) rende il valore di
    # portafoglio non finito: storicamente il risultato era "capitale finale 0.00".
    assets_attivi = [c for c in asset_columns if float(weights.get(c, 0.0) or 0.0) > 0.0]
    incompleti = [c for c in assets_attivi if prices[c].isna().any()]
    if incompleti:
        dettagli = []
        for c in incompleti:
            validi = prices[c].dropna().index
            dettagli.append(f"{c}: nessun prezzo nella finestra" if len(validi) == 0
                            else f"{c}: prezzi solo dal {validi[0].date()} al {validi[-1].date()}")
        raise ValueError(
            "Finestra temporale non coperta da tutti gli asset selezionati "
            f"(richiesta {prices.index[0].date()} / {prices.index[-1].date()}): "
            + "; ".join(dettagli)
            + ". Restringere la data iniziale o finale all'intervallo comune."
        )

    dates = prices.index
    initial_prices = prices.iloc[0]

    # Initialize tracker
    tracker = PortfolioTracker(asset_columns=asset_columns, begin_date=begin_date)

    # Ideal portfolio (zero costs) — its "broker" will be labeled as "gross" in output
    ideal_pf, _ = Portfolio.from_weights(
        prices=initial_prices, value=initial_value,
        weights=weights, brokerage_fee_rate=0., annual_costs_rate=0., tax_rate=0., bollo_rate=0.)
    ideal_rebalancer = Rebalancer(
        target_weights=pd.Series(weights), threshold=rebalance_threshold, tax_rate=0.)

    # Real portfolio
    real_pf, fees = Portfolio.from_weights(
        prices=initial_prices, value=initial_value,
        weights=weights, brokerage_fee_rate=brokerage_fee_rate,
        annual_costs_rate=annual_costs_rate, tax_rate=tax_rate)
    real_rebalancer = Rebalancer(
        target_weights=pd.Series(weights), threshold=rebalance_threshold, tax_rate=tax_rate)

    # Log initial state (t=0)
    tracker.update(real_pf, dates[0], gross_portfolio=ideal_pf,
        taxes=pd.Series(0., index=real_pf.prices.index), costs=fees,
        trade_deltas={col: 0. for col in asset_columns})

    for i in range(1, len(dates)):
        # 1. Update prices
        real_pf.prices = prices.iloc[i]
        ideal_pf.prices = prices.iloc[i]

        # 2. Apply daily holding costs (compounds; no-op for ideal with zero costs)
        real_pf.apply_holding_costs()
        ideal_pf.apply_holding_costs()

        # 3. Check and execute rebalance
        costs, taxes, trade_deltas = real_rebalancer.rebalance(real_pf)
        ideal_rebalancer.rebalance(ideal_pf)

        # 4. Log state
        tracker.update(real_pf, dates[i], gross_portfolio=ideal_pf,
            taxes=taxes, costs=costs, trade_deltas=trade_deltas)

    df_log, df_log_delta = tracker.to_dataframes()

    # Metriche di rischio (issue #17, #18) sulle tre serie, con le stesse convenzioni
    # dichiarate in metrics.py. Un valore non calcolabile resta None.
    serie = {"broker": "BrokerPortfolioValue", "net": "Net"}
    if "GrossPortfolioValue" in df_log.columns:
        serie["gross"] = "GrossPortfolioValue"
    risk = {nome: risk_metrics(df_log[col], risk_free_rate=risk_free_rate)
            for nome, col in serie.items()}

    if save_outputs:
        df_log.to_excel("output_ptf.xlsx")
        df_log_delta.to_excel("output_ptf_delta.xlsx")
        df_log.to_csv("output_ptf.csv")
        df_log_delta.to_csv("output_ptf_delta.csv")

    # Gli anni vanno calcolati sullo span effettivamente simulato: se la serie
    # parte dopo la data richiesta (o finisce prima), usare le date richieste
    # sottostima o sovrastima il CAGR. L'arrotondamento va fatto DOPO la divisione:
    # arrotondare prima manda in ZeroDivisionError ogni finestra sotto ~4 giorni.
    giorni = (dates[-1] - dates[0]).days
    if giorni <= 0:
        raise ValueError("La finestra di simulazione deve coprire almeno un giorno")
    years = round(giorni / 365.25, 2)
    if years <= 0:
        # una finestra di 1-2 giorni si arrotonda a 0,00: servono le frazioni esatte
        years = giorni / 365.25

    print(f"Orizzonte temporale   {dates[0].date()} / {dates[-1].date()}")
    print(
        f"Anni in simulazione   {years}"
    )
    print(f"CAGR  (gross)    {(tracker.compound_factor['gross_assets_value']**(1/years) - 1) * 100:.2f}%")
    print(f"CAGR  (broker)   {(tracker.compound_factor['broker_assets_value']**(1/years) - 1) * 100:.2f}%")
    print(f"CAGR  (net)      {(tracker.compound_factor['net_assets_value']**(1/years) - 1) * 100:.2f}%")

    print(tracker.compound_factor['net_assets_value'])
    print(f"Total compound return (gross)  {tracker.compound_factor['gross_assets_value'] * 100:.2f}%")
    print(f"Total compound return (broker) {tracker.compound_factor['broker_assets_value'] * 100:.2f}%")
    print(f"Total compound return (net)    {tracker.compound_factor['net_assets_value'] * 100:.2f}%")

    print(f"Capitale iniziale {initial_value}")
    print(f"Valore finale gross {ideal_pf.broker_assets_value:.2f}")
    print(f"Capitale finale {real_pf.broker_assets_value:.2f}")
    print(f"Capitale finale liquido {real_pf.net_assets_value:.2f}")

    m = risk["net"]
    def _p(x): return "n.d." if x is None else f"{x * 100:.2f}%"
    def _r(x): return "n.d." if x is None else f"{x:.2f}"
    print(f"Volatilità annua (netta)  {_p(m['volatility'])}")
    print(f"Max drawdown (netto)      {_p(m['max_drawdown'])}")
    if m["peak_date"] is not None:
        print(f"  da {m['peak_date'].date()} a {m['trough_date'].date()}  ({m['amount']:.2f} EUR)")
    print(f"Sharpe  (netto, rf {risk_free_rate * 100:.2f}%)  {_r(m['sharpe'])}")
    print(f"Sortino (netto)           {_r(m['sortino'])}")
    print(f"Ulcer index (netto)       {_p(m['ulcer_index'])}")
    print(f"Calmar (netto)            {_r(m['calmar'])}")

    # La figura si crea solo se serve: con plot=False e save_outputs=False il grafico
    # non lo vede nessuno, e crearlo dentro un thread che non e' il main (Streamlit,
    # AppTest) con un backend interattivo fa terminare il processo.
    if plot or save_outputs:
        plt.semilogy(df_log.index, tracker.compound_return['gross_assets_value'], label='gross')
        plt.semilogy(df_log.index, tracker.compound_return['broker_assets_value'], label='broker')
        plt.semilogy(df_log.index, tracker.compound_return['net_assets_value'], label='net')
        plt.xlabel("Data")
        plt.ylabel("Compound Return %")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        if save_outputs:
            plt.savefig("plot.png")
        if plot:
            plt.show()
    else:
        plt.close()

    summary = {
        "begin_date": dates[0],
        "end_date": dates[-1],
        "years": years,
        "cagr_gross": tracker.compound_factor["gross_assets_value"] ** (1 / years) - 1,
        "cagr_broker": tracker.compound_factor["broker_assets_value"] ** (1 / years) - 1,
        "cagr_net": tracker.compound_factor["net_assets_value"] ** (1 / years) - 1,
        "final_gross": ideal_pf.broker_assets_value,
        "final_broker": real_pf.broker_assets_value,
        "final_net": real_pf.net_assets_value,
        "risk_metrics": risk,
        "risk_free_rate": risk_free_rate,
    }
    return df_log, df_log_delta, summary


if __name__ == "__main__":
    weights = {
        'VTSIM': 0.60,
        'SPYSIM': 0.00,
        'VXUSSIM': 0.00,
        'GLDSIM': 0.10,
        'CASHX': 0.00,  # Cash as liquidity
        'SHYSIM': 0.00,
        'IEFSIM': 0.00,
        'TLTSIM': 0.00,
        'ZROZSIM': 0.25,
        'KMLMSIM': 0.00,
        'DBMFSIM': 0.05,
    }

    backtest(
        initial_value=10000,
        weights=weights,
        begin_date=pd.to_datetime("2010-01-02"),
        end_date=pd.to_datetime("2025-09-01"),
        brokerage_fee_rate=0.0029,
        rebalance_threshold=0.1,
        tax_rate=0.26,
    )