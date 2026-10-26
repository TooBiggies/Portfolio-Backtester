Portfolio Backtester simula l'evoluzione storica di un portafoglio tenendo conto dell'asset allocation, dei ribilanciamenti, delle commissioni, dei costi annuali e della fiscalità.

## Come avviare il backtester online

Da questa pagina:

1. Cliccare sul pulsante verde **Code**.
2. Selezionare la scheda **Codespaces**.
3. Cliccare su **Create codespace on main**.
4. Attendere l'apertura dell'ambiente di sviluppo nel browser.
5. Aprire il terminale dal menu **Terminal > New Terminal**.
6. Installare le dipendenze:

```bash
python -m pip install -r requirements.txt
```

7. Avviare l'applicazione:

```bash
python -m streamlit run streamlit_app.py
```

8. Quando il Codespace segnala che l'applicazione è disponibile sulla porta `8501`, cliccare su **Open in Browser**.

Se la notifica non compare, aprire la scheda **Porte**, individuare la porta `8501` e cliccare sull'icona per aprirla nel browser.

## Come utilizzare l'applicazione

Nella pagina dell'applicazione è possibile configurare:

- capitale iniziale;
- data iniziale e finale;
- peso percentuale di ciascun asset;
- costi di negoziazione;
- costi annuali;
- aliquota fiscale;
- soglia di ribilanciamento.

La somma dei pesi degli asset deve essere pari al `100%`.

Dopo aver impostato i parametri, cliccare su **Esegui backtest**.

## Risultati

Al termine dell'elaborazione, l'applicazione mostra:

- valore finale lordo;
- valore finale presso il broker;
- valore finale netto;
- CAGR lordo;
- CAGR presso il broker;
- CAGR netto;
- andamento storico del portafoglio.

### GrossPortfolioValue

Valore del portafoglio ideale simulato senza commissioni di negoziazione, costi annuali e imposte sulle plusvalenze realizzate.

### BrokerPortfolioValue

Valore degli asset effettivamente detenuti nel portafoglio reale, dopo l'applicazione dei costi e delle imposte già sostenuti durante la simulazione.

### Net

Valore stimato del portafoglio reale al netto dei costi e delle imposte applicabili in caso di liquidazione.

La differenza tra `GrossPortfolioValue` e `BrokerPortfolioValue` rappresenta l'effetto cumulato dei costi e della fiscalità, compreso il mancato rendimento sul capitale utilizzato per sostenere tali oneri.

## Esportazione dei risultati

Il pulsante **Scarica risultati Excel** genera un file con due fogli:

- `Portfolio`: evoluzione giornaliera del portafoglio;
- `Rebalancing`: operazioni e variazioni registrate durante i ribilanciamenti.

## Terminare la sessione

Per interrompere Streamlit, tornare al terminale e premere `Ctrl+C`.

Al termine dell'utilizzo è consigliabile arrestare o eliminare il Codespace per evitare di consumare inutilmente le ore e lo spazio disponibili.

## Note

- Le date devono rientrare nell'intervallo disponibile nelle serie storiche.
- La data iniziale deve precedere la data finale.
- I pesi degli asset devono sommare al `100%`.
- Le percentuali inserite vengono convertite automaticamente in valori decimali.
- I risultati dipendono dalla qualità e dalla completezza delle serie storiche.
- Il backtest non costituisce una previsione dei rendimenti futuri.
