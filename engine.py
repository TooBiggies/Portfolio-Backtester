import pandas as pd
import numpy as np

class Portfolio:
    def __init__(self, prices: pd.Series, initial_value: float = 1., brokerage_fee_rate: float=0.):
        self.prices = prices
        self.holdings = pd.Series(0.0, index=prices.index)
        self.assets_costs = pd.Series(0.0, index=prices.index)  # For PMC

        self.brokerage_fee_rate = brokerage_fee_rate
        self.initial_value = initial_value

    @property
    def assets(self): return self.holdings.index

    @property
    def assets_values(self): return self.holdings * self.prices
    
    @property
    def value(self): return self.assets_values.sum()  # Gross = TotValue
        
    @property
    def weights(self):
        return self.assets_values / self.value if self.value > 0 else pd.Series(0.0, index=self.holdings.index)
    
    def _pmc(self, asset):
        return self.assets_costs[asset] / self.holdings[asset] if self.holdings[asset] > 0 else 0.0

    def buy(self, price: float, asset: str, units: float):
        cost_basis = units * price
        fee = units * price * self.brokerage_fee_rate 

        self.holdings[asset] += units
        self.assets_costs[asset] += cost_basis  

        return fee

    def sell(self, price: float, asset: str, units: float, tax_rate: float=0.26):
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
        price = self.prices[asset]
        return self.sell(price, asset, -units, tax_rate) if units < 0 else self.buy(price, asset, units)


class Rebalancer:
    def __init__(self, target_weights, threshold, tax_rate=0.26):
        self.target_weights = target_weights
        self.threshold = threshold
        self.tax_rate = tax_rate

    def rebalance(self, portfolio) -> tuple[float, float]:
        delta = self.target_weights - portfolio.weights
        if not np.any(np.abs(delta) > self.threshold):
            return 0.0, 0.0
        
        snapshot_value = portfolio.value
        trades = {
            asset: delta[asset] * snapshot_value / portfolio.prices[asset]
            for asset in portfolio.assets
        }
        total_tax, total_cost = 0.0, 0.0
        for asset, units in trades.items():
            if units < 0:
                fee, tax = portfolio.sell(portfolio.prices[asset], asset, -units, self.tax_rate)
                total_tax += tax
                total_cost += fee
            else:
                fee = portfolio.buy(portfolio.prices[asset], asset, units)
                total_cost += fee
        return total_tax, total_cost



class PortfolioTracker:
    def __init__(self):
        self.prev_net_value = None
        self.compound_factor = 1.0
        self.log = []

    def update(self, portfolio: Portfolio, date, taxes=0.0, costs=0.0):
        curr_net = portfolio.value - taxes - costs
        
        if self.prev_net_value is None:
            daily_ret = 0.0
        elif self.prev_net_value == 0:
            daily_ret = 0.0
        else:
            daily_ret = curr_net / self.prev_net_value - 1.0
        
        self.compound_factor *= (1.0 + daily_ret)
        
        # Log entry
        self.log.append({
            'date': date,
            'TotValue': portfolio.value,
            'NetTotValue': curr_net,
            'Taxes': -taxes,  # Negate to match old code sign
            'TransacCost': -costs,
            'Return': daily_ret,
            'CompoundReturn': self.compound_factor
        })
        
        self.prev_net_value = curr_net

    def to_dataframe(self):
        return pd.DataFrame(self.log).set_index('date')