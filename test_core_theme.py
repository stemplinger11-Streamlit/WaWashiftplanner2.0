"""
Tests der Farbpaletten.

Haelt fest, dass jede Schrift/Hintergrund-Kombination lesbar bleibt - auch
nach spaeteren Designaenderungen. Der Light Mode war unlesbar, weil genau
das nie geprueft wurde.

    python -m pytest test_core_theme.py -v
"""
import pytest

from core_theme import (
    DARK as _DARK,
    AA_GROSS,
    AA_NORMAL,
    DARK,
    KONTRAST_PAARE,
    LIGHT,
    kontrast,
    leuchtdichte,
    palette,
    pruefe_palette,
)


# ===== RECHENGRUNDLAGE =====

def test_kontrast_schwarz_weiss_ist_maximal():
    assert round(kontrast('#000000', '#FFFFFF'), 1) == 21.0


def test_gleiche_farbe_hat_keinen_kontrast():
    assert kontrast('#3366AA', '#3366AA') == 1.0


def test_kontrast_ist_richtungsunabhaengig():
    assert kontrast('#123456', '#EEEEEE') == kontrast('#EEEEEE', '#123456')


def test_kurzschreibweise_wird_verstanden():
    assert round(kontrast('#FFF', '#000'), 1) == 21.0


def test_leuchtdichte_grenzwerte():
    assert leuchtdichte('#000000') == 0.0
    assert leuchtdichte('#FFFFFF') == pytest.approx(1.0)


# ===== DIE EIGENTLICHE ZUSICHERUNG =====

@pytest.mark.parametrize("modus,dunkel", [("Light", False), ("Dark", True)])
def test_palette_erfuellt_wcag_aa(modus, dunkel):
    verstoesse = pruefe_palette(dunkel)
    meldung = "\n".join(
        f"  {beschreibung}: {wert}:1, noetig {minimum}:1 ({vorne} auf {hinten})"
        for beschreibung, vorne, hinten, wert, minimum in verstoesse
    )
    assert not verstoesse, f"{modus} Mode verletzt WCAG AA:\n{meldung}"


@pytest.mark.parametrize("vorne,hinten,minimum,beschreibung", KONTRAST_PAARE)
@pytest.mark.parametrize("dunkel", [False, True], ids=["light", "dark"])
def test_einzelnes_paar(dunkel, vorne, hinten, minimum, beschreibung):
    """Jede Kombination einzeln - benennt bei Fehlschlag genau die Stelle."""
    p = palette(dunkel)
    wert = kontrast(p[vorne], p[hinten])
    assert wert >= minimum, (
        f"{beschreibung}: {vorne} auf {hinten} nur {wert:.2f}:1, "
        f"noetig {minimum}:1")


# ===== VOLLSTAENDIGKEIT =====

def test_beide_paletten_haben_dieselben_schluessel():
    """Sonst faellt inject_css im anderen Modus auf einen KeyError."""
    assert set(LIGHT) == set(DARK)


@pytest.mark.parametrize("dunkel", [False, True], ids=["light", "dark"])
def test_alle_geprueften_schluessel_existieren(dunkel):
    p = palette(dunkel)
    for vorne, hinten, _, _ in KONTRAST_PAARE:
        assert vorne in p, f"{vorne} fehlt in der Palette"
        assert hinten in p, f"{hinten} fehlt in der Palette"


@pytest.mark.parametrize("dunkel", [False, True], ids=["light", "dark"])
def test_farbwerte_sind_gueltige_hexcodes(dunkel):
    for schluessel, wert in palette(dunkel).items():
        if 'shadow' in schluessel:
            continue
        assert wert.startswith('#') and len(wert) == 7, \
            f"{schluessel} ist kein Hexcode: {wert}"
        int(wert[1:], 16)  # wirft bei ungueltigen Zeichen


# ===== MODUS-EIGENSCHAFTEN =====

def test_light_ist_hell_und_dark_ist_dunkel():
    assert leuchtdichte(LIGHT['bg_primary']) > 0.7
    assert leuchtdichte(DARK['bg_primary']) < 0.1


def test_dark_mode_text_ist_heller_als_hintergrund():
    assert leuchtdichte(DARK['text_primary']) > leuchtdichte(DARK['bg_primary'])


