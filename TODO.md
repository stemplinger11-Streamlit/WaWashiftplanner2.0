# TODO — Wasserwacht Dienstplan 2.0

Stand: 02.09.2026 · Basis: `streamlit_app.py` V9.0

**Erledigt:** P0 1–6, P1 8–15, P2 16, 17, 18, P3 20, 21, 22, 23, 24, 26.
**Offen:** P1 7 (Erinnerungen: gebaut, Zeitplan noch deaktiviert),
P3 25 (Modularisierung), 27 (Doppelbuchung).

**Tests:** 195, laufen ohne Firebase und ohne Streamlit (`python -m pytest -q`).

---

## Projektkontext & Rahmenbedingungen

Diese Punkte gelten für **jede** Änderung und dürfen nicht gebrochen werden:

| Thema | Ist-Zustand | Konsequenz für 2.0 |
|---|---|---|
| **Hosting** | Streamlit Community Cloud (streamlit.io) | Bleibt vorerst. Kein eigener Server, **kein persistenter Hintergrundprozess**, App schläft bei Inaktivität ein. |
| **Datenbank** | Firebase / Firestore, **mit Bestandsdaten** | Schema-Änderungen nur additiv oder mit Migrationsskript. Kein Feld umbenennen ohne Migration. |
| **Secrets** | Eine einzige Datei (`secrets.toml`), in Streamlit.io hinterlegt: Firebase-Credentials, Admin-Zugang, Twilio | Struktur der Keys beibehalten, sonst bricht das Deployment. Secrets gehören **nie** ins Repo. |
| **Deadline** | Saisonstart **Mitte September 2026** (~2 Wochen) | Priorisierung nach P0 → P1 → P2. Alles was P0 ist, muss vorher fertig sein. |
| **Bestandsnutzer** | Dürfen **nicht** verloren gehen | Keine Neuanlage der `users`-Collection, keine Passwort-Hash-Migration ohne Fallback-Login, keine E-Mail-Änderung an bestehenden Datensätzen. |

**Firestore-Collections:** `users`, `bookings`, `settings`, `archive`

---

## P0 — Blocker, muss vor Saisonstart erledigt sein

### ✅ 1. Sommerpause blockiert den gesamten September
`is_summer()` (Z. 119) blockiert **Juni bis einschließlich September** (`6 <= d.month <= 9`), hartkodiert für jedes Jahr. Wenn die Nutzer Mitte September zurückkommen, ist jeder September-Slot als „Blockiert (Sommerpause)" gesperrt und **nicht buchbar**.

→ **Klärungsbedarf:** Soll die Saison im September oder erst im Oktober starten? Danach richtet sich, ob das ein akuter Blocker oder nur eine Konfigurationsaufgabe ist.
→ **Lösung:** Sommerpause als konfigurierbaren Zeitraum (Start-/Enddatum) in `settings` auslagern, Admin-UI unter Verwaltung → Einstellungen.

### ✅ 2. Feiertage laufen Ende 2026 aus
`BAVARIA_HOLIDAYS` (Z. 45) enthält nur **2025 und 2026**. Die Saison 2026/27 läuft in den Januar 2027 hinein — Neujahr und Heilige Drei Könige 2027 werden dann **nicht** blockiert und sind fälschlich buchbar. `is_holiday()` gibt bei unbekanntem Jahr stillschweigend `False` zurück, ohne Warnung.

→ **Lösung:** Feiertage berechnen statt pflegen (Osterformel für bewegliche Feiertage) oder mindestens 2027/2028 ergänzen + Warnung im Admin-Bereich, wenn das laufende Jahr keine Daten hat.

### ✅ 3. Benachrichtigungs-Einstellungen im Profil sind wirkungslos
Zwei komplett getrennte Feld-Schemata in derselben Datenbank:

- **Geschrieben bei Registrierung** (Z. 653, 682): `email_notifications`, `sms_notifications`, `sms_booking_confirmation`
- **Gelesen beim Buchen** (Z. 1593, 1601): `email_notifications`, `sms_notifications`
- **Geschrieben/gelesen im Profil** (Z. 1802–1859): `email_notifications_booking`, `email_notifications_reminder`, `email_notifications_cancellation`, `sms_notifications_booking`, `sms_notifications_reminder`
- **Gelesen bei Admin-Buchung** (Z. 2307): `sms_notifications_booking`

**Effekt:** Der Nutzer speichert im Profil seine Benachrichtigungs-Einstellungen, bekommt „✅ Einstellungen gespeichert!" — und es ändert sich **nichts**. Die Buchungslogik liest die alten Felder weiter. SMS bei Selbstbuchung ist faktisch tot, weil `sms_notifications` nach der Registrierung nie wieder gesetzt wird (steht immer auf `False`).

