"""
Auswahl der faelligen Erinnerungen.

Bewusst frei von Streamlit-, Firestore- und Versand-Abhaengigkeiten: Diese
Datei entscheidet nur, WER eine Erinnerung bekommen soll. Das Versenden
uebernimmt scripts/send_reminders.py.

Doppelversand wird ueber das Feld 'reminder_sent_at' an der Buchung
verhindert - laeuft der Job zweimal am selben Tag, passiert beim zweiten
Mal nichts mehr.
"""
from datetime import datetime, timedelta

# Vorgabe: Erinnerung am Vortag des Dienstes.
STANDARD_VORLAUF_TAGE = 1


def zieldatum(vorlauf_tage=STANDARD_VORLAUF_TAGE, heute=None):
    """Datum, fuer das heute erinnert werden soll (als 'YYYY-MM-TT')."""
    heute = heute or datetime.now().date()
    if hasattr(heute, 'date'):
        heute = heute.date()
    return (heute + timedelta(days=vorlauf_tage)).strftime('%Y-%m-%d')


def notify_pref(user, channel, event='reminder'):
    """Moechte dieser Nutzer die Benachrichtigung erhalten?

    Spiegelt die Logik aus streamlit_app.py: das feingranulare Schema hat
    Vorrang, das alte Schema der Bestandsnutzer dient als Fallback.
    """
    if user is None:
        return False
    standard = True if channel == 'email' else False
    wert = user.get(f"{channel}_notifications_{event}")
    if wert is not None:
        return bool(wert)
    alt = user.get(f"{channel}_notifications")
    if alt is not None:
        return bool(alt)
    return standard


def faellige_erinnerungen(buchungen, nutzer_nach_email, ziel_datum):
    """Ermittelt die zu versendenden Erinnerungen.

    buchungen:          Liste von Buchungs-Dicts
    nutzer_nach_email:  {email: user_dict}
    ziel_datum:         'YYYY-MM-TT'

    Rueckgabe: Liste von Dicts mit booking, user, email (bool), sms (bool).
    Enthalten sind nur Eintraege, bei denen mindestens ein Kanal zutrifft.
    """
    ergebnis = []
    for b in buchungen:
        if b.get('slot_date') != ziel_datum:
            continue
        if b.get('status') != 'confirmed':
            continue
        # Bereits erinnert - schuetzt vor Doppelversand
        if b.get('reminder_sent_at'):
            continue

        email = b.get('user_email')
        user = nutzer_nach_email.get(email)
        if not user:
            # Konto geloescht, Buchung verwaist - nichts zu tun
            continue
        if not user.get('active', True):
            continue

        per_mail = bool(email) and notify_pref(user, 'email')
        per_sms = bool(user.get('phone')) and notify_pref(user, 'sms')

        if per_mail or per_sms:
            ergebnis.append({
                'booking': b,
                'user': user,
                'email': per_mail,
                'sms': per_sms,
            })

    return ergebnis


def platzhalter_ersetzen(text, daten):
    """Ersetzt {schluessel} durch die Werte aus daten."""
    if not text:
        return ''
    for schluessel, wert in daten.items():
        text = text.replace('{' + schluessel + '}', str(wert))
    return text
