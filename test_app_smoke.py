"""
Ladetest der App.

Faengt genau die Fehlerklasse, die den Deploy auf Streamlit Cloud gekippt
hat: Ein Paket-Upgrade oder eine entfernte Streamlit-API faellt hier auf,
bevor deployt wird - ohne echte Datenbank und ohne echte Zugangsdaten.

Firestore und die Credentials werden durch Attrappen ersetzt, Streamlit
laeuft im 'bare mode' (ohne 'streamlit run'), in dem die UI-Aufrufe
wirkungslos sind, aber trotzdem auf Existenz geprueft werden.

    python -m pytest test_app_smoke.py -v
"""
import sys
import types
from unittest import mock

import pytest

streamlit = pytest.importorskip("streamlit", reason="Streamlit nicht installiert")
pytest.importorskip("twilio", reason="twilio nicht installiert")
pytest.importorskip("plotly", reason="plotly nicht installiert")
pytest.importorskip("pandas", reason="pandas nicht installiert")

GEHEIMNISSE = {
    'firebase': {'project_id': 'test-projekt'},
    'ADMIN_EMAIL': 'admin@test.de',
    'ADMIN_PASSWORD': 'geheim',
    'ADMIN_EMAIL_RECEIVER': 'empfang@test.de',
    'SMTP_SERVER': 'smtp.test.de',
    'SMTP_PORT': 587,
    'SMTP_USER': 'user@test.de',
    'SMTP_PASSWORD': 'pw',
    'ENABLE_SMS_REMINDER': 'false',
}


class FakeSecrets(dict):
    """st.secrets verhaelt sich wie ein Dict mit .get()."""
    def get(self, key, default=None):
        return super().get(key, default)


@pytest.fixture(scope="module")
def app():
    """Laedt streamlit_app mit Attrappen statt echter Datenbank."""
    fake_firestore = types.ModuleType('google.cloud.firestore')
    fake_firestore.Client = mock.MagicMock()
    fake_firestore.SERVER_TIMESTAMP = 'SERVER_TIMESTAMP'
    fake_firestore.DELETE_FIELD = 'DELETE_FIELD'
    sys.modules['google.cloud.firestore'] = fake_firestore

    with mock.patch.object(streamlit, 'secrets', FakeSecrets(GEHEIMNISSE)), \
         mock.patch('google.oauth2.service_account.Credentials.'
                    'from_service_account_info', return_value=mock.MagicMock()):
        import streamlit_app
        return streamlit_app


def test_app_laedt(app):
    """Der reine Import muss durchlaufen - sonst startet die App nicht."""
    assert app.VERSION


def test_alle_seiten_vorhanden(app):
    """Der Router in main() verweist auf diese Funktionen."""
    seiten = ['kalender_page', 'meine_buchungen_page', 'profil_page',
              'statistik_page', 'verwaltung_page', 'benutzer_page',
              'export_page', 'debug_page', 'handbuch_page',
              'impressum_page', 'vorlagen_page', 'login_page']
    for name in seiten:
        assert callable(getattr(app, name, None)), f"{name} fehlt"


def test_zentrale_funktionen_vorhanden(app):
    for name in ['main', 'inject_css', 'show_navigation', 'notify_pref',
                 'wants_sms', 'can_cancel', 'is_blocked', 'block_reason',
                 'get_pause_range', 'get_cancel_deadline_hours',
                 'get_session_timeout_minutes']:
        assert callable(getattr(app, name, None)), f"{name} fehlt"


def test_klassen_vorhanden(app):
    for name in ['WasserwachtDB', 'Mailer', 'TwilioSMS']:
        assert getattr(app, name, None) is not None, f"{name} fehlt"


def test_benachrichtigungen_altes_schema_wirkt(app):
    """Bestandsnutzer haben nur die Altfelder - die muessen greifen."""
    assert app.notify_pref({'email_notifications': True}, 'email', 'booking')
    assert not app.notify_pref({'email_notifications': False}, 'email', 'booking')


def test_benachrichtigungen_neues_schema_hat_vorrang(app):
    nutzer = {'email_notifications': True, 'email_notifications_booking': False}
    assert not app.notify_pref(nutzer, 'email', 'booking')


def test_sms_nur_mit_telefonnummer(app):
    assert not app.wants_sms({'sms_notifications_booking': True}, 'booking')
    assert app.wants_sms(
        {'phone': '0172123', 'sms_notifications_booking': True}, 'booking')


