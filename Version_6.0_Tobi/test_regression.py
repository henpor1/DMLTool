"""Regressionstest: vergleicht das aktuelle Ergebnis mit testdaten/erwartet/*.json.

Aufruf: python -m pytest test_regression.py -v
"""
import json

import pytest

from referenz_erstellen import ERWARTET, ORDNER, pruefe_datei

REFERENZEN = sorted(ERWARTET.glob("*.json"))


def _schluessel(b):
    return (b["pruefung"], b["zeile"], b["befund"])


@pytest.mark.parametrize("referenz", REFERENZEN, ids=[r.stem for r in REFERENZEN])
def test_ergebnis_unveraendert(referenz):
    erwartet = json.loads(referenz.read_text(encoding="utf-8"))
    aktuell = pruefe_datei(ORDNER / (referenz.stem + ".xml"))

    assert aktuell["anzahl_eintraege"] == erwartet["anzahl_eintraege"]

    alt = {_schluessel(b) for b in erwartet["befunde"]}
    neu = {_schluessel(b) for b in aktuell["befunde"]}
    fehlen = sorted(alt - neu, key=str)
    dazu = sorted(neu - alt, key=str)

    meldung = []
    if fehlen:
        meldung.append("NICHT MEHR gefunden:\n  " + "\n  ".join(map(str, fehlen)))
    if dazu:
        meldung.append("NEU gefunden:\n  " + "\n  ".join(map(str, dazu)))
    assert not meldung, "\n".join(meldung)
