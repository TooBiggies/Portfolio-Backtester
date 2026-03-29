import pandas as pd
import numpy as np

from contextlib import contextmanager

class Portfolio:
    def __init__(self, prices: pd.Series, initial_value: float = 1., brokerage_fee_rate: float=0., annual_costs_rate: float=0.):
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
        self.annual_costs_rate = annual_costs_rate
        self.initial_value = initial_value

    @classmethod
    def from_weights(cls, prices, value, weights, brokerage_fee_rate, annual_costs_rate):
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
        portfolio = cls(
            prices=prices,
            initial_value=value,
            brokerage_fee_rate=brokerage_fee_rate,
            annual_costs_rate=0.002
        )

        fees = 0.
        # 2. Allocate capital based on weights
        for asset, weight in weights.items():
            # Ensure asset exists in price data and weight is positive
            if asset in portfolio.assets and weight > 0:
                price = prices[asset]
                if price > 0:
                    units = (value * weight) / price
                    # Execute the buy order internally
                    fees += portfolio.buy(price, asset, units)

        return portfolio, fees

    @property
    def assets(self):
        """
        Returns as pd.Index the list of unique asset symbols currently held in the portfolio.
        """
        return self.holdings.index

    @property
    def annual_costs(self):
        """
        Returns the calculated annual costs based on the current portfolio value and rate.
        """

        return self.value*self.annual_costs_rate

    @property
    def assets_values(self):
        """
        Returns a pd.Series of market values of each holding (holdings * current price).
        """
        return self.holdings * self.prices

    @property
    def value(self):
        """
        Returns the total gross value of the portfolio (sum of asset market values).
        """
        return self.assets_values.sum()  # Gross = TotValue

    @property
    def weights(self):
        """
        Returns a pd.Series: The allocation weight of each asset (value / total value) or a Series of 0.0 if value is 0 or negative.
        """
        return self.assets_values / self.value if self.value > 0 else pd.Series(0.0, index=self.holdings.index)

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

    def sell(self, price: float, asset: str, units: float, tax_rate: float=0.26):
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
        tax = max(0.0, units * (price - pmc)) * tax_rate
        fee = units * price * self.brokerage_fee_rate

        self.holdings[asset] -= units
        self.assets_costs[asset] -= units * pmc

        return fee, tax

    def trade(self, asset: str, units: float, tax_rate: float=0.26):
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

    def cash_out(self, tax_rate: float=0.26):
        "sell everything"

        broker_value = self.value
        total_taxes, total_costs = (0., 0.)
        for asset in self.holdings.index:
            taxes, costs = self.sell(self.prices[asset], asset, self.holdings[asset], tax_rate)
            total_costs += costs
            total_taxes += taxes

        return broker_value - total_costs - total_taxes

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
        self.target_weights = target_weights
        self.threshold = threshold
        self.tax_rate = tax_rate

    def rebalance(self, portfolio) -> tuple[float, float, dict]:
        """
        Calculates trades required to rebalance the portfolio and estimates costs.

        Compares current portfolio weights against target weights. If the deviation
        for any asset exceeds the threshold, trade units are calculated. The method
        then simulates execution via the portfolio object to determine fees and taxes.

        Args:
            portfolio (Portfolio): The portfolio object containing current positions,
                prices, and methods for `buy` and `sell` to estimate costs.

        Returns:
            tuple[float, float, dict]: A tuple containing:
                - total_tax (float): Estimated total capital gains tax payable.
                - total_cost (float): Estimated total transaction fees/costs.
                - trade_deltas (dict): Mapping of asset names to monetary value of the trade.
                    Positive values indicate buys, negative values indicate sells.
                    Returns zeros for all assets if the threshold is not breached.
        """

        delta = self.target_weights - portfolio.weights

        if not np.any(np.abs(delta) > self.threshold):
            return 0.0, 0.0, {asset: 0.0 for asset in portfolio.assets}

        V = portfolio.value
        V_prime = V
        converged = False

        while not converged:
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
            converged = abs(new_V_prime / V_prime - 1) < 1e-8
            V_prime = new_V_prime

        # Apply trades to the real portfolio
        trade_deltas = {}
        for asset, units in trades.items():
            trade_deltas[asset] = units * portfolio.prices[asset]
            if units < 0:
                portfolio.sell(portfolio.prices[asset], asset, -units, self.tax_rate)
            elif units > 0:
                portfolio.buy(portfolio.prices[asset], asset, units)

        return total_tax, total_cost, trade_deltas

class PortfolioTracker:
    """
    Tracks portfolio performance, returns, and cash flows over time.

    This class maintains a historical log of portfolio values, daily returns,
    compound growth, taxes, transaction costs, and asset-level allocations.
    It is designed to generate DataFrames compatible with reporting tools (e.g., Excel).

    Attributes:
        current_year (int): Tracks the current simulation year for annual cost application.
        prev_net_value (float): The net portfolio value from the previous update step.
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

        self.prev_net_value = None
        self.compound_factor = 1.0
        self.log = []
        self.delta_log = []
        self.asset_columns = asset_columns  # Exact column order for Excel


    def update(self, portfolio: 'Portfolio', date: pd.Timestamp, taxes: float = 0.0, costs: float = 0.0, trade_deltas: dict = None):
        """
        Records the portfolio state for a specific date.

        Calculates daily returns based on net value (after taxes and costs), updates
        the compound return factor, and logs asset allocations. If the year changes,
        annual maintenance costs are added to the transaction costs.

        Args:
            portfolio (Portfolio): The current portfolio object containing values and prices.
            date (pd.Timestamp): The date of this recording.
            taxes (float, optional): Taxes incurred during this period. Defaults to 0.0.
            costs (float, optional): Transaction costs incurred during this period. Defaults to 0.0.
            trade_deltas (dict, optional): Monetary value of trades per asset.
                Defaults to None (treated as zeros).

        Note:
            - In the internal log, Taxes and Transaction Costs are stored as negative
              values to represent cash outflows.
            - Annual costs (portfolio.annual_costs) are applied automatically when
              the date year increments.
        """


        if date.year > self.current_year:
            self.current_year = date.year
            costs += portfolio.annual_costs

        curr_net = portfolio.value - taxes - costs

        if self.prev_net_value is None:
            daily_ret = 0.0
        elif self.prev_net_value == 0:
            daily_ret = 0.0
        else:
            daily_ret = curr_net / self.prev_net_value - 1.0

        self.compound_factor *= (1.0 + daily_ret)

        # Build asset value row (align with expected columns)
        asset_values = portfolio.assets_values.reindex(self.asset_columns, fill_value=0.0)

        with portfolio.simulate_transactions() as temp: 
            cash_out = temp.cash_out()

        # Log entry for df_log
        self.log.append({
            'Date': date,
            'Return': daily_ret,
            'Compound Return': self.compound_factor,
            'TotValue': portfolio.value,
            'CashOut': cash_out,
            'Taxes': -taxes,  # Negate to match original Excel sign convention
            'TransacCost': -costs,
            **{col: asset_values[col] for col in self.asset_columns}
        })

        # Log entry for df_log_delta
        if trade_deltas is None:
            trade_deltas = {col: 0.0 for col in self.asset_columns}

        # Align trade deltas with asset columns, keep internal sign (positive=buy, negative=sell)
        delta_row = {col: trade_deltas.get(col, 0.0) for col in self.asset_columns}
        delta_row['Date'] = date
        self.delta_log.append(delta_row)

        self.prev_net_value = curr_net

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