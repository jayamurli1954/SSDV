from __future__ import annotations

from ssdv.connectors.base import ConnectorError, ConnectorInfo, ConnectorNotReady

_CONNECTORS: tuple[ConnectorInfo, ...] = (
    ConnectorInfo(
        "generic",
        "Any ERP (journal CSV)",
        "ready",
        "Read-only. Export a day book / journal register to CSV "
        "(voucher_id, date, voucher_type, account, debit, credit) plus a ledger map.",
    ),
    ConnectorInfo(
        "tally",
        "Tally / TallyPrime",
        "ready",
        "Native XML DayBook ingestion.",
    ),
    ConnectorInfo(
        "tally-http",
        "TallyPrime HTTP (live pull)",
        "ready",
        "Pull DayBook and Masters directly from a running TallyPrime instance "
        "(port 9000). Use --host to override the URL.",
    ),
    ConnectorInfo(
        "zoho",
        "Zoho Books",
        "export_csv",
        "No live Zoho API. Export the journal register to CSV (generic columns) and connect.",
    ),
    ConnectorInfo(
        "busy",
        "Busy",
        "export_csv",
        "No live Busy dump. Export vouchers to CSV (generic columns) and connect.",
    ),
    ConnectorInfo(
        "mitrabooks",
        "MitraBooks ERP",
        "export_csv",
        "No live MitraBooks API. Export journals to CSV (generic columns) and connect.",
    ),
)


def list_connectors() -> tuple[ConnectorInfo, ...]:
    return _CONNECTORS


def source_ids() -> tuple[str, ...]:
    return tuple(item.id for item in _CONNECTORS)


def get_connector(source_id: str) -> ConnectorInfo:
    for item in _CONNECTORS:
        if item.id == source_id:
            return item
    known = ", ".join(item.id for item in _CONNECTORS)
    raise ConnectorError(f"Unknown source {source_id!r}. Choose one of: {known}")


def require_ready(source_id: str) -> ConnectorInfo:
    info = get_connector(source_id)
    if info.status in {"ready", "export_csv"}:
        return info
    raise ConnectorNotReady(info.hint)
