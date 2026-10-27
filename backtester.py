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

    if begin_date is None:
        begin_date = pd.to_datetime(df.dropna()[date_column].min())
    if end_date is None:
        end_date = pd.to_datetime(df.dropna()[date_column].max())

    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column], dayfirst=True, errors="coerce")
    df = df[(df[date_column] >= pd.to_datetime(begin_date))].copy()
    df = df[(df[date_column] <= pd.to_datetime(end_date))].copy()
    df = df.reset_index(drop=True)

    if asset_columns is None:
        # Auto-detect: exclude Date column
        asset_columns = [col for col in df.columns if col != date_column]

    # Set Date as index
    df_prices = df.set_index(date_column)[asset_columns]

    return df_prices, begin_date, end_date


def backtest(initial_value, weights, begin_date=None, end_date=None, brokerage_fee_rate=0., rebalance_threshold=0.1, tax_rate=0., annual_costs_rate=0., plot=False, save_outputs=True, risk_free_rate=0.0):
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

    asset_columns=list(weights.keys())
    prices, begin_date, end_date = prepare_price_dataframe(pd.read_csv("./Timeseries.csv", sep=";"), begin_date=begin_date, end_date=end_date, asset_columns=asset_columns)
    dates = prices.index
    initial_prices = prices.iloc[0]

    # Initialize tracker
    tracker = PortfolioTracker(asset_columns=asset_columns, begin_date=begin_date)

    # Ideal portfolio (zero costs) — its "broker" will be labeled as "gross" in output
    ideal_pf, _ = Portfolio.from_weights(
        prices=initial_prices, value=initial_value,
        weights=weights, brokerage_fee_rate=0., annual_costs_rate=0.)
    ideal_rebalancer = Rebalancer(
        target_weights=pd.Series(weights), threshold=rebalance_threshold, tax_rate=0.)

    # Real portfolio
    real_pf, fees = Portfolio.from_weights(
        prices=initial_prices, value=initial_value,
        weights=weights, brokerage_fee_rate=brokerage_fee_rate,
        annual_costs_rate=annual_costs_rate)
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

    years = round(((pd.to_datetime(end_date) - pd.to_datetime(begin_date)).days / 365.25), 2)

    print(f"Orizzonte temporale   {begin_date} / {end_date}")
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
        "begin_date": pd.to_datetime(begin_date),
        "end_date": pd.to_datetime(end_date),
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