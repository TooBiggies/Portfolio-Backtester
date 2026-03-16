import sys
import logging
from datetime import datetime
import os
import pandas as pd
import matplotlib.pyplot as plt

from classes import portfolio_evo
from backtester_load_config import load_config
from backtester_report_creation import create_reports


def _infer_common_date_range(df: pd.DataFrame, asset_cols: list):
    """Return (common_start, common_end) across assets with non-null data."""
    starts = []
    ends = []
    for col in asset_cols:
        if col not in df.columns:
            continue
        series = df[col]
        valid_dates = df.loc[series.notna(), "Date"]
        if valid_dates.empty:
            return None, None
        starts.append(valid_dates.min())
        ends.append(valid_dates.max())
    if not starts or not ends:
        return None, None
    common_start = max(starts)
    common_end = min(ends)
    if common_start > common_end:
        return None, None
    return common_start, common_end


def _infer_dates_if_missing(imported_dataframe: pd.DataFrame, initial_w, start_date, end_date):
    """Infer missing start/end dates from the common range of selected assets."""
    if start_date and end_date:
        return start_date, end_date
    try:
        asset_cols = [c for c in imported_dataframe.columns if c != "Date"]
        if isinstance(initial_w, pd.Series):
            weights = [initial_w.get(c, 0.0) for c in asset_cols]
        else:
            weights = list(initial_w) if initial_w is not None else []
        selected_assets = [c for c, w in zip(asset_cols, weights) if w and float(w) > 0.0]
        if not selected_assets:
            return start_date, end_date
        common_start, common_end = _infer_common_date_range(imported_dataframe, selected_assets)
        if not start_date and common_start is not None:
            start_date = common_start
        if not end_date and common_end is not None:
            end_date = common_end
    except Exception:
        pass
    return start_date, end_date


