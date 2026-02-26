import os
from datetime import datetime


def write_markdown_report(report_path: str, ts: str, df_log, df_log_delta,
                          rebalance_explanations: list, rebalance_transactions: list,
                          ptf, cfg, asset_trade_totals: dict,
                          xlsx_path: str = None, delta_path: str = None):
    """Write the markdown report to `report_path` using provided data."""
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# Backtest report - {ts}\n\n")
            try:
                start_dt = min(ptf.date).date()
                end_dt = max(ptf.date).date()
                years = round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)
                cagr = (ptf.CompoundReturn ** (1 / years) - 1) * 100 if years > 0 else float('nan')
            except Exception:
                start_dt = end_dt = ''
                years = ''
                cagr = ''

            f.write(f"**Orizzonte temporale:** {start_dt} / {end_dt}  \n")
            f.write(f"**Anni in simulazione:** {years}  \n")
            f.write(f"**CAGR:** {cagr:.2f}%  \n" if isinstance(cagr, float) else f"**CAGR:** {cagr}  \n")
            try:
                f.write(f"**Total compound return:** {ptf.CompoundReturn * 100:.2f}%  \n")
                f.write(f"**Capitale iniziale:** {ptf.StartValue}  \n")
                f.write(f"**Capitale finale:** {ptf.TotValue:.2f}  \n\n")
            except Exception:
                pass

            f.write("**Parametri:**\n")
            try:
                f.write(f"- Capitale iniziale: {ptf.StartValue}\n")
                f.write(f"- Pesi iniziali (asset: peso):\n")
                for asset, w in ptf.initial_w.items():
                    f.write(f"  - {asset}: {w*100:.2f}%\n")
                f.write(f"- Costo transazionale (commissioni+spread): {ptf.transactional_cost_rate*100:.3f}%\n")
                f.write(f"- Expense rate (annuo): {ptf.exp_rate*100:.3f}%\n")
                f.write(f"- Aliquota fiscale sulle plusvalenze: {ptf.tax_rate*100:.2f}%\n")
                f.write(f"- Soglia ribilanciamento (per-asset): {ptf.rebalance_threshold*100:.2f}%\n")
                f.write(f"- Normalizzazione prezzi iniziali: {cfg.STOCK_PRICE_NORMALIZATION}\n\n")
            except Exception:
                pass

            f.write("**Output files:**\n")
            f.write(f"- {os.path.abspath(xlsx_path) if xlsx_path else '(none)'}\n")
            f.write(f"- {os.path.abspath(delta_path) if delta_path else '(none)'}\n\n")
            f.write("**Rebalance summary:**\n")
            num_rebalances = len(rebalance_transactions)
            total_trade_volume = sum(tx.get('total_trade_value', 0.0) for tx in rebalance_transactions) if num_rebalances > 0 else 0.0
            f.write(f"- Number of rebalances: {num_rebalances}\n")
            f.write(f"- Total traded volume (approx): {total_trade_volume:.2f}\n")
            if len(asset_trade_totals) > 0:
                f.write(f"- Traded volume per asset (approx):\n")
                for a, v in asset_trade_totals.items():
                    f.write(f"  - {a}: {v:.2f}\n")

            f.write("\n**Rebalance details:**\n\n")
            if len(rebalance_explanations) == 0:
                f.write("None\n")
            else:
                for entry in rebalance_explanations:
                    f.write(entry + "\n")

            f.write("\n**Rebalance transactions (summary):**\n\n")
            if len(rebalance_transactions) == 0:
                f.write("None\n")
            else:
                for tx in rebalance_transactions:
                    f.write(f"### Rebalance on {tx['date']}\n")
                    f.write(f"- Total trade value: {tx['total_trade_value']:.2f}\n")
                    f.write(f"- Transactional cost: {tx['transactional_cost']:.2f}\n")
                    f.write(f"- Tax: {tx['tax']:.2f}\n")
                    f.write("\nAsset | Price | Delta notional | Trade value | Pre notional | Post notional | Pre w | Post w\n")
                    f.write("--- | ---: | ---: | ---: | ---: | ---: | ---: | ---\n")
                    assets = tx['price'].keys()
                    for a in assets:
                        price = tx['price'].get(a, '')
                        delta = tx['delta_notional'].get(a, 0.0)
                        tradev = tx['trade_values'].get(a, 0.0)
                        pre_n = tx['pre_notional'].get(a, '') if tx['pre_notional'] else ''
                        post_n = tx['post_notional'].get(a, '')
                        pre_w = tx['pre_w'].get(a, '') if tx['pre_w'] else ''
                        post_w = tx['post_w'].get(a, '') if tx['post_w'] else ''
                        try:
                            f.write(f"{a} | {price:.6f} | {delta:.6f} | {tradev:.2f} | {pre_n} | {post_n} | {pre_w} | {post_w}\n")
                        except Exception:
                            f.write(f"{a} | {price} | {delta} | {tradev} | {pre_n} | {post_n} | {pre_w} | {post_w}\n")
    except Exception:
        return None
    return report_path
