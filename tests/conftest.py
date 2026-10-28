"""Configurazione comune dei test.

`MPLBACKEND=Agg` va impostato prima che matplotlib venga importato: senza, su una
macchina con display matplotlib sceglie TkAgg e la creazione di una figura dentro il
thread di Streamlit (AppTest, Streamlit in generale) termina il processo con
"Fatal Python error: Illegal instruction". Un backend non interattivo rende i test
deterministici anche su un runner headless.
"""
import os

os.environ.setdefault("MPLBACKEND", "Agg")
