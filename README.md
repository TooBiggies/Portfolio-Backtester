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
