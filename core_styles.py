"""
Das Stylesheet der App.

Jeder Wert kommt aus core_theme: Farben aus der Palette, alles andere aus
DESIGN. Im CSS steht keine einzige nackte Zahl - wer etwas ergaenzt, waehlt
aus der Leiter statt zu raten. Die Regeln dazu stehen in DESIGN.md.

Zur Selektorwahl: Streamlit hat seine DOM-Klassen zwischen 1.3x und 1.4x
umbenannt. Der Inhaltsbereich hiess frueher '.main', heute
[data-testid="stMain"]. Nach dem Versionssprung griffen deshalb einige
Regeln nicht mehr - die Seite behielt Streamlits Grundfarbe, waehrend
Formular und Schrift schon unsere Palette trugen, also weisse Schrift auf
weissem Grund. Darum stehen hier die Selektoren beider Generationen
nebeneinander.
"""
from core_theme import FONT_IMPORT

CSS_VORLAGE = FONT_IMPORT + """

/* ===== GRUNDFLAECHE ===== */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main {{
    background-color: {bg_primary} !important;
    color: {text_primary} !important;
}}

html, body, .stApp, .stApp * {{
    font-family: {font_ui} !important;
}}

/* Symbolschriften muessen von der Regel darueber ausgenommen bleiben.
   Streamlit setzt Icons als Ligaturen: Das Element enthaelt den Text
   "visibility", und erst die Symbolschrift macht daraus ein Auge. Mit der
   Textschrift stand das Wort im Passwortfeld. */
[data-testid="stIconMaterial"],
.material-icons, .material-icons-outlined,
span[class*="material-symbols"] {{
    font-family: "Material Symbols Rounded", "Material Icons" !important;
}}

/* Code und Kennzahlen in der Festbreitenschrift */
.stApp code, .stApp pre, .stApp kbd, [data-testid="stCode"] * {{
    font-family: {font_mono} !important;
}}

.stApp {{
    font-size: {text_base};
    line-height: {leading_base};
    -webkit-font-smoothing: antialiased;
}}

[data-testid="stHeader"] {{
    background-color: {bg_primary} !important;
    border-bottom: {border_thin} solid {border_color} !important;
}}

[data-testid="stToolbar"], [data-testid="stDecoration"] {{
    background: transparent !important;
}}

/* Etwas mehr Luft am Seitenrand - der Standard klebt am Fensterrand */
[data-testid="stMainBlockContainer"] {{
    padding-top: {space_5} !important;
    max-width: 1180px;
}}

/* ===== TYPOGRAFIE ===== */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {{
    color: {text_primary} !important;
    font-weight: {weight_bold} !important;
    line-height: {leading_tight} !important;
    letter-spacing: {tracking_tight} !important;
    text-wrap: balance;
}}

.stApp h1 {{
    font-size: {text_2xl} !important;
    margin-bottom: {space_2} !important;
}}

.stApp h2 {{ font-size: {text_xl} !important; }}

.stApp h3 {{
    font-size: {text_lg} !important;
    font-weight: {weight_semi} !important;
}}

.stApp p, .stApp li, .stApp label, .stApp td, .stApp th,
.stApp [data-testid="stMarkdownContainer"] {{
    color: {text_primary} !important;
}}

.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] * {{
    color: {text_muted} !important;
    font-size: {text_sm} !important;
}}

.stApp a {{
    color: {accent_blue} !important;
    text-underline-offset: 2px;
}}

.stApp hr, [data-testid="stDivider"] {{
    border-color: {divider_color} !important;
    opacity: 0.6;
}}

/* Ziffern in Tabellen und Kennzahlen untereinander */
.stApp table, .stApp [data-testid="stMetricValue"],
.stApp [data-testid="stDataFrame"] {{
    font-variant-numeric: tabular-nums;
}}

/* ===== SEITENLEISTE ===== */
section[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {{
    background-color: {bg_secondary} !important;
    border-right: {border_thin} solid {border_color} !important;
}}

section[data-testid="stSidebar"] * {{
    color: {text_primary} !important;
}}

/* Navigation: ruhige Zeilen statt einer Wand aus Schaltflaechen */
section[data-testid="stSidebar"] .stButton button {{
    background: transparent !important;
    color: {text_secondary} !important;
    border: {border_thin} solid transparent !important;
    border-radius: {radius_sm} !important;
    padding: {space_2} {space_3} !important;
    font-weight: {weight_medium} !important;
    font-size: {text_sm} !important;
    justify-content: flex-start !important;
    text-align: left !important;
    box-shadow: none !important;
    transition: background {motion_fast} {ease},
                color {motion_fast} {ease} !important;
}}

/* Streamlit legt in die Schaltflaeche einen eigenen Flex-Behaelter mit
   justify-content: center. Ohne diese Regel bleibt die Beschriftung mittig,
   obwohl der Button selbst linksbuendig ausgerichtet ist - eine Liste aus
   zentrierten Eintraegen wirkt versehentlich. */
section[data-testid="stSidebar"] .stButton button > div {{
    justify-content: flex-start !important;
    width: 100% !important;
}}

section[data-testid="stSidebar"] .stButton button:hover {{
    background: {bg_surface} !important;
    border-color: {border_color} !important;
    color: {text_primary} !important;
}}

section[data-testid="stSidebar"] .stButton button:hover * {{
    color: {text_primary} !important;
}}

/* ===== SCHALTFLAECHEN =====
   Die Sekundaerform schliesst Hauptaktionen ausdruecklich aus. Ohne das
   :not() gewinnt sie: '.stFormSubmitButton button' hat eine hoehere
   Spezifitaet als '[data-testid="stBaseButton-primaryFormSubmit"]', und
   !important auf beiden Seiten laesst dann die Spezifitaet entscheiden -
   die Hauptaktion sah aus wie eine Nebenaktion. */
.stButton button:not([kind*="primary"]),
.stFormSubmitButton button:not([kind*="primary"]),
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"] {{
    background: {bg_elevated} !important;
    color: {text_primary} !important;
    border: {border_medium} solid {border_color} !important;
    border-radius: {radius_sm} !important;
    padding: {space_2} {space_4} !important;
    font-weight: {weight_semi} !important;
    font-size: {text_sm} !important;
    box-shadow: none !important;
    transition: border-color {motion_fast} {ease},
                color {motion_fast} {ease},
                background {motion_fast} {ease} !important;
}}

.stButton button:not([kind*="primary"]) *,
.stFormSubmitButton button:not([kind*="primary"]) * {{
    color: inherit !important;
}}

.stButton button:not([kind*="primary"]):hover,
.stFormSubmitButton button:not([kind*="primary"]):hover {{
    border-color: {accent_blue} !important;
    color: {accent_blue} !important;
}}

.stButton button:active, .stFormSubmitButton button:active {{
    transform: translateY(1px);
}}

/* Hauptaktionen - gefuellt */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"],
.stButton button[kind="primary"],
.stFormSubmitButton button[kind="primary"],
.stButton button[kind="primaryFormSubmit"],
.stFormSubmitButton button[kind="primaryFormSubmit"] {{
    background: {accent_blue} !important;
    color: {on_accent} !important;
    border: {border_medium} solid {accent_blue} !important;
    /* Form und Groesse muessen hier mitkommen: Seit die Sekundaerform
       Hauptaktionen ausschliesst, erben sie von dort nichts mehr. */
    border-radius: {radius_sm} !important;
    padding: {space_2} {space_4} !important;
    font-weight: {weight_semi} !important;
    font-size: {text_sm} !important;
    box-shadow: none !important;
    transition: background {motion_fast} {ease},
                border-color {motion_fast} {ease} !important;
}}

[data-testid="stBaseButton-primary"] *,
[data-testid="stBaseButton-primaryFormSubmit"] *,
.stButton button[kind="primary"] *,
.stFormSubmitButton button[kind="primary"] * {{
    color: {on_accent} !important;
}}

[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover,
.stButton button[kind="primary"]:hover {{
    background: {accent_blue_hover} !important;
    border-color: {accent_blue_hover} !important;
}}

/* Sichtbarer Fokus - fuer alle, die mit der Tastatur arbeiten */
button:focus-visible, input:focus-visible, textarea:focus-visible,
select:focus-visible, a:focus-visible, [role="tab"]:focus-visible {{
    outline: 3px solid {accent_blue} !important;
    outline-offset: 2px !important;
}}

[data-testid="stDownloadButton"] button {{
    background: {accent_blue} !important;
    color: {on_accent} !important;
    border-color: {accent_blue} !important;
}}
[data-testid="stDownloadButton"] button * {{ color: {on_accent} !important; }}

/* ===== EINGABEFELDER ===== */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stDateInput input {{
    background-color: {bg_elevated} !important;
    color: {text_primary} !important;
    border: {border_medium} solid {border_color} !important;
    border-radius: {radius_sm} !important;
    font-size: {text_base} !important;
    transition: border-color {motion_fast} {ease} !important;
}}

[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="base-input"] {{
    background-color: {bg_elevated} !important;
    border-color: {border_color} !important;
    border-radius: {radius_sm} !important;
}}

.stTextInput input:focus, .stTextArea textarea:focus,
.stNumberInput input:focus {{
    border-color: {accent_blue} !important;
}}

.stTextInput input::placeholder, .stTextArea textarea::placeholder {{
    color: {text_muted} !important;
    opacity: 1 !important;
}}

[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] * {{
    color: {text_primary} !important;
    font-weight: {weight_semi} !important;
    font-size: {text_sm} !important;
}}

/* Auswahllisten und ihre Aufklapp-Menues */
[data-baseweb="select"] > div {{
    background-color: {bg_elevated} !important;
    color: {text_primary} !important;
    border-color: {border_color} !important;
    border-radius: {radius_sm} !important;
}}

[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {{
    background-color: {bg_secondary} !important;
    border: {border_thin} solid {border_color} !important;
    border-radius: {radius_md} !important;
}}

[data-baseweb="menu"] li, [role="option"] {{
    background-color: {bg_secondary} !important;
    color: {text_primary} !important;
}}

[data-baseweb="menu"] li:hover, [role="option"]:hover {{
    background-color: {bg_surface} !important;
}}

[data-baseweb="calendar"], [data-baseweb="calendar"] * {{
    background-color: {bg_secondary} !important;
    color: {text_primary} !important;
}}

/* Ausgewaehlte Eintraege in Mehrfachauswahl */
[data-baseweb="tag"] {{
    background-color: {slot_free_bg} !important;
    color: {accent_blue_text} !important;
    border-radius: {radius_sm} !important;
}}
[data-baseweb="tag"] * {{ color: {accent_blue_text} !important; }}

/* ===== FORMULARE, KARTEN, AUSKLAPPER ===== */
[data-testid="stForm"] {{
    background-color: {bg_secondary} !important;
    border: {border_thin} solid {border_color} !important;
    border-radius: {radius_md} !important;
    padding: {space_5} !important;
    box-shadow: {card_shadow} !important;
}}

[data-testid="stExpander"], [data-testid="stExpander"] details {{
    background-color: {bg_secondary} !important;
    border: {border_thin} solid {border_color} !important;
    border-radius: {radius_md} !important;
}}

[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * {{
    color: {text_primary} !important;
    font-weight: {weight_semi} !important;
    font-size: {text_sm} !important;
}}

[data-testid="stPopover"] {{
    border-radius: {radius_md} !important;
}}

/* ===== REITER ===== */
.stTabs [data-baseweb="tab-list"] {{
    gap: {space_1} !important;
    border-bottom: {border_thin} solid {border_color} !important;
    background: transparent !important;
}}

.stTabs [data-baseweb="tab"] {{
    color: {text_muted} !important;
    background: transparent !important;
    font-weight: {weight_semi} !important;
    font-size: {text_sm} !important;
    padding: {space_2} {space_4} !important;
    transition: color {motion_fast} {ease} !important;
}}

.stTabs [data-baseweb="tab"] * {{ color: inherit !important; }}
.stTabs [data-baseweb="tab"]:hover {{ color: {text_primary} !important; }}

.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] * {{
    color: {accent_blue} !important;
}}

.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {accent_blue} !important;
}}

/* ===== KENNZAHLEN ===== */
[data-testid="stMetric"] {{
    background-color: {bg_secondary} !important;
    border: {border_thin} solid {border_color} !important;
    border-radius: {radius_md} !important;
    padding: {space_3} {space_4} !important;
}}

[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
    color: {text_muted} !important;
    font-size: {text_xs} !important;
    font-weight: {weight_medium} !important;
    letter-spacing: {tracking_wide} !important;
    text-transform: uppercase;
}}

[data-testid="stMetricValue"], [data-testid="stMetricValue"] * {{
    color: {text_primary} !important;
    font-size: {text_2xl} !important;
    font-weight: {weight_bold} !important;
    letter-spacing: {tracking_tight} !important;
}}

/* ===== TABELLEN ===== */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    background-color: {bg_secondary} !important;
    border: {border_thin} solid {border_color} !important;
    border-radius: {radius_md} !important;
    overflow: hidden;
}}

/* st.table liefert eine schlichte HTML-Tabelle - die gestalten wir selbst.
   Waagerechte Linien genuegen; senkrechte Gitterlinien zerhacken die Zeile,
   ohne etwas zu trennen, was das Auge nicht ohnehin sieht. */
[data-testid="stTable"] table {{
    border-collapse: collapse !important;
    width: 100% !important;
    font-size: {text_sm} !important;
}}

[data-testid="stTable"] thead th {{
    background-color: {bg_surface} !important;
    color: {text_muted} !important;
    font-size: {text_xs} !important;
    font-weight: {weight_semi} !important;
    letter-spacing: {tracking_wide} !important;
    text-transform: uppercase;
    text-align: left !important;
    padding: {space_2} {space_3} !important;
    border: none !important;
    border-bottom: {border_thin} solid {border_color} !important;
}}

[data-testid="stTable"] tbody th,
[data-testid="stTable"] tbody td {{
    color: {text_primary} !important;
    padding: {space_2} {space_3} !important;
    border: none !important;
    border-bottom: {border_thin} solid {border_color} !important;
    background: transparent !important;
}}

[data-testid="stTable"] tbody tr:last-child th,
[data-testid="stTable"] tbody tr:last-child td {{
    border-bottom: none !important;
}}

[data-testid="stTable"] tbody tr:hover td,
[data-testid="stTable"] tbody tr:hover th {{
    background-color: {bg_surface} !important;
}}

/* Zahlenspalten rechtsbuendig, damit Groessen vergleichbar sind */
[data-testid="stTable"] tbody td:nth-last-child(-n+2),
[data-testid="stTable"] thead th:nth-last-child(-n+2) {{
    text-align: right !important;
}}

/* ===== MELDUNGEN ===== */
[data-testid="stAlert"] {{
    border-radius: {radius_md} !important;
    border-left-width: {border_accent} !important;
    padding: {space_3} {space_4} !important;
}}
[data-testid="stAlert"], [data-testid="stAlert"] * {{
    color: {text_primary} !important;
    font-size: {text_sm} !important;
}}

/* ===== KONTROLLKAESTCHEN ===== */
.stCheckbox label, .stRadio label,
.stCheckbox label *, .stRadio label * {{
    color: {text_primary} !important;
    font-size: {text_sm} !important;
}}

/* =====================================================================
   Eigene Bausteine. Mit .stApp davor, damit sie in der Kaskade ueber den
   breiten Grundregeln stehen.
   ===================================================================== */
.stApp .slot-card {{
    background-color: {bg_secondary} !important;
    color: {text_primary} !important;
    border: {border_thin} solid {border_color} !important;
    border-left: {border_accent} solid {divider_color} !important;
    border-radius: {radius_md} !important;
    padding: {space_4} !important;
    margin: {space_3} 0 !important;
    box-shadow: {card_shadow} !important;
    transition: box-shadow {motion_base} {ease},
                transform {motion_base} {ease} !important;
}}

.stApp .slot-card * {{ color: {text_primary} !important; }}

.stApp .slot-card h3 {{
    color: {text_primary} !important;
    margin: 0 !important;
    font-size: {text_lg} !important;
}}

.stApp .slot-card p {{
    color: {text_secondary} !important;
    font-size: {text_sm} !important;
}}

.stApp .slot-card:hover {{
    box-shadow: {card_shadow_hover} !important;
    transform: translateY(-1px);
}}

/* Der Zustand steckt in der linken Kante, nicht in einer Farbflaeche -
   so bleibt die Karte ruhig und der Status trotzdem auf einen Blick da. */
.stApp .slot-card.free {{
    background-color: {slot_free_bg} !important;
    border-color: {border_color} !important;
    border-left-color: {slot_free_border} !important;
}}

.stApp .slot-card.booked {{
    background-color: {slot_booked_bg} !important;
    border-color: {border_color} !important;
    border-left-color: {slot_booked_border} !important;
}}

.stApp .slot-card.blocked {{
    background-color: {slot_blocked_bg} !important;
    border-color: {border_color} !important;
    border-left-color: {slot_blocked_border} !important;
}}

.stApp .status-badge {{
    display: inline-flex;
    align-items: center;
    gap: {space_1};
    padding: {space_1} {space_3};
    border-radius: {radius_pill};
    font-weight: {weight_semi};
    font-size: {text_xs};
    letter-spacing: {tracking_wide};
    margin-top: {space_3};
    background: transparent;
}}

.stApp .status-badge.free {{
    color: {accent_blue_text} !important;
    border: {border_medium} solid {slot_free_border};
}}

.stApp .status-badge.booked {{
    color: {accent_orange_text} !important;
    border: {border_medium} solid {slot_booked_border};
}}

.stApp .status-badge.blocked {{
    color: {text_secondary} !important;
    border: {border_medium} solid {slot_blocked_border};
}}

/* ===== MOBIL ===== */
/* Die meisten buchen vom Handy - dort zaehlen Daumenflaechen und Platz. */
@media (max-width: 768px) {{
    [data-testid="stMainBlockContainer"] {{
        padding: {space_4} {space_3} !important;
    }}
    .stApp h1 {{ font-size: {text_xl} !important; }}
    .stApp .slot-card {{
        padding: {space_3} !important;
        margin: {space_2} 0 !important;
    }}
    .stButton button, .stFormSubmitButton button {{
        width: 100% !important;
        min-height: 44px !important;
    }}
    [data-testid="stMetricValue"] {{ font-size: {text_xl} !important; }}
}}

/* Wer Bewegung abgestellt hat, bekommt keine. */
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{
        transition: none !important;
        animation: none !important;
    }}
    .stApp .slot-card:hover {{ transform: none; }}
}}
"""


def build_css(farben):
    """Setzt Palette und Gestaltungstoken in die Vorlage ein.

    Fehlt ein Schluessel, wirft .format einen KeyError - genau das soll
    passieren, statt eine Regel still mit leerem Wert auszuliefern.
    """
    return CSS_VORLAGE.format(**farben)