def run_backtest(verbose: bool = False, calcola_minusvalenze: bool = False):
    logger = logging.getLogger('backtester')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(sh)

    # Load timeseries
    imported_dataframe = pd.read_csv("./Timeseries.csv", sep=';')
    imported_dataframe["Date"] = pd.to_datetime(imported_dataframe["Date"], dayfirst=True, errors="coerce")
    imported_dataframe = imported_dataframe[(imported_dataframe["Date"]>=pd.to_datetime("2000-01-03"))].copy()
    imported_dataframe = imported_dataframe[(imported_dataframe["Date"]<=pd.to_datetime("2025-09-04"))].copy().reset_index(drop=True)

    cfg, initial_w = load_config()
    initial_balance = cfg.CAPITAL
    start_date = cfg.START_DATE
    end_date = cfg.END_DATE
    # CLI flag takes priority; fall back to config value
    calcola_minusvalenze = calcola_minusvalenze or getattr(cfg, 'CALCOLA_MINUSVALENZE', False)

    # If dates are not provided, infer the widest common range across selected assets.
    if not start_date or not end_date:
        start_date, end_date = _infer_dates_if_missing(imported_dataframe, initial_w, start_date, end_date)

    logger.debug("Imported dataframe shape: %s", imported_dataframe.shape)
    if start_date:
        logger.debug("Backtest start date: %s", start_date)
    if end_date:
        logger.debug("Backtest end date: %s", end_date)

    ptf = portfolio_evo(initial_balance = initial_balance,
                        transac_cost_rate= cfg.TRANSAC_COST_RATE,
                        exp_rate=cfg.EXP_RATE,
                        tax_rate = cfg.TAX_RATE,
                        rebalance_threshold = cfg.REBALANCE_THRESHOLD,
                        initial_w = initial_w,
                        imported_dataframe= imported_dataframe,
                        start_date = start_date,
                        end_date = end_date,
                        stock_price_normalization= cfg.STOCK_PRICE_NORMALIZATION,
                        calcola_minusvalenze=calcola_minusvalenze)

    logger.debug("Portfolio initialized: IndexName=%s", ptf.IndexName)

    df_log       = pd.DataFrame(index = ptf.date)
    df_log_delta = pd.DataFrame(index = ptf.date)

    rebalance_explanations = []
    rebalance_transactions = []

    # helper defined locally (keeps previous behaviour)
    def log_portfolio_state(ptf_obj, stock_price=None, StockPrice=None, when=''):
        try:
            thr = 0.00001
            md_lines = []
            info_lines = []
            sp = stock_price if stock_price is not None else StockPrice
            if sp is not None:
                tot = ptf_obj.calculate_TotValue(sp)
                asset_vals = (ptf_obj.notional * sp)
                weights = asset_vals / tot if tot != 0 else pd.Series(0.0, index=ptf_obj.IndexName)
            else:
                weights = getattr(ptf_obj, 'w', pd.Series(0.0, index=ptf_obj.IndexName))
                try:
                    asset_vals = ptf_obj.notional * ptf_obj.StockPrice.loc[ptf_obj.StockPrice.index[-1], :]
                except Exception:
                    asset_vals = None

            to_show = {a: w for a, w in weights.items() if w >= thr}
            info_lines.append(f"Portfolio {when}: {len(to_show)} assets (threshold {thr*100:.6f}%)")
            md_lines.append(f"- Portfolio {when}: {len(to_show)} assets (threshold {thr*100:.6f}%)")
            for a, w in to_show.items():
                try:
                    notional = ptf_obj.notional.get(a, 0.0)
                except Exception:
                    notional = ''
                val = asset_vals[a] if asset_vals is not None and a in asset_vals else ''
                info_lines.append(f"  - {a}: weight={w*100:.6f}%, notional={notional if notional=='' else f'{notional:.6f}'}, value={val if val=='' else f'{val:.2f}' }")
                md_lines.append(f"- {a}: weight={w*100:.6f}%, notional={notional if notional=='' else f'{notional:.6f}'}, value={val if val=='' else f'{val:.2f}'}")

            for L in info_lines:
                logger.info(L)
            return "\n".join(md_lines)
        except Exception:
            logger.debug("Unable to log portfolio state at %s", when)
            return ""

    for i in ptf.StockPrice.index:
        ptf.reset_tax_transaccost()
        ptf.reset_delta_notional()

        StockPrice = ptf.StockPrice.loc[i, :]
        ptf.update_AssetValue_weight(StockPrice)

        logger.debug("Processing date index=%s date=%s", i, ptf.date[i])
        try:
            logger.debug("StockPrice (sample): %s", StockPrice.head().to_dict())
        except Exception:
            logger.debug("StockPrice: %s", StockPrice.to_dict())

        logger.debug("AssetValue: %s", ptf.AssetValue)
        logger.debug("TotValue: %s", ptf.calculate_TotValue(StockPrice))

        if ptf.check_rebalance():
            snap_before = log_portfolio_state(ptf, StockPrice=StockPrice, when=f"before rebalance {ptf.date[i].date()}")
            if snap_before:
                rebalance_explanations.append(f"### Portfolio snapshot before {ptf.date[i].date()}\n" + snap_before + "\n")

            # compute details
            try:
                delta_pre = (ptf.initial_w - ptf.w) * ptf.calculate_TotValue(StockPrice) / StockPrice
                deviations = (ptf.w - ptf.initial_w).abs()
                flagged = deviations[deviations > ptf.rebalance_threshold]
                tx_value = (abs(delta_pre) * StockPrice).sum()
                tx_cost_est = - tx_value * ptf.transactional_cost_rate
                mask_tax = (delta_pre < 0) & (StockPrice > ptf.PMC)
                tax_est = (delta_pre * StockPrice)[mask_tax].sum() * ptf.tax_rate if mask_tax.any() else 0.0

                md_lines = []
                for asset in flagged.index:
                    line = (
                        f"{asset}: current_w={ptf.w[asset]:.6f}, target_w={ptf.initial_w[asset]:.6f}, "
                        f"deviation={deviations[asset]:.6f}, delta_notional={delta_pre[asset]:.6f}, "
                        f"price={StockPrice[asset]:.6f}, trade_value={abs(delta_pre[asset])*StockPrice[asset]:.2f}"
                    )
                    md_lines.append(f"- {line}")

                entry = f"### Rebalance on {ptf.date[i].date()}\n"
                entry += f"- Threshold: {ptf.rebalance_threshold}\n"
                entry += f"- Flagged assets: {', '.join(flagged.index.tolist()) if not flagged.empty else 'none'}\n"
                entry += "- Asset details:\n"
                entry += "\n".join(md_lines) + "\n"
                entry += f"- Estimated total trade value: {tx_value:.2f}\n"
                entry += f"- Estimated transactional cost (approx): {tx_cost_est:.2f}\n"
                entry += f"- Estimated tax impact (approx): {tax_est:.2f}\n"

                rebalance_explanations.append(entry)
            except Exception:
                logger.info("Rebalance decision: details unavailable due to calculation error")

            try:
                pre_notional = ptf.notional.copy()
                pre_w = ptf.w.copy()
            except Exception:
                pre_notional = None
                pre_w = None

            ptf.update_notional_tax_transaccost(StockPrice, current_date=ptf.date[i])

            try:
                post_notional = ptf.notional.copy()
                delta_notional = ptf.delta_notional.copy()
                prices = StockPrice.copy()
                trade_values = (abs(delta_notional) * prices).to_dict()
                total_trade_value = sum(trade_values.values())
                tot_value_post = post_notional.dot(prices)
                post_w = (post_notional * prices) / tot_value_post if tot_value_post != 0 else None

                rebalance_transactions.append({
                    'date': str(ptf.date[i].date()),
                    'pre_notional': pre_notional.to_dict() if pre_notional is not None else None,
                    'post_notional': post_notional.to_dict(),
                    'delta_notional': delta_notional.to_dict(),
                    'price': prices.to_dict(),
                    'trade_values': trade_values,
                    'total_trade_value': total_trade_value,
                    'transactional_cost': ptf.TransactionalCost,
                    'tax': ptf.tax,
                    'loss_carryforward': dict(ptf.loss_carryforward),
                    'pre_w': pre_w.to_dict() if pre_w is not None else None,
                    'post_w': post_w.to_dict() if post_w is not None else None,
                })
            except Exception:
                pass

            snap_after = log_portfolio_state(ptf, StockPrice=StockPrice, when=f"after rebalance {ptf.date[i].date()}")
            if snap_after:
                rebalance_explanations.append(f"### Portfolio snapshot after {ptf.date[i].date()}\n" + snap_after + "\n")

        ptf.update_exp_cost(ptf.date[i], StockPrice)
        ptf.update_Return(StockPrice)
        ptf.update_TotValue(StockPrice)
        ptf.update_NetTotValue(StockPrice)

        df_log.loc[ptf.date[i], "Return"] = ptf.PercReturn
        df_log.loc[ptf.date[i], "Compound Return"] = ptf.CompoundReturn
        df_log.loc[ptf.date[i], "TotValue"] = ptf.TotValue
        df_log.loc[ptf.date[i], "NetValue"] = ptf.NetValue
        df_log.loc[ptf.date[i], "Cash"] = ptf.cash
        df_log.loc[ptf.date[i], "Taxes"] = ptf.tax
        df_log.loc[ptf.date[i], "TransacCost"] = ptf.TransactionalCost
        df_log.loc[ptf.date[i], "ExpCost"] = ptf.exp_cost
        df_log.loc[ptf.date[i], "LossCarryforward"] = sum(ptf.loss_carryforward.values())
        df_log.loc[ptf.date[i], ptf.IndexName] = ptf.AssetValue
        df_log_delta.loc[ptf.date[i], ptf.IndexName] = ptf.delta_notional * StockPrice

        logger.debug("PercReturn=%s CompoundReturn=%s TotValue=%s", ptf.PercReturn, ptf.CompoundReturn, ptf.TotValue)

    # Final liquidation: sell all positions on the last available date.
    try:
        last_idx = ptf.StockPrice.index[-1]
        last_date = ptf.date[last_idx]
        last_prices = ptf.StockPrice.loc[last_idx, :]

        ptf.reset_tax_transaccost()
        ptf.reset_delta_notional()

        # Sell all notionals at last prices.
        ptf.delta_notional = -ptf.notional.copy()
        ptf.update_tax(last_prices, current_date=last_date)
        ptf.update_transactional_cost(last_prices)
        ptf.cash += (ptf.notional * last_prices).sum()
        ptf.notional += ptf.delta_notional
        ptf.immediate_payments += (ptf.tax + ptf.TransactionalCost)

        # After liquidation, portfolio is in cash (asset notionals = 0).
        ptf.AssetValue = ptf.notional * last_prices
        ptf.w = pd.Series(0.0, index=ptf.IndexName)
        ptf.update_Return(last_prices)
        ptf.update_TotValue(last_prices)
        ptf.update_NetTotValue(last_prices)

        df_log.loc[last_date, "Return"] = ptf.PercReturn
        df_log.loc[last_date, "Compound Return"] = ptf.CompoundReturn
        df_log.loc[last_date, "TotValue"] = ptf.TotValue
        df_log.loc[last_date, "NetValue"] = ptf.NetValue
        df_log.loc[last_date, "Cash"] = ptf.cash
        df_log.loc[last_date, "Taxes"] = ptf.tax
        df_log.loc[last_date, "TransacCost"] = ptf.TransactionalCost
        df_log.loc[last_date, "ExpCost"] = ptf.exp_cost
        df_log.loc[last_date, "LossCarryforward"] = sum(ptf.loss_carryforward.values())
        df_log.loc[last_date, ptf.IndexName] = ptf.AssetValue
        df_log_delta.loc[last_date, ptf.IndexName] = ptf.delta_notional * last_prices
    except Exception:
        pass

    # Reports
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    results = create_reports(ts, df_log, df_log_delta, rebalance_explanations, rebalance_transactions, ptf, cfg)
    logger.info("Reports created: %s", results.get('md'))
    return results
