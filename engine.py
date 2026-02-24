import pandas as pd
import numpy as np


class Portfolio:

    def __init__(self, prices: pd.DataFrame, initial_cash: float = 0.0, initial_value: float = 1.):
        self.prices = prices
        self.holdings = pd.Series(0.0, index=prices.columns)
        self.total_cost = pd.Series(0.0, index=prices.columns)
        self.cash = initial_cash
        self.tax_paid = 0.0
        
        self.initial_value = initial_value

    @property
    def net_value(self):
        return (self.holdings * self.prices).sum() + self.cash

    @property
    def assets(self):
        return self.holdings.columns

    @property
    def gross_value(self):
        return self.value + self.tax_paid
            
    @property
    def net_return(self):
        return self.net_value / self.initial_capital - 1

    @property
    def gross_return(self):
        return self.gross_value / self.initial_capital - 1
        
    @property
    def weights(self):
        asset_value = self.holdings * self.prices
        total_value = self.value
        if total_value == 0:
            return pd.Series(0.0, index=self.holdings.index)
        return asset_value / total_value

    @property
    def average_cost(self):
        return self.total_cost / self.holdings

    def buy(self, asset: str, units: float):
        price = self.prices[asset]
        cost = units * price

        self.holdings[asset] += units
        self.total_cost[asset] += cost
        self.cash -= cost

    def sell(self, asset: str, units: float, transactional_cost_rate: float=0.26):

        if units > self.holdings[asset]:
            raise ValueError("Cannot sell more units than currently held.")

        price = self.prices[asset]
        avg_cost = self.average_cost[asset]

        realized_gain = units * (price - avg_cost)

        tax = max(0.0, realized_gain) * self.tax_rate

        # Update state
        self.holdings[asset] -= units
        self.total_cost[asset] -= units * avg_cost
        self.cash += units*price*(1-transactional_cost_rate) - tax 

        self.tax_paid += tax  

        return realized_gain, tax

    def trade(self, asset: str, units: float): 
        if units<0: 
            self.sell(asset, abs(units)) 
        else:
            self.buy(asset, abs(units))


class PortfolioTracker:

    def __init__(self):
        self.returns = []
        self.compound_returns = []
        self.total_value = []
        self.taxes = []
        self.transaction_cost = []
        self.assets_value = []
        self.delta_notional = []

    def update(self, portfolio: Portfolio):
        current_value = portfolio.value

        self.total_value.append(current_value)

        if len(self.total_value) > 1:
            ret = current_value / self.total_value[-2] - 1
        else:
            ret = 0.0

        self.returns.append(ret)

        if len(self.compound_returns) > 0:
            compounded = (1 + self.compound_returns[-1]) * (1 + ret) - 1
        else:
            compounded = ret

        self.compound_returns.append(compounded)
        self.assets_value.append((portfolio.holdings * portfolio.current_prices).sum())


    
class Rebalancer: 

    def __init__(self, target_weights, threshold):
        self.target_weights = target_weights
        self.threshold = threshold

    def rebalance(self, portfolio):
        current_weights = portfolio.weights

        delta_weights = current_weights-self.target_weights
        if np.any(np.abs(delta_weights)>self.threshold):
            

            for asset in portfolio.assets:
                units = delta_weights[asset] * portfolio.value / portfolio.prices[asset]

                portfolio.trade(asset, units)



# major issues:
# - should taxation change notional?
# - how to address the rebalancing not being 100% accurate?