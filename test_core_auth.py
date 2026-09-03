"""
Tests fuer das Passwort-Hashing und die Migration der Bestandsnutzer.

    python -m pytest test_core_auth.py -v
"""
import hashlib

import pytest

from core_auth import (
    BCRYPT_VERFUEGBAR,
    hash_pw,
    hash_pw_legacy,
    ist_legacy_hash,
    pw_pruefen,
)

# So sah ein Bestandshash in V8.1 aus
BESTAND_PW = "MeinAltesPasswort1"
BESTAND_HASH = hashlib.sha256(BESTAND_PW.encode()).hexdigest()


# ===== ERKENNUNG DES VERFAHRENS =====

def test_legacy_hash_wird_erkannt():
    assert ist_legacy_hash(BESTAND_HASH)


def test_bcrypt_hash_ist_kein_legacy():
    assert not ist_legacy_hash(hash_pw("egal"))


@pytest.mark.parametrize("wert", [None, "", "zu-kurz", 12345, "x" * 64])
def test_ungueltige_werte_sind_kein_legacy_hash(wert):
    assert not ist_legacy_hash(wert)


# ===== BESTANDSNUTZER =====

def test_bestandsnutzer_kann_sich_weiterhin_anmelden():
    """Kernanforderung: keine Neuregistrierung nach der Umstellung."""
    korrekt, _ = pw_pruefen(BESTAND_PW, BESTAND_HASH)
    assert korrekt


def test_falsches_passwort_wird_abgelehnt():
    korrekt, neuer = pw_pruefen("falsch", BESTAND_HASH)
    assert not korrekt
    assert neuer is None


@pytest.mark.skipif(not BCRYPT_VERFUEGBAR, reason="bcrypt nicht installiert")
def test_erfolgreicher_login_liefert_neuen_hash():
    """Beim ersten Login wird der Althash still auf bcrypt umgestellt."""
    korrekt, neuer = pw_pruefen(BESTAND_PW, BESTAND_HASH)
    assert korrekt
    assert neuer is not None
    assert neuer.startswith('$2')
    assert neuer != BESTAND_HASH


@pytest.mark.skipif(not BCRYPT_VERFUEGBAR, reason="bcrypt nicht installiert")
def test_nach_migration_funktioniert_das_gleiche_passwort():
    """Der Nutzer behaelt sein Passwort - nur die Speicherung aendert sich."""
    _, migriert = pw_pruefen(BESTAND_PW, BESTAND_HASH)
    korrekt, nochmal = pw_pruefen(BESTAND_PW, migriert)
    assert korrekt
    assert nochmal is None  # kein weiteres Upgrade noetig


@pytest.mark.skipif(not BCRYPT_VERFUEGBAR, reason="bcrypt nicht installiert")
def test_nach_migration_wird_falsches_passwort_abgelehnt():
    _, migriert = pw_pruefen(BESTAND_PW, BESTAND_HASH)
    korrekt, _ = pw_pruefen("falsch", migriert)
    assert not korrekt


# ===== NEUE PASSWOERTER =====

@pytest.mark.skipif(not BCRYPT_VERFUEGBAR, reason="bcrypt nicht installiert")
def test_neues_passwort_wird_mit_bcrypt_gehasht():
    assert hash_pw("Geheim123").startswith('$2')


@pytest.mark.skipif(not BCRYPT_VERFUEGBAR, reason="bcrypt nicht installiert")
def test_gleiches_passwort_ergibt_unterschiedliche_hashes():
    """Der Salt muss je Hash verschieden sein."""
    assert hash_pw("Geheim123") != hash_pw("Geheim123")


def test_neues_passwort_laesst_sich_pruefen():
    h = hash_pw("Geheim123")
    korrekt, _ = pw_pruefen("Geheim123", h)
    assert korrekt


def test_neues_passwort_lehnt_falsches_ab():
    h = hash_pw("Geheim123")
    korrekt, _ = pw_pruefen("Geheim124", h)
    assert not korrekt


# ===== ROBUSTHEIT =====

@pytest.mark.parametrize("hash_wert", [None, "", "kaputt", "$2b$defekt"])
def test_unbrauchbare_hashes_stuerzen_nicht_ab(hash_wert):
    korrekt, neuer = pw_pruefen("egal", hash_wert)
    assert not korrekt
    assert neuer is None


def test_leeres_passwort_wird_abgelehnt():
    korrekt, _ = pw_pruefen(None, BESTAND_HASH)
    assert not korrekt


def test_umlaute_im_passwort():
    h = hash_pw("Grüße123ß")
    korrekt, _ = pw_pruefen("Grüße123ß", h)
    assert korrekt


def test_legacy_funktion_unveraendert():
    """Absicherung: das alte Verfahren darf sich nicht verschieben."""
    assert hash_pw_legacy("test") == hashlib.sha256(b"test").hexdigest()


# ===== SITZUNGS-TIMEOUT =====

from datetime import datetime, timedelta, timezone  # noqa: E402

from core_auth import (  # noqa: E402
    DEFAULT_SESSION_TIMEOUT_MINUTES,
    session_abgelaufen,
)

