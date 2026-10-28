import pandas as pd
import numpy as np

from contextlib import contextmanager

class Portfolio:
    def __init__(self, prices: pd.Series, initial_value: float = 1., brokerage_fee_rate: float=0., ter: pd.Series = None, tax_rate: float = 0.26):
        """
        Initializes a Portfolio instance with price data and financial settings.

        Args:
            prices (pd.Series): A pandas Series containing asset prices indexed by time.
            initial_value (float): The starting capital amount of the portfolio. Defaults to 1.
            brokerage_fee_rate (float): The rate charged for brokerage transactions (e.g., 0.001 for 0.1%). Defaults to 0.
            annual_costs_rate (float): The rate charged for annual holding costs. Defaults to 0.

        Attributes:
            prices: The source of asset prices.
            holdings: Current quantity of assets held.
            assets_costs: Cost basis for each asset (used for tax/PMC calculations).
        """

        self.prices = prices
        self.holdings = pd.Series(0.0, index=prices.index)
        self.assets_costs = pd.Series(0.0, index=prices.index)  # For PMC

        self.brokerage_fee_rate = brokerage_fee_rate
        self.initial_value = initial_value
        # Aliquota per l'imposta di uscita (net_assets_value / cash_out_costs).
        # Prima era cablata a 0.26 dentro cash_out_costs: il "netto" ignorava
        # l'aliquota configurata nel backtest.
        self.tax_rate = tax_rate

        if ter is None:
            self.ter = pd.Series(0.0, index=prices.index, dtype='float64')
        else:
            self.ter = ter.reindex(prices.index, fill_value=0.0)

        self.bollo = pd.Series(0.002/252, index=prices.index) # assumo di pagare ogni giorno lo 0.2/252 del controvalore giornaliero

    @classmethod
    def from_weights(cls, prices, value, weights, brokerage_fee_rate, annual_costs_rate, tax_rate: float = 0.26):
        """
        Factory method to create a Portfolio and immediately allocate
        capital based on target weights at T=0.

        Args:
            prices (pd.Series): Prices of assets at T=0.
            value (float): Total starting capital.
            weights (dict): Target allocation weights {asset: weight}.
            brokerage_fee_rate (float): Fee rate for transactions.

        Returns:
            Portfolio: An initialized Portfolio instance with holdings.
        """
        # 1. Instantiate the empty portfolio
        ter = pd.Series(annual_costs_rate / 252, index=prices.index)
        portfolio = cls(
            prices=prices,
            initial_value=value,
            brokerage_fee_rate=brokerage_fee_rate,
            ter=ter,
            tax_rate=tax_rate,
        )

        fees = {}
        # 2. Allocate capital based on weights
        for asset, weight in weights.items():
            # Ensure asset exists in price data and weight is positive
            if asset in portfolio.assets and weight > 0:
                price = prices[asset]
                if price > 0:
                    units = (value * weight) / (price * (1 + brokerage_fee_rate))
                    # Execute the buy order internally
                    fees[asset] = -portfolio.buy(price, asset, units)

        return portfolio, fees

    @property
    def assets(self):
        return self.holdings.index

    @property
    def pmc(self):
        return pd.Series([self._pmc(asset) for asset in self.prices.index], index=self.prices.index )

    @property
    def daily_annual_costs(self):
        return self.broker_assets_values * (self.ter + self.bollo)

    @property
    def broker_assets_values(self):
        return self.holdings * self.prices

    @property
    def net_assets_values(self):
         return self.broker_assets_values - self.cash_out_costs()

    @property
    def broker_assets_value(self):
        return self.broker_assets_values.sum()

    @property
    def net_assets_value(self):
        return self.net_assets_values.sum()

    @property
    def weights(self):
        return self.broker_assets_values / self.broker_assets_value if self.broker_assets_value > 0 else pd.Series(0.0, index=self.holdings.index)

    def apply_holding_costs(self) -> None:
        factor = 1.0 - (self.ter + self.bollo)
        self.holdings *= factor
        self.assets_costs *= factor

    def _pmc(self, asset):
        """
        Internal method to calculate the Purchase Mean Cost (Average Cost Basis) for an asset.
        Returns the cost basis per unit (cost / units) or 0.0 if no holdings exist.
        """
        return self.assets_costs[asset] / self.holdings[asset] if self.holdings[asset] > 0 else 0.0

    @contextmanager
    def simulate_transactions(self):
        """
        Context manager that temporarily allows mutations to the portfolio,
        restoring the original state on exit.
        """
        saved_holdings = self.holdings.copy()
        saved_costs = self.assets_costs.copy()
        try:
            yield self
        finally:
            self.holdings = saved_holdings
            self.assets_costs = saved_costs


    def buy(self, price: float, asset: str, units: float):
        """
        Executes a purchase order for a specific asset.

        Args:
            price (float): The current market price of the asset.
            asset (str): The symbol of the asset to buy.
            units (float): The quantity of units to purchase.

        Returns:
            float: The total brokerage fee incurred for this transaction.

        Side Effects:
            - Increases holdings for the specified asset.
            - Updates asset cost basis (assets_costs).
        """
        cost_basis = units * price
        fee = units * price * self.brokerage_fee_rate

        self.holdings[asset] += units
        self.assets_costs[asset] += cost_basis

        return fee

    def sell(self, price: float, asset: str, units: float, tax_rate: float = None):
        """
        Executes a sale order for a specific asset, calculating tax and fees.

        Args:
            price (float): The current market price of the asset.
            asset (str): The symbol of the asset to sell.
            units (float): The quantity of units to sell.
            tax_rate (float): The capital gains tax rate applied to profits. Defaults to 0.26 (26%).

        Returns:
            tuple: A tuple of (transaction_fee, capital_gains_tax).

        Side Effects:
            - Decreases holdings for the specified asset.
            - Updates asset cost basis (assets_costs).
            - Raises ValueError if attempting to sell more than held.
        """
        if units > self.holdings[asset] * 1.0001:
            raise ValueError("Cannot sell more than held")
        units = min(units, self.holdings[asset])
        pmc = self._pmc(asset)
        rate = self.tax_rate if tax_rate is None else tax_rate
        tax = max(0.0, units * (price - pmc)) * rate
        fee = units * price * self.brokerage_fee_rate

        self.holdings[asset] -= units
        self.assets_costs[asset] -= units * pmc

        return (fee, tax)

    def trade(self, asset: str, units: float, tax_rate: float = None):
        """
        Convenience method to handle buying or selling an asset based on the sign of units.

        Args:
            asset (str): The symbol of the asset to trade.
            units (float): The quantity to trade. Negative values sell, positive values buy.
            tax_rate (float): The capital gains tax rate for selling. Defaults to 0.26.

        Returns:
            tuple or float: Returns (fee, tax) if selling, or fee if buying.
            Note: Return type is inconsistent with implementation (buy returns float, sell returns tuple).
        """
        price = self.prices[asset]
        return self.sell(price, asset, -units, tax_rate) if units < 0 else self.buy(price, asset, units)

    def cash_out_costs(self, tax_rate: float = None):
        "sell everything — returns a Series of exit costs per asset"

        rate = self.tax_rate if tax_rate is None else tax_rate
        costs_per_asset = pd.Series(0., index=self.holdings.index)
        with self.simulate_transactions() as temp:
            for asset in temp.holdings.index:
                fee, tax = temp.sell(temp.prices[asset], asset, temp.holdings[asset], rate)
                costs_per_asset[asset] = fee + tax

            return costs_per_asset

