# Azure App Service Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den WaWashiftplanner 2.0 auf Azure App Service (Linux, B1, West Europe) öffentlich erreichbar machen, dauerhaft wach, ohne jeden Netzwerkpfad zum Hermes-Agenten.

**Architecture:** Ein App Service Plan B1 in einer eigenen Resource Group `rg-wawa-web` ohne VNet-Integration trägt eine Python-3.14-Web-App. Ein Startskript holt die Zugangsdaten aus einem Key Vault, schreibt sie als `secrets.toml` und startet erst dann Streamlit. Ausgeliefert wird über GitHub Actions mit OIDC, abhängig von den bestehenden Tests.

**Tech Stack:** Azure App Service (Linux, `PYTHON|3.14`), Azure Key Vault, Managed Identity, Azure CLI, GitHub Actions, Streamlit 1.63, Python 3.14, pytest, pyflakes.

**Spec:** `docs/superpowers/specs/2026-09-09-azure-app-service-hosting-design.md`

## Global Constraints

- Subscription: `6e87d817-7495-412d-93e4-fad170123e80`, Tenant `78d975d6-0408-4e64-a71a-6f34f8596fec`.
- Region für alle neuen Ressourcen: `westeurope`. Resource Group: `rg-wawa-web`.
- **Die Web App erhält niemals VNet-Integration.** Kein Peering, kein Private Endpoint, keine Verbindung zu `vm-hermesVNET` (`10.0.0.0/16`).
- Laufzeit exakt `PYTHON|3.14` — dieselbe Version, für die `requirements.txt` cp314-Wheels pinnt.
- Tarif `B1` Linux, genau **eine** Instanz (`--number-of-workers 1`).
- Keine Zugangsdaten im Repository, in App-Settings, in Workflow-Dateien oder in Kommandozeilen, die in Protokolle wandern. Werte ausschließlich per Datei-Übergabe.
- Bestehende Dateien `.streamlit/config.toml`, `.github/workflows/tests.yml` und `.github/workflows/reminders.yml` bleiben inhaltlich unverändert.
- Neue Python-Module folgen der Namenskonvention `core_*.py` mit zugehörigem `test_core_*.py`; `pyflakes` prüft `core_*.py` in der Pipeline.
- Commit-Sprache: Deutsch, Betreff im Imperativ oder als Sachaussage, wie im bestehenden Verlauf (`git log --oneline`).
- Firestore bleibt die Datenbank. Die Streamlit-Community-Cloud-Instanz läuft während der gesamten Umsetzung parallel weiter und wird **nicht** abgeschaltet.

## Namen der Ressourcen

| Ressource | Name | Anmerkung |
|---|---|---|
| Resource Group | `rg-wawa-web` | |
| App Service Plan | `asp-wawa-web` | Linux, B1 |
| Web App | `app-wawa-shiftplaner` | muss weltweit eindeutig sein, wird in Task 2 geprüft |
| Key Vault | `kv-wawa-web-hzb` | muss weltweit eindeutig sein, 3–24 Zeichen, wird in Task 3 geprüft |
| Key-Vault-Secret | `streamlit-secrets-toml` | Inhalt: base64-kodierte `secrets.toml` |
| App-Einstellung | `STREAMLIT_SECRETS_B64` | Key-Vault-Verweis, kein Klartext |

## Dateien

| Datei | Verantwortung |
|---|---|
| `core_secrets.py` (neu) | Base64-Wert entgegennehmen, prüfen, als `secrets.toml` mit Rechten 600 schreiben. Als Skript aufrufbar. |
| `test_core_secrets.py` (neu) | Prüft `core_secrets.py` ohne Azure, ohne Streamlit. |
| `startup.sh` (neu) | Startbefehl der Web App: Secrets schreiben, dann Streamlit starten. |
| `.streamlit/secrets.toml.example` (bestehend) | Bleibt die Vorlage, wird um den Azure-Weg ergänzt. |
| `.github/workflows/deploy-azure.yml` (neu) | Ausliefern nach bestandenen Tests, Anmeldung per OIDC. |
| `README.md` (bestehend) | Abschnitt „Betrieb auf Azure" ergänzen. |
| `docs/BETRIEB-AZURE.md` (neu) | Betriebsanleitung: Secrets nachtragen, Tarif wechseln, Protokolle lesen. |

---

### Task 1: Secrets-Modul und Startskript

Das Herzstück: Streamlit liest Zugangsdaten nur aus einer Datei. Diese Task
baut die Brücke von der Umgebungsvariablen zur Datei — testbar ohne Azure.

**Files:**
- Create: `core_secrets.py`
- Test: `test_core_secrets.py`
- Create: `startup.sh`
- Modify: `.streamlit/secrets.toml.example` (Kopfkommentar)

**Interfaces:**
- Produces:
  - `core_secrets.write_secrets_file(encoded: str, target: pathlib.Path) -> int`
    — dekodiert `encoded` (Base64, UTF-8), schreibt nach `target`, legt fehlende
    Elternverzeichnisse an, setzt Rechte `0o600`, gibt die Anzahl geschriebener
    Bytes zurück. Wirft `ValueError` bei leerer Eingabe oder ungültigem Base64.
  - `core_secrets.main() -> int` — liest `STREAMLIT_SECRETS_B64` und `HOME` aus
    der Umgebung, schreibt nach `$HOME/.streamlit/secrets.toml`, gibt einen
    Exit-Code zurück (`0` Erfolg, `1` Fehler). Gibt niemals den Secret-Inhalt aus.
- Consumes: nichts aus früheren Tasks.

- [ ] **Step 1: Write the failing test**

Create `test_core_secrets.py`:

```python
"""Tests fuer core_secrets - ohne Azure, ohne Streamlit, ohne Netz."""

import base64
import stat

import pytest

import core_secrets


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_schreibt_dekodierten_inhalt(tmp_path):
    ziel = tmp_path / ".streamlit" / "secrets.toml"
    inhalt = 'ADMIN_EMAIL = "a@b.de"\n\n[firebase]\nproject_id = "x"\n'

    geschrieben = core_secrets.write_secrets_file(_b64(inhalt), ziel)

    assert ziel.read_text(encoding="utf-8") == inhalt
    assert geschrieben == len(inhalt.encode("utf-8"))


def test_legt_fehlendes_verzeichnis_an(tmp_path):
    ziel = tmp_path / "tief" / "tiefer" / "secrets.toml"

    core_secrets.write_secrets_file(_b64("A = 1\n"), ziel)

    assert ziel.exists()


def test_zeilenumbrueche_im_private_key_bleiben_erhalten(tmp_path):
    # Der Firebase-Schluessel enthaelt \n als zwei Zeichen im TOML-String.
    # Genau deshalb wird base64 verwendet - das muss unveraendert ankommen.
    ziel = tmp_path / "secrets.toml"
    inhalt = 'private_key = "-----BEGIN-----\\nMIIE\\n-----END-----\\n"\n'

    core_secrets.write_secrets_file(_b64(inhalt), ziel)

    assert ziel.read_text(encoding="utf-8") == inhalt


def test_datei_ist_nur_fuer_den_eigentuemer_lesbar(tmp_path):
    ziel = tmp_path / "secrets.toml"

    core_secrets.write_secrets_file(_b64("A = 1\n"), ziel)

    modus = stat.S_IMODE(ziel.stat().st_mode)
    # Auf Windows bildet Python die Gruppen- und Weltrechte nicht ab,
    # deshalb wird nur geprueft, dass niemand ausser dem Eigentuemer darf.
    assert modus & 0o077 == 0


def test_leere_eingabe_wird_abgelehnt(tmp_path):
    with pytest.raises(ValueError, match="leer"):
        core_secrets.write_secrets_file("", tmp_path / "secrets.toml")


def test_ungueltiges_base64_wird_abgelehnt(tmp_path):
    with pytest.raises(ValueError, match="Base64"):
        core_secrets.write_secrets_file("!!!kein base64!!!", tmp_path / "secrets.toml")


def test_ungueltige_datei_wird_nicht_angelegt(tmp_path):
    ziel = tmp_path / "secrets.toml"

    with pytest.raises(ValueError):
        core_secrets.write_secrets_file("!!!", ziel)

    assert not ziel.exists()


def test_main_ohne_umgebungsvariable_meldet_fehler(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("STREAMLIT_SECRETS_B64", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert core_secrets.main() == 1
    assert not (tmp_path / ".streamlit" / "secrets.toml").exists()


def test_main_schreibt_nach_home(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMLIT_SECRETS_B64", _b64("A = 1\n"))
    monkeypatch.setenv("HOME", str(tmp_path))

    assert core_secrets.main() == 0
    assert (tmp_path / ".streamlit" / "secrets.toml").read_text(encoding="utf-8") == "A = 1\n"


def test_main_gibt_den_inhalt_niemals_aus(tmp_path, monkeypatch, capsys):
    geheim = 'SMTP_PASSWORD = "streng-geheim-4711"\n'
    monkeypatch.setenv("STREAMLIT_SECRETS_B64", _b64(geheim))
    monkeypatch.setenv("HOME", str(tmp_path))

    core_secrets.main()

    ausgabe = capsys.readouterr()
    assert "streng-geheim-4711" not in ausgabe.out
    assert "streng-geheim-4711" not in ausgabe.err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test_core_secrets.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core_secrets'`

- [ ] **Step 3: Write minimal implementation**

Create `core_secrets.py`:

```python
"""Zugangsdaten aus der Umgebung in die von Streamlit erwartete Datei schreiben.

Streamlit liest ``st.secrets`` ausschliesslich aus einer Datei, nicht aus
Umgebungsvariablen. Auf Azure App Service kommen die Werte dagegen als
App-Einstellung an, die auf ein Key-Vault-Secret verweist. Dieses Modul
schlaegt die Bruecke: es dekodiert die base64-kodierte ``secrets.toml`` und
legt sie an, bevor Streamlit startet.

Base64 deshalb, weil der Firebase-Schluessel Zeilenumbrueche und
Anfuehrungszeichen enthaelt, die auf dem Weg durch App-Einstellungen sonst
beschaedigt werden koennen.
"""

import base64
import binascii
import os
import pathlib
import sys

ZIEL_UNTERHALB_HOME = pathlib.Path(".streamlit") / "secrets.toml"


def write_secrets_file(encoded: str, target: pathlib.Path) -> int:
    """Schreibt den base64-kodierten Inhalt nach ``target``.

    Gibt die Anzahl geschriebener Bytes zurueck. Wirft ``ValueError``, wenn
    ``encoded`` leer oder kein gueltiges Base64 ist - in dem Fall wird keine
    Datei angelegt, damit kein halb beschriebener Zustand entsteht.
    """
    if not encoded or not encoded.strip():
        raise ValueError("Der uebergebene Wert ist leer.")

    try:
        roh = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as fehler:
        raise ValueError(f"Der uebergebene Wert ist kein gueltiges Base64: {fehler}") from fehler

    target = pathlib.Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Rechte vor dem Schreiben setzen, damit der Inhalt nie - auch nicht
    # kurzzeitig - mit weiteren Rechten auf der Platte liegt.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, roh)
    finally:
        os.close(fd)

    # Bei bereits vorhandener Datei aendert O_CREAT die Rechte nicht mehr.
    os.chmod(target, 0o600)

    return len(roh)


def main() -> int:
    """Einstiegspunkt fuer ``startup.sh``. Gibt nie den Inhalt aus."""
    encoded = os.environ.get("STREAMLIT_SECRETS_B64", "")
    heim = pathlib.Path(os.environ.get("HOME", ""))
    ziel = heim / ZIEL_UNTERHALB_HOME

    try:
        anzahl = write_secrets_file(encoded, ziel)
    except ValueError as fehler:
        print(f"secrets: {fehler} Die App startet ohne Zugangsdaten.", file=sys.stderr)
        return 1
    except OSError as fehler:
        print(f"secrets: konnte {ziel} nicht schreiben: {fehler}", file=sys.stderr)
        return 1

    print(f"secrets: {ziel} geschrieben, {anzahl} Bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest test_core_secrets.py -q`