def test_wochenslots_vollstaendig(app):
    assert len(app.WEEKLY_SLOTS) == 3
    for slot in app.WEEKLY_SLOTS:
        assert {'day', 'day_name', 'start', 'end'} <= set(slot)


def test_streamlit_apis_vorhanden():
    """Von der App genutzte Streamlit-Aufrufe - faengt entfernte APIs."""
    benutzt = [
        'set_page_config', 'tabs', 'form', 'form_submit_button', 'rerun',
        'cache_resource', 'date_input', 'number_input', 'download_button',
        'metric', 'plotly_chart', 'text_input', 'text_area', 'selectbox',
        'checkbox', 'columns', 'expander', 'divider', 'caption', 'balloons',
        'stop', 'container', 'markdown', 'code', 'button', 'title', 'error',
        'success', 'warning', 'info', 'sidebar', 'session_state',
    ]
    fehlend = [name for name in benutzt if not hasattr(streamlit, name)]
    assert not fehlend, f"Streamlit kennt diese Aufrufe nicht mehr: {fehlend}"


def test_firestore_where_weiterhin_nutzbar():
    """Die App nutzt positionales where() an vielen Stellen."""
    from google.cloud import firestore as echtes_firestore
    if isinstance(echtes_firestore, types.ModuleType) and \
            not hasattr(echtes_firestore, 'Query'):
        pytest.skip("Firestore ist in diesem Lauf durch eine Attrappe ersetzt")
    assert hasattr(echtes_firestore, 'SERVER_TIMESTAMP')
    assert hasattr(echtes_firestore, 'DELETE_FIELD')


# ===== ANGEMELDET BLEIBEN =====

def test_cookie_funktionen_vorhanden(app):
    for name in ['get_cookie_manager', 'cookie_lesen', 'cookie_setzen',
                 'cookie_loeschen', 'get_remember_days',
                 'sitzung_aus_cookie_wiederherstellen']:
        assert callable(getattr(app, name, None)), f"{name} fehlt"


def test_datenbank_kann_dauersitzungen(app):
    for name in ['create_session', 'get_session_user', 'delete_session',
                 'delete_sessions_of_user']:
        assert callable(getattr(app.WasserwachtDB, name, None)), f"{name} fehlt"


def test_cookie_fehler_sperrt_niemanden_aus(app, monkeypatch):
    """Faellt das Cookie-Handling aus, muss der normale Login weiter gehen."""
    def kaputt(*a, **kw):
        raise RuntimeError("Komponente nicht erreichbar")
    monkeypatch.setattr(app, 'get_cookie_manager', kaputt)

    assert app.cookie_lesen('irgendwas') is None
    assert app.cookie_setzen('a', 'b', 30) is False
    assert app.cookie_loeschen('a') is False


def test_cookie_manager_ist_nicht_gecacht(app):
    """Regression: @st.cache_resource auf dem Cookie-Manager brach die App.

    Sein Konstruktor rendert eine Komponente. Streamlit verbietet Widgets in
    gecachten Funktionen und wirft CachedWidgetWarning - der Fehler trat auf,
    bevor sich ueberhaupt jemand anmelden konnte. Gecachte Funktionen sind
    keine gewoehnlichen Funktionen, sie tragen ein .clear().
    """
    assert not hasattr(app.get_cookie_manager, 'clear'), (
        "get_cookie_manager ist gecacht - der Konstruktor rendert aber eine "
        "Komponente. Cache entfernen.")


def test_keine_widgets_in_gecachten_funktionen():
    """Nur bekannte, widgetfreie Funktionen duerfen gecacht sein."""
    import pathlib
    import re

    quelle = (pathlib.Path(__file__).parent / 'streamlit_app.py').read_text(
        encoding='utf-8')
    gecacht = re.findall(
        r'@st\.cache_(?:resource|data)[^\n]*\ndef\s+(\w+)', quelle)

    # init_firestore erzeugt nur einen Datenbank-Client, kein UI-Element.
    erlaubt = {'init_firestore'}
    unerwartet = set(gecacht) - erlaubt
    assert not unerwartet, (
        f"Neu gecachte Funktionen pruefen, ob sie Streamlit-Elemente "
        f"erzeugen: {sorted(unerwartet)}")


# ===== VOM ADMIN GESPERRTE TERMINE =====

def test_sperr_funktionen_vorhanden(app):
    for name in ['get_blocked_dates', 'user_email_admin']:
        assert callable(getattr(app, name, None)), f"{name} fehlt"
    for name in ['get_blocked_dates', 'block_dates', 'unblock_date',
                 'set_booking_note']:
        assert callable(getattr(app.WasserwachtDB, name, None)), f"{name} fehlt"


