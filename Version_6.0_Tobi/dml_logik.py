# -*- coding: utf-8 -*-
"""Logikschicht des DML-Tools.

Enthält bewusst keinerlei GUI-Code (kein tkinter, kein globaler Zustand).
Alle Funktionen bekommen Listen herein und geben Listen zurück, damit sie
über test_dml_logik.py einzeln geprüft werden können.

Rückgabeformat aller Prüffunktionen: Liste von (zeile, fsp, befund)
  zeile  - Zeilennummer des <fehler>-Elements in der Quelldatei (oder None)
  fsp    - der Fehlerspeicher-Datensatz (Liste mit 11 Feldern)
  befund - Klartext, warum der Datensatz auffällig ist
"""

import re
import bisect
import xml.etree.ElementTree as ET
from collections import defaultdict


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Reihenfolge der Felder eines FSP-Datensatzes (Index 0..10).
# Die Namen entsprechen den XML-Attributen und bleiben deshalb ohne Umlaute.
FELDNAMEN = ["shortname", "variante", "status_v", "status_p", "teilenummer",
             "softwareversion", "produktschluessel", "ausstattung",
             "fehlervorbedingung", "text", "hexwert"]

NBSP = "\u00A0"          # geschütztes Leerzeichen
NEL = "\u0085"           # Next-Line, häufig aus falscher Kodierung
LS = "\u2028"            # Line Separator
PS = "\u2029"            # Paragraph Separator

# Zeichen, die innerhalb eines Werts nie vorkommen dürfen
STEUERZEICHEN = {"\n": "LF (Zeilenumbruch)",
                 "\r": "CR (Wagenrücklauf)",
                 "\t": "TAB",
                 NEL: "U+0085 (NEL / falsch kodiertes Sonderzeichen)",
                 LS: "U+2028 (Line Separator)",
                 PS: "U+2029 (Paragraph Separator)"}


# V6.1 Alle C1-Steuerzeichen außer NEL (NEL steht schon in STEUERZEICHEN).
# V6.1 Entstehen meist, wenn Windows-1252-Text (z. B. Gedankenstrich 0x96)
# V6.1 als ISO-8859-1 gespeichert wird.
C1_MUSTER = re.compile(r"[\x80-\x84\x86-\x9f]")

# Struktur des Hexwerts: 0x + genau 6 Hexziffern, Groß-/Kleinschreibung egal.
# Ob die Ziffern groß sind, prüft hexformat_pruef_logik() separat (A1).
HEX_STRUKTUR = re.compile(r"0x[0-9A-Fa-f]{6}")

# Erwartetes Format des Hexwerts, z.B. 0x000080
HEX_MUSTER = re.compile(r"^0x[0-9A-Fa-f]{6}$")

# Trennt an CRLF, CR und LF - bewusst nicht str.splitlines(),
# das würde auch bei U+0085 und U+2028 trennen.
ZEILENTRENNER = re.compile(r"\r\n|\r|\n")


# ---------------------------------------------------------------------------
# Dateizugriff
# ---------------------------------------------------------------------------

def ermittle_kodierung(pfad):
    """Liest die in der XML-Deklaration angegebene Kodierung aus."""
    try:
        with open(pfad, "rb") as f:
            kopf = f.read(200)
        treffer = re.search(rb'encoding\s*=\s*["\']([^"\']+)["\']', kopf)
        if treffer:
            return treffer.group(1).decode("ascii", errors="replace")
    except Exception:
        pass
    return "utf-8"


def lies_datei_text(pfad):
    """Liefert den Dateiinhalt als String, mit der deklarierten Kodierung."""
    kodierung = ermittle_kodierung(pfad)
    try:
        with open(pfad, "r", encoding=kodierung, errors="replace", newline="") as f:
            return f.read()
    except LookupError:
        with open(pfad, "r", encoding="utf-8", errors="replace", newline="") as f:
            return f.read()


def _zeilenanfaenge(text):
    """Byte-Offsets aller Zeilenanfänge, Basis für die Zeilennummern."""
    anfaenge = [0]
    for m in ZEILENTRENNER.finditer(text):
        anfaenge.append(m.end())
    return anfaenge


def _zeile_von(anfaenge, position):
    """Wandelt eine Zeichenposition in eine 1-basierte Zeilennummer um."""
    return bisect.bisect_right(anfaenge, position)


# ---------------------------------------------------------------------------
# XML einlesen
# ---------------------------------------------------------------------------

