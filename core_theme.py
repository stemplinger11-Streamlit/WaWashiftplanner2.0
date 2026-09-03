"""
Farbpaletten der App - mit nachpruefbarem Kontrast.

Der Light Mode war unlesbar, weil zwei Dinge zusammenkamen:

1. Einzelne Farbwerte hatten zu wenig Kontrast (text_muted #999999 auf
   Weiss erreicht 2,85:1, WCAG AA verlangt 4,5:1).
2. Eigene Container wie .slot-card setzten zwar einen Hintergrund, aber
   keine Textfarbe. Der Text erbte damit Streamlits eigenes Theme - lief
   der Browser auf dunkel, stand weisse Schrift auf hellem Grund (1,1:1).

Deshalb liegen die Farben jetzt hier, jede Kombination wird von
test_core_theme.py gegen WCAG AA geprueft, und jeder Container bekommt in
inject_css() eine ausdrueckliche Textfarbe.

Bewusst frei von Streamlit-Abhaengigkeiten.
"""

# WCAG 2.1 Schwellen
AA_NORMAL = 4.5   # Fliesstext
AA_GROSS = 3.0    # ab 18pt bzw. 14pt fett, sowie UI-Begrenzungen


def _kanal(wert):
    wert = wert / 255
    return wert / 12.92 if wert <= 0.03928 else ((wert + 0.055) / 1.055) ** 2.4


def leuchtdichte(hexfarbe):
    """Relative Leuchtdichte nach WCAG 2.1."""
    h = hexfarbe.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _kanal(r) + 0.7152 * _kanal(g) + 0.0722 * _kanal(b)


def kontrast(farbe_a, farbe_b):
    """Kontrastverhaeltnis zweier Farben (1:1 bis 21:1)."""
    hell, dunkel = sorted((leuchtdichte(farbe_a), leuchtdichte(farbe_b)),
                          reverse=True)
    return (hell + 0.05) / (dunkel + 0.05)


# ===== LIGHT MODE =====
# Akzente treten in zwei Rollen auf: als Flaeche/Rahmen (kraeftig) und als
# Schrift auf hellem Grund (dunkler, damit lesbar). Deshalb je zwei Werte.
LIGHT = {
    'bg_primary':   '#F6F8FB',   # Seitenhintergrund
    'bg_secondary': '#FFFFFF',   # Karten
    'bg_surface':   '#EDF1F6',   # abgesetzte Flaechen
    'bg_elevated':  '#FFFFFF',   # Eingabefelder

    'text_primary':   '#14181F',
    'text_secondary': '#48525F',
    'text_muted':     '#5C6675',

    'accent_blue':   '#1565C0',
    'accent_blue_hover': '#0F4C96',
    'accent_red':    '#B3261E',
    'accent_green':  '#1B6E2F',
    'accent_orange': '#B26A00',

    # Akzente als Schrift auf hellem Grund
    'accent_blue_text':   '#0F4C96',
    'accent_red_text':    '#96201A',
    'accent_green_text':  '#155724',
    'accent_orange_text': '#84500A',

    'border_color':  '#D3DAE3',
    'divider_color': '#B9C2CE',

    'slot_free_bg':       '#E7F1FD',
    'slot_free_border':   '#1565C0',
    'slot_booked_bg':     '#FDF1E2',
    'slot_booked_border': '#B26A00',
    'slot_blocked_bg':    '#ECEFF3',
    'slot_blocked_border': '#78828F',

    'on_accent': '#FFFFFF',      # Schrift auf gefuellten Akzentflaechen

    'input_shadow': '0 1px 3px rgba(16, 24, 40, 0.10), 0 0 0 1px rgba(16, 24, 40, 0.04)',
    'card_shadow': '0 2px 4px rgba(16, 24, 40, 0.08), 0 1px 2px rgba(16, 24, 40, 0.05)',
    'card_shadow_hover': '0 6px 14px rgba(16, 24, 40, 0.13), 0 2px 5px rgba(16, 24, 40, 0.08)',
}

# ===== DARK MODE =====
DARK = {
    'bg_primary':   '#161B2C',
    'bg_secondary': '#212739',
    'bg_surface':   '#2A3149',
    'bg_elevated':  '#333B57',

    'text_primary':   '#F4F7FB',
    'text_secondary': '#C2CCDB',
    'text_muted':     '#A2AEC0',

    'accent_blue':   '#6FB6F0',
    'accent_blue_hover': '#8CC6F5',
    'accent_red':    '#FF8A8A',
    'accent_green':  '#63D178',
    'accent_orange': '#FFC062',

    # Im Dark Mode sind die hellen Akzente bereits als Schrift geeignet
    'accent_blue_text':   '#8CC6F5',
    'accent_red_text':    '#FF9F9F',
    'accent_green_text':  '#7FDC90',
    'accent_orange_text': '#FFCE85',

    'border_color':  '#3D4562',
    'divider_color': '#4C5573',

    'slot_free_bg':       '#20395A',
    'slot_free_border':   '#6FB6F0',
    'slot_booked_bg':     '#42301A',
    'slot_booked_border': '#FFC062',
    'slot_blocked_bg':    '#2E3444',
    'slot_blocked_border': '#7C8798',

    'on_accent': '#10131C',

    'input_shadow': '0 2px 8px rgba(0, 0, 0, 0.32), 0 0 0 1px rgba(255, 255, 255, 0.06)',
    'card_shadow': '0 4px 12px rgba(0, 0, 0, 0.40), 0 1px 3px rgba(0, 0, 0, 0.24)',
    'card_shadow_hover': '0 8px 18px rgba(0, 0, 0, 0.50), 0 2px 6px rgba(0, 0, 0, 0.32)',
}


