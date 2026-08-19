"""Setup flow logic (no Streamlit dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from ssdv.connectors import list_connectors, load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.ingest.generic import IngestResult
from ssdv.models import IngestMeta, Voucher
from ssdv.paths import connect_db_path
from ssdv.validate import run_gates

_CONNECT_VAULT = connect_db_path()


@dataclass(frozen=True)
class SourceChoice:
    id: str
    title: str
    status: str
    hint: str

    @property
    def is_live(self) -> bool:
        return self.id == "tally-http"

    @property
    def needs_upload(self) -> bool:
        return not self.is_live

    @property
    def upload_journal_types(self) -> list[str]:
        if self.id == "tally":
            return ["xml"]
        return ["csv"]

    @property
    def journal_label(self) -> str:
        if self.id == "tally":
            return "TallyPrime DayBook XML export"
        return "Journal / day-book CSV export"


def source_choices() -> list[SourceChoice]:
    return [
        SourceChoice(item.id, item.title, item.status, item.hint)
        for item in list_connectors()
        if item.id != "mitrabooks"
    ]


def friendly_status(status: str) -> str:
    return {
        "ready": "Ready",
        "export_csv": "Upload export file",
    }.get(status, status)


def vault_voucher_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    engine = make_engine(db_path)
    create_schema(engine)
    with session_scope(engine) as session:
        return int(session.scalar(select(func.count()).select_from(Voucher)) or 0)


def vault_has_data(db_path: Path | None = None) -> bool:
    return vault_voucher_count(db_path or _CONNECT_VAULT) > 0


def ingest_meta_as_of(db_path: Path) -> date | None:
    if not db_path.exists():
        return None
    engine = make_engine(db_path)
    create_schema(engine)
    with session_scope(engine) as session:
        meta = session.get(IngestMeta, 1)
        if meta is not None:
            return meta.last_date
    return None


def validate_vault(db_path: Path, as_of: date) -> tuple[bool, list[str]]:
    engine = make_engine(db_path)
    create_schema(engine)
    with session_scope(engine) as session:
        gates = run_gates(session, as_of)
    errors = [f"{gate.name}: {gate.detail}" for gate in gates if not gate.ok]
    return len(errors) == 0, errors


def run_import(
    *,
    source: str,
    journals: Path | None,
    account_map: Path | None,
    company_name: str | None,
    tally_host: str | None,
    force: bool,
) -> IngestResult:
    return load_into_vault(
        _CONNECT_VAULT,
        source=source,
        journals=journals,
        account_map=account_map,
        company_name=company_name,
        force=force,
        tally_host=tally_host,
    )


def connect_vault_path() -> Path:
    return _CONNECT_VAULT
