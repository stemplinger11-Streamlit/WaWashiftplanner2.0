# Firebase-Datenbank sichern

Kurzanleitung für den Saisonwechsel. Ziel: **Die Nutzerkonten müssen erhalten
bleiben** – niemand soll sich neu registrieren müssen. Die Buchungsdaten der
vergangenen Saison sind dagegen verzichtbar.

---

## Das Wichtigste zuerst

⚠️ **Der Benutzer-Export in der App reicht als Backup nicht aus.**

Unter *Export → Benutzer als JSON* wird das Feld `password_hash` bewusst
entfernt. Aus dieser Datei zurückgespielt hätte **kein einziger Nutzer mehr ein
funktionierendes Passwort** – genau der Fall, den du vermeiden willst. Dieser
Export ist zum Nachschlagen gedacht, nicht zum Wiederherstellen.

Für eine wiederherstellbare Sicherung nimm einen der beiden Wege unten.

---

## Weg A – Skript im Repo (empfohlen)

Sichert alle Collections inklusive Passwort-Hashes in eine JSON-Datei.

### Einmalig vorbereiten

```bash
pip install google-cloud-firestore
```

Zugangsdaten braucht das Skript in einer dieser Formen:

1. Eine lokale `.streamlit/secrets.toml` mit dem Abschnitt `[firebase]` –
   also genau die Datei, die du auch in Streamlit.io hinterlegt hast.
2. Alternativ eine Service-Account-JSON, direkt übergeben mit `--key`.

Die Service-Account-Datei bekommst du in der
[Firebase Console](https://console.firebase.google.com) unter
*Projekteinstellungen → Dienstkonten → Neuen privaten Schlüssel generieren*.

### Sichern

```bash
python scripts/firestore_backup.py
```

Ergebnis: `backups/firestore_<datum>_<uhrzeit>.json`. Das Skript meldet am Ende,
wie viele Benutzer gesichert wurden und wie viele davon einen Passwort-Hash
haben. **Beide Zahlen müssen übereinstimmen** – sonst stimmt etwas nicht.

### Zurückspielen

Der Trockenlauf zeigt erst nur, was passieren würde:

```bash
python scripts/firestore_restore.py backups/firestore_20260902_101500.json
```

Erst mit `--schreiben` wird tatsächlich geschrieben (mit Rückfrage):

```bash
python scripts/firestore_restore.py backups/<datei>.json --schreiben
```

Nur die Benutzer zurückholen, Buchungen unangetastet lassen:

```bash
python scripts/firestore_restore.py backups/<datei>.json --nur users --schreiben
```

---

## Weg B – Managed Export von Google

Der offizielle Weg, unabhängig von diesem Repo. **Setzt den Blaze-Tarif voraus**
(nutzungsbasiert; für diese Datenmengen praktisch kostenlos, aber es muss eine
Zahlungsmethode hinterlegt sein).

```bash
gcloud config set project DEIN-PROJEKT-ID
gcloud firestore export gs://DEIN-BUCKET/backup-$(date +%Y%m%d)
```

Zurückspielen:

```bash
gcloud firestore import gs://DEIN-BUCKET/backup-20260902
```

Vorteil: von Google verwaltet, konsistenter Snapshot. Nachteil: Bucket und
Abrechnung nötig, und die Daten sind nicht ohne Weiteres lesbar.

---

## Empfohlenes Vorgehen zum Saisonstart

1. **Sicherung ziehen**, solange die alte App noch unverändert läuft:
   ```bash
   python scripts/firestore_backup.py --out backups/vor_saison_2026.json
   ```
2. **Prüfen**, dass die Datei brauchbar ist – Benutzerzahl und Hash-Zahl
   müssen gleich sein. Die Datei einmal öffnen und stichprobenartig nachsehen,
   ob deine eigene E-Mail-Adresse mit `password_hash` enthalten ist.
3. **Kopie außerhalb des Rechners** ablegen (privater Cloud-Ordner o. Ä.).
4. Zweite Streamlit-App auf `WaWashiftplanner2.0` anlegen, **dieselben Secrets**
   eintragen. Beide Apps zeigen dann auf dieselbe Datenbank.
5. Testen. Falls etwas schiefgeht, mit `firestore_restore.py --nur users`
   gezielt die Konten zurückholen.

### Alte Buchungen loswerden

Da die Buchungen der letzten Saison nicht wichtig sind, kannst du sie nach der
Sicherung aufräumen – in der App unter *Verwaltung → Archivieren*. Das
verschiebt Buchungen, die älter als 12 Monate sind, in die Collection `archive`,
statt sie zu löschen. Die Nutzerkonten bleiben dabei unberührt.

---

## Sicherheitshinweis

Die Sicherungsdatei enthält **Passwort-Hashes, E-Mail-Adressen und
Telefonnummern**. Sie gehört nicht ins Repository – `backups/` und
`*serviceAccount*.json` sind in der `.gitignore` bereits ausgeschlossen.
Bewahre sie so auf, wie du eine Mitgliederliste aufbewahren würdest.

---

## Regelmäßig sichern

Für den laufenden Betrieb genügt es, das Backup-Skript vor jeder größeren
Änderung und einmal zu Saisonbeginn und -ende laufen zu lassen. Wer es
automatisieren will: eine GitHub Action mit `schedule`-Trigger kann das Skript
wöchentlich ausführen – dafür müssen die Firebase-Zugangsdaten allerdings
zusätzlich als GitHub-Secret hinterlegt werden.
