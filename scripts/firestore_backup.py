"""
Vollstaendige Sicherung der Firestore-Datenbank in eine JSON-Datei.

Im Gegensatz zum Export in der App sichert dieses Skript ALLE Felder,
einschliesslich der Passwort-Hashes. Nur damit ist ein Zurueckspielen
moeglich, ohne dass sich die Nutzer neu registrieren muessen.

Aufruf:
    python scripts/firestore_backup.py
    python scripts/firestore_backup.py --out backups/vor_saison.json

Zugangsdaten werden in dieser Reihenfolge gesucht:
    1. --key <pfad-zur-serviceaccount.json>
    2. .streamlit/secrets.toml (Abschnitt [firebase])
    3. Umgebungsvariable GOOGLE_APPLICATION_CREDENTIALS
"""
import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from google.cloud import firestore
from google.oauth2 import service_account

# Diese Collections werden gesichert.
COLLECTIONS = ['users', 'bookings', 'settings', 'archive']

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def lade_credentials(key_path=None):
    """Service-Account-Zugangsdaten ermitteln -> (credentials, project_id)."""
    if key_path:
        info = json.loads(Path(key_path).read_text(encoding='utf-8'))
        return service_account.Credentials.from_service_account_info(info), info['project_id']

    secrets = PROJECT_ROOT / '.streamlit' / 'secrets.toml'
    if secrets.exists():
        with open(secrets, 'rb') as fh:
            data = tomllib.load(fh)
        if 'firebase' in data:
            info = dict(data['firebase'])
            return (service_account.Credentials.from_service_account_info(info),
                    info['project_id'])

    # Fallback: Standard-Credentials der Umgebung
    return None, None


def serialisierbar(wert):
    """Firestore-Typen in JSON-taugliche Werte umwandeln."""
    if isinstance(wert, (datetime, date)):
        return {'__typ__': 'datetime', 'wert': wert.isoformat()}
    if isinstance(wert, dict):
        return {k: serialisierbar(v) for k, v in wert.items()}
    if isinstance(wert, list):
        return [serialisierbar(v) for v in wert]
    if hasattr(wert, 'path'):  # DocumentReference
        return {'__typ__': 'ref', 'wert': wert.path}
    if hasattr(wert, 'latitude'):  # GeoPoint
        return {'__typ__': 'geo', 'lat': wert.latitude, 'lng': wert.longitude}
    if isinstance(wert, bytes):
        return {'__typ__': 'bytes', 'wert': wert.hex()}
    return wert


def main():
    parser = argparse.ArgumentParser(description="Firestore-Datenbank sichern")
    parser.add_argument('--out', help="Zieldatei (Standard: backups/firestore_<zeitstempel>.json)")
    parser.add_argument('--key', help="Pfad zu einer Service-Account-JSON")
    args = parser.parse_args()

    creds, project = lade_credentials(args.key)
    db = (firestore.Client(credentials=creds, project=project) if creds
          else firestore.Client())

    sicherung = {
        'erstellt_am': datetime.now().isoformat(),
        'projekt': project or getattr(db, 'project', 'unbekannt'),
        'collections': {},
    }

    gesamt = 0
    for name in COLLECTIONS:
        dokumente = {}
        for doc in db.collection(name).stream():
            dokumente[doc.id] = serialisierbar(doc.to_dict())
        sicherung['collections'][name] = dokumente
        gesamt += len(dokumente)
        print(f"  {name:12s} {len(dokumente):5d} Dokumente")

    ziel = Path(args.out) if args.out else (
        PROJECT_ROOT / 'backups' /
        f"firestore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(sicherung, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f"\n✅ {gesamt} Dokumente gesichert nach:\n   {ziel}")
    nutzer = sicherung['collections'].get('users', {})
    mit_hash = sum(1 for u in nutzer.values() if u.get('password_hash'))
    print(f"   davon {len(nutzer)} Benutzer, {mit_hash} mit Passwort-Hash")
    if nutzer and mit_hash < len(nutzer):
        print("   ⚠️ Nicht alle Benutzer haben einen Passwort-Hash!")

    print("\n⚠️ Diese Datei enthält Passwort-Hashes und Telefonnummern.")
    print("   Sicher aufbewahren und NICHT ins Repo committen.")


if __name__ == '__main__':
    sys.exit(main())