def test_gesperrter_termin_ist_nicht_buchbar(app, monkeypatch):
    """Verhalten, nicht nur Existenz: die Sperrliste muss durchschlagen."""
    monkeypatch.setattr(app, 'get_blocked_dates',
                        lambda neu_laden=False: {"2026-10-13": "Bad geschlossen"})
    monkeypatch.setattr(app, 'get_pause_range', lambda: ("06-01", "09-14"))

    assert app.is_blocked("2026-10-13")
    assert app.block_reason("2026-10-13") == "Bad geschlossen"
    # Nachbartag bleibt frei
    assert not app.is_blocked("2026-10-14")
    assert app.block_reason("2026-10-14") is None


def test_ohne_sperrung_gelten_weiter_feiertag_und_pause(app, monkeypatch):
    monkeypatch.setattr(app, 'get_blocked_dates', lambda neu_laden=False: {})
    monkeypatch.setattr(app, 'get_pause_range', lambda: ("06-01", "09-14"))

    assert app.is_blocked("2026-12-25")
    assert app.block_reason("2026-12-25").startswith("Feiertag")
    assert app.is_blocked("2026-07-01")
    assert app.block_reason("2026-07-01") == "Saisonpause"


# ===== NEUE FUNKTIONEN =====

def test_datenschutzseite_vorhanden(app):
    assert callable(getattr(app, 'datenschutz_page', None))


def test_vertretung_und_bilanz_vorhanden(app):
    for name in ['saison_zeitraum', 'dienstdauer_stunden']:
        assert callable(getattr(app, name, None)), f"{name} fehlt"
    for name in ['set_replacement_wanted', 'takeover_booking']:
        assert callable(getattr(app.WasserwachtDB, name, None)), f"{name} fehlt"


def test_buchung_hat_transaktion_und_rueckfall(app):
    """Beide Wege muessen existieren - der Rueckfall traegt die Verfuegbarkeit."""
    for name in ['_buchung_transaktional', '_buchung_einfach']:
        assert callable(getattr(app.WasserwachtDB, name, None)), f"{name} fehlt"


def test_module_fuer_kalender_und_import_eingebunden(app):
    assert callable(getattr(app.ics, 'baue_ics', None))
    assert callable(getattr(app.nutzerimport, 'lies_nutzerliste', None))


def test_dienstdauer_ueber_die_app(app):
    assert app.dienstdauer_stunden({'slot_time': '17:00 - 20:00'}) == 3.0


def test_router_kennt_datenschutz():
    """Die Seite muss auch erreichbar sein, nicht nur existieren."""
    import pathlib
    quelle = (pathlib.Path(__file__).parent / 'streamlit_app.py').read_text(
        encoding='utf-8')
    assert "elif page == 'datenschutz':" in quelle
    assert "('datenschutz', " in quelle


# ===== STATISTIK =====

def test_statistikmodul_eingebunden(app):
    for name in ['rangliste', 'eintrag_von', 'abstand_nach_oben',
                 'saisons_in_daten', 'im_zeitraum', 'kennzahlen']:
        assert callable(getattr(app.stats, name, None)), f"{name} fehlt"


def test_rangliste_ueber_die_app(app):
    """Verhalten, nicht nur Existenz."""
    daten = [{'user_email': 'a@x.de', 'user_name': 'Anna',
              'slot_date': '2026-10-01', 'slot_time': '17:00 - 20:00'}] * 2
    daten.append({'user_email': 'b@x.de', 'user_name': 'Bert',
                  'slot_date': '2026-10-02', 'slot_time': '17:00 - 20:00'})
    liste = app.stats.rangliste(daten)
    assert liste[0]['name'] == 'Anna'
    assert liste[0]['platz'] == 1
    assert liste[0]['medaille'] == '🥇'


def test_stylesheet_fehler_legt_die_app_nicht_lahm(app, monkeypatch):
    """Ein veraltetes Modul im Speicher darf keinen Traceback zeigen.

    Genau das trat nach einem Code-Push auf: Streamlit Cloud lud das
    Hauptskript neu, behielt core_theme aber im alten Stand - die App war
    komplett unbedienbar, statt nur unformatiert zu sein.
    """
    class VeraltetesModul:
        def palette(self, dark=False):
            return {}
        # tokens() fehlt absichtlich - wie im alten Modulstand

    monkeypatch.setattr(app, 'theme', VeraltetesModul())
    app.inject_css(dark=True)   # darf nicht werfen


