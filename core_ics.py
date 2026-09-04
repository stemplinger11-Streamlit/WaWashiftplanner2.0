"""
Kalenderdatei (ICS) aus Buchungen.

Erzeugt eine .ics-Datei nach RFC 5545, die sich in Handy- und
Desktop-Kalender importieren laesst.

Bewusst als Datei zum Herunterladen, nicht als Abo-Adresse: Ein echtes Abo
mit automatischer Aktualisierung braeuchte eine dauerhaft erreichbare
Adresse, die Streamlit Cloud nicht bereitstellt. Das steht als eigener
Punkt auf der TODO-Liste.

Zeiten werden nach UTC umgerechnet und mit 'Z' geschrieben. Damit braucht
die Datei keinen VTIMEZONE-Block und wird von allen Kalendern gleich
verstanden - auch ueber die Sommerzeitumstellung hinweg.

Bewusst frei von Streamlit- und Firestore-Abhaengigkeiten.
"""
from datetime import datetime, timedelta, timezone
import hashlib

import pytz

TZ = pytz.timezone("Europe/Berlin")

PRODID = "-//Wasserwacht//Dienstplan//DE"
MAX_ZEILE = 75  # Oktette, laut RFC 5545


def escape_text(wert):
    """Sonderzeichen nach RFC 5545 maskieren.

    Reihenfolge wichtig: der Backslash zuerst, sonst werden die von den
    folgenden Ersetzungen erzeugten Backslashes nochmals maskiert.
    """
    if wert is None:
        return ""
    return (str(wert)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace("\r", "")
            .replace(";", "\\;")
            .replace(",", "\\,"))


def falte(zeile):
    """Lange Zeilen nach RFC 5545 umbrechen.

    Fortsetzungszeilen beginnen mit einem Leerzeichen. Gezaehlt wird in
    Oktetten, nicht in Zeichen - Umlaute belegen in UTF-8 zwei.
    """
    roh = zeile.encode('utf-8')
    if len(roh) <= MAX_ZEILE:
        return zeile

    teile = []
    rest = roh
    grenze = MAX_ZEILE
    while len(rest) > grenze:
        schnitt = grenze
        # Nicht mitten in ein Mehrbyte-Zeichen schneiden
        while schnitt > 0 and (rest[schnitt] & 0xC0) == 0x80:
            schnitt -= 1
        teile.append(rest[:schnitt].decode('utf-8'))
        rest = rest[schnitt:]
        grenze = MAX_ZEILE - 1  # das fuehrende Leerzeichen zaehlt mit
    teile.append(rest.decode('utf-8'))
    return "\r\n ".join(teile)


def als_utc(datum_str, zeit_str):
    """'2026-09-15' + '17:00' -> zeitzonenbewusstes datetime in UTC."""
    naiv = datetime.strptime(f"{datum_str} {zeit_str}", "%Y-%m-%d %H:%M")
    return TZ.localize(naiv).astimezone(timezone.utc)


def ics_zeit(zeitpunkt):
    """datetime -> '20260915T150000Z'."""
    return zeitpunkt.strftime("%Y%m%dT%H%M%SZ")


def zeiten_der_buchung(buchung):
    """(start_utc, ende_utc) einer Buchung, oder None bei unlesbarer Angabe."""
    datum = buchung.get('slot_date')
    zeit = str(buchung.get('slot_time', ''))
    if not datum or '-' not in zeit:
        return None
    try:
        beginn_str, ende_str = [t.strip() for t in zeit.split('-', 1)]
        start = als_utc(datum, beginn_str)
        ende = als_utc(datum, ende_str)
        if ende <= start:
            # Dienst ueber Mitternacht - kommt derzeit nicht vor, schadet aber nicht
            ende += timedelta(days=1)
        return start, ende
    except (ValueError, TypeError):
        return None


def uid_fuer(buchung):
    """Stabile Kennung, damit ein erneuter Import nicht doppelt anlegt."""
    kennung = buchung.get('id') or "{}_{}_{}".format(
        buchung.get('slot_date', ''), buchung.get('slot_time', ''),
        buchung.get('user_email', ''))
    return "{}@wasserwacht-dienstplan".format(
        hashlib.sha1(str(kennung).encode('utf-8')).hexdigest()[:20])


def baue_ics(buchungen, kalendername="Wasserwacht Dienste",
             titel="Dienst Wasserwacht", ort="", jetzt=None):
    """Erzeugt den Inhalt einer .ics-Datei.

    buchungen: Liste von Dicts mit slot_date, slot_time, optional
    user_name und admin_note.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(kalendername)}",
        "X-WR-TIMEZONE:Europe/Berlin",
    ]

    for b in buchungen:
        zeiten = zeiten_der_buchung(b)
        if not zeiten:
            continue  # unlesbare Buchung ueberspringen statt die Datei zu verlieren
        start, ende = zeiten

        beschreibung = []
        if b.get('user_name'):
            beschreibung.append(f"Gebucht von {b['user_name']}")
        if b.get('admin_note'):
            beschreibung.append(f"Hinweis: {b['admin_note']}")

        zeilen.extend([
            "BEGIN:VEVENT",
            f"UID:{uid_fuer(b)}",
            f"DTSTAMP:{ics_zeit(jetzt)}",
            f"DTSTART:{ics_zeit(start)}",
            f"DTEND:{ics_zeit(ende)}",
            f"SUMMARY:{escape_text(titel)}",
        ])
        if beschreibung:
            zeilen.append(f"DESCRIPTION:{escape_text(' | '.join(beschreibung))}")
        if ort:
            zeilen.append(f"LOCATION:{escape_text(ort)}")
        zeilen.extend([
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "BEGIN:VALARM",
            "TRIGGER:-PT12H",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{escape_text(titel)}",
            "END:VALARM",
            "END:VEVENT",
        ])

    zeilen.append("END:VCALENDAR")
    return "\r\n".join(falte(z) for z in zeilen) + "\r\n"
