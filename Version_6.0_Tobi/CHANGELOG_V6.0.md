# DML-Tool – Änderungen von V5.2 auf V6.0

Version 6.0 betrifft ausschließlich die Oberfläche. `dml_logik.py` ist
inhaltlich unverändert (nur ein ungenutzter Import entfernt), alle 26 Tests in
`test_dml_logik.py` laufen unverändert durch. Die Prüfergebnisse auf `10.xml`
sind dieselben wie in V5.2: 15 Befunde.

---

## Dateien

| Datei | Inhalt |
|---|---|
| `DML_Tool_V6_0.py` | Neue Oberfläche. Startet das Tool. |
| `dml_logik.py` | Einlesen, Validierung, alle Prüfungen. Unverändert. |
| `test_dml_logik.py` | 26 Tests. Unverändert. |
| `CHANGELOG_V6.0.md` | Dieses Dokument. |
| `CHANGELOG_V5.2.md` | Die fachlichen Korrekturen aus der Vorversion. |

`DML_Tool_V5_2.py` wird nicht mehr benötigt und kann entfallen.
Alle Dateien müssen im selben Ordner liegen, gestartet wird
`DML_Tool_V6_0.py`.

---

## 1) Ergebnisse als Tabelle statt als Textblock

Das Ausgabe-Textfeld ist durch einen `ttk.Treeview` ersetzt. Die Tabelle hat
15 Spalten: DML, Zeile, Prüfung, alle elf Felder des Fehlerspeichers und den
Befund.

- **Sortieren** – Klick auf eine Spaltenüberschrift, erneuter Klick dreht die
  Richtung um. Zahlen werden numerisch sortiert, nicht alphabetisch, damit
  Zeile 51 nicht zwischen 413 und 421 landet.
- **Filtern** – Das Filterfeld über der Tabelle durchsucht alle sichtbaren
  Spalten. Die Anzeige rechts daneben nennt jederzeit „x von y Befunden".
- **Spalten ein- und ausblenden** – Menü *Ansicht*. Vorausgewählt sind DML,
  Zeile, Prüfung, SG-Name, Text, Hexwert und Befund; die übrigen Attribute
  lassen sich bei Bedarf zuschalten.
- **Zeilen kopieren** – markieren, Strg+C. Landet tabulatorgetrennt in der
  Zwischenablage und kann direkt in Excel eingefügt werden.
- Abwechselnde Zeilenfarben, damit lange Listen lesbar bleiben.

Die zehn Checkboxen für die Ausgabeattribute aus den Vorversionen entfallen
ersatzlos – das erledigt jetzt das Ansicht-Menü.

## 2) Übersichtsleiste

Über der Tabelle steht je Prüfung eine Kachel mit der Trefferzahl, grün bei
null Befunden und rot sonst. Prüfungen ohne Treffer werden bewusst mit
angezeigt: „0 Befunde" ist bei einer Freigabeprüfung die eigentliche Aussage.

Ein Klick auf eine Kachel filtert die Tabelle auf diese Prüfung. Die Kachel
„Syntax" öffnet die Meldungen des XML-Parsers mit Zeile und Spalte.

Die Kacheln brechen nach acht Stück in die nächste Zeile um, damit sie bei
neuen Prüfungen nicht aus dem Fenster laufen.

## 3) Reiter statt achtzehn Buttons

Die Aktionen liegen jetzt auf drei Reitern:

- **Prüfen** – Liste aller Prüfungen mit Haken, dazu *Alle* / *Keine* und ein
  großer Knopf „Prüfung starten" (F5). Es laufen genau die angehakten
  Prüfungen, über beide DMLs, wenn zwei geladen sind.
- **Suchen** – Text-, Hex- oder `*`-SW-Suche über eine Auswahl, ein Eingabefeld,
  Enter startet.
- **Vergleichen** – ein Knopf für die inhaltlichen Unterschiede.

Die Prüfung „Softwareversion ist genau `*`" ist standardmäßig **nicht**
angehakt. Sie trifft auf `10.xml` 444 von 493 Einträgen und ist eher eine
Suche als eine Fehlerprüfung.

Neue Prüfungen werden nur noch in der Liste `PRUEFUNGEN` am Dateianfang
ergänzt – Checkbox, Kachel und Tabellenspalte bauen sich daraus automatisch
auf. In V5.2 musste man dafür an drei Stellen Hand anlegen.

