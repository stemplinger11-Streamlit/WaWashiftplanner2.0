"""
Tests der Erinnerungs-Auswahl.

    python -m pytest test_core_reminders.py -v
"""
from datetime import date

import pytest

from core_reminders import (
    faellige_erinnerungen,
    notify_pref,
    platzhalter_ersetzen,
    zieldatum,
)

ZIEL = "2026-09-15"


def buchung(**kw):
    basis = {
        'id': 'b1',
        'slot_date': ZIEL,
        'slot_time': '17:00 - 20:00',
        'user_email': 'anna@example.de',
        'user_name': 'Anna',
        'status': 'confirmed',
    }
    basis.update(kw)
    return basis


def nutzer(**kw):
    basis = {
        'id': 'u1',
        'email': 'anna@example.de',
        'name': 'Anna',
        'phone': '01721234567',
        'active': True,
    }
    basis.update(kw)
    return {basis['email']: basis}


# ===== ZIELDATUM =====

def test_zieldatum_ist_morgen():
    assert zieldatum(heute=date(2026, 9, 14)) == "2026-09-15"


def test_zieldatum_mit_abweichendem_vorlauf():
    assert zieldatum(vorlauf_tage=2, heute=date(2026, 9, 13)) == "2026-09-15"


def test_zieldatum_ueber_monatsgrenze():
    assert zieldatum(heute=date(2026, 9, 30)) == "2026-10-01"


# ===== EINSTELLUNGEN =====

def test_neues_schema_hat_vorrang():
    u = {'email_notifications_reminder': False, 'email_notifications': True}
    assert not notify_pref(u, 'email')


def test_bestandsnutzer_altes_schema_wirkt():
    """Bestandsnutzer haben nur die Altfelder."""
    assert notify_pref({'email_notifications': True}, 'email')
    assert not notify_pref({'email_notifications': False}, 'email')


def test_standardwerte_ohne_jede_angabe():
    assert notify_pref({}, 'email') is True
    assert notify_pref({}, 'sms') is False


# ===== AUSWAHL =====

def test_einfache_erinnerung_wird_gefunden():
    treffer = faellige_erinnerungen([buchung()], nutzer(), ZIEL)
    assert len(treffer) == 1
    assert treffer[0]['email'] is True
    assert treffer[0]['sms'] is False  # SMS standardmaessig aus


def test_anderer_tag_wird_ignoriert():
    assert faellige_erinnerungen([buchung(slot_date="2026-09-16")], nutzer(), ZIEL) == []


def test_stornierte_buchung_wird_ignoriert():
    assert faellige_erinnerungen([buchung(status='cancelled')], nutzer(), ZIEL) == []


def test_bereits_erinnert_wird_uebersprungen():
    """Schutz vor Doppelversand, wenn der Job zweimal laeuft."""
    b = buchung(reminder_sent_at="2026-09-14T18:00:00")
    assert faellige_erinnerungen([b], nutzer(), ZIEL) == []


def test_deaktivierter_nutzer_bekommt_nichts():
    assert faellige_erinnerungen([buchung()], nutzer(active=False), ZIEL) == []


def test_verwaiste_buchung_stuerzt_nicht_ab():
    """Konto geloescht, Buchung blieb liegen."""
    assert faellige_erinnerungen([buchung()], {}, ZIEL) == []


def test_abgewaehlte_mail_wird_nicht_gesendet():
    u = nutzer(email_notifications_reminder=False)
    assert faellige_erinnerungen([buchung()], u, ZIEL) == []


def test_sms_wenn_aktiviert_und_nummer_vorhanden():
    u = nutzer(sms_notifications_reminder=True)
    treffer = faellige_erinnerungen([buchung()], u, ZIEL)
    assert treffer[0]['sms'] is True


def test_keine_sms_ohne_telefonnummer():
    u = nutzer(phone='', sms_notifications_reminder=True)
    treffer = faellige_erinnerungen([buchung()], u, ZIEL)
    assert treffer[0]['sms'] is False


def test_nur_sms_gewuenscht():
    u = nutzer(email_notifications_reminder=False, sms_notifications_reminder=True)
    treffer = faellige_erinnerungen([buchung()], u, ZIEL)
    assert len(treffer) == 1
    assert treffer[0]['email'] is False
    assert treffer[0]['sms'] is True


def test_mehrere_buchungen_am_selben_tag():
    buchungen = [
        buchung(id='b1', user_email='anna@example.de'),
        buchung(id='b2', user_email='bert@example.de', user_name='Bert'),
    ]
    alle = nutzer()
    alle['bert@example.de'] = {'id': 'u2', 'email': 'bert@example.de',
                              'name': 'Bert', 'active': True}
    treffer = faellige_erinnerungen(buchungen, alle, ZIEL)
    assert len(treffer) == 2


def test_leere_eingabe():
    assert faellige_erinnerungen([], {}, ZIEL) == []


# ===== PLATZHALTER =====

def test_platzhalter_werden_ersetzt():
    assert platzhalter_ersetzen(
        "Hallo {name}, am {date}", {'name': 'Anna', 'date': '15.09.2026'}
    ) == "Hallo Anna, am 15.09.2026"


def test_unbekannter_platzhalter_bleibt_stehen():
    assert platzhalter_ersetzen("Hallo {xyz}", {'name': 'Anna'}) == "Hallo {xyz}"


@pytest.mark.parametrize("text", ["", None])
def test_leerer_text(text):
    assert platzhalter_ersetzen(text, {'name': 'Anna'}) == ''