def extrahiere_rohelemente(pfad):
    """Liefert (rohtexte, zeilennummern) je <fehler>-Element aus der Quelldatei.

    Nötig, weil der XML-Parser Zeilenumbrüche in Attributen laut Standard
    durch ein Leerzeichen ersetzt - im geparsten Wert sind sie nicht mehr
    zu sehen.
    """
    try:
        text = lies_datei_text(pfad)
    except Exception:
        return [], []

    anfaenge = _zeilenanfaenge(text)
    rohtexte, zeilen = [], []
    for m in re.finditer(r"<fehler\b.*?</fehler>", text, re.S):
        rohtexte.append(m.group(0))
        zeilen.append(_zeile_von(anfaenge, m.start()))
    return rohtexte, zeilen


def _extract_fsp(sg, fehler):
    """Baut einen FSP-Datensatz aus Steuergerät- und Fehler-Element.

    Der Hexwert wird absichtlich nicht getrimmt - sonst verschwinden genau
    die Leerzeichen, nach denen die Umbruchprüfung sucht.
    """
    return [
        sg.attrib.get("shortname", ""),
        sg.attrib.get("variante", ""),
        fehler.attrib.get("status_v", ""),
        fehler.attrib.get("status_p", ""),
        fehler.attrib.get("teilenummer", ""),
        fehler.attrib.get("softwareversion", ""),
        fehler.attrib.get("produktschluessel", ""),
        fehler.attrib.get("ausstattung", ""),
        fehler.attrib.get("fehlervorbedingung", ""),
        fehler.attrib.get("text", ""),
        fehler.text if fehler.text is not None else ""
    ]


def lade_dml(pfad):
    """Liest eine DML ein.

    Rückgabe: (fehlerspeicher, zeilen, rohelemente, hinweise)
    Die drei Listen sind gleich lang und positionsgleich, sofern die Datei
    strukturell sauber ist. Weicht die Anzahl ab, steht ein Hinweis in
    'hinweise' und die Zeilennummern werden weggelassen.
    """
    hinweise = []

    try:
        from lxml import etree
        parser = etree.XMLParser(recover=True, huge_tree=True)
        with open(pfad, "rb") as f:
            wurzel = etree.parse(f, parser).getroot()
    except ImportError:
        wurzel = ET.parse(pfad).getroot()

    fehlerspeicher = []
    for sg in wurzel.iter("steuergeraet"):
        for fehler in sg.iter("fehler"):
            fehlerspeicher.append(_extract_fsp(sg, fehler))

    rohelemente, zeilen = extrahiere_rohelemente(pfad)

    if len(rohelemente) != len(fehlerspeicher):
        hinweise.append(
            f"Achtung: {len(rohelemente)} <fehler>-Elemente im Quelltext, aber "
            f"{len(fehlerspeicher)} eingelesen. Der Parser hat vermutlich "
            f"Elemente repariert oder übersprungen. Zeilennummern und die "
            f"Umbruchprüfung auf Quelltextebene entfallen für diese Datei.")
        rohelemente, zeilen = [], []

    return fehlerspeicher, zeilen, rohelemente, hinweise


# ---------------------------------------------------------------------------
# XML-Wohlgeformtheit prüfen (Syntaxebene)
# ---------------------------------------------------------------------------

def validate_xml_collect_errors(pfad):
    """Prüft die Datei auf XML-Syntaxfehler und verdächtige Zeichen."""
    errors = []

    # 1) Parser-Meldungen einsammeln
    try:
        from lxml import etree
        parser = etree.XMLParser(recover=True, huge_tree=True)
        with open(pfad, "rb") as f:
            etree.parse(f, parser)
        for e in parser.error_log:
            errors.append(f"Zeile {e.line}, Spalte {e.column}: {e.message}")
    except ImportError:
        try:
            ET.parse(pfad)
        except ET.ParseError as fatal:
            errors.append(f"[FATAL] {fatal}")
    except Exception as ex:
        errors.append(f"[FATAL] Datei konnte nicht gelesen werden: {ex}")

    # 2) Heuristiken auf Textebene
    unescaped_amp = re.compile(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)')
    suspicious_lt = re.compile(r'<(?=[^!?/A-Za-z_])')

    try:
        text = lies_datei_text(pfad)
        for i, line in enumerate(ZEILENTRENNER.split(text), start=1):
            for m in unescaped_amp.finditer(line):
                errors.append(f"Zeile {i}, Spalte {m.start() + 1}: Nicht maskiertes '&' gefunden")
            for m in suspicious_lt.finditer(line):
                errors.append(f"Zeile {i}, Spalte {m.start() + 1}: Verdächtiges '<' gefunden")
            if line.count('"') % 2 == 1:
                errors.append(f"Zeile {i}: Ungerade Anzahl '\"' -> Attributwert geht über "
                              f"das Zeilenende hinaus (Zeilenumbruch im Attribut)")
            for zeichen, klar in STEUERZEICHEN.items():
                if zeichen in ("\n", "\r"):
                    continue
                pos = line.find(zeichen)
                if pos >= 0:
                    errors.append(f"Zeile {i}, Spalte {pos + 1}: Steuerzeichen {klar} im Text")
    except Exception as ex:
        errors.append(f"[FATAL] Textprüfung fehlgeschlagen: {ex}")

    return list(dict.fromkeys(errors))


