"""
Tests der Auswertung.

    python -m pytest test_core_stats.py -v
"""
import pytest

from core_stats import (
    abstand_nach_oben,
    eintrag_von,
    im_zeitraum,
    kennzahlen,
    nur_bestaetigte,
    pro_monat,
    pro_wochentag,
    rangliste,
    saisons_in_daten,
)


def b(email, datum, name=None, zeit="17:00 - 20:00", status='confirmed'):
    return {'user_email': email, 'user_name': name or email.split('@')[0],
            'slot_date': datum, 'slot_time': zeit, 'status': status}


# ===== FILTER =====

def test_nur_bestaetigte():
    daten = [b('a@x.de', '2026-10-01'),
             b('a@x.de', '2026-10-02', status='cancelled')]
    assert len(nur_bestaetigte(daten)) == 1


def test_zeitraum_einschliesslich():
    daten = [b('a@x.de', '2026-09-30'), b('a@x.de', '2026-10-01'),
             b('a@x.de', '2026-10-31'), b('a@x.de', '2026-11-01')]
    treffer = im_zeitraum(daten, '2026-10-01', '2026-10-31')
    assert len(treffer) == 2


def test_zeitraum_ohne_grenzen():
    daten = [b('a@x.de', '2026-10-01')]
    assert len(im_zeitraum(daten)) == 1


def test_zeitraum_ignoriert_buchung_ohne_datum():
    assert im_zeitraum([{'user_email': 'a@x.de'}], '2026-01-01', '2026-12-31') == []


# ===== RANGLISTE =====

def test_meiste_dienste_ist_platz_eins():
    daten = [b('a@x.de', '2026-10-01'), b('a@x.de', '2026-10-02'),
             b('c@x.de', '2026-10-03')]
    liste = rangliste(daten)
    assert liste[0]['email'] == 'a@x.de'
    assert liste[0]['platz'] == 1
    assert liste[0]['dienste'] == 2


def test_gleichstand_teilt_den_platz():
    """Sportzaehlung: 1, 2, 2, 4 - nicht 1, 2, 2, 3."""
    daten = ([b('a@x.de', '2026-10-01')] * 3 +
             [b('b@x.de', '2026-10-02')] * 2 +
             [b('c@x.de', '2026-10-03')] * 2 +
             [b('d@x.de', '2026-10-04')])
    plaetze = [e['platz'] for e in rangliste(daten)]
    assert plaetze == [1, 2, 2, 4]


def test_medaillen_fuer_die_ersten_drei():
    daten = ([b('a@x.de', '2026-10-01')] * 4 +
             [b('b@x.de', '2026-10-02')] * 3 +
             [b('c@x.de', '2026-10-03')] * 2 +
             [b('d@x.de', '2026-10-04')])
    liste = rangliste(daten)
    assert [e['medaille'] for e in liste] == ["🥇", "🥈", "🥉", ""]


def test_gleichstand_wird_nach_stunden_getrennt():
    """Gleich viele Dienste, aber laengere Schichten stehen vorn."""
    daten = [b('kurz@x.de', '2026-10-01', zeit="14:00 - 17:00"),
             b('lang@x.de', '2026-10-02', zeit="14:00 - 20:00")]
    liste = rangliste(daten)
    assert liste[0]['email'] == 'lang@x.de'
    # Der Platz bleibt geteilt, die Dienstzahl ist ja gleich
    assert liste[0]['platz'] == liste[1]['platz'] == 1


def test_reihenfolge_ist_stabil():
    """Bei voelligem Gleichstand alphabetisch, damit nichts springt."""
    daten = [b('z@x.de', '2026-10-01', name='Zora'),
             b('a@x.de', '2026-10-02', name='Anna')]
    assert [e['name'] for e in rangliste(daten)] == ['Anna', 'Zora']


def test_stunden_werden_summiert():
    daten = [b('a@x.de', '2026-10-01', zeit="17:00 - 20:00"),
             b('a@x.de', '2026-10-02', zeit="14:00 - 17:00")]
    assert rangliste(daten)[0]['stunden'] == 6.0


def test_adresse_wird_kleingeschrieben_zusammengefasst():
    daten = [b('Anna@X.de', '2026-10-01'), b('anna@x.de', '2026-10-02')]
    liste = rangliste(daten)
    assert len(liste) == 1
    assert liste[0]['dienste'] == 2


def test_neuester_name_gewinnt():
    daten = [b('a@x.de', '2026-10-01', name='Anna Alt'),
             b('a@x.de', '2026-10-02', name='Anna Neu')]
    assert rangliste(daten)[0]['name'] == 'Anna Neu'


def test_buchung_ohne_adresse_wird_uebersprungen():
    daten = [b('a@x.de', '2026-10-01'), {'slot_date': '2026-10-02'}]
    assert len(rangliste(daten)) == 1