Expected: PASS, 10 Tests.

Falls `test_datei_ist_nur_fuer_den_eigentuemer_lesbar` unter Windows scheitert:
Das ist kein Implementierungsfehler. Windows bildet POSIX-Rechte nicht ab.
Dann den Test mit `@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte")`
versehen — die Pipeline läuft auf Ubuntu und prüft dort weiterhin.

- [ ] **Step 5: Gesamte Testsuite und statische Prüfung**

Run: `python -m pytest -q && python -m pyflakes streamlit_app.py core_*.py scripts/*.py`
Expected: Alles grün. Das neue Modul darf keinen bestehenden Test brechen.

- [ ] **Step 6: Startskript anlegen**

Create `startup.sh`:

```bash
#!/usr/bin/env bash
#
# Startbefehl der Azure Web App.
#
# Zwei Schritte: erst die Zugangsdaten aus der App-Einstellung
# STREAMLIT_SECRETS_B64 (Verweis auf den Key Vault) als Datei ablegen, dann
# Streamlit starten. App Service gibt den Port ueber $PORT vor; wird darauf
# nicht gelauscht, gilt die App als nicht gestartet.
set -euo pipefail

python core_secrets.py || echo "startup: weiter ohne Zugangsdaten - die App wird Fehler melden" >&2

exec python -m streamlit run streamlit_app.py \
    --server.port "${PORT:-8000}" \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection true
```

- [ ] **Step 7: Startskript örtlich prüfen**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
HOME=$(mktemp -d) STREAMLIT_SECRETS_B64=$(printf 'A = 1\n' | base64) \
  bash -c 'python core_secrets.py && echo "--- Ergebnis ---" && cat "$HOME/.streamlit/secrets.toml"'
```
Expected: `secrets: … geschrieben, 6 Bytes.` gefolgt von `A = 1`.
(Nur der Secrets-Teil wird hier geprüft; `streamlit run` startet einen Server
und wird örtlich nicht aufgerufen.)

- [ ] **Step 8: Vorlage um den Azure-Weg ergänzen**

In `.streamlit/secrets.toml.example` den Kopfkommentar erweitern — die
bestehenden Zeilen bleiben, darunter kommt:

```
# Azure App Service: Diese Datei wird NICHT ins Repo gelegt und auch nicht
# von Hand auf dem Server erzeugt. Sie wird base64-kodiert als ein einziges
# Key-Vault-Secret hinterlegt (streamlit-secrets-toml) und beim Start von
# core_secrets.py wieder als Datei geschrieben.
# Anleitung: docs/BETRIEB-AZURE.md
```

- [ ] **Step 9: Commit**

```bash
git add core_secrets.py test_core_secrets.py startup.sh .streamlit/secrets.toml.example
git commit -m "Zugangsdaten aus der Umgebung als secrets.toml schreiben

Streamlit liest st.secrets nur aus einer Datei, App Service liefert
Einstellungen aber als Umgebungsvariable. core_secrets.py dekodiert die
base64-kodierte secrets.toml und legt sie mit Rechten 600 unter \$HOME an,
bevor startup.sh Streamlit startet.

Base64, weil der Firebase-Schluessel Zeilenumbrueche enthaelt."
```

---

### Task 2: Resource Group, App Service Plan und Web App

Erst die Hülle, ohne Zugangsdaten und ohne Code. Am Ende dieser Task
antwortet die Adresse mit der Azure-Standardseite — und die Abschottung ist
belegt.

**Files:** keine Repository-Änderung. Alle Schritte laufen über die Azure CLI.

**Interfaces:**
- Consumes: nichts.
- Produces: Web App `app-wawa-shiftplaner` in `rg-wawa-web`, erreichbar unter
  `https://app-wawa-shiftplaner.azurewebsites.net`. Ihre systemseitige
  Identität (Objekt-ID) wird in Task 3 gebraucht.

- [ ] **Step 1: Namensverfügbarkeit prüfen**

```bash
az rest --method post \
  --url "https://management.azure.com/subscriptions/6e87d817-7495-412d-93e4-fad170123e80/providers/Microsoft.Web/checknameavailability?api-version=2023-12-01" \
  --body '{"name":"app-wawa-shiftplaner","type":"Microsoft.Web/sites"}' -o json
```
Expected: `"nameAvailable": true`.
Ist der Name vergeben, `app-wawa-shiftplaner-hzb` versuchen und den gewählten
Namen ab hier durchgängig verwenden — auch in Task 3, 4, 5 und 6.

- [ ] **Step 2: Resource Group anlegen**

```bash
az group create --name rg-wawa-web --location westeurope -o table
```
Expected: `Succeeded`.

- [ ] **Step 3: App Service Plan anlegen**

```bash
az appservice plan create \
  --name asp-wawa-web \
  --resource-group rg-wawa-web \
  --location westeurope \
  --is-linux \
  --sku B1 \
  --number-of-workers 1 \
  -o table
```
Expected: Plan mit `Sku B1`, `Kind linux`.

- [ ] **Step 4: Tarif und Instanzzahl belegen**

