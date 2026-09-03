"""
Fachliche Regeln des Dienstplans - Feiertage, Saisonpause, Stornofrist.

Bewusst frei von Streamlit- und Firestore-Abhaengigkeiten, damit die Logik
ohne laufende App und ohne Datenbankzugriff getestet werden kann.
Konfigurierbare Werte werden als Parameter uebergeben, nicht hier gelesen.
"""
from datetime import datetime, timedelta, date

import pytz

TIMEZONE_STR = "Europe/Berlin"
TZ = pytz.timezone(TIMEZONE_STR)

# Feste Feiertage in Bayern als (Monat, Tag, Name).
# Mariae Himmelfahrt gilt nur in ueberwiegend katholischen Gemeinden -
# fuer den Standort der Wasserwacht zutreffend.
FIXED_HOLIDAYS = [
    (1, 1, "Neujahr"),
    (1, 6, "Heilige Drei Könige"),
    (5, 1, "Tag der Arbeit"),
    (8, 15, "Mariä Himmelfahrt"),
    (10, 3, "Tag der Deutschen Einheit"),
    (11, 1, "Allerheiligen"),
    (12, 25, "1. Weihnachtstag"),
    (12, 26, "2. Weihnachtstag"),
]

# Bewegliche Feiertage als (Tage-Versatz zum Ostersonntag, Name).
EASTER_HOLIDAYS = [
    (-2, "Karfreitag"),
    (1, "Ostermontag"),
    (39, "Christi Himmelfahrt"),
    (50, "Pfingstmontag"),
    (60, "Fronleichnam"),
]

# Saisonpause, jaehrlich wiederkehrend im Format "MM-TT".
DEFAULT_PAUSE_START = "06-01"
DEFAULT_PAUSE_END = "09-14"

# Stornofrist in Stunden vor Dienstbeginn. Gilt nur fuer normale Nutzer.
DEFAULT_CANCEL_DEADLINE_HOURS = 12


def easter_sunday(year):
    """Ostersonntag nach der anonymen gregorianischen Osterformel."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def bavaria_holidays(year):
    """Alle bayerischen Feiertage eines Jahres als {'YYYY-MM-TT': 'Name'}."""
    result = {}
    for month, day, name in FIXED_HOLIDAYS:
        result[date(year, month, day).strftime("%Y-%m-%d")] = name
    easter = easter_sunday(year)
    for offset, name in EASTER_HOLIDAYS:
        result[(easter + timedelta(days=offset)).strftime("%Y-%m-%d")] = name
    return result


def to_date_str(d):
    """Normalisiert date/datetime/str auf 'YYYY-MM-TT'."""
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")


def holiday_name(d):
    """Name des Feiertags oder None."""
    try:
        d = to_date_str(d)
        return bavaria_holidays(int(d[:4])).get(d)
    except (ValueError, TypeError, AttributeError):
        return None


def is_holiday(d):
    return holiday_name(d) is not None


def is_in_pause(d, pause_start=DEFAULT_PAUSE_START, pause_end=DEFAULT_PAUSE_END):
    """Liegt das Datum in der Saisonpause?

    Die Pause ist jahresunabhaengig ueber Monat/Tag definiert. Ein Zeitraum,
    der ueber den Jahreswechsel laeuft (z.B. 11-01 bis 03-31), wird
    unterstuetzt. Beide Randtage gehoeren zur Pause.
    """
    try:
        md = to_date_str(d)[5:]
        if not md:
            return False
        if pause_start <= pause_end:
            return pause_start <= md <= pause_end
        # Zeitraum laeuft ueber den Jahreswechsel
        return md >= pause_start or md <= pause_end
    except (ValueError, TypeError, AttributeError):
        return False


def datumsbereich(von, bis):
    """Alle Tage von 'von' bis 'bis' einschliesslich, als Liste von Strings.

    Liegt 'bis' vor 'von', wird getauscht - eine vertauschte Eingabe im
    Formular soll keine leere Sperrung erzeugen.
    """
    try:
        a = datetime.strptime(to_date_str(von), "%Y-%m-%d").date()
        b = datetime.strptime(to_date_str(bis), "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        return []
    if b < a:
        a, b = b, a
    return [(a + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((b - a).days + 1)]


def is_blocked(d, pause_start=DEFAULT_PAUSE_START, pause_end=DEFAULT_PAUSE_END,
               gesperrte=None):
    """Ist an diesem Tag keine Buchung moeglich?

    gesperrte: {'YYYY-MM-TT': grund} - vom Admin gesperrte Einzeltermine,
    etwa bei geschlossenem Bad.
    """
    if gesperrte and to_date_str(d) in gesperrte:
        return True
    return is_holiday(d) or is_in_pause(d, pause_start, pause_end)


def block_reason(d, pause_start=DEFAULT_PAUSE_START, pause_end=DEFAULT_PAUSE_END,
                 gesperrte=None):
    """Grund der Sperrung oder None.

    Die Admin-Sperrung hat Vorrang: Sie wurde bewusst gesetzt und traegt den
    aussagekraeftigeren Grund ("Bad geschlossen" statt "Feiertag").
    """
    if gesperrte:
        grund = gesperrte.get(to_date_str(d))
        if grund is not None:
            return grund or "Gesperrt"
    name = holiday_name(d)
    if name:
        return f"Feiertag: {name}"
    if is_in_pause(d, pause_start, pause_end):
        return "Saisonpause"
    return None


def slot_start_datetime(slot_date_str, slot_time_str):
    """Startzeitpunkt eines Slots als zeitzonenbewusstes datetime.

    slot_time_str hat die Form '17:00 - 20:00'; ausgewertet wird der Beginn.
    """
    start_part = str(slot_time_str).split('-')[0].strip()
    naive = datetime.strptime(
        f"{to_date_str(slot_date_str)} {start_part}", "%Y-%m-%d %H:%M"
    )
    return TZ.localize(naive)


def can_cancel(slot_date_str, slot_time_str, is_admin=False, now=None,
               deadline_hours=DEFAULT_CANCEL_DEADLINE_HOURS):
    """Darf diese Buchung noch storniert werden? -> (bool, Begruendung)

    Admins sind von der Frist ausgenommen und duerfen jederzeit stornieren
    und umbuchen - auch fuer andere Nutzer und am Diensttag selbst.
    """
    if is_admin:
        return True, None
    try:
        start = slot_start_datetime(slot_date_str, slot_time_str)
    except (ValueError, AttributeError):
        # Unlesbare Zeitangabe darf den Nutzer nicht aussperren
        return True, None
    now = now or datetime.now(TZ)
    remaining = (start - now).total_seconds() / 3600
    if remaining < deadline_hours:
        if remaining < 0:
            return False, ("Der Dienst liegt in der Vergangenheit. "
                           "Bitte wende dich an einen Admin.")
        return False, (f"Stornierung nur bis {deadline_hours} Stunden vor "
                       f"Dienstbeginn möglich. Bitte wende dich an einen Admin.")
    return True, None
