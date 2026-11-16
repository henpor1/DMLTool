# -*- coding: utf-8 -*-
"""Tests für dml_logik.py.

Ausführen:   pytest -v
Voraussetzung: pytest (pip install pytest)

Jeder Test baut sich eine kleine DML mit genau einem eingebauten Fehler und
prüft, dass die zuständige Funktion ihn findet - und dass eine saubere DML
keinen Fehlalarm auslöst. Die Tests zu den Punkten "regression" decken die
drei Prüfungen ab, die in V5.1 nicht mehr angeschlagen haben.
"""

import pytest

import dml_logik as logik


# ---------------------------------------------------------------------------
# Hilfsmittel zum Bauen von Test-DMLs
# ---------------------------------------------------------------------------

KOPF = '<?xml version="1.0" encoding="ISO-8859-1"?>\r\n<steuergeraete>\r\n'
FUSS = '</steuergeraete>\r\n'


def fehlerzeile(text="Testtext", hexwert="0x000080", teilenummer="",
                softwareversion="*", status_v="-1", status_p="0",
                produktschluessel="F7*", ausstattung="", fehlervorbedingung=""):
    """Baut ein einzelnes <fehler>-Element als Quelltext."""
    return (f'          <fehler status_v="{status_v}" status_p="{status_p}" '
            f'teilenummer="{teilenummer}" softwareversion="{softwareversion}" '
            f'produktschluessel="{produktschluessel}" ausstattung="{ausstattung}" '
            f'fehlervorbedingung="{fehlervorbedingung}" text="{text}">{hexwert}</fehler>\r\n')


def schreibe_dml(tmp_path, *fehlerzeilen, shortname="SG_Test", variante="EV_*",
                 dateiname="test.xml"):
    """Schreibt eine vollständige Test-DML und gibt den Pfad zurück."""
    inhalt = (KOPF
              + f'     <steuergeraet shortname="{shortname}" variante="{variante}">\r\n'
              + "".join(fehlerzeilen)
              + '     </steuergeraet>\r\n'
              + FUSS)
    pfad = tmp_path / dateiname
    pfad.write_text(inhalt, encoding="ISO-8859-1", newline="")
    return str(pfad)


def lade(pfad):
    """Kurzform für lade_dml() ohne die Hinweisliste."""
    fehlerspeicher, zeilen, roh, _ = logik.lade_dml(pfad)
    return fehlerspeicher, zeilen, roh


def gruende(treffer):
    """Nur die Befundtexte aus dem Ergebnis."""
    return [t[2] for t in treffer]


def zeilen_von(treffer):
    """Nur die Zeilennummern aus dem Ergebnis."""
    return [t[0] for t in treffer]


# ---------------------------------------------------------------------------
# Einlesen und Zeilennummern
# ---------------------------------------------------------------------------

def test_lade_dml_liest_alle_felder(tmp_path):
    pfad = schreibe_dml(tmp_path, fehlerzeile(text="Hallo", teilenummer="4KD035285"))
    fehlerspeicher, zeilen, roh = lade(pfad)

    assert len(fehlerspeicher) == 1
    fsp = fehlerspeicher[0]
    assert len(fsp) == len(logik.FELDNAMEN)
    assert fsp[0] == "SG_Test"
    assert fsp[4] == "4KD035285"
    assert fsp[9] == "Hallo"
    assert fsp[10] == "0x000080"


def test_zeilennummern_stimmen(tmp_path):
    """Kopf = Zeile 1, <steuergeraete> = 2, <steuergeraet> = 3, Fehler ab 4."""
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(hexwert="0x000001"),
                        fehlerzeile(hexwert="0x000002"),
                        fehlerzeile(hexwert="0x000003"))
    _, zeilen, _ = lade(pfad)
    assert zeilen == [4, 5, 6]


def test_zeilennummer_landet_im_befund(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(hexwert="0x000001"),
                        fehlerzeile(hexwert="0xKAPUTT"))
    fehlerspeicher, zeilen, _ = lade(pfad)
    treffer = logik.hexformat_pruef_logik(fehlerspeicher, zeilen)

    assert len(treffer) == 1
    assert zeilen_von(treffer) == [5]


def test_ohne_zeilenliste_kommt_none(tmp_path):
    """Die Prüfungen müssen auch ohne Zeilennummern funktionieren."""
    pfad = schreibe_dml(tmp_path, fehlerzeile(hexwert="0xKAPUTT"))
    fehlerspeicher, _, _ = lade(pfad)
    treffer = logik.hexformat_pruef_logik(fehlerspeicher)
    assert zeilen_von(treffer) == [None]


# ---------------------------------------------------------------------------
# Regression: die drei in V5.1 defekten Prüfungen
# ---------------------------------------------------------------------------

