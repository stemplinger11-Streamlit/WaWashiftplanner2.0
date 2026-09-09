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
        raise ValueError(
            f"Der uebergebene Wert ist kein gueltiges Base64: {fehler}"
        ) from fehler

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
        print(
            f"secrets: {fehler} Die App startet ohne Zugangsdaten.",
            file=sys.stderr,
        )
        return 1
    except OSError as fehler:
        print(f"secrets: konnte {ziel} nicht schreiben: {fehler}", file=sys.stderr)
        return 1

    print(f"secrets: {ziel} geschrieben, {anzahl} Bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
