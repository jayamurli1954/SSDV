from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.connectors.base import ConnectorError
from ssdv.connectors.registry import require_ready
from ssdv.db import create_schema, drop_schema, make_engine, session_scope
from ssdv.ingest.errors import IngestError
from ssdv.ingest.generic import IngestResult, ingest_generic
from ssdv.ingest.tally_daybook import ingest_tally_daybook
from ssdv.models import Voucher


def connect_journals(
    session: Session,
    *,
    source: str,
    journals: Path | None,
    account_map: Path | None,
    company_name: str | None,
    tally_host: str | None = None,
) -> IngestResult:
    """Read source files only. Write posted books only into this SSDV session."""
    info = require_ready(source)

    if info.id == "tally-http":
        from ssdv.connectors.tally_http import DEFAULT_TALLY_HOST, pull_and_ingest

        return pull_and_ingest(
            session,
            host=tally_host or DEFAULT_TALLY_HOST,
            company_name=company_name,
            account_map=account_map,
        )

    if journals is None or not journals.exists():
        raise IngestError(f"Journal export not found: {journals}")
    if info.id == "tally":
        return ingest_tally_daybook(
            session,
            journals,
            account_map,
            company_name=company_name,
            source=info.id,
        )
    if info.id == "generic" or info.status == "export_csv":
        return ingest_generic(
            session,
            journals,
            account_map,
            company_name=company_name,
            source=info.id,
        )

    raise ConnectorError(f"Unsupported source {info.id!r}")


def load_into_vault(
    db_path: Path,
    *,
    source: str,
    journals: Path | None = None,
    account_map: Path | None = None,
    company_name: str | None = None,
    force: bool = False,
    tally_host: str | None = None,
) -> IngestResult:
    """Replace-or-fill an SSDV sidecar. Never writes back to the source app."""
    require_ready(source)
    if source != "tally-http" and (journals is None or not journals.exists()):
        raise IngestError(f"Journal export not found: {journals}")
    engine = make_engine(db_path)
    if force:
        drop_schema(engine)
    create_schema(engine)
    with session_scope(engine) as session:
        existing = int(session.scalar(select(func.count()).select_from(Voucher)) or 0)
        if existing and not force:
            raise ConnectorError(
                f"Database {db_path} already has {existing} vouchers. Re-run with --force to replace."
            )
        return connect_journals(
            session,
            source=source,
            journals=journals,
            account_map=account_map,
            company_name=company_name,
            tally_host=tally_host,
        )
