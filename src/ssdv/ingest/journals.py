from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ssdv.accounting.posting import LineDraft
from ssdv.ingest.errors import IngestError
from ssdv.models import VoucherType
from ssdv.money import ZERO, money

_ID_KEYS = ("voucher_id", "voucher", "id", "vch_id")
_NO_KEYS = ("voucher_no", "vch_no", "number")
_DATE_KEYS = ("date", "voucher_date", "vch_date")
_TYPE_KEYS = ("voucher_type", "type", "vch_type")
_ACCOUNT_KEYS = ("account", "account_code", "ledger", "ledger_name")
_DEBIT_KEYS = ("debit", "dr", "debit_amount")
_CREDIT_KEYS = ("credit", "cr", "credit_amount")
_PARTY_TYPE_KEYS = ("party_type",)
_PARTY_KEYS = ("party", "party_code", "party_name")
_NARRATION_KEYS = ("narration", "voucher_narration")
_LINE_KEYS = ("line_narration", "particulars", "line")

_TYPE_ALIASES = {
    "SALES": "SALE",
    "PURCHASES": "PURCHASE",
    "RECEIPTS": "RECEIPT",
    "PAYMENTS": "PAYMENT",
    "EXPENSES": "EXPENSE",
    "CREDITNOTE": "CREDIT_NOTE",
    "CREDIT_NOTE": "CREDIT_NOTE",
    "DEBITNOTE": "DEBIT_NOTE",
    "DEBIT_NOTE": "DEBIT_NOTE",
    "GST": "GST_PAYMENT",
    "GST_PAYMENT": "GST_PAYMENT",
    "GSTPAYMENT": "GST_PAYMENT",
}


@dataclass(frozen=True)
class SourceLine:
    voucher_id: str
    voucher_date: date
    voucher_type: VoucherType
    account: str
    debit: Decimal
    credit: Decimal
    party_type: str | None
    party_code: str | None
    narration: str
    line_narration: str | None
    row_no: int


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _pick(fields: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in fields:
            return fields[key]
    return None


def _amount(raw: str | None) -> Decimal:
    text = str(raw or "").strip().replace(",", "")
    if text == "":
        return ZERO
    try:
        return money(text)
    except (InvalidOperation, ValueError) as exc:
        raise IngestError(f"Not an amount: {raw!r}") from exc


def _parse_date(raw: str, row_no: int) -> date:
    text = raw.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    for sep in ("-", "/"):
        parts = text.split(sep)
        if len(parts) != 3:
            continue
        try:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        if year < 100 or day > 31:
            continue
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise IngestError(f"Row {row_no}: cannot parse date {raw!r} (use YYYY-MM-DD)")


def parse_voucher_type(raw: str | None) -> VoucherType:
    if not raw or not str(raw).strip():
        return VoucherType.JOURNAL
    key = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    key = _TYPE_ALIASES.get(key, key)
    try:
        return VoucherType[key]
    except KeyError as exc:
        known = ", ".join(t.name for t in VoucherType)
        raise IngestError(f"Unknown voucher type {raw!r}. Use one of: {known}") from exc


def _party_type(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    key = str(raw).strip().casefold()
    if key in {"customer", "cust", "debtor", "sundry debtor"}:
        return "customer"
    if key in {"vendor", "supplier", "creditor", "sundry creditor"}:
        return "vendor"
    return str(raw).strip().casefold()


def load_journal_csv(path: Path) -> list[SourceLine]:
    if not path.exists():
        raise IngestError(f"Journals file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise IngestError(f"{path} has no header row")
        fields = {_norm(name): name for name in reader.fieldnames if name}
        col_id = _pick(fields, _ID_KEYS)
        col_no = _pick(fields, _NO_KEYS)
        col_date = _pick(fields, _DATE_KEYS)
        col_type = _pick(fields, _TYPE_KEYS)
        col_account = _pick(fields, _ACCOUNT_KEYS)
        col_debit = _pick(fields, _DEBIT_KEYS)
        col_credit = _pick(fields, _CREDIT_KEYS)
        col_ptype = _pick(fields, _PARTY_TYPE_KEYS)
        col_party = _pick(fields, _PARTY_KEYS)
        col_narr = _pick(fields, _NARRATION_KEYS)
        col_line = _pick(fields, _LINE_KEYS)
        if col_date is None or col_account is None or col_debit is None or col_credit is None:
            raise IngestError(
                f"{path} needs date, account, debit and credit columns (got {reader.fieldnames})"
            )
        if col_id is None and col_no is None:
            raise IngestError(f"{path} needs voucher_id (or voucher_no) to group lines")

        rows: list[SourceLine] = []
        for index, row in enumerate(reader, start=2):
            account = str(row.get(col_account) or "").strip()
            debit = _amount(row.get(col_debit))
            credit = _amount(row.get(col_credit))
            if not account and debit == ZERO and credit == ZERO:
                continue
            raw_date = str(row.get(col_date) or "").strip()
            if not raw_date:
                raise IngestError(f"Row {index}: missing date")
            voucher_id = str((row.get(col_id) if col_id else "") or "").strip()
            voucher_no = str((row.get(col_no) if col_no else "") or "").strip()
            vtype = parse_voucher_type(row.get(col_type) if col_type else None)
            if not voucher_id:
                voucher_id = f"{voucher_no}|{raw_date}|{vtype.value}"
            rows.append(
                SourceLine(
                    voucher_id=voucher_id,
                    voucher_date=_parse_date(raw_date, index),
                    voucher_type=vtype,
                    account=account,
                    debit=debit,
                    credit=credit,
                    party_type=_party_type(row.get(col_ptype) if col_ptype else None),
                    party_code=(str(row.get(col_party) or "").strip() or None) if col_party else None,
                    narration=str(row.get(col_narr) or "").strip() if col_narr else "",
                    line_narration=(str(row.get(col_line) or "").strip() or None) if col_line else None,
                    row_no=index,
                )
            )
    if not rows:
        raise IngestError(f"{path} has no journal lines")
    return rows


def grouped_vouchers(lines: list[SourceLine]) -> dict[str, list[SourceLine]]:
    groups: dict[str, list[SourceLine]] = defaultdict(list)
    for line in lines:
        groups[line.voucher_id].append(line)
    for voucher_id, group in groups.items():
        dates = {row.voucher_date for row in group}
        types = {row.voucher_type for row in group}
        if len(dates) > 1:
            raise IngestError(f"Voucher {voucher_id} has mixed dates {sorted(dates)}")
        if len(types) > 1:
            raise IngestError(f"Voucher {voucher_id} has mixed types {[t.value for t in types]}")
    return dict(groups)


def drafts_for(group: list[SourceLine], mapping: dict[str, str], known_codes: set[str]) -> list[LineDraft]:
    from ssdv.ingest.mapping import resolve_account

    drafts: list[LineDraft] = []
    for row in group:
        drafts.append(
            LineDraft(
                account_code=resolve_account(row.account, mapping, known_codes),
                debit=row.debit,
                credit=row.credit,
                party_type=row.party_type,
                party_code=row.party_code,
                line_narration=row.line_narration or row.narration or None,
            )
        )
    return drafts
