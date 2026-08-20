from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ssdv.money import money

_PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running from a PyInstaller / bundled desktop build."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Read-only product files (config, assets, bundled YAML)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(str(meipass))
        return Path(sys.executable).resolve().parent
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def install_dir() -> Path:
    """Folder that contains the app executable (or the repo in dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return resource_root()


def user_data_dir() -> Path:
    """Writable vault, logs, and license files.

    Override with OFFICEMITRA_HOME (useful for tests and portable installs).
    """
    override = os.environ.get("OFFICEMITRA_HOME", "").strip()
    if override:
        path = Path(override).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    if is_frozen():
        if sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / "OfficeMitra"
        elif os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            path = Path(base) / "OfficeMitra"
        else:
            path = Path.home() / ".officemitra"
        path.mkdir(parents=True, exist_ok=True)
        return path
    return resource_root()


def repo_root() -> Path:
    """Product root for config/assets. Prefer resource_root() in new code."""
    return resource_root()


def _vault_dir() -> Path:
    data_dir = user_data_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def default_db_path() -> Path:
    return _vault_dir() / "ssdv.sqlite"


def ingest_db_path() -> Path:
    return _vault_dir() / "ssdv_ingest.sqlite"


def connect_db_path() -> Path:
    return _vault_dir() / "ssdv_connect.sqlite"


def default_dashboard_path() -> Path:
    return _vault_dir() / "mis.html"


def default_board_pack_path() -> Path:
    return _vault_dir() / "board-pack.pdf"


def default_company_path() -> Path:
    return resource_root() / "config" / "companies" / "abc_industrial.yaml"


def coa_path() -> Path:
    return _PACKAGE_DIR / "data" / "coa.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


@lru_cache(maxsize=4)
def load_company(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or default_company_path())


def opening_entries(company: dict[str, Any] | None = None) -> list[tuple[str, object, object]]:
    """Return (account_code, debit, credit) for the opening voucher.

    Side is taken from the chart of accounts: liabilities, equity, income, and
    contra-assets are credits; everything else is a debit.
    """
    cfg = company or load_company()
    coa = {str(row["code"]): row for row in load_yaml(coa_path())["accounts"]}
    credit_types = {"liability", "equity", "income"}
    rows: list[tuple[str, object, object]] = []
    for code, amount in cfg["opening"].items():
        amt = money(amount)
        if amt == 0:
            continue
        code = str(code)
        account = coa.get(code)
        if account is None:
            raise ValueError(f"Opening account {code} is not on the chart of accounts")
        is_credit = account["type"] in credit_types or account.get("subtype") == "contra_asset"
        if is_credit:
            rows.append((code, money(0), amt))
        else:
            rows.append((code, amt, money(0)))
    return rows