class Rebalancer:
    """
    Calculates trade requirements to align a portfolio with target asset weights.

    This class determines the necessary buys and sells to reach a target allocation
    based on a specified deviation threshold. It also estimates the associated
    transaction costs and capital gains taxes by interacting with the Portfolio object.

    Attributes:
        target_weights (pd.Series or dict): The desired weight allocation for each asset.
        threshold (float): The minimum absolute weight deviation required to trigger rebalancing.
        tax_rate (float): The capital gains tax rate applied to profitable sales (default 0.26).
    """

    def __init__(self, target_weights, threshold, tax_rate=0.26):
        """
        Initializes the Rebalancer with target configuration.

        Args:
            target_weights (pd.Series or dict): Mapping of asset names to target weights (0.0 to 1.0).
            threshold (float): Rebalancing trigger threshold (e.g., 0.05 for 5% deviation).
            tax_rate (float, optional): Capital gains tax rate. Defaults to 0.26.
        """
        # La docstring dichiara 'pd.Series or dict': normalizziamo a Series, che e'
        # l'unico tipo con cui funzionano la sottrazione e l'allineamento per asset.
        self.target_weights = (target_weights if isinstance(target_weights, pd.Series)
                               else pd.Series(target_weights))
        self.threshold = threshold
        self.tax_rate = tax_rate

    def rebalance(self, portfolio) -> tuple[dict, dict, dict]:
        """
        Calculates trades required to rebalance the portfolio and estimates costs.

        Compares current portfolio weights against target weights. If the deviation
        for any asset exceeds the threshold, trade units are calculated. The method
        then simulates execution via the portfolio object to determine fees and taxes.

        Args:
            portfolio (Portfolio): The portfolio object containing current positions,
                prices, and methods for `buy` and `sell` to estimate costs.

        Returns:
            tuple[dict, dict, dict]: A tuple containing, in this order:
                - costs (dict): fee per asset, negative (cash out); 0.0 if no rebalance.
                - taxes (dict): capital gains tax per asset, negative; 0.0 if no rebalance.
                - trade_deltas (dict): traded value per asset, positive = buy,
                  negative = sell. All zeros if the threshold is not breached.
        """

        delta = self.target_weights - portfolio.weights

        if not np.any(np.abs(delta) > self.threshold):
            return {asset: 0.0 for asset in portfolio.assets}, {asset: 0.0 for asset in portfolio.assets}, {asset: 0.0 for asset in portfolio.assets}

        V = portfolio.broker_assets_value
        if not np.isfinite(V) or V <= 0:
            raise ValueError(
                "Valore del portafoglio nullo o non finito all'atto del ribilanciamento: "
                "verificare che ogni asset selezionato abbia un prezzo valido alla data iniziale."
            )
        V_prime = V
        converged = False
        iterations = 0
        max_iterations = 50

        while not converged:
            iterations += 1
            if iterations > max_iterations:
                raise RuntimeError(
                    f"Il ribilanciamento non converge in {max_iterations} iterazioni: "
                    "prezzi non finiti o portafoglio a valore nullo."
                )
            with portfolio.simulate_transactions() as temp:
                trades = {
                    asset: (self.target_weights[asset] * V_prime / temp.prices[asset]) - temp.holdings[asset]
                    for asset in temp.assets
                }

                total_tax, total_cost = 0.0, 0.0
                for asset, units in trades.items():
                    if units < 0:
                        fee, tax = temp.sell(temp.prices[asset], asset, -units, self.tax_rate)
                        total_tax += tax
                        total_cost += fee
                    elif units > 0:
                        fee = temp.buy(temp.prices[asset], asset, units)
                        total_cost += fee

            new_V_prime = V - total_tax - total_cost
            if not np.isfinite(new_V_prime):
                raise ValueError(
                    "Valore del portafoglio non finito durante il ribilanciamento "
                    "(prezzi NaN nella finestra selezionata?)."
                )
            converged = abs(new_V_prime / V_prime - 1) < 1e-8
            V_prime = new_V_prime

        # Apply trades to the real portfolio
        trade_deltas = {}
        taxes = {k: 0. for k in portfolio.prices.index}
        costs = {k: 0. for k in portfolio.prices.index}
        for asset, units in trades.items():
            trade_deltas[asset] = units * portfolio.prices[asset]
            if units < 0:
                c, t = portfolio.sell(portfolio.prices[asset], asset, -units, self.tax_rate)
                costs[asset] = -c
                taxes[asset] = -t
            elif units > 0:
                costs[asset] = -portfolio.buy(portfolio.prices[asset], asset, units)
                taxes[asset] = 0.

        return costs, taxes, trade_deltas

