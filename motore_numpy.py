"""Motore di simulazione in numpy: stessa matematica di `backtester.backtest`, più veloce.

Perché esiste
-------------
Il motore di `backtester` lavora con pandas: ogni giorno costruisce Series per il
portafoglio, e su una griglia di migliaia di combinazioni il costo dell'analisi supera
quello del calcolo (sedici secondi per una simulazione di quarantanove anni). Qui la
stessa sequenza — costi di detenzione, ribilanciamento a soglia, commissioni, imposte
sul capital gain, valore netto di liquidazione — è eseguita su array.

Cosa NON fa
-----------
Non introduce regole nuove e non approssima: è la stessa matematica, e i test in
`tests/test_motore_numpy.py` la confrontano con `backtester.backtest`. Se le due
implementazioni divergono, il test fallisce: è il solo modo per tenere una sola verità.
È riprodotto anche il **punto fisso** del ribilanciamento: le quantità da trattare
dipendono da imposte e commissioni, che dipendono dalle quantità, e `Rebalancer` itera
finché il capitale non si stabilizza (tolleranza 1e-8).
"""
from __future__ import annotations

import math

import numpy as np


def _prezzo_medio(quantita: np.ndarray, costo: np.ndarray) -> np.ndarray:
    """Prezzo medio di carico per asset: costo diviso quantità, zero se non si possiede."""
    return np.where(quantita > 0, costo / np.where(quantita > 0, quantita, 1.0), 0.0)


def _vendita(prezzi, quantita, costo, j, unita, commissione, imposta):
    """Commissione e imposta di una vendita di `unita` quote, come `Portfolio.sell`."""
    prezzo_medio = costo[j] / quantita[j] if quantita[j] > 0 else 0.0
    commissione_pagata = unita * prezzi[j] * commissione
    # Il corrispettivo è al netto della commissione: senza questo l'imposta si
    # calcolerebbe su un guadagno più grande di quello vero (issue #87).
    imposta_dovuta = max(0.0, unita * (prezzi[j] - prezzo_medio) - commissione_pagata) * imposta
    return commissione_pagata, imposta_dovuta


def _ribilancia(quantita, costo, prezzi_giorno, target, commissione, imposta):
    """Porta il portafoglio ai pesi obiettivo, con lo stesso punto fisso di `Rebalancer`.

    Le quantità si calcolano su un capitale che parte dal valore di mercato e scende di
    imposte e commissioni a ogni iterazione: vendere per ribilanciare costa, e il costo
    cambia le quantità.
    """
    valore_mercato = float((quantita * prezzi_giorno).sum())
    v_prime = valore_mercato

    for _ in range(50):
        trattare = target * v_prime / prezzi_giorno - quantita
        totale_imposte = 0.0
        totale_commissioni = 0.0
        for j in range(len(quantita)):
            if trattare[j] < 0:
                fee, tax = _vendita(prezzi_giorno, quantita, costo, j, -trattare[j],
                                    commissione, imposta)
                totale_imposte += tax
                totale_commissioni += fee
            elif trattare[j] > 0:
                totale_commissioni += trattare[j] * prezzi_giorno[j] * commissione
        nuovo = valore_mercato - totale_imposte - totale_commissioni
        if not math.isfinite(nuovo):
            raise ValueError("Valore del portafoglio non finito durante il ribilanciamento.")
        if abs(nuovo / v_prime - 1) < 1e-8:
            v_prime = nuovo
            break
        v_prime = nuovo

    trattare = target * v_prime / prezzi_giorno - quantita
    for j in range(len(quantita)):
        unita = trattare[j]
        if unita > 0:
            fee = unita * prezzi_giorno[j] * commissione
            quantita[j] += unita
            # La commissione entra nel costo di carico: è quanto si è pagato per quota.
            costo[j] += unita * prezzi_giorno[j] + fee
        elif unita < 0:
            unita = max(unita, -quantita[j])          # non si vende più di quanto si ha
            prezzo_medio = costo[j] / quantita[j] if quantita[j] > 0 else 0.0
            quantita[j] += unita
            costo[j] -= (-unita) * prezzo_medio


