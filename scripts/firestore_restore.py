"""
Spielt eine mit firestore_backup.py erstellte Sicherung zurueck.

Standardmaessig laeuft das Skript als Trockenlauf und veraendert NICHTS.
Erst mit --schreiben wird tatsaechlich geschrieben.

Aufruf:
    python scripts/firestore_restore.py backups/firestore_20260902.json
    python scripts/firestore_restore.py <datei> --nur users --schreiben
    python scripts/firestore_restore.py <datei> --schreiben --loeschen-fehlende

Ohne --loeschen-fehlende werden vorhandene Dokumente ueberschrieben und
zusaetzliche Dokumente in der Datenbank in Ruhe gelassen.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from google.cloud import firestore

sys.path.insert(0, str(Path(__file__).resolve().parent))
from firestore_backup import lade_credentials, COLLECTIONS  # noqa: E402

BATCH_GROESSE = 400  # Firestore erlaubt 500 Operationen pro Batch


def entserialisieren(wert):
    """Kehrt die Umwandlung aus firestore_backup.serialisierbar um."""
    if isinstance(wert, dict):
        typ = wert.get('__typ__')
        if typ == 'datetime':
            return datetime.fromisoformat(wert['wert'])
        if typ == 'bytes':
            return bytes.fromhex(wert['wert'])
        if typ == 'geo':
            return firestore.GeoPoint(wert['lat'], wert['lng'])
        if typ == 'ref':
            return wert['wert']  # als Pfad-String belassen
        return {k: entserialisieren(v) for k, v in wert.items()}
    if isinstance(wert, list):
        return [entserialisieren(v) for v in wert]
    return wert


def main():
    parser = argparse.ArgumentParser(description="Firestore-Sicherung zurueckspielen")
    parser.add_argument('datei', help="Pfad zur Sicherungsdatei")
    parser.add_argument('--key', help="Pfad zu einer Service-Account-JSON")
    parser.add_argument('--nur', nargs='+', choices=COLLECTIONS,
                        help="Nur diese Collections zurueckspielen")
    parser.add_argument('--schreiben', action='store_true',
                        help="Tatsaechlich schreiben (ohne dies: Trockenlauf)")
    parser.add_argument('--loeschen-fehlende', action='store_true',
                        help="Dokumente loeschen, die in der Sicherung fehlen")
    args = parser.parse_args()

    sicherung = json.loads(Path(args.datei).read_text(encoding='utf-8'))
    collections = args.nur or list(sicherung['collections'].keys())

    print(f"Sicherung vom {sicherung.get('erstellt_am', 'unbekannt')}")
    print(f"Projekt:      {sicherung.get('projekt', 'unbekannt')}")
    print(f"Modus:        {'SCHREIBEN' if args.schreiben else 'Trockenlauf (keine Änderung)'}\n")

    creds, project = lade_credentials(args.key)
    db = (firestore.Client(credentials=creds, project=project) if creds
          else firestore.Client())

    if args.schreiben:
        ziel = project or getattr(db, 'project', 'unbekannt')
        print(f"⚠️  Es wird in das Projekt '{ziel}' geschrieben.")
        if input("    Zum Fortfahren 'JA' eingeben: ").strip() != 'JA':
            print("Abgebrochen.")
            return 1
        print()

    for name in collections:
        dokumente = sicherung['collections'].get(name, {})
        vorhanden = {d.id for d in db.collection(name).stream()}
        neu = set(dokumente) - vorhanden
        ueberschrieben = set(dokumente) & vorhanden
        fehlend = vorhanden - set(dokumente)

        print(f"{name}:")
        print(f"  {len(neu):5d} neu, {len(ueberschrieben):5d} überschrieben, "
              f"{len(fehlend):5d} nur in der Datenbank")

        if not args.schreiben:
            continue

        batch = db.batch()
        anzahl = 0
        for doc_id, daten in dokumente.items():
            batch.set(db.collection(name).document(doc_id), entserialisieren(daten))
            anzahl += 1
            if anzahl % BATCH_GROESSE == 0:
                batch.commit()
                batch = db.batch()

        if args.loeschen_fehlende:
            for doc_id in fehlend:
                batch.delete(db.collection(name).document(doc_id))
                anzahl += 1
                if anzahl % BATCH_GROESSE == 0:
                    batch.commit()
                    batch = db.batch()
        batch.commit()
        print(f"  ✅ {anzahl} Operationen geschrieben")

    if not args.schreiben:
        print("\nTrockenlauf beendet – es wurde nichts verändert.")
        print("Zum tatsächlichen Zurückspielen: --schreiben ergänzen.")
    else:
        print("\n✅ Zurückspielen abgeschlossen.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
