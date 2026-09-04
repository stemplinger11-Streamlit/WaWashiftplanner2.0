"""
Tests des Nutzer-Imports.

    python -m pytest test_core_import.py -v
"""
import pytest

from core_import import (
    BEISPIEL_CSV,
    erkenne_trennzeichen,
    ist_gueltige_email,
    lies_nutzerliste,
    normalisiere_spalte,
)


# ===== SPALTENERKENNUNG =====

@pytest.mark.parametrize("bezeichnung,erwartet", [
    ("Name", "name"), ("NAME", "name"), (" name ", "name"),
    ("E-Mail", "email"), ("email", "email"), ("E-Mail-Adresse", "email"),
    ("Telefon", "phone"), ("Handy", "phone"), ("Mobil", "phone"),
    ("Beitrag", None), ("", None), (None, None),
])
def test_spaltenerkennung(bezeichnung, erwartet):
    assert normalisiere_spalte(bezeichnung) == erwartet


def test_unterstrich_wird_als_leerzeichen_gelesen():
    assert normalisiere_spalte("e_mail") == "email"


# ===== TRENNZEICHEN =====

def test_semikolon_erkannt():
    assert erkenne_trennzeichen("Name;E-Mail;Telefon\na;b;c") == ";"


def test_komma_erkannt():
    assert erkenne_trennzeichen("Name,E-Mail,Telefon\na,b,c") == ","


# ===== E-MAIL-PRUEFUNG =====

@pytest.mark.parametrize("wert", [
    "a@b.de", "vorname.nachname@wasserwacht-muenchen.de", "x@y.co.uk"])
def test_gueltige_adressen(wert):
    assert ist_gueltige_email(wert)


@pytest.mark.parametrize("wert", [
    "", None, "keine-adresse", "a@b", "a@.de", "a b@c.de", "@b.de"])
def test_ungueltige_adressen(wert):
    assert not ist_gueltige_email(wert)


# ===== EINLESEN =====

def test_beispieldatei_wird_gelesen():
    eintraege, fehler = lies_nutzerliste(BEISPIEL_CSV)
    assert len(eintraege) == 2
    assert not fehler
    assert eintraege[0] == {'name': 'Anna Beispiel',
                            'email': 'anna@example.de',
                            'phone': '0172 1234567'}


def test_fehlendes_telefon_ist_erlaubt():
    eintraege, _ = lies_nutzerliste(BEISPIEL_CSV)
    assert eintraege[1]['phone'] == ''


def test_komma_getrennt():
    eintraege, fehler = lies_nutzerliste(
        "Name,E-Mail\nAnna,anna@example.de\n")
    assert len(eintraege) == 1 and not fehler


def test_ohne_telefonspalte():
    eintraege, fehler = lies_nutzerliste("Name;E-Mail\nAnna;anna@example.de\n")
    assert eintraege[0]['phone'] == ''
    assert not fehler


def test_adresse_wird_kleingeschrieben():
    """Sonst waeren Anna@… und anna@… zwei Konten."""
    eintraege, _ = lies_nutzerliste("Name;E-Mail\nAnna;Anna@Example.DE\n")
    assert eintraege[0]['email'] == 'anna@example.de'


def test_bom_am_dateianfang():
    """Excel schreibt gern ein BOM voran."""
    eintraege, fehler = lies_nutzerliste(
        "﻿Name;E-Mail\nAnna;anna@example.de\n")
    assert len(eintraege) == 1, fehler


def test_leerzeilen_werden_uebersprungen():
    eintraege, fehler = lies_nutzerliste(
        "Name;E-Mail\nAnna;anna@example.de\n\n\nBert;bert@example.de\n")
    assert len(eintraege) == 2 and not fehler


def test_spalten_in_anderer_reihenfolge():
    eintraege, _ = lies_nutzerliste(
        "Telefon;E-Mail;Name\n0172;anna@example.de;Anna\n")
    assert eintraege[0]['name'] == 'Anna'
    assert eintraege[0]['phone'] == '0172'


def test_zusaetzliche_spalten_stoeren_nicht():
    eintraege, fehler = lies_nutzerliste(
        "Name;E-Mail;Beitrag;Eintritt\nAnna;anna@example.de;30;2020\n")
    assert len(eintraege) == 1 and not fehler


# ===== FEHLERFAELLE =====

def test_leere_datei():
    eintraege, fehler = lies_nutzerliste("")
    assert not eintraege and fehler


def test_fehlende_emailspalte_wird_benannt():
    eintraege, fehler = lies_nutzerliste("Name;Telefon\nAnna;0172\n")
    assert not eintraege
    assert "E-Mail" in fehler[0][1]


def test_fehlende_namensspalte_wird_benannt():
    eintraege, fehler = lies_nutzerliste("E-Mail;Telefon\na@b.de;0172\n")
    assert not eintraege
    assert "Namen" in fehler[0][1]


def test_ungueltige_adresse_wird_gemeldet_der_rest_bleibt():
    """Eine schlechte Zeile darf den ganzen Import nicht kippen."""
    eintraege, fehler = lies_nutzerliste(
        "Name;E-Mail\nAnna;anna@example.de\nBert;keine-adresse\n"
        "Cara;cara@example.de\n")
    assert len(eintraege) == 2
    assert len(fehler) == 1
    assert fehler[0][0] == 3          # Zeilennummer der Datei
    assert "keine-adresse" in fehler[0][1]


def test_doppelte_adresse_in_der_datei():
    eintraege, fehler = lies_nutzerliste(
        "Name;E-Mail\nAnna;a@b.de\nAnna Zweitkonto;a@b.de\n")
    assert len(eintraege) == 1
    assert "doppelt" in fehler[0][1]


def test_zeile_ohne_namen():
    eintraege, fehler = lies_nutzerliste("Name;E-Mail\n;a@b.de\n")
    assert not eintraege
    assert "Name" in fehler[0][1]


def test_zeile_ohne_adresse_nennt_den_namen():
    _, fehler = lies_nutzerliste("Name;E-Mail\nAnna;\n")
    assert "Anna" in fehler[0][1]


def test_nur_kopfzeile():
    eintraege, fehler = lies_nutzerliste("Name;E-Mail\n")
    assert not eintraege and fehler
