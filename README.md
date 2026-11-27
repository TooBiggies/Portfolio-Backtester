# Portfolio Backtester (Focus Italia) 🇮🇹

Un tool per simulare l'andamento di portafogli d'investimento pensato specificamente per andare oltre i classici calcoli dei rendimenti lordi, permettendo di comprendere come la **tassazione** e i **costi operativi** influiscano sulla crescita del capitale nel tempo.

## L'app

Si usa online, senza installare niente: **https://tbtfolio.streamlit.app**

## Dati storici e permesso d'uso

Il dataset storico usato dal simulatore (`Timeseries.csv`) **non è distribuito con questo
progetto**. Contiene serie esportate da [testfol.io](https://testfol.io), che ne ha
autorizzato l'uso per questo progetto non commerciale ma non la ridistribuzione.

Il testo integrale del permesso, con data e condizioni, è in [PERMISSION.md](PERMISSION.md).
Le serie si procurano con un'esportazione personale dal sito, oppure — per chi ha accesso
al deposito privato — con lo script `scripts/scarica_dati.py` del branch di sviluppo.

Nei materiali che mostrano risultati calcolati su questi dati la fonte va indicata:
«dati storici: testfol.io».

## 🎯 Cosa permette di fare

* **Modellazione dei costi reali:** Il tool integra parametri fondamentali come **spread**, **commissioni** e **tracking difference**. Questi costi sono aggregati logicamente per riflettere l'operatività reale:
    * I costi "spot" sono applicati sia in acquisto che in vendita (commissioni e spread).
    * La componente fiscale sulle plusvalenze viene calcolata al momento della vendita.
    * I costi ricorrenti, come l'imposta di bollo e la tracking difference, vengono applicati su base annuale.
* **Rendimenti reali (Netti):** Confronto tra la crescita lorda del mercato e il rendimento effettivamente disponibile per l'investitore dopo tasse e costi.
* **Analisi dei ribilanciamenti:** Valutazione dell'impatto fiscale e commissionale quando si vendono quote per riportare il portafoglio all'asset allocation desiderata.

## ⚠️ Nota

Questo strumento è creato a scopo informativo e di studio personale. Non fornisce consigli finanziari o fiscali e i risultati delle simulazioni non sono garanzia di rendimenti futuri.
