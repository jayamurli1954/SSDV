from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.activity import voucher_account_net
from ssdv.accounting.equation import accounting_equation
from ssdv.accounting.subledger import ap_subledger, ar_subledger, subledger_total
from ssdv.accounting.trial_balance import ledger_balance, tb_totals, trial_balance
from ssdv.cash.aging import aging_totals, ap_aging, ar_aging
from ssdv.cash.banks import choose_bank, current_bank_balances
from ssdv.cash.outstanding import document_ap_outstanding, document_ar_outstanding
from ssdv.gl import (
    ACCUM_DEP_FURNITURE,
    AP_CONTROL,
    AR_CONTROL,
    BANK_HDFC,
    BANK_ICICI,
    BANK_OD,
    COGS,
    GST_PAYABLE,
    INPUT_CGST,
    INPUT_IGST,
    INPUT_SGST,
    INVENTORY,
    OUTPUT_CGST,
    OUTPUT_IGST,
    OUTPUT_SGST,
    SALES,
)
from ssdv.gstin import is_valid_gstin
from ssdv.inventory.stock import stock_quantity, stock_value
from ssdv.models import (
    BankCharge,
    Customer,
    GstSettlement,
    IngestMeta,
    LoanEmi,
    OpexEntry,
    Payment,
    Product,
    PurchaseBill,
    Receipt,
    SalesInvoice,
    ScenarioMeta,
    Vendor,
    Voucher,
    VoucherType,
)
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.scenarios.metrics import scenario_metrics, signal_holds
from ssdv.scenarios.spec import GOLDEN

VOLUME_GATES = frozenset(
    {
        "purchase_count",
        "sales_count",
        "receipt_count",
        "payment_count",
        "expense_months",
        "emi_count",
        "gst_months",
        "depreciation",
        "year_closed",
    }
)

INTEGRITY_GATES = frozenset({"trial_balance", "accounting_equation"})


@dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str


