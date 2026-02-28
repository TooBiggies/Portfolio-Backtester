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
                for i, tx in enumerate(rebalance_transactions):
                    # Build plain-English summary for markdown (include totals and per-asset taxes if available)
                    date = tx.get('date', '(unknown)')
                    total_trade = tx.get('total_trade_value', 0.0) or 0.0
                    tcost = tx.get('transactional_cost', 0.0) or 0.0
                    tax_total = tx.get('tax', 0.0) or 0.0

                    pre_w = tx.get('pre_w') or {}
                    post_w = tx.get('post_w') or {}
                    thresh = getattr(ptf, 'rebalance_threshold', None)

                    # find primary asset with max deviation
                    max_dev = 0.0
                    max_asset = None
                    keys = set(list(pre_w.keys()) + list(post_w.keys()))
                    for k in keys:
                        pw = pre_w.get(k, 0.0) or 0.0
                        qw = post_w.get(k, 0.0) or 0.0
                        dev = abs(pw - qw)
                        if dev > max_dev:
                            max_dev = dev
                            max_asset = (k, pw, qw)

                    if max_asset and thresh is not None and max_dev >= thresh:
                        k, pw, qw = max_asset
                        lead = (f"For the asset {k} the initial value was {pw*100:.2f}% and "
                                f"the current one is {qw*100:.2f}%. This exceeds the rebalance "
                                f"threshold of {thresh*100:.2f}%, so a rebalance is being executed to "
                                f"restore target weights.")
                    elif max_asset:
                        k, pw, qw = max_asset
                        lead = (f"For the asset {k} the value moved from {pw*100:.2f}% to {qw*100:.2f}% "
                                f"(deviation {max_dev*100:.2f}%), which did not exceed the configured "
                                f"rebalance threshold.")
                    else:
                        # fallback to any provided explanation
                        lead = ''

                    # per-asset taxes if present under common keys
                    tax_map = tx.get('tax_by_asset') or tx.get('taxes_by_asset') or tx.get('taxes') or tx.get('tax_map') or {}

                    # build asset-level notes for buys/sells
                    sells = []
                    buys = []
                    delta_map = tx.get('delta_notional') or {}
                    price_map = tx.get('price') or {}
                    trade_values = tx.get('trade_values') or {}
                    for a, delta in (delta_map.items() if isinstance(delta_map, dict) else []):
                        if delta is None:
                            continue
                        if delta < 0:
                            sells.append((a, delta, price_map.get(a, None), trade_values.get(a, None)))
                        elif delta > 0:
                            buys.append((a, delta, price_map.get(a, None), trade_values.get(a, None)))

                    # Compose summary paragraph
                    summary_lines = []
                    if lead:
                        summary_lines.append(lead)
                    summary_lines.append(f"In total, this rebalance executed approximately ${total_trade:.2f} of trades, incurring ${tcost:.2f} in transaction costs and ${tax_total:.2f} in taxes.")
                    for a, delta, price, tv in sells:
                        tax_a = None
                        if isinstance(tax_map, dict):
                            tax_a = tax_map.get(a)
                        tax_str = f" and paid ${tax_a:.2f} in taxes" if isinstance(tax_a, (int, float)) and tax_a != 0 else ""
                        tv_str = f" for a trade value of ${tv:.2f}" if isinstance(tv, (int, float)) else ""
                        summary_lines.append(f"Sold {abs(delta):.2f} notional of {a}{tv_str}{tax_str}.")
                    for a, delta, price, tv in buys:
                        tv_str = f" for a trade value of ${tv:.2f}" if isinstance(tv, (int, float)) else ""
                        summary_lines.append(f"Bought {delta:.2f} notional of {a}{tv_str}.")

                    # Write header and summary paragraph
                    f.write(f"### Rebalance on {date}\n")
                    f.write(f"_ {' '.join(summary_lines)} _\n\n")
                    f.write(f"- Total trade value: {total_trade:.2f}\n")
                    f.write(f"- Transactional cost: {tcost:.2f}\n")
                    f.write(f"- Tax: {tax_total:.2f}\n")
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
