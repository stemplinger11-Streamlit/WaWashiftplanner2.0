"""
Tests der fachlichen Regeln. Laufen ohne Firebase und ohne Streamlit:

    python -m pytest test_core_rules.py -v
"""
from datetime import datetime, date

import pytest

from core_rules import (
    TZ,
    easter_sunday,
    bavaria_holidays,
    holiday_name,
    is_holiday,
    is_in_pause,
    is_blocked,
    block_reason,
    slot_start_datetime,
    can_cancel,
    to_date_str,
)

# Die in V8.1 hartkodierten Listen - die Berechnung muss sie exakt reproduzieren.
LEGACY_2025 = [
    "2025-01-01", "2025-01-06", "2025-04-18", "2025-04-21", "2025-05-01",
    "2025-05-29", "2025-06-09", "2025-06-19", "2025-08-15", "2025-10-03",
    "2025-11-01", "2025-12-25", "2025-12-26",
]
LEGACY_2026 = [
    "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01",
    "2026-05-14", "2026-05-25", "2026-06-04", "2026-08-15", "2026-10-03",
    "2026-11-01", "2026-12-25", "2026-12-26",
]


# ===== OSTERFORMEL =====

@pytest.mark.parametrize("year,expected", [
    (2024, date(2024, 3, 31)),
    (2025, date(2025, 4, 20)),
    (2026, date(2026, 4, 5)),
    (2027, date(2027, 3, 28)),
    (2028, date(2028, 4, 16)),
    (2030, date(2030, 4, 21)),
])
def test_ostersonntag_bekannte_jahre(year, expected):
    assert easter_sunday(year) == expected


# ===== FEIERTAGE =====

def test_feiertage_2025_entsprechen_altbestand():
    assert sorted(bavaria_holidays(2025)) == sorted(LEGACY_2025)


def test_feiertage_2026_entsprechen_altbestand():
    assert sorted(bavaria_holidays(2026)) == sorted(LEGACY_2026)


def test_feiertage_2027_werden_erkannt():
    """Der Altbestand endete 2026 - die Saison 2026/27 laeuft in 2027 hinein."""
    assert is_holiday("2027-01-01")
    assert is_holiday("2027-01-06")
    assert holiday_name("2027-01-01") == "Neujahr"


def test_feiertage_fuer_beliebiges_zukunftsjahr():
    for year in (2028, 2035, 2050):
        feiertage = bavaria_holidays(year)
        assert len(feiertage) == 13
        assert f"{year}-12-25" in feiertage


def test_normaler_tag_ist_kein_feiertag():
    assert not is_holiday("2026-09-15")
    assert holiday_name("2026-09-15") is None


def test_is_holiday_akzeptiert_date_objekt():
    assert is_holiday(date(2026, 12, 25))


def test_unlesbares_datum_stuerzt_nicht_ab():
    assert not is_holiday("kein-datum")
    assert holiday_name(None) is None


# ===== SAISONPAUSE =====

def test_mitte_september_ist_buchbar_mit_standardpause():
    """Kernanforderung: Saisonstart Mitte September muss moeglich sein."""
    assert not is_in_pause("2026-09-15")
    assert not is_in_pause("2026-09-20")


def test_sommer_bleibt_gesperrt():
    assert is_in_pause("2026-07-01")
    assert is_in_pause("2026-06-01")   # Randtag Beginn
    assert is_in_pause("2026-09-14")   # Randtag Ende


def test_pause_gilt_jahresunabhaengig():
    for year in (2025, 2026, 2027, 2030):
        assert is_in_pause(f"{year}-07-15")
        assert not is_in_pause(f"{year}-11-15")


def test_pause_ueber_jahreswechsel():
    """Konfiguration wie 01.11. bis 31.03. muss funktionieren."""
    assert is_in_pause("2026-12-15", pause_start="11-01", pause_end="03-31")
    assert is_in_pause("2026-01-15", pause_start="11-01", pause_end="03-31")
    assert not is_in_pause("2026-07-15", pause_start="11-01", pause_end="03-31")


def test_konfigurierbare_pause_wird_beachtet():
    assert is_in_pause("2026-09-20", pause_start="06-01", pause_end="09-30")
    assert not is_in_pause("2026-09-20", pause_start="06-01", pause_end="09-14")


# ===== SPERRUNG GESAMT =====

def test_block_reason_nennt_feiertagsnamen():
    assert block_reason("2026-12-25") == "Feiertag: 1. Weihnachtstag"


def test_block_reason_saisonpause():
    assert block_reason("2026-07-01") == "Saisonpause"


def test_block_reason_none_bei_freiem_tag():
    assert block_reason("2026-09-15") is None
    assert not is_blocked("2026-09-15")


def test_feiertag_in_der_pause_meldet_feiertag():
    """15.08. liegt in der Sommerpause und ist zugleich Feiertag."""
    assert is_blocked("2026-08-15")
    assert block_reason("2026-08-15").startswith("Feiertag")


# ===== SLOT-ZEITPUNKT =====

def test_slot_start_datetime_liest_beginn():
    dt = slot_start_datetime("2026-09-15", "17:00 - 20:00")
    assert dt.year == 2026 and dt.month == 9 and dt.day == 15
    assert dt.hour == 17 and dt.minute == 0


def test_slot_start_datetime_ist_zeitzonenbewusst():
    assert slot_start_datetime("2026-09-15", "17:00 - 20:00").tzinfo is not None


def test_slot_start_datetime_ohne_leerzeichen():
    dt = slot_start_datetime("2026-09-15", "14:00-17:00")
    assert dt.hour == 14