```bash
az appservice plan show -g rg-wawa-web -n asp-wawa-web \
  --query "{sku:sku.name,capacity:sku.capacity,linux:reserved,region:location}" -o json
```
Expected: `{"sku":"B1","capacity":1,"linux":true,"region":"westeurope"}`.
Weicht `capacity` von 1 ab, mit `az appservice plan update … --number-of-workers 1` korrigieren (Risiko R2 der Spec).

- [ ] **Step 5: Web App anlegen**

```bash
az webapp create \
  --name app-wawa-shiftplaner \
  --resource-group rg-wawa-web \
  --plan asp-wawa-web \
  --runtime "PYTHON|3.14" \
  -o table
```
Expected: `Succeeded`, `state: Running`.

- [ ] **Step 6: Abschottung belegen — dieser Schritt ist der Kern der Spec**

```bash
echo "--- VNet-Integration (muss null / leer sein) ---"
az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query "virtualNetworkSubnetId" -o tsv
az webapp vnet-integration list -g rg-wawa-web -n app-wawa-shiftplaner -o json

echo "--- kein VNet in der neuen Gruppe ---"
az network vnet list -g rg-wawa-web -o json

echo "--- kein Peering am Hermes-VNet ---"
az network vnet peering list -g rg-hermes --vnet-name vm-hermesVNET -o json
```
Expected: erste Ausgabe leer, danach dreimal `[]`.
**Schlägt eine dieser Prüfungen fehl, wird nicht weitergearbeitet, sondern gemeldet.**

- [ ] **Step 7: Erreichbarkeit der Hülle prüfen**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://app-wawa-shiftplaner.azurewebsites.net
```
Expected: `200` oder `403`/`503` mit Azure-Standardseite — die App hat noch
keinen Code. Ein Verbindungsfehler dagegen ist ein Problem.

- [ ] **Step 8: Kosten gegenprüfen**

```bash
az appservice plan show -g rg-wawa-web -n asp-wawa-web --query "sku" -o json
```
Expected: `B1`. Zur Erinnerung: 0,0155 €/h ≈ 11,32 €/Monat. Steht dort
versehentlich `P1v3` oder Ähnliches, sofort mit
`az appservice plan update -g rg-wawa-web -n asp-wawa-web --sku B1` korrigieren.

---

### Task 3: Key Vault, Identität und Zugangsdaten

**Files:** keine Repository-Änderung.

**Interfaces:**
- Consumes: Web App aus Task 2.
- Produces: Key-Vault-Secret `streamlit-secrets-toml` und die App-Einstellung
  `STREAMLIT_SECRETS_B64`, die `core_secrets.main()` aus Task 1 liest.

- [ ] **Step 1: Key Vault anlegen**

```bash
az keyvault create \
  --name kv-wawa-web-hzb \
  --resource-group rg-wawa-web \
  --location westeurope \
  --enable-rbac-authorization true \
  --retention-days 90 \
  -o table
```
Expected: `Succeeded`. Vorläufiges Löschen ist bei neuen Vaults voreingestellt
(Risiko R5 der Spec). Ist der Name weltweit vergeben, `kv-wawa-web-hzb2`
verwenden und ab hier durchgängig beibehalten.

- [ ] **Step 2: Löschschutz einschalten**

```bash
az keyvault update -n kv-wawa-web-hzb -g rg-wawa-web --enable-purge-protection true -o none
az keyvault show -n kv-wawa-web-hzb -g rg-wawa-web \
  --query "{softDelete:properties.enableSoftDelete,purge:properties.enablePurgeProtection,rbac:properties.enableRbacAuthorization}" -o json
```
Expected: alle drei `true`.

- [ ] **Step 3: Eigene Schreibrechte auf den Vault**

```bash
MEINE_ID=$(az ad signed-in-user show --query id -o tsv)
VAULT_ID=$(az keyvault show -n kv-wawa-web-hzb -g rg-wawa-web --query id -o tsv)
az role assignment create --assignee-object-id "$MEINE_ID" --assignee-principal-type User \
  --role "Key Vault Secrets Officer" --scope "$VAULT_ID" -o table
```
Expected: Rollenzuweisung angelegt. (Bei RBAC-Vaults reicht Besitz der
Subscription nicht aus, um Secrets zu setzen.)

- [ ] **Step 4: Managed Identity der Web App einschalten**

```bash
az webapp identity assign -g rg-wawa-web -n app-wawa-shiftplaner -o json
```
Expected: JSON mit `principalId`. Diese ID im nächsten Schritt verwenden.

- [ ] **Step 5: Der Web App ausschließlich Lesezugriff geben**

```bash
APP_ID=$(az webapp identity show -g rg-wawa-web -n app-wawa-shiftplaner --query principalId -o tsv)
VAULT_ID=$(az keyvault show -n kv-wawa-web-hzb -g rg-wawa-web --query id -o tsv)
az role assignment create --assignee-object-id "$APP_ID" --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" --scope "$VAULT_ID" -o table
```
Expected: Rolle `Key Vault Secrets User`, Geltungsbereich nur dieser Vault
(Risiko R6 der Spec).

- [ ] **Step 6: Vorlage für die Zugangsdaten im Scratchpad ablegen**

Aus `.streamlit/secrets.toml.example` eine ausfüllbare Datei erzeugen — im
Scratchpad, **nicht** im Repository:

```bash
SP="$SCRATCHPAD"   # das sitzungseigene Scratchpad-Verzeichnis
cp .streamlit/secrets.toml.example "$SP/secrets.toml"
echo "Bitte ausfuellen: $SP/secrets.toml"
```

Danach **anhalten** und die Werte anfordern. Die Datei enthält nach dem
Ausfüllen: `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_EMAIL_RECEIVER`,
`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
`ENABLE_SMS_REMINDER`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_PHONE_NUMBER` sowie den vollständigen Abschnitt `[firebase]`.
Am schnellsten geht es, wenn die bereits gepflegten Werte aus
Streamlit Community Cloud (Settings → Secrets) unverändert übernommen werden.

- [ ] **Step 7: Ausgefüllte Datei prüfen, ohne Werte auszugeben**

```bash
python - <<'PY'
import os, pathlib, tomllib
p = pathlib.Path(os.environ["SCRATCHPAD"]) / "secrets.toml"
d = tomllib.loads(p.read_text(encoding="utf-8"))
noetig = ["ADMIN_EMAIL","ADMIN_PASSWORD","ADMIN_EMAIL_RECEIVER","SMTP_SERVER",
          "SMTP_PORT","SMTP_USER","SMTP_PASSWORD","ENABLE_SMS_REMINDER"]
