"""Setup flow logic (no Streamlit dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ssdv.connectors import list_connectors, load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.ingest.client_chart import parse_tally_ledger_masters, saved_client_chart
from ssdv.ingest.generic import IngestResult
from ssdv.ingest.suggest import (
    LedgerReview,
    confirm_map,
    effective_map,
    load_source_lines,
    needs_review,
    review_ledgers,
)
from ssdv.models import IngestMeta
from ssdv.officemitra.firm import discover_vaults, voucher_count
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
    ]


def friendly_status(status: str) -> str:
    return {
        "ready": "Ready",
        "export_csv": "Upload export file",
    }.get(status, status)


def vault_voucher_count(db_path: Path) -> int:
    return voucher_count(db_path)


def vault_has_data(db_path: Path | None = None) -> bool:
    if db_path is not None:
        return vault_voucher_count(db_path) > 0
    if discover_vaults():
        return True
    return vault_voucher_count(_CONNECT_VAULT) > 0


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
    db_path: Path | None = None,
    client_chart: Path | None = None,
) -> IngestResult:
    return load_into_vault(
        db_path or _CONNECT_VAULT,
        source=source,
        journals=journals,
        account_map=account_map,
        company_name=company_name,
        force=force,
        tally_host=tally_host,
        client_chart=client_chart,
    )


@dataclass(frozen=True)
class MappingReview:
    rows: list[LedgerReview]
    base_map: dict[str, str]

    @property
    def pending(self) -> list[LedgerReview]:
        return needs_review(self.rows)


def review_mapping(
    *,
    source: str,
    journals: Path,
    account_map: Path | None,
    db_path: Path,
    client_chart: Path | None = None,
) -> MappingReview:
    """Read the export only. Says which ledgers still need a person to confirm a code."""
    base = effective_map(db_path, account_map)
    chart = saved_client_chart(db_path, client_chart)
    rows = review_ledgers(load_source_lines(source, journals), base, client_chart=chart)
    return MappingReview(rows=rows, base_map=base)


def pull_tally_chart(host: str) -> Path | None:
    """Pull TallyPrime's ledger list (names and groups) into a temp chart CSV.

    Optional: returns None when TallyPrime does not answer, so the import still works.
    """
    import tempfile

    from ssdv.connectors.tally_http import pull_ledger_masters_xml
    from ssdv.ingest.client_chart import save_client_chart

    try:
        chart = parse_tally_ledger_masters(pull_ledger_masters_xml(host, timeout=120))
    except Exception:  # noqa: BLE001 — the chart is a helper, never a blocker
        return None
    if not chart:
        return None
    folder = Path(tempfile.mkdtemp(prefix="ssdv_setup_"))
    return save_client_chart(folder / "tally.sqlite", chart)


def save_confirmed_map(db_path: Path, base_map: dict[str, str], choices: dict[str, str]) -> Path:
    return confirm_map(db_path, base_map, choices)


def pull_tally_daybook(host: str) -> Path:
    """Pull the live TallyPrime DayBook into a temp file so it can be reviewed first."""
    import tempfile

    from ssdv.connectors.base import ConnectorError
    from ssdv.connectors.tally_http import pull_daybook_xml

    xml_bytes = pull_daybook_xml(host, timeout=180)
    if not xml_bytes or len(xml_bytes) < 50:
        raise ConnectorError(
            "TallyPrime returned an empty or very short response. "
            "Check that the company has vouchers in the requested date range."
        )
    folder = Path(tempfile.mkdtemp(prefix="ssdv_setup_"))
    path = folder / "daybook.xml"
    path.write_bytes(xml_bytes)
    return path


def connect_vault_path() -> Path:
    return _CONNECT_VAULT
