from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.connectors.base import ConnectorError
from ssdv.connectors.registry import require_ready
from ssdv.db import create_schema, drop_schema, make_engine, session_scope
from ssdv.ingest.errors import IngestError
from ssdv.ingest.generic import IngestResult, ingest_generic
from ssdv.models import Voucher


def connect_journals(
    session: Session,
    *,
    source: str,
    journals: Path,
    account_map: Path | None,
    company_name: str | None,
) -> IngestResult:
    """Read source files only. Write posted books only into this SSDV session."""
    info = require_ready(source)
    if not journals.exists():
        raise IngestError(f"Journal export not found: {journals}")
    return ingest_generic(
        session,
        journals,
        account_map,
        company_name=company_name,
        source=info.id,
    )


def load_into_vault(
    db_path: Path,
    *,
    source: str,
    journals: Path,
    account_map: Path | None,
    company_name: str | None,
    force: bool = False,
) -> IngestResult:
    """Replace-or-fill an SSDV sidecar. Never writes back to the source app."""
    require_ready(source)
    if not journals.exists():
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
        )