fehlt = [k for k in noetig if not str(d.get(k, "")).strip()]
fb = d.get("firebase", {})
fb_noetig = ["type","project_id","private_key_id","private_key","client_email","token_uri"]
fehlt += [f"firebase.{k}" for k in fb_noetig if not str(fb.get(k, "")).strip()]
print("Syntax in Ordnung. Fehlend:", fehlt if fehlt else "nichts")
print("Privater Schluessel plausibel:", "BEGIN" in str(fb.get("private_key", "")))
PY
```
Expected: `Fehlend: nichts` und `Privater Schluessel plausibel: True`.
Die Werte selbst werden nicht ausgegeben.

- [ ] **Step 8: Base64 erzeugen und in den Vault legen**

Die Kodierung geschieht über eine Datei, damit kein Zugangswert in der
Kommandozeile und damit in der Prozessliste oder im Protokoll auftaucht.

```bash
base64 -w0 "$SCRATCHPAD/secrets.toml" > "$SCRATCHPAD/secrets.b64"
az keyvault secret set \
  --vault-name kv-wawa-web-hzb \
  --name streamlit-secrets-toml \
  --file "$SCRATCHPAD/secrets.b64" \
  --encoding utf-8 \
  --query "{name:name,version:id,enabled:attributes.enabled}" -o json
```
Expected: JSON mit Namen und Versions-URL. **Kein Secret-Wert in der Ausgabe.**

- [ ] **Step 9: Rückweg belegen und lokale Dateien löschen**

```bash
az keyvault secret show --vault-name kv-wawa-web-hzb --name streamlit-secrets-toml \
  --query "length(value)" -o tsv
rm -f "$SCRATCHPAD/secrets.toml" "$SCRATCHPAD/secrets.b64"
ls "$SCRATCHPAD" | grep -c secrets || echo "0 - lokale Dateien geloescht"
```
Expected: eine Längenangabe (nicht der Wert), danach die Bestätigung, dass
nichts mehr lokal liegt.

- [ ] **Step 10: App-Einstellung als Key-Vault-Verweis setzen**

```bash
SECRET_URI=$(az keyvault secret show --vault-name kv-wawa-web-hzb --name streamlit-secrets-toml --query id -o tsv)
# Version abschneiden, damit die App nach einer Rotation automatisch die neueste zieht.
SECRET_URI_OHNE_VERSION="${SECRET_URI%/*}"
az webapp config appsettings set -g rg-wawa-web -n app-wawa-shiftplaner --settings \
  "STREAMLIT_SECRETS_B64=@Microsoft.KeyVault(SecretUri=${SECRET_URI_OHNE_VERSION}/)" \
  -o none
az webapp config appsettings list -g rg-wawa-web -n app-wawa-shiftplaner \
  --query "[?name=='STREAMLIT_SECRETS_B64'].{name:name,value:value}" -o json
```
Expected: Der Wert zeigt den `@Microsoft.KeyVault(...)`-Verweis, **nicht** die
Zugangsdaten.

- [ ] **Step 11: Auflösung des Verweises prüfen**

```bash
az webapp config appsettings list -g rg-wawa-web -n app-wawa-shiftplaner -o none
az rest --method get --url "https://management.azure.com$(az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query id -o tsv)/configreferences/appsettings?api-version=2023-12-01" \
  --query "value[].{name:name,status:properties.status}" -o table
```
Expected: `STREAMLIT_SECRETS_B64` mit Status `Resolved`.
Steht dort `AccessToKeyVaultDenied`, fehlt die Rollenzuweisung aus Step 5 —
sie braucht gelegentlich einige Minuten, bis sie greift. Dann erneut prüfen.

---

### Task 4: Laufzeitkonfiguration und erste Auslieferung von Hand

**Files:** keine Repository-Änderung.

**Interfaces:**
- Consumes: Task 1 (`startup.sh`, `core_secrets.py` im Repository), Task 2, Task 3.
- Produces: laufende Anwendung unter der Azure-Adresse.

- [ ] **Step 1: Alle Laufzeiteinstellungen setzen**

```bash
az webapp config set -g rg-wawa-web -n app-wawa-shiftplaner \
  --always-on true \
  --web-sockets-enabled true \
  --min-tls-version 1.2 \
  --ftps-state Disabled \
  --number-of-workers 1 \
  --startup-file "bash startup.sh" \
  -o none

az webapp update -g rg-wawa-web -n app-wawa-shiftplaner --https-only true -o none

az webapp config appsettings set -g rg-wawa-web -n app-wawa-shiftplaner \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=1 -o none
```

- [ ] **Step 2: Einstellungen belegen**

```bash
az webapp config show -g rg-wawa-web -n app-wawa-shiftplaner \
  --query "{alwaysOn:alwaysOn,webSockets:webSocketsEnabled,tls:minTlsVersion,ftps:ftpsState,workers:numberOfWorkers,start:appCommandLine,runtime:linuxFxVersion}" -o json
