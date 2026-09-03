"""
Passwort-Hashing mit sanfter Migration.

Bis V8.1 wurden Passwoerter als ungesalzener SHA-256 gespeichert - anfaellig
fuer Rainbow-Table-Angriffe. Neue und geaenderte Passwoerter werden jetzt mit
bcrypt gehasht.

Bestandsnutzer duerfen dabei nichts verlieren: Ihre Klartext-Passwoerter sind
nicht bekannt, ein Rehash im Voraus ist also unmoeglich. Stattdessen wird beim
naechsten erfolgreichen Login geprueft, ob der gespeicherte Hash noch das alte
Verfahren nutzt - wenn ja, wird er im selben Moment transparent auf bcrypt
umgestellt. Der Nutzer merkt davon nichts und muss nichts tun.

Bewusst frei von Streamlit- und Firestore-Abhaengigkeiten, damit die Logik
ohne App und ohne Datenbank testbar ist.
"""
import hashlib
from datetime import datetime

try:
    import bcrypt
    BCRYPT_VERFUEGBAR = True
except ImportError:  # pragma: no cover
    bcrypt = None
    BCRYPT_VERFUEGBAR = False

# Kostenfaktor. 12 ist ein gaengiger Kompromiss aus Sicherheit und Wartezeit.
BCRYPT_ROUNDS = 12

# Abmeldung nach Inaktivitaet. Bewusst grosszuegig: die App wird ueberwiegend
# nebenbei benutzt, ein zu kurzer Wert waere nur laestig. 0 schaltet ab.
DEFAULT_SESSION_TIMEOUT_MINUTES = 60


def session_abgelaufen(letzte_aktivitaet, jetzt=None,
                       timeout_minuten=DEFAULT_SESSION_TIMEOUT_MINUTES):
    """Ist die Sitzung wegen Inaktivitaet abgelaufen?

    Im Zweifel wird False zurueckgegeben: Ein Fehler hier duerfte niemanden
    aus der App aussperren.
    """
    if not timeout_minuten or timeout_minuten <= 0:
        return False  # Timeout deaktiviert
    if letzte_aktivitaet is None:
        return False

    jetzt = jetzt or datetime.now()
    try:
        vergangen = (jetzt - letzte_aktivitaet).total_seconds()
    except TypeError:
        # Ein Wert mit, einer ohne Zeitzone - nicht vergleichbar.
        return False
    return vergangen > timeout_minuten * 60


def hash_pw_legacy(pw):
    """Altes Verfahren aus V8.1 - nur noch zum Pruefen von Bestandshashes."""
    return hashlib.sha256(pw.encode()).hexdigest()


def ist_legacy_hash(hash_wert):
    """Stammt der Hash aus dem alten SHA-256-Verfahren?

    SHA-256 liefert 64 Hex-Zeichen; bcrypt-Hashes beginnen mit '$2'.
    """
    if not hash_wert or not isinstance(hash_wert, str):
        return False
    if hash_wert.startswith('$2'):
        return False
    return len(hash_wert) == 64 and all(c in '0123456789abcdef' for c in hash_wert.lower())


def hash_pw(pw):
    """Neues Passwort hashen - bcrypt, sofern verfuegbar."""
    if not BCRYPT_VERFUEGBAR:
        # Ohne bcrypt bleibt das Altverfahren die einzige Option. Die App
        # laeuft weiter, statt beim Start auszufallen.
        return hash_pw_legacy(pw)
    return bcrypt.hashpw(pw.encode('utf-8'),
                         bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode('utf-8')


def pw_pruefen(pw, gespeicherter_hash):
    """Passwort gegen den gespeicherten Hash pruefen -> (korrekt, neuer_hash)

    'neuer_hash' ist gesetzt, wenn der Hash auf bcrypt umgestellt werden sollte
    (also nur beim ersten erfolgreichen Login eines Bestandsnutzers).
    Der Aufrufer schreibt ihn dann in die Datenbank.
    """
    if not gespeicherter_hash or pw is None:
        return False, None

    if ist_legacy_hash(gespeicherter_hash):
        if hash_pw_legacy(pw) != gespeicherter_hash:
            return False, None
        # Passwort stimmt - Gelegenheit zum stillen Upgrade
        if BCRYPT_VERFUEGBAR:
            return True, hash_pw(pw)
        return True, None

    if not BCRYPT_VERFUEGBAR:  # pragma: no cover
        return False, None

    try:
        korrekt = bcrypt.checkpw(pw.encode('utf-8'),
                                 gespeicherter_hash.encode('utf-8'))
    except (ValueError, TypeError):
        return False, None
    return korrekt, None


# ===== ANGEMELDET BLEIBEN =====
# Der Browser bekommt ein Cookie mit einem Zufallstoken. In der Datenbank
# liegt nur dessen Hash - wer die Datenbank liest, kann sich damit nicht
# anmelden. Dasselbe Prinzip wie bei Passwoertern.

SESSION_COOKIE_NAME = 'wawa_dienstplan_session'
DEFAULT_REMEMBER_DAYS = 30


def neues_session_token():
    """Kryptografisch sicheres Token fuer das Cookie."""
    import secrets
    return secrets.token_urlsafe(32)


def token_hash(token):
    """Nur der Hash wird gespeichert."""
    if not token:
        return None
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def session_eintrag(user_id, tage=DEFAULT_REMEMBER_DAYS, jetzt=None):
    """Erzeugt (token, datensatz) fuer eine neue Dauersitzung.

    Zeiten als ISO-Text in UTC, damit der Vergleich unabhaengig davon
    funktioniert, wie Firestore Zeitstempel zurueckgibt.
    """
    from datetime import timedelta, timezone
    jetzt = jetzt or datetime.now(timezone.utc)
    token = neues_session_token()
    return token, {
        'user_id': user_id,
        'expires_at': (jetzt + timedelta(days=tage)).isoformat(),
        'created_at': jetzt.isoformat(),
    }


def session_datensatz_gueltig(datensatz, jetzt=None):
    """Ist die gespeicherte Dauersitzung noch gueltig?

    Im Zweifel False: eine unlesbare Angabe darf keine Anmeldung erlauben.
    """
    from datetime import timezone
    if not datensatz or not datensatz.get('user_id'):
        return False
    ablauf = datensatz.get('expires_at')
    if not ablauf:
        return False
    try:
        if isinstance(ablauf, str):
            ablauf = datetime.fromisoformat(ablauf)
        jetzt = jetzt or datetime.now(timezone.utc)
        if ablauf.tzinfo is None:
            ablauf = ablauf.replace(tzinfo=timezone.utc)
        if jetzt.tzinfo is None:
            jetzt = jetzt.replace(tzinfo=timezone.utc)
        return ablauf > jetzt
    except (ValueError, TypeError, AttributeError):
        return False