class PortfolioTracker:
    """
    Tracks portfolio performance, returns, and cash flows over time.

    This class maintains a historical log of portfolio values, daily returns,
    compound growth, taxes, transaction costs, and asset-level allocations.
    It is designed to generate DataFrames compatible with reporting tools (e.g., Excel).

    Attributes:
        current_year (int): Tracks the current simulation year for annual cost application.
        prev_value (dict): The various portfolio values from the previous update step.
        compound_return (dict): The various portfolio compounds.
        compound_factor (float): Cumulative return factor since inception.
        log (list): List of dictionaries containing daily performance metrics.
        delta_log (list): List of dictionaries containing daily trade cash flows.
        asset_columns (list): Ordered list of asset names for consistent DataFrame columns.
    """

    def __init__(self, asset_columns: list, begin_date: pd.Timestamp):
        """
        Initializes the tracker with asset schema and start date.

        Args:
            asset_columns (list): List of asset names defining the column order for output.
            begin_date (pd.Timestamp): The starting date of the tracking period.
        """
        self.current_year = begin_date.year

        self.prev_value = {"gross_assets_value": None, "broker_assets_value": None, "net_assets_value": None}
        self.compound_factor = {"gross_assets_value": 1., "broker_assets_value": 1., "net_assets_value": 1.}
        self.compound_return = {"gross_assets_value": [], "broker_assets_value": [], "net_assets_value": []}
        self.log = []
        self.delta_log = []
        self.asset_columns = asset_columns  # Exact column order for Excel

    def _update_compounds(self, portfolio, value_prop, label):

        curr_value = getattr(portfolio, value_prop)
        prev_value = self.prev_value[label]

        if prev_value is None:
            self.prev_value[label] = portfolio.initial_value
            self.compound_return[label].append(1.0)
            return
        else:
            daily_ret = curr_value / prev_value - 1.0 if prev_value != 0 else 0.0

        self.prev_value[label] = curr_value
        self.compound_factor[label] *= (1.0 + daily_ret)
        self.compound_return[label].append(self.compound_factor[label])

    def update(self, portfolio, date, gross_portfolio=None, taxes={}, costs={}, trade_deltas={}):

        if gross_portfolio is not None:
            self._update_compounds(gross_portfolio, 'broker_assets_value', 'gross_assets_value')
        self._update_compounds(portfolio, 'broker_assets_value', 'broker_assets_value')
        self._update_compounds(portfolio, 'net_assets_value', 'net_assets_value')

        # Build asset value row (align with expected columns)
        get_per_asset = lambda x: getattr(portfolio, x).reindex(self.asset_columns, fill_value=0.0)

        prices_dict = {f"Price_{k}": v for k, v in get_per_asset('prices').to_dict().items()}
        pmc_dict = {f"PMC_{k}": v for k, v in get_per_asset('pmc').to_dict().items()}
        broker_dict = {f"Broker_{k}": v for k, v in get_per_asset('broker_assets_values').to_dict().items()}
        net_dict = {f"Net_{k}": v for k, v in get_per_asset('net_assets_values').to_dict().items()}
        costs_holding_dict = {f"HoldingCost_{k}": v for k, v in get_per_asset('daily_annual_costs').to_dict().items()}

        gross_dict = {}
        gross_value = None
        if gross_portfolio is not None:
            get_gross = lambda x: getattr(gross_portfolio, x).reindex(self.asset_columns, fill_value=0.0)
            gross_dict = {f"Gross_{k}": v for k, v in get_gross('broker_assets_values').to_dict().items()}
            gross_value = gross_portfolio.broker_assets_value

        taxes_dict = {f"Tax_{k}": v for k, v in taxes.items()}
        costs_trade_dict = {f"TradeCost_{k}": v for k, v in costs.items()}

        log_entry = {
            'Date': date,
            'BrokerPortfolioValue': portfolio.broker_assets_value,
            'Net': portfolio.net_assets_value,
            **prices_dict, **pmc_dict, **broker_dict, **net_dict, **costs_holding_dict,
            **taxes_dict, **costs_trade_dict,
        }
        if gross_portfolio is not None:
            log_entry['GrossPortfolioValue'] = gross_value
            log_entry.update(gross_dict)
        self.log.append(log_entry)

        # Log entry for df_log_delta
        if trade_deltas is None:
            trade_deltas = {col: 0.0 for col in self.asset_columns}

        # Align trade deltas with asset columns, keep internal sign (positive=buy, negative=sell)
        delta_row = {col: trade_deltas.get(col, 0.0) for col in self.asset_columns}
        delta_row['Date'] = date
        self.delta_log.append(delta_row)

    def to_dataframes(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Converts internal logs into pandas DataFrames.

        Constructs the final performance and trade logs, ensuring column order
        matches the initialization schema. Sets 'Date' as the index for both DataFrames.

        Returns:
            tuple[pd.DataFrame, pd.DataFrame]:
                - df_log: Performance log containing returns, values, taxes, costs, and asset holdings.
                - df_log_delta: Trade log containing monetary trade deltas per asset.
        """
        df_log = pd.DataFrame(self.log).set_index('Date')
        df_log_delta = pd.DataFrame(self.delta_log).set_index('Date')

        df_log = df_log

        df_log_delta = df_log_delta[self.asset_columns]

        return df_log, df_log_delta
