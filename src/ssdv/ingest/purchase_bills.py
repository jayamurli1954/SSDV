"""Invoice-level purchase register import for GSTR-2B reconciliation.

Day-book / Tally journal connectors post GL only — they never create PurchaseBill
rows. This module loads a purchase register CSV as *detail* for ITC matching
against GSTR-2B without posting a second set of purchase journals (no double GL).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.coa import load_coa
from ssdv.accounting.posting import LineDraft, PostingRequest, post
from ssdv.fy import fy_code
from ssdv.gl import AP_CONTROL
from ssdv.ingest.errors import IngestError
from ssdv.models import PurchaseBill, Vendor, Voucher, VoucherType, Warehouse
from ssdv.money import ZERO, money

DEFAULT_WAREHOUSE = "WH-IMP"


@dataclass(frozen=True)
class PurchaseBillImportResult:
    bills: int
    vendors_created: int
    skipped: int


def _norm_key(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _parse_date(raw: str) -> date:
    text = (raw or "").strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d/%b/%Y"):
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    raise IngestError(f"Unrecognised invoice_date {raw!r}")


def _vendor_code_from_gstin(gstin: str) -> str:
    clean = re.sub(r"[^A-Z0-9]", "", gstin.upper())
    return f"V{clean[-14:]}" if len(clean) > 14 else f"V{clean}"


def _state_from_gstin(gstin: str) -> str:
    return gstin[:2] if len(gstin) >= 2 else "27"


def _ensure_warehouse(session: Session) -> Warehouse:
    wh = session.get(Warehouse, DEFAULT_WAREHOUSE)
    if wh is not None:
        return wh
    wh = Warehouse(code=DEFAULT_WAREHOUSE, name="Import / recon warehouse", branch_code=None)
    session.add(wh)
    session.flush()
    return wh


def _ensure_vendor(
    session: Session,
    *,
    gstin: str,
    name: str | None,
    state_code: str | None,
    created: list[int],
) -> Vendor:
    gstin_u = gstin.strip().upper()
    existing = session.scalar(select(Vendor).where(Vendor.gstin == gstin_u))
    if existing is not None:
        return existing
    code = _vendor_code_from_gstin(gstin_u)
    if session.get(Vendor, code) is not None:
        code = f"{code[:12]}{created[0] % 100:02d}"
    vendor = Vendor(
        code=code,
        name=(name or f"Vendor {gstin_u}").strip()[:128],
        state_code=(state_code or _state_from_gstin(gstin_u))[:2],
        gstin=gstin_u,
        is_active=True,
    )
    session.add(vendor)
    session.flush()
    created[0] += 1
    return vendor


def _import_anchor_voucher(session: Session) -> int:
    """Reuse any voucher, or create a net-zero JOURNAL so PurchaseBill.voucher_id is set.

    Imported purchase-register rows must not re-post purchase GL (day-book already did).
    """
    existing = session.scalar(select(Voucher.id).order_by(Voucher.id).limit(1))
    if existing is not None:
        return int(existing)

    load_coa(session)
    voucher = post(
        session,
        PostingRequest(
            voucher_date=date.today(),
            voucher_type=VoucherType.JOURNAL,
            narration="Purchase register import anchor (no economic effect)",
            lines=[
                LineDraft(account_code=AP_CONTROL, debit=money("0.01"), line_narration="anchor"),
                LineDraft(account_code=AP_CONTROL, credit=money("0.01"), line_narration="anchor"),
            ],
            source="purchase_bill_import",
            scenario="imported",
            source_table="purchase_bill_import",
            source_id="anchor",
        ),
    )
    return int(voucher.id)


def load_purchase_bills_csv(session: Session, csv_path: Path) -> PurchaseBillImportResult:
    """Load invoice-level purchase register rows into purchase_bills.

    Expected columns (case-insensitive; aliases accepted):
      supplier_gstin / gstin, invoice_no / bill_no, invoice_date / bill_date,
      taxable, cgst, sgst, igst
    Optional: supplier_name, vendor_state / state_code

    Does **not** post purchase journals. Safe after Tally/generic day-book ingest.
    """
    if not csv_path.is_file():
        raise IngestError(f"Purchase bill CSV not found: {csv_path}")

    warehouse = _ensure_warehouse(session)
    anchor_id = _import_anchor_voucher(session)
    vendors_created = [0]
    loaded = 0
    skipped = 0

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise IngestError("Purchase bill CSV has no header row")

        for raw in reader:
            row = {_norm_key(k): (v or "").strip() for k, v in raw.items() if k}
            gstin = row.get("supplier_gstin") or row.get("gstin") or row.get("vendor_gstin") or ""
            invoice_no = row.get("invoice_no") or row.get("bill_no") or row.get("inv_no") or ""
            date_raw = row.get("invoice_date") or row.get("bill_date") or row.get("date") or ""
            if not gstin or not invoice_no or not date_raw:
                skipped += 1
                continue
            gstin_u = gstin.upper()
            if len(gstin_u) != 15:
                raise IngestError(f"Invalid GSTIN length for invoice {invoice_no!r}: {gstin!r}")

            bill_date = _parse_date(date_raw)
            taxable = money(row.get("taxable") or row.get("taxable_value") or "0")
            cgst = money(row.get("cgst") or "0")
            sgst = money(row.get("sgst") or "0")
            igst = money(row.get("igst") or "0")
            if taxable == ZERO and (cgst + sgst + igst) == ZERO:
                skipped += 1
                continue

            bill_no = invoice_no[:32]
            vendor = _ensure_vendor(
                session,
                gstin=gstin_u,
                name=row.get("supplier_name") or row.get("vendor_name"),
                state_code=row.get("vendor_state") or row.get("state_code"),
                created=vendors_created,
            )

            exists = session.scalar(
                select(func.count())
                .select_from(PurchaseBill)
                .where(
                    PurchaseBill.bill_no == bill_no,
                    PurchaseBill.vendor_code == vendor.code,
                )
            )
            if int(exists or 0) > 0:
                skipped += 1
                continue

            interstate = igst > ZERO
            grand = money(taxable + cgst + sgst + igst)
            fy = fy_code(bill_date)
            seq = (
                int(
                    session.scalar(
                        select(func.count())
                        .select_from(PurchaseBill)
                        .where(PurchaseBill.fy_code == fy)
                    )
                    or 0
                )
                + 1
            )

            session.add(
                PurchaseBill(
                    bill_no=bill_no,
                    grn_no=f"IMP/{fy}/{seq:06d}",
                    bill_date=bill_date,
                    fy_code=fy,
                    vendor_code=vendor.code,
                    vendor_gstin=gstin_u,
                    vendor_state=str(vendor.state_code or _state_from_gstin(gstin_u)),
                    warehouse_code=warehouse.code,
                    interstate=interstate,
                    taxable=taxable,
                    cgst=cgst,
                    sgst=sgst,
                    igst=igst,
                    grand_total=grand,
                    voucher_id=anchor_id,
                    narration="Imported purchase register (GSTR-2B recon detail; no extra GL)",
                )
            )
            loaded += 1

        session.flush()

    return PurchaseBillImportResult(
        bills=loaded,
        vendors_created=vendors_created[0],
        skipped=skipped,
    )
