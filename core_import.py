"""
Einlesen einer Nutzerliste aus CSV.

Absichtlich nachsichtig bei der Form: Die Datei kommt aus Excel oder aus
einer Mitgliederverwaltung, mit Semikolon oder Komma getrennt, mit
unterschiedlich geschriebenen Spaltenueberschriften und gelegentlich einem
BOM am Anfang. Streng ist die Pruefung nur dort, wo es zaehlt - bei der
E-Mail-Adresse, denn sie ist zugleich der Anmeldename.

Bewusst frei von Streamlit- und Firestore-Abhaengigkeiten.
"""
import csv
import io
import re

# Schreibweisen, unter denen eine Spalte erkannt wird
SPALTEN = {
    'name': ['name', 'nachname', 'vorname', 'vollstaendiger name',
             'vollständiger name', 'anzeigename', 'mitglied'],
    'email': ['email', 'e-mail', 'e mail', 'mail', 'emailadresse',
              'e-mail-adresse', 'e-mailadresse'],
    'phone': ['telefon', 'telefonnummer', 'handy', 'mobil', 'mobiltelefon',
              'phone', 'tel', 'rufnummer'],
}

EMAIL_MUSTER = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')


def normalisiere_spalte(bezeichnung):
    """Spaltenueberschrift auf einen bekannten Feldnamen abbilden."""
    if not bezeichnung:
        return None
    schlank = bezeichnung.strip().lstrip('﻿').lower().replace('_', ' ')
    for feld, varianten in SPALTEN.items():
        if schlank in varianten:
            return feld
    return None


def erkenne_trennzeichen(text):
    """Semikolon oder Komma? Excel schreibt im Deutschen Semikolon."""
    kopf = text.split('\n', 1)[0]
    return ';' if kopf.count(';') > kopf.count(',') else ','


def ist_gueltige_email(wert):
    return bool(wert and EMAIL_MUSTER.match(wert.strip()))


def lies_nutzerliste(text):
    """CSV einlesen -> (eintraege, fehler)

    eintraege: Liste von {'name', 'email', 'phone'} - nur brauchbare Zeilen
    fehler:    Liste von (zeilennummer, beschreibung)

    Beide Rueckgaben zusammen ergeben ein vollstaendiges Bild: Die guten
    Zeilen lassen sich anlegen, die schlechten werden benannt, statt den
    ganzen Import scheitern zu lassen.
    """
    if not text or not text.strip():
        return [], [(0, "Die Datei ist leer")]

    text = text.lstrip('﻿')
    leser = csv.reader(io.StringIO(text), delimiter=erkenne_trennzeichen(text))

    try:
        kopfzeile = next(leser)
    except StopIteration:
        return [], [(0, "Die Datei ist leer")]

    zuordnung = {}
    for i, bezeichnung in enumerate(kopfzeile):
        feld = normalisiere_spalte(bezeichnung)
        if feld and feld not in zuordnung:
            zuordnung[feld] = i

    if 'email' not in zuordnung:
        return [], [(1, "Keine Spalte für die E-Mail-Adresse gefunden. "
                        "Erwartet wird eine Überschrift wie 'E-Mail'.")]
    if 'name' not in zuordnung:
        return [], [(1, "Keine Spalte für den Namen gefunden. "
                        "Erwartet wird eine Überschrift wie 'Name'.")]

    eintraege = []
    fehler = []
    gesehen = set()

    for nummer, zeile in enumerate(leser, start=2):
        if not any(feld.strip() for feld in zeile):
            continue  # Leerzeile

        def hole(feld):
            i = zuordnung.get(feld)
            return zeile[i].strip() if i is not None and i < len(zeile) else ''

        name = hole('name')
        email = hole('email').lower()
        phone = hole('phone')

        if not name:
            fehler.append((nummer, "Kein Name angegeben"))
            continue
        if not email:
            fehler.append((nummer, f"Keine E-Mail-Adresse für {name}"))
            continue
        if not ist_gueltige_email(email):
            fehler.append((nummer, f"Ungültige E-Mail-Adresse: {email}"))
            continue
        if email in gesehen:
            fehler.append((nummer, f"E-Mail-Adresse doppelt in der Datei: {email}"))
            continue

        gesehen.add(email)
        eintraege.append({'name': name, 'email': email, 'phone': phone})

    if not eintraege and not fehler:
        fehler.append((0, "Keine Datenzeilen gefunden"))

    return eintraege, fehler


BEISPIEL_CSV = (
    "Name;E-Mail;Telefon\n"
    "Anna Beispiel;anna@example.de;0172 1234567\n"
    "Bert Muster;bert@example.de;\n"
)