def _valore_netto(quantita, costo, prezzi_giorno, commissione, imposta):
    """Valore di liquidazione: quote a prezzo di mercato meno commissioni e imposte di uscita."""
    quote = quantita * prezzi_giorno
    prezzo_medio = _prezzo_medio(quantita, costo)
    commissioni_uscita = np.abs(quote) * commissione
    imposte_uscita = np.maximum(0.0, quote - quantita * prezzo_medio - commissioni_uscita) * imposta
    return float((quote - commissioni_uscita - imposte_uscita).sum())


def valori_netti(prezzi, pesi, valore_iniziale=10_000.0, soglia_assoluta=0.05,
                 soglia_relativa=None, commissione=0.001, costi_annui=0.002,
                 imposta=0.26) -> np.ndarray:
    """Valore netto del portafoglio per ogni giorno di `prezzi`.

    Parametri
    ---------
    prezzi : array (giorni x asset)
        Prezzi di chiusura, già allineati sulle stesse date.
    pesi : array (asset,)
        Pesi obiettivo, somma 1.
    soglia_assoluta : float
        Scostamento in punti di peso oltre il quale si ribilancia.
    soglia_relativa : float o None
        Scostamento in frazione del peso obiettivo, in OR con quella assoluta.

    Restituisce
    -----------
    np.ndarray
        Valore netto, giorno per giorno, al netto di costi e imposte di liquidazione.
    """
    prezzi = np.asarray(prezzi, dtype=float)
    target = np.asarray(pesi, dtype=float)
    giorni, n_asset = prezzi.shape

    ter_giornaliero = costi_annui / 252.0
    # Come `Portfolio.from_weights`: la commissione d'ingresso si paga comprando meno
    # quote, non aggiungendo un costo fuori dal capitale. Il costo di carico resta
    # pari al capitale investito, commissione compresa.
    quantita = target * valore_iniziale / (prezzi[0] * (1.0 + commissione))
    costo = quantita * prezzi[0] * (1.0 + commissione)

    netti = np.empty(giorni, dtype=float)

    for i in range(giorni):
        prezzi_giorno = prezzi[i]
        if i:
            quantita *= (1.0 - ter_giornaliero)
            costo *= (1.0 - ter_giornaliero)

            broker = quantita * prezzi_giorno
            totale = broker.sum()
            pesi_correnti = broker / totale if totale > 0 else np.zeros(n_asset)
            delta = target - pesi_correnti

            scatta = np.abs(delta) > soglia_assoluta
            if soglia_relativa is not None:
                base = np.where(target > 0, target, np.nan)
                with np.errstate(invalid="ignore"):
                    scatta = scatta | ((np.abs(delta) / base) > soglia_relativa)

            if scatta.any():
                _ribilancia(quantita, costo, prezzi_giorno, target, commissione, imposta)

        netti[i] = _valore_netto(quantita, costo, prezzi_giorno, commissione, imposta)

    return netti


def sortino_netto(valori_netto, rendimento_privo_rischio) -> float:
    """Sortino come `metrics.py`: eccesso sul tasso privo di rischio, downside su tutte le osservazioni."""
    valori = np.asarray(valori_netto, dtype=float)
    if len(valori) < 3:
        return float("nan")
    rendimenti = valori[1:] / valori[:-1] - 1.0
    rf = np.asarray(rendimento_privo_rischio, dtype=float)[1:len(rendimenti) + 1]
    eccesso = rendimenti - rf
    periodi = 252
    annuo = eccesso.mean() * periodi
    downside = math.sqrt((np.minimum(eccesso, 0.0) ** 2).mean()) * math.sqrt(periodi)
    if downside <= 0 or not math.isfinite(downside):
        return float("nan")
    return float(annuo / downside)
