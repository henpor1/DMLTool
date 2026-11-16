# DML-Tool – Änderungen von V6.0 auf V6.1

Stand: in Arbeit. Jede Änderung wird hier direkt nach Abschluss eingetragen.

## Übersicht

| Nr | Änderung | Status |
|---|---|---|
| F1 | Umbruchprüfung meldet alle C1-Steuerzeichen (0x80–0x9F) | erledigt |

---

## F1) Umbruchprüfung: alle C1-Steuerzeichen melden

**Problem**
Die Prüfung „Zeilenumbruch, Steuerzeichen, Rand-Leerzeichen“ kannte aus dem
Bereich 0x80–0x9F nur U+0085 (NEL). Andere Zeichen aus diesem Bereich wurden
nicht gemeldet. Sie sind in ISO-8859-1 Steuerzeichen und entstehen meist, wenn
Windows-1252-Text als ISO-8859-1 gespeichert wird (z. B. Gedankenstrich „–“ = 0x96).

Gefunden in `kaputte.xml`, Zeile 455: zweimal 0x96 im Fehlertext
(„Emergency call module (0x33) – fun…“), von V6.0 nicht gemeldet.

**Änderung in `dml_logik.py`**
- Neue Konstante unter `STEUERZEICHEN`:
  `C1_MUSTER = re.compile(r"[\x80-\x84\x86-\x9f]")`
  NEL (0x85) ist bewusst ausgenommen, weil es schon in `STEUERZEICHEN` steht
  (sonst Doppelmeldung).
- `zeilenumbruch_pruef_logik()`: nach der Schleife über `STEUERZEICHEN` eine
  zweite Schleife, die jedes gefundene C1-Zeichen einmal pro Feld meldet.

**Neuer Befundtext**
`U+0096 (C1-Steuerzeichen / falsch kodiertes Sonderzeichen) in 'text'`

**Test in `test_dml_logik.py`**
`test_umbruchpruefung_findet_alle_c1_steuerzeichen` mit den Zeichen
0x96, 0x80 und 0x9F. Je eine kaputte und eine saubere Zeile; erwartet wird
genau ein Treffer in Zeile 4.

**Testergebnis**
- Vor der Änderung: 3 failed, 26 passed (Lücke nachgewiesen)
- Nach der Änderung: 29 passed

**Auswirkung auf echte Daten**
`kaputte.xml` sollte jetzt 16 statt 15 Befunde liefern (neu: Zeile 455,
Umbruch / Leerzeichen 11 statt 10). Noch in der Oberfläche zu bestätigen.

---

## Offene Punkte

- Ergebnis von F1 in der Oberfläche auf `kaputte.xml` prüfen (Zeile 455).
- Regressionstest (`referenz_erstellen.py`, `test_regression.py`, Ordner
  `testdaten/`) in `Version_6.0_Tobi/` einrichten und Referenz erzeugen.
- Docstring in `test_dml_logik.py` bzw. Doku: Testanzahl jetzt 29 statt 26.
