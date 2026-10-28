"""Validazione degli ingressi di backtest(): pesi e capitale.

Due difetti chiusi qui, entrambi silenziosi (issue #62 e #66):

- pesi che non sommano a 1: il ribilanciamento porta il portafoglio ai target vendendo
  la quota non investita, e il ricavato sparisce — non esiste un conto liquidita'.
  Con pesi a somma 0,5 ogni ribilanciamento dimezza il capitale e il risultato e' -100%
  senza alcun errore;
- capitale iniziale 0: nel ciclo di convergenza `new_V_prime / V_prime` diventa 0/0 = NaN,
  e `NaN < 1e-8` e' sempre falso, quindi il ciclo non termina mai (nessun errore, processo
  appeso). Con capitale negativo il primo riacquisto non e' finanziabile.
"""
import pandas as pd
import pytest

from backtester import backtest

PERIODO = dict(begin_date=pd.Timestamp("2020-01-02"), end_date=pd.Timestamp("2020-03-02"))


def esegui(**kwargs):
    parametri = dict(initial_value=10000, weights={"VTSIM": 1.0}, save_outputs=False)
    parametri.update(kwargs)
    return backtest(**parametri, **PERIODO)


# --- pesi (issue #62) ----------------------------------------------------

def test_pesi_che_sommano_a_meno_di_uno_sono_rifiutati():
    with pytest.raises(ValueError, match="sommare a 1.0"):
        esegui(weights={"VTSIM": 0.5})


def test_pesi_che_sommano_a_piu_di_uno_sono_rifiutati():
    with pytest.raises(ValueError, match="sommare a 1.0"):
        esegui(weights={"VTSIM": 0.6, "GLDSIM": 0.6})


def test_il_messaggio_elenca_i_pesi_ricevuti():
    """Chi sbaglia un ticker o dimentica una quota deve vedere cosa ha passato."""
    with pytest.raises(ValueError) as errore:
        esegui(weights={"VTSIM": 0.5, "GLDSIM": 0.1})
    messaggio = str(errore.value)
    assert "0.600000" in messaggio
    assert "VTSIM" in messaggio and "GLDSIM" in messaggio


def test_pesi_negativi_sono_rifiutati():
    """Il motore non va allo scoperto: un peso negativo verrebbe ignorato in acquisto e
    venduto al primo ribilanciamento, quindi va fermato all'ingresso."""
    with pytest.raises(ValueError, match="negativi"):
        esegui(weights={"VTSIM": 1.5, "GLDSIM": -0.5})


def test_pesi_vuoti_sono_rifiutati():
    with pytest.raises(ValueError, match="vuoto"):
        esegui(weights={})


def test_la_tolleranza_sull_arrotondamento_e_ammessa():
    """0,333+0,333+0,334 non fa esattamente 1 in virgola mobile: non deve essere un errore."""
    esegui(weights={"VTSIM": 0.333, "GLDSIM": 0.333, "ZROZSIM": 0.334})


# --- capitale (issue #66) ------------------------------------------------

def test_capitale_zero_viene_rifiutato_subito():
    """Senza la guardia il backtest non termina: 0/0 = NaN nel ciclo di convergenza."""
    with pytest.raises(ValueError, match="capitale iniziale"):
        esegui(initial_value=0)


def test_capitale_negativo_viene_rifiutato():
    with pytest.raises(ValueError, match="capitale iniziale"):
        esegui(initial_value=-1000)


def test_capitale_non_numerico_viene_rifiutato_con_messaggio_chiaro():
    with pytest.raises(ValueError, match="deve essere un numero"):
        esegui(initial_value="diecimila")


def test_capitale_nan_viene_rifiutato():
    """NaN non e' > 0: deve cadere come gli altri casi non validi."""
    with pytest.raises(ValueError, match="capitale iniziale"):
        esegui(initial_value=float("nan"))


def test_un_capitale_valido_continua_a_funzionare():
    """La guardia non deve rompere il caso normale."""
    _, _, sommario = esegui(initial_value=5000)
    assert sommario["final_net"] > 0
