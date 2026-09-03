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
