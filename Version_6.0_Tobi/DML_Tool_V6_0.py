# -*- coding: utf-8 -*-
# DML-Auswertung  Version 6.0
# Neu aufgebaute Oberfläche. Die Prüflogik liegt unverändert in dml_logik.py.
# Was sich geändert hat, steht in CHANGELOG_V6.0.md.
# Kodierung der Quelldatei: UTF-8

import json
import os
import queue
import threading
import csv as csv_module
import logging
from collections import namedtuple
from datetime import datetime

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

from dml_logik import (
    FELDNAMEN, sichtbar,
    lade_dml, validate_xml_collect_errors,
    sw_suche_logik, na_pruef_logik, wildcard_pruef_logik, x_pruef_logik,
    zeilenumbruch_pruef_logik, hexformat_pruef_logik, attribut_pruef_logik,
    pruef_dopplung_logik, inhaltssuche_logik, hexwert_suche_logik,
    unterschiede_logik,
)

VERSION = "6.0"
EINSTELLUNGSDATEI = os.path.join(os.path.expanduser("~"), ".dml_tool.json")


# ---------------------------------------------------------------------------
# Prüfungskatalog
# Ein Eintrag je Prüfung: Schlüssel, Beschriftung, Funktion, Vorauswahl.
# Neue Prüfungen werden hier ergänzt, die Oberfläche baut sich daraus auf.
# ---------------------------------------------------------------------------

Pruefung = namedtuple("Pruefung", "schluessel kurz titel funktion vorauswahl")

PRUEFUNGEN = [
    Pruefung("na", "NA / NBSP",
             "NA-Prüfung (geschütztes Leerzeichen)",
             lambda fs, roh, z: na_pruef_logik(fs, z), True),
    Pruefung("x", "x-TN/SW",
             "x in Teilenummer oder Softwareversion",
             lambda fs, roh, z: x_pruef_logik(fs, z), True),
    Pruefung("xx", "xx-Wildcard",
             "xx-Wildcard in einem Wert",
             lambda fs, roh, z: wildcard_pruef_logik(fs, z), True),
    Pruefung("umbruch", "Umbruch / Leerzeichen",
             "Zeilenumbruch, Steuerzeichen, Rand-Leerzeichen",
             lambda fs, roh, z: zeilenumbruch_pruef_logik(fs, roh, z), True),
    Pruefung("hex", "Hex-Format",
             "Hexwert-Format (0xHHHHHH)",
             lambda fs, roh, z: hexformat_pruef_logik(fs, z), True),
    Pruefung("pflicht", "Pflichtfelder",
             "Leere Pflichtfelder",
             lambda fs, roh, z: attribut_pruef_logik(fs, z), True),
    Pruefung("dopplung", "Duplikate",
             "Doppelte Einträge",
             lambda fs, roh, z: pruef_dopplung_logik(fs, z), True),
    Pruefung("sw", "SW = '*'",
             "Softwareversion ist genau '*'",
             lambda fs, roh, z: sw_suche_logik(fs, z), False),
]

# Kacheln je Zeile in der Übersichtsleiste
KACHELN_PRO_ZEILE = 8

# Spalten der Ergebnistabelle: Schlüssel, Überschrift, Breite, Vorauswahl
SPALTEN = [
    ("quelle",            "DML",           55,  True),
    ("zeile",             "Zeile",         60,  True),
    ("pruefung",          "Prüfung",       210, True),
    ("shortname",         "SG-Name",       190, True),
    ("variante",          "Variante",      120, False),
    ("status_v",          "Status_v",      70,  False),
    ("status_p",          "Status_p",      70,  False),
    ("teilenummer",       "Teilenummer",   130, False),
    ("softwareversion",   "SW-Version",    100, False),
    ("produktschluessel", "Produktschl.",  100, False),
    ("ausstattung",       "Ausstattung",   110, False),
    ("fehlervorbedingung", "Fehlervorbed.", 110, False),
    ("text",              "Text",          320, True),
    ("hexwert",           "Hexwert",       90,  True),
    ("befund",            "Befund",        420, True),
]

# Zuordnung Spaltenschlüssel -> Index im FSP-Datensatz
FELD_INDEX = {name: i for i, name in enumerate(FELDNAMEN)}


# ---------------------------------------------------------------------------
# Zustand und Logging
# ---------------------------------------------------------------------------

class DmlState:
    """Hält die eingelesenen DMLs und alle aktuellen Befunde."""

    def __init__(self):
        self.dml = {}           # "1.XML"/"2.XML" -> (fehlerspeicher, zeilen, roh)
        self.befunde = []       # Liste von Dicts, siehe _mache_befund()
        self.syntaxhinweise = {}
        self.gelaufen = []      # Kurznamen der Prüfungen, die im letzten Lauf wirklich liefen (C1)
        self.laeuft = False


state = DmlState()
logger = logging.getLogger('Log')


LOG_PFAD = None      # Pfad der Logdatei, falls eingerichtet (C3)
LOG_FEHLER = None    # Fehlermeldung, falls Logging nicht möglich war (C3)

