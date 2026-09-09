# TODO — Wasserwacht Dienstplan 2.0

Stand: 07.09.2026 · `streamlit_app.py` V9.0 auf Streamlit 1.63 / Python 3.14

**Aus der Bestandsaufnahme erledigt:** P0 1–6, P1 8–15, P2 16–19,
P3 20–24, 26, 27.
**Davon offen:** P1 7 (Erinnerungen: gebaut, Zeitplan bewusst deaktiviert),
P3 25 (Modularisierung, nach der Saison).

**Was du selbst tun musst:** siehe Abschnitt „Offen" weiter unten –
Firestore-Index, Datenschutztext freigeben, Fehlermeldungen abschalten.

**Tests:** 350, laufen ohne Firebase und ohne Streamlit (`python -m pytest -q`).

---

## Projektkontext & Rahmenbedingungen

Diese Punkte gelten für **jede** Änderung und dürfen nicht gebrochen werden:

| Thema | Ist-Zustand | Konsequenz für 2.0 |
|---|---|---|
| **Hosting** | Streamlit Community Cloud **und** Azure App Service (seit 09.09.2026, parallel) | Beide laufen gegen dieselbe Firestore-Datenbank. Auf Azure schläft die App nicht ein, **einen persistenten Hintergrundprozess gibt es aber weiterhin nicht** – der Plan bleibt eine Streamlit-App mit einer Instanz. Solange die alte Instanz lebt, muss jede Änderung auf beiden laufen. |
| **Datenbank** | Firebase / Firestore, **mit Bestandsdaten** | Schema-Änderungen nur additiv oder mit Migrationsskript. Kein Feld umbenennen ohne Migration. |
| **Secrets** | Eine einzige Datei (`secrets.toml`): in Streamlit.io hinterlegt, auf Azure base64-kodiert im Key Vault `kv-wawa-web-hzb` | Struktur der Keys beibehalten, sonst bricht das Deployment. Secrets gehören **nie** ins Repo. |
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
- Termineinladung per Mail beim Buchen, Absage beim Stornieren,
  aktualisierter Termin bei einer Admin-Notiz
- Vertretung suchen und übernehmen
- Eigene Dienstbilanz (Dienste und Stunden der Saison)
- Übersicht der nächsten acht Wochen
- Hinweis zum Ablegen auf dem Handy, mit Anleitung für iOS und Android
- Nutzer-Import aus CSV
- Datenschutzseite (Entwurf, siehe unten)
- Doppelbuchung: Prüfen und Schreiben in einer Transaktion
- Statistik: Rangliste mit eigenem Platz, Saison- und Wochentagsfilter

### Gestrichen
Mehrere Personen je Termin · Qualifikationen · Anwesenheitsbestätigung
(bleibt bei der Unterschrift im Ordner) · Serientermine · Saison-Ampel ·
automatischer Aufruf bei unbesetzten Terminen

---

## Azure-Hosting — offene Punkte (Stand 09.09.2026)

Die App läuft seit dem 09.09.2026 zusätzlich auf Azure App Service unter
https://app-wawa-shiftplaner.azurewebsites.net — öffentlich erreichbar,
dauerhaft wach, rund 11,32 € im Monat. Einzelheiten zum Betrieb stehen in
[`docs/BETRIEB-AZURE.md`](docs/BETRIEB-AZURE.md), Entwurf und Umsetzungsplan
unter `docs/superpowers/`.

Die Streamlit-Community-Cloud-Instanz läuft **absichtlich weiter** und schreibt
in dieselbe Firestore-Datenbank. Sie ist bis auf Weiteres das Produktivsystem.

### ⚠️ Warnung: `origin` zeigt auf das falsche Repo

In diesem Arbeitsverzeichnis zeigt `origin` auf das **alte** Repo
`stemplinger11-Streamlit/Shiftplanner`, und `main` verfolgt ausgerechnet
`origin/main`. Das richtige Ziel ist `target`
(`stemplinger11-Streamlit/WaWashiftplanner2.0`).

**Ein bloßes `git push` schreibt also in die falsche Ablage.** Bis das Tracking
umgestellt ist, gilt ausnahmslos:

```bash
git push target main
```

Umstellen ließe sich das mit `git branch -u target/main main` — bewusst noch
nicht getan, weil es das Verhalten aller künftigen Pushes ändert.

### ✅ 1. Zusammengeführten Stand pushen — erledigt am 09.09.2026

`git push target main` ist durch, acht Commits liegen in
`WaWashiftplanner2.0`. Die Warnung oben gilt unverändert weiter: `main`
verfolgt nach wie vor `origin/main`, also das **alte** Repo.

