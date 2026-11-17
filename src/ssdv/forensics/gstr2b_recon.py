"""GSTR-2B vs Purchase Books ITC reconciliation (Phase 5.2).

Compares GSTR-2B portal data against booked purchase bills to flag:
  - Missing in books  (in 2B but no matching purchase bill)
  - Missing in 2B     (purchase bill exists but not in 2B)
  - Amount mismatch   (both exist but taxable/GST differs)
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ssdv.models import Gstr2bLine, PurchaseBill
from ssdv.money import ZERO, money

_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


def period_key(d: date) -> str:
    """GSTR-2B return period as YYYY-MM."""
    return f"{d.year:04d}-{d.month:02d}"


@dataclass(frozen=True)
class ReconRow:
    supplier_gstin: str
    invoice_no: str
    flag: str  # "missing_in_books" | "missing_in_2b" | "amount_mismatch"
    portal_taxable: Decimal
    portal_gst: Decimal
    books_taxable: Decimal
    books_gst: Decimal
    diff_gst: Decimal


@dataclass(frozen=True)
class ReconSummary:
    total_portal_itc: Decimal
    total_books_itc: Decimal
    itc_gap: Decimal
    rows: tuple[ReconRow, ...]


def load_gstr2b_csv(session: Session, csv_path: Path) -> int:
    """Load a GSTR-2B CSV into the gstr2b_lines table. Returns rows loaded.

    Expected columns (case-insensitive, flexible naming):
      return_period, supplier_gstin, supplier_name, invoice_no, invoice_date,
      taxable, cgst, sgst, igst, itc_available
    """
    with open(csv_path, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return 0
        normalised = {f.strip().lower().replace(" ", "_"): f for f in reader.fieldnames}

        def _col(key: str) -> str:
            return normalised.get(key, key)

        loaded = 0
        for raw in reader:
            row = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in raw.items()}
            inv_date_str = row.get("invoice_date", "")
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    inv_date = datetime.strptime(inv_date_str, fmt).date()  # noqa: DTZ007
                    break
                except ValueError:
                    continue
            else:
                inv_date = date(2000, 1, 1)

            itc_raw = row.get("itc_available", "Y").upper()
            itc_available = itc_raw not in ("N", "NO", "0", "FALSE")

            session.add(
                Gstr2bLine(
                    return_period=row.get("return_period", ""),
                    supplier_gstin=row.get("supplier_gstin", ""),
                    supplier_name=row.get("supplier_name"),
                    invoice_no=row.get("invoice_no", ""),
                    invoice_date=inv_date,
                    taxable=money(row.get("taxable", "0")),
                    cgst=money(row.get("cgst", "0")),
                    sgst=money(row.get("sgst", "0")),
                    igst=money(row.get("igst", "0")),
                    itc_available=itc_available,
                )
            )
            loaded += 1
        session.flush()
    return loaded


def reconcile_2b(session: Session, return_period: str | None = None) -> ReconSummary:
    """Match GSTR-2B lines against PurchaseBill records by supplier GSTIN + invoice_no."""

    # Portal side
    stmt_2b = select(Gstr2bLine)
    if return_period:
        stmt_2b = stmt_2b.where(Gstr2bLine.return_period == return_period)
    portal_lines: dict[tuple[str, str], Gstr2bLine] = {}
    for line in session.scalars(stmt_2b):
        key = (str(line.supplier_gstin).strip(), str(line.invoice_no).strip().upper())
        portal_lines[key] = line

    # Books side — when return_period is YYYY-MM, compare only that month's bills
    # so a single portal file doesn't false-flag every other month as missing_in_2b.
    stmt_bills = select(PurchaseBill)
    books: dict[tuple[str, str], PurchaseBill] = {}
    for bill in session.scalars(stmt_bills):
        if return_period and _PERIOD_RE.match(return_period):
            if period_key(bill.bill_date) != return_period:
                continue
        gstin = str(bill.vendor_gstin or "").strip()
        bill_no = str(bill.bill_no).strip().upper()
        if gstin:
            books[(gstin, bill_no)] = bill

    rows: list[ReconRow] = []
    total_portal = ZERO
    total_books = ZERO

    # Check portal lines against books
    for key, p in portal_lines.items():
        p_gst = money(p.cgst + p.sgst + p.igst)
        total_portal += p_gst
        if key not in books:
            rows.append(
                ReconRow(
                    supplier_gstin=key[0],
                    invoice_no=key[1],
                    flag="missing_in_books",
                    portal_taxable=p.taxable,
                    portal_gst=p_gst,
                    books_taxable=ZERO,
                    books_gst=ZERO,
                    diff_gst=p_gst,
                )
            )
            continue
        b = books[key]
        b_gst = money(b.cgst + b.sgst + b.igst)
        total_books += b_gst
        diff = money(p_gst - b_gst)
        if diff != ZERO:
            rows.append(
                ReconRow(
                    supplier_gstin=key[0],
                    invoice_no=key[1],
                    flag="amount_mismatch",
                    portal_taxable=p.taxable,
                    portal_gst=p_gst,
                    books_taxable=b.taxable,
                    books_gst=b_gst,
                    diff_gst=diff,
                )
            )

    # Check books entries missing from portal
    for key, b in books.items():
        b_gst = money(b.cgst + b.sgst + b.igst)
        if key not in portal_lines:
            total_books += b_gst
            rows.append(
                ReconRow(
                    supplier_gstin=key[0],
                    invoice_no=key[1],
                    flag="missing_in_2b",
                    portal_taxable=ZERO,
                    portal_gst=ZERO,
                    books_taxable=b.taxable,
                    books_gst=b_gst,
                    diff_gst=money(-b_gst),
                )
            )

    rows.sort(key=lambda r: abs(r.diff_gst), reverse=True)
    return ReconSummary(
        total_portal_itc=money(total_portal),
        total_books_itc=money(total_books),
        itc_gap=money(total_portal - total_books),
        rows=tuple(rows),
    )


@dataclass(frozen=True)
class SeedFromBooksResult:
    period: str
    bills_in_period: int
    portal_rows: int
    matched: int
    omitted_from_2b: int
    amount_mismatches: int
    portal_only: int


def seed_gstr2b_from_books(
    session: Session,
    *,
    return_period: str,
    omit_count: int = 4,
    amount_mismatch_count: int = 3,
    portal_only_count: int = 2,
    replace_period: bool = True,
) -> SeedFromBooksResult:
    """Build synthetic GSTR-2B lines from booked purchase bills for demos.

    Matches most invoices exactly, then plants a few controlled gaps so
    reconciliation and the quality ITC signal have something real to show.
    """
    if not _PERIOD_RE.match(return_period):
        raise ValueError(f"return_period must be YYYY-MM, got {return_period!r}")

    bills = [
        b
        for b in session.scalars(select(PurchaseBill)).all()
        if period_key(b.bill_date) == return_period and str(b.vendor_gstin or "").strip()
    ]
    bills.sort(key=lambda b: (b.bill_date, b.bill_no))
    if not bills:
        raise ValueError(f"No purchase bills with GSTIN in period {return_period}")

    if replace_period:
        session.execute(delete(Gstr2bLine).where(Gstr2bLine.return_period == return_period))
        session.flush()

    omit_n = min(max(0, omit_count), max(0, len(bills) - 1))
    mismatch_n = min(max(0, amount_mismatch_count), max(0, len(bills) - omit_n))
    # Keep the largest invoices for mismatches so the ITC gap is visible on screen.
    by_gst = sorted(bills, key=lambda b: abs(b.cgst + b.sgst + b.igst), reverse=True)
    omit_set = {id(b) for b in by_gst[:omit_n]}
    mismatch_set = {id(b) for b in by_gst[omit_n : omit_n + mismatch_n]}

    matched = 0
    amount_mismatches = 0
    for bill in bills:
        if id(bill) in omit_set:
            continue
        cgst, sgst, igst = money(bill.cgst), money(bill.sgst), money(bill.igst)
        taxable = money(bill.taxable)
        if id(bill) in mismatch_set:
            # Inflate portal GST ~8% so amount_mismatch + positive ITC gap show up.
            bump = money(Decimal("1.08"))
            cgst, sgst, igst = money(cgst * bump), money(sgst * bump), money(igst * bump)
            taxable = money(taxable * bump)
            amount_mismatches += 1
        else:
            matched += 1
        session.add(
            Gstr2bLine(
                return_period=return_period,
                supplier_gstin=str(bill.vendor_gstin).strip(),
                supplier_name=None,
                invoice_no=str(bill.bill_no).strip(),
                invoice_date=bill.bill_date,
                taxable=taxable,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                itc_available=True,
            )
        )

    portal_only = 0
    for i in range(max(0, portal_only_count)):
        session.add(
            Gstr2bLine(
                return_period=return_period,
                supplier_gstin="27AABCT1332L1ZV",
                supplier_name="Portal-only Demo Supplier",
                invoice_no=f"PORTAL-ONLY-{return_period}-{i + 1}",
                invoice_date=date(int(return_period[:4]), int(return_period[5:7]), min(28, 10 + i)),
                taxable=money("25000.00"),
                cgst=money("2250.00"),
                sgst=money("2250.00"),
                igst=ZERO,
                itc_available=True,
            )
        )
        portal_only += 1

    session.flush()
    portal_rows = matched + amount_mismatches + portal_only
    return SeedFromBooksResult(
        period=return_period,
        bills_in_period=len(bills),
        portal_rows=portal_rows,
        matched=matched,
        omitted_from_2b=omit_n,
        amount_mismatches=amount_mismatches,
        portal_only=portal_only,
    )