def beschreibe_logfehler(fehler):
    """Übersetzt einen Fehler beim Anlegen der Logdatei in Ursache und Lösung (C3)."""
    import errno
    if isinstance(fehler, PermissionError):
        ursache = ("Keine Schreibrechte im Benutzerordner oder die Logdatei ist gesperrt "
                   "(z. B. weil das Tool bereits in einem zweiten Fenster läuft).")
        loesung = ("Andere Fenster des Tools schließen und neu starten. Hilft das nicht, "
                   "die IT nach Schreibrechten für den Benutzerordner fragen.")
    elif isinstance(fehler, FileNotFoundError):
        ursache = "Der Benutzerordner ist nicht erreichbar (z. B. Netzlaufwerk ohne Verbindung)."
        loesung = "Netzwerk- bzw. VPN-Verbindung prüfen und das Tool neu starten."
    elif getattr(fehler, "errno", None) == errno.ENOSPC:
        ursache = "Auf dem Laufwerk ist kein Speicherplatz mehr frei."
        loesung = "Speicherplatz freigeben und das Tool neu starten."
    else:
        ursache = "Unbekannte Ursache."
        loesung = "Diese Meldung an den Betreuer des Tools weitergeben."
    return f"{ursache}\n\nLösung: {loesung}\n\nTechnische Meldung: {fehler}"

