import json
import os
import datetime
from typing import Optional
import pandas as pd
import html
import re

def _round_numbers(obj, ndigits=2):
    """Recursively round floats in lists/dicts/tuples to `ndigits` decimals."""
    try:
        if isinstance(obj, float):
            return round(obj, ndigits)
        if isinstance(obj, dict):
            return {k: _round_numbers(v, ndigits) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_round_numbers(v, ndigits) for v in obj]
        if isinstance(obj, tuple):
            return tuple(_round_numbers(v, ndigits) for v in obj)
        # ints and others left unchanged
        return obj
    except Exception:
        return obj

plotly_cdn = 'https://cdn.plot.ly/plotly-latest.min.js'


def write_html_report(html_path: str, ts: str, df_log: pd.DataFrame,
                      rebalance_explanations: list, rebalance_transactions: list,
                      ptf, cfg, asset_trade_totals: dict,
                      trans_csv_path: Optional[str] = None,
                      xlsx_path: Optional[str] = None,
                      delta_path: Optional[str] = None) -> Optional[str]:
    """Write the HTML backtest report to `html_path` using provided data.

    Returns the html_path on success, or None on failure.
    """
    try:
        # Prepare series data
        try:
            dates = [str(d) for d in df_log.index]
        except Exception:
            dates = []
        try:
            compound = (df_log['Compound Return'] * 100).tolist() if 'Compound Return' in df_log.columns else []
        except Exception:
            compound = []
        try:
            totvalue = df_log['TotValue'].tolist() if 'TotValue' in df_log.columns else []
        except Exception:
            totvalue = []

        # Prepare per-rebalance pies (pre & post weights)
        pies = []
        for i, tx in enumerate(rebalance_transactions):
            pre_w = tx.get('pre_w') or {}
            post_w = tx.get('post_w') or {}

            def filt(d):
                return {k: v for k, v in (d.items() if isinstance(d, dict) else []) if (v or 0.0) > 1e-5}

            pies.append({'date': tx.get('date'), 'pre': filt(pre_w), 'post': filt(post_w)})

        # Final pie from portfolio object (ptf.w)
        try:
            final_w = {k: float(v) for k, v in ptf.w.items()}
        except Exception:
            final_w = {}

        # Build HTML
        with open(html_path, 'w', encoding='utf-8') as hf:
            hf.write('<!doctype html><html><head><meta charset="utf-8"><title>Backtest report</title>')
            hf.write(f'<script src="{plotly_cdn}"></script>')
            hf.write('<style>body{font-family:Inter,Arial,Helvetica,sans-serif;margin:18px;color:#111;background:#fff}.container{max-width:1100px;margin:0 auto}h1,h2,h3{color:#123}table{border-collapse:collapse;width:100%;margin-top:8px}th,td{border:1px solid #e1e4e8;padding:8px;text-align:left;font-size:13px}th{background:#f6f8fa;text-align:left}tr:nth-child(even){background:#fbfbfb}code{background:#f6f8fa;padding:2px 4px;border-radius:3px;font-family:monospace}</style>')
            hf.write('</head><body><div class="container">')
            hf.write(f'<h1>Backtest report - {ts}</h1>')

            # Summary block
            # Safely render portfolio date: prefer the first element if date is index/sequence
            ptf_date = getattr(ptf, 'date', None)
            date_str = ''
            if ptf_date is None:
                date_str = ''
            else:
                try:
                    # Try to get first element (works for lists, tuples, pandas Index)
                    first = ptf_date[0]
                    date_str = str(first)
                except Exception:
                    date_str = str(ptf_date)
            hf.write(f'<p><strong>Orizzonte temporale:</strong> {date_str}<br>')

            # Detailed English summary: key metrics and allocation tables
            hf.write('<h2>Detailed Summary (English)</h2>')
            hf.write('<h3>Key Metrics</h3>')
            hf.write('<table>')
            hf.write('<tr><th>Metric</th><th>Value</th></tr>')
            try:
                start_dt = min(ptf.date).date()
                end_dt = max(ptf.date).date()
                years = round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)
                cagr = (ptf.CompoundReturn ** (1 / years) - 1) * 100 if years > 0 else float('nan')
            except Exception:
                start_dt = end_dt = ''
                years = ''
                cagr = ''
            hf.write(f'<tr><td>Start date</td><td>{start_dt}</td></tr>')
            hf.write(f'<tr><td>End date</td><td>{end_dt}</td></tr>')
            hf.write(f'<tr><td>Years</td><td>{years}</td></tr>')
            hf.write(f'<tr><td>CAGR</td><td>{cagr:.2f}%</td></tr>' if isinstance(cagr, float) else f'<tr><td>CAGR</td><td>{cagr}</td></tr>')
            try:
                hf.write(f'<tr><td>Start capital</td><td>{ptf.StartValue}</td></tr>')
                hf.write(f'<tr><td>Final capital</td><td>{ptf.TotValue:.2f}</td></tr>')
            except Exception:
                pass
            hf.write(f'<tr><td>Number of rebalances</td><td>{len(rebalance_transactions)}</td></tr>')
            hf.write(f'<tr><td>Total traded volume (approx)</td><td>${sum(tx.get("total_trade_value",0.0) for tx in rebalance_transactions):.2f}</td></tr>')
            try:
                hf.write(f'<tr><td>Transactional cost rate</td><td>{ptf.transactional_cost_rate*100:.3f}%</td></tr>')
            except Exception:
                pass
            try:
                hf.write(f'<tr><td>Tax rate (on gains)</td><td>{ptf.tax_rate*100:.2f}%</td></tr>')
            except Exception:
                pass
            hf.write(f'<tr><td>Price normalization</td><td>{cfg.STOCK_PRICE_NORMALIZATION}</td></tr>')

            # Compute metrics from df_log inside writer as well
            max_dd = None
            vol_ann = None
            sharpe = None
            sortino = None
            try:
                if 'TotValue' in df_log.columns:
                    tv = pd.Series(df_log['TotValue']).astype(float)
                    running_max = tv.cummax()
                    dd = (tv - running_max) / running_max
                    max_dd = float(dd.min()) if not dd.empty else None
                    rets = tv.pct_change().dropna()
                else:
                    if 'Return' in df_log.columns:
                        rets = pd.Series(df_log['Return']).astype(float).dropna()
                    elif 'returns' in df_log.columns:
                        rets = pd.Series(df_log['returns']).astype(float).dropna()
                    else:
                        rets = pd.Series(dtype=float)

                if rets is not None and len(rets) > 0:
                    try:
                        idx = pd.to_datetime(df_log.index)
                        if len(idx) >= 2:
                            median_delta_days = int((idx[1:] - idx[:-1]).median().days)
                            periods_per_year = int(365.25 / median_delta_days) if median_delta_days > 0 else 252
                        else:
                            periods_per_year = 252
                    except Exception:
                        periods_per_year = 252

                    mean_ret = float(rets.mean())
                    vol = float(rets.std())
                    vol_ann = vol * (periods_per_year ** 0.5)
                    try:
                        ann_ret = (1.0 + rets).prod() ** (periods_per_year / len(rets)) - 1.0
                    except Exception:
                        ann_ret = mean_ret * periods_per_year

                    sharpe = float(ann_ret / vol_ann) if vol_ann and vol_ann > 0 else None

                    neg = rets[rets < 0]
                    if len(neg) > 0:
                        downside_std = (neg.pow(2).mean()) ** 0.5
                        downside_ann = downside_std * (periods_per_year ** 0.5)
                        sortino = float(ann_ret / downside_ann) if downside_ann and downside_ann > 0 else None
                    else:
                        sortino = None
            except Exception:
                max_dd = vol_ann = sharpe = sortino = None

            hf.write(f'<tr><td>Max drawdown</td><td>{abs(max_dd)*100:.2f}%</td></tr>' if max_dd is not None else '<tr><td>Max drawdown</td><td>-</td></tr>')
            hf.write(f'<tr><td>Volatility (ann.)</td><td>{vol_ann*100:.2f}%</td></tr>' if vol_ann is not None else '<tr><td>Volatility (ann.)</td><td>-</td></tr>')
            hf.write(f'<tr><td>Sharpe ratio</td><td>{sharpe:.2f}</td></tr>' if sharpe is not None else '<tr><td>Sharpe ratio</td><td>-</td></tr>')
            hf.write(f'<tr><td>Sortino ratio</td><td>{sortino:.2f}</td></tr>' if sortino is not None else '<tr><td>Sortino ratio</td><td>-</td></tr>')

            hf.write('</table>')

            hf.write('<h3>Initial vs Final Allocation</h3>')
            hf.write('<div id="alloc_bar" style="width:100%;height:360px;"></div>')
            hf.write('<h3>Traded Volume per Asset (approx)</h3>')
            hf.write('<div id="trade_bar" style="width:100%;height:360px;"></div>')

            # Inline HTML table for initial vs final allocations (readable fallback)
            try:
                hf.write('<table>')
                hf.write('<tr><th>Asset</th><th>Initial %</th><th>Final %</th><th>Change</th></tr>')
                all_assets = sorted(set(list(getattr(ptf, 'initial_w', {}).keys()) + list(final_w.keys())))
                for asset in all_assets:
                    init = getattr(ptf, 'initial_w', {}).get(asset, 0.0) * 100
                    fin = final_w.get(asset, 0.0) * 100
                    ch = fin - init
                    hf.write(f'<tr><td>{asset}</td><td>{init:.2f}%</td><td>{fin:.2f}%</td><td>{ch:+.2f}%</td></tr>')
                hf.write('</table>')
            except Exception:
                pass

            # Compound Return and TotValue plots
            hf.write('<h2>Compound Return (interattivo)</h2>')
            hf.write('<div id="compound_plot" style="width:100%;height:420px;"></div>')
            hf.write('<h2>TotValue (interattivo)</h2>')
            hf.write('<div id="totvalue_plot" style="width:100%;height:420px;"></div>')
            hf.write('<h2>Final Allocation (interattivo)</h2>')
            hf.write('<div id="final_pie" style="width:700px;height:420px;"></div>')

            # Rebalances
            hf.write('<h2>Rebalances</h2>')
            if len(rebalance_transactions) == 0:
                hf.write('<p>No rebalances were executed.</p>')
            else:
                for i, tx in enumerate(rebalance_transactions):
                    date = tx.get('date')
                    total_trade = tx.get('total_trade_value', 0.0) or 0.0
                    tcost = tx.get('transactional_cost', 0.0) or 0.0
                    tax = tx.get('tax', 0.0) or 0.0
                    pre_w = tx.get('pre_w') or {}
                    post_w = tx.get('post_w') or {}
                    price_map = tx.get('price') or {}
                    delta_map = tx.get('delta_notional') or {}

                    lead = ''
                    if i < len(rebalance_explanations) and rebalance_explanations[i]:
                        raw = rebalance_explanations[i]
                        lines = [ln.strip() for ln in str(raw).splitlines() if ln.strip()]
                        clean_lines = []
                        for ln in lines:
                            ln2 = ln.lstrip('#').lstrip('-').strip()
                            clean_lines.append(ln2)
                        lead = ' '.join(clean_lines)
                    else:
                        try:
                            thresh = getattr(ptf, 'rebalance_threshold', None)
                            try:
                                keys = set(list(pre_w.keys()) + list(post_w.keys()))
                                max_dev = 0.0
                                max_asset = None
                                for k in keys:
                                    pw = pre_w.get(k, 0.0) or 0.0
                                    qw = post_w.get(k, 0.0) or 0.0
                                    dev = abs(pw - qw)
                                    if dev > max_dev:
                                        max_dev = dev
                                        max_asset = (k, pw, qw)

                                if max_asset:
                                    k, pw, qw = max_asset
                                    if thresh is not None and max_dev >= thresh:
                                        lead = (
                                            f"For the asset {k} the initial value was {pw*100:.2f}% "
                                            f"and the current one is {qw*100:.2f}%. This exceeds the rebalance "
                                            f"threshold of {thresh*100:.2f}%, so a rebalance is being executed to "
                                            f"restore target weights."
                                        )
                                    else:
                                        lead = (
                                            f"For the asset {k} the value moved from {pw*100:.2f}% to {qw*100:.2f}% "
                                            f"(deviation {max_dev*100:.2f}%), which did not exceed the configured "
                                            f"rebalance threshold. A rebalance may still be applied to fine-tune allocations."
                                        )
                                else:
                                    if thresh is not None:
                                        lead = f"This rebalance was executed to restore the portfolio to its target weights because one or more assets deviated beyond the configured rebalance threshold ({thresh*100:.2f}%)."
                                    else:
                                        lead = "This rebalance was executed to restore the portfolio to its target weights because asset weights had deviated from targets."
                            except Exception:
                                if thresh is not None:
                                    lead = f"This rebalance was executed to restore the portfolio to its target weights because one or more assets deviated beyond the configured rebalance threshold ({thresh*100:.2f}%)."
                                else:
                                    lead = "This rebalance was executed to restore the portfolio to its target weights because asset weights had deviated from targets."
                        except Exception:
                            lead = "This rebalance was executed to restore the portfolio to its target weights."

                    sells = []
                    buys = []
                    for a, delta in (delta_map.items() if isinstance(delta_map, dict) else []):
                        if delta is None:
                            continue
                        if delta < 0:
                            sells.append((a, delta, price_map.get(a, None)))
                        elif delta > 0:
                            buys.append((a, delta, price_map.get(a, None)))

                    hf.write(f'<h3>Rebalance {i+1} — {date}</h3>')

                    # Build a plain-English summary paragraph to appear at the start
                    # of each rebalance section. Include totals and per-asset tax if present.
                    total_trade = total_trade or 0.0
                    tcost = tcost or 0.0
                    tax_total = tax or 0.0

                    # Look for possible per-asset tax maps under common keys
                    tax_map = tx.get('tax_by_asset') or tx.get('taxes_by_asset') or tx.get('taxes') or tx.get('tax_map') or {}

                    summary_sentences = []
                    # Lead sentence (why/what)
                    if lead:
                        summary_sentences.append(lead)

                    # Totals sentence
                    summary_sentences.append(
                        f"In total, this rebalance executed approximately ${total_trade:.2f} of trades, "
                        f"incurring ${tcost:.2f} in transaction costs and ${tax_total:.2f} in taxes."
                    )

                    # Per-asset notes for sells/buys with trade values and taxes when available
                    asset_notes = []
                    for a, delta, price in sells:
                        tradev = (tx.get('trade_values') or {}).get(a, None)
                        tradev_str = f", for a trade value of ${tradev:.2f}" if isinstance(tradev, (int, float)) else ""
                        tax_a = None
                        if isinstance(tax_map, dict):
                            tax_a = tax_map.get(a)
                        tax_str = f" and paid ${tax_a:.2f} in taxes" if isinstance(tax_a, (int, float)) and tax_a != 0 else ""
                        asset_notes.append(f"Sold {abs(delta):.2f} notional of {a}{tradev_str}{tax_str}")
                    for a, delta, price in buys:
                        tradev = (tx.get('trade_values') or {}).get(a, None)
                        tradev_str = f", for a trade value of ${tradev:.2f}" if isinstance(tradev, (int, float)) else ""
                        asset_notes.append(f"Bought {delta:.2f} notional of {a}{tradev_str}")

                    if asset_notes:
                        summary_sentences.append(' ; '.join(asset_notes) + '.')

                    plain_summary = ' '.join(summary_sentences)
                    print(f"DEBUG: writing plain_summary for rebalance {i}: {plain_summary}")

                    def _round_numbers_in_text(text: str, ndigits: int = 2) -> str:
                        # Replace floating numbers (optionally followed by %) with rounded versions
                        def _repl(m):
                            num = m.group(1)
                            pct = m.group(2) or ''
                            try:
                                f = float(num)
                                if pct == '%':
                                    return f"{round(f, ndigits):.{ndigits}f}%"
                                return f"{round(f, ndigits):.{ndigits}f}"
                            except Exception:
                                return m.group(0)

                        return re.sub(r'(-?\d+\.\d+)(%)?', _repl, str(text))

                    def _render_summary_to_html(text: str) -> str:
                        # escape HTML and preserve line breaks and bullet lines starting with "- "
                        pieces = []
                        in_list = False
                        for raw_ln in str(text).splitlines():
                            ln = raw_ln.rstrip()
                            if ln.lstrip().startswith('- '):
                                # list item
                                if not in_list:
                                    pieces.append('<ul>')
                                    in_list = True
                                item = ln.lstrip()[2:]
                                pieces.append(f'<li>{html.escape(item)}</li>')
                            else:
                                if in_list:
                                    pieces.append('</ul>')
                                    in_list = False
                                if ln.strip() == '':
                                    pieces.append('<br/>')
                                else:
                                    pieces.append(f'<p>{html.escape(ln)}</p>')
                        if in_list:
                            pieces.append('</ul>')
                        return ''.join(pieces)

                    rounded_plain = _round_numbers_in_text(plain_summary, 2)
                    rendered = _render_summary_to_html(rounded_plain)
                    hf.write('<!--DEBUG:SUMMARY_START-->')
                    hf.write(f'<div class="summary"><em>{rendered}</em></div>')
                    hf.write('<!--DEBUG:SUMMARY_END-->')

                    parts = [lead]
                    if sells:
                        sold_parts = []
                        for a, delta, price in sells:
                            price_str = f" at ${price:.2f}" if isinstance(price, (int, float)) else ''
                            sold_parts.append(f"{abs(delta):.2f} of notional in {a}{price_str}")
                        parts.append('The rebalancing process sold ' + ', '.join(sold_parts) + '.')
                    if buys:
                        buy_parts = []
                        for a, delta, price in buys:
                            price_str = f" at ${price:.2f}" if isinstance(price, (int, float)) else ''
                            buy_parts.append(f"{delta:.2f} of notional in {a}{price_str}")
                        parts.append('At the same time it bought ' + ', '.join(buy_parts) + '.')

                    parts.append(f"The total value of trades executed was ${total_trade:.2f}; transactional costs applied amounted to ${tcost:.2f} and taxes to ${tax:.2f}.")

                    try:
                        changes = []
                        keys = set(list(pre_w.keys()) + list(post_w.keys()))
                        for k in sorted(keys):
                            pw = pre_w.get(k, 0.0) or 0.0
                            qw = post_w.get(k, 0.0) or 0.0
                            if abs(pw - qw) >= 1e-4:
                                changes.append(f"{k}: {pw*100:.2f}% → {qw*100:.2f}%")
                        if changes:
                            parts.append('Portfolio weights changed as follows: ' + '; '.join(changes) + '.')
                    except Exception:
                        pass

                    # Round numbers inside the 'lead' text and escape for HTML
                    try:
                        rounded_lead = _round_numbers_in_text(lead, 2) if lead else lead
                    except Exception:
                        rounded_lead = lead
                    hf.write('<ul>')
                    hf.write(f'<li><strong>Reason:</strong> {html.escape(str(rounded_lead))}</li>')

                    if sells:
                        hf.write('<li><strong>Sells:</strong><ul>')
                        tv_map = tx.get('trade_values', {}) or {}
                        for a, delta, price in sells:
                            tradev = tv_map.get(a, 0.0) or 0.0
                            price_str = f" at ${price:.2f}" if isinstance(price, (int, float)) else ''
                            hf.write(f'<li>{a}: sold {abs(delta):.2f} notional{price_str}; trade value ${tradev:.2f}</li>')
                        hf.write('</ul></li>')

                    if buys:
                        hf.write('<li><strong>Buys:</strong><ul>')
                        tv_map = tx.get('trade_values', {}) or {}
                        for a, delta, price in buys:
                            tradev = tv_map.get(a, 0.0) or 0.0
                            price_str = f" at ${price:.2f}" if isinstance(price, (int, float)) else ''
                            hf.write(f'<li>{a}: bought {delta:.2f} notional{price_str}; trade value ${tradev:.2f}</li>')
                        hf.write('</ul></li>')

                    hf.write(f'<li><strong>Totals:</strong> total trades ${total_trade:.2f}; transactional costs ${tcost:.2f}; taxes ${tax:.2f}</li>')

                    try:
                        keys = set(list(pre_w.keys()) + list(post_w.keys()))
                        if keys:
                            hf.write('<li><strong>Weight changes:</strong><ul>')
                            for k in sorted(keys):
                                pw = pre_w.get(k, 0.0) or 0.0
                                qw = post_w.get(k, 0.0) or 0.0
                                if abs(pw - qw) >= 1e-4:
                                    hf.write(f'<li>{k}: {pw*100:.2f}% → {qw*100:.2f}%</li>')
                            hf.write('</ul></li>')
                    except Exception:
                        pass

                    hf.write('</ul>')

                    safe_date = str(pies[i].get('date')) if i < len(pies) else str(date)
                    hf.write(f'<div id="pie_pre_{i}" style="width:420px;height:360px;display:inline-block"></div>')
                    hf.write(f'<div id="pie_post_{i}" style="width:420px;height:360px;display:inline-block"></div>')

            hf.write('<h2>Files</h2>')
            hf.write(f'<p>Transactions CSV: <a href="{os.path.basename(trans_csv_path) if trans_csv_path else ""}">{os.path.basename(trans_csv_path) if trans_csv_path else "(none)"}</a></p>')

            # Inject data as JSON and create Plotly plots
            hf.write('<script>')
            hf.write(f'var dates = {json.dumps(dates)};')
            # Ensure numeric arrays/dicts don't have more than 2 decimal places
            try:
                compound = _round_numbers(compound, 2)
            except Exception:
                pass
            try:
                totvalue = _round_numbers(totvalue, 2)
            except Exception:
                pass
            try:
                final_w = _round_numbers(final_w, 2)
            except Exception:
                pass
            try:
                pies = _round_numbers(pies, 2)
            except Exception:
                pass

            hf.write(f'var compound = {json.dumps(compound)};')
            hf.write(f'var totvalue = {json.dumps(totvalue)};')
            hf.write(f'var final_w = {json.dumps(final_w)};')
            hf.write(f'var pies = {json.dumps(pies)};')

            # initial vs final arrays for interactive plots
            initial_w = {}
            src_init = getattr(ptf, 'initial_w', None)
            if src_init is not None:
                try:
                    for k, v in dict(src_init).items():
                        try:
                            initial_w[str(k)] = float(v)
                        except Exception:
                            initial_w[str(k)] = 0.0
                except Exception:
                    try:
                        for k, v in src_init.items():
                            try:
                                initial_w[str(k)] = float(v)
                            except Exception:
                                initial_w[str(k)] = 0.0
                    except Exception:
                        initial_w = {}
            try:
                initial_w = _round_numbers(initial_w, 2)
            except Exception:
                pass
            try:
                asset_trade_totals = _round_numbers(asset_trade_totals, 2)
            except Exception:
                pass
            hf.write(f'var initial_w = {json.dumps(initial_w)};')
            hf.write(f'var asset_trade_totals = {json.dumps(asset_trade_totals)};')

            hf.write("var comp_trace = { x: dates, y: compound, type: 'scatter', mode: 'lines+markers', name: 'Compound %' };\n")
            hf.write("Plotly.newPlot('compound_plot', [comp_trace], {title:'Compound Return (%)', xaxis:{title:'Date'}, yaxis:{title:'Compound %'}});\n")

            hf.write("var tv_trace = { x: dates, y: totvalue, type: 'scatter', mode: 'lines', name: 'TotValue' };\n")
            hf.write("Plotly.newPlot('totvalue_plot', [tv_trace], {title:'TotValue', xaxis:{title:'Date'}, yaxis:{title:'TotValue'}});\n")

            hf.write("var final_labels = Object.keys(final_w); var final_values = final_labels.map(l=>final_w[l]*100);\n")
            hf.write("Plotly.newPlot('final_pie', [{values: final_values, labels: final_labels, type:'pie'}], {title:'Final allocation (%)'});\n")

            hf.write("var alloc_labels = Object.keys(initial_w).concat(Object.keys(final_w).filter(l=>Object.keys(initial_w).indexOf(l)===-1));\n")
            hf.write("var alloc_init = alloc_labels.map(l=>initial_w[l]?initial_w[l]*100:0);\n")
            hf.write("var alloc_final = alloc_labels.map(l=>final_w[l]?final_w[l]*100:0);\n")
            hf.write("var trace_init = {x:alloc_labels, y:alloc_init, name:'Initial %', type:'bar'};\n")
            hf.write("var trace_final = {x:alloc_labels, y:alloc_final, name:'Final %', type:'bar'};\n")
            hf.write("Plotly.newPlot('alloc_bar', [trace_init, trace_final], {barmode:'group', title:'Initial vs Final Allocation (%)'});\n")

            hf.write("var trade_labels = Object.keys(asset_trade_totals); var trade_vals = trade_labels.map(l=>asset_trade_totals[l]);\n")
            hf.write("var trace_trade = {x:trade_labels, y:trade_vals, type:'bar', name:'Trade Volume ($)'};\n")
            hf.write("Plotly.newPlot('trade_bar', [trace_trade], {title:'Approx. Traded Volume per Asset ($)'});\n")

            hf.write("for(var i=0;i<pies.length;i++){\n")
            hf.write("  var pre = pies[i].pre || {}; var post = pies[i].post || {};\n")
            hf.write("  var pre_labels = Object.keys(pre); var pre_vals = pre_labels.map(k=>pre[k]*100);\n")
            hf.write("  var post_labels = Object.keys(post); var post_vals = post_labels.map(k=>post[k]*100);\n")
            hf.write("  if(pre_labels.length>0) Plotly.newPlot('pie_pre_'+i, [{values:pre_vals, labels:pre_labels, type:'pie'}], {title:'Pre-rebalance (%)'});\n")
            hf.write("  else document.getElementById('pie_pre_'+i).innerHTML='<em>No pre-rebalance weights</em>';\n")
            hf.write("  if(post_labels.length>0) Plotly.newPlot('pie_post_'+i, [{values:post_vals, labels:post_labels, type:'pie'}], {title:'Post-rebalance (%)'});\n")
            hf.write("  else document.getElementById('pie_post_'+i).innerHTML='<em>No post-rebalance weights</em>';\n")
            hf.write('}\n')
            hf.write('</script>')

            hf.write('</div></body></html>')
        return html_path
    except Exception:
        return None
