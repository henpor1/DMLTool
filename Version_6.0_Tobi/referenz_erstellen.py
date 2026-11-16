"""Erzeugt die Referenzergebnisse für die Regressionstests.

Aufruf (im Projektordner):
    python referenz_erstellen.py            -> alle XML-Dateien in testdaten/
    python referenz_erstellen.py kaputte.xml -> nur diese Datei

Ergebnis: testdaten/erwartet/<dateiname>.json
Nur ausführen, wenn das aktuelle Ergebnis bewusst als "richtig" gelten soll!
"""
import json
import sys
from pathlib import Path

import dml_logik as L

ORDNER = Path(__file__).parent / "testdaten"
ERWARTET = ORDNER / "erwartet"

# Entspricht den standardmäßig angehakten Prüfungen in der GUI
# (SW = '*' ist standardmäßig aus und daher nicht enthalten).
PRUEFUNGEN = {
    "NA / NBSP":             lambda fs, z, roh: L.na_pruef_logik(fs, zeilen=z),
    "x-TN/SW":               lambda fs, z, roh: L.x_pruef_logik(fs, zeilen=z),
    "xx-Wildcard":           lambda fs, z, roh: L.wildcard_pruef_logik(fs, zeilen=z),
    "Umbruch / Leerzeichen": lambda fs, z, roh: L.zeilenumbruch_pruef_logik(fs, rohelemente=roh, zeilen=z),
    "Hex-Format":            lambda fs, z, roh: L.hexformat_pruef_logik(fs, zeilen=z),
    "Pflichtfelder":         lambda fs, z, roh: L.attribut_pruef_logik(fs, zeilen=z),
    "Duplikate":             lambda fs, z, roh: L.pruef_dopplung_logik(fs, zeilen=z),
}


def pruefe_datei(pfad):
    """Lässt alle Prüfungen laufen und liefert eine sortierte Befundliste."""
    fehlerspeicher, zeilen, rohelemente, hinweise = L.lade_dml(str(pfad))
    befunde = []
    for name, pruefung in PRUEFUNGEN.items():
        for zeile, fsp, befund in pruefung(fehlerspeicher, zeilen, rohelemente):
            befunde.append({
                "pruefung": name,
                "zeile": zeile,
                "fsp": [str(f) for f in fsp],
                "befund": befund,
            })
    befunde.sort(key=lambda b: (b["pruefung"], b["zeile"] or 0, b["befund"]))
    return {
        "anzahl_eintraege": len(fehlerspeicher),
        "hinweise": hinweise,
        "befunde": befunde,
    }


def main():
    ERWARTET.mkdir(parents=True, exist_ok=True)
    dateien = [ORDNER / n for n in sys.argv[1:]] or sorted(ORDNER.glob("*.xml"))
    for pfad in dateien:
        ergebnis = pruefe_datei(pfad)
        ziel = ERWARTET / (pfad.stem + ".json")
        # ensure_ascii=True: Steuerzeichen wie U+0085 bleiben als \u0085 lesbar
        ziel.write_text(json.dumps(ergebnis, indent=2, ensure_ascii=True), encoding="utf-8")

        zaehler = {}
        for b in ergebnis["befunde"]:
            zaehler[b["pruefung"]] = zaehler.get(b["pruefung"], 0) + 1
        print(f"{pfad.name}: {len(ergebnis['befunde'])} Befunde in "
              f"{ergebnis['anzahl_eintraege']} Einträgen -> {ziel.name}")
        for name in PRUEFUNGEN:
            print(f"   {name:<24}{zaehler.get(name, 0)}")
        for h in ergebnis["hinweise"]:
            print("   HINWEIS:", h)


if __name__ == "__main__":
    main()