def log_start():
    """Richtet die Logdatei im Benutzerverzeichnis ein."""
    global LOG_PFAD, LOG_FEHLER
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    logger.setLevel(logging.DEBUG)

    try:
        log_ordner = Path.home() / "DML_Tool" / "logs"
        log_ordner.mkdir(parents=True, exist_ok=True)
        log_datei = log_ordner / "debug.log"

        fh = RotatingFileHandler(log_datei, maxBytes=1_000_000,
                                 backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
        LOG_PFAD = log_datei

    except OSError as fehler:
        # Das Tool soll auch ohne Schreibrechte starten können.
        LOG_FEHLER = beschreibe_logfehler(fehler)

log_start()


def lade_einstellungen():
    """Liest Fenstergröße und zuletzt geöffnete Dateien aus dem Benutzerprofil."""
    try:
        with open(EINSTELLUNGSDATEI, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def speichere_einstellungen():
    """Sichert Fenstergröße und Dateiverlauf beim Beenden."""
    try:
        daten = {"geometry": root.geometry(), "zuletzt": zuletzt_geoeffnet[:8]}
        with open(EINSTELLUNGSDATEI, "w", encoding="utf-8") as f:
            json.dump(daten, f)
    except Exception:
        logger.warning("Einstellungen konnten nicht gespeichert werden", exc_info=True)


einstellungen = lade_einstellungen()
zuletzt_geoeffnet = list(einstellungen.get("zuletzt", []))


# ---------------------------------------------------------------------------
# Hintergrundausführung
# ---------------------------------------------------------------------------

def im_hintergrund(arbeit, danach, statustext):
    """Führt 'arbeit' in einem Thread aus und ruft 'danach' im GUI-Thread auf.

    Die Prüflogik ist frei von tkinter, deshalb ist das gefahrlos möglich.
    Die Oberfläche bleibt währenddessen bedienbar.
    """
    if state.laeuft:
        return
    state.laeuft = True
    set_status(statustext)
    fortschritt.start(12)

    ergebnisse = queue.Queue()

    def lauf():
        try:
            ergebnisse.put(("ok", arbeit()))
        except Exception as fehler:      # noqa: BLE001 - bewusst alles abfangen
            ergebnisse.put(("fehler", fehler))

    threading.Thread(target=lauf, daemon=True).start()

    def abfragen():
        try:
            art, wert = ergebnisse.get_nowait()
        except queue.Empty:
            root.after(80, abfragen)
            return

        fortschritt.stop()
        state.laeuft = False
        if art == "ok":
            danach(wert)
        else:
            logger.warning("Fehler im Hintergrundlauf", exc_info=wert)
            hinweis = f"siehe {LOG_PFAD}" if LOG_PFAD else "keine Logdatei verfügbar"
            set_status(f"Fehler - {hinweis}")
            messagebox.showerror("Fehler", f"Die Prüfung ist fehlgeschlagen:\n\n{wert}\n\nDetails: {hinweis}")

    root.after(80, abfragen)


# ---------------------------------------------------------------------------
# Dateiauswahl
# ---------------------------------------------------------------------------

def merke_datei(pfad):
    """Nimmt einen Pfad in den Verlauf auf und aktualisiert beide Auswahlfelder."""
    if not pfad:
        return
    if pfad in zuletzt_geoeffnet:
        zuletzt_geoeffnet.remove(pfad)
    zuletzt_geoeffnet.insert(0, pfad)
    for feld in (pfad_feld1, pfad_feld2):
        feld["values"] = zuletzt_geoeffnet[:8]


def waehle_datei(feld):
    """Öffnet den Dateidialog und trägt das Ergebnis in das Auswahlfeld ein."""
    pfad = filedialog.askopenfilename(
        title="DML auswählen", filetypes=[("XML-Dateien", "*.xml"), ("Alle Dateien", "*.*")])
    if pfad:
        feld.set(pfad)
        merke_datei(pfad)


def aktive_pfade():
    """Liefert die eingetragenen Pfade als {"1.XML": pfad, ...}."""
    pfade = {}
    if pfad_var1.get().strip():
        pfade["1.XML"] = pfad_var1.get().strip()
    if pfad_var2.get().strip():
        pfade["2.XML"] = pfad_var2.get().strip()
    return pfade


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def lese_dmls(pfade):
    """Liest alle angegebenen DMLs ein. Läuft im Hintergrundthread."""
    geladen, hinweise = {}, {}
    for quelle, pfad in pfade.items():
        fehlerspeicher, zeilen, roh, meldungen = lade_dml(pfad)
        geladen[quelle] = (fehlerspeicher, zeilen, roh)
        hinweise[quelle] = validate_xml_collect_errors(pfad) + meldungen
    return geladen, hinweise


def _mache_befund(quelle, pruefung, zeile, fsp, text):
    """Baut einen Ergebnisdatensatz für die Tabelle."""
    return {"quelle": quelle, "pruefung": pruefung, "zeile": zeile,
            "fsp": fsp, "befund": text}


# ---------------------------------------------------------------------------
# Aktionen: Prüfen, Suchen, Vergleichen
# ---------------------------------------------------------------------------

def starte_pruefung():
    """Führt alle angehakten Prüfungen über alle geladenen DMLs aus."""
    pfade = aktive_pfade()
    if not pfade:
        messagebox.showinfo("Keine DML", "Bitte zuerst eine DML auswählen.")
        return

    gewaehlt = [p for p in PRUEFUNGEN if pruef_vars[p.schluessel].get()]
    if not gewaehlt:
        messagebox.showinfo("Keine Auswahl", "Bitte mindestens eine Prüfung anhaken.")
        return

    def arbeit():
        geladen, hinweise = lese_dmls(pfade)
        befunde = []
        for quelle, (fehlerspeicher, zeilen, roh) in geladen.items():
            for pruefung in gewaehlt:
                for zeile, fsp, grund in pruefung.funktion(fehlerspeicher, roh, zeilen):
                    befunde.append(_mache_befund(quelle, pruefung.kurz, zeile, fsp, grund))
        return geladen, hinweise, befunde

    def danach(ergebnis):
        geladen, hinweise, befunde = ergebnis
        state.dml, state.syntaxhinweise, state.befunde = geladen, hinweise, befunde
        state.gelaufen = [p.kurz for p in gewaehlt]
        zeige_ergebnis()
        anzahl = sum(len(f[0]) for f in geladen.values())
        set_status(f"{len(befunde)} Befunde in {anzahl} Fehlerspeicher-Einträgen")

    im_hintergrund(arbeit, danach, "Prüfung läuft...")


def starte_suche(_event=None):
    """Führt die auf dem Reiter 'Suchen' gewählte Suche aus."""
    pfade = aktive_pfade()
    if not pfade:
        messagebox.showinfo("Keine DML", "Bitte zuerst eine DML auswählen.")
        return

    modus = such_modus.get()
    begriffe = [b.strip().lower() for b in such_feld.get().split(",") if b.strip()]
    if modus in ("text", "hex") and not begriffe:
        messagebox.showinfo("Kein Suchbegriff",
                            "Bitte einen Suchbegriff eingeben (mehrere mit Komma trennen).")
        return

    titel = {"text": "Text-Suche", "hex": "Hex-Suche", "sw": "Softwareversion '*'"}[modus]

    def arbeit():
        geladen, hinweise = lese_dmls(pfade)
        befunde = []
        for quelle, (fehlerspeicher, zeilen, _) in geladen.items():
            if modus == "text":
                treffer = inhaltssuche_logik(fehlerspeicher, begriffe, zeilen)
            elif modus == "hex":
                treffer = hexwert_suche_logik(fehlerspeicher, begriffe, zeilen)
            else:
                treffer = sw_suche_logik(fehlerspeicher, zeilen)
            for zeile, fsp, grund in treffer:
                befunde.append(_mache_befund(quelle, titel, zeile, fsp, grund))
        return geladen, hinweise, befunde

    def danach(ergebnis):
        geladen, hinweise, befunde = ergebnis
        state.dml, state.syntaxhinweise, state.befunde = geladen, hinweise, befunde
        state.gelaufen = [] #C1
        zeige_ergebnis()
        set_status(f"{titel}: {len(befunde)} Treffer")

    im_hintergrund(arbeit, danach, f"{titel} läuft...")


def starte_vergleich():
    """Vergleicht die 1. und die 2. DML inhaltlich."""
    pfade = aktive_pfade()
    if len(pfade) < 2:
        messagebox.showinfo("Zwei DMLs nötig",
                            "Für den Vergleich müssen beide DMLs ausgewählt sein.")
        return

    def arbeit():
        geladen, hinweise = lese_dmls(pfade)
        fs1, z1, _ = geladen["1.XML"]
        fs2, z2, _ = geladen["2.XML"]
        nur1, nur2 = unterschiede_logik(fs1, fs2, z1, z2)
        befunde = [_mache_befund("1.XML", "Nur in 1.XML", z, f, g) for z, f, g in nur1]
        befunde += [_mache_befund("2.XML", "Nur in 2.XML", z, f, g) for z, f, g in nur2]
        return geladen, hinweise, befunde

    def danach(ergebnis):
        geladen, hinweise, befunde = ergebnis
        state.dml, state.syntaxhinweise, state.befunde = geladen, hinweise, befunde
        state.gelaufen = []     # C1: beim Vergleich läuft keine Prüfung
        zeige_ergebnis()
        set_status(f"Vergleich: {len(befunde)} Unterschiede")

    im_hintergrund(arbeit, danach, "Vergleich läuft...")


# ---------------------------------------------------------------------------
# Ergebnisdarstellung
# ---------------------------------------------------------------------------

def zeige_ergebnis():
    """Baut Übersicht und Tabelle nach einem Lauf neu auf."""
    baue_uebersicht()
    fuelle_tabelle()


def baue_uebersicht():
    """Zeigt je Prüfung eine Kachel mit der Trefferzahl, grün bei null Befunden."""
    for kind in uebersicht.winfo_children():
        kind.destroy()

    if not state.befunde and not state.syntaxhinweise:
        ttk.Label(uebersicht, text="Noch kein Lauf durchgeführt.",
                  foreground="#777777").grid(row=0, column=0, columnspan=4,
                                             sticky="w", padx=4, pady=4)
        return

    # Syntaxhinweise zuerst, sie betreffen die ganze Datei
    for quelle, meldungen in state.syntaxhinweise.items():
        _kachel(f"Syntax {quelle}", len(meldungen),
                lambda q=quelle: zeige_syntaxdetails(q))

    gezaehlt = {}
    for b in state.befunde:
        gezaehlt[b["pruefung"]] = gezaehlt.get(b["pruefung"], 0) + 1

    # Auch Prüfungen ohne Treffer anzeigen - "0 Befunde" ist die eigentliche Aussage
    gelaufen = state.gelaufen
    for titel in gelaufen:
        _kachel(titel, gezaehlt.get(titel, 0), lambda t=titel: setze_filter(t))

    for titel in sorted(gezaehlt):
        if titel not in gelaufen:
            _kachel(titel, gezaehlt[titel], lambda t=titel: setze_filter(t))


def _kachel(titel, anzahl, befehl):
    """Eine anklickbare Kachel der Übersichtsleiste.

    Die Kacheln werden in ein Raster gesetzt und brechen nach
    KACHELN_PRO_ZEILE Stück um, damit sie nicht aus dem Fenster laufen.
    """
    position = len(uebersicht.winfo_children())
    farbe = "#1B7F3B" if anzahl == 0 else "#B3261E"

    rahmen = ttk.Frame(uebersicht, padding=(10, 3), relief="solid", borderwidth=1)
    rahmen.grid(row=position // KACHELN_PRO_ZEILE,
                column=position % KACHELN_PRO_ZEILE, padx=3, pady=2, sticky="ew")
    kopf = ttk.Label(rahmen, text=str(anzahl), foreground=farbe,
                     font=("Segoe UI", 12, "bold"), anchor="center")
    kopf.pack(fill="x")
    unten = ttk.Label(rahmen, text=titel, foreground="#444444",
                      font=("Segoe UI", 8), anchor="center")
    unten.pack(fill="x")

    for widget in (rahmen, kopf, unten):
        widget.bind("<Button-1>", lambda _e: befehl())
        widget.configure(cursor="hand2")


def setze_filter(text):
    """Setzt den Filter auf einen Prüfungsnamen (Klick auf eine Kachel)."""
    filter_var.set(text)
    fuelle_tabelle()


def zeilenwerte(befund):
    """Wandelt einen Befund in die Werte der Tabellenspalten um."""
    fsp = befund["fsp"]
    werte = []
    for schluessel, _, _, _ in SPALTEN:
        if schluessel == "quelle":
            werte.append(befund["quelle"])
        elif schluessel == "zeile":
            werte.append(befund["zeile"] if befund["zeile"] else "")
        elif schluessel == "pruefung":
            werte.append(befund["pruefung"])
        elif schluessel == "befund":
            werte.append(befund["befund"])
        else:
            werte.append(sichtbar(str(fsp[FELD_INDEX[schluessel]])))
    return werte


def sichtbare_befunde():
    """Liefert die Befunde, die dem aktuellen Filter entsprechen."""
    text = filter_var.get().strip().lower()
    if not text:
        return list(state.befunde)
    return [b for b in state.befunde
            if any(text in str(w).lower() for w in zeilenwerte(b))]


def fuelle_tabelle(*_):
    """Leert die Tabelle und schreibt die gefilterten Befunde hinein."""
    tabelle.delete(*tabelle.get_children())
    for i, befund in enumerate(sichtbare_befunde()):
        tabelle.insert("", "end", values=zeilenwerte(befund),
                       tags=("gerade" if i % 2 == 0 else "ungerade",))
    treffer_label.configure(
        text=f"{len(tabelle.get_children())} von {len(state.befunde)} Befunden")


def sortiere_nach(spalte, umgekehrt):
    """Sortiert die Tabelle nach einer Spalte, Zahlen numerisch."""
    daten = [(tabelle.set(k, spalte), k) for k in tabelle.get_children("")]

    def schluessel(paar):
        wert = paar[0]
        try:
            return (0, float(wert))
        except ValueError:
            return (1, wert.lower())

    daten.sort(key=schluessel, reverse=umgekehrt)
    for index, (_, k) in enumerate(daten):
        tabelle.move(k, "", index)
        tabelle.item(k, tags=("gerade" if index % 2 == 0 else "ungerade",))
    tabelle.heading(spalte, command=lambda: sortiere_nach(spalte, not umgekehrt))


def aktualisiere_spalten():
    """Blendet Spalten gemäß dem Menü 'Ansicht' ein und aus."""
    sichtbar_spalten = [s for s, _, _, _ in SPALTEN if spalten_vars[s].get()]
    tabelle.configure(displaycolumns=sichtbar_spalten or ["befund"])


def kopiere_auswahl(_event=None):
    """Kopiert die markierten Zeilen tabulatorgetrennt in die Zwischenablage."""
    auswahl = tabelle.selection()
    if not auswahl:
        return
    sichtbar_spalten = [s for s, _, _, _ in SPALTEN if spalten_vars[s].get()]
    zeilen = ["\t".join(str(tabelle.set(k, s)) for s in sichtbar_spalten) for k in auswahl]
    root.clipboard_clear()
    root.clipboard_append("\n".join(zeilen))
    set_status(f"{len(auswahl)} Zeile(n) kopiert")

def markiere_alle(_event=None):
    """Markiert alle Zeilen der Ergebnistabelle."""
    eintraege = tabelle.get_children()
    if eintraege:
        tabelle.selection_set(*eintraege)
    return "break"

def leere_ergebnis():
    """Setzt Tabelle, Übersicht und Filter zurück."""
    state.befunde, state.syntaxhinweise = [], {}
    state.gelaufen = []
    filter_var.set("")
    zeige_ergebnis()
    set_status("Bereit.")


# ---------------------------------------------------------------------------
# Export und Zusatzfenster
# ---------------------------------------------------------------------------

def exportiere_csv(_event=None):
    """Exportiert die aktuell sichtbaren Zeilen als CSV."""
    befunde = sichtbare_befunde()
    if not befunde:
        messagebox.showinfo("Nichts zu exportieren", "Die Tabelle enthält keine Zeilen.")
        return

    pfad = filedialog.asksaveasfilename(
        defaultextension=".csv", filetypes=[("CSV-Dateien", "*.csv")],
        initialfile=f"DML_Befunde_{datetime.now():%Y-%m-%d_%H_%M_%S}",
        title="Ergebnis speichern")
    if not pfad:
        return

    try:
        with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
            schreiber = csv_module.writer(f, delimiter=";")
            schreiber.writerow([ueberschrift for _, ueberschrift, _, _ in SPALTEN])
            for befund in befunde:
                schreiber.writerow(zeilenwerte(befund))
        set_status(f"{len(befunde)} Zeilen gespeichert: {os.path.basename(pfad)}")
    except Exception as fehler:                      # noqa: BLE001
        logger.warning("CSV-Export fehlgeschlagen", exc_info=True)
        messagebox.showerror("Export fehlgeschlagen", str(fehler))


def zeige_textfenster(titel, inhalt):
    """Öffnet ein scrollbares Fenster mit einem längeren Text."""
    fenster = tk.Toplevel(root)
    fenster.title(titel)
    fenster.geometry("900x500")
    feld = ScrolledText(fenster, wrap="word", font=("Consolas", 9))
    feld.pack(fill="both", expand=True)
    feld.insert("end", inhalt)
    feld.configure(state="disabled")


def zeige_syntaxdetails(quelle=None):
    """Zeigt die Syntaxhinweise zu einer oder allen geladenen DMLs."""
    if not state.syntaxhinweise:
        pfade = aktive_pfade()
        if not pfade:
            messagebox.showinfo("Keine DML", "Bitte zuerst eine DML auswählen.")
            return
        state.syntaxhinweise = {q: validate_xml_collect_errors(p) for q, p in pfade.items()}

    teile = []
    for q, meldungen in state.syntaxhinweise.items():
        if quelle and q != quelle:
            continue
        teile.append(f"{q} - " + ("keine Syntaxfehler."
                                  if not meldungen else f"{len(meldungen)} Hinweise/Fehler:"))
        if meldungen:
            teile.append("\n".join(meldungen))
    zeige_textfenster("XML-Validierung", "\n\n".join(teile))


HILFETEXT = """DML-Auswertung {v}

DML auswählen
    Über die Schaltflächen rechts neben den Pfadfeldern, oder durch Auswahl
    aus dem Verlauf. Die zweite DML wird nur für den Vergleich benötigt.

Reiter "Prüfen"
    Haken setzen, welche Prüfungen laufen sollen, dann "Prüfung starten" (F5).
    Es laufen alle angehakten Prüfungen über alle geladenen DMLs.

Reiter "Suchen"
    Text-Suche durchsucht den Fehlertext, Hex-Suche den Hexwert. Mehrere
    Begriffe mit Komma trennen. Enter startet die Suche.

Reiter "Vergleichen"
    Zeigt alle Einträge, die nur in einer der beiden DMLs vorkommen.

Übersicht
    Je Prüfung eine Kachel mit der Trefferzahl, grün bei null Befunden.
    Ein Klick filtert die Tabelle auf diese Prüfung. Die Syntax-Kachel
    öffnet die Meldungen des XML-Parsers mit Zeile und Spalte.

Tabelle
    Klick auf eine Überschrift sortiert, erneuter Klick dreht die Richtung um.
    Das Filterfeld durchsucht alle sichtbaren Spalten. Welche Spalten
    angezeigt werden, steuert das Menü "Ansicht".
    Strg+C kopiert die markierten Zeilen.

Tastatur
    F5      Prüfung starten
    F1      diese Hilfe
    Strg+O  1. DML öffnen
    Strg+S  Ergebnis als CSV
    Strg+C  markierte Zeilen kopieren
    Entf    Ergebnis leeren

Anzeige unsichtbarer Zeichen
    \\n = Zeilenumbruch, \\t = Tabulator, <NBSP> = geschütztes Leerzeichen,
    <U+0085> = falsch kodiertes Sonderzeichen.

Der CSV-Export enthält genau die Zeilen, die gerade in der Tabelle stehen -
ein gesetzter Filter wirkt sich also aus.
""".format(v=VERSION)


def zeige_hilfe(_event=None):
    """Öffnet das Hilfefenster."""
    zeige_textfenster("Hilfe", HILFETEXT)


def zeige_ueber():
    """Zeigt Versionsinformationen."""
    messagebox.showinfo(
        "Über",
        f"DML-Auswertung Version {VERSION}\n\n"
        f"Prüflogik: dml_logik.py\n"
        f"Tests: test_dml_logik.py (pytest)\n"
        f"Änderungen: CHANGELOG_V6.0.md")


def set_status(text):
    """Aktualisiert die Statuszeile."""
    status_var.set(text)


def beim_beenden():
    """Speichert die Einstellungen und schließt das Fenster."""
    speichere_einstellungen()
    root.destroy()


# ---------------------------------------------------------------------------
# Oberfläche
# ---------------------------------------------------------------------------

def setze_dpi_bewusstsein():
    """Sorgt unter Windows für eine scharfe Darstellung auf HiDPI-Bildschirmen."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


setze_dpi_bewusstsein()

root = tk.Tk()
root.title(f"DML-Auswertung {VERSION}")
root.geometry(einstellungen.get("geometry", "1280x800"))
root.minsize(1000, 620)
root.protocol("WM_DELETE_WINDOW", beim_beenden)

stil = ttk.Style()
if "clam" in stil.theme_names():
    stil.theme_use("clam")          # einheitliches Aussehen auf allen Rechnern
stil.configure("Treeview", rowheight=22)
stil.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
stil.configure("Start.TButton", font=("Segoe UI", 10, "bold"), padding=8)

root.columnconfigure(0, weight=1)
root.rowconfigure(3, weight=1)

# --- Menüleiste ---
menue = tk.Menu(root)
datei_menue = tk.Menu(menue, tearoff=0)
datei_menue.add_command(label="1. DML öffnen...", accelerator="Strg+O",
                        command=lambda: waehle_datei(pfad_var1))
datei_menue.add_command(label="2. DML öffnen...",
                        command=lambda: waehle_datei(pfad_var2))
datei_menue.add_separator()
datei_menue.add_command(label="Ergebnis als CSV...", accelerator="Strg+S",
                        command=exportiere_csv)
datei_menue.add_separator()
datei_menue.add_command(label="Beenden", command=beim_beenden)
menue.add_cascade(label="Datei", menu=datei_menue)

ansicht_menue = tk.Menu(menue, tearoff=0)
spalten_vars = {}
for _s, _ueberschrift, _breite, _an in SPALTEN:
    spalten_vars[_s] = tk.BooleanVar(value=_an)
    ansicht_menue.add_checkbutton(label=_ueberschrift, variable=spalten_vars[_s],
                                  command=lambda: aktualisiere_spalten())
ansicht_menue.add_separator()
ansicht_menue.add_command(label="Ergebnis leeren", accelerator="Entf", command=leere_ergebnis)
menue.add_cascade(label="Ansicht", menu=ansicht_menue)

extras_menue = tk.Menu(menue, tearoff=0)
extras_menue.add_command(label="XML-Validierung anzeigen", command=zeige_syntaxdetails)
menue.add_cascade(label="Extras", menu=extras_menue)

hilfe_menue = tk.Menu(menue, tearoff=0)
hilfe_menue.add_command(label="Hilfe", accelerator="F1", command=zeige_hilfe)
hilfe_menue.add_command(label="Über", command=zeige_ueber)
menue.add_cascade(label="Hilfe", menu=hilfe_menue)
root.configure(menu=menue)

# --- Kopfbereich: Dateiauswahl ---
kopf = ttk.LabelFrame(root, text="DML-Dateien", padding=10)
kopf.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
kopf.columnconfigure(1, weight=1)

pfad_var1 = tk.StringVar()
pfad_var2 = tk.StringVar()

ttk.Label(kopf, text="1. DML").grid(row=0, column=0, sticky="w", padx=(0, 8))
pfad_feld1 = ttk.Combobox(kopf, textvariable=pfad_var1, values=zuletzt_geoeffnet[:8])
pfad_feld1.grid(row=0, column=1, sticky="ew")
ttk.Button(kopf, text="Durchsuchen...",
           command=lambda: waehle_datei(pfad_var1)).grid(row=0, column=2, padx=(8, 0))

ttk.Label(kopf, text="2. DML").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
pfad_feld2 = ttk.Combobox(kopf, textvariable=pfad_var2, values=zuletzt_geoeffnet[:8])
pfad_feld2.grid(row=1, column=1, sticky="ew", pady=(6, 0))
ttk.Button(kopf, text="Durchsuchen...",
           command=lambda: waehle_datei(pfad_var2)).grid(row=1, column=2, padx=(8, 0), pady=(6, 0))
ttk.Label(kopf, text="(nur für den Vergleich nötig)", foreground="#777777").grid(
    row=2, column=1, sticky="w", pady=(2, 0))

# --- Reiter mit den Aktionen ---
reiter = ttk.Notebook(root)
reiter.grid(row=1, column=0, sticky="ew", padx=10, pady=4)

# Reiter "Prüfen"
tab_pruefen = ttk.Frame(reiter, padding=10)
reiter.add(tab_pruefen, text="  Prüfen  ")
tab_pruefen.columnconfigure(0, weight=1)

pruef_liste = ttk.Frame(tab_pruefen)
pruef_liste.grid(row=0, column=0, sticky="ew")
for _i in range(2):
    pruef_liste.columnconfigure(_i, weight=1)

pruef_vars = {}
for _i, _p in enumerate(PRUEFUNGEN):
    pruef_vars[_p.schluessel] = tk.BooleanVar(value=_p.vorauswahl)
    ttk.Checkbutton(pruef_liste, text=_p.titel,
                    variable=pruef_vars[_p.schluessel]).grid(
        row=_i // 2, column=_i % 2, sticky="w", pady=1)


def setze_alle_pruefungen(wert):
    """Hakt alle Prüfungen an oder ab."""
    for var in pruef_vars.values():
        var.set(wert)


steuerung = ttk.Frame(tab_pruefen)
steuerung.grid(row=1, column=0, sticky="ew", pady=(10, 0))
ttk.Button(steuerung, text="Alle", width=8,
           command=lambda: setze_alle_pruefungen(True)).pack(side="left")
ttk.Button(steuerung, text="Keine", width=8,
           command=lambda: setze_alle_pruefungen(False)).pack(side="left", padx=(6, 0))
ttk.Button(steuerung, text="Prüfung starten  (F5)", style="Start.TButton",
           command=starte_pruefung).pack(side="right")

# Reiter "Suchen"
tab_suchen = ttk.Frame(reiter, padding=10)
reiter.add(tab_suchen, text="  Suchen  ")
tab_suchen.columnconfigure(1, weight=1)

such_modus = tk.StringVar(value="text")
modus_rahmen = ttk.Frame(tab_suchen)
modus_rahmen.grid(row=0, column=0, columnspan=3, sticky="w")
for _wert, _text in [("text", "Fehlertext"), ("hex", "Hexwert"),
                     ("sw", "Softwareversion ist genau '*'")]:
    ttk.Radiobutton(modus_rahmen, text=_text, value=_wert,
                    variable=such_modus).pack(side="left", padx=(0, 16))

ttk.Label(tab_suchen, text="Suchbegriffe").grid(row=1, column=0, sticky="w", pady=(10, 0))
such_feld = ttk.Entry(tab_suchen)
such_feld.grid(row=1, column=1, sticky="ew", padx=8, pady=(10, 0))
ttk.Button(tab_suchen, text="Suchen", style="Start.TButton",
           command=starte_suche).grid(row=1, column=2, pady=(10, 0))
ttk.Label(tab_suchen, text="Mehrere Begriffe mit Komma trennen. Enter startet die Suche.",
          foreground="#777777").grid(row=2, column=1, sticky="w", padx=8, pady=(2, 0))

# Reiter "Vergleichen"
tab_vergleich = ttk.Frame(reiter, padding=10)
reiter.add(tab_vergleich, text="  Vergleichen  ")
ttk.Label(tab_vergleich,
          text="Zeigt alle Fehlerspeicher-Einträge, die nur in einer der beiden "
               "DMLs vorkommen.\nUnterschiede entstehen durch geänderte Werte oder "
               "durch neue bzw. entfallene Einträge.").pack(anchor="w")
ttk.Button(tab_vergleich, text="Unterschiede suchen", style="Start.TButton",
           command=starte_vergleich).pack(anchor="w", pady=(12, 0))

# --- Übersichtsleiste ---
uebersicht_rahmen = ttk.LabelFrame(root, text="Übersicht", padding=(8, 4))
uebersicht_rahmen.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
uebersicht = ttk.Frame(uebersicht_rahmen)
uebersicht.pack(fill="x")
for _i in range(KACHELN_PRO_ZEILE):
    uebersicht.columnconfigure(_i, weight=1, uniform="kachel")

# --- Ergebnistabelle ---
ergebnis = ttk.LabelFrame(root, text="Befunde", padding=(8, 6))
ergebnis.grid(row=3, column=0, sticky="nsew", padx=10, pady=4)
ergebnis.columnconfigure(0, weight=1)
ergebnis.rowconfigure(1, weight=1)

filterzeile = ttk.Frame(ergebnis)
filterzeile.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
filterzeile.columnconfigure(1, weight=1)

ttk.Label(filterzeile, text="Filter").grid(row=0, column=0, padx=(0, 8))
filter_var = tk.StringVar()
filter_feld = ttk.Entry(filterzeile, textvariable=filter_var)
filter_feld.grid(row=0, column=1, sticky="ew")
ttk.Button(filterzeile, text="Zurücksetzen", width=14,
           command=lambda: (filter_var.set(""), fuelle_tabelle())).grid(row=0, column=2, padx=8)
treffer_label = ttk.Label(filterzeile, text="0 von 0 Befunden", foreground="#555555")
treffer_label.grid(row=0, column=3)

tabelle = ttk.Treeview(ergebnis, columns=[s for s, _, _, _ in SPALTEN],
                       show="headings", selectmode="extended")
tabelle.grid(row=1, column=0, sticky="nsew")

for _s, _ueberschrift, _breite, _an in SPALTEN:
    tabelle.heading(_s, text=_ueberschrift,
                    command=lambda sp=_s: sortiere_nach(sp, False))
    tabelle.column(_s, width=_breite, anchor="w",
                   stretch=(_s in ("text", "befund")))

tabelle.tag_configure("gerade", background="#FFFFFF")
tabelle.tag_configure("ungerade", background="#F4F6F8")

senkrecht = ttk.Scrollbar(ergebnis, orient="vertical", command=tabelle.yview)
senkrecht.grid(row=1, column=1, sticky="ns")
waagerecht = ttk.Scrollbar(ergebnis, orient="horizontal", command=tabelle.xview)
waagerecht.grid(row=2, column=0, sticky="ew")
tabelle.configure(yscrollcommand=senkrecht.set, xscrollcommand=waagerecht.set)

# --- Statuszeile ---
fusszeile = ttk.Frame(root, padding=(10, 4))
fusszeile.grid(row=4, column=0, sticky="ew")
fusszeile.columnconfigure(0, weight=1)

status_var = tk.StringVar(value="Bereit.")
ttk.Label(fusszeile, textvariable=status_var, anchor="w").grid(row=0, column=0, sticky="ew")
fortschritt = ttk.Progressbar(fusszeile, mode="indeterminate", length=160)
fortschritt.grid(row=0, column=1, sticky="e")

# --- Verknüpfungen ---
filter_var.trace_add("write", fuelle_tabelle)
such_feld.bind("<Return>", starte_suche)
root.bind("<F5>", lambda _e: starte_pruefung())
root.bind("<F1>", zeige_hilfe)
root.bind("<Control-o>", lambda _e: waehle_datei(pfad_var1))
root.bind("<Control-s>", exportiere_csv)
tabelle.bind("<Control-c>", kopiere_auswahl)
tabelle.bind("<Control-a>", markiere_alle)
tabelle.bind("<Delete>", lambda _e: leere_ergebnis())

aktualisiere_spalten()
zeige_ergebnis()

# C3: Hinweis, falls keine Logdatei angelegt werden konnte
# C3: Hinweis, falls keine Logdatei angelegt werden konnte
if LOG_FEHLER:
    set_status("Hinweis: Logdatei konnte nicht angelegt werden")
    root.after(500, lambda: messagebox.showwarning(
        "Logdatei nicht verfügbar",
        "Die Logdatei konnte nicht angelegt werden.\n\n" + LOG_FEHLER +
        "\n\nDas Tool funktioniert trotzdem, Fehler werden aber nicht protokolliert."))
try:
    root.mainloop()
except KeyboardInterrupt:
    beim_beenden()