def run_gates(session: Session, as_of: date, company: dict | None = None) -> list[Gate]:
    cfg = company or load_company()
    gates: list[Gate] = []

    rows = trial_balance(session, as_of)
    debit, credit = tb_totals(rows)
    gates.append(Gate("trial_balance", debit == credit, f"debit {debit} credit {credit}"))

    snap = accounting_equation(session, as_of)
    gates.append(Gate("accounting_equation", snap.holds, f"delta {snap.delta}"))

    imported = (
        str(cfg.get("generator", {}).get("scenario")) == "imported"
        or cfg.get("validate_mode") == "imported"
        or session.get(IngestMeta, 1) is not None
    )
    if imported:
        return gates

    ar = ar_subledger(session, as_of)
    ar_gl = ledger_balance(session, AR_CONTROL, as_of)
    gates.append(
        Gate(
            "ar_subledger",
            subledger_total(ar) == ar_gl,
            f"subledger {subledger_total(ar)} gl {ar_gl} parties {len(ar)}",
        )
    )

    ap = ap_subledger(session, as_of)
    ap_gl = money(-ledger_balance(session, AP_CONTROL, as_of))
    gates.append(
        Gate(
            "ap_subledger",
            subledger_total(ap) == ap_gl,
            f"subledger {subledger_total(ap)} gl {ap_gl} parties {len(ap)}",
        )
    )

    inv_gl = ledger_balance(session, INVENTORY, as_of)
    inv_stock = stock_value(session, as_of)
    gates.append(Gate("inventory_value", inv_stock == inv_gl, f"stock {inv_stock} gl {inv_gl}"))
    gates.append(
        Gate(
            "no_negative_stock",
            stock_quantity(session, as_of) >= ZERO,
            f"total qty {stock_quantity(session, as_of)}",
        )
    )

    customers = list(session.scalars(select(Customer)).all())
    vendors = list(session.scalars(select(Vendor)).all())
    products = list(session.scalars(select(Product)).all())
    gstin_ok = all(c.gstin and is_valid_gstin(c.gstin) for c in customers) and all(
        v.gstin and is_valid_gstin(v.gstin) for v in vendors
    )
    gates.append(
        Gate(
            "gstin_checksum",
            gstin_ok,
            f"customers {len(customers)} vendors {len(vendors)}",
        )
    )
    hsn_ok = all(p.hsn for p in products)
    gates.append(Gate("product_hsn", hsn_ok, f"products {len(products)}"))

    scale = cfg["scale"]
    counts_ok = (
        len(customers) == int(scale["customers"])
        and len(vendors) == int(scale["vendors"])
        and len(products) == int(scale["products"])
    )
    gates.append(
        Gate(
            "master_counts",
            counts_ok,
            f"customers {len(customers)} vendors {len(vendors)} products {len(products)}",
        )
    )

    bill_count = int(
        session.scalar(
            select(func.count()).select_from(PurchaseBill).where(PurchaseBill.bill_date <= as_of)
        )
        or 0
    )
    cgst_bills = money(
        session.scalar(
            select(func.coalesce(func.sum(PurchaseBill.cgst), 0)).where(
                PurchaseBill.bill_date <= as_of
            )
        )
        or 0
    )
    sgst_bills = money(
        session.scalar(
            select(func.coalesce(func.sum(PurchaseBill.sgst), 0)).where(
                PurchaseBill.bill_date <= as_of
            )
        )
        or 0
    )
    igst_bills = money(
        session.scalar(
            select(func.coalesce(func.sum(PurchaseBill.igst), 0)).where(
                PurchaseBill.bill_date <= as_of
            )
        )
        or 0
    )
    gates.append(
        Gate(
            "input_gst",
            cgst_bills
            == voucher_account_net(session, INPUT_CGST, as_of, (VoucherType.PURCHASE.value,))
            and sgst_bills
            == voucher_account_net(session, INPUT_SGST, as_of, (VoucherType.PURCHASE.value,))
            and igst_bills
            == voucher_account_net(session, INPUT_IGST, as_of, (VoucherType.PURCHASE.value,)),
            f"bills cgst {cgst_bills} sgst {sgst_bills} igst {igst_bills} count {bill_count}",
        )
    )
    books_end = date.fromisoformat(str(cfg["calendar"]["books_end"]))
    purchase_target = int(cfg["volumes"]["purchase_invoices"])
    if as_of >= books_end:
        gates.append(
            Gate(
                "purchase_count",
                bill_count == purchase_target,
                f"{bill_count} of {purchase_target}",
            )
        )

    invoice_count = int(
        session.scalar(
            select(func.count()).select_from(SalesInvoice).where(SalesInvoice.invoice_date <= as_of)
        )
        or 0
    )
    cgst_sales = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.cgst), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    sgst_sales = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.sgst), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    igst_sales = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.igst), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    taxable_sales = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.taxable), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    cogs_sales = money(
        session.scalar(
            select(func.coalesce(func.sum(SalesInvoice.cogs), 0)).where(
                SalesInvoice.invoice_date <= as_of
            )
        )
        or 0
    )
    gates.append(
        Gate(
            "output_gst",
            cgst_sales
            == money(-voucher_account_net(session, OUTPUT_CGST, as_of, (VoucherType.SALE.value,)))
            and sgst_sales
            == money(-voucher_account_net(session, OUTPUT_SGST, as_of, (VoucherType.SALE.value,)))
            and igst_sales
            == money(-voucher_account_net(session, OUTPUT_IGST, as_of, (VoucherType.SALE.value,))),
            f"invoices cgst {cgst_sales} sgst {sgst_sales} igst {igst_sales} count {invoice_count}",
        )
    )
    gates.append(
        Gate(
            "sales_and_cogs",
            taxable_sales
            == money(-voucher_account_net(session, SALES, as_of, (VoucherType.SALE.value,)))
            and cogs_sales == voucher_account_net(session, COGS, as_of, (VoucherType.SALE.value,)),
            f"taxable {taxable_sales} cogs {cogs_sales}",
        )
    )
    sales_target = int(cfg["volumes"]["sales_invoices"])
    if as_of >= books_end:
        gates.append(
            Gate(
                "sales_count",
                invoice_count == sales_target,
                f"{invoice_count} of {sales_target}",
            )
        )

    receipt_count = int(
        session.scalar(
            select(func.count()).select_from(Receipt).where(Receipt.receipt_date <= as_of)
        )
        or 0
    )
    payment_count = int(
        session.scalar(
            select(func.count()).select_from(Payment).where(Payment.payment_date <= as_of)
        )
        or 0
    )
    receipt_target = int(cfg["volumes"]["receipts"])
    payment_target = int(cfg["volumes"]["payments"])
    if as_of >= books_end:
        gates.append(
            Gate(
                "receipt_count",
                receipt_count >= int(receipt_target * 0.90),
                f"{receipt_count} of {receipt_target}",
            )
        )
        payment_needed = int(payment_target * 0.90)
        payment_ok = payment_count >= payment_needed
        payment_detail = f"{payment_count} of {payment_target}"
        if not payment_ok:
            od_cap = money(cfg["accounting"]["od_limit_inr"])
            exhausted = (
                choose_bank(current_bank_balances(session, as_of), money("10000"), od_cap) is None
            )
            if exhausted:
                payment_ok = True
                payment_detail += " (bank floors stopped further payments)"
        gates.append(Gate("payment_count", payment_ok, payment_detail))

    ar_docs = document_ar_outstanding(session, as_of)
    ap_docs = document_ap_outstanding(session, as_of)
    gates.append(
        Gate(
            "ar_documents",
            ar_docs == ar_gl,
            f"documents {ar_docs} gl {ar_gl}",
        )
    )
    gates.append(
        Gate(
            "ap_documents",
            ap_docs == ap_gl,
            f"documents {ap_docs} gl {ap_gl}",
        )
    )

    ar_age = aging_totals(ar_aging(session, as_of))
    ap_age = aging_totals(ap_aging(session, as_of))
    gates.append(
        Gate(
            "ar_aging",
            ar_age["total"] == ar_gl,
            f"aging {ar_age['total']} gl {ar_gl} "
            f"0-30 {ar_age['0-30']} 31-60 {ar_age['31-60']} 61-90 {ar_age['61-90']} "
            f"91-120 {ar_age['91-120']} 120+ {ar_age['120+']} 90+ {ar_age['90+']}",
        )
    )
    gates.append(
        Gate(
            "ap_aging",
            ap_age["total"] == ap_gl,
            f"aging {ap_age['total']} gl {ap_gl} "
            f"0-30 {ap_age['0-30']} 31-60 {ap_age['31-60']} 61-90 {ap_age['61-90']} "
            f"91-120 {ap_age['91-120']} 120+ {ap_age['120+']} 90+ {ap_age['90+']}",
        )
    )

    opening = cfg["opening"]
    od_limit = money(cfg["accounting"]["od_limit_inr"])

    itc_c = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.itc_cgst), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    itc_s = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.itc_sgst), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    itc_i = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.itc_igst), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    cleared_c = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.output_cgst), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    cleared_s = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.output_sgst), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    cleared_i = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.output_igst), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    gst_payable_docs = money(
        session.scalar(
            select(func.coalesce(func.sum(GstSettlement.payable - GstSettlement.paid), 0)).where(
                GstSettlement.settlement_date <= as_of
            )
        )
        or 0
    )
    gates.append(
        Gate(
            "gst_itc",
            money(ledger_balance(session, INPUT_CGST, as_of) + itc_c) == cgst_bills
            and money(ledger_balance(session, INPUT_SGST, as_of) + itc_s) == sgst_bills
            and money(ledger_balance(session, INPUT_IGST, as_of) + itc_i) == igst_bills,
            f"itc cgst {itc_c} sgst {itc_s} igst {itc_i}",
        )
    )
    gates.append(
        Gate(
            "gst_output_cleared",
            cgst_sales == money(-ledger_balance(session, OUTPUT_CGST, as_of) + cleared_c)
            and sgst_sales == money(-ledger_balance(session, OUTPUT_SGST, as_of) + cleared_s)
            and igst_sales == money(-ledger_balance(session, OUTPUT_IGST, as_of) + cleared_i),
            f"cleared cgst {cleared_c} sgst {cleared_s} igst {cleared_i}",
        )
    )
    gates.append(
        Gate(
            "gst_payable",
            gst_payable_docs == money(-ledger_balance(session, GST_PAYABLE, as_of)),
            f"documents {gst_payable_docs} gl {money(-ledger_balance(session, GST_PAYABLE, as_of))}",
        )
    )

    bank_ok = True
    bank_bits: list[str] = []
    for gl, opening_key in (
        (BANK_HDFC, "111000"),
        (BANK_ICICI, "112000"),
        (BANK_OD, "113000"),
    ):
        opening_bal = money(opening.get(opening_key, 0))
        received = money(
            session.scalar(
                select(func.coalesce(func.sum(Receipt.amount), 0)).where(
                    Receipt.bank_gl == gl, Receipt.receipt_date <= as_of
                )
            )
            or 0
        )
        vendor_paid = money(
            session.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0)).where(
                    Payment.bank_gl == gl, Payment.payment_date <= as_of
                )
            )
            or 0
        )
        opex_paid = money(
            session.scalar(
                select(func.coalesce(func.sum(OpexEntry.paid_amount), 0)).where(
                    OpexEntry.bank_gl == gl, OpexEntry.pay_date <= as_of
                )
            )
            or 0
        )
        charges = money(
            session.scalar(
                select(func.coalesce(func.sum(BankCharge.amount), 0)).where(
                    BankCharge.bank_gl == gl,
                    BankCharge.accrued.is_(False),
                    BankCharge.charge_date <= as_of,
                )
            )
            or 0
        )
        emi_paid = money(
            session.scalar(
                select(func.coalesce(func.sum(LoanEmi.principal + LoanEmi.interest), 0)).where(
                    LoanEmi.bank_gl == gl, LoanEmi.emi_date <= as_of
                )
            )
            or 0
        )
        gst_paid = money(
            session.scalar(
                select(func.coalesce(func.sum(GstSettlement.paid), 0)).where(
                    GstSettlement.bank_gl == gl, GstSettlement.settlement_date <= as_of
                )
            )
            or 0
        )
        reconstructed = money(
            opening_bal + received - vendor_paid - opex_paid - charges - emi_paid - gst_paid
        )
        actual = ledger_balance(session, gl, as_of)
        if reconstructed != actual:
            bank_ok = False
        bank_bits.append(f"{gl} recon {reconstructed} gl {actual}")
    hdfc = ledger_balance(session, BANK_HDFC, as_of)
    icici = ledger_balance(session, BANK_ICICI, as_of)
    od = ledger_balance(session, BANK_OD, as_of)
    floors_ok = hdfc >= ZERO and icici >= ZERO and od >= money(-od_limit)
    gates.append(Gate("bank_recon", bank_ok, "; ".join(bank_bits)))
    gates.append(
        Gate(
            "bank_floors",
            floors_ok,
            f"hdfc {hdfc} icici {icici} od {od} limit {od_limit}",
        )
    )

    salary_months = int(
        session.scalar(
            select(func.count())
            .select_from(OpexEntry)
            .where(OpexEntry.kind == "salary", OpexEntry.expense_date <= as_of)
        )
        or 0
    )
    emi_n = int(
        session.scalar(select(func.count()).select_from(LoanEmi).where(LoanEmi.emi_date <= as_of))
        or 0
    )
    gst_n = int(
        session.scalar(
            select(func.count())
            .select_from(GstSettlement)
            .where(GstSettlement.settlement_date <= as_of)
        )
        or 0
    )
    if as_of >= books_end:
        gates.append(Gate("expense_months", salary_months >= 36, f"{salary_months} salary months"))
        gates.append(Gate("emi_count", emi_n >= 36, f"{emi_n} of 36"))
        gates.append(Gate("gst_months", gst_n >= 30, f"{gst_n} settlements"))
        years = len(cfg["calendar"]["fiscal_years"])
        expected_accum = money(
            money(opening.get("161000", 0))
            * money(cfg["accounting"]["furniture_slm_pct"])
            / money("100")
            * years
        )
        accum = money(-ledger_balance(session, ACCUM_DEP_FURNITURE, as_of))
        gates.append(
            Gate(
                "depreciation", accum == expected_accum, f"accum {accum} expected {expected_accum}"
            )
        )
        pl_open = any(row.account_type in {"income", "expense"} for row in rows)
        closed_n = int(
            session.scalar(
                select(func.count())
                .select_from(Voucher)
                .where(Voucher.voucher_type == VoucherType.CLOSING.value)
            )
            or 0
        )
        gates.append(
            Gate(
                "year_closed",
                (not pl_open) and closed_n >= years,
                f"closing vouchers {closed_n} pl_open {pl_open}",
            )
        )

    metrics = scenario_metrics(session, as_of, cfg)
    ok, detail = signal_holds(metrics, cfg)
    gates.append(Gate("scenario_signal", ok, detail))
    recorded = session.get(ScenarioMeta, str(cfg["generator"]["scenario"]))
    expected = GOLDEN[str(cfg["generator"]["scenario"])]["golden"]
    if recorded is None:
        gates.append(Gate("scenario_golden", True, "no scenario_meta row"))
    else:
        gates.append(
            Gate(
                "scenario_golden",
                recorded.golden_explanation == expected,
                recorded.golden_explanation[:80],
            )
        )
    return gates
