# Betrieb auf Azure

Diese Anleitung beschreibt den laufenden Betrieb der App auf Azure App Service.
Die Entwurfsentscheidungen dahinter stehen in
`docs/superpowers/specs/2026-09-09-azure-app-service-hosting-design.md`.

---

## 1. Wo die App läuft

| | |
|---|---|
| Adresse | https://app-wawa-shiftplaner.azurewebsites.net |
| Resource Group | `rg-wawa-web` |
| Region | West Europe |
| App Service Plan | `asp-wawa-web` — Linux, **B1**, eine Instanz |
| Web App | `app-wawa-shiftplaner` — `PYTHON|3.14` |
| Key Vault | `kv-wawa-web-hzb` |
| Kosten | rund **11,32 €** im Monat (0,0155 €/h × 730 h) |
| Datenbank | unverändert Google Firestore, Projekt `wasserwacht-dienstplan` |

Die App startet über `startup.sh`. Das Skript legt zuerst die
Zugangsdaten als Datei ab (`core_secrets.py`) und ruft danach Streamlit auf.

## 2. Zugangsdaten ändern

Alle Zugangsdaten liegen als **eine** base64-kodierte `secrets.toml` im Key
Vault, im Secret `streamlit-secrets-toml`.

Im Portal findet man es unter
*Key Vaults → kv-wawa-web-hzb → Objects → Secrets → streamlit-secrets-toml*.
Dort lässt sich der Wert ansehen, aber **nicht sinnvoll bearbeiten**: Er ist
base64-kodiert, und das Eingabefeld des Portals ist einzeilig. Der vorgesehene
Weg führt über die Kommandozeile:

```bash
# 1. secrets.toml oertlich pflegen (nach dem Muster von
#    .streamlit/secrets.toml.example), dann:
base64 -w0 secrets.toml > secrets.b64

az keyvault secret set --vault-name kv-wawa-web-hzb \
  --name streamlit-secrets-toml --file secrets.b64 --encoding utf-8

az webapp restart -g rg-wawa-web -n app-wawa-shiftplaner

# 2. Unbedingt aufraeumen:
rm secrets.toml secrets.b64
```

Der Verweis in der App-Einstellung `STREAMLIT_SECRETS_B64` nagelt **keine
Version** fest. Die App zieht deshalb beim nächsten Neustart automatisch die
neueste Fassung; die alte bleibt im Vault versioniert erhalten und lässt sich
zurückholen.

Die Werte selbst gehören nie in das Repository, nie in eine App-Einstellung und
nie in eine Kommandozeile — deshalb der Umweg über `--file`.

**Feldliste:** `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_EMAIL_RECEIVER`,
`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
`ENABLE_SMS_REMINDER`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_PHONE_NUMBER` und der Abschnitt `[firebase]`.

`ADMIN_EMAIL` und `ADMIN_PASSWORD` sind bewusst **leer**. Sie dienen
ausschließlich dazu, beim allerersten Start einen Admin anzulegen. Da der
Adminzugang in Firestore längst besteht, würde ein Wert hier nur einen zweiten
schaffen. Die App protokolliert dazu die Zeile
`ADMIN_EMAIL/ADMIN_PASSWORD nicht gesetzt - kein Admin angelegt` — das ist der
gewünschte Zustand, keine Störung.

## 3. Protokolle lesen

```bash
# Laufende Ausgabe mitschneiden
az webapp log tail -g rg-wawa-web -n app-wawa-shiftplaner

# Verlauf der letzten Auslieferung
az webapp log deployment show -g rg-wawa-web -n app-wawa-shiftplaner
```

`az webapp log tail` zeigt nur, was **ab dem Aufruf** anfällt. Wer den
Startvorgang sehen will, muss den Mitschnitt starten und die App erst danach
neu starten.

Der Kaltstart dauert rund **150 Sekunden**. Deshalb steht die App-Einstellung
`WEBSITES_CONTAINER_START_TIME_LIMIT` auf `600`; das Standardzeitlimit von 230
Sekunden wäre zu knapp und bräche den Hochlauf gelegentlich mit
`SiteStartupCancelled` ab.

Beim gesunden Start steht dort:

```
secrets: /root/.streamlit/secrets.toml geschrieben, <n> Bytes.
  You can now view your Streamlit app in your browser.
```

Steht stattdessen `secrets: Der uebergebene Wert ist leer.`, greift der
Key-Vault-Verweis nicht. Dann prüfen, ob die Managed Identity noch die Rolle
*Key Vault Secrets User* auf dem Vault besitzt.

## 4. Wenn es zu langsam wird

Der Tarif lässt sich ohne Ausfall und ohne erneutes Deployment wechseln:

```bash
az appservice plan update -g rg-wawa-web -n asp-wawa-web --sku B2
```

B2 bringt 2 vCPU und 3,5 GB statt 1 vCPU und 1,75 GB und kostet 22,56 €
im Monat.

**Die Instanzzahl bleibt bei 1.** Streamlit hält den Sitzungszustand im
Arbeitsspeicher des Prozesses; bei zwei Instanzen landeten Anfragen derselben
Person auf verschiedenen Servern. Der Weg bei Lastproblemen heißt also
Aufstieg, nicht Verbreiterung.

