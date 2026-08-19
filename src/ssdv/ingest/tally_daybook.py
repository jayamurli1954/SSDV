from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.coa import load_coa
from ssdv.accounting.posting import PostingError, PostingRequest, post
from ssdv.ingest.errors import IngestError
from ssdv.ingest.generic import IngestResult
from ssdv.ingest.journals import SourceLine, drafts_for, grouped_vouchers, parse_voucher_type
from ssdv.ingest.mapping import load_account_map
from ssdv.models import Account, IngestMeta, Voucher, VoucherType
from ssdv.scenarios.meta import record_scenario
from ssdv.scenarios.spec import apply_scenario


def _local_name(tag: str) -> str:
    # ElementTree tags may be namespaced: `{namespace}VOUCHER`
    return tag.rsplit("}", 1)[-1]


def _child_text(elem: ET.Element, *tag_names: str) -> str | None:
    wanted = {_t.casefold() for _t in tag_names}
    for child in list(elem):
        if _local_name(child.tag).casefold() in wanted:
            text = child.text or ""
            return text.strip() or None
    return None


def _parse_tally_date(raw: str, *, row_no: int) -> date:
    text = raw.strip()
    if not text:
        raise IngestError(f"Row {row_no}: missing voucher date")
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    # Common Tally formats: `01-Apr-2024` / `01/04/2024`
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    raise IngestError(f"Row {row_no}: cannot parse date {raw!r}")


def _parse_amount(raw: str, *, row_no: int) -> Decimal:
    text = raw.strip().replace(",", "")
    try:
        return Decimal(text)
    except Exception as exc:  # pragma: no cover
        raise IngestError(f"Row {row_no}: not an amount: {raw!r}") from exc


def load_journal_tally_daybook(path: Path) -> list[SourceLine]:
    if not path.exists():
        raise IngestError(f"DayBook XML not found: {path}")

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise IngestError(f"Invalid XML: {path}") from exc

    lines: list[SourceLine] = []
    voucher_idx = 0
    row_no = 0

    for voucher_elem in root.iter():
        if _local_name(voucher_elem.tag) != "VOUCHER":
            continue
        voucher_idx += 1

        vch_type_raw = _child_text(voucher_elem, "VCHTYPE", "VOUCHERTYPE", "TYPE")
        if not vch_type_raw:
            raise IngestError(f"Voucher {voucher_idx}: missing VCHTYPE")
        voucher_type = parse_voucher_type(vch_type_raw)

        vch_date_raw = _child_text(voucher_elem, "VCHDATE", "DATE", "VOUCHERDATE")
        if not vch_date_raw:
            raise IngestError(f"Voucher {voucher_idx}: missing VCHDATE")
        voucher_date = _parse_tally_date(vch_date_raw, row_no=voucher_idx)

        vch_no_raw = _child_text(voucher_elem, "VCHNO", "VOUCHERNUMBER", "VCH_NUMBER")
        voucher_no = vch_no_raw or f"V{voucher_idx}"
        narration = _child_text(voucher_elem, "NARRATION", "VOUCHERNARRATION", "NARRATIVE") or ""

        party_ledger = _child_text(voucher_elem, "PARTYLEDGERNAME") or None

        inferred_party_type: str | None
        if voucher_type in {VoucherType.SALE, VoucherType.CREDIT_NOTE, VoucherType.RECEIPT}:
            inferred_party_type = "customer"
        elif voucher_type in {
            VoucherType.PURCHASE,
            VoucherType.DEBIT_NOTE,
            VoucherType.PAYMENT,
        }:
            inferred_party_type = "vendor"
        else:
            inferred_party_type = None

        voucher_id = f"{voucher_no}|{voucher_date.isoformat()}|{voucher_type.value}"

        ledger_entries: list[ET.Element] = [
            elem for elem in voucher_elem.iter() if _local_name(elem.tag) == "ALLLEDGERENTRIES.LIST"
        ]
        if not ledger_entries:
            # Some exports keep ledger entries as `LEDGERENTRIES.LIST`
            ledger_entries = [
                elem
                for elem in voucher_elem.iter()
                if _local_name(elem.tag) == "LEDGERENTRIES.LIST"
            ]

        for entry_i, entry_elem in enumerate(ledger_entries, start=1):
            row_no += 1
            ledger_name = _child_text(entry_elem, "LEDGERNAME") or ""
            if not ledger_name:
                continue

            amount_raw = _child_text(entry_elem, "AMOUNT") or "0"
            deemed_positive = _child_text(entry_elem, "ISDEEMEDPOSITIVE")

            amount = _parse_amount(amount_raw, row_no=row_no)
            if deemed_positive is not None:
                is_pos = deemed_positive.casefold() in {"yes", "true", "1", "y"}
                amount = abs(amount) if is_pos else -abs(amount)

            if amount == 0:
                continue

            debit = amount if amount > 0 else Decimal(0)
            credit = -amount if amount < 0 else Decimal(0)

            party_type: str | None = None
            party_code: str | None = None
            if inferred_party_type is not None:
                if party_ledger is not None:
                    if ledger_name.casefold() == party_ledger.casefold():
                        party_type = inferred_party_type
                        party_code = party_ledger
                else:
                    # If the XML doesn't provide PARTYLEDGERNAME, use the first ledger
                    # line as the party line.
                    if entry_i == 1:
                        party_type = inferred_party_type
                        party_code = ledger_name

            lines.append(
                SourceLine(
                    voucher_id=voucher_id,
                    voucher_date=voucher_date,
                    voucher_type=voucher_type,
                    account=ledger_name,
                    debit=debit,
                    credit=credit,
                    party_type=party_type,
                    party_code=party_code,
                    narration=narration.strip(),
                    line_narration=None,
                    row_no=row_no,
                )
            )

    if not lines:
        raise IngestError(f"{path} has no VOUCHER ledger lines")
    return lines


def ingest_tally_daybook(
    session: Session,
    daybook_xml: Path,
    account_map: Path | None = None,
    *,
    company_name: str | None = None,
    source: str = "tally",
) -> IngestResult:
    load_coa(session)
    known = set(session.scalars(select(Account.code)))
    mapping = load_account_map(account_map)
    lines = load_journal_tally_daybook(daybook_xml)
    groups = grouped_vouchers(lines)

    for voucher_id, group in groups.items():
        head = group[0]
        narration = next(
            (row.narration for row in group if row.narration), f"Imported {voucher_id}"
        )
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
                    source_table="xml",
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
            journals_path=str(daybook_xml),
            first_date=min(dates),
            last_date=max(dates),
        )
        session.add(meta)
    else:
        meta.source = source
        meta.company_name = str(cfg["company"]["legal_name"])
        meta.journals_path = str(daybook_xml)
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
