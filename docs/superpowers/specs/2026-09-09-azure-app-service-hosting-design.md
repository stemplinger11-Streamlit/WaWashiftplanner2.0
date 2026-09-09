# WaWashiftplanner 2.0 auf Azure App Service

Stand: 09.09.2026

Die App läuft heute auf Streamlit Community Cloud. Sie soll künftig auf Azure
liegen: öffentlich erreichbar, jederzeit ohne Wartezeit, und ohne jeden
Netzwerkpfad zum Hermes-Agenten.

---

## 1. Ziele

1. Die Website ist unter einer öffentlichen HTTPS-Adresse erreichbar, ohne
   Anmeldung an Azure, aus dem gesamten Internet.
2. Sie antwortet jederzeit sofort. Kein Einschlafen, kein Kaltstart im Betrieb.
3. Vom Webserver aus ist `vm-hermes` **nicht erreichbar** – auch dann nicht,
   wenn ein Angreifer die Webanwendung vollständig übernimmt.
4. Zugangsdaten liegen nicht in der Deployment-Konfiguration und nicht im
   Repository.
5. Die Kosten bleiben unter 70 € im Monat, gerechnet nur für den Webserver.

## 2. Nicht-Ziele

- **Keine Datenmigration.** Firestore bleibt die Datenbank. Es wird keine
  Azure-Datenbank angelegt.
- **Keine eigene Domain in dieser Ausbaustufe.** Die Azure-Adresse genügt
  vorerst; eine externe Domain ist in Beschaffung und wird später ergänzt.
- **Kein CDN, keine WAF, kein Front Door.** Für eine Vereins-App mit
  zweistelliger Nutzerzahl unnötige Kosten und Komplexität.
- **Kein Staging-Slot.** Der Basic-Tarif unterstützt keine Bereitstellungsslots.
  Bewusst in Kauf genommen (siehe Abschnitt 9).
- **Keine Änderung am Hermes-Agenten.** Dessen Kosten und Konfiguration werden
  getrennt betrachtet.

## 3. Ausgangslage

Erhoben am 09.09.2026 gegen Subscription `6e87d817-7495-412d-93e4-fad170123e80`
(Tenant: Förderverein der BRK Wasserwacht Ortsgruppe Hauzenberg e.V.).

| Vorgefunden | Wert |
|---|---|
| Vorhandene Resource Groups | `rg-hermes` (swedencentral), `NetworkWatcherRG` |
| Vorhandene Ressourcen | ausschließlich VM `vm-hermes` samt NIC, NSG, VNet, Public IP |
| VNet `vm-hermesVNET` | `10.0.0.0/16`, Subnetz `vm-hermesSubnet` `10.0.0.0/24` |
| NSG `vm-hermesNSG` | **keine eigenen Regeln**, nur Azure-Standardregeln |
| Anwendung | Streamlit 1.63, Python, Datenhaltung in Google Firestore |
| Weitere Abhängigkeiten | Gmail-SMTP, Twilio (SMS), alles öffentliches Internet |

**Sicherheitsrelevanter Befund:** Weil `vm-hermesNSG` keine eigenen Regeln hat,
greift die Azure-Standardregel `AllowVnetInBound`. Sie erlaubt jeglichen Verkehr
*innerhalb* von `10.0.0.0/16`. Aus dem Internet ist nichts erreichbar
(`DenyAllInBound`), aber jede Ressource, die in dieses VNet aufgenommen wird,
hätte per Voreinstellung vollen Netzzugriff auf Hermes. Daraus folgt die
zentrale Entwurfsentscheidung in Abschnitt 5.

## 4. Architektur

Azure App Service, Linux, Tarif Basic B1, Laufzeit `PYTHON|3.14`.

```
Internet
   │  HTTPS (443)
   ▼
┌──────────────────────────────────────────────┐
│ Resource Group  rg-wawa-web  (West Europe)   │
│                                              │
│  App Service Plan  asp-wawa-web   (Linux B1) │
│      └── Web App  app-wawa-shiftplaner       │
│              │  System-assigned Identity     │
│              ▼                               │
│          Key Vault  kv-wawa-web-<suffix>     │
└──────────────────────────────────────────────┘
   │ ausgehend, öffentliches Internet
   ├──► Google Firestore   (Dienstplandaten)
   ├──► smtp.gmail.com     (E-Mail)
   └──► api.twilio.com     (SMS)

                    ╳  keine Verbindung  ╳

┌──────────────────────────────────────────────┐
│ Resource Group  rg-hermes  (Sweden Central)  │
│  vm-hermes  im VNet 10.0.0.0/16              │
└──────────────────────────────────────────────┘
```