JETZT = datetime(2026, 9, 15, 18, 0, 0)


def test_standard_timeout_ist_60_minuten():
    assert DEFAULT_SESSION_TIMEOUT_MINUTES == 60


def test_frische_aktivitaet_laeuft_nicht_ab():
    assert not session_abgelaufen(JETZT - timedelta(minutes=5), jetzt=JETZT)


def test_kurz_vor_ablauf_bleibt_angemeldet():
    assert not session_abgelaufen(JETZT - timedelta(minutes=59), jetzt=JETZT)


def test_genau_an_der_grenze_bleibt_angemeldet():
    assert not session_abgelaufen(JETZT - timedelta(minutes=60), jetzt=JETZT)


def test_nach_ablauf_wird_abgemeldet():
    assert session_abgelaufen(JETZT - timedelta(minutes=61), jetzt=JETZT)


def test_lange_inaktivitaet():
    assert session_abgelaufen(JETZT - timedelta(hours=8), jetzt=JETZT)


def test_abweichender_timeout():
    letzte = JETZT - timedelta(minutes=31)
    assert session_abgelaufen(letzte, jetzt=JETZT, timeout_minuten=30)
    assert not session_abgelaufen(letzte, jetzt=JETZT, timeout_minuten=60)


@pytest.mark.parametrize("wert", [0, None])
def test_timeout_deaktivierbar(wert):
    assert not session_abgelaufen(JETZT - timedelta(days=3), jetzt=JETZT,
                                  timeout_minuten=wert)


def test_ohne_letzte_aktivitaet_kein_ablauf():
    """Erster Aufruf nach dem Login - noch nichts gemerkt."""
    assert not session_abgelaufen(None, jetzt=JETZT)


def test_gemischte_zeitzonen_sperren_niemanden_aus():
    """Ein Vergleichsfehler darf nicht zur Abmeldung fuehren."""
    mit_zone = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)
    assert not session_abgelaufen(mit_zone, jetzt=JETZT)


# ===== ANGEMELDET BLEIBEN =====

from core_auth import (  # noqa: E402
    DEFAULT_REMEMBER_DAYS,
    SESSION_COOKIE_NAME,
    neues_session_token,
    session_datensatz_gueltig,
    session_eintrag,
    token_hash,
)

UTC_JETZT = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_cookie_name_ist_gesetzt():
    assert SESSION_COOKIE_NAME


def test_token_ist_lang_genug():
    assert len(neues_session_token()) >= 32


def test_tokens_sind_verschieden():
    assert len({neues_session_token() for _ in range(50)}) == 50


def test_token_hash_ist_deterministisch():
    t = neues_session_token()
    assert token_hash(t) == token_hash(t)


def test_verschiedene_tokens_verschiedene_hashes():
    assert token_hash("a") != token_hash("b")


def test_hash_gibt_token_nicht_preis():
    """Aus der Datenbank darf sich niemand anmelden koennen."""
    t = neues_session_token()
    assert t not in token_hash(t)


@pytest.mark.parametrize("wert", [None, ""])
def test_token_hash_ohne_token(wert):
    assert token_hash(wert) is None


def test_neue_sitzung_ist_gueltig():
    _, satz = session_eintrag("u1", jetzt=UTC_JETZT)
    assert session_datensatz_gueltig(satz, jetzt=UTC_JETZT)


def test_sitzung_enthaelt_nutzer():
    _, satz = session_eintrag("u1", jetzt=UTC_JETZT)
    assert satz['user_id'] == "u1"


def test_sitzung_laeuft_nach_der_frist_ab():
    _, satz = session_eintrag("u1", tage=30, jetzt=UTC_JETZT)
    spaeter = UTC_JETZT + timedelta(days=31)
    assert not session_datensatz_gueltig(satz, jetzt=spaeter)


def test_sitzung_gilt_kurz_vor_ablauf_noch():
    _, satz = session_eintrag("u1", tage=30, jetzt=UTC_JETZT)
    fast = UTC_JETZT + timedelta(days=29, hours=23)
    assert session_datensatz_gueltig(satz, jetzt=fast)


def test_standarddauer_ist_30_tage():
    assert DEFAULT_REMEMBER_DAYS == 30


@pytest.mark.parametrize("satz", [
    None, {}, {'expires_at': '2027-01-01T00:00:00+00:00'},   # ohne user_id
    {'user_id': 'u1'},                                        # ohne Ablauf
    {'user_id': 'u1', 'expires_at': 'kaputt'},
    {'user_id': 'u1', 'expires_at': None},
])
def test_unbrauchbare_sitzung_gilt_nicht(satz):
    """Im Zweifel keine Anmeldung."""
    assert not session_datensatz_gueltig(satz, jetzt=UTC_JETZT)


def test_zeitstempel_ohne_zeitzone_wird_angenommen():
    """Firestore kann Zeitangaben ohne Zone zurueckgeben."""
    satz = {'user_id': 'u1', 'expires_at': '2026-10-15T12:00:00'}
    assert session_datensatz_gueltig(satz, jetzt=UTC_JETZT)
