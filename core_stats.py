"""
Auswertung der Buchungen - Rangliste, Saisonfilter, Verteilungen.

Bewusst frei von Streamlit- und Firestore-Abhaengigkeiten, damit sich das
Zaehlen ohne App und ohne Datenbank pruefen laesst.

Zur Rangfolge: Bei Gleichstand bekommen alle denselben Platz, der naechste
Platz wird uebersprungen (1, 2, 2, 4) - so wird es im Sport gezaehlt und so
erwartet es jeder, der auf eine Rangliste schaut.
"""
from collections import Counter, defaultdict

from core_rules import dienstdauer_stunden, saison_zeitraum, to_date_str

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]

MEDAILLEN = {1: "🥇", 2: "🥈", 3: "🥉"}


def nur_bestaetigte(buchungen):
    return [b for b in buchungen if b.get('status') == 'confirmed']


def im_zeitraum(buchungen, von=None, bis=None):
    """Buchungen zwischen zwei Datumsangaben, jeweils einschliesslich."""
    ergebnis = []
    for b in buchungen:
        datum = b.get('slot_date')
        if not datum:
            continue
        if von and datum < von:
            continue
        if bis and datum > bis:
            continue
        ergebnis.append(b)
    return ergebnis


def rangliste(buchungen):
    """Rangfolge nach Anzahl der Dienste.

    Rueckgabe: Liste von Dicts mit platz, email, name, dienste, stunden.
    Sortiert nach Diensten, bei Gleichstand nach Stunden, dann nach Name -
    damit die Reihenfolge bei gleichen Werten stabil bleibt und nicht bei
    jedem Aufruf springt.
    """
    dienste = Counter()
    stunden = defaultdict(float)
    namen = {}

    for b in buchungen:
        email = (b.get('user_email') or '').lower()
        if not email:
            continue
        dienste[email] += 1
        stunden[email] += dienstdauer_stunden(b)
        # Der zuletzt gesehene Name gewinnt - Namensaenderungen schlagen so durch
        if b.get('user_name'):
            namen[email] = b['user_name']

    eintraege = sorted(
        ({'email': e,
          'name': namen.get(e, e),
          'dienste': dienste[e],
          'stunden': round(stunden[e], 2)}
         for e in dienste),
        key=lambda x: (-x['dienste'], -x['stunden'], x['name'].lower()))

    platz = 0
    vorher = None
    for i, eintrag in enumerate(eintraege, start=1):
        if eintrag['dienste'] != vorher:
            platz = i          # Gleichstand teilt sich den Platz
            vorher = eintrag['dienste']
        eintrag['platz'] = platz
        eintrag['medaille'] = MEDAILLEN.get(platz, "")

    return eintraege


def eintrag_von(liste, email):
    """Der Eintrag einer Person, oder None."""
    if not email:
        return None
    email = email.lower()
    for eintrag in liste:
        if eintrag['email'] == email:
            return eintrag
    return None


def abstand_nach_oben(liste, email):
    """Wie viele Dienste fehlen bis zum naechstbesseren Platz?

    Rueckgabe: (fehlende_dienste, name_der_person_davor) oder None, wenn
    die Person schon auf Platz 1 steht oder nicht vorkommt.
    """
    eigener = eintrag_von(liste, email)
    if not eigener or eigener['platz'] == 1:
        return None

    besser = [e for e in liste if e['platz'] < eigener['platz']]
    if not besser:
        return None

    # Der naechste ist der mit dem kleinsten Vorsprung
    naechster = min(besser, key=lambda e: e['dienste'])
    fehlend = naechster['dienste'] - eigener['dienste'] + 1
    return max(fehlend, 1), naechster['name']


def pro_monat(buchungen):
    """{'YYYY-MM': anzahl}, aufsteigend sortiert."""
    zaehler = Counter()
    for b in buchungen:
        datum = b.get('slot_date')
        if datum and len(str(datum)) >= 7:
            zaehler[str(datum)[:7]] += 1
    return dict(sorted(zaehler.items()))


def pro_wochentag(buchungen):
    """{'Dienstag': anzahl} - nur Tage, an denen es Dienste gibt."""
    from datetime import datetime
    zaehler = Counter()
    for b in buchungen:
        try:
            tag = datetime.strptime(to_date_str(b.get('slot_date')),
                                    "%Y-%m-%d").weekday()
            zaehler[WOCHENTAGE[tag]] += 1
        except (ValueError, TypeError, AttributeError):
            continue
    # In Wochenreihenfolge, nicht nach Haeufigkeit
    return {tag: zaehler[tag] for tag in WOCHENTAGE if zaehler[tag]}


def saisons_in_daten(buchungen, pause_start, pause_end):
    """Alle Saisons, in denen Buchungen liegen.

    Rueckgabe: Liste von (bezeichnung, start, ende), neueste zuerst.
    """
    from datetime import datetime
    zeitraeume = set()
    for b in buchungen:
        datum = b.get('slot_date')
        if not datum:
            continue
        try:
            tag = datetime.strptime(to_date_str(datum), "%Y-%m-%d").date()
        except (ValueError, TypeError, AttributeError):
            continue
        zeitraeume.add(saison_zeitraum(pause_start, pause_end, heute=tag))

    ergebnis = []
    for start, ende in sorted(zeitraeume, reverse=True):
        jahr_a, jahr_b = start[:4], ende[:4]
        bezeichnung = (f"Saison {jahr_a}/{jahr_b[2:]}" if jahr_a != jahr_b
                       else f"Saison {jahr_a}")
        ergebnis.append((bezeichnung, start, ende))
    return ergebnis


def kennzahlen(buchungen):
    """Ein paar Summen fuer die Kopfzeile."""
    return {
        'dienste': len(buchungen),
        'stunden': round(sum(dienstdauer_stunden(b) for b in buchungen), 2),
        'personen': len({(b.get('user_email') or '').lower()
                         for b in buchungen if b.get('user_email')}),
    }