# ===== STORNOFRIST =====

def _now(y, m, d, hh, mm=0):
    return TZ.localize(datetime(y, m, d, hh, mm))


def test_nutzer_darf_frueh_genug_stornieren():
    ok, grund = can_cancel("2026-09-15", "17:00 - 20:00",
                           now=_now(2026, 9, 14, 10), deadline_hours=12)
    assert ok and grund is None


def test_nutzer_darf_innerhalb_der_frist_nicht_stornieren():
    """13:00 am Diensttag -> nur noch 4 Stunden bis 17:00."""
    ok, grund = can_cancel("2026-09-15", "17:00 - 20:00",
                           now=_now(2026, 9, 15, 13), deadline_hours=12)
    assert not ok
    assert "12 Stunden" in grund


def test_frist_greift_exakt_an_der_grenze():
    genau_12h = can_cancel("2026-09-15", "17:00 - 20:00",
                           now=_now(2026, 9, 15, 5), deadline_hours=12)
    knapp_darunter = can_cancel("2026-09-15", "17:00 - 20:00",
                                now=_now(2026, 9, 15, 5, 1), deadline_hours=12)
    assert genau_12h[0] is True
    assert knapp_darunter[0] is False


def test_admin_ist_von_der_frist_ausgenommen():
    ok, grund = can_cancel("2026-09-15", "17:00 - 20:00", is_admin=True,
                           now=_now(2026, 9, 15, 16, 59), deadline_hours=12)
    assert ok and grund is None


def test_admin_darf_auch_vergangene_dienste_umbuchen():
    ok, _ = can_cancel("2026-09-01", "17:00 - 20:00", is_admin=True,
                       now=_now(2026, 9, 15, 12), deadline_hours=12)
    assert ok


def test_vergangener_dienst_fuer_nutzer_gesperrt():
    ok, grund = can_cancel("2026-09-01", "17:00 - 20:00",
                           now=_now(2026, 9, 15, 12), deadline_hours=12)
    assert not ok
    assert "Vergangenheit" in grund


def test_unlesbare_zeit_sperrt_nutzer_nicht_aus():
    ok, grund = can_cancel("2026-09-15", "kaputt", now=_now(2026, 9, 14, 10))
    assert ok and grund is None


def test_abweichende_frist_wird_beachtet():
    ok, _ = can_cancel("2026-09-15", "17:00 - 20:00",
                       now=_now(2026, 9, 14, 10), deadline_hours=48)
    assert not ok


# ===== HILFSFUNKTION =====

def test_to_date_str_normalisiert():
    assert to_date_str("2026-09-15") == "2026-09-15"
    assert to_date_str(date(2026, 9, 15)) == "2026-09-15"
    assert to_date_str(datetime(2026, 9, 15, 17, 0)) == "2026-09-15"


# ===== VOM ADMIN GESPERRTE TERMINE =====

from core_rules import datumsbereich  # noqa: E402


def test_datumsbereich_einzelner_tag():
    assert datumsbereich("2026-09-15", "2026-09-15") == ["2026-09-15"]


def test_datumsbereich_mehrere_tage():
    assert datumsbereich("2026-09-15", "2026-09-18") == [
        "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]


def test_datumsbereich_ueber_monatsgrenze():
    assert datumsbereich("2026-09-29", "2026-10-02") == [
        "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]


def test_datumsbereich_vertauschte_eingabe():
    """Vertauschte Daten im Formular duerfen nicht zu einer leeren Sperrung fuehren."""
    assert datumsbereich("2026-09-18", "2026-09-15") == [
        "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]


@pytest.mark.parametrize("von,bis", [(None, None), ("kaputt", "2026-09-15")])
def test_datumsbereich_unbrauchbare_eingabe(von, bis):
    assert datumsbereich(von, bis) == []


def test_datumsbereich_akzeptiert_date_objekte():
    assert datumsbereich(date(2026, 9, 15), date(2026, 9, 16)) == [
        "2026-09-15", "2026-09-16"]


def test_gesperrter_termin_blockiert():
    gesperrt = {"2026-09-15": "Bad geschlossen"}
    assert is_blocked("2026-09-15", gesperrte=gesperrt)
    assert block_reason("2026-09-15", gesperrte=gesperrt) == "Bad geschlossen"


def test_nicht_gesperrter_termin_bleibt_frei():
    gesperrt = {"2026-09-15": "Bad geschlossen"}
    assert not is_blocked("2026-09-16", gesperrte=gesperrt)
    assert block_reason("2026-09-16", gesperrte=gesperrt) is None


def test_sperrung_ohne_grund_bekommt_standardtext():
    assert block_reason("2026-09-15", gesperrte={"2026-09-15": ""}) == "Gesperrt"


def test_adminsperrung_hat_vorrang_vor_feiertag():
    """Der bewusst gesetzte Grund ist aussagekraeftiger."""
    gesperrt = {"2026-12-25": "Sonderöffnung trotz Feiertag abgesagt"}
    assert block_reason("2026-12-25", gesperrte=gesperrt) == \
        "Sonderöffnung trotz Feiertag abgesagt"


def test_feiertag_gilt_weiter_ohne_adminsperrung():
    assert block_reason("2026-12-25", gesperrte={}).startswith("Feiertag")


def test_ohne_sperrliste_unveraendert():
    """Bestehendes Verhalten darf sich nicht verschieben."""
    assert block_reason("2026-07-01") == "Saisonpause"
    assert block_reason("2026-09-15") is None
    assert not is_blocked("2026-09-15", gesperrte=None)