→ **Lösung:** Auf **ein** Schema vereinheitlichen. Migration nötig, da Bestandsnutzer die alten Felder haben — beim Lesen Fallback auf Altfeld, damit niemand seine Einstellung verliert.

### ✅ 4. Checkboxen bei der Registrierung sind Attrappen
In `login_page()` werden `email_notif` und `sms_notif` abgefragt (Z. 1330/1331), aber `create_user()` wird ohne sie aufgerufen (Z. 1345). Die Werte landen nie in der Datenbank — es gilt immer der Hardcode `email_notifications=True`, `sms_notifications=False`.

### ✅ 5. Umbuchung kann Buchungen vernichten
In der Admin-Umbuchung (Z. 2385 ff.) wird die alte Buchung **zuerst per `delete()` gelöscht**, dann die neue erstellt. Schlägt `create_booking()` fehl, ist die Buchung **ersatzlos weg** — der Slot ist frei, der ursprüngliche Nutzer ausgetragen, niemand ist informiert.

Zusätzlich: `delete()` statt `cancel_booking()` heißt, es bleibt **kein Audit-Trail**. Bei einer Stornierung wird sonst der Status auf `cancelled` gesetzt und mitprotokolliert, wer wann storniert hat.

→ **Lösung:** Reihenfolge umdrehen (erst neu anlegen, dann alte stornieren) oder Firestore-Transaktion. Alte Buchung als `cancelled` markieren statt löschen.

### ✅ 6. Admin-Buchung stürzt bei leerer Wochenauswahl ab
In Tab „Admin-Buchung" wird `selected_slot` nur innerhalb des `else:`-Zweigs gesetzt (Z. 2264). Sind für die gewählte Woche keine Slots verfügbar (alle in der Vergangenheit), wird das Formular trotzdem mit Submit-Button gerendert. Klick → `NameError: selected_slot is not defined` → Absturz der Seite.

---

## P1 — Funktioniert nicht wie angezeigt

### 🔸 7. Erinnerungsfunktion existiert nicht
`APScheduler` und `CronTrigger` werden importiert (Z. 19/20), aber **nie verwendet**. `Mailer.send_reminder()` (Z. 1007) und `TwilioSMS.send_reminder()` (Z. 1260) werden von nirgendwo aufgerufen.

Trotzdem verspricht das Handbuch „Sie erhalten Erinnerungen 24h vor Ihrem Dienst", das Profil bietet die Checkbox „Erinnerungen (24h vorher)" an, und es gibt eine editierbare Vorlage dafür. **Es wurde noch nie eine Erinnerung verschickt.**

→ **Wichtig:** Auf Streamlit Community Cloud läuft kein zuverlässiger Hintergrundprozess — die App schläft bei Inaktivität ein, ein `BackgroundScheduler` stirbt mit. Braucht eine externe Lösung (GitHub Action mit Cron, Cloud Function o. ä.) oder muss ehrlich aus der UI entfernt werden.

### ✅ 8. Willkommens-E-Mail wird nie versendet
`Mailer.send_welcome()` (Z. 1035) ist vollständig implementiert, hat eine editierbare Vorlage im Admin-Bereich — wird aber weder bei der Selbstregistrierung noch bei der Admin-Neuanlage aufgerufen.

### ✅ 9. Passwort-Reset: Admin sieht das Notfall-Passwort nie
In der Benutzerverwaltung (Z. 2556 ff.) wird nach dem Reset korrekt angezeigt:
`st.info("🔑 Neues Passwort (für Notfälle): ...")` mit dem Hinweis „Bitte notiere das Passwort".
Direkt danach steht aber `st.rerun()` (Z. 2570) — die Seite lädt sofort neu und **löscht die Anzeige, bevor sie gelesen werden kann**. Schlägt der E-Mail-Versand fehl, ist das Passwort unwiederbringlich verloren und der Nutzer ausgesperrt.

→ Gleiches Muster bei Löschen/Deaktivieren: Erfolgsmeldung wird vom sofortigen `st.rerun()` verschluckt.

### ✅ 10. „Zurücksetzen" bei den Vorlagen wirkt folgenlos
In `vorlagen_page()` (Z. 3249) haben die Editor-Felder einen festen `key` (`f"body_{template_key}"`). Streamlit priorisiert bei gesetztem `key` den Session-State über den `value`-Parameter. Nach „Zurücksetzen" wird zwar die Datenbank auf den Default gesetzt, das Textfeld zeigt aber **weiterhin den alten Text**. Klickt der Admin danach auf „Speichern", schreibt er den alten Text zurück — der Reset ist rückgängig gemacht, ohne dass es jemand merkt.

