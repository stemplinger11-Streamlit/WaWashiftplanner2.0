"""
Versendet die Erinnerungen fuer die Dienste des Folgetags.

Laeuft bewusst AUSSERHALB der Streamlit-App: Streamlit Community Cloud haelt
keinen zuverlaessigen Hintergrundprozess offen - die App schlaeft bei
Inaktivitaet ein, ein Scheduler im Prozess stirbt mit. Dieses Skript wird
stattdessen von aussen angestossen (z.B. GitHub Action, siehe
.github/workflows/reminders.yml).

Standardmaessig ein TROCKENLAUF. Erst mit --senden wird tatsaechlich
verschickt.

Aufruf:
    python scripts/send_reminders.py                 # zeigt nur an
    python scripts/send_reminders.py --senden        # verschickt
    python scripts/send_reminders.py --tage 2 --senden

Zugangsdaten: .streamlit/secrets.toml oder Umgebungsvariablen
(SMTP_USER, SMTP_PASSWORD, ..., FIREBASE_CREDENTIALS als JSON-String).
"""
import argparse
import email.utils
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core_reminders import (  # noqa: E402
    faellige_erinnerungen,
    platzhalter_ersetzen,
    zieldatum,
)

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STANDARD_MAIL_BETREFF = '⏰ Erinnerung: Dienst morgen - {date}'
STANDARD_MAIL_TEXT = """Hallo {name},

dein Dienst ist morgen:

📅 Datum: {date}
⏰ Uhrzeit: {time}

Bis morgen!
Dein {org_name} Team 🌊"""
STANDARD_SMS_TEXT = """⏰ Erinnerung: Dienst morgen!
📅 {date}
⏰ {time}

{org_name}"""


def lade_konfiguration():
    """Secrets aus .streamlit/secrets.toml oder aus der Umgebung lesen."""
    konf = {}
    pfad = PROJECT_ROOT / '.streamlit' / 'secrets.toml'
    if pfad.exists():
        with open(pfad, 'rb') as fh:
            konf = tomllib.load(fh)

    # Umgebungsvariablen haben Vorrang (fuer GitHub Actions)
    for schluessel in ('SMTP_SERVER', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD',
                       'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN',
                       'TWILIO_PHONE_NUMBER', 'ENABLE_SMS_REMINDER'):
        if os.environ.get(schluessel):
            konf[schluessel] = os.environ[schluessel]

    if os.environ.get('FIREBASE_CREDENTIALS'):
        konf['firebase'] = json.loads(os.environ['FIREBASE_CREDENTIALS'])

    return konf


def firestore_client(konf):
    if 'firebase' not in konf:
        raise SystemExit("❌ Keine Firebase-Zugangsdaten gefunden "
                         "(.streamlit/secrets.toml oder FIREBASE_CREDENTIALS).")
    info = dict(konf['firebase'])
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(credentials=creds, project=info['project_id'])


