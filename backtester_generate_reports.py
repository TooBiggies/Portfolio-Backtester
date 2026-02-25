import os
from datetime import datetime
import logging
import pandas as pd
import matplotlib.pyplot as plt


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _write_xlsx(out_dir, ts, df_log, df_log_delta, cfg):
    xlsx_name = f"{ts}_{os.path.basename(cfg.OUTPUT_XLSX)}"
    delta_name = f"{ts}_{os.path.basename(cfg.OUTPUT_DELTA_XLSX)}"
    xlsx_path = os.path.join(out_dir, xlsx_name)
    delta_path = os.path.join(out_dir, delta_name)
    df_log.to_excel(xlsx_path)
    df_log_delta.to_excel(delta_path)
    return xlsx_path, delta_path


def _write_markdown(out_dir, ts, summary, params, xlsx_path, delta_path):
    report_name = f"{ts}_backtest_report.md"
    report_path = os.path.join(out_dir, report_name)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# Backtest report - {ts}\n\n")
        f.write(summary)
        f.write("\n**Parametri:**\n")
        for k, v in params.items():
            f.write(f"- {k}: {v}\n")
        f.write("\n**Output files:**\n")
        f.write(f"- {os.path.abspath(xlsx_path)}\n")
        f.write(f"- {os.path.abspath(delta_path)}\n")
    return report_path


def _write_css(out_dir):
    css_path = os.path.join(out_dir, 'backtest_report.css')
    css_text = '''
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; margin: 24px; color: #111; background: #f7f8fb; }
.container { max-width: 1100px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 8px; box-shadow: 0 6px 18px rgba(15,23,42,0.08); }
h1 { color: #0b4a6f; }
table { border-collapse: collapse; width: 100%; margin-bottom: 16px; }
th, td { text-align: left; padding: 8px; border-bottom: 1px solid #e6eef6; }
th { background: #f1f8ff; color: #0b4a6f; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
.metric { background: #fbfcfe; padding: 12px; border-radius: 6px; border: 1px solid #eef6fb; }
.plot { text-align: center; margin-top: 16px; }
a { color: #0b6fa4; }
'''
    with open(css_path, 'w', encoding='utf-8') as f:
        f.write(css_text)
    return css_path


def _write_html(out_dir, ts, summary_html, params, img_path, xlsx_path, delta_path, css_path):
    html_name = f"{ts}_backtest_report.html"
    html_path = os.path.join(out_dir, html_name)
    rel_img = os.path.basename(img_path) if img_path else ''
    rel_xlsx = os.path.basename(xlsx_path)
    rel_delta = os.path.basename(delta_path)
    css_file = os.path.basename(css_path)

    html = f'''<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Backtest report - {ts}</title>
  <link rel="stylesheet" href="{css_file}">
</head>
<body>
  <div class="container">
    <h1>Backtest report — {ts}</h1>
    {summary_html}
    <h2>Parametri</h2>
    <table>
      <thead><tr><th>Parametro</th><th>Valore</th></tr></thead>
      <tbody>
'''
    for k, v in params.items():
        html += f"      <tr><td>{k}</td><td>{v}</td></tr>\n"
    html += f'''  </tbody>
    </table>
    <h2>Grafico valori</h2>
    <div class="plot">
      <img src="{rel_img}" alt="Time series plot" style="max-width:100%;height:auto;">
    </div>
    <h3>Output files</h3>
    <ul>
      <li><a href="{rel_xlsx}">{rel_xlsx}</a></li>
      <li><a href="{rel_delta}">{rel_delta}</a></li>
    </ul>
  </div>
</body>
</html>
'''
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return html_path


def _plot_values(out_dir, ts, df_log):
    img_name = f"{ts}_values_plot.png"
    img_path = os.path.join(out_dir, img_name)
    try:
        plt.figure(figsize=(10, 5))
        for col, color in [('GrossValue', '#2b6cb0'), ('BrokerValue', '#38a169'), ('NetValue', '#dd6b20')]:
            if col in df_log.columns:
                plt.plot(df_log.index, df_log[col], label=col, color=color)
        plt.legend()
        plt.grid(alpha=0.25)
        plt.xlabel('Date')
        plt.ylabel('Value')
        plt.tight_layout()
        plt.savefig(img_path, dpi=150)
        plt.close()
        return img_path
    except Exception:
        return None


def generate_reports(ptf, df_log, df_log_delta, cfg, ts=None, out_dir=None):
    """Generate XLSX, markdown and HTML reports (with CSS and plot)."""
    if ts is None:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if out_dir is None:
        out_dir = cfg.REPORTS_DIR
    _ensure_dir(out_dir)

    # Save data files
    xlsx_path, delta_path = _write_xlsx(out_dir, ts, df_log, df_log_delta, cfg)

    # Summary text and params
    start_dt = min(ptf.date).date()
    end_dt = max(ptf.date).date()
    years = round(((max(ptf.date) - min(ptf.date)).days / 365.25), 2)
    try:
        cagr = (ptf.CompoundReturn ** (1 / years) - 1) * 100 if years > 0 else float('nan')
    except Exception:
        cagr = float('nan')

    summary = ''
    summary += f"**Orizzonte temporale:** {start_dt} / {end_dt}  \n"
    summary += f"**Anni in simulazione:** {years}  \n"
    summary += f"**CAGR:** {cagr:.2f}%  \n"
    summary += f"**Total compound return:** {ptf.CompoundReturn * 100:.2f}%  \n"
    summary += f"**Capitale iniziale:** {ptf.StartValue}  \n"
    summary += f"**Capitale finale:** {ptf.TotValue:.2f}  \n\n"

    params = {
        'initial_w': getattr(ptf, 'initial_w', None),
        'transac_cost_rate': getattr(ptf, 'transactional_cost_rate', None),
        'tax_rate': getattr(ptf, 'tax_rate', None),
        'rebalance_threshold': getattr(ptf, 'rebalance_threshold', None),
    }

    # Write markdown
    report_path = _write_markdown(out_dir, ts, summary, params, xlsx_path, delta_path)

    # Write CSS
    css_path = _write_css(out_dir)

    # Generate plot image
    img_path = _plot_values(out_dir, ts, df_log)

    # Compose HTML summary block (slightly richer than markdown)
    summary_html = f"<div class=\"summary\">"
    summary_html += f"<div class=\"metric\"><strong>Orizzonte</strong><br>{start_dt} / {end_dt}</div>"
    summary_html += f"<div class=\"metric\"><strong>Anni</strong><br>{years}</div>"
    summary_html += f"<div class=\"metric\"><strong>CAGR</strong><br>{cagr:.2f}%</div>"
    summary_html += f"<div class=\"metric\"><strong>Capitale finale</strong><br>{ptf.TotValue:.2f}</div>"
    summary_html += "</div>"

    # Write HTML
    html_path = _write_html(out_dir, ts, summary_html, params, img_path, xlsx_path, delta_path, css_path)

    logger = logging.getLogger('backtester')
    logger.info(f"Saved markdown report: {report_path}")
    logger.info(f"Saved html report: {html_path}")
    return {
        'xlsx': xlsx_path,
        'delta': delta_path,
        'markdown': report_path,
        'html': html_path,
        'css': css_path,
        'img': img_path,
    }