def palette(dark=False):
    return DARK if dark else LIGHT


# Jede Kombination, die in inject_css() tatsaechlich vorkommt.
# (Schriftfarbe, Hintergrund, Mindestkontrast, Beschreibung)
KONTRAST_PAARE = [
    ('text_primary', 'bg_primary', AA_NORMAL, 'Fliesstext auf Seite'),
    ('text_primary', 'bg_secondary', AA_NORMAL, 'Fliesstext auf Karte'),
    ('text_primary', 'bg_surface', AA_NORMAL, 'Fliesstext auf Flaeche'),
    ('text_primary', 'bg_elevated', AA_NORMAL, 'Text im Eingabefeld'),

    ('text_secondary', 'bg_primary', AA_NORMAL, 'Sekundaertext auf Seite'),
    ('text_secondary', 'bg_secondary', AA_NORMAL, 'Sekundaertext auf Karte'),
    ('text_muted', 'bg_primary', AA_NORMAL, 'Hilfstext auf Seite'),
    ('text_muted', 'bg_secondary', AA_NORMAL, 'Hilfstext auf Karte'),
    ('text_muted', 'bg_surface', AA_NORMAL, 'Hilfstext auf Flaeche'),

    # Slot-Karten: Text steht ausdruecklich in text_primary
    ('text_primary', 'slot_free_bg', AA_NORMAL, 'Text auf freiem Slot'),
    ('text_primary', 'slot_booked_bg', AA_NORMAL, 'Text auf gebuchtem Slot'),
    ('text_primary', 'slot_blocked_bg', AA_NORMAL, 'Text auf gesperrtem Slot'),
    ('text_secondary', 'slot_free_bg', AA_NORMAL, 'Zusatz auf freiem Slot'),
    ('text_secondary', 'slot_booked_bg', AA_NORMAL, 'Zusatz auf gebuchtem Slot'),
    ('text_secondary', 'slot_blocked_bg', AA_NORMAL, 'Zusatz auf gesperrtem Slot'),

    # Badges: Akzentschrift auf der jeweiligen Slot-Flaeche
    ('accent_blue_text', 'slot_free_bg', AA_NORMAL, 'Badge frei'),
    ('accent_orange_text', 'slot_booked_bg', AA_NORMAL, 'Badge gebucht'),
    ('accent_blue_text', 'bg_secondary', AA_NORMAL, 'Akzenttext auf Karte'),
    ('accent_red_text', 'bg_secondary', AA_NORMAL, 'Fehlertext auf Karte'),
    ('accent_green_text', 'bg_secondary', AA_NORMAL, 'Erfolgstext auf Karte'),
    ('accent_orange_text', 'bg_secondary', AA_NORMAL, 'Warntext auf Karte'),

    # Gefuellte Schaltflaechen
    ('on_accent', 'accent_blue', AA_NORMAL, 'Schrift auf blauem Button'),
    ('on_accent', 'accent_blue_hover', AA_NORMAL, 'Schrift auf blauem Button (Hover)'),
    ('on_accent', 'accent_red', AA_NORMAL, 'Schrift auf rotem Button'),
    ('on_accent', 'accent_green', AA_NORMAL, 'Schrift auf gruenem Button'),

    # Rahmen und Trenner brauchen nur UI-Kontrast
    ('border_color', 'bg_secondary', 1.3, 'Rahmen sichtbar'),
    ('slot_free_border', 'slot_free_bg', AA_GROSS, 'Rahmen freier Slot'),
    ('slot_booked_border', 'slot_booked_bg', AA_GROSS, 'Rahmen gebuchter Slot'),
]


def pruefe_palette(dark=False):
    """Alle Paare pruefen -> Liste der Verstoesse."""
    p = palette(dark)
    verstoesse = []
    for vorne, hinten, minimum, beschreibung in KONTRAST_PAARE:
        wert = kontrast(p[vorne], p[hinten])
        if wert < minimum:
            verstoesse.append((beschreibung, vorne, hinten, round(wert, 2), minimum))
    return verstoesse
