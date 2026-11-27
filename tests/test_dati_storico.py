"""Il modulo che decide dove sta il dataset deve fallire in modo leggibile.

Non si testa il download vero: quello richiede il token e il repository privato, e lo
verifica il job manuale `dati-verifica`. Qui si testano le tre diramazioni che decidono
il comportamento quando il file manca, che è il caso di chi clona il progetto.
"""

from __future__ import annotations

import io
import pathlib

import pytest

import dati_storico


def test_file_accanto_al_codice_ha_la_precedenza(monkeypatch, tmp_path):
    """Chi ha già il dataset in casa non deve scaricare niente."""
    finto_modulo = tmp_path / "dati_storico.py"
    finto_modulo.write_text("", encoding="utf-8")
    (tmp_path / "Timeseries.csv").write_bytes(b"x" * 10)
    monkeypatch.setattr(dati_storico, "__file__", str(finto_modulo))
    monkeypatch.setenv("PTF_DATI_TOKEN", "token-che-non-deve-servire")

    assert dati_storico.percorso_dataset() == tmp_path / "Timeseries.csv"


def test_senza_file_e_senza_token_spiega_cosa_fare(monkeypatch, tmp_path):
    finto_modulo = tmp_path / "dati_storico.py"
    finto_modulo.write_text("", encoding="utf-8")
    monkeypatch.setattr(dati_storico, "__file__", str(finto_modulo))
    monkeypatch.setattr(dati_storico.tempfile, "gettempdir", lambda: str(tmp_path / "cache"))
    monkeypatch.delenv("PTF_DATI_TOKEN", raising=False)
    monkeypatch.setattr(dati_storico, "token_disponibile", lambda: "")

    with pytest.raises(RuntimeError) as errore:
        dati_storico.percorso_dataset()

    messaggio = str(errore.value)
    assert "PTF_DATI_TOKEN" in messaggio
    assert "testfol" in messaggio


def test_scarica_scrive_il_file(monkeypatch, tmp_path):
    contenuto = b"Date;AAA\n" + b"2020-01-01;1\n" * 40_000

    class RispostaFinta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *argomenti):
            return None

    monkeypatch.setattr(dati_storico.urllib.request, "urlopen", lambda *a, **k: RispostaFinta(contenuto))

    destinazione = tmp_path / "Timeseries.csv"
    assert dati_storico.scarica(destinazione, "token-finto") == destinazione
    assert destinazione.read_bytes() == contenuto


def test_scarica_rifiuta_un_file_troppo_piccolo(monkeypatch, tmp_path):
    """Un 200 con 100 byte è un errore travestito: non deve passare come dataset."""
    monkeypatch.setattr(
        dati_storico.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"Date;AAA\n")
    )

    destinazione = tmp_path / "Timeseries.csv"
    with pytest.raises(RuntimeError):
        dati_storico.scarica(destinazione, "token-finto")
    assert not destinazione.exists(), "il file parziale non deve restare su disco"


def test_il_percorso_locale_e_quello_del_modulo():
    """Sanity check: il nome cercato è quello che il resto del codice si aspetta."""
    assert dati_storico.NOME_FILE == "Timeseries.csv"
    assert pathlib.Path(dati_storico.__file__).name == "dati_storico.py"
