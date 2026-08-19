from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.cash.outstanding import bill_outstanding
from ssdv.models import PurchaseBill, Vendor
from ssdv.money import ZERO, money


@dataclass(frozen=True)
class Msme43bhVendorRisk:
    vendor_code: str
    vendor_name: str
    msme_category: str
    threshold_days: int
    oldest_days: int
    risk_amount: Decimal


def msme_43bh_risk(
    session: Session,
    as_of: date,
    *,
    limit: int = 10,
) -> tuple[Decimal, tuple[Msme43bhVendorRisk, ...]]:
    """Compute 43B(h) risk (simplified v1):

    - Only applies to vendors tagged as MSME.
    - For each PurchaseBill, if bill age exceeds the vendor’s allowed window
      (45 days when agreement exists; otherwise 15 days), then the bill’s
      *outstanding* payable is counted as risk.
    """

    stmt = (
        select(
            PurchaseBill,
            Vendor.name,
            Vendor.msme_category,
            Vendor.msme_has_agreement,
        )
        .join(Vendor, Vendor.code == PurchaseBill.vendor_code)
        .where(Vendor.msme_category.isnot(None))
        .where(PurchaseBill.bill_date <= as_of)
    )

    risks: dict[str, Msme43bhVendorRisk] = {}

    for bill, vendor_name, category, has_agreement in session.execute(stmt):
        vendor_code = str(bill.vendor_code)
        msme_category = str(category)
        threshold_days = 45 if bool(has_agreement) else 15
        age_days = (as_of - bill.bill_date).days

        if age_days <= threshold_days:
            continue

        outstanding = bill_outstanding(session, bill, as_of)
        if outstanding <= ZERO:
            continue

        current = risks.get(vendor_code)
        if current is None:
            risks[vendor_code] = Msme43bhVendorRisk(
                vendor_code=vendor_code,
                vendor_name=str(vendor_name),
                msme_category=msme_category,
                threshold_days=threshold_days,
                oldest_days=age_days,
                risk_amount=outstanding,
            )
            continue

        # Keep the stricter threshold + max age seen.
        oldest = max(current.oldest_days, age_days)
        risk_total = money(current.risk_amount + outstanding)
        risks[vendor_code] = Msme43bhVendorRisk(
            vendor_code=current.vendor_code,
            vendor_name=current.vendor_name,
            msme_category=current.msme_category,
            threshold_days=min(current.threshold_days, threshold_days),
            oldest_days=oldest,
            risk_amount=risk_total,
        )

    ordered = sorted(risks.values(), key=lambda r: r.risk_amount, reverse=True)[:limit]
    total = money(sum((row.risk_amount for row in ordered), ZERO))
    return total, tuple(ordered)

