from __future__ import annotations

from pathlib import Path

from ssdv.paths import connect_db_path, default_company_path, user_data_dir


def test_user_data_dir_override(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "om-home"
    monkeypatch.setenv("OFFICEMITRA_HOME", str(home))
    assert user_data_dir() == home
    vault = connect_db_path()
    assert vault.parent == home / "data"
    assert vault.parent.is_dir()
    assert default_company_path().is_file()


def test_desktop_entry_script_is_present() -> None:
    from ssdv.officemitra.desktop import _app_script

    assert _app_script().is_file()
