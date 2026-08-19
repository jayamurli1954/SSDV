from __future__ import annotations

import random
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.accounting.coa import load_coa
from ssdv.accounting.posting import LineDraft, PostingRequest, post
from ssdv.gl import AP_CONTROL, AR_CONTROL
from ssdv.inventory.stock import record_stock_move
from ssdv.masters.generate import generate_all_masters
from ssdv.masters.opening_alloc import (
    allocate_opening_ap,
    allocate_opening_ar,
    allocate_opening_stock,
)
from ssdv.models import BankMaster, StockMove, Voucher, VoucherType
from ssdv.money import ZERO, money
from ssdv.paths import load_company, opening_entries


def seed_banks(session: Session, company: dict | None = None) -> int:
    cfg = company or load_company()
    created = 0
    for row in cfg.get("banks", []):
        code = row["code"]
        if session.get(BankMaster, code) is None:
            od = row.get("od_limit_inr")
            session.add(
                BankMaster(
                    code=code,
                    name=row["name"],
                    gl_code=str(row["gl_code"]),
                    ifsc=row.get("ifsc"),
                    account_no=row.get("account_no"),
                    od_limit=money(od) if od is not None else None,
                )
            )
            created += 1
    session.flush()
    return created


def _opening_rng(cfg: dict[str, Any], salt: int = 17) -> random.Random:
    return random.Random(int(cfg["generator"]["seed"]) + salt)


def post_opening(
    session: Session,
    company: dict | None = None,
    rng: random.Random | None = None,
) -> Voucher | None:
    cfg = company or load_company()
    existing = session.scalar(
        select(Voucher).where(Voucher.voucher_type == VoucherType.OPENING.value)
    )
    if existing is not None:
        return existing

    rng = rng or _opening_rng(cfg, 17)
    as_of = date.fromisoformat(str(cfg["opening_as_of"]))
    skip = {AR_CONTROL, AP_CONTROL}
    lines: list[LineDraft] = []
    for code, debit, credit in opening_entries(cfg):
        if code in skip or (debit == ZERO and credit == ZERO):
            continue
        lines.append(LineDraft(account_code=code, debit=debit, credit=credit))

    for customer, amount in allocate_opening_ar(session, rng, cfg):
        lines.append(
            LineDraft(
                account_code=AR_CONTROL,
                debit=amount,
                party_type="customer",
                party_code=customer.code,
                line_narration=f"Opening AR {customer.code}",
            )
        )
    for vendor, amount in allocate_opening_ap(session, rng, cfg):
        lines.append(
            LineDraft(
                account_code=AP_CONTROL,
                credit=amount,
                party_type="vendor",
                party_code=vendor.code,
                line_narration=f"Opening AP {vendor.code}",
            )
        )

    return post(
        session,
        PostingRequest(
            voucher_date=as_of,
            voucher_type=VoucherType.OPENING,
            narration="Opening balances as at books start",
            lines=lines,
            source="opening",
            scenario=cfg.get("generator", {}).get("scenario"),
        ),
    )


def post_opening_stock(
    session: Session,
    voucher: Voucher,
    company: dict | None = None,
    rng: random.Random | None = None,
) -> int:
    existing = session.scalar(
        select(func.count()).select_from(StockMove).where(StockMove.move_type == "OPENING")
    )
    if int(existing or 0) > 0:
        return 0
    cfg = company or load_company()
    rng = rng or _opening_rng(cfg, 31)
    rows = allocate_opening_stock(session, rng, cfg)
    for product, warehouse, qty, rate, value in rows:
        record_stock_move(
            session,
            move_date=voucher.voucher_date,
            product_code=product.code,
            warehouse_code=warehouse.code,
            qty_in=qty,
            qty_out=ZERO,
            rate=rate,
            value=value,
            voucher_id=voucher.id,
            move_type="OPENING",
        )
    session.flush()
    return len(rows)


def bootstrap_books(session: Session, company: dict | None = None) -> Voucher:
    cfg = company or load_company()
    load_coa(session)
    seed_banks(session, cfg)
    generate_all_masters(session, cfg)
    voucher = post_opening(session, cfg)
    if voucher is None:
        raise RuntimeError("Opening voucher was not posted")
    post_opening_stock(session, voucher, cfg)
    return voucher