### ⚠️ 2. Automatische Auslieferung — geprüft, **Deploy scheitert**

Stand 09.09.2026: „Tests" lief mit `success` durch, „Deploy nach Azure" ist
angesprungen und nach drei Sekunden am Schritt **„An Azure anmelden"**
gescheitert
([Lauf 34358842682](https://github.com/stemplinger11-Streamlit/WaWashiftplanner2.0/actions/runs/34358842682)).
Alle folgenden Schritte wurden übersprungen; die laufende App auf Azure ist
davon unberührt.

Geprüft und in Ordnung: Die föderierte Anmeldung an
`gh-deploy-wawa-shiftplaner` trägt genau das richtige Subject
`repo:stemplinger11-Streamlit/WaWashiftplanner2.0:ref:refs/heads/main`, die
Rollenzuweisung *Website Contributor* auf `app-wawa-shiftplaner` existiert,
und der Workflow setzt `permissions: id-token: write`.

Damit bleiben zwei Verdächtige, die im Protokoll unterschiedlich aussehen:

| Meldung im Protokoll | Ursache | Behebung |
|---|---|---|
| `Not all values are present` | Die drei Werte liegen als **Secrets** statt als **Variables**, oder nur im alten Repo | Unter *Settings → Secrets and variables → Actions → Variables* anlegen; der Workflow liest `vars.*` |
| `AADSTS70021` | Der Anspruch passt nicht zum `workflow_run`-Auslöser | Zweite föderierte Anmeldung ergänzen |

**Nächster Schritt:** die rote Meldung aus dem Lauf lesen — sie entscheidet
zwischen beiden. Erst danach sinnvoll:

- Der Lauf endet mit `success` und der Schritt „Erreichbarkeit pruefen" meldet
  HTTP 200.
- Ein **roter** Test liefert **nicht** aus. Dafür auf einem Wegwerf-Branch
  einen absichtlich fehlschlagenden Test einbauen, Pull Request öffnen, prüfen
  dass „Deploy nach Azure" nicht startet, danach alles verwerfen.

Die drei Repository-Variablen `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` und
`AZURE_SUBSCRIPTION_ID` sind bereits hinterlegt.

### 3. Repository auf privat stellen

**Empfehlung: ja.** Beide Repos (`WaWashiftplanner2.0` und `Shiftplanner`) sind
derzeit öffentlich.

Akut gefährdet ist nichts: Im Repository liegen keine Zugangsdaten, und die drei
Azure-Variablen sind Kennungen, keine Geheimnisse — ein Token bekommt nur ein
Workflow-Lauf auf `refs/heads/main` genau dieses Repos, was ohne Schreibrechte
niemand auslösen kann. Öffentlich einsehbar sind aber die Firestore-Projekt-
kennung, die Admin- und Rollenlogik, die Azure-Ressourcennamen und künftig alle
Workflow-Protokolle. Für den Dienstplan eines Vereins hat das keinen Nutzen.

**⚠️ Vor dem Umstellen bedenken:** Streamlit Community Cloud braucht für private
Repositories erweiterte GitHub-Rechte. Die parallel laufende alte Instanz kann
stehenbleiben, bis der Zugriff neu erlaubt ist. Da sie noch das Produktivsystem
ist: umstellen, **sofort** prüfen ob sie noch lädt, und die Rechte
gegebenenfalls gleich nachziehen.

### 4. Fachlicher Durchklick auf Azure

Mit einem echten Konto anmelden, eine Schicht buchen, wieder stornieren,
Rangliste mit Diagramm öffnen, ICS exportieren. Belegt ist bisher nur, dass die
Anmeldemaske vollständig lädt — was immerhin beweist, dass die Firebase-
Initialisierung mit den Zugangsdaten aus dem Key Vault durchläuft.

Dabei die **Darstellung** prüfen: Beim Testaufruf wirkte das Anmeldeformular
nach rechts über den Fensterrand hinausgeschoben. Das kann am schmalen
Testfenster gelegen haben. Zum Vergleich dieselbe Seite auf Streamlit Community
Cloud öffnen.

### 5. Abschaltung der alten Instanz terminieren

Noch offen und bewusst nicht entschieden. Solange beide laufen, schreiben zwei
Anwendungen in dieselbe Firestore-Datenbank. Vor dem Abschalten festlegen, ab
wann die Azure-Adresse die maßgebliche ist, und die Nutzer erst dann umleiten.

### 6. Eigene Domain anbinden

Sobald die extern bestellte Domain vorliegt. Vorgehen samt CNAME und
`asuid`-TXT-Eintrag steht in `docs/BETRIEB-AZURE.md`, Abschnitt 5. Das
verwaltete Zertifikat von Azure ist kostenlos.

---

## Offen — braucht eine Entscheidung von dir

### A. Datenschutzerklärung inhaltlich freigeben
Die Seite steht und ist bearbeitbar, der Text ist als **ungeprüfter Entwurf**
gekennzeichnet und für alle sichtbar erst nach dem Speichern. Er nennt
Firestore, Streamlit und Twilio als Auftragsverarbeiter und beschreibt das
Anmelde-Cookie. **Inhaltlich verantworten muss ihn der Verein**, nicht ich –
insbesondere Verantwortlicher, Aufbewahrungsfristen und Kontaktweg.

### ✅ B. Kalendereintrag beim Buchen — erledigt am 09.09.2026
Statt eines Abos bekommt der Nutzer eine **Termineinladung** an die Mail,
die er ohnehin erhält: Buchung → Einladung, Storno → Absage, Notiz des
Admins → aktualisierter Termin. Sein Kalender legt den Termin selbst an
und ändert ihn wieder — ohne neue Infrastruktur, ohne öffentliche Adresse
und ohne zusätzliche Firestore-Zugriffe.

Eingebaut in `Mailer.send_booking_confirmation()`, `send_cancellation()`
und die neue `send_booking_note()`; alle elf Aufrufwege sind dadurch
abgedeckt. Der Kalenderteil entsteht in `core_ics.baue_einladung()` und
`baue_absage()`.

**Zwei Einstellungen sind vor dem Saisonstart zu füllen** (Verwaltung →
Einstellungen → Kalendereinladung): der **Ort des Dienstes** (steht leer,
dann fehlt im Termin die Navigation) und die **Adresse der App**
(vorbelegt mit der Azure-Adresse).

Was das bewusst nicht kann: Es ist ein Versand, kein Abgleich. Wer den
Termin löscht, bekommt ihn nicht von selbst zurück — die Mail bleibt ihm.
Der ICS-Download bleibt als zweiter Weg bestehen.

### C. Echte App statt Lesezeichen
Der Hinweis zum Ablegen auf dem Handy funktioniert, aber es bleibt ein
Browser-Lesezeichen: kein eigenes Symbol, kein Offline-Betrieb. Eine richtige
PWA bräuchte Zugriff auf die ausgelieferte `index.html`, den Streamlit Cloud
nicht gewährt. **Entscheidung: eigenes Hosting oder so belassen.**

### D. Firestore-Indizes anlegen — es sind **zwei**, und der vorhandene hilft nicht
Geprüft am 09.09.2026: In `bookings` existiert bereits ein Index
`slot_date, status`. **Der bedient keine der beiden Abfragen** — Firestore
verlangt die Gleichheitsfelder *vor* dem Bereichsfeld, und beide Abfragen
filtern `status` per Gleichheit und `slot_date` als Bereich.

Anzulegen in der [Firebase Console](https://console.firebase.google.com)
unter *Firestore Database → Indexes → Zusammengesetzt*, Collection
`bookings`, alle Felder aufsteigend:

1. `status`, `slot_date` — für `get_week_bookings()`
2. `user_email`, `status`, `slot_date` — für `get_user_bookings(future_only=True)`

Der zweite ist der dringendere: `get_week_bookings()` fängt den Fehler ab
und liest im Fallback alle Buchungen, `get_user_bookings()` hat **keinen**
Fallback und liefert dann stillschweigend eine leere Liste — „Meine
Buchungen“ wäre leer, ohne dass jemand einen Fehler sähe.

Per Dienstkonto ist das nicht machbar: Das Konto der App darf lesen, nicht
verwalten (HTTP 403 beim Anlegen).

Ohne den Index läuft die App weiter, fällt aber auf das Laden **aller**
Buchungen mit Filterung im Speicher zurück. Das wird mit wachsender
Datenmenge langsam und verbraucht unnötig Lesekontingent. Firestore
verlinkt beim ersten Fehlschlag in der Logausgabe einen fertigen
Erstellungslink – der schnellste Weg.

### E. Fehlermeldungen vor dem Saisonstart abschalten
`showErrorDetails` steht bewusst noch auf sichtbar, damit du beim Testen
echte Meldungen bekommst. **Vor dem Saisonstart in `.streamlit/config.toml`
umstellen**, sonst sehen Nutzer im Fehlerfall Code-Auszüge.

### F. Erinnerungen scharf schalten
Das Skript und die GitHub Action stehen, der Zeitplan ist deaktiviert. Vorher
klären, ob bereits eine andere Stelle Erinnerungen verschickt — sonst kommt
alles doppelt an.

### G. Aufteilung der Hauptdatei
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