# ---------------------------------------------------------------------------
# Hilfsfunktionen der Prüfungen
# ---------------------------------------------------------------------------

def feldname(i):
    """Feldname zu einem Index des FSP-Datensatzes."""
    return FELDNAMEN[i] if i < len(FELDNAMEN) else f"Feld{i}"


def sichtbar(wert):
    """Stellt unsichtbare Zeichen lesbar dar, damit sie in der Ausgabe auffallen."""
    ersetzungen = {"\n": "\\n", "\r": "\\r", "\t": "\\t",
                   NBSP: "<NBSP>", NEL: "<U+0085>", LS: "<U+2028>", PS: "<U+2029>"}
    for zeichen, klar in ersetzungen.items():
        wert = wert.replace(zeichen, klar)
    return wert


def _z(zeilen, index):
    """Zeilennummer zum Datensatz-Index, oder None wenn nicht bekannt."""
    return zeilen[index] if zeilen and index < len(zeilen) else None


# ---------------------------------------------------------------------------
# Prüfungen
# ---------------------------------------------------------------------------

def sw_suche_logik(fehlerspeicher, zeilen=None):
    """Alle DTCs, deren Softwareversion genau '*' ist."""
    return [(_z(zeilen, i), fsp, "softwareversion == '*'")
            for i, fsp in enumerate(fehlerspeicher) if fsp[5] == "*"]


def na_pruef_logik(fehlerspeicher, zeilen=None):
    """NA-Prüfung: geschütztes Leerzeichen (NBSP) in einem beliebigen Wert."""
    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        gruende = [f"NBSP in '{feldname(j)}'" for j, e in enumerate(fsp)
                   if isinstance(e, str) and NBSP in e]
        if gruende:
            treffer.append((_z(zeilen, i), fsp, "; ".join(gruende)))
    return treffer


def wildcard_pruef_logik(fehlerspeicher, zeilen=None):
    """xx-Prüfung: Wildcard 'xx' in einem beliebigen Wert."""
    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        gruende = [f"'xx' in '{feldname(j)}' -> {e}" for j, e in enumerate(fsp)
                   if isinstance(e, str) and "xx" in e]
        if gruende:
            treffer.append((_z(zeilen, i), fsp, "; ".join(gruende)))
    return treffer


def x_pruef_logik(fehlerspeicher, zeilen=None):
    """x-TN/SW: 'x' in Teilenummer (Index 4) oder Softwareversion (Index 5)."""
    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        gruende = []
        if "x" in fsp[4]:
            gruende.append(f"'x' in teilenummer -> {fsp[4]}")
        if "x" in fsp[5]:
            gruende.append(f"'x' in softwareversion -> {fsp[5]}")
        if gruende:
            treffer.append((_z(zeilen, i), fsp, "; ".join(gruende)))
    return treffer


def zeilenumbruch_pruef_logik(fehlerspeicher, rohelemente=None, zeilen=None):
    """Umbruch-Suche, dreistufig:
    Rand-Leerzeichen, Steuerzeichen im Wert, echter Umbruch im Quelltext.
    """
    rohelemente = rohelemente or []
    passend = len(rohelemente) == len(fehlerspeicher)

    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        gruende = []

        for j, e in enumerate(fsp):
            if not isinstance(e, str) or e == "":
                continue
            if e[0] == " ":
                gruende.append(f"Leerzeichen am Anfang von '{feldname(j)}'")
            if e[-1] == " ":
                gruende.append(f"Leerzeichen am Ende von '{feldname(j)}'")
            for zeichen, klar in STEUERZEICHEN.items():
                if zeichen in e:
                    gruende.append(f"{klar} in '{feldname(j)}'")
            for z in sorted(set(C1_MUSTER.findall(e))):     #v6.1
                gruende.append(f"U+{ord(z):04X} (C1-Steuerzeichen / falsch "
                               f"kodiertes Sonderzeichen) in '{feldname(j)}'")

        if passend and ("\n" in rohelemente[i] or "\r" in rohelemente[i]):
            gruende.append("echter Zeilenumbruch im Quelltext des <fehler>-Elements")

        if gruende:
            treffer.append((_z(zeilen, i), fsp, "; ".join(dict.fromkeys(gruende))))
    return treffer


