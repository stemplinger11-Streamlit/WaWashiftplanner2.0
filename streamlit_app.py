"""
Wasserwacht Dienstplan+ - Streamlit-App mit Firestore-Anbindung.

Einstiegspunkt fuer Streamlit Community Cloud. Fachliche Regeln liegen in
core_rules.py, damit sie ohne App und ohne Datenbank testbar sind.
"""
import streamlit as st
import io
import json
import zipfile
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import email.utils
import smtplib
import pytz
from twilio.rest import Client
import pandas as pd
import plotly.express as px
from google.cloud import firestore
from google.oauth2 import service_account
from collections import Counter

# Fachliche Regeln (Feiertage, Saisonpause, Stornofrist) liegen in
# core_rules.py und sind durch test_core_rules.py abgedeckt.
import core_rules as rules
import core_theme as theme
import core_styles as styles
from core_rules import (
    DEFAULT_PAUSE_START,
    DEFAULT_PAUSE_END,
    DEFAULT_CANCEL_DEADLINE_HOURS,
)
# Passwort-Hashing inkl. stiller Migration der Bestandsnutzer,
# abgedeckt durch test_core_auth.py.
from core_auth import (
    DEFAULT_REMEMBER_DAYS,
    DEFAULT_SESSION_TIMEOUT_MINUTES,
    SESSION_COOKIE_NAME,
    hash_pw,
    pw_pruefen,
    session_abgelaufen,
    session_datensatz_gueltig,
    session_eintrag,
    token_hash,
)
import extra_streamlit_components as stx

