from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.activity import voucher_account_net
from ssdv.accounting.trial_balance import ledger_balance
from ssdv.gl import AP_CONTROL, AR_CONTROL, COGS, INVENTORY, SALES
from ssdv.models import JournalLine, PurchaseBill, SalesInvoice, Voucher, VoucherType
from ssdv.money import ZERO, money
from ssdv.scenarios.spec import knobs


@dataclass(frozen=True)
class ScenarioMetrics:
    scenario_id: str
    top_customer: str | None
    top_customer_share: Decimal
    top_vendor: str | None
    top_vendor_share: Decimal
    ar_to_sales: Decimal
    inventory_to_sales: Decimal
    cogs_ratio: Decimal
    taxable_sales: Decimal
    inventory: Decimal
    ar: Decimal


def _share(part: Decimal, whole: Decimal) -> Decimal:
    if whole <= ZERO:
        return ZERO
    return money(part / whole)


def _journal_party_totals(
    session: Session,
    as_of: date,
    voucher_type: str,
    account_code: str,
    party_type: str,
    credit: bool,
) -> tuple[str | None, Decimal, Decimal]:
    """Sum SALE/PURCHASE control lines by party. Returns top party, top amount, total."""
    stmt = (
        select(
            JournalLine.party_code, func.sum(JournalLine.credit if credit else JournalLine.debit)
        )
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .where(Voucher.voucher_type == voucher_type)
        .where(Voucher.voucher_date <= as_of)
        .where(JournalLine.account_code == account_code)
        .where(JournalLine.party_type == party_type)
        .where(JournalLine.party_code.isnot(None))
        .group_by(JournalLine.party_code)
        .order_by(func.sum(JournalLine.credit if credit else JournalLine.debit).desc())
    )
    rows = list(session.execute(stmt))
    total = money(sum((money(row[1] or 0) for row in rows), ZERO))
    if not rows:
        return None, ZERO, total
    return str(rows[0][0]), money(rows[0][1] or 0), total


def scenario_metrics(session: Session, as_of: date, company: dict) -> ScenarioMetrics:
    taxable = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.taxable), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    cogs = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.cogs), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    purchases = money(
        session.scalar(
            select(func.coalesce(func.sum(PurchaseBill.taxable), 0)).where(
                PurchaseBill.bill_date <= as_of
            )
        )
        or 0
    )
    top_cust = session.execute(
        select(SalesInvoice.customer_code, func.sum(SalesInvoice.taxable))
        .where(SalesInvoice.invoice_date <= as_of)
        .group_by(SalesInvoice.customer_code)
        .order_by(func.sum(SalesInvoice.taxable).desc())
        .limit(1)
    ).first()
    top_vend = session.execute(
        select(PurchaseBill.vendor_code, func.sum(PurchaseBill.taxable))
        .where(PurchaseBill.bill_date <= as_of)
        .group_by(PurchaseBill.vendor_code)
        .order_by(func.sum(PurchaseBill.taxable).desc())
        .limit(1)
    ).first()
    if taxable <= ZERO:
        taxable = money(-voucher_account_net(session, SALES, as_of, (VoucherType.SALE.value,)))
        cogs = voucher_account_net(session, COGS, as_of, (VoucherType.SALE.value,))
        cust_code, cust_amt, _ = _journal_party_totals(
            session, as_of, VoucherType.SALE.value, AR_CONTROL, "customer", credit=False
        )
        top_cust = (cust_code, cust_amt) if cust_code else None
    if purchases <= ZERO:
        vend_code, vend_amt, purch_total = _journal_party_totals(
            session, as_of, VoucherType.PURCHASE.value, AP_CONTROL, "vendor", credit=True
        )
        purchases = purch_total
        top_vend = (vend_code, vend_amt) if vend_code else None
    ar = ledger_balance(session, AR_CONTROL, as_of)
    inv = ledger_balance(session, INVENTORY, as_of)
    cust_code = str(top_cust[0]) if top_cust else None
    cust_share = _share(money(top_cust[1] if top_cust else 0), taxable)
    vend_code = str(top_vend[0]) if top_vend else None
    vend_share = _share(money(top_vend[1] if top_vend else 0), purchases)
    return ScenarioMetrics(
        scenario_id=str(company.get("generator", {}).get("scenario", "baseline")),
        top_customer=cust_code,
        top_customer_share=cust_share,
        top_vendor=vend_code,
        top_vendor_share=vend_share,
        ar_to_sales=_share(ar, taxable),
        inventory_to_sales=_share(inv, taxable),
        cogs_ratio=_share(cogs, taxable),
        taxable_sales=taxable,
        inventory=inv,
        ar=ar,
    )


def signal_holds(metrics: ScenarioMetrics, company: dict) -> tuple[bool, str]:
    sid = metrics.scenario_id
    extra = knobs(company)
    if sid == "imported":
        return True, "imported books; no planted cause"
    if sid == "customer_concentration":
        if metrics.taxable_sales <= ZERO:
            return True, "no sales yet"
        ok = metrics.top_customer_share >= money("0.35")
        return ok, f"top customer {metrics.top_customer} share {metrics.top_customer_share}"
    if sid == "vendor_dependency":
        if metrics.top_vendor is None:
            return True, "no purchases yet"
        ok = metrics.top_vendor_share >= money("0.55")
        return ok, f"top vendor {metrics.top_vendor} share {metrics.top_vendor_share}"
    if sid == "cash_flow_crisis":
        if metrics.taxable_sales <= ZERO:
            return True, "no sales yet"
        ok = metrics.ar_to_sales >= money("0.30")
        return ok, f"AR/sales {metrics.ar_to_sales}"
    if sid == "inventory_buildup":
        if metrics.taxable_sales <= ZERO:
            return True, "no sales yet"
        ok = metrics.inventory_to_sales >= money("0.45")
        return ok, f"inventory/sales {metrics.inventory_to_sales}"
    if sid == "margin_erosion":
        if metrics.taxable_sales <= ZERO:
            return True, "no sales yet"
        ok = metrics.cogs_ratio >= money("0.84")
        return ok, f"COGS/sales {metrics.cogs_ratio}"
    return True, f"baseline control knobs={sorted(extra)}"