**Warum App Service und nicht etwas anderes.** App Service ist die vordefinierte
Webserver-Instanz: Python-Laufzeit, TLS-Zertifikat, Betriebssystem-Patching und
GitHub-Deployment kommen fertig. Container Apps kostet für eine dauerhaft
laufende Instanz rund das Dreifache und verlangt zusätzlich ein selbst gebautes
Container-Image. Eine zweite VM wäre billiger als Container Apps, verlagert aber
Systemaktualisierung, Reverse Proxy und Zertifikatserneuerung auf uns.

**Warum West Europe.** Gleicher Preis wie Sweden Central (0,0155 €/h für B1),
aber geringere Laufzeit zu deutschen Nutzern. Dass es eine andere Region als
Hermes ist, ist ein willkommener Nebeneffekt, nicht die Begründung – die
Trennung entsteht in Abschnitt 5, nicht durch die Region.

**Warum B1 und nicht größer.** B1 bietet 1 vCPU und 1,75 GB RAM und unterstützt
„Always On". Der Tarif eines App-Service-Plans lässt sich später ohne erneutes
Deployment und ohne Ausfall auf B2 (2 vCPU, 3,5 GB, 22,56 €/Monat) heben. Größer
einzukaufen, bevor gemessen ist, dass RAM knapp wird, bringt keinen Nutzen.

## 5. Abschottung gegenüber Hermes

Die Trennung wird **durch das Fehlen einer Netzwerkverbindung** hergestellt, nicht
durch eine Regel, die jemand später lockern kann.

| Maßnahme | Wirkung |
|---|---|
| Eigene Resource Group `rg-wawa-web`, eigene Region | Keine gemeinsame Verwaltungseinheit, getrennte Zugriffsrechte und Kostensicht |
| **Keine VNet-Integration der Web App** | Ohne Integration besitzt App Service keine Route nach `10.0.0.0/16`. Ausgehender Verkehr verlässt Azure über öffentliche Adressen. |
| Kein Peering, kein Private Endpoint, kein Private DNS zwischen den Gruppen | Es entsteht kein Umweg |
| `httpsOnly = true`, `minTlsVersion = 1.2`, `ftpsState = Disabled` | Kein unverschlüsselter Zugang, kein FTP-Deployment |
| Zugangsdaten nur im Key Vault, Zugriff über Managed Identity | Kein Token in Repository, App-Settings oder Deployment-Konfiguration |

**Verbindlich für die Zukunft:** Für diese Web App wird VNet-Integration nie
aktiviert. Sollte die App eines Tages eine private Azure-Ressource brauchen,
gehört diese in ein **eigenes, neues** VNet – niemals in `vm-hermesVNET`. Und
sobald irgendetwas in `vm-hermesVNET` aufgenommen wird, muss zuvor die
Verlassenschaft auf `AllowVnetInBound` durch ausdrückliche NSG-Regeln ersetzt
werden.

## 6. Umgang mit Zugangsdaten

Die App liest ihre Geheimnisse über `st.secrets`, also aus einer Datei
`secrets.toml`. Zu den flachen Werten (`SMTP_PASSWORD`, `TWILIO_AUTH_TOKEN`, …)
kommt der verschachtelte Abschnitt `[firebase]`, dessen `private_key`
Zeilenumbrüche enthält. Einzelne Werte auf App-Settings abzubilden wäre deshalb
fehleranfällig.

**Entscheidung:** Die vollständige `secrets.toml` wird als *ein* Key-Vault-Secret
abgelegt, Base64-kodiert, unter dem Namen `streamlit-secrets-toml`. Base64
verhindert, dass Zeilenumbrüche und Anführungszeichen auf dem Weg beschädigt
werden.

Ablauf:

1. Web App erhält eine systemseitig zugewiesene Managed Identity.
2. Diese Identität bekommt per RBAC die Rolle **Key Vault Secrets User** auf dem
   Key Vault – ausschließlich lesend, ausschließlich auf diesen Vault.
3. Die App-Einstellung `STREAMLIT_SECRETS_B64` verweist per
   `@Microsoft.KeyVault(SecretUri=…)` auf das Secret. Der Wert selbst erscheint
   nirgends in der Konfiguration.
4. `startup.sh` dekodiert den Wert beim Start nach `$HOME/.streamlit/secrets.toml`
   mit Dateirechten `600` und startet erst danach Streamlit.

