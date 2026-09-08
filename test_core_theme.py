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
    DESIGN,
    tokens,
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

def test_jeder_platzhalter_ist_bekannt():
    """Ein fehlender Schluessel wuerde erst beim Seitenaufbau auffallen."""
    import re

    import core_styles

    platzhalter = set(re.findall(r'(?<!\{)\{([a-z_]+)\}(?!\})',
                                 core_styles.CSS_VORLAGE))
    assert platzhalter, "Keine Platzhalter gefunden - Regex pruefen"

    for modus, dunkel in (("Light", False), ("Dark", True)):
        fehlend = sorted(platzhalter - set(tokens(dunkel)))
        assert not fehlend, f"{modus}: unbekannte Platzhalter {fehlend}"


@pytest.mark.parametrize("dunkel", [False, True], ids=["light", "dark"])
def test_stylesheet_baut_sich_vollstaendig(dunkel):
    """Nach dem Einsetzen darf kein Platzhalter uebrig bleiben."""
    import re

    import core_styles

    css = core_styles.build_css(tokens(dunkel))
    assert len(css) > 2000
    assert not re.findall(r'(?<!\{)\{([a-z_]+)\}(?!\})', css)
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


# ===== GESTALTUNGSTOKEN =====
# Halten den Designguide durch. Ohne diese Tests waeren die Leitern in
# DESIGN.md eine Empfehlung; mit ihnen sind sie eine Zusicherung.

def test_alle_gestaltungsgruppen_vorhanden():
    for schluessel in ('font_ui', 'font_mono', 'text_base', 'space_4',
                       'radius_md', 'motion_base', 'ease', 'border_thin'):
        assert schluessel in DESIGN, f"{schluessel} fehlt"


def test_tokens_enthalten_farben_und_gestaltung():
    for dunkel in (False, True):
        alle = tokens(dunkel)
        assert 'bg_primary' in alle      # aus der Palette
        assert 'space_4' in alle         # aus DESIGN


def test_gestaltungstoken_sind_modusunabhaengig():
    """Schrift und Abstaende duerfen sich zwischen hell und dunkel nicht
    unterscheiden - sonst springt das Layout beim Umschalten."""
    hell, dunkel = tokens(False), tokens(True)
    for schluessel in DESIGN:
        assert hell[schluessel] == dunkel[schluessel], schluessel


def test_gestaltung_ueberschreibt_keine_farbe():
    """Ein doppelt vergebener Name wuerde still eine Farbe ersetzen."""
    ueberschneidung = set(DESIGN) & set(LIGHT)
    assert not ueberschneidung, f"Doppelte Namen: {sorted(ueberschneidung)}"


def test_schriftgroessen_steigen_an():
    stufen = ['text_xs', 'text_sm', 'text_base', 'text_lg',
              'text_xl', 'text_2xl', 'text_3xl']
    werte = [float(DESIGN[s].replace('rem', '')) for s in stufen]
    assert werte == sorted(werte), f"Leiter nicht aufsteigend: {werte}"
    assert len(set(werte)) == len(werte), "Doppelte Groessen in der Leiter"


def test_abstaende_steigen_an():
    stufen = [f'space_{i}' for i in range(1, 7)]
    werte = [float(DESIGN[s].replace('rem', '')) for s in stufen]
    assert werte == sorted(werte)
    # Vierer-Leiter: jeder Wert ist ein Vielfaches von 0.25rem (4px)
    for wert in werte:
        assert abs((wert / 0.25) - round(wert / 0.25)) < 1e-9, wert


def test_radien_steigen_an():
    stufen = ['radius_sm', 'radius_md', 'radius_lg']
    werte = [int(DESIGN[s].replace('px', '')) for s in stufen]
    assert werte == sorted(werte)


def test_schriftarten_haben_fallback():
    """Laedt Google Fonts nicht, muss die App trotzdem lesbar bleiben."""
    for schluessel in ('font_ui', 'font_mono'):
        assert ',' in DESIGN[schluessel], f"{schluessel} ohne Ersatzschrift"
    assert 'sans-serif' in DESIGN['font_ui']
    assert 'monospace' in DESIGN['font_mono']


def test_bewegung_bleibt_kurz():
    """Eine Oberflaeche fuer den Alltag darf nicht bei jedem Klick spielen."""
    for schluessel in ('motion_fast', 'motion_base'):
        assert int(DESIGN[schluessel].replace('ms', '')) <= 250


def test_stylesheet_nutzt_die_leitern_statt_eigener_werte():
    """Kein nackter px- oder rem-Wert im CSS - die Leiter ist verbindlich."""
    import re

    import core_styles

    # Vorlage ohne den Font-Import betrachten; der traegt Gewichtsangaben.
    vorlage = core_styles.CSS_VORLAGE.split('*/', 1)[-1]
    ohne_platzhalter = re.sub(r'\{[a-z_]+\}', '', vorlage)

    erlaubt = {
        '0px', '1px', '2px', '3px',   # Umrisse, Versatz, Haarlinien
        '100%', '999px', '44px',      # Vollbreite, Pille, Daumenflaeche
        '1180px', '768px',            # Layoutbreite, Umbruchpunkt
    }
    gefunden = set(re.findall(r'\b\d+(?:\.\d+)?(?:px|rem)\b', ohne_platzhalter))
    unerwartet = gefunden - erlaubt
    assert not unerwartet, (
        f"Werte ausserhalb der Leiter im CSS: {sorted(unerwartet)} - "
        f"passenden Token aus DESIGN verwenden")


def test_sekundaerform_schliesst_hauptaktionen_aus():
    """Sonst sieht die Hauptaktion aus wie eine Nebenaktion.

    '.stFormSubmitButton button' hat eine hoehere Spezifitaet als
    '[data-testid="stBaseButton-primaryFormSubmit"]'. Da beide Seiten
    !important tragen, entscheidet die Spezifitaet - ohne das :not()
    gewinnt die graue Sekundaerform. Im Browser gefunden.
    """
    import core_styles

    for selektor in ('.stButton button', '.stFormSubmitButton button'):
        # Jede Verwendung als Sekundaerform muss den Ausschluss tragen
        for zeile in core_styles.CSS_VORLAGE.split('\n'):
            zeile = zeile.strip().rstrip(',')
            if zeile == selektor:
                raise AssertionError(
                    f"'{selektor}' ohne :not([kind*=\"primary\"]) - "
                    f"ueberschreibt die Hauptaktion")


def test_symbolschrift_bleibt_erhalten():
    """Icons sind Ligaturen - mit der Textschrift wird ein Wort daraus.

    Die Pauschalregel '.stApp *' setzt die Oberflaechenschrift auf alles.
    Ohne die Ausnahme darunter stand im Passwortfeld "visibility" statt
    des Augensymbols. Im Browser gefunden.
    """
    import core_styles

    v = core_styles.CSS_VORLAGE
    assert '[data-testid="stIconMaterial"]' in v, "Ausnahme fuer Icons fehlt"
    assert 'Material Symbols Rounded' in v, "Symbolschrift nicht gesetzt"

    # Die Ausnahme muss NACH der Pauschalregel stehen, sonst verliert sie
    pauschal = v.index('.stApp * {')
    ausnahme = v.index('[data-testid="stIconMaterial"]')
    assert ausnahme > pauschal, (
        "Die Icon-Ausnahme steht vor der Pauschalregel und wird ueberschrieben")