az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query "httpsOnly" -o tsv
```
Expected: `alwaysOn true`, `webSockets true`, `tls 1.2`, `ftps Disabled`,
`workers 1`, `start "bash startup.sh"`, `runtime "PYTHON|3.14"`, `httpsOnly true`.
Jede Abweichung hier führt zu einem Fehlerbild, das später schwer zu deuten ist
— deshalb vor dem Deployment prüfen.

- [ ] **Step 3: Protokollierung einschalten, damit der erste Start nachvollziehbar ist**

```bash
az webapp log config -g rg-wawa-web -n app-wawa-shiftplaner \
  --application-logging filesystem --docker-container-logging filesystem --level information -o none
```

- [ ] **Step 4: Code ausliefern**

Vom Wurzelverzeichnis des Repositories, auf dem Branch mit den Änderungen aus Task 1:

```bash
git ls-files -z | xargs -0 zip -q "$SCRATCHPAD/app.zip"
az webapp deploy -g rg-wawa-web -n app-wawa-shiftplaner \
  --src-path "$SCRATCHPAD/app.zip" --type zip --async false -o table
```
Expected: `Deployment successful`. Der Bau dauert einige Minuten, weil
`requirements.txt` vollständig installiert wird (pandas, plotly, grpcio).

`git ls-files` sorgt dafür, dass nur versionierte Dateien mitgehen — eine
örtlich vorhandene `.streamlit/secrets.toml` bliebe damit zuverlässig draußen.

- [ ] **Step 5: Start beobachten**

```bash
az webapp log tail -g rg-wawa-web -n app-wawa-shiftplaner --provider application
```
Expected: die Zeile `secrets: /home/.streamlit/secrets.toml geschrieben, <n> Bytes.`
gefolgt von Streamlits `You can now view your Streamlit app`.
Erscheint stattdessen `secrets: Der uebergebene Wert ist leer.`, greift der
Key-Vault-Verweis nicht — zurück zu Task 3, Step 11.

- [ ] **Step 6: Antwort prüfen**

```bash
curl -sS -o /dev/null -w "HTTPS: %{http_code}\n" https://app-wawa-shiftplaner.azurewebsites.net
curl -sS -o /dev/null -w "HTTP:  %{http_code} -> %{redirect_url}\n" http://app-wawa-shiftplaner.azurewebsites.net
```
Expected: `HTTPS: 200`, `HTTP: 301` mit Umleitung auf `https://`
(Abnahmekriterien 1 und 2 der Spec).

- [ ] **Step 7: Abschottung im laufenden Betrieb belegen**

Private Adresse der Hermes-VM ermitteln und vom Webserver aus prüfen:

```bash
HERMES_IP=$(az vm show -g rg-hermes -n vm-hermes -d --query privateIps -o tsv)
echo "Hermes privat: $HERMES_IP"
az webapp ssh -g rg-wawa-web -n app-wawa-shiftplaner \
  --command "timeout 5 bash -c '</dev/tcp/${HERMES_IP}/22' && echo ERREICHBAR || echo 'nicht erreichbar - richtig so'"
```
Expected: `nicht erreichbar - richtig so` (Abnahmekriterium 6 der Spec).
Steht dort `ERREICHBAR`, sofort anhalten und melden.

Bietet `az webapp ssh` in dieser Umgebung kein `--command`, den Test über die
Kudu-Konsole im Portal ausführen: **App Service → Development Tools → SSH**.

- [ ] **Step 8: Neustart überstehen**

```bash
az webapp restart -g rg-wawa-web -n app-wawa-shiftplaner -o none
sleep 90
curl -sS -o /dev/null -w "%{http_code}\n" https://app-wawa-shiftplaner.azurewebsites.net
```
Expected: `200` (Abnahmekriterium 7 — belegt, dass der Secrets-Abruf bei jedem
Start funktioniert, nicht nur beim ersten).

- [ ] **Step 9: Fachlicher Durchstich im Browser**

Von Hand, gegen dieselbe Firestore-Datenbank wie bisher:
Anmelden, Schicht buchen, Buchung stornieren, Rangliste mit Diagramm öffnen,
ICS-Datei exportieren, Dark/Light-Umschaltung prüfen (Abnahmekriterium 3).

Die parallel laufende Streamlit-Community-Cloud-Instanz bleibt an. Eine dort
angelegte Buchung muss in Azure sichtbar sein und umgekehrt — das belegt,
dass beide auf derselben Datenbasis arbeiten.

- [ ] **Step 10: Zwischenstand festhalten**

Kein Commit nötig (keine Repository-Änderung). Ergebnis der Abnahmekriterien
1, 2, 3, 6 und 7 notieren; sie werden in Task 6 zusammengeführt.

---

### Task 5: Auslieferung über GitHub Actions

**Files:**
- Create: `.github/workflows/deploy-azure.yml`

**Interfaces:**
- Consumes: Web App aus Task 2, bestehende `tests.yml`.
- Produces: automatische Auslieferung bei Push auf `main`.

- [ ] **Step 1: Anwendungsregistrierung für OIDC anlegen**

```bash
APP_JSON=$(az ad app create --display-name "gh-deploy-wawa-shiftplaner" -o json)
APP_ID=$(echo "$APP_JSON" | python -c "import json,sys; print(json.load(sys.stdin)['appId'])")
az ad sp create --id "$APP_ID" -o none
echo "AZURE_CLIENT_ID = $APP_ID"
```
Expected: eine Client-ID. Diese ist **kein Geheimnis** — sie darf in
GitHub-Variablen stehen.

- [ ] **Step 2: Föderierte Anmeldedaten für den Branch `main` hinterlegen**