def fmt_de(datum):
    try:
        return datetime.strptime(datum, "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(datum)


def einstellung(db, schluessel, standard=''):
    """Wert aus der settings-Collection lesen (vom Admin gepflegte Vorlagen)."""
    try:
        doc = db.collection('settings').document(schluessel).get()
        if doc.exists:
            wert = doc.to_dict().get('value')
            if wert:
                return wert
    except Exception as e:
        print(f"⚠️ Einstellung '{schluessel}' nicht lesbar: {e}")
    return standard


def sende_mail(konf, empfaenger, betreff, text):
    user = konf.get('SMTP_USER')
    pw = konf.get('SMTP_PASSWORD')
    if not user or not pw:
        return False, "keine SMTP-Zugangsdaten"

    msg = MIMEMultipart()
    msg['From'] = email.utils.formataddr(("Wasserwacht Dienstplan", user))
    msg['To'] = empfaenger
    msg['Subject'] = betreff
    msg['Date'] = email.utils.formatdate(localtime=True)
    msg.attach(MIMEText(text, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP(konf.get('SMTP_SERVER', 'smtp.gmail.com'),
                          int(konf.get('SMTP_PORT', 587)), timeout=60) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, pw)
            smtp.send_message(msg)
        return True, "gesendet"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def formatiere_nummer(nummer):
    """Telefonnummer ins E.164-Format bringen (deutsche Vorwahl als Standard)."""
    if not nummer:
        return None
    nummer = ''.join(c for c in str(nummer) if c.isdigit() or c == '+')
    if nummer.startswith('+'):
        return nummer
    if nummer.startswith('0'):
        return '+49' + nummer[1:]
    return '+49' + nummer if nummer else None


def sende_sms(konf, nummer, text):
    if str(konf.get('ENABLE_SMS_REMINDER', 'false')).lower() != 'true':
        return False, "SMS deaktiviert"
    sid = konf.get('TWILIO_ACCOUNT_SID')
    token = konf.get('TWILIO_AUTH_TOKEN')
    absender = konf.get('TWILIO_PHONE_NUMBER')
    if not (sid and token and absender):
        return False, "keine Twilio-Zugangsdaten"

    ziel = formatiere_nummer(nummer)
    if not ziel:
        return False, f"ungültige Nummer: {nummer}"

    try:
        from twilio.rest import Client
        nachricht = Client(sid, token).messages.create(
            to=ziel, from_=absender, body=text)
        return True, f"gesendet (SID {nachricht.sid})"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Dienst-Erinnerungen versenden")
    parser.add_argument('--senden', action='store_true',
                        help="Tatsächlich versenden (ohne dies: Trockenlauf)")
    parser.add_argument('--tage', type=int, default=1,
                        help="Vorlauf in Tagen (Standard: 1 = morgen)")
    args = parser.parse_args()

    konf = lade_konfiguration()
    db = firestore_client(konf)

    ziel = zieldatum(vorlauf_tage=args.tage)
    print(f"Erinnerungen für Dienste am {fmt_de(ziel)}")
    print(f"Modus: {'VERSAND' if args.senden else 'Trockenlauf (kein Versand)'}\n")

    buchungen = []
    for doc in db.collection('bookings').where('slot_date', '==', ziel).stream():
        b = doc.to_dict()
        b['id'] = doc.id
        buchungen.append(b)

    nutzer = {}
    for doc in db.collection('users').stream():
        u = doc.to_dict()
        u['id'] = doc.id
        if u.get('email'):
            nutzer[u['email']] = u

    faellig = faellige_erinnerungen(buchungen, nutzer, ziel)

    if not faellig:
        print("Nichts zu tun – keine offenen Erinnerungen.")
        return 0

    org = einstellung(db, 'org_name', 'Wasserwacht')
    betreff_vorlage = einstellung(db, 'email_reminder_subject', STANDARD_MAIL_BETREFF)
    text_vorlage = einstellung(db, 'email_reminder_body', STANDARD_MAIL_TEXT)
    sms_vorlage = einstellung(db, 'sms_reminder_body', STANDARD_SMS_TEXT)

    versendet = 0
    fehler = 0

    for eintrag in faellig:
        b, u = eintrag['booking'], eintrag['user']
        daten = {
            'name': u.get('name', ''),
            'date': fmt_de(b.get('slot_date')),
            'time': b.get('slot_time', ''),
            'email': u.get('email', ''),
            'phone': u.get('phone', ''),
            'org_name': org,
            'org_email': konf.get('ADMIN_EMAIL_RECEIVER', ''),
            'current_date': datetime.now().strftime('%d.%m.%Y %H:%M'),
        }

        kanaele = []
        if eintrag['email']:
            kanaele.append('E-Mail')
        if eintrag['sms']:
            kanaele.append('SMS')
        print(f"  {u.get('name'):20s} {b.get('slot_time'):15s} → {', '.join(kanaele)}")

        if not args.senden:
            continue

        erfolg_irgendwo = False

        if eintrag['email']:
            ok, meldung = sende_mail(
                konf, u['email'],
                platzhalter_ersetzen(betreff_vorlage, daten),
                platzhalter_ersetzen(text_vorlage, daten))
            print(f"      E-Mail: {meldung}")
            erfolg_irgendwo = erfolg_irgendwo or ok
            if not ok:
                fehler += 1

        if eintrag['sms']:
            ok, meldung = sende_sms(
                konf, u.get('phone'),
                platzhalter_ersetzen(sms_vorlage, daten))
            print(f"      SMS:    {meldung}")
            erfolg_irgendwo = erfolg_irgendwo or ok
            if not ok:
                fehler += 1

        # Nur markieren, wenn mindestens ein Kanal geklappt hat - sonst
        # soll der naechste Lauf es erneut versuchen.
        if erfolg_irgendwo:
            try:
                db.collection('bookings').document(b['id']).update({
                    'reminder_sent_at': firestore.SERVER_TIMESTAMP
                })
                versendet += 1
            except Exception as e:
                print(f"      ⚠️ Markierung fehlgeschlagen: {e}")

    if args.senden:
        print(f"\n✅ {versendet} Erinnerung(en) versendet, {fehler} Fehler.")
        return 1 if fehler else 0

    print(f"\n{len(faellig)} Erinnerung(en) wären zu versenden.")
    print("Zum tatsächlichen Versand: --senden ergänzen.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
