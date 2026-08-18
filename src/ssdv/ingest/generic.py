from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.coa import load_coa
from ssdv.accounting.posting import PostingError, PostingRequest, post
from ssdv.ingest.errors import IngestError
from ssdv.ingest.journals import drafts_for, grouped_vouchers, load_journal_csv
from ssdv.ingest.mapping import load_account_map
from ssdv.models import Account, IngestMeta, Voucher
from ssdv.scenarios.meta import record_scenario
from ssdv.scenarios.spec import apply_scenario


@dataclass(frozen=True)
class IngestResult:
    vouchers: int
    lines: int
    first_date: date
    last_date: date
    source: str


def ingest_generic(
    session: Session,
    journals: Path,
    account_map: Path | None = None,
    *,
    company_name: str | None = None,
    source: str = "generic",
) -> IngestResult:
    load_coa(session)
    known = set(session.scalars(select(Account.code)))
    mapping = load_account_map(account_map)
    lines = load_journal_csv(journals)
    groups = grouped_vouchers(lines)
    for voucher_id, group in groups.items():
        head = group[0]
        narration = next((row.narration for row in group if row.narration), f"Imported {voucher_id}")
        try:
            post(
                session,
                PostingRequest(
                    voucher_date=head.voucher_date,
                    voucher_type=head.voucher_type,
                    narration=narration[:255],
                    lines=drafts_for(group, mapping, known),
                    source=source,
                    scenario="imported",
                    source_table="csv",
                    source_id=voucher_id[:64],
                ),
            )
        except PostingError as exc:
            raise IngestError(f"Voucher {voucher_id} (row {head.row_no}): {exc}") from exc

    cfg = apply_scenario(None, "imported")
    if company_name:
        cfg["company"]["legal_name"] = company_name
        cfg["company"]["short_name"] = company_name
    dates = [row.voucher_date for row in lines]
    cfg["calendar"]["books_start"] = min(dates).isoformat()
    cfg["calendar"]["books_end"] = max(dates).isoformat()
    record_scenario(session, cfg)
    meta = session.get(IngestMeta, 1)
    if meta is None:
        meta = IngestMeta(
            id=1,
            source=source,
            company_name=str(cfg["company"]["legal_name"]),
            journals_path=str(journals),
            first_date=min(dates),
            last_date=max(dates),
        )
        session.add(meta)
    else:
        meta.source = source
        meta.company_name = str(cfg["company"]["legal_name"])
        meta.journals_path = str(journals)
        meta.first_date = min(dates)
        meta.last_date = max(dates)
    voucher_n = int(session.scalar(select(func.count()).select_from(Voucher)) or 0)
    return IngestResult(
        vouchers=voucher_n,
        lines=len(lines),
        first_date=min(dates),
        last_date=max(dates),
        source=source,
    )
