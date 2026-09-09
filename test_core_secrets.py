"""Tests fuer core_secrets - ohne Azure, ohne Streamlit, ohne Netz."""

import base64
import os
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
    inhalt = 'private_key = "-----BEGIN-----\nMIIE\n-----END-----\n"\n'

    core_secrets.write_secrets_file(_b64(inhalt), ziel)

    assert ziel.read_text(encoding="utf-8") == inhalt


@pytest.mark.skipif(os.name == "nt", reason="Windows bildet POSIX-Rechte nicht ab")
def test_datei_ist_nur_fuer_den_eigentuemer_lesbar(tmp_path):
    ziel = tmp_path / "secrets.toml"

    core_secrets.write_secrets_file(_b64("A = 1\n"), ziel)

    modus = stat.S_IMODE(ziel.stat().st_mode)
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


def test_main_ohne_umgebungsvariable_meldet_fehler(tmp_path, monkeypatch):
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