```bash
cat > "$SCRATCHPAD/fic.json" <<'JSON'
{
  "name": "gh-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:stemplinger11-Streamlit/WaWashiftplanner2.0:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}
JSON
az ad app federated-credential create --id "$APP_ID" --parameters "$SCRATCHPAD/fic.json" -o table
```
Expected: Anmeldedaten angelegt. Damit kann **nur** ein Lauf aus diesem
Repository auf diesem Branch ein Token bekommen — es gibt kein langlebiges
Geheimnis bei GitHub.

- [ ] **Step 3: Rechte auf genau diese Web App, nicht mehr**

```bash
SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)
SITE_ID=$(az webapp show -g rg-wawa-web -n app-wawa-shiftplaner --query id -o tsv)
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
  --role "Website Contributor" --scope "$SITE_ID" -o table
```
Expected: Rolle nur auf die Web App, nicht auf die Subscription.

- [ ] **Step 4: Workflow anlegen**

Create `.github/workflows/deploy-azure.yml`:

```yaml
name: Deploy nach Azure

# Nur nach gruenem Test ausliefern. Der Ladetest test_app_smoke.py prueft
# die App gegen die echten Paketversionen und faengt genau die Paketbrueche
# ab, die sonst erst in Azure auffallen.
on:
  workflow_run:
    workflows: ["Tests"]
    types: [completed]
    branches: [main]
  workflow_dispatch:

permissions:
  id-token: write   # fuer die Anmeldung per OIDC
  contents: read

concurrency:
  group: deploy-azure
  cancel-in-progress: false

jobs:
  deploy:
    # Bei rotem Test wird nicht ausgeliefert.
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    environment: produktion

    steps:
      - uses: actions/checkout@v4
        with:
          ref: main

      - name: An Azure anmelden
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Paket schnueren
        # Nur versionierte Dateien - eine oertliche secrets.toml koennte so
        # gar nicht mitgehen.
        run: git ls-files -z | xargs -0 zip -q app.zip

      - name: Ausliefern
        uses: azure/webapps-deploy@v3
        with:
          app-name: app-wawa-shiftplaner
          package: app.zip

      - name: Erreichbarkeit pruefen
        run: |
          for i in $(seq 1 20); do
            code=$(curl -sS -o /dev/null -w "%{http_code}" https://app-wawa-shiftplaner.azurewebsites.net || true)
            echo "Versuch $i: HTTP $code"
            if [ "$code" = "200" ]; then exit 0; fi
            sleep 15
          done
          echo "Die App antwortet nach dem Deployment nicht mit 200." >&2
          exit 1
```

- [ ] **Step 5: GitHub-Variablen setzen**

```bash
gh variable set AZURE_CLIENT_ID       --repo stemplinger11-Streamlit/WaWashiftplanner2.0 --body "$APP_ID"
gh variable set AZURE_TENANT_ID       --repo stemplinger11-Streamlit/WaWashiftplanner2.0 --body "78d975d6-0408-4e64-a71a-6f34f8596fec"
gh variable set AZURE_SUBSCRIPTION_ID --repo stemplinger11-Streamlit/WaWashiftplanner2.0 --body "6e87d817-7495-412d-93e4-fad170123e80"
gh variable list --repo stemplinger11-Streamlit/WaWashiftplanner2.0
```
Expected: drei Variablen. Es sind **Variablen**, keine Secrets — keiner der
drei Werte ist geheim.

Ist die GitHub-CLI nicht angemeldet, die Werte im Portal unter
**Settings → Secrets and variables → Actions → Variables** eintragen.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/deploy-azure.yml
git commit -m "Nach gruenem Test automatisch nach Azure ausliefern

Der Workflow haengt an der bestehenden Test-Pipeline und laeuft nur, wenn
sie erfolgreich war. Die Anmeldung erfolgt per OIDC mit foederierten
Anmeldedaten, es liegt also kein langlebiges Geheimnis bei GitHub. Die
Rolle Website Contributor gilt nur fuer diese eine Web App."
```

- [ ] **Step 7: Workflow von Hand auslösen und prüfen**

```bash
gh workflow run "Deploy nach Azure" --repo stemplinger11-Streamlit/WaWashiftplanner2.0
sleep 30
gh run list --repo stemplinger11-Streamlit/WaWashiftplanner2.0 --workflow "Deploy nach Azure" --limit 1
```
Expected: Lauf endet mit `success`, der Schritt „Erreichbarkeit pruefen"
meldet `HTTP 200`.

---

### Task 6: Betriebsanleitung und Abnahme

**Files:**
- Create: `docs/BETRIEB-AZURE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: alles aus Task 1 bis 5.
- Produces: nachvollziehbare Abnahme aller zehn Kriterien der Spec.

- [ ] **Step 1: Betriebsanleitung schreiben**

Create `docs/BETRIEB-AZURE.md` mit genau diesen Abschnitten:

1. **Wo die App läuft** — Resource Group `rg-wawa-web`, West Europe, Web App
   `app-wawa-shiftplaner`, Plan `asp-wawa-web` (B1, ~11,32 €/Monat), Adresse
   `https://app-wawa-shiftplaner.azurewebsites.net`.
2. **Zugangsdaten ändern** — im Portal unter
   *Key Vaults → kv-wawa-web-hzb → Objects → Secrets → streamlit-secrets-toml*.
   Ausdrücklicher Hinweis: Der Wert ist base64-kodiert; im Portal lässt er sich
   ansehen, aber nicht sinnvoll bearbeiten. Der vorgesehene Weg ist:
   ```bash
   # secrets.toml oertlich pflegen, dann:
   base64 -w0 secrets.toml > secrets.b64
   az keyvault secret set --vault-name kv-wawa-web-hzb --name streamlit-secrets-toml \
     --file secrets.b64 --encoding utf-8
   az webapp restart -g rg-wawa-web -n app-wawa-shiftplaner
   rm secrets.toml secrets.b64
   ```
   Die App zieht die neueste Version beim Neustart, weil der Verweis keine
   Version festnagelt.