def test_leere_liste():
    assert rangliste([]) == []


# ===== EIGENER EINTRAG =====

def test_eintrag_wird_gefunden():
    liste = rangliste([b('a@x.de', '2026-10-01')])
    assert eintrag_von(liste, 'a@x.de')['dienste'] == 1


def test_eintrag_unabhaengig_von_gross_klein():
    liste = rangliste([b('a@x.de', '2026-10-01')])
    assert eintrag_von(liste, 'A@X.de') is not None


@pytest.mark.parametrize("email", [None, '', 'unbekannt@x.de'])
def test_eintrag_nicht_vorhanden(email):
    liste = rangliste([b('a@x.de', '2026-10-01')])
    assert eintrag_von(liste, email) is None


# ===== ABSTAND NACH OBEN =====

def test_abstand_zum_naechsten_platz():
    """Drei Dienste vorn, einer selbst -> drei fehlen zum Ueberholen."""
    daten = [b('vorne@x.de', '2026-10-01')] * 3 + [b('ich@x.de', '2026-10-02')]
    fehlend, name = abstand_nach_oben(rangliste(daten), 'ich@x.de')
    assert fehlend == 3
    assert name == 'vorne'


def test_abstand_bei_einem_dienst_unterschied():
    daten = [b('vorne@x.de', '2026-10-01')] * 2 + [b('ich@x.de', '2026-10-02')]
    fehlend, _ = abstand_nach_oben(rangliste(daten), 'ich@x.de')
    assert fehlend == 2


def test_platz_eins_hat_keinen_abstand():
    daten = [b('ich@x.de', '2026-10-01')] * 2 + [b('b@x.de', '2026-10-02')]
    assert abstand_nach_oben(rangliste(daten), 'ich@x.de') is None


def test_abstand_bei_gleichstand_zielt_auf_den_platz_davor():
    daten = ([b('a@x.de', '2026-10-01')] * 3 +
             [b('ich@x.de', '2026-10-02')] * 2 +
             [b('c@x.de', '2026-10-03')] * 2)
    fehlend, _ = abstand_nach_oben(rangliste(daten), 'ich@x.de')
    assert fehlend == 2


def test_abstand_fuer_unbekannte_person():
    assert abstand_nach_oben(rangliste([b('a@x.de', '2026-10-01')]), 'x@x.de') is None


# ===== VERTEILUNGEN =====

def test_pro_monat():
    daten = [b('a@x.de', '2026-10-01'), b('a@x.de', '2026-10-15'),
             b('a@x.de', '2026-11-02')]
    assert pro_monat(daten) == {'2026-10': 2, '2026-11': 1}


def test_pro_monat_ist_sortiert():
    daten = [b('a@x.de', '2026-11-01'), b('a@x.de', '2026-09-01')]
    assert list(pro_monat(daten)) == ['2026-09', '2026-11']


def test_pro_wochentag():
    # 15.09.2026 ist ein Dienstag, 18.09. ein Freitag
    daten = [b('a@x.de', '2026-09-15'), b('a@x.de', '2026-09-18')]
    assert pro_wochentag(daten) == {'Dienstag': 1, 'Freitag': 1}


def test_wochentage_in_wochenreihenfolge():
    daten = [b('a@x.de', '2026-09-19'), b('a@x.de', '2026-09-15')]  # Sa, Di
    assert list(pro_wochentag(daten)) == ['Dienstag', 'Samstag']


def test_unlesbares_datum_stuerzt_nicht_ab():
    assert pro_wochentag([b('a@x.de', 'kaputt')]) == {}


# ===== SAISONS =====

def test_saison_wird_erkannt():
    daten = [b('a@x.de', '2026-10-01'), b('a@x.de', '2027-01-15')]
    saisons = saisons_in_daten(daten, "06-01", "09-14")
    assert len(saisons) == 1
    assert saisons[0][0] == "Saison 2026/27"
    assert saisons[0][1] == "2026-09-15"


def test_mehrere_saisons_neueste_zuerst():
    daten = [b('a@x.de', '2025-10-01'), b('a@x.de', '2026-10-01')]
    saisons = saisons_in_daten(daten, "06-01", "09-14")
    assert [s[0] for s in saisons] == ["Saison 2026/27", "Saison 2025/26"]


def test_saisons_ohne_daten():
    assert saisons_in_daten([], "06-01", "09-14") == []


# ===== KENNZAHLEN =====

def test_kennzahlen():
    daten = [b('a@x.de', '2026-10-01'), b('a@x.de', '2026-10-02'),
             b('c@x.de', '2026-10-03')]
    k = kennzahlen(daten)
    assert k == {'dienste': 3, 'stunden': 9.0, 'personen': 2}


def test_kennzahlen_leer():
    assert kennzahlen([]) == {'dienste': 0, 'stunden': 0, 'personen': 0}