# ===== PAGE CONFIG =====
st.set_page_config(
    page_title="Wasserwacht Dienstplan+",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== KONFIGURATION =====
VERSION = "9.0"
TIMEZONE_STR = "Europe/Berlin"
TZ = pytz.timezone(TIMEZONE_STR)

WEEKLY_SLOTS = [
    {"id": 1, "day": "tuesday", "day_name": "Dienstag", "start": "17:00", "end": "20:00"},
    {"id": 2, "day": "friday", "day_name": "Freitag", "start": "17:00", "end": "20:00"},
    {"id": 3, "day": "saturday", "day_name": "Samstag", "start": "14:00", "end": "17:00"},
]

# Feiertage, Saisonpause und Stornofrist liegen in core_rules.py -
# dort ohne Streamlit/Firestore und durch test_core_rules.py abgedeckt.

COLORS = {
    "rot": "#DC143C",
    "rot_dunkel": "#B22222",
    "rot_hell": "#FF6B6B",
    "blau": "#003087",
    "blau_hell": "#4A90E2",
    "weiss": "#FFFFFF",
    "grau_hell": "#F5F7FA",
    "grau_mittel": "#E1E8ED",
    "grau_dunkel": "#657786",
    "text": "#14171A",
    "erfolg": "#17BF63",
    "warnung": "#FFAD1F",
    "fehler": "#E0245E",
    "orange": "#FF8C00",
    "orange_hell": "#FFA500"
}

# ===== FIREBASE INIT =====
@st.cache_resource
def init_firestore():
    try:
        if not hasattr(st, 'secrets') or 'firebase' not in st.secrets:
            st.error("❌ Firebase Secrets fehlen!")
            st.stop()
        
        firebase_config = dict(st.secrets['firebase'])
        creds = service_account.Credentials.from_service_account_info(firebase_config)
        return firestore.Client(credentials=creds, project=firebase_config['project_id'])
    except Exception as e:
        st.error(f"❌ Firebase Init Fehler: {e}")
        st.stop()

db = init_firestore()

# ===== HELPER FUNCTIONS =====
def week_start(d=None):
    d = d or datetime.now().date()
    if hasattr(d, "date"):
        d = d.date()
    return d - timedelta(days=d.weekday())

def slot_date(ws, day):
    days = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
    return (ws + timedelta(days=days.get(day,0))).strftime("%Y-%m-%d")

def fmt_de(d):
    try:
        if isinstance(d, str):
            return datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y")
        return d.strftime("%d.%m.%Y")
    except:
        return str(d)

def get_pause_range():
    """Saisonpause als ('MM-TT', 'MM-TT') aus den Einstellungen."""
    start = ww_db.get_setting('season_pause_start', DEFAULT_PAUSE_START)
    end = ww_db.get_setting('season_pause_end', DEFAULT_PAUSE_END)
    return start or DEFAULT_PAUSE_START, end or DEFAULT_PAUSE_END

def get_cancel_deadline_hours():
    """Stornofrist in Stunden aus den Einstellungen."""
    try:
        return int(ww_db.get_setting('cancel_deadline_hours',
                                     DEFAULT_CANCEL_DEADLINE_HOURS))
    except (ValueError, TypeError):
        return DEFAULT_CANCEL_DEADLINE_HOURS

def get_session_timeout_minutes():
    """Abmeldung nach Inaktivitaet, in Minuten (0 = aus)."""
    try:
        return int(ww_db.get_setting('session_timeout_minutes',
                                     DEFAULT_SESSION_TIMEOUT_MINUTES))
    except (ValueError, TypeError):
        return DEFAULT_SESSION_TIMEOUT_MINUTES

def is_in_pause(d):
    return rules.is_in_pause(d, *get_pause_range())

def is_blocked(d):
    return rules.is_blocked(d, *get_pause_range())

def block_reason(d):
    return rules.block_reason(d, *get_pause_range())

def can_cancel(slot_date_str, slot_time_str, is_admin=False, now=None):
    """Stornoregel mit der in den Einstellungen gepflegten Frist."""
    return rules.can_cancel(slot_date_str, slot_time_str, is_admin=is_admin,
                            now=now, deadline_hours=get_cancel_deadline_hours())


def generate_random_password(length=8):
    """Generiert ein sicheres, zufälliges Passwort (nur Buchstaben + Zahlen)"""
    import random
    import string
    # Nur Buchstaben (Groß+Klein) und Zahlen - KEINE Sonderzeichen
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# ===== COOKIES ("Angemeldet bleiben") =====
# Streamlit kann Cookies nicht selbst setzen (st.context.cookies ist nur
# lesbar), deshalb die Komponente. Jeder Zugriff ist abgesichert: faellt
# das Cookie-Handling aus, muss der normale Login trotzdem funktionieren -
# ein Fehler hier darf niemanden aussperren.

# Der Manager wird bei JEDEM Skriptlauf neu erzeugt - bewusst ohne Cache:
#   * Sein Konstruktor rendert eine Komponente. Streamlit verbietet Widgets
#     in gecachten Funktionen und bricht dort mit CachedWidgetWarning ab.
#   * Er liest die Cookies im Konstruktor in self.cookies. Eine ueber
#     mehrere Laeufe wiederverwendete Instanz lieferte veraltete Werte.
# Schlaegt die Erzeugung fehl, bleibt der Manager None und die App laeuft
# ohne "Angemeldet bleiben" weiter - der normale Login darf nie blockieren.
try:
    _cookie_manager = stx.CookieManager(key='wawa_cookies')
except Exception as _cookie_fehler:
    print(f"⚠️ Cookie-Manager nicht verfügbar: {_cookie_fehler}")
    _cookie_manager = None


def get_cookie_manager():
    """Der Manager dieses Skriptlaufs, oder None wenn nicht verfuegbar."""
    return _cookie_manager


def cookie_lesen(name):
    try:
        manager = get_cookie_manager()
        if manager is None:
            return None
        return manager.get(cookie=name)
    except Exception as e:
        print(f"⚠️ Cookie nicht lesbar: {e}")
        return None


def cookie_setzen(name, wert, tage):
    try:
        manager = get_cookie_manager()
        if manager is None:
            return False
        manager.set(
            name, wert,
            expires_at=datetime.now() + timedelta(days=tage),
            key=f'set_{name}'
        )
        return True
    except Exception as e:
        print(f"⚠️ Cookie nicht setzbar: {e}")
        return False


def cookie_loeschen(name):
    try:
        manager = get_cookie_manager()
        if manager is None:
            return False
        manager.delete(name, key=f'del_{name}')
        return True
    except Exception as e:
        print(f"⚠️ Cookie nicht loeschbar: {e}")
        return False


def get_remember_days():
    """Gueltigkeit des Anmelde-Cookies in Tagen (0 = Funktion aus)."""
    try:
        return int(ww_db.get_setting('remember_me_days', DEFAULT_REMEMBER_DAYS))
    except (ValueError, TypeError):
        return DEFAULT_REMEMBER_DAYS


def sitzung_aus_cookie_wiederherstellen():
    """Meldet den Nutzer per Cookie an, falls eines gueltig ist."""
    if st.session_state.get('user') or st.session_state.get('cookie_geprueft'):
        return False

    token = cookie_lesen(SESSION_COOKIE_NAME)
    if not token:
        # Die Komponente liefert beim allerersten Lauf noch nichts zurueck.
        # Deshalb wird erst beim zweiten Durchlauf endgueltig aufgegeben.
        if st.session_state.get('cookie_zweiter_versuch'):
            st.session_state.cookie_geprueft = True
        else:
            st.session_state.cookie_zweiter_versuch = True
        return False

    nutzer = ww_db.get_session_user(token)
    st.session_state.cookie_geprueft = True
    if not nutzer:
        cookie_loeschen(SESSION_COOKIE_NAME)
        return False

    st.session_state.user = nutzer
    st.session_state.last_activity = datetime.now()
    st.session_state.dauersitzung = True
    return True


# ===== BENACHRICHTIGUNGS-EINSTELLUNGEN =====
# Bis V8.1 existierten zwei unabhaengige Feld-Schemata nebeneinander:
# das Profil schrieb '<kanal>_notifications_<ereignis>', die Buchungslogik
# las '<kanal>_notifications'. Dadurch blieben Profil-Einstellungen wirkungslos.
# Kanonisch ist jetzt das feingranulare Schema; das alte dient als Fallback,
# damit Bestandsnutzer ihre bisherige Einstellung behalten.
NOTIFY_DEFAULTS = {
    ('email', 'booking'): True,
    ('email', 'cancellation'): True,
    ('email', 'reminder'): True,
    ('sms', 'booking'): False,
    ('sms', 'reminder'): False,
}

def notify_pref(user, channel, event):
    """Moechte dieser Nutzer die Benachrichtigung erhalten?

    channel: 'email' | 'sms'   event: 'booking' | 'cancellation' | 'reminder'
    """
    # None bedeutet 'kein Nutzer bekannt'; ein leeres Dict ist ein Nutzer
    # ohne gepflegte Einstellungen und bekommt die Standardwerte.
    if user is None:
        return False
    default = NOTIFY_DEFAULTS.get((channel, event), False)
    value = user.get(f"{channel}_notifications_{event}")
    if value is not None:
        return bool(value)
    # Fallback auf das alte Schema der Bestandsnutzer
    legacy = user.get(f"{channel}_notifications")
    if legacy is not None:
        return bool(legacy)
    return default

def wants_sms(user, event):
    """SMS nur wenn gewuenscht UND eine Telefonnummer hinterlegt ist."""
    return bool(user.get('phone')) and notify_pref(user, 'sms', event)

# ===== CSS INJECTION (PROFESSIONELLES DESIGN) =====
def inject_css(dark=False):
    """Faerbt die App nach der geprueften Palette.

    Farben: core_theme.py (durch test_core_theme.py gegen WCAG AA geprueft)
    Regeln: core_styles.py
    """
    st.markdown(
        "<style>" + styles.build_css(theme.palette(dark)) + "</style>",
        unsafe_allow_html=True
    )



# ===== DATABASE CLASS =====
class WasserwachtDB:
    def __init__(self):
        self.db = db
        self._init_admin()
    
    def _init_admin(self):
        """Admin-User beim ersten Start erstellen.

        Ohne gesetzte Secrets wird bewusst KEIN Admin angelegt - ein
        Standardpasswort wuerde einen offen erreichbaren Adminzugang schaffen.
        """
        if not hasattr(st, 'secrets'):
            return

        email = st.secrets.get("ADMIN_EMAIL", "")
        pw = st.secrets.get("ADMIN_PASSWORD", "")

        if not email or not pw:
            print("⚠️ ADMIN_EMAIL/ADMIN_PASSWORD nicht gesetzt - kein Admin angelegt")
            return

        if self.get_user(email):
            return

        try:
            self.db.collection('users').add({
                'email': email, 'name': 'Admin', 'phone': '',
                'password_hash': hash_pw(pw),
                'role': 'admin', 'active': True,
                'email_notifications_booking': True,
                'email_notifications_cancellation': True,
                'email_notifications_reminder': True,
                'sms_notifications_booking': False,
                'sms_notifications_reminder': False,
                'email_notifications': True,
                'sms_notifications': False,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Admin erstellt: {email}")
        except Exception as e:
            print(f"Admin-Erstellung fehlgeschlagen: {e}")
    
    def get_user(self,email):
        try:
            for doc in self.db.collection('users').where('email','==',email).limit(1).stream():
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            print(f"❌ get_user Fehler: {e}")
            return None
    
    def create_user(self, email, name, phone, password, role='user',
                    active=True, pending_approval=False,
                    email_notifications=True, sms_notifications=False):
        try:
            if self.get_user(email):
                return False, "E-Mail bereits registriert"

            self.db.collection('users').add({
                'email': email, 'name': name, 'phone': phone,
                'password_hash': hash_pw(password),
                'role': role, 'active': active,
                'pending_approval': pending_approval,
                # Kanonisches Schema, siehe notify_pref()
                'email_notifications_booking': email_notifications,
                'email_notifications_cancellation': email_notifications,
                'email_notifications_reminder': email_notifications,
                'sms_notifications_booking': sms_notifications,
                'sms_notifications_reminder': sms_notifications,
                # Altfelder weiterhin mitschreiben, solange Altcode sie liest
                'email_notifications': email_notifications,
                'sms_notifications': sms_notifications,
                'created_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ User erstellt: {email} (aktiv: {active})")
            return True, "Registrierung erfolgreich"
        except Exception as e:
            print(f"❌ create_user Fehler: {e}")
            return False, str(e)

    def auth(self, email, password):
        """Anmeldung pruefen -> (erfolg, user, grund)

        'grund' unterscheidet falsche Zugangsdaten von einem Konto, das noch
        auf die Freigabe durch einen Admin wartet.
        """
        u = self.get_user(email)
        if not u:
            return False, None, 'unknown'

        korrekt, neuer_hash = pw_pruefen(password, u.get('password_hash'))
        if not korrekt:
            return False, None, 'credentials'

        # Bestandsnutzer still auf das neue Verfahren heben. Schlaegt das
        # Schreiben fehl, bleibt der alte Hash gueltig - die Anmeldung
        # funktioniert trotzdem.
        if neuer_hash:
            if self.update_user(u['id'], password_hash=neuer_hash):
                u['password_hash'] = neuer_hash
                print(f"🔐 Passwort-Hash migriert: {email}")
        # Bestandsnutzer ohne 'active'-Feld gelten als aktiv
        if not u.get('active', True):
            return False, None, 'pending' if u.get('pending_approval') else 'disabled'
        return True, u, None

    # ===== DAUERSITZUNGEN ("Angemeldet bleiben") =====
    # Gespeichert wird nur der Hash des Tokens, das Dokument traegt ihn als
    # ID. Wer die Datenbank liest, kann sich damit nicht anmelden.

    def create_session(self, user_id, tage=None):
        """Legt eine Dauersitzung an und gibt das Token zurueck."""
        try:
            tage = tage or DEFAULT_REMEMBER_DAYS
            token, datensatz = session_eintrag(user_id, tage=tage)
            self.db.collection('sessions').document(token_hash(token)).set(datensatz)
            return token
        except Exception as e:
            print(f"❌ create_session Fehler: {e}")
            return None

    def get_session_user(self, token):
        """Nutzer zu einem Token - oder None, wenn ungueltig/abgelaufen."""
        if not token:
            return None
        try:
            doc = self.db.collection('sessions').document(token_hash(token)).get()
            if not doc.exists:
                return None
            datensatz = doc.to_dict()
            if not session_datensatz_gueltig(datensatz):
                self.delete_session(token)
                return None

            nutzer_doc = self.db.collection('users').document(
                datensatz['user_id']).get()
            if not nutzer_doc.exists:
                self.delete_session(token)
                return None

            nutzer = nutzer_doc.to_dict()
            nutzer['id'] = nutzer_doc.id
            # Zwischenzeitlich gesperrte Konten kommen nicht mehr herein
            if not nutzer.get('active', True):
                self.delete_session(token)
                return None
            return nutzer
        except Exception as e:
            print(f"❌ get_session_user Fehler: {e}")
            return None

    def delete_session(self, token):
        try:
            if token:
                self.db.collection('sessions').document(token_hash(token)).delete()
            return True
        except Exception as e:
            print(f"❌ delete_session Fehler: {e}")
            return False

    def delete_sessions_of_user(self, user_id):
        """Alle Dauersitzungen eines Nutzers beenden.

        Wird bei Passwortwechsel und Passwort-Reset aufgerufen, damit ein
        altes Cookie danach nicht weitergilt.
        """
        try:
            anzahl = 0
            for doc in self.db.collection('sessions')\
                    .where('user_id', '==', user_id).stream():
                doc.reference.delete()
                anzahl += 1
            return anzahl
        except Exception as e:
            print(f"❌ delete_sessions_of_user Fehler: {e}")
            return 0

    def get_pending_users(self):
        """Konten, die auf Freigabe durch einen Admin warten."""
        return [u for u in self.get_all_users()
                if u.get('pending_approval') and not u.get('active', True)]

    def approve_user(self, uid):
        """Gibt ein registriertes Konto frei."""
        return self.update_user(uid, active=True, pending_approval=False,
                                approved_at=firestore.SERVER_TIMESTAMP)
    
    def get_all_users(self):
        try:
            users = []
            for doc in self.db.collection('users').stream():
                data = doc.to_dict()
                data['id'] = doc.id
                users.append(data)
            return users
        except Exception as e:
            print(f"❌ get_all_users Fehler: {e}")
            return []
    
    def update_user(self,uid,**kwargs):
        try:
            self.db.collection('users').document(uid).update(kwargs)
            print(f"✅ User geupdatet: {uid}")
            return True
        except Exception as e:
            print(f"❌ update_user Fehler: {e}")
            return False
    
    def delete_user(self,uid):
        try:
            self.db.collection('users').document(uid).delete()
            print(f"✅ User gelöscht: {uid}")
            return True
        except Exception as e:
            print(f"❌ delete_user Fehler: {e}")
            return False
            
    def trigger_password_reset(self, uid):
        """
        Triggert Password Reset für einen User:
        - Generiert neues temporäres Passwort (8 Zeichen, nur Buchstaben+Zahlen)
        - Setzt neues password_hash
        - Returned (success, new_password) für Email-Versand
        """
        try:
            new_password = generate_random_password(8)
            self.db.collection('users').document(uid).update({
                'password_hash': hash_pw(new_password),
                'password_reset_at': firestore.SERVER_TIMESTAMP
            })
            # Alte Anmelde-Cookies duerfen nach einem Reset nicht weitergelten
            self.delete_sessions_of_user(uid)
            print(f"✅ Password Reset triggered für User: {uid}")
            return True, new_password
        except Exception as e:
            print(f"❌ trigger_password_reset Fehler: {e}")
            return False, None

    
    def get_week_bookings(self, ws):
        """Alle Buchungen für eine Woche laden"""
        try:
            we = (datetime.strptime(ws,'%Y-%m-%d')+timedelta(days=6)).strftime('%Y-%m-%d')
            result = []
            for doc in self.db.collection('bookings')\
                    .where('slot_date','>=',ws)\
                    .where('slot_date','<=',we)\
                    .where('status','==','confirmed').stream():
                data = doc.to_dict()
                data['id'] = doc.id
                result.append(data)
            return result
        except Exception as e:
            print(f"❌ get_week_bookings Fehler: {e}")
            # Fallback
            try:
                result = []
                for doc in self.db.collection('bookings').where('status','==','confirmed').stream():
                    b = doc.to_dict()
                    if ws <= b.get('slot_date','') <= we:
                        b['id'] = doc.id
                        result.append(b)
                return result
            except:
                return []
    
    def create_booking(self,slot_date,slot_time,user_email,user_name,user_phone):
        try:
            existing = self.get_booking(slot_date,slot_time)
            if existing:
                return False,"Slot bereits gebucht"
            
            self.db.collection('bookings').add({
                'slot_date':slot_date,'slot_time':slot_time,
                'user_email':user_email,'user_name':user_name,
                'user_phone':user_phone,'status':'confirmed',
                'created_at':firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Buchung erstellt: {user_name} | {slot_date} {slot_time}")
            return True,"Buchung erfolgreich"
        except Exception as e:
            print(f"❌ create_booking Fehler: {e}")
            return False,str(e)
    
    def get_booking(self,slot_date,slot_time):
        try:
            for doc in self.db.collection('bookings')\
                    .where('slot_date','==',slot_date)\
                    .where('slot_time','==',slot_time)\
                    .where('status','==','confirmed').limit(1).stream():
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            print(f"❌ get_booking Fehler: {e}")
            return None
    
    def get_user_bookings(self,email,future_only=False):
        try:
            q = self.db.collection('bookings')\
                .where('user_email','==',email)\
                .where('status','==','confirmed')
            
            if future_only:
                q = q.where('slot_date','>=',datetime.now().strftime("%Y-%m-%d"))
            
            bookings = []
            for doc in q.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                bookings.append(data)
            return sorted(bookings,key=lambda x:x['slot_date'])
        except Exception as e:
            print(f"❌ get_user_bookings Fehler: {e}")
            return []
    
    def cancel_booking(self,bid,cancelled_by):
        try:
            self.db.collection('bookings').document(bid).update({
                'status':'cancelled',
                'cancelled_by':cancelled_by,
                'cancelled_at':firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Buchung storniert: {bid}")
            return True
        except Exception as e:
            print(f"❌ cancel_booking Fehler: {e}")
            return False
    
    def get_bookings_between(self, von, bis, status='confirmed'):
        """Alle Buchungen eines Zeitraums mit EINER Abfrage.

        Ersetzt Schleifen, die je Slot bzw. je Nutzer einzeln abgefragt haben -
        auf dem Firestore-Free-Tier zaehlt jeder Lesezugriff.
        """
        try:
            q = self.db.collection('bookings')
            if status:
                q = q.where('status', '==', status)
            result = []
            for doc in q.where('slot_date', '>=', von).where('slot_date', '<=', bis).stream():
                data = doc.to_dict()
                data['id'] = doc.id
                result.append(data)
            return result
        except Exception as e:
            print(f"⚠️ get_bookings_between Fallback: {e}")
            # Ohne passenden Composite-Index: einmal laden und im Speicher filtern
            try:
                result = []
                for doc in self.db.collection('bookings').stream():
                    b = doc.to_dict()
                    if status and b.get('status') != status:
                        continue
                    if von <= b.get('slot_date', '') <= bis:
                        b['id'] = doc.id
                        result.append(b)
                return result
            except Exception as e2:
                print(f"❌ get_bookings_between Fehler: {e2}")
                return []

    def count_bookings_per_user(self):
        """Buchungen je E-Mail-Adresse mit EINER Abfrage -> Counter."""
        try:
            return Counter(
                doc.to_dict().get('user_email')
                for doc in self.db.collection('bookings')
                .where('status', '==', 'confirmed').stream()
            )
        except Exception as e:
            print(f"❌ count_bookings_per_user Fehler: {e}")
            return Counter()

    def restore_booking(self, bid):
        """Macht eine Stornierung rueckgaengig (Rollback bei fehlgeschlagener Umbuchung)."""
        try:
            self.db.collection('bookings').document(bid).update({
                'status': 'confirmed',
                'cancelled_by': firestore.DELETE_FIELD,
                'cancelled_at': firestore.DELETE_FIELD,
                'restored_at': firestore.SERVER_TIMESTAMP
            })
            print(f"↩️ Buchung wiederhergestellt: {bid}")
            return True
        except Exception as e:
            print(f"❌ restore_booking Fehler: {e}")
            return False

    def get_setting(self,key,default=''):
        try:
            doc = self.db.collection('settings').document(key).get()
            return doc.to_dict().get('value',default) if doc.exists else default
        except:
            return default
    
    def set_setting(self,key,value):
        try:
            self.db.collection('settings').document(key).set({
                'value':value,
                'updated_at':firestore.SERVER_TIMESTAMP
            },merge=True)
            return True
        except:
            return False
    
    def archive_old(self):
        """Alte Buchungen archivieren"""
        try:
            months = 12
            archive_date = (datetime.now()-timedelta(days=30*months)).strftime("%Y-%m-%d")
            count = 0
            for doc in self.db.collection('bookings').where('slot_date','<',archive_date).stream():
                self.db.collection('archive').add(doc.to_dict())
                doc.reference.delete()
                count += 1
            if count > 0:
                print(f"✅ {count} Buchungen archiviert")
            return count
        except Exception as e:
            print(f"❌ archive_old Fehler: {e}")
            return 0

ww_db = WasserwachtDB()

# ===== E-MAIL KLASSE (VOLLSTÄNDIG MIT TEMPLATE-SUPPORT) =====
class Mailer:
    """E-Mail Versand mit detailliertem Error-Handling und Template-System"""
    def __init__(self):
        if hasattr(st,'secrets'):
            self.server = st.secrets.get("SMTP_SERVER","smtp.gmail.com")
            self.port = int(st.secrets.get("SMTP_PORT",587))
            self.user = st.secrets.get("SMTP_USER","")
            self.pw = st.secrets.get("SMTP_PASSWORD","")
            self.admin_receiver = st.secrets.get("ADMIN_EMAIL_RECEIVER","")
            self.fromname = "Wasserwacht Dienstplan"
        else:
            self.server = self.port = self.user = self.pw = self.admin_receiver = ""
            self.fromname = "Dienstplan"
    
    def send(self, to, subject, body, attachments=None, html=False):
        """
        Sendet eine E-Mail mit detailliertem Error-Handling
        Returns: (success: bool, error_message: str)
        """
        if not self.user or not self.pw:
            return False, "❌ E-Mail: Keine SMTP Credentials in secrets.toml konfiguriert"
        
        if not to:
            return False, "❌ E-Mail: Keine Empfänger-Adresse angegeben"
        
        try:
            msg = MIMEMultipart()
            msg['From'] = email.utils.formataddr((self.fromname, self.user))
            msg['To'] = to
            msg['Subject'] = subject
            msg['Date'] = email.utils.formatdate(localtime=True)
            msg.attach(MIMEText(body, 'html' if html else 'plain', 'utf-8'))
            
            if attachments:
                for filename, data in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(data)
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename={filename}')
                    msg.attach(part)
            
            with smtplib.SMTP(self.server, self.port, timeout=60) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                
                try:
                    smtp.login(self.user, self.pw)
                except smtplib.SMTPAuthenticationError as auth_err:
                    return False, f"❌ SMTP Login fehlgeschlagen: {str(auth_err)}\n\nPrüfen Sie:\n1. Ist SMTP_USER korrekt? (aktuell: {self.user})\n2. Verwenden Sie ein Gmail App-Passwort?\n3. Ist 2-Faktor-Auth aktiviert?"
                
                smtp.send_message(msg)
            
            return True, f"✅ E-Mail erfolgreich an {to} gesendet"
            
        except smtplib.SMTPException as smtp_err:
            return False, f"❌ SMTP Fehler: {type(smtp_err).__name__}: {str(smtp_err)}"
        except Exception as e:
            return False, f"❌ E-Mail Fehler: {type(e).__name__}: {str(e)}"
    
    # ===== TEMPLATE-VERSAND =====
    # Bis V8.1 wiederholte jede Methode dieselbe Lade-, Ersetz- und
    # Sendelogik. Sie liegt jetzt einmal in _send_template().

    def _base_data(self, **extra):
        """Platzhalter, die in jeder Nachricht verfuegbar sind."""
        data = {
            'org_name': ww_db.get_setting('org_name', 'Wasserwacht'),
            'org_email': self.admin_receiver,
            'current_date': datetime.now(TZ).strftime('%d.%m.%Y %H:%M'),
        }
        data.update({k: v for k, v in extra.items() if v is not None})
        return data

    def _send_template(self, to, template_key, default_subject, default_body, data):
        """Laedt das Template aus den Einstellungen, ersetzt Platzhalter, sendet."""
        if not to:
            return False, "❌ E-Mail: Keine Empfänger-Adresse angegeben"

        subject = ww_db.get_setting(f'{template_key}_subject', default_subject) or default_subject
        body = ww_db.get_setting(f'{template_key}_body', default_body) or default_body

        for key, value in data.items():
            placeholder = '{' + key + '}'
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))

        return self.send(to, subject, body)

    def send_booking_confirmation(self, user_email, user_name, slot_date, slot_time):
        """Buchungsbestätigung senden"""
        return self._send_template(
            user_email, 'email_booking',
            'Buchungsbestätigung - {date}',
            """Hallo {name},

deine Buchung wurde bestätigt:

📅 Datum: {date}
⏰ Uhrzeit: {time}

Bei Fragen melde dich gerne unter {org_email}.

Viele Grüße,
Dein {org_name} Team 🌊""",
            self._base_data(name=user_name, date=fmt_de(slot_date),
                            time=slot_time, email=user_email)
        )

    def send_cancellation(self, user_email, user_name, slot_date, slot_time, comment=None):
        """Stornierungsbestätigung senden"""
        return self._send_template(
            user_email, 'email_cancellation',
            'Stornierung - {date}',
            """Hallo {name},

deine Buchung wurde storniert:

📅 Datum: {date}
⏰ Uhrzeit: {time}
{comment}
Viele Grüße,
Dein {org_name} Team 🌊""",
            self._base_data(name=user_name, date=fmt_de(slot_date),
                            time=slot_time, email=user_email,
                            comment=("\n💬 Grund: " + comment + "\n") if comment else "")
        )

    def send_reminder(self, user_email, user_name, slot_date, slot_time):
        """Erinnerung senden"""
        return self._send_template(
            user_email, 'email_reminder',
            '⏰ Erinnerung: Dienst morgen - {date}',
            """Hallo {name},

dein Dienst ist morgen:

📅 Datum: {date}
⏰ Uhrzeit: {time}

Bis morgen!
Dein {org_name} Team 🌊""",
            self._base_data(name=user_name, date=fmt_de(slot_date),
                            time=slot_time, email=user_email)
        )

    def send_welcome(self, user_email, user_name):
        """Bestätigung der Registrierung - Konto wartet auf Freigabe"""
        return self._send_template(
            user_email, 'email_welcome',
            'Deine Registrierung bei {org_name}',
            """Hallo {name},

danke für deine Registrierung bei {org_name}! 🌊

Dein Konto wurde angelegt und muss noch von einem Administrator
freigegeben werden. Sobald das erledigt ist, erhältst du eine
weitere E-Mail und kannst dich anmelden.

📧 Deine E-Mail: {email}

Bei Fragen erreichst du uns unter {org_email}.

Viele Grüße,
Dein {org_name} Team""",
            self._base_data(name=user_name, email=user_email)
        )

    def send_account_approved(self, user_email, user_name):
        """Konto wurde von einem Admin freigegeben"""
        return self._send_template(
            user_email, 'email_approved',
            '✅ Dein Zugang ist freigeschaltet - {org_name}',
            """Hallo {name},

dein Konto wurde freigegeben. Du kannst dich ab sofort anmelden
und Schichten buchen. 🌊

📧 Deine E-Mail: {email}

Viele Grüße,
Dein {org_name} Team""",
            self._base_data(name=user_name, email=user_email)
        )

    def send_password_reset(self, user_email, user_name, new_password):
        """Password Reset Email senden"""
        return self._send_template(
            user_email, 'email_password_reset',
            '🔐 Passwort zurückgesetzt - {org_name}',
            """Hallo {name},

dein Passwort wurde von einem Administrator zurückgesetzt.

🔑 Dein neues temporäres Passwort:
{new_password}

⚠️ WICHTIG - Bitte beachten:
1. Verwende dieses Passwort für die nächste Anmeldung
2. Ändere dein Passwort danach im Profil unter "Sicherheit"
3. Bewahre dieses Passwort sicher auf

📧 Deine E-Mail: {email}

Bei Fragen erreichst du uns unter {org_email}.

Viele Grüße,
Dein {org_name} Team 🌊

---
Gesendet am {current_date}""",
            self._base_data(name=user_name, email=user_email,
                            new_password=new_password)
        )

    def send_admin_notification(self, user_name, user_email, user_phone, slot_date, slot_time):
        """Admin-Benachrichtigung bei neuer Buchung"""
        if not self.admin_receiver:
            return False, "Keine Admin-E-Mail konfiguriert"
        return self._send_template(
            self.admin_receiver, 'email_admin_notification',
            '🔔 Neue Buchung: {name} - {date}',
            """Neue Buchung im Dienstplan:

👤 Name: {name}
📧 E-Mail: {email}
📱 Telefon: {phone}

📅 Datum: {date}
⏰ Uhrzeit: {time}

Gebucht am: {current_date}""",
            self._base_data(name=user_name, email=user_email,
                            phone=user_phone or 'Nicht angegeben',
                            date=fmt_de(slot_date), time=slot_time)
        )

    def send_registration_notice(self, user_name, user_email, user_phone):
        """Admin ueber eine neue, freizugebende Registrierung informieren"""
        if not self.admin_receiver:
            return False, "Keine Admin-E-Mail konfiguriert"
        return self._send_template(
            self.admin_receiver, 'email_registration_notice',
            '👤 Neue Registrierung wartet auf Freigabe: {name}',
            """Eine neue Registrierung wartet auf Freigabe:

👤 Name: {name}
📧 E-Mail: {email}
📱 Telefon: {phone}

Registriert am: {current_date}

Freigeben unter: Benutzer -> Offene Freigaben""",
            self._base_data(name=user_name, email=user_email,
                            phone=user_phone or 'Nicht angegeben')
        )


# ===== SMS KLASSE (VOLLSTÄNDIG MIT TEMPLATE-SUPPORT) =====
class TwilioSMS:
    """SMS Versand mit Twilio und robuster Telefonnummer-Formatierung"""
    def __init__(self):
        if hasattr(st, 'secrets'):
            self.enabled = st.secrets.get("ENABLE_SMS_REMINDER", "false").lower() == "true"
            self.account_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
            self.auth_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
            self.from_number = st.secrets.get("TWILIO_PHONE_NUMBER", "")
            
            if self.account_sid and self.auth_token:
                try:
                    self.client = Client(self.account_sid, self.auth_token)
                except Exception as e:
                    print(f"⚠️ Twilio-Client nicht initialisierbar: {e}")
                    self.client = None
                    self.enabled = False
            else:
                self.client = None
                self.enabled = False
        else:
            self.enabled = False
            self.client = None
            self.from_number = ""
    
    def format_phone_number(self, phone):
        """Formatiert Telefonnummern für Twilio (E.164 Format)"""
        if not phone:
            return None
        
        phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        if phone.startswith('+'):
            return phone
        if phone.startswith('0'):
            return '+49' + phone[1:]
        if phone[0].isdigit():
            return '+49' + phone
        
        return None
    
    def send(self, to, body):
        """Sendet SMS über Twilio"""
        if not self.enabled:
            return False, "SMS ist deaktiviert"
        
        if not self.client:
            return False, "❌ Twilio Client konnte nicht initialisiert werden"
        
        if not self.from_number:
            return False, "❌ Keine Twilio-Telefonnummer konfiguriert"
        
        if not self.from_number.startswith('+'):
            return False, f"❌ Twilio-Nummer muss mit + beginnen (aktuell: {self.from_number})"
        
        formatted_to = self.format_phone_number(to)
        if not formatted_to:
            return False, f"❌ Ungültige Telefonnummer: {to}"
        
        try:
            message = self.client.messages.create(
                to=formatted_to,
                from_=self.from_number,
                body=body
            )
            
            if message.sid:
                return True, f"✅ SMS erfolgreich an {formatted_to} gesendet (SID: {message.sid})"
            else:
                return False, "❌ SMS-Versand fehlgeschlagen"
                
        except Exception as e:
            error_msg = f"❌ Twilio Fehler: {type(e).__name__}: {str(e)}"
            if "Unable to create record" in str(e):
                error_msg += f"\n\nMögliche Ursachen:\n1. Ziel-Nummer ist ungültig: {formatted_to}\n2. Twilio-Nummer ist nicht SMS-fähig"
            elif "authenticate" in str(e).lower():
                error_msg += "\n\nPrüfen Sie TWILIO_ACCOUNT_SID und TWILIO_AUTH_TOKEN"
            return False, error_msg
    
    def send_booking_confirmation(self, phone, name, slot_date, slot_time):
        """SMS-Buchungsbestätigung - verwendet Template"""
        body_template = ww_db.get_setting('sms_booking_body',
            """🌊 Buchung bestätigt: {name}
📅 {date}
⏰ {time}

{org_name}""")
        
        data = {
            'name': name,
            'date': fmt_de(slot_date),
            'time': slot_time,
            'org_name': ww_db.get_setting('org_name', 'Wasserwacht')
        }
        
        body = body_template
        for key, value in data.items():
            body = body.replace('{' + key + '}', str(value))
        
        return self.send(phone, body)
    
    def send_reminder(self, phone, name, slot_date, slot_time):
        """SMS-Erinnerung - verwendet Template"""
        body_template = ww_db.get_setting('sms_reminder_body',
            """⏰ Erinnerung: Dienst morgen!
📅 {date}
⏰ {time}

{org_name}""")
        
        data = {
            'name': name,
            'date': fmt_de(slot_date),
            'time': slot_time,
            'org_name': ww_db.get_setting('org_name', 'Wasserwacht')
        }
        
        body = body_template
        for key, value in data.items():
            body = body.replace('{' + key + '}', str(value))
        
        return self.send(phone, body)

# ===== INIT =====
mailer = Mailer()
sms_client = TwilioSMS()

# ===== SESSION STATE INIT =====
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'kalender'
if 'dark_mode' not in st.session_state:
    # Standard ist der Dark Mode; er passt zu base='dark' in
    # .streamlit/config.toml, damit Streamlits eigene Elemente
    # dieselbe Grundfarbe haben wie unser CSS.
    st.session_state.dark_mode = ww_db.get_setting('dark_mode', 'true') != 'false'
if 'selected_week' not in st.session_state:
    st.session_state.selected_week = week_start()

# ===== LOGIN & REGISTRIERUNG =====
def login_page():
    st.title("🌊 Wasserwacht Dienstplan+")
    st.markdown(f"**Version:** {VERSION}")

    if st.session_state.pop('session_expired', False):
        st.info("🔒 Du wurdest wegen längerer Inaktivität abgemeldet. "
                "Bitte melde dich erneut an.")
    
    tab1, tab2 = st.tabs(["🔐 Anmelden", "📝 Registrieren"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("E-Mail")
            password = st.text_input("Passwort", type="password")
            angemeldet_bleiben = st.checkbox(
                "Angemeldet bleiben", value=True,
                help="Auf diesem Gerät angemeldet bleiben. Auf gemeinsam "
                     "genutzten Geräten bitte abwählen.")
            submit = st.form_submit_button("Anmelden", use_container_width=True)
            
            if submit:
                if email and password:
                    success, user, reason = ww_db.auth(email, password)
                    if success:
                        st.session_state.user = user
                        st.session_state.last_activity = datetime.now()
                        st.session_state.pop('session_expired', None)
                        st.session_state.cookie_geprueft = True

                        tage = get_remember_days()
                        if angemeldet_bleiben and tage > 0:
                            token = ww_db.create_session(user['id'], tage=tage)
                            if token and cookie_setzen(SESSION_COOKIE_NAME, token, tage):
                                st.session_state.dauersitzung = True

                        st.success(f"✅ Willkommen, {user['name']}!")
                        st.rerun()
                    elif reason == 'pending':
                        st.warning("⏳ Dein Konto wurde noch nicht freigegeben. "
                                   "Ein Administrator prüft deine Registrierung.")
                    elif reason == 'disabled':
                        st.error("❌ Dein Konto ist deaktiviert. "
                                 "Bitte wende dich an einen Administrator.")
                    else:
                        st.error("❌ Ungültige Anmeldedaten")
                else:
                    st.warning("⚠️ Bitte alle Felder ausfüllen")
    
    with tab2:
        with st.form("register_form"):
            st.markdown("### Neuen Account erstellen")
            reg_name = st.text_input("Name*")
            reg_email = st.text_input("E-Mail*")
            reg_phone = st.text_input("Telefon (optional)", placeholder="+49 oder 0172...")
            reg_pw = st.text_input("Passwort*", type="password")
            reg_pw2 = st.text_input("Passwort wiederholen*", type="password")
            
            email_notif = st.checkbox("E-Mail Benachrichtigungen", value=True)
            sms_notif = st.checkbox("SMS Benachrichtigungen", value=False)
            
            reg_submit = st.form_submit_button("Registrieren", use_container_width=True)
            
            if reg_submit:
                if not reg_name or not reg_email or not reg_pw:
                    st.error("❌ Bitte alle Pflichtfelder (*) ausfüllen")
                elif '@' not in reg_email or '.' not in reg_email:
                    st.error("❌ Bitte eine gültige E-Mail-Adresse angeben")
                elif reg_pw != reg_pw2:
                    st.error("❌ Passwörter stimmen nicht überein")
                elif len(reg_pw) < 6:
                    st.error("❌ Passwort muss mindestens 6 Zeichen haben")
                else:
                    # Neue Konten sind bis zur Freigabe durch einen Admin inaktiv.
                    # Die Auswahl der Benachrichtigungen wird jetzt uebernommen -
                    # bis V8.1 wurden die Checkboxen ignoriert.
                    success, msg = ww_db.create_user(
                        reg_email, reg_name, reg_phone, reg_pw,
                        active=False, pending_approval=True,
                        email_notifications=email_notif,
                        sms_notifications=sms_notif
                    )
                    if success:
                        st.success("✅ Registrierung eingegangen!")
                        st.info("⏳ Ein Administrator muss dein Konto noch freigeben. "
                                "Du erhältst eine E-Mail, sobald du dich anmelden kannst.")
                        st.balloons()
                        mailer.send_welcome(reg_email, reg_name)
                        mailer.send_registration_notice(reg_name, reg_email, reg_phone)
                    else:
                        st.error(f"❌ {msg}")

def logout():
    # Erst die Dauersitzung beenden, dann die Sitzung im Speicher leeren -
    # sonst gilt das Cookie weiter und meldet sofort wieder an.
    token = cookie_lesen(SESSION_COOKIE_NAME)
    if token:
        ww_db.delete_session(token)
        cookie_loeschen(SESSION_COOKIE_NAME)

    st.session_state.user = None
    st.session_state.page = 'kalender'
    for schluessel in ('last_activity', 'dauersitzung', 'cookie_geprueft',
                       'cookie_zweiter_versuch'):
        st.session_state.pop(schluessel, None)
    st.rerun()

# ===== NAVIGATION =====
def show_navigation():
    user = st.session_state.user
    is_admin = user.get('role') == 'admin' if user else False
    
    with st.sidebar:
        st.title(f"👤 {user.get('name', 'Benutzer')}")
        st.markdown(f"**{user.get('email')}**")
        
        if is_admin:
            st.markdown("🔑 **Administrator**")
        
        st.divider()
        
        # Navigation Buttons
        pages = [
            ('kalender', '📅 Kalender'),
            ('meine_buchungen', '📋 Meine Buchungen'),
            ('profil', '👤 Profil'),
            ('statistik', '📊 Statistik'),
            ('handbuch', '📖 Handbuch'),
            ('impressum', '⚖️ Impressum'),
        ]
        
        if is_admin:
            pages.extend([
                ('verwaltung', '⚙️ Verwaltung'),
                ('benutzer', '👥 Benutzer'),
                ('export', '💾 Export'),
                ('vorlagen', '📧 Vorlagen'),
                ('debug', '🔧 Debug'),
            ])
        
        for page_id, label in pages:
            if st.button(label, key=f"nav_{page_id}", use_container_width=True):
                st.session_state.page = page_id
                st.rerun()
        
        st.divider()
        
        # Dark Mode Toggle
        # ===== iOS-STYLE DARK MODE TOGGLE =====
        st.markdown("---")
        st.markdown("### 🎨 Design")
    
        # Custom iOS-Style Toggle mit CSS
        current_mode = st.session_state.dark_mode
    
        toggle_html = f"""
        <style>
        .theme-toggle {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 1rem;
            background: {'#1E1E1E' if current_mode else '#FFFFFF'};
            border: 2px solid {'#2C2C2C' if current_mode else '#E0E0E0'};
            border-radius: 12px;
            margin: 0.5rem 0;
            box-shadow: 0 2px 4px rgba(0, 0, 0, {'0.3' if current_mode else '0.1'});
            transition: all 0.3s ease;
        }}
    
        .theme-label {{
            font-size: 0.9rem;
            font-weight: 500;
            color: {'#FFFFFF' if current_mode else '#1A1A1A'};
        }}
    
        .theme-icon {{
            font-size: 1.2rem;
        }}
        </style>
    
        <div class="theme-toggle">
            <span class="theme-icon">{'🌙' if current_mode else '☀️'}</span>
            <span class="theme-label">{'Dark Mode' if current_mode else 'Light Mode'}</span>
        </div>
        """
    
        st.markdown(toggle_html, unsafe_allow_html=True)
    
        # Toggle Button
        col1, col2 = st.columns(2)
        with col1:
            if not current_mode:
                if st.button("🌙 Dark", key="switch_dark", use_container_width=True):
                    st.session_state.dark_mode = True
                    if is_admin:
                        ww_db.set_setting('dark_mode', 'true')
                    st.rerun()
        with col2:
            if current_mode:
                if st.button("☀️ Light", key="switch_light", use_container_width=True):
                    st.session_state.dark_mode = False
                    if is_admin:
                        ww_db.set_setting('dark_mode', 'false')
                    st.rerun()

        st.divider()
        
        if st.button("🚪 Abmelden", use_container_width=True):
            logout()
        
        st.divider()
        st.caption(f"Version {VERSION}")
# ===== KALENDER SEITE (KOMPLETT ÜBERARBEITET) =====
def kalender_page():
    """Kalender-Seite - Original-Funktionalität mit modernem 3D-Design"""
    user = st.session_state.user
    
    st.title("📅 Wochenschichten buchen")
    st.caption("Buchen Sie Ihre Schichten für die kommenden Wochen")
    
    # Session State für Woche
    if 'selected_week' not in st.session_state:
        st.session_state.selected_week = week_start()
    
    # ===== WOCHENAUSWAHL =====
    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    
    with col1:
        kw = st.session_state.selected_week.isocalendar()[1]
        jahr = st.session_state.selected_week.year
        st.markdown(f"### KW {kw}, {jahr}")
        st.caption(f"Woche ab {fmt_de(st.session_state.selected_week)}")
    
    with col2:
        if st.button("⬅️ Vorherige", use_container_width=True):
            st.session_state.selected_week = week_start(
                st.session_state.selected_week - timedelta(days=7)
            )
            st.rerun()
    
    with col3:
        if st.button("Nächste ➡️", use_container_width=True):
            st.session_state.selected_week = week_start(
                st.session_state.selected_week + timedelta(days=7)
            )
            st.rerun()
    
    with col4:
        if st.button("🔄 Diese Woche", use_container_width=True):
            st.session_state.selected_week = week_start()
            st.rerun()
    
    st.divider()
    
    # ===== BUCHUNGEN LADEN =====
    ws_str = st.session_state.selected_week.strftime("%Y-%m-%d")
    bookings = ww_db.get_week_bookings(ws_str)
    
    # ===== SLOTS MIT 3D-CARDS ANZEIGEN =====
    for slot_config in WEEKLY_SLOTS:
        sd = slot_date(st.session_state.selected_week, slot_config['day'])
        
        # Blockierung prüfen
        blocked = is_blocked(sd)
        reason = block_reason(sd) if blocked else None
        
        # Buchung suchen
        booking = None
        for b in bookings:
            if b.get('slot_date') == sd and b.get('slot_time', '').startswith(slot_config['start']):
                booking = b
                break
        
        # ===== STATUS =====
        if blocked:
            status_class = "blocked"
            status_text = f"🚫 Blockiert ({reason})"
            status_icon = "🚫"
        elif booking:
            status_class = "booked"
            status_text = f"✅ Gebucht von {booking.get('user_name', 'N/A')}"
            status_icon = "✅"
        else:
            status_class = "free"
            status_text = "✨ Verfügbar"
            status_icon = "✨"
        
        # ===== 3D CARD =====
        st.markdown(f"""
        <div class="slot-card {status_class}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                <div style="flex: 1;">
                    <h3 style="margin: 0; font-size: 1.15rem; font-weight: 700;">{slot_config['day_name']}</h3>
                    <p style="margin: 0.3rem 0 0 0; font-size: 0.9rem; opacity: 0.85;">
                        📅 {fmt_de(sd)} | 🕐 {slot_config['start']} - {slot_config['end']}
                    </p>
                </div>
                <div style="font-size: 1.8rem; line-height: 1;">
                    {status_icon}
                </div>
            </div>
            <div class="status-badge {status_class}">
                {status_text}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # ===== AKTIONEN (WIE IM ORIGINAL) =====
        if not blocked:
            if booking:
                # Gebuchter Slot
                is_admin_user = user.get('role') == 'admin'
                if booking.get('user_email') == user.get('email') or is_admin_user:
                    slot_time_str = f"{slot_config['start']} - {slot_config['end']}"
                    allowed, hinweis = can_cancel(sd, slot_time_str, is_admin=is_admin_user)

                    col_btn1, col_btn2 = st.columns([4, 1])
                    if not allowed:
                        with col_btn1:
                            st.caption(f"🔒 {hinweis}")
                    else:
                        with col_btn2:
                            if st.button("❌ Stornieren",
                                         key=f"cancel_{sd}_{slot_config['start']}",
                                         use_container_width=True):
                                success = ww_db.cancel_booking(booking['id'], user.get('email'))
                                if success:
                                    booked_user = ww_db.get_user(booking.get('user_email')) or {}
                                    # Unbekanntes Konto -> Standardwerte,
                                    # die Stornomail geht trotzdem raus
                                    if notify_pref(booked_user, 'email', 'cancellation'):
                                        mailer.send_cancellation(
                                            booking.get('user_email'),
                                            booking.get('user_name'),
                                            sd, slot_time_str
                                        )
                                    st.success("✅ Stornierung erfolgreich!")
                                    st.rerun()
                                else:
                                    st.error("❌ Fehler bei der Stornierung")
            else:
                # Freier Slot - DIREKTER BUTTON WIE IM ORIGINAL
                col_info, col_btn = st.columns([4, 1])
                with col_btn:
                    if st.button("📝 Buchen", key=f"book_{sd}_{slot_config['start']}", use_container_width=True, type="primary"):
                        # Direkt buchen mit Session-User-Daten
                        success, msg = ww_db.create_booking(
                            sd,
                            f"{slot_config['start']} - {slot_config['end']}",
                            user.get('email'),
                            user.get('name'),
                            user.get('phone', '')
                        )
                        
                        if success:
                            # Benachrichtigungen senden
                            if notify_pref(user, 'email', 'booking'):
                                mailer.send_booking_confirmation(
                                    user.get('email'),
                                    user.get('name'),
                                    sd,
                                    f"{slot_config['start']} - {slot_config['end']}"
                                )

                            if wants_sms(user, 'booking'):
                                sms_client.send_booking_confirmation(
                                    user.get('phone'),
                                    user.get('name'),
                                    sd,
                                    f"{slot_config['start']} - {slot_config['end']}"
                                )

                            # Admin-Benachrichtigung
                            if user.get('role') != 'admin':
                                mailer.send_admin_notification(
                                    user.get('name'),
                                    user.get('email'),
                                    user.get('phone', ''),
                                    sd,
                                    f"{slot_config['start']} - {slot_config['end']}"
                                )
                            
                            st.success(f"✅ {msg}")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
        
        st.markdown("---")
    
    # ===== ADMIN-ÜBERSICHT =====
    if user.get('role') == 'admin':
        st.divider()
        with st.expander("🔍 Wochenübersicht (Admin)", expanded=False):
            if bookings:
                st.markdown(f"**📊 {len(bookings)} Buchung(en):**")
                for b in sorted(bookings, key=lambda x: (x.get('slot_date', ''), x.get('slot_time', ''))):
                    st.markdown(f"- **{fmt_de(b.get('slot_date'))}** | {b.get('slot_time')} | {b.get('user_name')} ({b.get('user_email')})")
            else:
                st.info("Noch keine Buchungen in dieser Woche")

# ===== MEINE BUCHUNGEN =====
def meine_buchungen_page():
    user = st.session_state.user
    
    st.title("📋 Meine Buchungen")
    
    bookings = ww_db.get_user_bookings(user['email'], future_only=False)
    
    if not bookings:
        st.info("Du hast noch keine Buchungen.")
        return
    
    # Nach zukünftig/vergangen filtern
    today = datetime.now().date().strftime("%Y-%m-%d")
    future = [b for b in bookings if b['slot_date'] >= today]
    past = [b for b in bookings if b['slot_date'] < today]
    
    tab1, tab2 = st.tabs([f"🔜 Zukünftig ({len(future)})", f"📅 Vergangen ({len(past)})"])
    
    with tab1:
        if not future:
            st.info("Keine zukünftigen Buchungen.")
        else:
            for b in future:
                with st.expander(f"{fmt_de(b['slot_date'])} - {b.get('slot_time', 'N/A')}", expanded=True):
                    st.markdown(f"**📅 Datum:** {fmt_de(b['slot_date'])}")
                    st.markdown(f"**⏰ Zeit:** {b.get('slot_time', 'N/A')}")
                    st.markdown(f"**📧 E-Mail:** {b['user_email']}")
                    if b.get('user_phone'):
                        st.markdown(f"**📱 Telefon:** {b['user_phone']}")
                    
                    allowed, hinweis = can_cancel(
                        b['slot_date'], b.get('slot_time', ''),
                        is_admin=user.get('role') == 'admin'
                    )
                    if not allowed:
                        st.info(f"🔒 {hinweis}")
                    elif st.button("❌ Stornieren", key=f"cancel_my_{b['id']}"):
                        if ww_db.cancel_booking(b['id'], user['email']):
                            if notify_pref(user, 'email', 'cancellation'):
                                mailer.send_cancellation(
                                    user['email'], user['name'],
                                    b['slot_date'], b.get('slot_time', '')
                                )
                            st.success("✅ Buchung storniert")
                            st.rerun()
                        else:
                            st.error("❌ Fehler bei der Stornierung")
    
    with tab2:
        if not past:
            st.info("Keine vergangenen Buchungen.")
        else:
            for b in past:
                with st.expander(f"{fmt_de(b['slot_date'])} - {b.get('slot_time', 'N/A')}"):
                    st.markdown(f"**📅 Datum:** {fmt_de(b['slot_date'])}")
                    st.markdown(f"**⏰ Zeit:** {b.get('slot_time', 'N/A')}")
                    st.markdown(f"**Status:** {b.get('status', 'confirmed')}")

# ===== PROFIL-SEITE (FÜR ALLE USER) =====
def profil_page():
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    # Titel mit Admin-Badge
    if is_admin:
        st.title("👤 Mein Profil 🔑")
        st.info("👑 **Administrator**")
    else:
        st.title("👤 Mein Profil")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📋 Profil-Info", "🔔 Benachrichtigungen", "🔒 Sicherheit"])
    
    # ===== TAB 1: PROFIL-INFO =====
    with tab1:
        st.subheader("Persönliche Informationen")
        
        with st.form("profil_info"):
            # Name (editierbar)
            name = st.text_input(
                "Name",
                value=user.get('name', ''),
                help="Ihr vollständiger Name"
            )
            
            # E-Mail: nicht selbst aenderbar.
            # Buchungen sind ueber die E-Mail-Adresse mit dem Konto verknuepft.
            # Eine Aenderung hier trennte bisher stillschweigend alle
            # bisherigen Buchungen vom Nutzer.
            st.markdown("**E-Mail-Adresse**")
            st.text_input(
                "E-Mail",
                value=user.get('email', ''),
                disabled=True,
                help="Die E-Mail-Adresse ist mit deinen Buchungen verknüpft",
                label_visibility="collapsed"
            )
            st.caption("ℹ️ Deine E-Mail-Adresse ist zugleich dein Login und mit deinen "
                       "Buchungen verknüpft. Für eine Änderung wende dich bitte an "
                       "einen Administrator.")
            
            # Telefon (editierbar mit Auto-Format)
            st.markdown("**Telefonnummer**")
            phone = st.text_input(
                "Telefon",
                value=user.get('phone', ''),
                placeholder="z.B. 0172 1234567 oder +49 172 1234567",
                help="Für SMS-Benachrichtigungen (optional)",
                label_visibility="collapsed"
            )
            
            # Vorschau der formatierten Nummer
            if phone:
                formatted_phone = sms_client.format_phone_number(phone)
                if formatted_phone:
                    st.caption(f"📱 Formatiert: {formatted_phone}")
                else:
                    st.caption("⚠️ Ungültiges Format - bitte prüfen")
            
            st.divider()
            
            # Read-Only Felder
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Rolle", value=user.get('role', 'user'), disabled=True)
            with col2:
                created = user.get('created_at')
                if created and hasattr(created, 'strftime'):
                    created_str = created.strftime('%d.%m.%Y')
                else:
                    created_str = "N/A"
                st.text_input("Mitglied seit", value=created_str, disabled=True)
            
            # Speichern-Button
            submit = st.form_submit_button("💾 Änderungen speichern", use_container_width=True, type="primary")
            
            if submit:
                # Validierung (E-Mail ist nicht editierbar, daher nicht geprueft)
                if not name:
                    st.error("❌ Name ist ein Pflichtfeld!")
                elif len(name) < 2:
                    st.error("❌ Name muss mindestens 2 Zeichen haben")
                else:
                    success = ww_db.update_user(
                        user['id'],
                        name=name,
                        phone=phone
                    )

                    if success:
                        # Session aktualisieren
                        st.session_state.user['name'] = name
                        st.session_state.user['phone'] = phone

                        st.success("✅ Profil erfolgreich aktualisiert!")
                        st.rerun()
                    else:
                        st.error("❌ Fehler beim Speichern")
    
    # ===== TAB 2: BENACHRICHTIGUNGEN =====
    with tab2:
        st.subheader("Benachrichtigungs-Einstellungen")
        st.caption("Wählen Sie, welche Benachrichtigungen Sie erhalten möchten")
        
        with st.form("benachrichtigungen"):
            st.markdown("### ✉️ E-Mail-Benachrichtigungen")
            
            email_booking = st.checkbox(
                "Buchungsbestätigungen",
                value=user.get('email_notifications_booking', True),
                help="E-Mail bei jeder neuen Buchung"
            )
            
            email_reminder = st.checkbox(
                "Erinnerungen (24h vorher)",
                value=user.get('email_notifications_reminder', True),
                help="E-Mail-Erinnerung 24h vor Ihrem Dienst"
            )
            
            email_cancellation = st.checkbox(
                "Stornierungen",
                value=user.get('email_notifications_cancellation', True),
                help="E-Mail bei Stornierung"
            )
            
            st.divider()
            st.markdown("### 📱 SMS-Benachrichtigungen")
            
            if not user.get('phone'):
                st.info("💡 Tipp: Hinterlegen Sie eine Telefonnummer unter 'Profil-Info', um SMS zu erhalten.")
            
            sms_booking = st.checkbox(
                "Buchungsbestätigungen",
                value=user.get('sms_notifications_booking', False),
                help="SMS bei jeder neuen Buchung",
                disabled=not user.get('phone')
            )
            
            sms_reminder = st.checkbox(
                "Erinnerungen",
                value=user.get('sms_notifications_reminder', False),
                help="SMS-Erinnerung vor Ihrem Dienst",
                disabled=not user.get('phone')
            )
            
            st.divider()
            
            # Speichern-Button
            submit = st.form_submit_button("💾 Einstellungen speichern", use_container_width=True, type="primary")
            
            if submit:
                success = ww_db.update_user(
                    user['id'],
                    email_notifications_booking=email_booking,
                    email_notifications_reminder=email_reminder,
                    email_notifications_cancellation=email_cancellation,
                    sms_notifications_booking=sms_booking,
                    sms_notifications_reminder=sms_reminder,
                    # Altfelder mitschreiben, damit beide Schemata konsistent
                    # bleiben, solange Bestandsdaten sie noch enthalten
                    email_notifications=email_booking,
                    sms_notifications=sms_booking
                )
                
                if success:
                    # Session aktualisieren
                    st.session_state.user['email_notifications_booking'] = email_booking
                    st.session_state.user['email_notifications_reminder'] = email_reminder
                    st.session_state.user['email_notifications_cancellation'] = email_cancellation
                    st.session_state.user['sms_notifications_booking'] = sms_booking
                    st.session_state.user['sms_notifications_reminder'] = sms_reminder
                    
                    st.success("✅ Einstellungen gespeichert!")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")
    
    # ===== TAB 3: SICHERHEIT (PASSWORT ÄNDERN) =====
    with tab3:
        st.subheader("Passwort ändern")
        st.caption("Ändern Sie hier Ihr Passwort")
        
        with st.form("passwort_aendern"):
            old_password = st.text_input(
                "Aktuelles Passwort",
                type="password",
                help="Geben Sie Ihr aktuelles Passwort ein"
            )
            
            new_password = st.text_input(
                "Neues Passwort",
                type="password",
                help="Mindestens 6 Zeichen"
            )
            
            new_password_confirm = st.text_input(
                "Neues Passwort bestätigen",
                type="password",
                help="Wiederholen Sie das neue Passwort"
            )
            
            st.divider()
            
            # Speichern-Button
            submit = st.form_submit_button("🔒 Passwort ändern", use_container_width=True, type="primary")
            
            if submit:
                # Validierung
                # Der Vergleich muss ueber pw_pruefen laufen: bcrypt erzeugt
                # bei jedem Aufruf einen neuen Salt, ein direkter Hash-
                # Vergleich koennte daher nie uebereinstimmen.
                altes_pw_korrekt = (
                    pw_pruefen(old_password, user.get('password_hash'))[0]
                    if old_password else False
                )

                if not old_password or not new_password or not new_password_confirm:
                    st.error("❌ Bitte alle Felder ausfüllen!")
                elif not altes_pw_korrekt:
                    st.error("❌ Aktuelles Passwort ist falsch!")
                elif new_password != new_password_confirm:
                    st.error("❌ Neue Passwörter stimmen nicht überein!")
                elif len(new_password) < 6:
                    st.error("❌ Passwort muss mindestens 6 Zeichen haben!")
                elif old_password == new_password:
                    st.error("❌ Neues Passwort muss sich vom alten unterscheiden!")
                else:
                    # Genau einmal hashen - sonst enthielte die Session einen
                    # anderen Hash als die Datenbank.
                    neuer_hash = hash_pw(new_password)
                    success = ww_db.update_user(
                        user['id'],
                        password_hash=neuer_hash
                    )
                    if success:
                        # Anmeldungen auf anderen Geraeten beenden und die
                        # eigene Dauersitzung erneuern
                        ww_db.delete_sessions_of_user(user['id'])
                        tage = get_remember_days()
                        if st.session_state.get('dauersitzung') and tage > 0:
                            neues_token = ww_db.create_session(user['id'], tage=tage)
                            if neues_token:
                                cookie_setzen(SESSION_COOKIE_NAME, neues_token, tage)

                    if success:
                        # Session aktualisieren
                        st.session_state.user['password_hash'] = neuer_hash

                        st.success("✅ Passwort erfolgreich geändert!")
                        st.balloons()
                    else:
                        st.error("❌ Fehler beim Ändern des Passworts")

# ===== STATISTIK =====
def statistik_page():
    st.title("📊 Statistik")
    
    # Lade alle Buchungen
    all_bookings = []
    try:
        for doc in db.collection('bookings').where('status', '==', 'confirmed').stream():
            b = doc.to_dict()
            b['id'] = doc.id
            all_bookings.append(b)
    except:
        st.error("Fehler beim Laden der Statistiken")
        return
    
    if not all_bookings:
        st.info("Noch keine Buchungen vorhanden.")
        return
    
    # Top Helfer
    st.subheader("🏆 Top Helfer")
    user_counts = Counter([b['user_name'] for b in all_bookings])
    top_10 = user_counts.most_common(10)
    
    if top_10:
        df_top = pd.DataFrame(top_10, columns=['Name', 'Anzahl Dienste'])
        fig = px.bar(df_top, x='Name', y='Anzahl Dienste', title='Top 10 Helfer')
        st.plotly_chart(fig, use_container_width=True)
    
    # Buchungen pro Monat
    st.subheader("📅 Buchungen pro Monat")
    monthly = Counter([b['slot_date'][:7] for b in all_bookings])
    df_month = pd.DataFrame(sorted(monthly.items()), columns=['Monat', 'Anzahl'])
    fig_month = px.line(df_month, x='Monat', y='Anzahl', title='Buchungen pro Monat')
    st.plotly_chart(fig_month, use_container_width=True)
# ===== VERWALTUNG (ADMIN) =====
# ===== VERWALTUNG (ADMIN) - ERWEITERT MIT FREIEN SLOTS =====
# ===== VERWALTUNG (ADMIN) - KOMPLETT MIT ADMIN-BUCHUNG =====
def verwaltung_page():
    st.title("⚙️ Verwaltung")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Alle Buchungen", 
        "🔍 Freie Slots", 
        "👥 Admin-Buchung", 
        "🗑️ Archivieren", 
        "⚙️ Einstellungen"
    ])
    
    # ===== TAB 1: ALLE BUCHUNGEN (wie gehabt) =====
    with tab1:
        st.subheader("Alle Buchungen")
        
        col1, col2 = st.columns(2)
        with col1:
            filter_status = st.selectbox("Status", ["alle", "confirmed", "cancelled"])
        with col2:
            filter_future = st.checkbox("Nur zukünftige", value=True)
        
        try:
            query = db.collection('bookings')
            if filter_status != "alle":
                query = query.where('status', '==', filter_status)
            
            all_bookings = []
            for doc in query.stream():
                b = doc.to_dict()
                b['id'] = doc.id
                all_bookings.append(b)
            
            if filter_future:
                today = datetime.now().date().strftime("%Y-%m-%d")
                all_bookings = [b for b in all_bookings if b.get('slot_date', '') >= today]
            
            all_bookings.sort(key=lambda x: x.get('slot_date', ''), reverse=True)
            
            if not all_bookings:
                st.info("Keine Buchungen gefunden.")
            else:
                st.write(f"**{len(all_bookings)} Buchungen gefunden**")
                
                for booking in all_bookings:
                    with st.expander(
                        f"{fmt_de(booking.get('slot_date', 'N/A'))} - {booking.get('user_name', 'N/A')} ({booking.get('status', 'N/A')})"
                    ):
                        col_a, col_b = st.columns([3, 1])
                        
                        with col_a:
                            st.markdown(f"**📅 Datum:** {fmt_de(booking.get('slot_date', 'N/A'))}")
                            st.markdown(f"**⏰ Zeit:** {booking.get('slot_time', 'N/A')}")
                            st.markdown(f"**👤 Name:** {booking.get('user_name', 'N/A')}")
                            st.markdown(f"**📧 E-Mail:** {booking.get('user_email', 'N/A')}")
                            if booking.get('user_phone'):
                                st.markdown(f"**📱 Telefon:** {booking.get('user_phone')}")
                            st.markdown(f"**Status:** {booking.get('status', 'N/A')}")
                        
                        with col_b:
                            if booking.get('status') == 'confirmed':
                                if st.button("❌ Stornieren", key=f"admin_cancel_{booking['id']}"):
                                    if ww_db.cancel_booking(booking['id'], 'admin'):
                                        st.success("✅ Storniert")
                                        st.rerun()
                            
                            if st.button("🗑️ Löschen", key=f"admin_del_{booking['id']}"):
                                try:
                                    db.collection('bookings').document(booking['id']).delete()
                                    st.success("✅ Gelöscht")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Fehler: {e}")
        
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
    
    # ===== TAB 2: FREIE SLOTS (wie zuvor erstellt) =====
    with tab2:
        st.subheader("🔍 Freie Slots in den nächsten 4 Wochen")
        st.caption("Übersicht über alle noch nicht gebuchten Schichten")
        
        today = datetime.now().date()
        weeks_ahead = 4

        all_slots = []
        current_week = week_start(today)

        # Alle Buchungen des Zeitraums mit einer Abfrage laden, statt je Slot
        # einzeln nachzuschlagen.
        zeitraum_ende = (current_week + timedelta(days=7 * weeks_ahead)).strftime('%Y-%m-%d')
        belegte_slots = {
            (b.get('slot_date'), b.get('slot_time'))
            for b in ww_db.get_bookings_between(today.strftime('%Y-%m-%d'), zeitraum_ende)
        }

        for week_offset in range(weeks_ahead):
            ws = current_week + timedelta(days=7 * week_offset)
            
            for slot_config in WEEKLY_SLOTS:
                slot_d = slot_date(ws, slot_config['day'])
                slot_date_obj = datetime.strptime(slot_d, '%Y-%m-%d').date()
                
                if slot_date_obj < today:
                    continue
                
                if is_blocked(slot_d):
                    continue
                
                slot_time = f"{slot_config['start']} - {slot_config['end']}"

                if (slot_d, slot_time) not in belegte_slots:
                    days_until = (slot_date_obj - today).days
                    
                    if days_until < 7:
                        color = "🔴"
                        urgency = "kritisch"
                    elif days_until < 14:
                        color = "🟠"
                        urgency = "achtung"
                    else:
                        color = "🟢"
                        urgency = "entspannt"
                    
                    all_slots.append({
                        'date': slot_d,
                        'date_obj': slot_date_obj,
                        'weekday': slot_config['day_name'],
                        'time': slot_time,
                        'days_until': days_until,
                        'color': color,
                        'urgency': urgency
                    })
        
        all_slots.sort(key=lambda x: x['date'])
        
        if all_slots:
            st.markdown("### 📊 Zusammenfassung")
            
            kritisch = len([s for s in all_slots if s['urgency'] == 'kritisch'])
            achtung = len([s for s in all_slots if s['urgency'] == 'achtung'])
            entspannt = len([s for s in all_slots if s['urgency'] == 'entspannt'])
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Gesamt", len(all_slots))
            with col2:
                st.metric("🔴 Kritisch", kritisch)
            with col3:
                st.metric("🟠 Achtung", achtung)
            with col4:
                st.metric("🟢 Entspannt", entspannt)
            
            st.divider()
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                df = pd.DataFrame([{
                    'Datum': fmt_de(s['date']),
                    'Wochentag': s['weekday'],
                    'Uhrzeit': s['time'],
                    'Tage bis Slot': s['days_until'],
                    'Dringlichkeit': s['urgency']
                } for s in all_slots])
                
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Als CSV exportieren",
                    csv,
                    file_name=f"freie_slots_{today.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col_b:
                if st.button("📧 Per E-Mail senden", use_container_width=True):
                    if mailer.admin_receiver:
                        email_body = f"""Freie Slots - Übersicht vom {today.strftime('%d.%m.%Y')}

Gesamt: {len(all_slots)} freie Slots
🔴 Kritisch: {kritisch}
🟠 Achtung: {achtung}
🟢 Entspannt: {entspannt}

Details:
---

"""
                        for s in all_slots:
                            email_body += f"{s['color']} {fmt_de(s['date'])} ({s['weekday']}) - {s['time']} - in {s['days_until']} Tagen\n"
                        
                        csv_bytes = csv.encode('utf-8')
                        
                        success, msg = mailer.send(
                            mailer.admin_receiver,
                            f"🔍 Freie Slots - {today.strftime('%d.%m.%Y')}",
                            email_body,
                            attachments=[(f"freie_slots_{today.strftime('%Y%m%d')}.csv", csv_bytes)]
                        )
                        
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
                    else:
                        st.error("❌ Keine Admin-E-Mail konfiguriert")
            
            st.divider()
            st.markdown("### 📋 Details")
            
            for slot in all_slots:
                with st.container():
                    col1, col2, col3, col4 = st.columns([1, 3, 3, 2])
                    
                    with col1:
                        st.markdown(f"### {slot['color']}")
                    with col2:
                        st.markdown(f"**{fmt_de(slot['date'])}**")
                        st.caption(slot['weekday'])
                    with col3:
                        st.markdown(f"**{slot['time']}**")
                        st.caption(f"in {slot['days_until']} Tagen")
                    with col4:
                        if slot['urgency'] == 'kritisch':
                            st.error("Dringend!")
                        elif slot['urgency'] == 'achtung':
                            st.warning("Bald fällig")
                        else:
                            st.success("Zeit vorhanden")
                    
                    st.divider()
        else:
            st.success("🎉 Alle Slots in den nächsten 4 Wochen sind gebucht!")
    
    # ===== TAB 3: ADMIN-BUCHUNG (NEU) =====
    with tab3:
        st.subheader("👥 Schichten für User buchen & umbuchen")
        
        sub_tab1, sub_tab2 = st.tabs(["➕ Neue Buchung", "🔄 Umbuchung"])
        
        # --- SUB-TAB 1: NEUE BUCHUNG ---
        with sub_tab1:
            st.markdown("### Neue Buchung für User erstellen")
            st.caption("Buchen Sie eine Schicht im Namen eines Users")
            
            with st.form("admin_neue_buchung"):
                # User auswählen
                all_users = ww_db.get_all_users()
                active_users = [u for u in all_users if u.get('active', True)]
                
                if not active_users:
                    st.error("Keine aktiven User gefunden!")
                else:
                    user_options = {f"{u['name']} ({u['email']})": u for u in active_users}
                    selected_user_str = st.selectbox(
                        "User auswählen",
                        options=list(user_options.keys()),
                        help="Wählen Sie den User, für den Sie buchen möchten"
                    )
                    selected_user = user_options[selected_user_str]
                    
                    # Datum & Zeit
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Wähle Woche
                        today = datetime.now().date()
                        weeks = []
                        for i in range(8):  # Nächsten 8 Wochen
                            ws = week_start(today + timedelta(days=7*i))
                            weeks.append((f"KW {ws.isocalendar()[1]} ({fmt_de(ws)})", ws))
                        
                        selected_week_str = st.selectbox(
                            "Woche auswählen",
                            options=[w[0] for w in weeks]
                        )
                        selected_week = [w[1] for w in weeks if w[0] == selected_week_str][0]
                    
                    with col2:
                        # Verfügbare Slots für diese Woche
                        available_slots = []
                        # Buchungen der Woche einmal laden statt je Slot
                        woche_buchungen = {
                            (b.get('slot_date'), b.get('slot_time')): b
                            for b in ww_db.get_week_bookings(
                                selected_week.strftime('%Y-%m-%d'))
                        }
                        for slot_config in WEEKLY_SLOTS:
                            slot_d = slot_date(selected_week, slot_config['day'])
                            slot_date_obj = datetime.strptime(slot_d, '%Y-%m-%d').date()

                            if slot_date_obj < today:
                                continue

                            slot_time = f"{slot_config['start']} - {slot_config['end']}"
                            booking = woche_buchungen.get((slot_d, slot_time))
                            blocked = is_blocked(slot_d)
                            
                            label = f"{slot_config['day_name']} {fmt_de(slot_d)} | {slot_time}"
                            
                            if booking:
                                label += f" (Gebucht: {booking['user_name']})"
                                available_slots.append((label, slot_d, slot_time, True, booking))
                            elif blocked:
                                label += f" (Blockiert: {block_reason(slot_d)})"
                                available_slots.append((label, slot_d, slot_time, True, None))
                            else:
                                label += " (Frei)"
                                available_slots.append((label, slot_d, slot_time, False, None))
                        
                        selected_slot = None
                        if not available_slots:
                            st.warning("Keine Slots in dieser Woche verfügbar")
                        else:
                            selected_slot_str = st.selectbox(
                                "Slot auswählen",
                                options=[s[0] for s in available_slots]
                            )
                            selected_slot = [s for s in available_slots if s[0] == selected_slot_str][0]

                    # Optionen
                    notify_user = st.checkbox("User per E-Mail/SMS benachrichtigen", value=True)

                    # Submit
                    submit = st.form_submit_button("📝 Buchung erstellen", use_container_width=True, type="primary")

                    if submit:
                        if selected_slot is None:
                            # Ohne diese Pruefung lief der Zugriff bisher in
                            # einen NameError und die Seite stuerzte ab.
                            st.error("❌ In dieser Woche gibt es keinen Slot zum Buchen. "
                                     "Bitte eine andere Woche wählen.")
                            st.stop()

                        slot_d = selected_slot[1]
                        slot_time = selected_slot[2]
                        is_occupied = selected_slot[3]

                        if is_occupied:
                            st.error("❌ Dieser Slot ist bereits gebucht oder blockiert!")
                        else:
                            # Buchung erstellen
                            success, msg = ww_db.create_booking(
                                slot_d,
                                slot_time,
                                selected_user['email'],
                                selected_user['name'],
                                selected_user.get('phone', '')
                            )
                            
                            if success:
                                st.success(f"✅ Buchung erstellt für {selected_user['name']}!")
                                
                                # Benachrichtigung
                                if notify_user:
                                    # E-Mail
                                    email_success, email_msg = mailer.send_booking_confirmation(
                                        selected_user['email'],
                                        selected_user['name'],
                                        slot_d,
                                        slot_time
                                    )
                                    if email_success:
                                        st.info(f"📧 {email_msg}")
                                    
                                    # SMS
                                    if wants_sms(selected_user, 'booking'):
                                        sms_success, sms_msg = sms_client.send_booking_confirmation(
                                            selected_user['phone'],
                                            selected_user['name'],
                                            slot_d,
                                            slot_time
                                        )
                                        if sms_success:
                                            st.info(f"📱 {sms_msg}")
                                
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
        
        # --- SUB-TAB 2: UMBUCHUNG ---
        with sub_tab2:
            st.markdown("### Bestehende Buchung umbuchen")
            st.caption("Übertragen Sie eine Buchung von einem User auf einen anderen")
            
            with st.form("admin_umbuchung"):
                # Zukünftige Buchungen laden
                today = datetime.now().date().strftime("%Y-%m-%d")
                future_bookings = []
                
                try:
                    for doc in db.collection('bookings').where('status', '==', 'confirmed').stream():
                        b = doc.to_dict()
                        b['id'] = doc.id
                        if b.get('slot_date', '') >= today:
                            future_bookings.append(b)
                except:
                    pass
                
                if not future_bookings:
                    st.info("Keine zukünftigen Buchungen vorhanden")
                else:
                    # Sortieren
                    future_bookings.sort(key=lambda x: x['slot_date'])
                    
                    # Buchung auswählen
                    booking_options = {
                        f"{fmt_de(b['slot_date'])} | {b['slot_time']} | {b['user_name']}": b
                        for b in future_bookings
                    }
                    
                    selected_booking_str = st.selectbox(
                        "Buchung auswählen",
                        options=list(booking_options.keys()),
                        help="Wählen Sie die Buchung, die umgebucht werden soll"
                    )
                    selected_booking = booking_options[selected_booking_str]
                    
                    st.info(f"**Aktuell gebucht von:** {selected_booking['user_name']} ({selected_booking['user_email']})")
                    
                    # Neuen User auswählen
                    all_users = ww_db.get_all_users()
                    active_users = [u for u in all_users if u.get('active', True) and u['email'] != selected_booking['user_email']]
                    
                    if not active_users:
                        st.error("Keine anderen User verfügbar!")
                    else:
                        user_options = {f"{u['name']} ({u['email']})": u for u in active_users}
                        new_user_str = st.selectbox(
                            "Neuer User",
                            options=list(user_options.keys()),
                            help="Wählen Sie den neuen User für diese Buchung"
                        )
                        new_user = user_options[new_user_str]
                        
                        # Kommentar
                        comment = st.text_area(
                            "Kommentar (optional)",
                            placeholder="z.B. 'Krankheit', 'Urlaub', 'Tausch', etc.",
                            help="Grund für die Umbuchung (wird in Benachrichtigung erwähnt)"
                        )
                        
                        # Benachrichtigung
                        notify_users = st.checkbox("Beide User benachrichtigen", value=True)
                        
                        # Submit
                        submit = st.form_submit_button("🔄 Umbuchung durchführen", use_container_width=True, type="primary")
                        
                        if submit:
                            # Reihenfolge ist bewusst: erst die alte Buchung
                            # stornieren (nicht loeschen - Nachvollziehbarkeit),
                            # dann die neue anlegen. Schlaegt das Anlegen fehl,
                            # wird die Stornierung zurueckgenommen, damit die
                            # Schicht nie unbesetzt zurueckbleibt.
                            if not ww_db.cancel_booking(selected_booking['id'],
                                                        f"umbuchung durch {st.session_state.user.get('email')}"):
                                st.error("❌ Die bestehende Buchung konnte nicht storniert werden. "
                                         "Es wurde nichts verändert.")
                                st.stop()

                            success, msg = ww_db.create_booking(
                                selected_booking['slot_date'],
                                selected_booking['slot_time'],
                                new_user['email'],
                                new_user['name'],
                                new_user.get('phone', '')
                            )

                            if not success:
                                # Rollback: alte Buchung wieder aktiv setzen
                                ww_db.restore_booking(selected_booking['id'])
                                st.error(f"❌ Umbuchung fehlgeschlagen: {msg}")
                                st.warning("↩️ Die ursprüngliche Buchung von "
                                           f"{selected_booking['user_name']} wurde wiederhergestellt.")
                                st.stop()

                            if success:
                                st.success(f"✅ Umbuchung erfolgreich! Slot wurde von {selected_booking['user_name']} auf {new_user['name']} übertragen.")
                                
                                # Benachrichtigungen
                                if notify_users:
                                    # Alter User: Stornierung
                                    mailer.send_cancellation(
                                        selected_booking['user_email'],
                                        selected_booking['user_name'],
                                        selected_booking['slot_date'],
                                        selected_booking['slot_time'],
                                        comment=comment or None
                                    )
                                    
                                    # Neuer User: Buchungsbestätigung
                                    mailer.send_booking_confirmation(
                                        new_user['email'],
                                        new_user['name'],
                                        selected_booking['slot_date'],
                                        selected_booking['slot_time']
                                    )
                                    
                                    if comment:
                                        st.info(f"💬 Kommentar: {comment}")
                                    
                                    st.info("📧 Beide User wurden benachrichtigt")
                                
                                st.rerun()
                            else:
                                st.error(f"❌ Fehler bei neuer Buchung: {msg}")
    
    # ===== TAB 4: ARCHIVIEREN (wie gehabt) =====
    with tab4:
        st.subheader("🗑️ Alte Buchungen archivieren")
        st.info("Buchungen älter als 12 Monate werden archiviert.")
        
        if st.button("Archivierung starten"):
            count = ww_db.archive_old()
            if count > 0:
                st.success(f"✅ {count} Buchungen archiviert")
            else:
                st.info("Keine Buchungen zum Archivieren gefunden")
    
    # ===== TAB 5: EINSTELLUNGEN (wie gehabt) =====
    with tab5:
        st.subheader("⚙️ Systemeinstellungen")

        # ===== SAISONPAUSE =====
        st.markdown("### 🏖️ Saisonpause")
        st.caption("In diesem Zeitraum sind keine Buchungen möglich. Gilt jedes Jahr erneut.")

        pause_start, pause_end = get_pause_range()
        try:
            start_default = datetime.strptime(f"2000-{pause_start}", "%Y-%m-%d").date()
            end_default = datetime.strptime(f"2000-{pause_end}", "%Y-%m-%d").date()
        except ValueError:
            start_default = datetime.strptime(f"2000-{DEFAULT_PAUSE_START}", "%Y-%m-%d").date()
            end_default = datetime.strptime(f"2000-{DEFAULT_PAUSE_END}", "%Y-%m-%d").date()

        with st.form("saisonpause_form"):
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                neu_start = st.date_input("Pause beginnt am", value=start_default,
                                          format="DD.MM.YYYY",
                                          help="Nur Tag und Monat sind relevant")
            with col_p2:
                neu_end = st.date_input("Pause endet am (einschließlich)", value=end_default,
                                        format="DD.MM.YYYY",
                                        help="Nur Tag und Monat sind relevant")

            st.caption("💡 Ein Zeitraum über den Jahreswechsel (z. B. 01.11. – 31.03.) "
                       "wird unterstützt.")

            if st.form_submit_button("💾 Saisonpause speichern", type="primary"):
                s = neu_start.strftime("%m-%d")
                e = neu_end.strftime("%m-%d")
                ok = ww_db.set_setting('season_pause_start', s)
                ok = ww_db.set_setting('season_pause_end', e) and ok
                if ok:
                    st.success(f"✅ Saisonpause gespeichert: {neu_start.strftime('%d.%m.')} "
                               f"bis {neu_end.strftime('%d.%m.')}")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")

        # Vorschau: welche der naechsten Slots waeren gesperrt?
        with st.expander("👁️ Vorschau: gesperrte Termine der nächsten 8 Wochen"):
            heute = datetime.now().date()
            gesperrt = []
            for w in range(8):
                ws = week_start(heute + timedelta(days=7 * w))
                for sc in WEEKLY_SLOTS:
                    sd_ = slot_date(ws, sc['day'])
                    if datetime.strptime(sd_, '%Y-%m-%d').date() < heute:
                        continue
                    grund = block_reason(sd_)
                    if grund:
                        gesperrt.append(f"- **{fmt_de(sd_)}** ({sc['day_name']}) – {grund}")
            if gesperrt:
                st.markdown("\n".join(gesperrt))
            else:
                st.success("Keine Sperrungen in den nächsten 8 Wochen.")

        st.divider()

        # ===== STORNOFRIST =====
        st.markdown("### ⏱️ Stornofrist")
        with st.form("stornofrist_form"):
            aktuelle_frist = get_cancel_deadline_hours()
            neue_frist = st.number_input(
                "Stunden vor Dienstbeginn, bis zu denen Nutzer selbst stornieren dürfen",
                min_value=0, max_value=336, value=aktuelle_frist, step=1
            )
            st.caption("💡 Administratoren sind von dieser Frist ausgenommen und können "
                       "jederzeit stornieren und umbuchen – auch am Diensttag selbst.")
            if st.form_submit_button("💾 Frist speichern", type="primary"):
                if ww_db.set_setting('cancel_deadline_hours', str(int(neue_frist))):
                    st.success(f"✅ Stornofrist gespeichert: {int(neue_frist)} Stunden")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")

        st.divider()

        # ===== SITZUNG =====
        st.markdown("### 🔒 Automatische Abmeldung")
        with st.form("session_form"):
            aktuell = get_session_timeout_minutes()
            neuer_wert = st.number_input(
                "Abmeldung nach ... Minuten ohne Aktivität",
                min_value=0, max_value=1440, value=aktuell, step=15
            )
            st.caption("💡 0 schaltet die automatische Abmeldung ab. "
                       "Schützt vor allem geteilte Geräte, auf denen sich "
                       "jemand anzumelden vergisst.")
            if st.form_submit_button("💾 Speichern", type="primary"):
                if ww_db.set_setting('session_timeout_minutes', str(int(neuer_wert))):
                    st.success("✅ Gespeichert"
                               if neuer_wert else "✅ Automatische Abmeldung deaktiviert")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")

        st.markdown("### 🍪 Angemeldet bleiben")
        with st.form("remember_form"):
            aktuell_tage = get_remember_days()
            neue_tage = st.number_input(
                "Tage, die eine Anmeldung auf dem Gerät gültig bleibt",
                min_value=0, max_value=365, value=aktuell_tage, step=1
            )
            st.caption("💡 0 schaltet die Funktion ab – dann muss sich jeder "
                       "bei jedem Besuch neu anmelden. Bei Passwortwechsel, "
                       "Passwort-Reset und Deaktivierung werden bestehende "
                       "Anmeldungen automatisch beendet.")
            if st.form_submit_button("💾 Speichern", type="primary"):
                if ww_db.set_setting('remember_me_days', str(int(neue_tage))):
                    st.success("✅ Gespeichert")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")

        st.divider()

        # ===== ORGANISATION =====
        st.markdown("### 🏢 Organisation")
        with st.form("org_form"):
            org_name = st.text_input("Name der Organisation",
                                     value=ww_db.get_setting('org_name', 'Wasserwacht'),
                                     help="Wird in allen E-Mails und SMS als {org_name} eingesetzt")
            if st.form_submit_button("💾 Speichern", type="primary"):
                if ww_db.set_setting('org_name', org_name):
                    st.success("✅ Gespeichert")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")

        st.divider()

        # ===== DARSTELLUNG =====
        st.markdown("### 🎨 Darstellung")
        dark = ww_db.get_setting('dark_mode', 'false') == 'true'
        new_dark = st.checkbox("Dark Mode (Global)", value=dark)
        if new_dark != dark:
            ww_db.set_setting('dark_mode', 'true' if new_dark else 'false')
            st.success("✅ Gespeichert")
            st.rerun()

# ===== BENUTZERVERWALTUNG (ADMIN) =====
def benutzer_page():
    st.title("👥 Benutzerverwaltung")
    
    users = ww_db.get_all_users()
    pending = ww_db.get_pending_users()
    # Eine Abfrage statt einer je Nutzer (vorher N+1 bei jedem Rerun)
    buchungen_je_nutzer = ww_db.count_bookings_per_user()

    # Ein zuletzt zurueckgesetztes Passwort ueberlebt den Rerun, damit der
    # Admin es notieren kann - bisher wurde es sofort wieder weggeblendet.
    shown_pw = st.session_state.pop('last_reset_password', None)
    if shown_pw:
        st.success(f"✅ Passwort für **{shown_pw['name']}** zurückgesetzt.")
        if shown_pw['mail_ok']:
            st.info(f"📧 E-Mail an {shown_pw['email']} gesendet.")
        else:
            st.error("❌ E-Mail-Versand fehlgeschlagen – bitte das Passwort manuell übergeben!")
        st.code(shown_pw['password'], language=None)
        st.caption("☝️ Bitte jetzt notieren – diese Anzeige erscheint nur einmal.")
        st.divider()

    tab_labels = ["📋 Alle Benutzer", "➕ Neuer Benutzer"]
    if pending:
        tab_labels.insert(0, f"⏳ Offene Freigaben ({len(pending)})")
        tab_pending, tab1, tab2 = st.tabs(tab_labels)
    else:
        tab_pending = None
        tab1, tab2 = st.tabs(tab_labels)

    # ===== OFFENE FREIGABEN =====
    if tab_pending is not None:
        with tab_pending:
            st.subheader("⏳ Registrierungen warten auf Freigabe")
            st.caption("Diese Konten können sich erst nach der Freigabe anmelden.")

            for u in pending:
                col_a, col_b, col_c = st.columns([4, 1, 1])
                with col_a:
                    st.markdown(f"**{u.get('name', 'N/A')}**")
                    st.caption(f"📧 {u.get('email', 'N/A')} | 📱 {u.get('phone') or '-'}")
                with col_b:
                    if st.button("✅ Freigeben", key=f"approve_{u['id']}",
                                 use_container_width=True, type="primary"):
                        if ww_db.approve_user(u['id']):
                            mailer.send_account_approved(u.get('email'), u.get('name'))
                            st.success(f"✅ {u.get('name')} freigegeben und benachrichtigt")
                            st.rerun()
                        else:
                            st.error("❌ Freigabe fehlgeschlagen")
                with col_c:
                    if st.button("🗑️ Ablehnen", key=f"reject_{u['id']}",
                                 use_container_width=True):
                        if ww_db.delete_user(u['id']):
                            st.success(f"Registrierung von {u.get('name')} abgelehnt")
                            st.rerun()
                st.divider()

    with tab1:
        st.markdown(f"**Gesamt:** {len(users)} Benutzer")
        
        # Filter
        col1, col2 = st.columns([3, 1])
        with col1:
            search = st.text_input("🔍 Suche nach Name oder E-Mail", "")
        with col2:
            role_filter = st.selectbox("Filter Rolle", ["Alle", "user", "admin"])
        
        # Gefilterte Liste
        filtered = users
        if search:
            filtered = [u for u in users if search.lower() in u.get('name', '').lower() 
                       or search.lower() in u.get('email', '').lower()]
        if role_filter != "Alle":
            filtered = [u for u in filtered if u.get('role') == role_filter]
        
        st.markdown(f"**Angezeigt:** {len(filtered)} Benutzer")
        st.divider()
        
        # User-Liste
        for u in sorted(filtered, key=lambda x: x.get('name', '')):
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 3])
                
                with col1:
                    status_icon = "✅" if u.get('active', True) else "❌"
                    role_badge = "🔑 Admin" if u.get('role') == 'admin' else "👤 User"
                    
                    st.markdown(f"**{status_icon} {u.get('name', 'N/A')}** {role_badge}")
                    st.caption(f"📧 {u.get('email', 'N/A')} | 📱 {u.get('phone', '-')}")
                
                with col2:
                    st.metric("Buchungen", buchungen_je_nutzer.get(u.get('email'), 0))
                
                with col3:
                    # Schutz vor Selbst-Aussperrung: Der angemeldete Admin darf
                    # sich nicht selbst deaktivieren oder loeschen, und der
                    # letzte aktive Admin muss erhalten bleiben.
                    is_self = u.get('email') == st.session_state.user.get('email')
                    aktive_admins = len([a for a in users
                                         if a.get('role') == 'admin' and a.get('active', True)])
                    is_last_admin = u.get('role') == 'admin' and u.get('active', True) and aktive_admins <= 1
                    lock_reason = ("eigenes Konto" if is_self
                                   else "letzter aktiver Admin" if is_last_admin else None)

                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

                    with btn_col1:
                        if st.button("✏️", key=f"edit_{u['id']}", help="Bearbeiten"):
                            st.session_state[f'edit_user_{u["id"]}'] = True
                            st.rerun()

                    with btn_col2:
                        active = u.get('active', True)
                        toggle_label = "🔓" if not active else "🔒"
                        toggle_help = ("Aktivieren" if not active else "Deaktivieren")
                        if lock_reason and active:
                            st.button(toggle_label, key=f"toggle_{u['id']}", disabled=True,
                                      help=f"Nicht möglich: {lock_reason}")
                        elif st.button(toggle_label, key=f"toggle_{u['id']}", help=toggle_help):
                            ww_db.update_user(u['id'], active=not active)
                            if active:  # wurde gerade deaktiviert
                                ww_db.delete_sessions_of_user(u['id'])
                            st.success(f"✅ User {'aktiviert' if not active else 'deaktiviert'}")
                            st.rerun()

                    with btn_col3:
                        # NEU: Password Reset Button
                        if st.button("🔑", key=f"pwreset_{u['id']}", help="Passwort zurücksetzen"):
                            st.session_state[f'confirm_reset_{u["id"]}'] = True
                            st.rerun()

                    with btn_col4:
                        if lock_reason:
                            st.button("🗑️", key=f"del_{u['id']}", disabled=True,
                                      help=f"Nicht möglich: {lock_reason}")
                        elif st.button("🗑️", key=f"del_{u['id']}", help="Löschen"):
                            st.session_state[f'confirm_delete_{u["id"]}'] = True
                            st.rerun()
                
                # NEU: Password Reset Confirmation Modal
                if st.session_state.get(f'confirm_reset_{u["id"]}', False):
                    with st.form(f"reset_confirm_form_{u['id']}"):
                        st.warning(f"⚠️ **Passwort zurücksetzen für {u.get('name')}?**")
                        st.info("""
**Was passiert:**
1. Ein neues, zufälliges Passwort wird generiert (8 Zeichen)
2. Der User erhält eine E-Mail mit dem neuen Passwort
3. Der User wird aufgefordert, sein Passwort nach dem Login zu ändern
                        """)
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.form_submit_button("✅ Ja, zurücksetzen", type="primary", use_container_width=True):
                                # Trigger Password Reset
                                success, new_pw = ww_db.trigger_password_reset(u['id'])

                                if success and new_pw:
                                    email_success, _ = mailer.send_password_reset(
                                        u.get('email'),
                                        u.get('name'),
                                        new_pw
                                    )
                                    # Ergebnis ueber den Rerun hinweg merken -
                                    # sonst wird die Anzeige des Passworts
                                    # sofort wieder weggeblendet.
                                    st.session_state['last_reset_password'] = {
                                        'name': u.get('name'),
                                        'email': u.get('email'),
                                        'password': new_pw,
                                        'mail_ok': email_success,
                                    }
                                    del st.session_state[f'confirm_reset_{u["id"]}']
                                    st.rerun()
                                else:
                                    st.error("❌ Fehler beim Zurücksetzen des Passworts")
                        
                        with col_b:
                            if st.form_submit_button("❌ Abbrechen", use_container_width=True):
                                del st.session_state[f'confirm_reset_{u["id"]}']
                                st.rerun()
                
                # Delete Confirmation Modal
                if st.session_state.get(f'confirm_delete_{u["id"]}', False):
                    with st.form(f"delete_confirm_form_{u['id']}"):
                        st.error(f"⚠️ **User {u.get('name')} wirklich löschen?**")
                        st.warning("Diese Aktion kann nicht rückgängig gemacht werden!")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.form_submit_button("✅ Ja, löschen", type="primary", use_container_width=True):
                                ww_db.delete_user(u['id'])
                                st.success(f"✅ User {u.get('name')} gelöscht")
                                del st.session_state[f'confirm_delete_{u["id"]}']
                                st.rerun()
                        with col_b:
                            if st.form_submit_button("❌ Abbrechen", use_container_width=True):
                                del st.session_state[f'confirm_delete_{u["id"]}']
                                st.rerun()
                
                # Edit Modal
                if st.session_state.get(f'edit_user_{u["id"]}', False):
                    with st.form(f"edit_form_{u['id']}"):
                        st.markdown(f"### ✏️ Bearbeiten: {u.get('name')}")
                        
                        edit_name = st.text_input("Name", value=u.get('name', ''))
                        st.text_input("E-Mail", value=u.get('email', ''), disabled=True,
                                      key=f"edit_email_{u['id']}")
                        edit_phone = st.text_input("Telefon", value=u.get('phone', ''))
                        edit_role = st.selectbox("Rolle", ["user", "admin"], 
                                                index=0 if u.get('role') == 'user' else 1)
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.form_submit_button("💾 Speichern", type="primary", use_container_width=True):
                                ww_db.update_user(u['id'], name=edit_name, phone=edit_phone, role=edit_role)
                                st.success("✅ Gespeichert!")
                                del st.session_state[f'edit_user_{u["id"]}']
                                st.rerun()
                        with col_b:
                            if st.form_submit_button("❌ Abbrechen", use_container_width=True):
                                del st.session_state[f'edit_user_{u["id"]}']
                                st.rerun()
                
                st.divider()
    
    with tab2:
        # Neuer User erstellen
        with st.form("create_user_admin"):
            st.markdown("### ➕ Neuen Benutzer erstellen")
            
            new_name = st.text_input("Name*")
            new_email = st.text_input("E-Mail*")
            new_phone = st.text_input("Telefon")
            new_pw = st.text_input("Passwort*", type="password", value="")
            new_role = st.selectbox("Rolle", ["user", "admin"])
            
            if st.form_submit_button("✅ Benutzer erstellen", type="primary", use_container_width=True):
                if not new_name or not new_email or not new_pw:
                    st.error("❌ Name, E-Mail und Passwort sind Pflichtfelder")
                elif len(new_pw) < 6:
                    st.error("❌ Passwort muss mindestens 6 Zeichen haben")
                else:
                    success, msg = ww_db.create_user(
                        new_email, new_name, new_phone, new_pw, role=new_role
                    )
                    if success:
                        # Vom Admin angelegte Konten sind sofort aktiv
                        mail_ok, _ = mailer.send_account_approved(new_email, new_name)
                        st.success(f"✅ Benutzer {new_name} erstellt")
                        if mail_ok:
                            st.info(f"📧 Zugangsinfo an {new_email} gesendet")
                        else:
                            st.warning("⚠️ Benutzer angelegt, aber E-Mail-Versand "
                                       "fehlgeschlagen – bitte Zugangsdaten manuell übergeben.")
                        st.balloons()
                    else:
                        st.error(f"❌ {msg}")

# ===== EXPORT (ADMIN) =====
def export_page():
    st.title("💾 Export & Backup")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📥 Daten exportieren")
        st.caption("Die Dateien werden direkt erzeugt – ein Klick genügt.")

        # Die Downloads lagen bisher hinter einem st.button. Nach dem
        # Herunterladen loest Streamlit einen Rerun aus, der Button ist dann
        # wieder False und der Download-Button verschwand. Daher werden die
        # Daten jetzt direkt geladen.
        stamp = datetime.now().strftime('%Y%m%d')

        try:
            bookings_raw = []
            for doc in db.collection('bookings').stream():
                b = doc.to_dict()
                b['id'] = doc.id
                for key in b:
                    if hasattr(b[key], 'strftime'):
                        b[key] = b[key].strftime('%Y-%m-%d %H:%M:%S')
                bookings_raw.append(b)

            st.download_button(
                f"📄 Buchungen als JSON ({len(bookings_raw)})",
                json.dumps(bookings_raw, indent=2, ensure_ascii=False),
                file_name=f"buchungen_{stamp}.json",
                mime="application/json",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Buchungen konnten nicht geladen werden: {e}")
            bookings_raw = []

        try:
            users = ww_db.get_all_users()
            # Passwort-Hashes werden nicht exportiert
            users_export = [{k: v for k, v in u.items() if k != 'password_hash'}
                            for u in users]
            for u in users_export:
                for key in u:
                    if hasattr(u[key], 'strftime'):
                        u[key] = u[key].strftime('%Y-%m-%d %H:%M:%S')

            st.download_button(
                f"📄 Benutzer als JSON ({len(users_export)})",
                json.dumps(users_export, indent=2, ensure_ascii=False),
                file_name=f"benutzer_{stamp}.json",
                mime="application/json",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Benutzer konnten nicht geladen werden: {e}")

        confirmed = [b for b in bookings_raw if b.get('status') == 'confirmed']
        if confirmed:
            df_export = pd.DataFrame(confirmed)
            st.download_button(
                f"📊 Bestätigte Buchungen als CSV ({len(confirmed)})",
                df_export.to_csv(index=False).encode('utf-8-sig'),
                file_name=f"statistik_{stamp}.csv",
                mime="text/csv",
                use_container_width=True
            )

            # Excel-Export - openpyxl war bislang als Abhaengigkeit
            # eingetragen, wurde aber nirgends genutzt.
            try:
                xlsx_buffer = io.BytesIO()
                spalten = ['slot_date', 'slot_time', 'user_name', 'user_email',
                           'user_phone', 'status']
                df_xlsx = df_export.reindex(
                    columns=[c for c in spalten if c in df_export.columns]
                ).rename(columns={
                    'slot_date': 'Datum', 'slot_time': 'Uhrzeit',
                    'user_name': 'Name', 'user_email': 'E-Mail',
                    'user_phone': 'Telefon', 'status': 'Status'
                }).sort_values('Datum')

                with pd.ExcelWriter(xlsx_buffer, engine='openpyxl') as writer:
                    df_xlsx.to_excel(writer, index=False, sheet_name='Dienstplan')
                    sheet = writer.sheets['Dienstplan']
                    for spalte in sheet.columns:
                        breite = max((len(str(z.value)) for z in spalte if z.value), default=10)
                        sheet.column_dimensions[spalte[0].column_letter].width = min(breite + 3, 40)

                st.download_button(
                    f"📗 Dienstplan als Excel ({len(confirmed)})",
                    xlsx_buffer.getvalue(),
                    file_name=f"dienstplan_{stamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            except Exception as e:
                st.warning(f"Excel-Export nicht möglich: {e}")
        else:
            st.info("Noch keine bestätigten Buchungen vorhanden.")
    
    with col2:
        st.subheader("📧 E-Mail Backup")
        
        if st.button("📧 Backup per E-Mail senden", use_container_width=True):
            if mailer.admin_receiver:
                try:
                    # Lade Daten
                    bookings = []
                    for doc in db.collection('bookings').stream():
                        b = doc.to_dict()
                        for key in b:
                            if hasattr(b[key], 'strftime'):
                                b[key] = b[key].strftime('%Y-%m-%d %H:%M:%S')
                        bookings.append(b)
                    
                    users = ww_db.get_all_users()
                    users_export = [{k: v for k, v in u.items() if k != 'password_hash'} for u in users]
                    
                    # ZIP erstellen
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr('buchungen.json', json.dumps(bookings, indent=2, ensure_ascii=False))
                        zf.writestr('benutzer.json', json.dumps(users_export, indent=2, ensure_ascii=False))
                    
                    zip_buffer.seek(0)
                    
                    # E-Mail senden
                    subject = f"Dienstplan Backup - {datetime.now().strftime('%d.%m.%Y')}"
                    body = f"""
                    <html><body>
                    <h2 style="color:{COLORS['rot']};">🌊 Automatisches Backup</h2>
                    <p><strong>Datum:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
                    <p><strong>Buchungen:</strong> {len(bookings)}</p>
                    <p><strong>Benutzer:</strong> {len(users)}</p>
                    </body></html>
                    """
                    
                    success, msg = mailer.send(
                        mailer.admin_receiver,
                        subject,
                        body,
                        attachments=[(f"backup_{datetime.now().strftime('%Y%m%d')}.zip", zip_buffer.getvalue())],
                        html=True
                    )
                    
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                
                except Exception as e:
                    st.error(f"Fehler: {e}")
            else:
                st.error("❌ Keine Admin-E-Mail konfiguriert")

# ===== DEBUG-PANEL (ADMIN) =====
def debug_page():
    st.title("🔧 Debug-Panel")
    
    tab1, tab2, tab3 = st.tabs(["📧 E-Mail Test", "📱 SMS Test", "⚙️ System-Info"])
    
    with tab1:
        st.markdown("### 📧 E-Mail Test")
        with st.form("email_test"):
            test_email = st.text_input("Test E-Mail Adresse")
            test_subject = st.text_input("Betreff", value="Test E-Mail")
            test_body = st.text_area("Nachricht", value="Dies ist eine Test-E-Mail vom Wasserwacht Dienstplan.")
            
            if st.form_submit_button("📧 Test-E-Mail senden", use_container_width=True):
                if test_email:
                    success, msg = mailer.send(test_email, test_subject, test_body)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Bitte E-Mail-Adresse eingeben")
    
    with tab2:
        st.markdown("### 📱 SMS Test")
        with st.form("sms_test"):
            test_phone = st.text_input("Test Telefonnummer", placeholder="0172... oder +49172...")
            test_sms_body = st.text_area("SMS Text", value="Test SMS vom Wasserwacht Dienstplan")
            
            if st.form_submit_button("📱 Test-SMS senden", use_container_width=True):
                if test_phone:
                    success, msg = sms_client.send(test_phone, test_sms_body)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Bitte Telefonnummer eingeben")
    
    with tab3:
        st.markdown("### ⚙️ System-Info")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**SMTP Konfiguration:**")
            st.code(f"""
Server: {mailer.server}
Port: {mailer.port}
User: {mailer.user[:15]}...
Password: {'✅ gesetzt' if mailer.pw else '❌ NICHT GESETZT'}
Admin: {mailer.admin_receiver}
            """)
        
        with col2:
            st.markdown("**Twilio Konfiguration:**")
            st.code(f"""
Enabled: {sms_client.enabled}
Account SID: {sms_client.account_sid[:15]}...
Auth Token: {'✅ gesetzt' if sms_client.auth_token else '❌ NICHT GESETZT'}
From Number: {sms_client.from_number}
Client: {'✅ OK' if sms_client.client else '❌ FEHLER'}
            """)
        
        st.markdown("**Firestore:**")
        st.code(f"Verbindung: {'✅ OK' if db else '❌ FEHLER'}")
        
        st.markdown("**Benutzer in DB:**")
        users_count = len(ww_db.get_all_users())
        st.code(f"Anzahl: {users_count}")

# ===== HANDBUCH (MIT EDIT-FUNKTION) =====
def handbuch_page():
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    st.title("📖 Handbuch")
    
    # Lade Handbuch-Inhalt aus Firestore
    handbuch_content = ww_db.get_setting('handbuch_content', '')
    
    # Falls leer, verwende Default-Inhalt
    if not handbuch_content:
        handbuch_content = """
## 🌊 Wasserwacht Dienstplan+ - Benutzerhandbuch

### 📅 Schichten buchen

0. **Konto**: Neue Konten muss ein Administrator freigeben, bevor die
   erste Anmeldung möglich ist.
1. **Kalender öffnen**: Gehen Sie zur Seite "📅 Kalender"
2. **Woche auswählen**: Verwenden Sie die Pfeile ⬅️ ➡️ oder "Heute"
3. **Schicht buchen**: Klicken Sie auf "📝 Buchen" bei einem verfügbaren Slot
4. **Bestätigung**: Sie erhalten eine E-Mail-Bestätigung (und SMS, falls aktiviert)

### 🚫 Blockierte Tage

- **Feiertage**: An bayerischen Feiertagen sind keine Buchungen möglich
- **Saisonpause**: Im festgelegten Pausenzeitraum ruht der Dienst.
  Den aktuellen Zeitraum pflegt der Admin unter Verwaltung → Einstellungen.

### 📋 Meine Buchungen

- Sehen Sie alle Ihre zukünftigen und vergangenen Buchungen
- Stornieren Sie Buchungen selbst bis **12 Stunden** vor Dienstbeginn.
  Danach wenden Sie sich bitte an einen Admin – er kann jederzeit
  stornieren und umbuchen.

### 📊 Statistik

- Top-10 Helfer Ranking
- Monatliche Übersichten

### ⚙️ Admin-Funktionen

**Nur für Administratoren:**

- **Verwaltung**: Alle Buchungen einsehen und verwalten,
  Saisonpause und Stornofrist einstellen
- **Benutzer**: Benutzer freigeben, erstellen, bearbeiten, löschen
- **Export**: Daten exportieren als JSON/CSV
- **Debug**: E-Mail und SMS testen
- **Handbuch**: Dieses Handbuch bearbeiten

### 💡 Tipps

- Stellen Sie in Ihrem Profil ein, welche Benachrichtigungen Sie erhalten
- Für SMS muss eine Telefonnummer im Profil hinterlegt sein
- Bei Fragen kontaktieren Sie Ihren Administrator

### 🔧 Support

Bei Problemen kontaktieren Sie den Admin über: admin@wasserwacht.de
        """
    
    # ADMIN: Bearbeiten-Modus
    if is_admin:
        tab1, tab2 = st.tabs(["📖 Ansicht", "✏️ Bearbeiten"])
        
        with tab1:
            # Nur Anzeige
            st.markdown(handbuch_content, unsafe_allow_html=True)
        
        with tab2:
            st.info("💡 Verwenden Sie **Markdown** zur Formatierung. Änderungen werden für alle Benutzer gespeichert.")
            
            # Editor
            edited_content = st.text_area(
                "Handbuch-Inhalt (Markdown)",
                value=handbuch_content,
                height=500,
                help="Verwenden Sie Markdown-Syntax: ## für Überschriften, ** für fett, * für kursiv, - für Listen"
            )
            
            col1, col2, col3 = st.columns([2, 2, 6])
            
            with col1:
                if st.button("💾 Speichern", use_container_width=True, type="primary"):
                    if ww_db.set_setting('handbuch_content', edited_content):
                        st.success("✅ Handbuch gespeichert!")
                        st.rerun()
                    else:
                        st.error("❌ Fehler beim Speichern")
            
            with col2:
                if st.button("🔄 Zurücksetzen", use_container_width=True):
                    st.info("Seite wird neu geladen...")
                    st.rerun()
            
            # Live-Vorschau
            with st.expander("👁️ Live-Vorschau", expanded=True):
                st.markdown(edited_content, unsafe_allow_html=True)
    
    # USER: Nur Ansicht
    else:
        st.markdown(handbuch_content, unsafe_allow_html=True)
        
        st.divider()
        st.caption("💡 Tipp: Haben Sie Fragen? Wenden Sie sich an Ihren Administrator.")

# ===== IMPRESSUM (MIT EDIT-FUNKTION) =====
def impressum_page():
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    st.title("⚖️ Impressum")
    
    # Lade Impressum-Inhalt aus Firestore
    impressum_content = ww_db.get_setting('impressum_content', '')
    
    # Falls leer, verwende Default-Inhalt
    if not impressum_content:
        impressum_content = """
## ⚖️ Impressum

### Angaben gemäß § 5 TMG

**Wasserwacht [Ortsgruppe]**  
[Straße und Hausnummer]  
[PLZ] [Ort]

### Vertreten durch:

[Name des Verantwortlichen]  
[Funktion/Rolle]

### Kontakt:

**Telefon:** [Telefonnummer]  
**E-Mail:** [E-Mail-Adresse]  
**Website:** [Website-URL]

### Registereintrag:

Eingetragen im Vereinsregister  
**Registergericht:** [Amtsgericht]  
**Registernummer:** [VR-Nummer]

### Verantwortlich für den Inhalt nach § 55 Abs. 2 RStV:

[Name]  
[Adresse]

### Haftungsausschluss:

#### Haftung für Inhalte
Die Inhalte unserer Seiten wurden mit größter Sorgfalt erstellt. Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte können wir jedoch keine Gewähr übernehmen.

#### Haftung für Links
Unser Angebot enthält Links zu externen Webseiten Dritter, auf deren Inhalte wir keinen Einfluss haben. Deshalb können wir für diese fremden Inhalte auch keine Gewähr übernehmen.

#### Urheberrecht
Die durch die Seitenbetreiber erstellten Inhalte und Werke auf diesen Seiten unterliegen dem deutschen Urheberrecht. Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung außerhalb der Grenzen des Urheberrechtes bedürfen der schriftlichen Zustimmung des jeweiligen Autors bzw. Erstellers.

### Datenschutz

Informationen zum Datenschutz finden Sie in unserer [Datenschutzerklärung](#).

---

*Erstellt mit Wasserwacht Dienstplan+ v{0}*
        """.format(VERSION)
    
    # ADMIN: Bearbeiten-Modus
    if is_admin:
        tab1, tab2 = st.tabs(["⚖️ Ansicht", "✏️ Bearbeiten"])
        
        with tab1:
            # Nur Anzeige
            st.markdown(impressum_content, unsafe_allow_html=True)
        
        with tab2:
            st.info("💡 Verwenden Sie **Markdown** zur Formatierung. Passen Sie das Impressum an Ihre Organisation an.")
            st.warning("⚠️ **WICHTIG:** Stellen Sie sicher, dass alle rechtlich erforderlichen Angaben vorhanden sind!")
            
            # Editor
            edited_content = st.text_area(
                "Impressum-Inhalt (Markdown)",
                value=impressum_content,
                height=600,
                help="Verwenden Sie Markdown-Syntax: ## für Überschriften, ** für fett, [Text](URL) für Links"
            )
            
            col1, col2, col3 = st.columns([2, 2, 6])
            
            with col1:
                if st.button("💾 Speichern", use_container_width=True, type="primary"):
                    if ww_db.set_setting('impressum_content', edited_content):
                        st.success("✅ Impressum gespeichert!")
                        st.rerun()
                    else:
                        st.error("❌ Fehler beim Speichern")
            
            with col2:
                if st.button("🔄 Zurücksetzen", use_container_width=True):
                    st.info("Seite wird neu geladen...")
                    st.rerun()
            
            # Live-Vorschau
            with st.expander("👁️ Live-Vorschau", expanded=True):
                st.markdown(edited_content, unsafe_allow_html=True)
    
    # USER: Nur Ansicht
    else:
        st.markdown(impressum_content, unsafe_allow_html=True)

# ===== VORLAGEN / TEMPLATES (NUR ADMIN) =====
def vorlagen_page():
    st.title("📧 Nachrichten-Vorlagen")
    
    st.info("💡 Hier können Sie die E-Mail und SMS Templates anpassen. Verwenden Sie Platzhalter wie {name}, {date}, {time} für dynamische Inhalte.")
    
    # Template-Definitionen mit Defaults
    templates = {
        'email_booking': {
            'name': '✉️ E-Mail - Buchungsbestätigung',
            'type': 'email',
            'default_subject': 'Buchungsbestätigung - {date}',
            'default_body': """Hallo {name},

deine Buchung wurde bestätigt:

📅 Datum: {date}
⏰ Uhrzeit: {time}

Bei Fragen melde dich gerne unter {org_email}.

Viele Grüße,
Dein {org_name} Team 🌊"""
        },
        'email_cancellation': {
            'name': '✉️ E-Mail - Stornierung',
            'type': 'email',
            'default_subject': 'Stornierung - {date}',
            'default_body': """Hallo {name},

deine Buchung wurde storniert:

📅 Datum: {date}
⏰ Uhrzeit: {time}

Viele Grüße,
Dein {org_name} Team 🌊"""
        },
        'email_reminder': {
            'name': '✉️ E-Mail - Erinnerung',
            'type': 'email',
            'default_subject': '⏰ Erinnerung: Dienst morgen - {date}',
            'default_body': """Hallo {name},

dein Dienst ist morgen:

📅 Datum: {date}
⏰ Uhrzeit: {time}

Bis morgen!
Dein {org_name} Team 🌊"""
        },
        'email_welcome': {
            'name': '✉️ E-Mail - Registrierung eingegangen',
            'type': 'email',
            'default_subject': 'Deine Registrierung bei {org_name}',
            'default_body': """Hallo {name},

danke für deine Registrierung bei {org_name}! 🌊

Dein Konto wurde angelegt und muss noch von einem Administrator
freigegeben werden. Sobald das erledigt ist, erhältst du eine
weitere E-Mail und kannst dich anmelden.

📧 Deine E-Mail: {email}

Bei Fragen erreichst du uns unter {org_email}.

Viele Grüße,
Dein {org_name} Team"""
        },
        'email_admin_notification': {
            'name': '✉️ E-Mail - Admin-Benachrichtigung (neue Buchung)',
            'type': 'email',
            'default_subject': '🔔 Neue Buchung: {name} - {date}',
            'default_body': """Neue Buchung im Dienstplan:

👤 Name: {name}
📧 E-Mail: {email}
📱 Telefon: {phone}

📅 Datum: {date}
⏰ Uhrzeit: {time}

Gebucht am: {current_date}"""
        },
        'email_password_reset': {
            'name': '✉️ E-Mail - Passwort zurückgesetzt',
            'type': 'email',
            'default_subject': '🔐 Passwort zurückgesetzt - {org_name}',
            'default_body': """Hallo {name},

dein Passwort wurde von einem Administrator zurückgesetzt.

🔑 **Dein neues temporäres Passwort:**
{new_password}

⚠️ **WICHTIG - Bitte beachten:**
1. Verwende dieses Passwort für die nächste Anmeldung
2. Ändere dein Passwort nach dem Login in ein persönliches, sicheres Passwort (im Profil unter "Sicherheit")
3. Bewahre dieses Passwort sicher auf

📧 Deine E-Mail: {email}

Bei Fragen erreichst du uns unter {org_email}.

Viele Grüße,
Dein {org_name} Team 🌊

---
Gesendet am {current_date}"""
        },
        'email_approved': {
            'name': '✉️ E-Mail - Konto freigegeben',
            'type': 'email',
            'default_subject': '✅ Dein Zugang ist freigeschaltet - {org_name}',
            'default_body': """Hallo {name},

dein Konto wurde freigegeben. Du kannst dich ab sofort anmelden
und Schichten buchen. 🌊

📧 Deine E-Mail: {email}

Viele Grüße,
Dein {org_name} Team"""
        },
        'email_registration_notice': {
            'name': '✉️ E-Mail - Admin: neue Registrierung',
            'type': 'email',
            'default_subject': '👤 Neue Registrierung wartet auf Freigabe: {name}',
            'default_body': """Eine neue Registrierung wartet auf Freigabe:

👤 Name: {name}
📧 E-Mail: {email}
📱 Telefon: {phone}

Registriert am: {current_date}

Freigeben unter: Benutzer -> Offene Freigaben"""
        },
        'sms_booking': {
            'name': '📱 SMS - Buchungsbestätigung',
            'type': 'sms',
            'default_subject': None,
            'default_body': """🌊 Buchung bestätigt: {name}
📅 {date}
⏰ {time}

{org_name}"""
        },
        'sms_reminder': {
            'name': '📱 SMS - Erinnerung',
            'type': 'sms',
            'default_subject': None,
            'default_body': """⏰ Erinnerung: Dienst morgen!
📅 {date}
⏰ {time}

{org_name}"""
        }
    }
    
    # Platzhalter-Info
    with st.expander("ℹ️ Verfügbare Platzhalter", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **Standard:**
            - `{name}` - Name des Benutzers
            - `{date}` - Datum (formatiert: DD.MM.YYYY)
            - `{time}` - Uhrzeit
            - `{email}` - E-Mail des Benutzers
            """)
        with col2:
            st.markdown("""
            **Erweitert:**
            - `{phone}` - Telefonnummer
            - `{org_name}` - Organisationsname
            - `{org_email}` - Organisation E-Mail
            - `{current_date}` - Heutiges Datum
            """)
        st.caption("💡 Platzhalter werden automatisch durch echte Daten ersetzt")
    
    st.divider()
    
    # Tabs für Template-Typen
    tab_names = [t['name'] for t in templates.values()]
    tabs = st.tabs(tab_names)
    
    for i, (template_key, template_config) in enumerate(templates.items()):
        with tabs[i]:
            # Lade gespeicherten Inhalt oder verwende Default
            saved_subject = ww_db.get_setting(f'{template_key}_subject', template_config['default_subject'])
            saved_body = ww_db.get_setting(f'{template_key}_body', template_config['default_body'])
            
            # Editor
            if template_config['type'] == 'email':
                subject = st.text_input(
                    "Betreff",
                    value=saved_subject if saved_subject else template_config['default_subject'],
                    key=f"subject_{template_key}",
                    help="Betreff der E-Mail (nur bei E-Mails)"
                )
            else:
                subject = None
            
            body = st.text_area(
                "Nachricht",
                value=saved_body if saved_body else template_config['default_body'],
                height=300,
                key=f"body_{template_key}",
                help="Nachrichtentext - verwenden Sie Platzhalter für dynamische Inhalte"
            )
            
            # Buttons
            col1, col2, col3 = st.columns([2, 2, 6])
            
            with col1:
                if st.button("💾 Speichern", key=f"save_{template_key}", use_container_width=True, type="primary"):
                    success = True
                    if subject:
                        success = success and ww_db.set_setting(f'{template_key}_subject', subject)
                    success = success and ww_db.set_setting(f'{template_key}_body', body)

                    if success:
                        st.success("✅ Template gespeichert!")
                    else:
                        st.error("❌ Fehler beim Speichern")

            with col2:
                if st.button("🔄 Zurücksetzen", key=f"reset_{template_key}", use_container_width=True):
                    ww_db.set_setting(f'{template_key}_subject', template_config['default_subject'])
                    ww_db.set_setting(f'{template_key}_body', template_config['default_body'])
                    # Die Editorfelder haben feste Keys - Streamlit bevorzugt
                    # dann den Session-State gegenueber dem value-Parameter.
                    # Ohne dieses Loeschen zeigte das Feld nach dem Reset
                    # weiter den alten Text und schrieb ihn beim naechsten
                    # Speichern zurueck.
                    st.session_state.pop(f"subject_{template_key}", None)
                    st.session_state.pop(f"body_{template_key}", None)
                    st.success("✅ Auf Standard zurückgesetzt!")
                    st.rerun()
            
            # Live-Vorschau
            st.divider()
            st.markdown("### 👁️ Live-Vorschau")
            
            # Beispieldaten für Vorschau
            preview_data = {
                'name': 'Max Mustermann',
                'date': '15.12.2025',
                'time': '14:00 - 17:00',
                'email': 'max.mustermann@example.com',
                'phone': '+49 172 1234567',
                'org_name': 'Wasserwacht München',
                'org_email': 'info@wasserwacht-muenchen.de',
                'current_date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                'new_password': 'Xy7bK2mQ',
                'comment': ''
            }

            # Template-Rendering
            preview_body = body
            if subject:
                preview_subject = subject
                for key, value in preview_data.items():
                    preview_subject = preview_subject.replace('{' + key + '}', str(value))
                for key, value in preview_data.items():
                    preview_body = preview_body.replace('{' + key + '}', str(value))
                
                st.markdown(f"**Betreff:** {preview_subject}")
            else:
                for key, value in preview_data.items():
                    preview_body = preview_body.replace('{' + key + '}', str(value))
            
            # Vorschau-Box
            if template_config['type'] == 'email':
                st.code(preview_body, language=None)
            else:
                st.info(preview_body)
            
            st.caption("💡 So wird die Nachricht mit Beispieldaten aussehen")

# ===== MAIN =====
def main():
    # CSS injizieren
    inject_css(dark=st.session_state.dark_mode)
    
    # Vor dem Login-Check: gibt es ein gueltiges Anmelde-Cookie?
    if not st.session_state.user:
        if sitzung_aus_cookie_wiederherstellen():
            st.rerun()

    # Login Check
    if not st.session_state.user:
        login_page()
        return

    # Abmeldung nach Inaktivitaet. Die Sitzung liegt nur im Arbeitsspeicher
    # des Browsers - dieser Timeout schuetzt vor allem geteilte Geraete.
    # Wer "Angemeldet bleiben" gewaehlt hat, soll nicht nach einer Stunde
    # herausfliegen - dort schuetzt die Laufzeit des Cookies.
    if not st.session_state.get('dauersitzung') and             session_abgelaufen(st.session_state.get('last_activity'),
                               timeout_minuten=get_session_timeout_minutes()):
        st.session_state.user = None
        st.session_state.pop('last_activity', None)
        st.session_state.session_expired = True
        st.rerun()

    # Jede Interaktion verlaengert die Sitzung
    st.session_state.last_activity = datetime.now()

    # Navigation anzeigen
    show_navigation()
    
    # Seiten-Router
    page = st.session_state.page
    user = st.session_state.user
    is_admin = user.get('role') == 'admin'
    
    if page == 'kalender':
        kalender_page()
    
    elif page == 'meine_buchungen':
        meine_buchungen_page()
    
    elif page == 'statistik':
        statistik_page()
    
    elif page == 'verwaltung':
        if is_admin:
            verwaltung_page()
        else:
            st.error("❌ Keine Berechtigung")
    
    elif page == 'benutzer':
        if is_admin:
            benutzer_page()
        else:
            st.error("❌ Keine Berechtigung")
    
    elif page == 'export':
        if is_admin:
            export_page()
        else:
            st.error("❌ Keine Berechtigung")
    
    elif page == 'debug':
        if is_admin:
            debug_page()
        else:
            st.error("❌ Keine Berechtigung")
    
    elif page == 'handbuch':
        handbuch_page()
        
    elif page == 'impressum':
        impressum_page()
        
    elif page == 'profil':
        profil_page()
        
    elif page == 'vorlagen':
        if is_admin:
            vorlagen_page()
        else:
            st.error("❌ Keine Berechtigung")
    
    else:
        st.error(f"❌ Unbekannte Seite: {page}")

if __name__ == "__main__":
    main()