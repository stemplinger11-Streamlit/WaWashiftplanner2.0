"""
Das Stylesheet der App.

Getrennt von streamlit_app.py, weil es rund 300 Zeilen sind und weil sich so
pruefen laesst, dass jeder verwendete Platzhalter in der Palette existiert.

Zur Selektorwahl: Streamlit hat seine DOM-Klassen zwischen 1.3x und 1.4x
umbenannt. Der Bereich hiess frueher '.main', heute
[data-testid="stMain"]. Nach dem Versionssprung griffen deshalb einige
unserer Regeln nicht mehr - die Seite behielt Streamlits Grundfarbe,
waehrend Formular und Schrift bereits unsere Palette trugen. Ergebnis war
weisse Schrift auf weissem Grund. Darum stehen hier bewusst die Selektoren
beider Generationen nebeneinander.
"""

CSS_VORLAGE = """
/* ===== GRUNDFLAECHE ===== */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
.main {{
    background-color: {bg_primary} !important;
    color: {text_primary} !important;
}}

[data-testid="stHeader"] {{
    background-color: {bg_primary} !important;
    border-bottom: 1px solid {border_color} !important;
}}

[data-testid="stToolbar"], [data-testid="stDecoration"] {{
    background: transparent !important;
}}

/* ===== TYPOGRAFIE ===== */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {{
    color: {text_primary} !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
}}

.stApp p, .stApp li, .stApp label, .stApp td, .stApp th,
.stApp [data-testid="stMarkdownContainer"] {{
    color: {text_primary} !important;
}}

.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] * {{
    color: {text_muted} !important;
}}

.stApp a {{ color: {accent_blue} !important; }}

.stApp hr, [data-testid="stDivider"] {{
    border-color: {divider_color} !important;
}}

/* ===== SEITENLEISTE ===== */
section[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {{
    background-color: {bg_secondary} !important;
    border-right: 1px solid {border_color} !important;
}}

section[data-testid="stSidebar"] * {{
    color: {text_primary} !important;
}}

section[data-testid="stSidebar"] .stButton button {{
    background: {bg_elevated} !important;
    color: {text_primary} !important;
    border: 1px solid {border_color} !important;
    font-weight: 500 !important;
    justify-content: flex-start !important;
}}

section[data-testid="stSidebar"] .stButton button:hover,
section[data-testid="stSidebar"] .stButton button:hover * {{
    background: {accent_blue} !important;
    border-color: {accent_blue} !important;
    color: {on_accent} !important;
}}

/* ===== SCHALTFLAECHEN ===== */
.stButton button, .stFormSubmitButton button,
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"] {{
    background: {bg_elevated} !important;
    color: {text_primary} !important;
    border: 1.5px solid {border_color} !important;
    border-radius: 10px !important;
    padding: 0.55rem 1.2rem !important;
    font-weight: 600 !important;
    transition: all 0.18s ease !important;
    box-shadow: none !important;
}}

.stButton button *, .stFormSubmitButton button * {{
    color: inherit !important;
}}

.stButton button:hover, .stFormSubmitButton button:hover {{
    border-color: {accent_blue} !important;
    color: {accent_blue} !important;
}}

/* Hauptaktionen - gefuellt */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"],
.stButton button[kind="primary"],
.stFormSubmitButton button[kind="primary"],
.stButton button[kind="primaryFormSubmit"] {{
    background: {accent_blue} !important;
    color: {on_accent} !important;
    border: 1.5px solid {accent_blue} !important;
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

button:focus-visible {{
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
    border: 1.5px solid {border_color} !important;
    border-radius: 9px !important;
}}

[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="base-input"] {{
    background-color: {bg_elevated} !important;
    border-color: {border_color} !important;
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
    font-weight: 600 !important;
}}

/* Auswahllisten und ihre Aufklapp-Menues */
[data-baseweb="select"] > div {{
    background-color: {bg_elevated} !important;
    color: {text_primary} !important;
    border-color: {border_color} !important;
}}

[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"] {{
    background-color: {bg_secondary} !important;
    border: 1px solid {border_color} !important;
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

/* ===== FORMULARE, KARTEN, AUSKLAPPER ===== */
[data-testid="stForm"] {{
    background-color: {bg_secondary} !important;
    border: 1px solid {border_color} !important;
    border-radius: 12px !important;
    padding: 1.4rem !important;
    box-shadow: {card_shadow} !important;
}}

[data-testid="stExpander"], [data-testid="stExpander"] details {{
    background-color: {bg_secondary} !important;
    border: 1px solid {border_color} !important;
    border-radius: 10px !important;
}}

[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * {{
    color: {text_primary} !important;
    font-weight: 600 !important;
}}

/* ===== REITER ===== */
.stTabs [data-baseweb="tab-list"] {{
    gap: 4px !important;
    border-bottom: 1px solid {border_color} !important;
    background: transparent !important;
}}

.stTabs [data-baseweb="tab"] {{
    color: {text_muted} !important;
    background: transparent !important;
    font-weight: 600 !important;
    padding: 0.5rem 1rem !important;
}}

.stTabs [data-baseweb="tab"] * {{ color: inherit !important; }}

.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] * {{
    color: {accent_blue} !important;
}}

.stTabs [data-baseweb="tab-highlight"] {{
    background-color: {accent_blue} !important;
}}

/* ===== KENNZAHLEN & TABELLEN ===== */
[data-testid="stMetric"] {{
    background-color: {bg_secondary} !important;
    border: 1px solid {border_color} !important;
    border-radius: 10px !important;
    padding: 0.9rem 1rem !important;
}}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"],
[data-testid="stMetricValue"] *, [data-testid="stMetricLabel"] * {{
    color: {text_primary} !important;
}}

[data-testid="stDataFrame"], [data-testid="stTable"] {{
    background-color: {bg_secondary} !important;
    border: 1px solid {border_color} !important;
    border-radius: 10px !important;
}}

/* ===== MELDUNGEN ===== */
[data-testid="stAlert"] {{
    border-radius: 10px !important;
    border-left-width: 5px !important;
}}
[data-testid="stAlert"], [data-testid="stAlert"] * {{
    color: {text_primary} !important;
}}

/* ===== KONTROLLKAESTCHEN ===== */
.stCheckbox label, .stRadio label,
.stCheckbox label *, .stRadio label * {{
    color: {text_primary} !important;
}}

/* =====================================================================
   Eigene Bausteine. Bewusst mit .stApp davor, damit sie in der Kaskade
   ueber den breiten Grundregeln weiter oben stehen.
   ===================================================================== */
.stApp .slot-card {{
    background-color: {bg_secondary} !important;
    color: {text_primary} !important;
    border: 1.5px solid {border_color} !important;
    border-radius: 12px !important;
    padding: 1rem 1.15rem !important;
    margin: 0.6rem 0 !important;
    box-shadow: {card_shadow} !important;
    transition: box-shadow 0.2s ease !important;
}}

.stApp .slot-card * {{ color: {text_primary} !important; }}
.stApp .slot-card h3 {{ color: {text_primary} !important; margin: 0 !important; }}
.stApp .slot-card p {{ color: {text_secondary} !important; }}
.stApp .slot-card:hover {{ box-shadow: {card_shadow_hover} !important; }}

.stApp .slot-card.free {{
    background-color: {slot_free_bg} !important;
    border-color: {slot_free_border} !important;
    border-left: 5px solid {slot_free_border} !important;
}}

.stApp .slot-card.booked {{
    background-color: {slot_booked_bg} !important;
    border-color: {slot_booked_border} !important;
    border-left: 5px solid {slot_booked_border} !important;
}}

.stApp .slot-card.blocked {{
    background-color: {slot_blocked_bg} !important;
    border-color: {slot_blocked_border} !important;
    border-left: 5px solid {slot_blocked_border} !important;
}}

.stApp .status-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.32rem 0.8rem;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.88rem;
    margin-top: 0.6rem;
    background: transparent;
}}

.stApp .status-badge.free {{
    color: {accent_blue_text} !important;
    border: 1.5px solid {slot_free_border};
}}

.stApp .status-badge.booked {{
    color: {accent_orange_text} !important;
    border: 1.5px solid {slot_booked_border};
}}

.stApp .status-badge.blocked {{
    color: {text_secondary} !important;
    border: 1.5px solid {slot_blocked_border};
}}

/* ===== MOBIL ===== */
@media (max-width: 768px) {{
    [data-testid="stMainBlockContainer"] {{
        padding: 1rem 0.8rem !important;
    }}
    .stApp .slot-card {{ padding: 0.8rem !important; margin: 0.5rem 0 !important; }}
    .stButton button {{ width: 100% !important; }}
}}

@media (prefers-reduced-motion: reduce) {{
    * {{ transition: none !important; animation: none !important; }}
}}
"""


def build_css(farben):
    """Setzt die Palette in die Vorlage ein.

    Fehlt ein Schluessel, wirft .format einen KeyError - genau das soll
    passieren, statt eine Regel still mit leerem Wert auszuliefern.
    """
    return CSS_VORLAGE.format(**farben)