def test_regression_umbruch_im_attribut(tmp_path):
    """V5.1 fand das nicht, weil der Parser den Umbruch zu einem Leerzeichen macht."""
    kaputt = ('          <fehler status_v="-1" status_p="0" teilenummer="" '
              'softwareversion="*" produktschluessel="F7*" ausstattung="" '
              'fehlervorbedingung="" text="SFD Role act\nive    ">0x000080</fehler>\r\n')
    pfad = schreibe_dml(tmp_path, kaputt, fehlerzeile(text="sauber"))
    fehlerspeicher, zeilen, roh = lade(pfad)

    treffer = logik.zeilenumbruch_pruef_logik(fehlerspeicher, roh, zeilen)

    assert len(treffer) == 1
    assert zeilen_von(treffer) == [4]
    assert "Zeilenumbruch im Quelltext" in gruende(treffer)[0]
    assert "Leerzeichen am Ende" in gruende(treffer)[0]


def test_regression_xx_wildcard(tmp_path):
    """V5.1 verglich auf Gleichheit mit 'x', damit war 'xx' nie zu finden."""
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(teilenummer="4KD03528xx"),
                        fehlerzeile(teilenummer="4KD035285"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.wildcard_pruef_logik(fehlerspeicher, zeilen)

    assert len(treffer) == 1
    assert zeilen_von(treffer) == [4]
    assert "teilenummer" in gruende(treffer)[0]


def test_regression_x_in_teilenummer_und_sw(tmp_path):
    """V5.1 fand nur Felder, die aus genau einem 'x' bestanden."""
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(teilenummer="4KD03528x"),
                        fehlerzeile(softwareversion="0x45"),
                        fehlerzeile(teilenummer="4KD035285", softwareversion="0045"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.x_pruef_logik(fehlerspeicher, zeilen)

    assert zeilen_von(treffer) == [4, 5]
    assert "teilenummer" in gruende(treffer)[0]
    assert "softwareversion" in gruende(treffer)[1]


# ---------------------------------------------------------------------------
# Weitere Prüfungen
# ---------------------------------------------------------------------------

def test_na_pruefung_findet_nbsp(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text=f"Text{logik.NBSP}mit NBSP"),
                        fehlerzeile(text="Text mit normalem Leerzeichen"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.na_pruef_logik(fehlerspeicher, zeilen)

    assert len(treffer) == 1
    assert zeilen_von(treffer) == [4]
    assert "NBSP in 'text'" in gruende(treffer)[0]


def test_umbruchpruefung_findet_randleerzeichen(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text="Text mit Leerzeichen am Ende "),
                        fehlerzeile(text=" Leerzeichen am Anfang"),
                        fehlerzeile(text="sauber"))
    fehlerspeicher, zeilen, roh = lade(pfad)

    treffer = logik.zeilenumbruch_pruef_logik(fehlerspeicher, roh, zeilen)

    assert zeilen_von(treffer) == [4, 5]
    assert "Leerzeichen am Ende" in gruende(treffer)[0]
    assert "Leerzeichen am Anfang" in gruende(treffer)[1]


def test_umbruchpruefung_findet_steuerzeichen(tmp_path):
    pfad = schreibe_dml(tmp_path, fehlerzeile(text=f"Abgeschnittener Text{logik.NEL}"))
    fehlerspeicher, zeilen, roh = lade(pfad)

    treffer = logik.zeilenumbruch_pruef_logik(fehlerspeicher, roh, zeilen)

    assert len(treffer) == 1
    assert "U+0085" in gruende(treffer)[0]
    
@pytest.mark.parametrize("zeichen", ["\x96", "\x80", "\x9f"])
def test_umbruchpruefung_findet_alle_c1_steuerzeichen(tmp_path, zeichen):
    """0x80-0x9F sind in ISO-8859-1 Steuerzeichen (z. B. 0x96 aus Windows-1252)."""
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text=f"Emergency call {zeichen} function"),
                        fehlerzeile(text="sauber"))
    fehlerspeicher, zeilen, roh = lade(pfad)

    treffer = logik.zeilenumbruch_pruef_logik(fehlerspeicher, roh, zeilen)

    assert zeilen_von(treffer) == [4]

@pytest.mark.parametrize("hexwert, erwartet_treffer", [
    ("0x000080", False),   # korrekt
    ("0xE0005", True),     # eine Stelle zu wenig
    ("0x0000800", True),   # eine Stelle zu viel
    ("0xZZZZZZ", True),    # keine Hexziffern
    ("000080", True),      # Präfix fehlt
])
def test_hexformat(tmp_path, hexwert, erwartet_treffer):
    pfad = schreibe_dml(tmp_path, fehlerzeile(hexwert=hexwert))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.hexformat_pruef_logik(fehlerspeicher, zeilen)

    assert bool(treffer) is erwartet_treffer