## 4) Menüleiste

*Datei* (DMLs öffnen, CSV-Export, Beenden), *Ansicht* (Spalten, Ergebnis
leeren), *Extras* (XML-Validierung), *Hilfe*. Das entlastet die Buttonleiste
und entspricht dem, was Anwender von Windows-Programmen erwarten.

## 5) Oberfläche friert nicht mehr ein

Prüfung, Suche und Vergleich laufen in einem Hintergrundthread, in der
Statuszeile läuft solange ein Fortschrittsbalken. Möglich ist das nur, weil
`dml_logik.py` keinen tkinter-Code enthält – ein Nebeneffekt der Trennung aus
V5.2.

Die Kommunikation läuft über eine `queue.Queue`, die der GUI-Thread per
`root.after()` abfragt. Aus dem Thread heraus wird kein Widget angefasst, das
wäre bei tkinter nicht zulässig.

## 6) Dateiauswahl

Statt zweier nackter Eingabefelder gibt es Auswahlfelder mit dem Verlauf der
zuletzt geöffneten DMLs. Der Verlauf und die Fenstergröße werden beim Beenden
in `~/.dml_tool.json` gesichert und beim nächsten Start wiederhergestellt.

Drag & Drop habe ich bewusst weggelassen: Das braucht `tkinterdnd2` als
zusätzliches Paket, und ein `pip install` auf fremden Rechnern ist
erfahrungsgemäß die Hürde, an der so ein Tool liegen bleibt.

## 7) Darstellung

- **DPI-Bewusstsein unter Windows** – ohne `SetProcessDpiAwareness` ist tkinter
  auf 4K-Bildschirmen unscharf und zu klein. Drei Zeilen, großer Effekt.
- **Theme `clam`** – sieht auf allen Rechnern gleich aus, statt je nach
  Windows-Version anders.
- **Mindestgröße** 1000 × 620, damit sich das Layout nicht zerstören lässt.
- Einheitliche Abstände über `padding` statt fester Pixelkoordinaten.

## 8) Tastatur

| Taste | Funktion |
|---|---|
| F5 | Prüfung starten |
| F1 | Hilfe |
| Strg+O | 1. DML öffnen |
| Strg+S | Ergebnis als CSV |
| Strg+C | markierte Zeilen kopieren |
| Entf | Ergebnis leeren |
| Enter | im Suchfeld: Suche starten |

## 9) CSV-Export

Exportiert genau die Zeilen, die gerade in der Tabelle stehen – ein gesetzter
Filter wirkt sich also aus. Das ist praktischer als der Export aller Befunde
und in der Hilfe vermerkt. Weiterhin Semikolon als Trennzeichen und BOM, damit
Excel die Datei direkt korrekt öffnet.

## 10) Logdatei

`debug.log` läuft jetzt über einen `RotatingFileHandler` (1 MB, zwei
Sicherungen). Vorher wuchs die Datei unbegrenzt.

---

## Was gleich geblieben ist

- Alle Prüfungen und ihre Ergebnisse, inklusive Zeilennummern und Befundtexten
- Die Darstellung unsichtbarer Zeichen (`\n`, `<NBSP>`, `<U+0085>`)
- Die Trennung von Logik und Oberfläche, damit die Tests weiter greifen

## Offene Punkte

1. **Prüfregeln auslagern** – Hexmuster, verbotene Zeichen und Pflichtfelder
   stehen weiterhin im Code. In einer JSON-Datei könnte die Fachabteilung sie
   ohne Python-Kenntnisse pflegen.
2. **Kommandozeilenmodus** – ohne GUI, mit Rückgabecode ungleich null bei
   Befunden, für den automatisierten Lauf vor einer Freigabe.
3. **Sprung in die Datei** – Doppelklick auf eine Zeile könnte die XML im
   Standardeditor an der betreffenden Stelle öffnen. Bei Notepad++ ginge das
   über den Parameter `-n<Zeile>`, ist aber editorabhängig.
4. **Kodierungsprüfung als eigene Regel** – statt „Steuerzeichen U+0085"
   direkt „Datei ist vermutlich cp1252 statt ISO-8859-1" melden.
5. **Fachliche Duplikatsuche** – gleiches Steuergerät und gleicher Hexwert bei
   unterschiedlichem Text.