### ✅ 11. Umbuchungs-Kommentar wird nirgends verwendet
Das Feld ist beschriftet mit „Grund für die Umbuchung (**wird in Benachrichtigung erwähnt**)" (Z. 2371). Der Kommentar wird jedoch nur dem Admin selbst als `st.info()` angezeigt (Z. 2419) und weder gespeichert noch in eine der beiden E-Mails übernommen.

### ✅ 12. E-Mail-Änderung im Profil trennt den Nutzer von seinen Buchungen
Buchungen referenzieren den Nutzer über `user_email` als String, nicht über die Dokument-ID. Ändert ein Nutzer im Profil seine E-Mail (Z. 1770 ff., ausdrücklich erlaubt), verschwinden **alle bisherigen Buchungen** aus „Meine Buchungen", und die Buchungsstatistik zählt ihn doppelt.

→ In der Benutzerverwaltung ist das Feld korrekterweise auf `disabled=True` gesetzt (Z. 2596) — im Profil aber nicht.
→ **Lösung:** Buchungen an `user_id` binden (additiv, mit Fallback auf E-Mail für Bestandsdaten) oder E-Mail-Änderung mit Nachziehen aller Buchungen umsetzen.

### ✅ 13. Backup-Mail wird als HTML-Quelltext verschickt
`export_page()` baut den Body als HTML (Z. 2740 ff.), `Mailer.send()` hängt ihn aber grundsätzlich als `MIMEText(body, 'plain')` an (Z. 909). Der Empfänger sieht rohe `<html><body><h2 style=...>`-Tags.

### ✅ 14. Kein Schutz vor Selbst-Aussperrung
Ein Admin kann sich in der Benutzerverwaltung selbst löschen oder deaktivieren. Wird der letzte Admin entfernt, kommt niemand mehr in die Verwaltung. Zugang wäre nur über das Secrets-Fallback wiederherstellbar — und `_init_admin()` legt den Admin nur an, wenn die E-Mail **nicht** existiert, greift bei einem nur deaktivierten Admin also nicht.

### ✅ 15. Download-Buttons verschwinden nach dem ersten Klick
Im Export-Bereich liegen die `st.download_button` innerhalb eines `if st.button(...)`-Blocks (Z. 2654 ff.). Nach dem Download löst Streamlit einen Rerun aus, `st.button` ist dann wieder `False` und der Download-Button verschwindet. Für jeden weiteren Download muss der erste Button erneut geklickt werden — verwirrend, wirkt wie ein Fehler.

---

## P2 — Sicherheit

### ✅ 16. Passwörter mit ungesalzenem SHA-256
`hash_pw()` (Z. 93) ist ein einfacher SHA-256 ohne Salt und ohne Key-Stretching — anfällig für Rainbow-Table-Angriffe. Zeitgemäß wäre bcrypt oder Argon2.

→ **Bestandsnutzer-Constraint:** Kein Rehash möglich, ohne die Klartext-Passwörter zu kennen. Lösung: beim nächsten erfolgreichen Login transparent auf das neue Verfahren umstellen (Hash-Typ am Präfix erkennen), Altverfahren als Fallback behalten. So verliert niemand seinen Zugang.

### ✅ 17. Admin-Fallback-Passwort `admin123`
`_init_admin()` (Z. 646) fällt auf `admin@wasserwacht.de` / `admin123` zurück, wenn die Secrets fehlen. Fehlt der Key, entsteht ein öffentlich erreichbarer Admin-Zugang mit trivialem Passwort.

### ✅ 18. Selbstregistrierung ohne jede Prüfung
Jeder mit der URL kann sich einen Account anlegen und sofort Schichten buchen — keine E-Mail-Verifikation, keine Admin-Freigabe, keine Einladungscodes.

→ **Klärungsbedarf:** Ist das gewollt (interner Link im Verein) oder soll eine Freigabe durch den Admin dazwischen?

### ✅ 19. Keine Session-Persistenz / kein Timeout
Login liegt ausschließlich im `st.session_state`. Ein Browser-Reload loggt aus (schlechte UX), gleichzeitig gibt es kein Timeout bei Inaktivität.

**Timeout: erledigt.** Abmeldung nach 60 Minuten ohne Aktivität, unter
Verwaltung → Einstellungen zwischen 0 (aus) und 1440 Minuten einstellbar.
Der Nutzer bekommt beim nächsten Aufruf einen Hinweis statt eines wortlosen
Logins.

