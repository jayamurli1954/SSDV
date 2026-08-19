from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.activity import voucher_account_net
from ssdv.accounting.equation import EquationSnapshot, accounting_equation
from ssdv.accounting.trial_balance import ledger_balance, trial_balance
from ssdv.cash.aging import aging_totals, ap_aging, ar_aging
from ssdv.cash.banks import current_bank_balances
from ssdv.cash.parties import PartyExposure, customer_vendor_tops
from ssdv.fy import fy_code, fy_start
from ssdv.gl import (
    AP_CONTROL,
    AR_CONTROL,
    BANK_HDFC,
    BANK_ICICI,
    BANK_OD,
    COGS,
    GST_PAYABLE,
    INVENTORY,
    SALARY_PAYABLE,
    SALES,
    TERM_LOAN,
)
from ssdv.mis.policy import DSO_DAYS_MAX
from ssdv.mis.series import MonthlySeries, monthly_activity
from ssdv.models import (
    Account,
    IngestMeta,
    JournalLine,
    Payment,
    PurchaseBill,
    Receipt,
    Voucher,
    VoucherType,
)
from ssdv.money import ZERO, money
from ssdv.paths import load_company
from ssdv.scenarios.metrics import ScenarioMetrics, scenario_metrics, signal_holds
from ssdv.scenarios.spec import GOLDEN, apply_scenario

_CURRENT_ASSET_SUBTYPES = frozenset({"cash", "bank", "debtor", "inventory", "gst_input", "other"})
_CURRENT_LIABILITY_SUBTYPES = frozenset({"creditor", "gst_output", "other"})


