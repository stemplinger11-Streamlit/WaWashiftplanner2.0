"""
Tests des Kalender-Exports.

    python -m pytest test_core_ics.py -v
"""
from datetime import datetime, timezone

import pytest

from core_ics import (
    als_utc,
    baue_absage,
    baue_einladung,
    baue_ics,
    laufende_nummer,
    escape_text,
    falte,
    ics_zeit,
    uid_fuer,
    zeiten_der_buchung,
)

JETZT = datetime(2026, 9, 4, 10, 0, 0, tzinfo=timezone.utc)


def entfalte(text):
    """Umbruch nach RFC 5545 rueckgaengig machen, damit Erwartungen an
    lange Zeilen nicht am Faltpunkt scheitern."""
    return text.replace(chr(13) + chr(10) + " ", "")


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


# ===== EINLADUNG UND ABSAGE =====
#
# Anders als baue_ics() erzeugen diese beiden eine Nachricht nach iTIP:
# der Kalender des Empfaengers legt den Termin selbst an und aendert ihn
# spaeter wieder, statt dass jemand eine Datei importiert.

def test_einladung_ist_eine_anfrage():
    text = baue_einladung(buchung(), 'verein@example.de', jetzt=JETZT)
    assert 'METHOD:REQUEST' in text
    assert 'STATUS:CONFIRMED' in text


def test_absage_sagt_den_termin_ab():
    text = baue_absage(buchung(), 'verein@example.de', jetzt=JETZT)
    assert 'METHOD:CANCEL' in text
    assert 'STATUS:CANCELLED' in text


def test_absage_traegt_dieselbe_kennung_wie_die_einladung():
    """Sonst sagt die Absage einen Termin ab, den es im Kalender nicht gibt."""
    b = buchung()
    ein = baue_einladung(b, 'verein@example.de', jetzt=JETZT)
    ab = baue_absage(b, 'verein@example.de', jetzt=JETZT)
    kennung = [z for z in ein.split('\r\n') if z.startswith('UID:')]
    assert kennung == [z for z in ab.split('\r\n') if z.startswith('UID:')]


def test_kennung_haengt_nicht_an_der_dokument_id():
    """Beim Umbuchen wird die alte Buchung geloescht - die Absage kennt
    deren Dokument-ID nicht mehr. Datum, Uhrzeit und Adresse muessen
    deshalb genuegen."""
    mit = baue_einladung(buchung(id='abc123'), 'verein@example.de', jetzt=JETZT)
    ohne = baue_einladung(buchung(id=None), 'verein@example.de', jetzt=JETZT)
    kennung = lambda t: [z for z in t.split('\r\n') if z.startswith('UID:')]
    assert kennung(mit) == kennung(ohne)


def test_laufende_nummer_steigt_mit_der_zeit():
    """Buchen, stornieren, denselben Slot neu buchen: die Kennung ist
    wieder dieselbe. Eine Einladung mit kleinerer Nummer als die vorherige
    Absage wird von Kalendern stillschweigend verworfen."""
    frueher = laufende_nummer(datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc))
    spaeter = laufende_nummer(datetime(2026, 9, 4, 10, 5, tzinfo=timezone.utc))
    assert spaeter > frueher


def test_absage_traegt_eine_hoehere_nummer_als_die_einladung():
    b = buchung()
    ein = baue_einladung(b, 'verein@example.de',
                         jetzt=datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc))
    ab = baue_absage(b, 'verein@example.de',
                     jetzt=datetime(2026, 9, 4, 11, 0, tzinfo=timezone.utc))
    nummer = lambda t: int([z for z in t.split('\r\n')
                            if z.startswith('SEQUENCE:')][0][9:])
    assert nummer(ab) > nummer(ein)


def test_eingeladen_wird_wer_gebucht_hat():
    text = entfalte(baue_einladung(buchung(), 'verein@example.de', jetzt=JETZT))
    assert 'ORGANIZER;CN=Wasserwacht:mailto:verein@example.de' in text
    assert 'mailto:anna@example.de' in text


def test_keine_rueckmeldung_angefordert():
    """Der Nutzer hat in der App gebucht - er soll nicht noch einmal
    zu- oder absagen, und im Vereinspostfach sollen keine Antworten
    auflaufen, die niemand liest."""
    text = entfalte(baue_einladung(buchung(), 'verein@example.de', jetzt=JETZT))
    teilnehmer = [z for z in text.split('\r\n') if z.startswith('ATTENDEE')][0]
    assert 'PARTSTAT=ACCEPTED' in teilnehmer
    assert 'RSVP=FALSE' in teilnehmer


def test_einladung_enthaelt_ort_notiz_und_link():
    text = entfalte(baue_einladung(
        buchung(admin_note='Bitte Schluessel mitbringen'),
        'verein@example.de', ort='Freibad Hauzenberg',
        link='https://app-wawa-shiftplaner.azurewebsites.net',
        stornofrist=12, jetzt=JETZT))
    assert 'LOCATION:Freibad Hauzenberg' in text
    assert 'Bitte Schluessel mitbringen' in text
    assert 'URL:https://app-wawa-shiftplaner.azurewebsites.net' in text
    assert '12 Stunden' in text


def test_absage_ohne_erinnerung():
    """Ein abgesagter Termin darf nicht mehr klingeln."""
    assert 'BEGIN:VALARM' not in baue_absage(buchung(), 'verein@example.de',
                                             jetzt=JETZT)


def test_einladung_ohne_lesbare_zeit_gibt_nichts_zurueck():
    """Lieber keine Einladung als eine kaputte - die Mail geht trotzdem raus."""
    assert baue_einladung(buchung(slot_time='kaputt'), 'verein@example.de',
                          jetzt=JETZT) is None