**Übergabe der Werte:** Die tatsächlichen Zugangsdaten werden über eine Datei im
Scratchpad-Verzeichnis übergeben, nicht über den Chatverlauf. Nach der Übertragung
in den Key Vault wird die lokale Datei gelöscht und das Löschen bestätigt.

**Schlüsselrotation:** Der Firebase-Dienstkontoschlüssel und das
Gmail-App-Passwort liegen unbefristet im Vault. Bei einem Wechsel wird nur die
neue Version des Vault-Secrets angelegt; die Web App zieht sie beim nächsten
Neustart. Die alte Version bleibt im Vault versioniert erhalten.

## 7. Laufzeitkonfiguration

| Einstellung | Wert | Begründung |
|---|---|---|
| `alwaysOn` | `true` | Erfüllt Ziel 2. Ohne diese Einstellung entlädt App Service die Anwendung nach 20 Minuten Ruhe. |
| `webSocketsEnabled` | `true` | Streamlit hält die Verbindung zum Browser über WebSockets. Ohne dies bleibt die Seite leer. |
| `numberOfWorkers` / Instanzen | `1` | Streamlit hält Sitzungszustand im Arbeitsspeicher des Prozesses. Siehe Risiko R2. |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `1` | Azure installiert `requirements.txt` beim Deployment. |
| Startbefehl | `bash startup.sh` | |

`startup.sh` wird neu im Repository angelegt und leistet zweierlei: Secrets
schreiben, dann Streamlit starten – gebunden an `$PORT`, den App Service
vorgibt, auf `0.0.0.0`, im Headless-Modus.

Die vorhandene `.streamlit/config.toml` (Farbschema, `gatherUsageStats = false`)
liegt im Anwendungsverzeichnis und wird unverändert weiterverwendet.

**Python 3.14 ist auf App Service Linux verfügbar** (geprüft am 09.09.2026,
Support bis 2030-10-31). Das ist genau die Version, für die `requirements.txt`
die cp314-Wheels gepinnt hat. Die Pins bleiben deshalb unverändert – der
Kommentarblock in `requirements.txt`, der sich auf Streamlit Community Cloud
bezieht, wird um den Hinweis auf App Service ergänzt.

## 8. Deployment

GitHub Actions im Repository `stemplinger11-Streamlit/WaWashiftplanner2.0`
(Remote `target`), Auslöser: Push auf `main`.

- Die Anmeldung an Azure erfolgt über **OIDC mit föderierten Anmeldedaten**, nicht
  über ein Publish-Profile. Damit liegt kein langlebiges Geheimnis bei GitHub.
- Der Deployment-Auftrag hängt am bestehenden Test-Auftrag aus `tests.yml`.
  Schlagen die Tests fehl, wird nicht ausgeliefert. `test_app_smoke.py` lädt die
  gesamte App gegen die echten Paketversionen und fängt genau die Paketbrüche ab,
  die sonst erst in Azure auffallen.
- `reminders.yml` bleibt unverändert; die Erinnerungen laufen weiterhin als
  GitHub-Action gegen Firestore und sind vom Hosting unabhängig.

## 9. Kosten

Listenpreise West Europe, abgerufen über die Azure-Retail-Prices-API am
09.09.2026, gerechnet mit 730 Stunden im Monat.

| Posten | Monat |
|---|---|
| App Service Plan B1 Linux (0,0155 €/h) | **11,32 €** |
| Key Vault (Vorgangsgebühr, wenige Zugriffe je Neustart) | < 0,10 € |
| Ausgehender Datenverkehr (die ersten 100 GB je Monat sind frei) | 0,00 € |
| TLS-Zertifikat der `azurewebsites.net`-Adresse | 0,00 € |
| **Summe** | **~11,4 €** |

Das sind rund 16 % des Budgets von 70 €. Reserve für später:

- Aufstieg auf **B2** (2 vCPU, 3,5 GB): 22,56 €/Monat, jederzeit ohne Ausfall.
- Eigene Domain: Das verwaltete Zertifikat von Azure ist kostenlos. Wird die
  DNS-Zone zu Azure geholt, kommen ~0,45 €/Monat je Zone hinzu; beim externen
  Anbieter zu bleiben kostet in Azure nichts.

Die Kosten des Hermes-Agenten (~49 €/Monat nach Listenpreis) werden getrennt
geführt und sind hier nicht enthalten.

## 10. Abnahmekriterien

Prüfbar, jeweils mit Kommando oder Handgriff:

1. `curl -sI https://app-wawa-shiftplaner.azurewebsites.net` liefert `200`.
2. `curl -sI http://app-wawa-shiftplaner.azurewebsites.net` liefert eine
   Umleitung auf HTTPS.
3. Im Browser: Anmeldung, Buchung einer Schicht, Stornierung, Anzeige der
   Rangliste mit Diagramm, ICS-Export. Alle gegen dieselbe Firestore-Datenbank
   wie bisher.
4. `az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query virtualNetworkSubnetId`
   liefert `null`.
5. `az webapp vnet-integration list -g rg-wawa-web -n app-wawa-shiftplaner`
   liefert eine leere Liste.
6. Aus der SSH-Konsole der Web App scheitert `nc -z -w3 <private IP vm-hermes> 22`
   im Timeout.
7. `az webapp restart …`, danach ist Kriterium 1 innerhalb von 90 Sekunden ohne
   manuellen Eingriff wieder erfüllt – der Secrets-Abruf funktioniert also
   dauerhaft, nicht nur beim ersten Start.
8. Ein Push auf `main` mit rotem Test liefert **nicht** aus.
9. Nach 20 Minuten ohne Zugriff antwortet die Seite weiterhin ohne Verzögerung
   (Beleg für `alwaysOn`).
10. Weder Repository noch App-Settings noch Workflow-Datei enthalten einen
    Klartext-Zugangswert. `git log -p` der neuen Dateien wird darauf geprüft.

## 11. Risiken

**R1 – Arbeitsspeicher auf B1.** 1,75 GB für Python, pandas, plotly und mehrere
gleichzeitige Sitzungen. *Erkennung:* Kriterium 9 in Verbindung mit der
Speichermetrik des App Service Plans über zwei Wochen. *Gegenmaßnahme:* Aufstieg
auf B2, Kosten und Vorgehen in Abschnitt 9.

**R2 – Sitzungszustand bei mehreren Instanzen.** Streamlit hält den Zustand einer
Sitzung im Prozess. Würde der Plan auf zwei Instanzen skaliert, landeten Anfragen
derselben Person auf verschiedenen Instanzen. App Service setzt zwar
standardmäßig ein Zuordnungs-Cookie (`ARRAffinity`), darauf soll sich aber
niemand verlassen: Die Instanzzahl bleibt auf 1. Bei Lastproblemen ist der Weg
Aufstieg (B2), nicht Verbreiterung.

**R3 – Kein Staging-Slot im Basic-Tarif.** Ein Deployment ersetzt die laufende
Anwendung; dabei entsteht eine Unterbrechung von etwa 30 bis 60 Sekunden.
*Bewertung:* Für einen Vereinsdienstplan hinnehmbar, zumal Deployments selten
und planbar sind. Slots gäbe es erst ab Standard (S1), was den Preis mehr als
verdreifachen würde.

**R4 – Doppelbetrieb während der Umstellung.** Solange die alte Instanz auf
Streamlit Community Cloud läuft, schreiben zwei Anwendungen in dieselbe
Firestore-Datenbank. Das ist für den Abnahmetest gewollt, darf aber kein
Dauerzustand werden. *Gegenmaßnahme:* Nach bestandener Abnahme wird die alte
Instanz abgeschaltet, bevor Nutzerinnen und Nutzer die neue Adresse erhalten.
Der genaue Zeitpunkt der Umstellung wird vor dem Abschalten abgestimmt.

**R5 – Key Vault als Einzelfehlerquelle.** Ist der Vault nicht erreichbar,
startet die App nicht. *Bewertung:* Akzeptiert. Der Vault wird mit
vorläufigem Löschen (Soft Delete, 90 Tage) und Löschschutz angelegt, damit ein
versehentliches Entfernen behebbar bleibt.

**R6 – Firebase-Dienstkontoschlüssel im Klartext im Vault.** Wer den Vault liest,
erhält Vollzugriff auf Firestore. *Gegenmaßnahme:* Lesezugriff ausschließlich für
die Managed Identity der Web App, keine Zugriffsrichtlinie für Nutzerkonten außer
dem Administrator; Diagnoseprotokoll des Vaults aktiviert.

## 12. Offene Punkte

Ausdrücklich nicht Teil dieser Ausbaustufe, bewusst später zu entscheiden:

- Zeitpunkt der Abschaltung der Streamlit-Community-Cloud-Instanz (R4).
- Anbindung der externen Domain, sobald sie vorliegt.