**Angemeldetbleiben: erledigt.** Über `extra-streamlit-components`, da
`st.context.cookies` auch in Streamlit 1.63 nur lesbar ist. Token im Cookie,
nur der Hash in Firestore; Dauer in den Einstellungen pflegbar.

---

## P3 — Aufräumen & Struktur

### ✅ 20. Excel-Export fehlt
`openpyxl` steht in den `requirements.txt`, wird aber nirgends verwendet. Export kann derzeit nur JSON und CSV. Excel-Export (Dienstplan pro Monat/Saison, formatiert) nachrüsten — oder die Abhängigkeit entfernen.

### ✅ 21. Ungenutzte Imports entfernen
`calendar as cal_module` (Z. 10), `plotly.graph_objects as go` (Z. 24), `APScheduler`/`CronTrigger` (Z. 19/20, siehe Punkt 7) werden nie benutzt.

### ✅ 22. Handbuch verspricht nicht vorhandene Funktionen
Der Default-Text nennt „Stornieren Sie Buchungen bis 24h vorher" (**keine solche Regel implementiert** — Stornierung ist immer möglich, auch am Diensttag selbst), „Erinnerungen 24h vor Ihrem Dienst" (Punkt 7) und „Sehen Sie Ihre Dienst-Statistiken" (die Statistik ist rein global, es gibt keine persönliche Auswertung).

→ **Klärungsbedarf:** Soll die 24h-Stornofrist tatsächlich existieren? Dann ist das ein fehlendes Feature, kein Doku-Fehler.

### ✅ 23. Firestore-Abfragen: N+1-Probleme
- Benutzerverwaltung ruft `get_user_bookings()` **pro Nutzer** auf (Z. 2502) → bei 30 Nutzern 30 Abfragen bei **jedem** Rerun.
- „Freie Slots" ruft `get_booking()` einzeln pro Slot auf (Z. 2059) → 12 Abfragen.

Auf dem Firestore-Free-Tier zählt jeder Read gegen das Kontingent. Besser: einmal alle relevanten Buchungen laden und im Speicher zuordnen.

### ✅ 24. Fehlender Composite-Index
`get_week_bookings()` braucht einen zusammengesetzten Index für `slot_date` + `status`. Der Code fängt den Fehler ab und fällt auf einen **Full-Scan aller Buchungen** zurück (Z. 762 ff.) — funktioniert, wird aber mit wachsender Datenmenge langsam und teuer. Index in der Firebase-Konsole anlegen.

### 25. Monolith aufteilen
3.362 Zeilen in einer Datei, davon ~490 Zeilen CSS in `inject_css()`. Für die Weiterentwicklung sinnvoll: Trennung in `db.py`, `notifications.py`, `pages/`, `config.py`, CSS in eine `.css`-Datei. **Achtung:** Streamlit.io startet `streamlit_app.py` — der Einstiegspunkt muss so heißen und im Root liegen.

### ✅ 26. Repo-Hygiene
Es fehlen `.gitignore` (u. a. `.streamlit/secrets.toml` ausschließen!), `README.md` mit Setup-Anleitung und eine `secrets.toml.example` als Vorlage ohne echte Werte.

---

### 27. Doppelbuchung bei gleichzeitigem Klick möglich

`create_booking()` prüft mit `get_booking()`, ob der Slot frei ist, und legt
dann an — zwei getrennte Schritte ohne Transaktion. Klicken zwei Nutzer im
selben Moment, können beide eine Buchung für denselben Slot erhalten; im
Kalender erscheint dann nur eine, die andere Person hält sich aber ebenfalls
für eingeteilt.

Wahrscheinlichkeit ist gering (drei Slots pro Woche, überschaubarer Kreis),
die Folge aber ärgerlich. **Bewusst nicht kurz vor Saisonstart geändert**, weil
der Buchungspfad ohne laufende Datenbank nicht erprobt werden kann.

→ **Lösung:** Firestore-Transaktion, oder sauberer: die Dokument-ID aus
`slot_date` + `slot_time` bilden und mit `create()` anlegen — das schlägt
serverseitig fehl, wenn das Dokument schon existiert. Letzteres erfordert eine
Migration der Bestandsbuchungen auf die neuen IDs.

---

## Ausbau — Stand 04.09.2026

