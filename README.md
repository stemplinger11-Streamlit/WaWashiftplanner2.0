# WaWashiftplanner 2.0

Dienstplan der Wasserwacht: Streamlit-App mit Firestore-Anbindung.
Nutzer buchen wöchentliche Schichten, Administratoren verwalten Buchungen,
Konten und Benachrichtigungen.

Weiterentwicklung des produktiven [Shiftplanner](https://github.com/stemplinger11-Streamlit/Shiftplanner)
auf gemeinsamer Datenbasis.

---

## Aufbau

| Datei | Inhalt |
|---|---|
| `streamlit_app.py` | Einstiegspunkt: Oberfläche, Datenzugriff, E-Mail/SMS |
| `core_rules.py` | Feiertage, Saisonpause, Stornofrist, Saisonzeitraum |
| `core_auth.py` | Passwort-Hashing inkl. Migration der Bestandsnutzer |
| `core_theme.py` / `core_styles.py` | Farbpalette und Stylesheet |
| `core_ics.py` | Kalenderdatei (.ics) aus Buchungen |
| `core_import.py` | Nutzerliste aus CSV einlesen |
| `core_reminders.py` | Auswahl der fälligen Erinnerungen |
| `test_core_*.py` | Tests der fachlichen Regeln (ohne Firebase/Streamlit) |
| `scripts/` | Sicherung und Wiederherstellung der Datenbank |
| `TODO.md` | Befunde, offene Punkte, Projektrahmen |
| `BACKUP.md` | Anleitung zur Datensicherung |

Die fachlichen Regeln liegen bewusst außerhalb von `streamlit_app.py`, damit
sie ohne laufende App und ohne Datenbankzugriff geprüft werden können.

---

## Lokal starten

Getestet mit **Python 3.14** – der Version, die Streamlit Community Cloud
verwendet. Weichen lokale und deployte Version ab, fallen fehlende Wheels
erst beim Deploy auf.

```bash
pip install -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml ausfüllen, dann:
streamlit run streamlit_app.py
```

## Tests

```bash
python -m pytest -q
```

Die Regeltests (`test_core_*.py`) brauchen weder Firebase noch Streamlit.
`test_app_smoke.py` lädt zusätzlich die ganze App gegen die echten
Paketversionen – mit Attrappen statt Datenbank – und deckt damit
Paket- und API-Brüche vor dem Deploy auf.

---

## Auf Streamlit Community Cloud einrichten

1. Auf [share.streamlit.io](https://share.streamlit.io) eine neue App anlegen.
2. Repository `WaWashiftplanner2.0`, Branch `main`, Datei `streamlit_app.py`.
3. Unter *Settings → Secrets* den Inhalt von
   `.streamlit/secrets.toml.example` einfügen und ausfüllen.
4. Deploy.

> **Vor dem ersten Start mit echten Daten:** eine Sicherung ziehen.
> Siehe [BACKUP.md](BACKUP.md).

### Firestore-Index

Für die Wochen- und Zeitraumabfragen wird ein zusammengesetzter Index
benötigt:

| Collection | Felder |
|---|---|
| `bookings` | `status` (aufsteigend), `slot_date` (aufsteigend) |

Anlegen in der [Firebase Console](https://console.firebase.google.com) unter
*Firestore Database → Indexes → Zusammengesetzt → Index erstellen*.

Ohne diesen Index funktioniert die App weiterhin: Sie fällt auf das Laden
aller Buchungen mit anschließender Filterung im Speicher zurück. Das wird
mit wachsender Datenmenge aber langsam und verbraucht unnötig
Lesekontingent. Firestore verlinkt beim ersten Fehlschlag in der Logausgabe
einen fertigen Erstellungslink.

---

## Erinnerungen

Streamlit Community Cloud hält keinen zuverlässigen Hintergrundprozess offen –
die App schläft bei Inaktivität ein. Erinnerungen werden deshalb von außen
angestoßen, über `scripts/send_reminders.py`.

Trockenlauf (verändert nichts, zeigt nur an, wer eine Erinnerung bekäme):

```bash
python scripts/send_reminders.py
```

Tatsächlich versenden:

```bash
python scripts/send_reminders.py --senden
```

Ein Doppelversand ist ausgeschlossen: Nach erfolgreichem Versand wird
`reminder_sent_at` an der Buchung gesetzt, bereits erinnerte Buchungen werden
übersprungen.

### Automatisch per GitHub Action

`.github/workflows/reminders.yml` kann den Versand täglich ausführen. Der
Zeitplan ist **noch deaktiviert** – siehe die Hinweise in der Datei. Zum
Aktivieren:

1. Klären, ob bereits eine andere Stelle Erinnerungen verschickt. Läuft
   beides parallel, bekommen die Nutzer alles doppelt.
2. Unter *Settings → Secrets and variables → Actions* die Zugangsdaten
   hinterlegen: `FIREBASE_CREDENTIALS` (die Service-Account-JSON als ein
   String), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT`,
   bei SMS zusätzlich `ENABLE_SMS_REMINDER` und die drei `TWILIO_*`-Werte.
3. Den `schedule`-Block in der Workflow-Datei einkommentieren.

Vorher lässt sich der Ablauf gefahrlos testen: *Actions → Dienst-Erinnerungen
→ Run workflow*, ohne den Haken bei „Tatsächlich versenden".

---

## Konfiguration in der App

Diese Werte pflegt ein Administrator unter *Verwaltung → Einstellungen*,
sie liegen in der Collection `settings` und brauchen keine Codeänderung:

- **Saisonpause** – jährlich wiederkehrender Zeitraum, in dem nicht gebucht
  werden kann. Standard: 01.06. bis 14.09.
- **Stornofrist** – Stunden vor Dienstbeginn, bis zu denen Nutzer selbst
  stornieren dürfen. Standard: 12. Administratoren sind ausgenommen.
- **Organisationsname** – erscheint in allen Nachrichten als `{org_name}`.
- **Automatische Abmeldung** – Minuten ohne Aktivität, bis die Sitzung
  endet. Standard: 60. `0` schaltet die Abmeldung ab. Gilt nicht, wenn
  „Angemeldet bleiben" gewählt wurde.
- **Angemeldet bleiben** – Tage, die eine Anmeldung auf dem Gerät gültig
  bleibt. Standard: 30. `0` schaltet die Funktion ab.
- **Dark Mode** – globale Voreinstellung.

Die Texte aller E-Mails und SMS lassen sich unter *Vorlagen* bearbeiten.

Feste Werte im Code: die drei Wochenslots (`WEEKLY_SLOTS` in
`streamlit_app.py`). Die bayerischen Feiertage werden berechnet und müssen
nicht gepflegt werden.

---

## Angemeldet bleiben

Beim Login lässt sich „Angemeldet bleiben" wählen. Der Browser erhält dann
ein Cookie mit einem Zufallstoken; in Firestore (`sessions`) liegt nur
dessen SHA-256-Hash – wer die Datenbank liest, kann sich damit nicht
anmelden. Ein Reload oder das erneute Öffnen des Tabs meldet dann nicht
mehr ab.

Bestehende Anmeldungen werden automatisch beendet bei Passwortwechsel,
Passwort-Reset durch einen Admin und Deaktivierung des Kontos.

Streamlit kann Cookies nur lesen (`st.context.cookies`), nicht setzen –
daher die Komponente `extra-streamlit-components`. Jeder Cookie-Zugriff ist
abgesichert: Fällt die Komponente aus, funktioniert die normale Anmeldung
unverändert weiter.

---

## Rollen

**Nutzer** buchen und stornieren eigene Schichten, verwalten ihr Profil und
ihre Benachrichtigungen.

**Administratoren** zusätzlich: alle Buchungen verwalten, Schichten für
andere buchen und umbuchen, Konten freigeben und verwalten, Passwörter
zurücksetzen, exportieren, Vorlagen und Einstellungen pflegen, E-Mail- und
SMS-Versand testen.

Neue Registrierungen müssen von einem Administrator freigegeben werden,
bevor eine Anmeldung möglich ist.
