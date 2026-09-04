"""
Tests des Kalender-Exports.

    python -m pytest test_core_ics.py -v
"""
from datetime import datetime, timezone

import pytest

from core_ics import (
    als_utc,
    baue_ics,
    escape_text,
    falte,
    ics_zeit,
    uid_fuer,
    zeiten_der_buchung,
)

JETZT = datetime(2026, 9, 4, 10, 0, 0, tzinfo=timezone.utc)


def buchung(**kw):
    basis = {
        'id': 'abc123',
        'slot_date': '2026-09-15',
        'slot_time': '17:00 - 20:00',
        'user_name': 'Anna Beispiel',
        'user_email': 'anna@example.de',
    }
    basis.update(kw)
    return basis


# ===== ZEITUMRECHNUNG =====

def test_sommerzeit_wird_beruecksichtigt():
    """15.09. liegt in der MESZ: 17:00 Ortszeit sind 15:00 UTC."""
    assert ics_zeit(als_utc('2026-09-15', '17:00')) == '20260915T150000Z'


def test_winterzeit_wird_beruecksichtigt():
    """15.12. liegt in der MEZ: 17:00 Ortszeit sind 16:00 UTC."""
    assert ics_zeit(als_utc('2026-12-15', '17:00')) == '20261215T160000Z'


def test_zeiten_der_buchung():
    start, ende = zeiten_der_buchung(buchung())
    assert ics_zeit(start) == '20260915T150000Z'
    assert ics_zeit(ende) == '20260915T180000Z'


def test_zeiten_ohne_leerzeichen():
    start, ende = zeiten_der_buchung(buchung(slot_time='14:00-17:00'))
    assert ics_zeit(start) == '20260915T120000Z'
    assert ics_zeit(ende) == '20260915T150000Z'


@pytest.mark.parametrize("zeit", ['', 'kaputt', None, '17:00'])
def test_unlesbare_zeit_liefert_none(zeit):
    assert zeiten_der_buchung(buchung(slot_time=zeit)) is None


def test_fehlendes_datum_liefert_none():
    assert zeiten_der_buchung(buchung(slot_date=None)) is None


# ===== MASKIERUNG =====

def test_komma_und_semikolon_werden_maskiert():
    assert escape_text("a,b;c") == "a\\,b\\;c"


def test_backslash_wird_zuerst_maskiert():
    """Sonst wuerden die neu erzeugten Backslashes nochmals maskiert."""
    assert escape_text("a\\b") == "a\\\\b"


def test_zeilenumbruch_wird_maskiert():
    assert escape_text("a\nb") == "a\\nb"


def test_none_wird_zu_leerstring():
    assert escape_text(None) == ""


# ===== ZEILENFALTUNG =====

def test_kurze_zeile_bleibt_unveraendert():
    assert falte("SUMMARY:Dienst") == "SUMMARY:Dienst"


def test_lange_zeile_wird_gefaltet():
    lang = "DESCRIPTION:" + "x" * 200
    gefaltet = falte(lang)
    assert "\r\n " in gefaltet
    for teil in gefaltet.split("\r\n"):
        assert len(teil.encode('utf-8')) <= 75


def test_faltung_zerlegt_keine_umlaute():
    """In UTF-8 belegt ein Umlaut zwei Oktette - der Schnitt darf nicht hinein."""
    lang = "DESCRIPTION:" + "ü" * 100
    gefaltet = falte(lang)
    # Muss sich fehlerfrei zurueckdecodieren lassen
    assert gefaltet.replace("\r\n ", "").count("ü") == 100


# ===== KENNUNG =====

def test_uid_ist_stabil():
    assert uid_fuer(buchung()) == uid_fuer(buchung())


def test_verschiedene_buchungen_verschiedene_uid():
    assert uid_fuer(buchung(id='a')) != uid_fuer(buchung(id='b'))


def test_uid_auch_ohne_id():
    """Ohne Dokument-ID aus den Felddaten gebildet."""
    ohne = dict(buchung())
    del ohne['id']
    assert uid_fuer(ohne)


# ===== GESAMTE DATEI =====

def test_grundgeruest():
    ics = baue_ics([buchung()], jetzt=JETZT)
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert "VERSION:2.0" in ics


def test_zeilen_enden_mit_crlf():
    """RFC 5545 verlangt CRLF; manche Kalender sind sonst pingelig."""
    ics = baue_ics([buchung()], jetzt=JETZT)
    assert "\r\n" in ics
    assert ics.count("\n") == ics.count("\r\n")


def test_termin_ist_enthalten():
    ics = baue_ics([buchung()], jetzt=JETZT)
    assert "BEGIN:VEVENT" in ics
    assert "DTSTART:20260915T150000Z" in ics
    assert "DTEND:20260915T180000Z" in ics


def test_mehrere_buchungen():
    ics = baue_ics([buchung(id='a'), buchung(id='b', slot_date='2026-09-18')],
                   jetzt=JETZT)
    assert ics.count("BEGIN:VEVENT") == 2


def test_leere_liste_ergibt_gueltigen_kalender():
    ics = baue_ics([], jetzt=JETZT)
    assert "BEGIN:VCALENDAR" in ics and "END:VCALENDAR" in ics
    assert "BEGIN:VEVENT" not in ics


def test_unlesbare_buchung_wird_uebersprungen():
    """Eine kaputte Buchung darf nicht die ganze Datei verlieren."""
    ics = baue_ics([buchung(id='gut'), buchung(id='kaputt', slot_time='xxx')],
                   jetzt=JETZT)
    assert ics.count("BEGIN:VEVENT") == 1


def test_notiz_landet_in_der_beschreibung():
    ics = baue_ics([buchung(admin_note="Schlüssel im Büro")], jetzt=JETZT)
    assert "Schlüssel im Büro" in ics


def test_erinnerung_ist_enthalten():
    """12 Stunden vorher - passt zur Stornofrist."""
    ics = baue_ics([buchung()], jetzt=JETZT)
    assert "BEGIN:VALARM" in ics
    assert "TRIGGER:-PT12H" in ics


def test_kalendername_wird_uebernommen():
    ics = baue_ics([buchung()], kalendername="Meine Dienste", jetzt=JETZT)
    assert "X-WR-CALNAME:Meine Dienste" in ics


def test_ort_wird_uebernommen():
    ics = baue_ics([buchung()], ort="Hallenbad", jetzt=JETZT)
    assert "LOCATION:Hallenbad" in ics


def test_ohne_ort_keine_leere_zeile():
    assert "LOCATION" not in baue_ics([buchung()], jetzt=JETZT)


def test_jede_zeile_haelt_die_laengenbegrenzung():
    lang = buchung(admin_note="Sehr langer Hinweis " * 20)
    for zeile in baue_ics([lang], jetzt=JETZT).split("\r\n"):
        assert len(zeile.encode('utf-8')) <= 75