def test_keine_fest_verdrahteten_farben_in_der_app():
    """Farben gehoeren in core_theme, nicht in die Oberflaeche.

    Bis zuletzt trug streamlit_app.py eine eigene 15-Farben-Palette aus
    V8.1 und einen Theme-Umschalter mit fuenf festen Hexwerten. Beides ging
    am Tokensystem vorbei und sah im Dark Mode entsprechend fremd aus.
    """
    import pathlib
    import re

    quelle = (pathlib.Path(__file__).parent / 'streamlit_app.py').read_text(
        encoding='utf-8')
    treffer = re.findall(r'["\']#[0-9A-Fa-f]{3,8}["\']', quelle)
    assert not treffer, (
        f"Feste Farbwerte in streamlit_app.py: {sorted(set(treffer))} - "
        f"gehoeren nach core_theme")


def test_diagramme_folgen_der_palette(app):
    """Plotly folgt sonst Streamlits Theme aus config.toml.

    Das steht fest auf dunkel, waehrend die App umschaltbar ist - im Light
    Mode standen schwarze Diagramme auf heller Seite. Im Browser gesehen.
    """
    import plotly.express as px

    fig = app.diagramm_stil(px.bar(x=['a', 'b'], y=[1, 2]))
    farben = app.aktuelle_farben()
    assert fig.layout.paper_bgcolor == farben['bg_secondary']
    assert fig.layout.plot_bgcolor == farben['bg_secondary']
    assert fig.layout.font.color == farben['text_secondary']


def test_diagramme_werden_ohne_streamlit_theme_gezeichnet():
    """theme=None ist noetig, sonst legt Streamlit sein Theme obendrauf."""
    import pathlib
    import re

    quelle = (pathlib.Path(__file__).parent / 'streamlit_app.py').read_text(
        encoding='utf-8')
    for aufruf in re.findall(r'st\.plotly_chart\((?:[^()]|\([^()]*\))*\)', quelle):
        assert 'theme=None' in aufruf, f"ohne theme=None: {aufruf[:70]}"


def test_anmelde_cookie_wird_nicht_vor_einem_rerun_geschrieben():
    """Regression: 'Angemeldet bleiben' setzte nie ein Cookie.

    Die Cookie-Komponente schreibt erst, wenn sie im Browser gerendert
    wurde. Im Anmeldeformular folgte direkt danach ein st.rerun(), das den
    Durchlauf abbrach - der Auftrag erreichte den Browser nie. Serverseitig
    stimmte alles, im Browser fehlte das Cookie. Nur live zu finden.

    Der Schreibvorgang wird jetzt vorgemerkt und in main() ausgefuehrt.
    """
    import pathlib
    import re

    quelle = (pathlib.Path(__file__).parent / 'streamlit_app.py').read_text(
        encoding='utf-8')

    # Im Anmeldeformular darf nicht direkt geschrieben werden
    anmelde_block = quelle[quelle.index('def login_page'):
                           quelle.index('def logout')]
    assert 'cookie_setzen(' not in anmelde_block, (
        "login_page schreibt das Cookie direkt - vor dem rerun wirkungslos")
    assert 'cookie_spaeter_setzen(' in anmelde_block

    # In main() muss der Auftrag abgearbeitet werden
    main_block = quelle[quelle.index('def main():'):]
    assert 'ausstehenden_cookie_schreiben()' in main_block

    # Und danach darf in main() kein sofortiges rerun folgen
    nach_schreiben = main_block[main_block.index('ausstehenden_cookie_schreiben()'):]
    naechste_zeilen = nach_schreiben.split('\n')[1:6]
    assert not any(re.match(r'\s*st\.rerun\(\)', z) for z in naechste_zeilen), (
        "rerun direkt nach dem Schreiben macht es wieder wirkungslos")


def test_cookie_auftrag_wird_vorgemerkt_und_abgeraeumt(app, monkeypatch):
    """Der Auftrag darf nicht liegenbleiben und bei jedem Lauf erneut feuern."""
    geschrieben = []
    monkeypatch.setattr(app, 'cookie_setzen',
                        lambda name, wert, tage: geschrieben.append(name) or True)

    app.st.session_state.clear()
    app.cookie_spaeter_setzen('token123', 30)
    assert 'cookie_zu_setzen' in app.st.session_state

    app.ausstehenden_cookie_schreiben()
    assert geschrieben == [app.SESSION_COOKIE_NAME]
    assert 'cookie_zu_setzen' not in app.st.session_state

    # Zweiter Durchlauf schreibt nichts mehr
    app.ausstehenden_cookie_schreiben()
    assert len(geschrieben) == 1
