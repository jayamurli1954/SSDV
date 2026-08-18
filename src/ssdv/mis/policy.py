from __future__ import annotations

from decimal import Decimal

from ssdv.money import money

CUSTOMER_SHARE_MAX = money("0.35")
VENDOR_SHARE_MAX = money("0.55")
DSO_DAYS_MAX = 120
INVENTORY_TO_SALES_MAX = money("0.45")
COGS_RATIO_MAX = money("0.84")
AR_TO_SALES_STRESS = money("0.30")
COLLECTION_EFFICIENCY_MIN = money("0.80")

PACK_IDS = ("ceo", "cfo", "board", "all")

SCORECARD = (
    ("customer_concentration", "Customer concentration", "Top customer < 35%", CUSTOMER_SHARE_MAX),
    ("vendor_dependency", "Vendor dependency", "Top vendor < 55%", VENDOR_SHARE_MAX),
    ("collections", "Collections", "DSO <= 120 days", Decimal(DSO_DAYS_MAX)),
    ("stock", "Stock", "Inventory / sales < 0.45", INVENTORY_TO_SALES_MAX),
    ("gross_margin", "Gross margin", "COGS / sales < 0.84", COGS_RATIO_MAX),
    ("solvency", "Solvency", "Equity >= 0 after close", money("0")),
)