Ausführlich: **[Dienstplan Ausbaustufen](https://claude.ai/code/artifact/538b96de-9b61-4092-b8ab-78a328b08543)**

**Grundlage:** Immer genau **eine** Person im Bad, an der Kasse — kein
Wachdienst. Das Datenmodell (eine Buchung je Termin) bleibt damit richtig.

### Umgesetzt
- Termine sperren durch Admins, mit Grund im Kalender und optionaler
  Stornierung betroffener Buchungen
- Rundnachricht an alle aktiven Nutzer
- Admin-Notiz an einer Buchung, für den Nutzer sichtbar
- Kalenderdatei (.ics) für eigene Termine und für alle Dienste
- Vertretung suchen und übernehmen
- Eigene Dienstbilanz (Dienste und Stunden der Saison)
- Übersicht der nächsten acht Wochen
- Hinweis zum Ablegen auf dem Handy, mit Anleitung für iOS und Android
- Nutzer-Import aus CSV
- Datenschutzseite (Entwurf, siehe unten)
- Doppelbuchung: Prüfen und Schreiben in einer Transaktion

### Gestrichen
Mehrere Personen je Termin · Qualifikationen · Anwesenheitsbestätigung
(bleibt bei der Unterschrift im Ordner) · Serientermine · Saison-Ampel ·
automatischer Aufruf bei unbesetzten Terminen

---

## Offen — braucht eine Entscheidung von dir

### A. Datenschutzerklärung inhaltlich freigeben
Die Seite steht und ist bearbeitbar, der Text ist als **ungeprüfter Entwurf**
gekennzeichnet und für alle sichtbar erst nach dem Speichern. Er nennt
Firestore, Streamlit und Twilio als Auftragsverarbeiter und beschreibt das
Anmelde-Cookie. **Inhaltlich verantworten muss ihn der Verein**, nicht ich –
insbesondere Verantwortlicher, Aufbewahrungsfristen und Kontaktweg.

### B. Echtes Kalender-Abo statt Download
Heute wird eine `.ics`-Datei heruntergeladen: einmal importieren, fertig.
Ändert sich später eine Buchung, merkt der Kalender das nicht. Ein echtes Abo
bräuchte eine dauerhaft erreichbare Adresse, die Streamlit Cloud nicht
bereitstellt — also eine Cloud Function oder ähnliches. **Das ist eine
Entscheidung über zusätzliche Infrastruktur und Kosten.**

### C. Echte App statt Lesezeichen
Der Hinweis zum Ablegen auf dem Handy funktioniert, aber es bleibt ein
Browser-Lesezeichen: kein eigenes Symbol, kein Offline-Betrieb. Eine richtige
PWA bräuchte Zugriff auf die ausgelieferte `index.html`, den Streamlit Cloud
nicht gewährt. **Entscheidung: eigenes Hosting oder so belassen.**

### D. Fehlermeldungen vor dem Saisonstart abschalten
`showErrorDetails` steht bewusst noch auf sichtbar, damit du beim Testen
echte Meldungen bekommst. **Vor dem Saisonstart in `.streamlit/config.toml`
umstellen**, sonst sehen Nutzer im Fehlerfall Code-Auszüge.

### E. Erinnerungen scharf schalten
Das Skript und die GitHub Action stehen, der Zeitplan ist deaktiviert. Vorher
klären, ob bereits eine andere Stelle Erinnerungen verschickt — sonst kommt
alles doppelt an.

### F. Aufteilung der Hauptdatei
`streamlit_app.py` ist weiter gewachsen. Die Fachlogik liegt inzwischen in
`core_*.py`, die Oberfläche nicht. Sinnvoll nach der Saison, nicht davor.

---

## Entschiedene Fragen

1. **Saisonpause:** konfigurierbar, Standard 01.06.–14.09. → ab Mitte September buchbar.
2. **Stornofrist:** 12 Stunden für Nutzer, Admins ausgenommen (dürfen jederzeit
   für sich und alle Nutzer stornieren und umbuchen).
3. **Registrierung:** offen, aber ein Admin muss jedes neue Konto freigeben.
4. **Erinnerungen:** siehe Punkt 7 – noch offen, weil der versendende Prozess fehlt.

## Offene Fragen an den Auftraggeber

1. **Erinnerungen:** Kommen aktuell tatsächlich welche an? Falls ja, versendet sie
   etwas außerhalb dieses Repos – das müsste gefunden werden, bevor ein neuer
   Versand danebengestellt wird (sonst doppelte Nachrichten). Falls nein:
   Umsetzung per GitHub-Action-Cron freigeben?
2. **E-Mail-Änderung:** Soll ein Admin die E-Mail eines Nutzers ändern können
   (inklusive Nachziehen aller Buchungen)? Aktuell ist das Feld gesperrt.
3. **Passwort-Hashing:** Umstellung auf bcrypt beim nächsten Login freigeben?
   (Punkt 16 – Bestandsnutzer verlieren dabei nichts.)
4. Weitere gewünschte Features (wurden für später angekündigt).