def _current_position(session: Session, as_of: date) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Current assets / liabilities and GST input / output from postable TB rows. Term loan is excluded."""
    assets = ZERO
    liabilities = ZERO
    gst_input = ZERO
    gst_output = ZERO
    for row in trial_balance(session, as_of):
        if row.account_type == "asset" and row.subtype in _CURRENT_ASSET_SUBTYPES:
            assets += money(row.debit - row.credit)
        elif row.account_type == "liability" and row.subtype in _CURRENT_LIABILITY_SUBTYPES:
            liabilities += money(row.credit - row.debit)
        if row.subtype == "gst_input":
            gst_input += money(row.debit - row.credit)
        elif row.subtype == "gst_output":
            gst_output += money(row.credit - row.debit)
    return money(assets), money(liabilities), money(gst_input), money(gst_output)


def _ratio(part: Decimal, whole: Decimal) -> Decimal:
    if whole <= ZERO:
        return ZERO
    return (part / whole).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _turnover_days(balance: Decimal, flow: Decimal, days: int) -> int | None:
    if flow <= ZERO or days <= 0:
        return None
    raw = balance / flow * Decimal(days)
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _shift_year(d: date, years: int) -> date:
    try:
        return date(d.year + years, d.month, d.day)
    except ValueError:
        return date(d.year + years, d.month, 28)


def _period_expense_net(session: Session, start: date, end: date) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
        .join(Voucher, Voucher.id == JournalLine.voucher_id)
        .join(Account, Account.code == JournalLine.account_code)
        .where(Account.type == "expense")
        .where(Account.code != COGS)
        .where(Voucher.voucher_date >= start)
        .where(Voucher.voucher_date <= end)
        .where(Voucher.voucher_type != VoucherType.CLOSING.value)
    )
    return money(session.scalar(stmt) or 0)


def _sum_bills(session: Session, start: date, end: date) -> Decimal:
    return money(
        session.scalar(
            select(func.coalesce(func.sum(PurchaseBill.taxable), 0)).where(
                PurchaseBill.bill_date >= start,
                PurchaseBill.bill_date <= end,
            )
        )
        or 0
    )


def _sum_receipts(session: Session, start: date, end: date) -> Decimal:
    return money(
        session.scalar(
            select(func.coalesce(func.sum(Receipt.amount), 0)).where(
                Receipt.receipt_date >= start,
                Receipt.receipt_date <= end,
            )
        )
        or 0
    )


def _sum_payments(session: Session, start: date, end: date) -> Decimal:
    return money(
        session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.payment_date >= start,
                Payment.payment_date <= end,
            )
        )
        or 0
    )


def _receipts_for_period(session: Session, start: date, end: date) -> Decimal:
    docs = _sum_receipts(session, start, end)
    if docs > ZERO:
        return docs
    return money(
        -voucher_account_net(
            session,
            AR_CONTROL,
            end,
            (VoucherType.RECEIPT.value,),
            since=start,
        )
    )


def _payments_for_period(session: Session, start: date, end: date) -> Decimal:
    docs = _sum_payments(session, start, end)
    if docs > ZERO:
        return docs
    return voucher_account_net(
        session,
        AP_CONTROL,
        end,
        (VoucherType.PAYMENT.value,),
        since=start,
    )


def _plan_for_fy(company: dict, fy: str) -> Decimal:
    for year in company["calendar"]["fiscal_years"]:
        if str(year["code"]) == fy:
            return money(year["revenue_inr"])
    return ZERO


@dataclass(frozen=True)
class PeriodPnl:
    start: date
    end: date
    fy_code: str
    days: int
    sales: Decimal
    cogs: Decimal
    gross_margin: Decimal
    gm_pct: Decimal
    opex: Decimal
    purchases: Decimal
    receipts: Decimal
    payments: Decimal
    plan: Decimal


@dataclass(frozen=True)
class MisSnapshot:
    as_of: date
    scenario_id: str
    title: str
    known_cause: str
    golden: str
    company_name: str
    fy: PeriodPnl
    prior: PeriodPnl | None
    sales_growth: Decimal | None
    equation: EquationSnapshot
    ar: Decimal
    ap: Decimal
    inventory: Decimal
    cash: Decimal
    hdfc: Decimal
    icici: Decimal
    od: Decimal
    od_limit: Decimal
    od_utilisation: Decimal
    gst_payable: Decimal
    salary_payable: Decimal
    term_loan: Decimal
    dso: int | None
    dio: int | None
    dpo: int | None
    ccc: int | None
    ar_aging: dict[str, Decimal]
    ap_aging: dict[str, Decimal]
    overdue_customers: tuple[PartyExposure, ...]
    customer_rank: str
    vendor_exposure: tuple[PartyExposure, ...]
    metrics: ScenarioMetrics
    signal_ok: bool
    signal_detail: str
    series: MonthlySeries
    current_assets: Decimal
    current_liabilities: Decimal
    gst_input: Decimal
    gst_output: Decimal
    msme_43bh_total: Decimal

    @property
    def gm_pct(self) -> Decimal:
        return self.fy.gm_pct

    @property
    def equity(self) -> Decimal:
        return self.equation.equity

    @property
    def ytd_profit(self) -> Decimal:
        return money(self.fy.sales - self.fy.cogs - self.fy.opex)

    @property
    def monthly_profit(self) -> Decimal:
        if not self.series.sales:
            return ZERO
        return money(self.series.sales[-1] - self.series.cogs[-1] - self.series.opex[-1])

    @property
    def working_capital(self) -> Decimal:
        """Operating WC: AR + inventory - AP. Cash is a separate CEO tile."""
        return money(self.ar + self.inventory - self.ap)

    @property
    def collection_efficiency(self) -> Decimal:
        return _ratio(self.fy.receipts, self.fy.sales)

    @property
    def current_ratio(self) -> Decimal:
        return _ratio(self.current_assets, self.current_liabilities)

    @property
    def quick_ratio(self) -> Decimal:
        return _ratio(money(self.cash + self.ar), self.current_liabilities)

    @property
    def monthly_net_cash(self) -> Decimal:
        if not self.series.receipts:
            return ZERO
        return money(self.series.receipts[-1] - self.series.payments[-1])

    @property
    def cash_blocked_90(self) -> Decimal:
        return money(self.ar_aging.get("90+", ZERO))

    @property
    def dso_policy_gap_ar(self) -> Decimal | None:
        """AR implied by DSO days above the 120-day policy. None if DSO is missing or within policy."""
        if self.dso is None or self.dso <= DSO_DAYS_MAX or self.dso <= 0:
            return None
        extra = Decimal(self.dso - DSO_DAYS_MAX) / Decimal(self.dso)
        return money(self.ar * extra)

    @property
    def gst_net(self) -> Decimal:
        if self.gst_input != ZERO or self.gst_output != ZERO:
            return money(self.gst_output - self.gst_input)
        return self.gst_payable


def _period_pnl(session: Session, company: dict, start: date, end: date) -> PeriodPnl:
    fy = fy_code(end)
    days = (end - start).days + 1
    sales = money(
        -voucher_account_net(
            session,
            SALES,
            end,
            (VoucherType.SALE.value,),
            since=start,
        )
    )
    cogs = voucher_account_net(
        session,
        COGS,
        end,
        (VoucherType.SALE.value,),
        since=start,
    )
    gross = money(sales - cogs)
    gm_pct = _ratio(gross, sales)
    return PeriodPnl(
        start=start,
        end=end,
        fy_code=fy,
        days=days,
        sales=sales,
        cogs=cogs,
        gross_margin=gross,
        gm_pct=gm_pct,
        opex=_period_expense_net(session, start, end),
        purchases=_sum_bills(session, start, end),
        receipts=_receipts_for_period(session, start, end),
        payments=_payments_for_period(session, start, end),
        plan=_plan_for_fy(company, fy),
    )


def mis_snapshot(
    session: Session,
    as_of: date,
    company: dict | None = None,
) -> MisSnapshot:
    cfg = company or apply_scenario(load_company(), str(load_company()["generator"]["scenario"]))
    ingest = session.get(IngestMeta, 1)
    if ingest is not None:
        cfg = apply_scenario(cfg, "imported")
        cfg["company"]["legal_name"] = ingest.company_name
        cfg["calendar"]["books_start"] = ingest.first_date.isoformat()
        cfg["calendar"]["books_end"] = ingest.last_date.isoformat()
    sid = str(cfg["generator"]["scenario"])
    meta = GOLDEN[sid]
    start = fy_start(as_of)
    fy = _period_pnl(session, cfg, start, as_of)

    prior: PeriodPnl | None = None
    prior_as_of = _shift_year(as_of, -1)
    books_start = date.fromisoformat(str(cfg["calendar"]["books_start"]))
    if prior_as_of >= books_start:
        prior = _period_pnl(session, cfg, fy_start(prior_as_of), prior_as_of)

    growth: Decimal | None = None
    if prior is not None and prior.sales > ZERO:
        growth = _ratio(fy.sales - prior.sales, prior.sales)

    eq = accounting_equation(session, as_of)
    banks = current_bank_balances(session, as_of)
    hdfc = banks[BANK_HDFC]
    icici = banks[BANK_ICICI]
    od = banks[BANK_OD]
    cash = money(hdfc + icici + od)
    od_limit = money(cfg["accounting"]["od_limit_inr"])
    od_util = ZERO if od_limit <= ZERO else _ratio(money(-od) if od < ZERO else ZERO, od_limit)

    ar = ledger_balance(session, AR_CONTROL, as_of)
    ap = money(-ledger_balance(session, AP_CONTROL, as_of))
    inv = ledger_balance(session, INVENTORY, as_of)
    dso = _turnover_days(ar, fy.sales, fy.days)
    dio = _turnover_days(inv, fy.cogs, fy.days)
    dpo = _turnover_days(ap, fy.purchases, fy.days)
    ccc = None
    if None not in (dso, dio, dpo):
        ccc = int(dso) + int(dio) - int(dpo)

    metrics = scenario_metrics(session, as_of, cfg)
    ok, detail = signal_holds(metrics, cfg)
    series = monthly_activity(session, books_start, as_of)
    current_assets, current_liabilities, gst_input, gst_output = _current_position(session, as_of)
    overdue_customers, customer_rank, vendor_exposure = customer_vendor_tops(session, as_of)
    # 43B(h) analysis: MSME-related overdue payables risk.
    from ssdv.forensics.msme_43bh import msme_43bh_risk

    msme_total, _msme_top = msme_43bh_risk(session, as_of)
    return MisSnapshot(
        as_of=as_of,
        scenario_id=sid,
        title=meta["title"],
        known_cause=meta["known_cause"],
        golden=meta["golden"],
        company_name=str(cfg["company"]["legal_name"]),
        fy=fy,
        prior=prior,
        sales_growth=growth,
        equation=eq,
        ar=ar,
        ap=ap,
        inventory=inv,
        cash=cash,
        hdfc=hdfc,
        icici=icici,
        od=od,
        od_limit=od_limit,
        od_utilisation=od_util,
        gst_payable=money(-ledger_balance(session, GST_PAYABLE, as_of)),
        salary_payable=money(-ledger_balance(session, SALARY_PAYABLE, as_of)),
        term_loan=money(-ledger_balance(session, TERM_LOAN, as_of)),
        dso=dso,
        dio=dio,
        dpo=dpo,
        ccc=ccc,
        ar_aging=aging_totals(ar_aging(session, as_of)),
        ap_aging=aging_totals(ap_aging(session, as_of)),
        overdue_customers=overdue_customers,
        customer_rank=customer_rank,
        vendor_exposure=vendor_exposure,
        metrics=metrics,
        signal_ok=ok,
        signal_detail=detail,
        series=series,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        gst_input=gst_input,
        gst_output=gst_output,
        msme_43bh_total=msme_total,
    )
