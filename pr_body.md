## Perché

`Timeseries.csv` contiene serie esportate da **testfol.io**. Il permesso arrivato il 24 novembre 2026 copre l'uso del dataset e la pubblicazione degli output derivati, ma vieta esplicitamente la ridistribuzione. Un CSV dentro un repository pubblico **è** ridistribuzione: chiunque scarica l'archivio, anche senza autenticarsi.

Il testo integrale del permesso è in `PERMISSION.md`.

## Cosa cambia

| File | Effetto |
|---|---|
| `Timeseries.csv` | esce dall'albero (resta in locale, `.gitignore` già esclude `*.csv`) |
| `scripts/scarica_dati.py` | nuovo: recupera il dataset dal repo privato con token di sola lettura, oppure copia un'esportazione personale con `--da` |
| `PERMISSION.md` | nuovo: permesso citato, cosa è coperto, cosa no, come procurarsi i dati |
| `.github/workflows/dati-verifica.yml` | nuovo: job **solo manuale** che gira la suite sui dati veri |
| `README.md` | sezione «Il dataset storico» prima delle istruzioni di avvio |

## Perché il workflow è solo `workflow_dispatch`

Il job ha bisogno di un token che legge il repository privato. Se partisse sulle pull request, chiunque aprisse una PR potrebbe modificare lo YAML per far uscire il token o i dati. Il comando manuale ha codice scelto da chi avvia il job, non da chi propone la modifica.

## Comportamento senza dataset

I test end-to-end già si saltavano con un messaggio esplicito quando il file manca (`tests/test_backtest_end_to_end.py`). Dopo questa modifica quel caso diventa la norma su un clone pulito, invece dell'eccezione: la CI resta verde, ma nessun test finge di aver verificato i numeri.

## Prove eseguite

```
python scripts/scarica_dati.py --da Timeseries.csv --destinazione prova.csv
  → Scritto prova.csv (1392 KB, 14135 righe)

senza token        → spiega le due strade, exit 1, nessun file scritto
token non valido   → "Token non valido o senza permesso di lettura", exit 1
file già esistente → non sovrascrive
```

## Cosa resta da fare (fuori da questa PR)

1. creare il repository privato `Portfolio-Backtester-dati` e caricarci il CSV;
2. rimuovere il file **dalla storia** con `git filter-repo` e force-push, altrimenti resta scaricabile dai commit vecchi;
3. creare il fine-grained token (`Contents: Read-only` sul solo repo privato) e salvarlo come secret `PTF_DATI_TOKEN`.
