# Portfolio Backtester

Quick notes to run the backtester in this repo.

Files:
- `backtester.py` — script that runs the backtest using `backtester_config.py` settings.
- `backtester_config.py` — configuration for initial weights, capital and dates.
- `classes.py` — contains `portfolio_evo` class (backtest engine).
- `Timeseries.csv` — historical price data (semicolon-separated).

Run in a virtual environment (this repo created `.venv`):

```bash
python3 -m venv .venv
# activate venv
source .venv/bin/activate

pip install -r requirements.txt

# run the backtest (will write output_ptf.xlsx and output_ptf_delta.xlsx)
python backtester.py

# run tests
pytest -q
```
Jupyter:
- A Jupyter server can be started from the venv with `.venv/bin/jupyter lab --no-browser --ip=127.0.0.1 --port=8888`.
- Then open `Backtester.ipynb` in the web UI.

Notes:
- `backtester_config.py` holds the UI variables extracted from the notebook (weights, capital, dates).
- `backtester.py` mirrors the notebook `backtest()` logic and saves results to Excel files.
# Portfolio Backtester (Focus Italia) 🇮🇹

Un tool per simulare l'andamento di portafogli d'investimento pensato specificamente per andare oltre i classici calcoli dei rendimenti lordi, permettendo di comprendere come la **tassazione** e i **costi operativi** influiscano sulla crescita del capitale nel tempo.

## 🎯 Cosa permette di fare

* **Modellazione dei costi reali:** Il tool integra parametri fondamentali come **spread**, **commissioni** e **tracking difference**. Questi costi sono aggregati logicamente per riflettere l'operatività reale: 
    * I costi "spot" sono applicati sia in acquisto che in vendita (commissioni e spread).
    * La componente fiscale sulle plusvalenze viene calcolata al momento della vendita.
    * I costi ricorrenti, come l'imposta di bollo e la tracking difference, vengono applicati su base annuale.
* **Rendimenti reali (Netti):** Confronto tra la crescita lorda del mercato e il rendimento effettivamente disponibile per l'investitore dopo tasse e costi.
* **Analisi dei ribilanciamenti:** Valutazione dell'impatto fiscale e commissionale quando si vendono quote per riportare il portafoglio all'asset allocation desiderata.

---

## ⚠️ Nota
Questo strumento è creato a scopo informativo e di studio personale. Non fornisce consigli finanziari o fiscali e i risultati delle simulazioni non sono garanzia di rendimenti futuri.
