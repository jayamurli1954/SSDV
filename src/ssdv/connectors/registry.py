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
        "Native API is not wired. Export journals to CSV and use --source generic.",
    ),
    ConnectorInfo(
        "busy",
        "Busy",
        "export_csv",
        "Native dump is not wired. Export vouchers to CSV and use --source generic.",
    ),
    ConnectorInfo(
        "mitrabooks",
        "MitraBooks ERP",
        "export_csv",
        "SSDV is the connector, not the ERP. Export journals or point at an SSDV vault.",
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
    if info.status != "ready":
        raise ConnectorNotReady(info.hint)
    return info