3. **Protokolle lesen** —
   `az webapp log tail -g rg-wawa-web -n app-wawa-shiftplaner`.
4. **Wenn es zu langsam wird** —
   `az appservice plan update -g rg-wawa-web -n asp-wawa-web --sku B2`
   (22,56 €/Monat, kein Ausfall, kein erneutes Deployment). Die Instanzzahl
   bleibt bei 1, weil Streamlit den Sitzungszustand im Prozess hält.
5. **Eigene Domain ergänzen** —
   `az webapp config hostname add`, danach
   `az webapp config ssl create --hostname <domain>` für das kostenlose
   verwaltete Zertifikat. Voraussetzung ist ein CNAME beim DNS-Anbieter.
6. **Was niemals getan wird** — für diese Web App keine VNet-Integration
   einschalten und sie nicht in `vm-hermesVNET` aufnehmen. Begründung samt
   `AllowVnetInBound` aus der Spec in zwei Sätzen wiederholen.

- [ ] **Step 2: README ergänzen**

In `README.md` nach dem Abschnitt „Lokal starten" einen kurzen Abschnitt
„Betrieb auf Azure" einfügen: drei bis fünf Zeilen mit Adresse, Tarif,
monatlichen Kosten und Verweis auf `docs/BETRIEB-AZURE.md`. Die bestehende
Tabelle im Abschnitt „Aufbau" um die Zeilen für `core_secrets.py`,
`startup.sh` und `docs/BETRIEB-AZURE.md` erweitern.

- [ ] **Step 3: Alle zehn Abnahmekriterien am Stück durchlaufen**

```bash
APP=app-wawa-shiftplaner
RG=rg-wawa-web

echo "1) HTTPS:  $(curl -sS -o /dev/null -w '%{http_code}' https://$APP.azurewebsites.net)"
echo "2) HTTP:   $(curl -sS -o /dev/null -w '%{http_code}' http://$APP.azurewebsites.net)"
echo "4) Subnet: $(az webapp show -g $RG -n $APP --query virtualNetworkSubnetId -o tsv):leer-erwartet"
echo "5) VNetInt:$(az webapp vnet-integration list -g $RG -n $APP -o tsv | wc -l):0-erwartet"
echo "9) AlwaysOn/WebSockets:"
az webapp config show -g $RG -n $APP --query "{alwaysOn:alwaysOn,ws:webSocketsEnabled,workers:numberOfWorkers}" -o json
echo "10) Klartext im Repo:"
git grep -nIE "(BEGIN [A-Z ]*PRIVATE KEY|SG\.|AC[0-9a-f]{32}|xox[bp]-)" -- . ':!docs/' || echo "  nichts gefunden"
az webapp config appsettings list -g $RG -n $APP --query "[].{n:name,v:value}" -o json
```
Expected: 1 = `200`, 2 = `301`, 4 leer, 5 = `0`, `alwaysOn true`,
`ws true`, `workers 1`, kein Klartextfund, und in den App-Einstellungen steht
bei `STREAMLIT_SECRETS_B64` nur der `@Microsoft.KeyVault(...)`-Verweis.

Kriterium 3 (fachlicher Durchstich), 6 (Hermes nicht erreichbar), 7 (Neustart)
und 8 (roter Test liefert nicht aus) stammen aus Task 4 Step 7/8/9 und Task 5
Step 7; Ergebnisse hier zusammenführen.

- [ ] **Step 4: Kriterium 8 gezielt belegen**

Auf einem Wegwerf-Branch einen absichtlich fehlschlagenden Test einbauen, Pull
Request gegen `main` öffnen, prüfen dass „Tests" rot ist und „Deploy nach
Azure" **nicht** läuft, danach Branch und Pull Request verwerfen. Nichts davon
wird nach `main` gebracht.

- [ ] **Step 5: Tatsächliche Kosten prüfen**

```bash
cat > "$SCRATCHPAD/costq.json" <<'JSON'
{"type":"ActualCost","timeframe":"MonthToDate","dataset":{"granularity":"None",
 "aggregation":{"totalCost":{"name":"Cost","function":"Sum"}},
 "grouping":[{"type":"Dimension","name":"ResourceGroupName"}]}}
JSON
az rest --method post \
  --url "https://management.azure.com/subscriptions/6e87d817-7495-412d-93e4-fad170123e80/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
  --body @"$SCRATCHPAD/costq.json" -o json
```
Expected: `rg-wawa-web` taucht mit einem kleinen Betrag auf. Die API antwortet
zeitweise mit HTTP 429 — dann später erneut versuchen, das ist kein Fehler der
Umsetzung. Der Wert wächst über den Monat auf rund 11,40 € an.

- [ ] **Step 6: Commit**

```bash
git add docs/BETRIEB-AZURE.md README.md
git commit -m "Betriebsanleitung fuer den Azure-Betrieb

Wo die App laeuft, wie Zugangsdaten nachgetragen werden, wie der Tarif
gewechselt wird und warum diese Web App niemals VNet-Integration erhaelt."
```

- [ ] **Step 7: Branch zusammenführen**

Die Skill `superpowers:finishing-a-development-branch` anwenden. Vorher prüfen,
dass die Testpipeline auf dem Branch grün ist.

---

## Offen, bewusst nicht Teil dieses Plans

- **Abschaltung der Streamlit-Community-Cloud-Instanz.** Sie läuft ausdrücklich
  parallel weiter. Der Zeitpunkt wird gesondert entschieden (Risiko R4 der Spec).
- **Anbindung der externen Domain**, sobald sie vorliegt. Das Vorgehen steht in
  `docs/BETRIEB-AZURE.md`, Abschnitt 5.