@pytest.mark.parametrize("hexwert", ["0x00e017", "0xabcdef", "0x0A0b0C"]) #V6.2
def test_hexformat_meldet_kleinbuchstaben(tmp_path, hexwert):
    """Hexziffern müssen Großbuchstaben sein, sonst eigener Befund (A1)."""
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(hexwert=hexwert),
                        fehlerzeile(hexwert="0x00E017"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.hexformat_pruef_logik(fehlerspeicher, zeilen)

    assert zeilen_von(treffer) == [4]
    assert "Kleinbuchstaben" in gruende(treffer)[0]


def test_dopplung_nennt_alle_fundzeilen(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text="Doppelt", hexwert="0x000005"),
                        fehlerzeile(text="Einmalig", hexwert="0x000006"),
                        fehlerzeile(text="Doppelt", hexwert="0x000005"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.pruef_dopplung_logik(fehlerspeicher, zeilen)

    assert len(treffer) == 1
    assert zeilen_von(treffer) == [4]
    assert "2x identisch" in gruende(treffer)[0]
    assert "Zeilen 4, 6" in gruende(treffer)[0]


def test_pflichtfelder(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text=""),          # Text fehlt
                        fehlerzeile(text="vorhanden"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.attribut_pruef_logik(fehlerspeicher, zeilen)

    assert zeilen_von(treffer) == [4]
    assert "text" in gruende(treffer)[0]


def test_sw_suche_nur_bei_exaktem_stern(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(softwareversion="*"),
                        fehlerzeile(softwareversion="X45*/045*"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.sw_suche_logik(fehlerspeicher, zeilen)

    assert zeilen_von(treffer) == [4]


def test_inhaltssuche_ist_case_insensitive(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text="SFD Role active"),
                        fehlerzeile(text="Motor Gangposition"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.inhaltssuche_logik(fehlerspeicher, ["sfd"], zeilen)

    assert zeilen_von(treffer) == [4]


def test_hexwert_suche(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(hexwert="0x000080"),
                        fehlerzeile(hexwert="0xE00017"))
    fehlerspeicher, zeilen, _ = lade(pfad)

    treffer = logik.hexwert_suche_logik(fehlerspeicher, ["0xe00017"], zeilen)

    assert zeilen_von(treffer) == [5]


def test_unterschiede_beidseitig(tmp_path):
    pfad1 = schreibe_dml(tmp_path, fehlerzeile(text="gemeinsam"),
                         fehlerzeile(text="nur in 1"), dateiname="dml_a.xml")
    pfad2 = schreibe_dml(tmp_path, fehlerzeile(text="gemeinsam"),
                         fehlerzeile(text="nur in 2"), dateiname="dml_b.xml")
    fs1, z1, _ = lade(pfad1)
    fs2, z2, _ = lade(pfad2)

    nur1, nur2 = logik.unterschiede_logik(fs1, fs2, z1, z2)

    assert [t[1][9] for t in nur1] == ["nur in 1"]
    assert [t[1][9] for t in nur2] == ["nur in 2"]
    assert zeilen_von(nur1) == [5]


# ---------------------------------------------------------------------------
# Keine Fehlalarme auf einer sauberen DML
# ---------------------------------------------------------------------------

def test_saubere_dml_liefert_keine_befunde(tmp_path):
    pfad = schreibe_dml(tmp_path,
                        fehlerzeile(text="Alles in Ordnung", hexwert="0x000080"),
                        fehlerzeile(text="Zweiter Eintrag", hexwert="0x000081"))
    fehlerspeicher, zeilen, roh = lade(pfad)

    assert logik.na_pruef_logik(fehlerspeicher, zeilen) == []
    assert logik.wildcard_pruef_logik(fehlerspeicher, zeilen) == []
    assert logik.x_pruef_logik(fehlerspeicher, zeilen) == []
    assert logik.zeilenumbruch_pruef_logik(fehlerspeicher, roh, zeilen) == []
    assert logik.hexformat_pruef_logik(fehlerspeicher, zeilen) == []
    assert logik.pruef_dopplung_logik(fehlerspeicher, zeilen) == []


# ---------------------------------------------------------------------------
# Syntaxvalidierung
# ---------------------------------------------------------------------------

def test_validierung_meldet_umbruch_im_attribut(tmp_path):
    kaputt = ('          <fehler status_v="-1" status_p="0" teilenummer="" '
              'softwareversion="*" produktschluessel="F7*" ausstattung="" '
              'fehlervorbedingung="" text="mit\nUmbruch">0x000080</fehler>\r\n')
    pfad = schreibe_dml(tmp_path, kaputt)

    meldungen = logik.validate_xml_collect_errors(pfad)

    assert any("Zeile 4" in m for m in meldungen)


def test_validierung_meldet_unmaskiertes_und(tmp_path):
    pfad = schreibe_dml(tmp_path, fehlerzeile(text="Klima & Heizung"))

    meldungen = logik.validate_xml_collect_errors(pfad)

    assert any("&" in m for m in meldungen)


def test_validierung_ist_still_bei_sauberer_datei(tmp_path):
    pfad = schreibe_dml(tmp_path, fehlerzeile(text="sauber"))
    assert logik.validate_xml_collect_errors(pfad) == []


def test_kodierung_wird_aus_deklaration_gelesen(tmp_path):
    pfad = schreibe_dml(tmp_path, fehlerzeile(text="Funktionseinschränkung"))

    assert logik.ermittle_kodierung(pfad).lower() in ("iso-8859-1", "latin-1")

    fehlerspeicher, _, _ = lade(pfad)
    assert fehlerspeicher[0][9] == "Funktionseinschränkung"