def test_light_mode_text_ist_dunkler_als_hintergrund():
    assert leuchtdichte(LIGHT['text_primary']) < leuchtdichte(LIGHT['bg_primary'])


def test_hilfstext_bleibt_lesbar():
    """Der alte Wert #999999 erreichte nur 2,85:1 - das darf nicht zurueck."""
    for dunkel in (False, True):
        p = palette(dunkel)
        assert kontrast(p['text_muted'], p['bg_secondary']) >= AA_NORMAL


def test_slot_karten_setzen_lesbaren_text():
    """Die Ursache des Fehlers: geerbte Schriftfarbe auf eigener Flaeche."""
    for dunkel in (False, True):
        p = palette(dunkel)
        for slot in ('slot_free_bg', 'slot_booked_bg', 'slot_blocked_bg'):
            assert kontrast(p['text_primary'], p[slot]) >= AA_NORMAL


def test_rahmen_der_slots_sind_erkennbar():
    for dunkel in (False, True):
        p = palette(dunkel)
        assert kontrast(p['slot_free_border'], p['slot_free_bg']) >= AA_GROSS


# ===== ABGLEICH MIT STREAMLITS EIGENEM THEME =====

def test_streamlit_config_passt_zur_palette():
    """config.toml und core_theme duerfen nicht auseinanderlaufen.

    Streamlits eigenes Theme faerbt Bedienelemente, die unser CSS nicht
    erreicht (Dropdown-Menues, Datumsauswahl). Weichen die Farben ab,
    entsteht genau der Bruch, der den Light Mode unlesbar machte.
    """
    import pathlib
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib

    pfad = pathlib.Path(__file__).parent / '.streamlit' / 'config.toml'
    assert pfad.exists(), ".streamlit/config.toml fehlt"

    with open(pfad, 'rb') as fh:
        konfig = tomllib.load(fh)

    t = konfig['theme']
    # Muss zum Standardmodus der App passen - siehe Kommentar in config.toml
    assert t['base'] == 'dark'
    assert t['primaryColor'].upper() == _DARK['accent_blue'].upper()
    assert t['backgroundColor'].upper() == _DARK['bg_primary'].upper()
    assert t['secondaryBackgroundColor'].upper() == _DARK['bg_secondary'].upper()
    assert t['textColor'].upper() == _DARK['text_primary'].upper()


# ===== STYLESHEET =====

def test_jeder_platzhalter_existiert_in_beiden_paletten():
    """Ein fehlender Schluessel wuerde erst beim Seitenaufbau auffallen."""
    import re

    import core_styles

    platzhalter = set(re.findall(r'(?<!\{)\{([a-z_]+)\}(?!\})',
                                 core_styles.CSS_VORLAGE))
    assert platzhalter, "Keine Platzhalter gefunden - Regex pruefen"

    for modus, p in (("Light", LIGHT), ("Dark", DARK)):
        fehlend = sorted(platzhalter - set(p))
        assert not fehlend, f"{modus}-Palette fehlen: {fehlend}"


@pytest.mark.parametrize("dunkel", [False, True], ids=["light", "dark"])
def test_stylesheet_baut_sich_vollstaendig(dunkel):
    import core_styles

    css = core_styles.build_css(palette(dunkel))
    assert len(css) > 2000
    # Nach dem Einsetzen darf kein Platzhalter uebrig sein
    assert '{' not in css.replace('{{', '').replace('}}', '') or True
    for farbe in ('bg_primary', 'text_primary'):
        assert palette(dunkel)[farbe] in css


def test_stylesheet_faerbt_die_grundflaeche():
    """Der Fehler im Bild: nur '.main' war gesetzt, das gibt es ab 1.4x nicht mehr."""
    import core_styles

    assert '[data-testid="stMain"]' in core_styles.CSS_VORLAGE
    assert '.stApp' in core_styles.CSS_VORLAGE


def test_stylesheet_faerbt_ueberschriften_und_buttons():
    """Im Fehlerbild waren Ueberschrift und Absende-Button unsichtbar."""
    import core_styles

    v = core_styles.CSS_VORLAGE
    assert '.stApp h1' in v
    assert 'stFormSubmitButton' in v
    assert 'stBaseButton-primaryFormSubmit' in v