## 5. Eigene Domain ergänzen

Voraussetzung: beim DNS-Anbieter ein `CNAME` von der gewünschten Subdomain auf
`app-wawa-shiftplaner.azurewebsites.net`, dazu ein `TXT`-Eintrag auf
`asuid.<subdomain>` mit der Kennung aus
`az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query customDomainVerificationId -o tsv`.

```bash
az webapp config hostname add -g rg-wawa-web \
  --webapp-name app-wawa-shiftplaner --hostname dienstplan.example.de

az webapp config ssl create -g rg-wawa-web \
  --name app-wawa-shiftplaner --hostname dienstplan.example.de
```

Das verwaltete Zertifikat ist kostenlos und erneuert sich selbst. Die
`azurewebsites.net`-Adresse bleibt daneben bestehen.

## 6. Was niemals getan wird

**Für diese Web App wird keine VNet-Integration eingeschaltet, und sie wird
nicht in `vm-hermesVNET` (`10.0.0.0/16`) aufgenommen.**

Grund: Die NSG `vm-hermesNSG` hat keine eigenen Regeln, es greift also die
Azure-Standardregel `AllowVnetInBound`. Sie erlaubt jeglichen Verkehr innerhalb
des VNets. Jede Ressource in diesem Netz hätte damit vollen Netzzugriff auf den
Hermes-Agenten — auch eine übernommene Webanwendung. Die Trennung beruht
bewusst darauf, dass **kein Pfad existiert**, nicht auf einer Regel, die sich
versehentlich lockern lässt.

Braucht die App eines Tages eine private Azure-Ressource, gehört diese in ein
eigenes, neues VNet. Und bevor überhaupt etwas in `vm-hermesVNET` aufgenommen
wird, muss dort die Verlassenschaft auf `AllowVnetInBound` durch ausdrückliche
NSG-Regeln ersetzt werden.

Prüfen lässt sich der Zustand jederzeit:

```bash
az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query virtualNetworkSubnetId -o tsv   # leer
az webapp vnet-integration list -g rg-wawa-web -n app-wawa-shiftplaner -o json                # []
az network vnet peering list -g rg-hermes --vnet-name vm-hermesVNET -o json                   # []
```

## 7. Auslieferung

Ein Push auf `main` löst die Test-Pipeline aus; war sie erfolgreich, liefert
`.github/workflows/deploy-azure.yml` automatisch nach Azure aus. Die Anmeldung
läuft über OIDC mit föderierten Anmeldedaten — bei GitHub liegt kein
langlebiges Geheimnis.

Von Hand geht es so:

```bash
git archive --format=zip -o app.zip HEAD
az webapp deploy -g rg-wawa-web -n app-wawa-shiftplaner --src-path app.zip --type zip
```

`git archive` statt eines Zips über das Arbeitsverzeichnis: Es liefert den
Inhalt aus dem Repository mit LF-Zeilenenden — unter Windows mit
`core.autocrlf = true` hätte `startup.sh` sonst CRLF-Enden und der Container
scheiterte an der Shebang-Zeile.

Der Bau dauert einige Minuten, weil pandas, plotly und grpcio installiert
werden. Läuft die CLI dabei in einen `HTTP 504`, ist das nur ihr eigenes
Zeitlimit — der Bau läuft auf dem Server weiter. Der wahre Stand steht in
`az webapp log deployment show`.

## 8. Parallelbetrieb mit Streamlit Community Cloud

Die alte Instanz läuft vorerst weiter und schreibt in dieselbe
Firestore-Datenbank. Das ist gewollt, aber kein Dauerzustand: Vor dem
Abschalten wird abgestimmt, ab wann die Azure-Adresse die maßgebliche ist.

## Lesezugriff des Hermes-Agenten

Seit 09.09.2026 liest der Hermes-Agent (Azure-VM `vm-hermes`) die Firestore-Datenbank
mit einem **eigenen Dienstkonto**:

| | |
|---|---|
| Dienstkonto | `hermes-readonly@wasserwacht-dienstplan.iam.gserviceaccount.com` |
| Rolle | `roles/datastore.viewer` — nur lesen, projektweit |
| Zugriffsweg | direkt auf Firestore, **nicht** über diese Web-App |

Der Agent nutzt weder die Streamlit-Oberfläche noch einen App-Login. Der Admin-Account
`WaWaBot / mex100bot@gmail.com` in der `users`-Collection bleibt trotzdem sinnvoll: Er
ist die Spur in den Daten, sobald ein späteres Schreib-Werkzeug `approved_by` oder
`cancelled_by` setzt.

**Für die Entwicklung an dieser App heißt das:** Feldnamen in `bookings` und `users`
sind jetzt eine Schnittstelle nach außen. Wer `slot_date`, `slot_time`, `status`,
`user_email`, `user_name`, `pending_approval` oder `active` umbenennt, muss
`~/.hermes/scripts/wawa_query.py` auf der Hermes-VM mit anpassen — sonst liefert der
Agent stillschweigend leere Ergebnisse statt eines Fehlers.

Schreibzugriff hat der Agent **nicht**; ein Schreibversuch endet mit HTTP 403.
Freigaben und Stornos laufen weiter über die App. Details und die Befehlsliste stehen
in `azure-hermes/README.md`.