def hexformat_pruef_logik(fehlerspeicher, zeilen=None):
    """Prüft den Hexwert: erst die Struktur 0xHHHHHH, dann Großbuchstaben,
    dann Rand-Leerzeichen. Pro Datensatz wird höchstens ein Befund gemeldet."""
    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        roh = fsp[10]
        wert = roh.strip()
        if not HEX_STRUKTUR.fullmatch(wert):
            treffer.append((_z(zeilen, i), fsp,
                            f"Hexwert entspricht nicht 0xHHHHHH -> '{sichtbar(roh)}'"))
        elif wert[2:] != wert[2:].upper():
            treffer.append((_z(zeilen, i), fsp,
                            f"Hexwert enthält Kleinbuchstaben -> '{wert}' "
                            f"(erwartet '0x{wert[2:].upper()}')"))
        elif roh != wert:
            treffer.append((_z(zeilen, i), fsp,
                            "Hexwert enthält führende/abschließende Leerzeichen"))
    return treffer


def attribut_pruef_logik(fehlerspeicher, zeilen=None, pflichtfelder=(0, 1, 2, 3, 9, 10)):
    """Meldet Datensätze, bei denen ein Pflichtfeld leer ist."""
    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        leer = [feldname(j) for j in pflichtfelder if not str(fsp[j]).strip()]
        if leer:
            treffer.append((_z(zeilen, i), fsp, "Pflichtfeld leer: " + ", ".join(leer)))
    return treffer


def pruef_dopplung_logik(fehlerspeicher, zeilen=None):
    """Findet mehrfach identisch vorhandene Datensätze und nennt alle Fundzeilen."""
    positionen = defaultdict(list)
    for i, fsp in enumerate(fehlerspeicher):
        positionen[tuple(fsp)].append(i)

    treffer = []
    for schluessel, idx in positionen.items():
        if len(idx) > 1:
            fundzeilen = [z for z in (_z(zeilen, i) for i in idx) if z is not None]
            grund = f"{len(idx)}x identisch in der DML enthalten"
            if fundzeilen:
                grund += " (Zeilen " + ", ".join(str(z) for z in fundzeilen) + ")"
            treffer.append((_z(zeilen, idx[0]), list(schluessel), grund))
    return treffer


def inhaltssuche_logik(fehlerspeicher, begriffe, zeilen=None):
    """Alle DTCs, deren Fehlertext einen der Suchbegriffe enthält."""
    treffer = []
    for i, fsp in enumerate(fehlerspeicher):
        fehlertext = fsp[9].lower()
        for begriff in begriffe:
            if begriff in fehlertext:
                treffer.append((_z(zeilen, i), fsp, f"Suchbegriff '{begriff}' im Fehlertext"))
                break
    return treffer


def hexwert_suche_logik(fehlerspeicher, suchhex, zeilen=None):
    """Alle DTCs mit einem der gesuchten Hexwerte."""
    return [(_z(zeilen, i), fsp, f"Hexwert {fsp[10].strip()}")
            for i, fsp in enumerate(fehlerspeicher)
            if (fsp[10] or "").strip().lower() in suchhex]


def unterschiede_logik(fehlerspeicher1, fehlerspeicher2, zeilen1=None, zeilen2=None):
    """Vergleicht zwei DMLs und liefert die jeweils nur einseitig vorhandenen DTCs."""
    def _normalize(row, target_len=11):
        r = [("" if v is None else str(v)) for v in row]
        if len(r) < target_len:
            r += [""] * (target_len - len(r))
        return r[:target_len]

    def _index(fehlerspeicher):
        karte = {}
        for i, fsp in enumerate(fehlerspeicher):
            karte.setdefault(tuple(_normalize(fsp)), i)
        return karte

    karte1, karte2 = _index(fehlerspeicher1), _index(fehlerspeicher2)

    nur1 = [(_z(zeilen1, karte1[s]), list(s), "nur in 1.XML enthalten")
            for s in karte1 if s not in karte2]
    nur2 = [(_z(zeilen2, karte2[s]), list(s), "nur in 2.XML enthalten")
            for s in karte2 if s not in karte1]
    return nur1, nur2
