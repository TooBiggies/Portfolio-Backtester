# Uso dei dati storici — permesso e condizioni

Il file `Timeseries.csv` contiene serie storiche esportate da **testfol.io**. Non è
distribuito con questo repository: sta in un repository privato, `TooBiggies/Portfolio-Backtester-dati`,
e viene recuperato da `scripts/scarica_dati.py` quando serve.

## Il permesso

Richiesta inviata il 18 novembre 2026 a `support@testfol.io`; risposta il 24 novembre 2026:

> Hi Camillo,
>
> Thanks for reaching out and for the kind words about testfolio. Your educational
> project sounds like a great initiative. **You have my permission to use the exported
> historical data for your non-commercial project as described in your email, provided
> you do not redistribute or resell the data, sublicense it, use it to build a competing
> analytics service, or present testfolio outputs as investment advice.** Including
> clear attribution to testfolio is appreciated.
>
> Best, testfolio

## Che cosa è coperto

- Usare le serie esportate come input del simulatore, così che esempi e test riproducano
  gli stessi risultati.
- Mostrare **output derivati** — grafici di performance, metriche di rischio — nel
  materiale divulgativo, con attribuzione a testfol.io come fonte dei dati di partenza.

## Che cosa non è coperto

- Ridistribuire il dataset, in tutto o in parte, anche dentro un repository pubblico.
- Rivenderlo, sublicenziarlo, o usarlo per costruire un servizio di analisi concorrente.
- Presentare gli output come consiglio di investimento.

Per questo il CSV non è nel repository, nemmeno nella storia dei commit.

## Come procurarsi i dati

Tre strade, tutte legittime:

1. **Esportazione personale** da testfol.io (richiede un account), poi
   `python scripts/scarica_dati.py --da PERCORSO/Timeseries.csv`.
2. **Accesso al repository privato**: un fine-grained token con `Contents: Read-only`
   limitato a `TooBiggies/Portfolio-Backtester-dati`, messo in `PTF_DATI_TOKEN`.
   Senza il permesso sul repository privato il token non serve a niente.
3. **Serie proprie** nel formato del dataset: le colonne sono i ticker, il separatore è
   `;`, l'encoding `utf-8-sig`, la prima colonna sono le date.

## Attribuzione

Nei materiali che mostrano risultati calcolati su questi dati va indicata la fonte:
«dati storici: testfol.io». Non è un obbligo contrattuale ma una richiesta esplicita, ed
è anche la ragione per cui il permesso è stato dato.
