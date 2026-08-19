from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ssdv.models import Product, StockMove
from ssdv.money import ZERO, money


def stock_quantity(session: Session, as_of: date, product_code: str | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(StockMove.qty_in - StockMove.qty_out), 0)).where(
        StockMove.move_date <= as_of
    )
    if product_code is not None:
        stmt = stmt.where(StockMove.product_code == product_code)
    qty = session.scalar(stmt) or ZERO
    return Decimal(qty)


def stock_value(session: Session, as_of: date, product_code: str | None = None) -> Decimal:
    sign_value = case((StockMove.qty_in > 0, StockMove.value), else_=-StockMove.value)
    stmt = select(func.coalesce(func.sum(sign_value), 0)).where(StockMove.move_date <= as_of)
    if product_code is not None:
        stmt = stmt.where(StockMove.product_code == product_code)
    total = session.scalar(stmt) or ZERO
    return money(total)


def weighted_average_cost(session: Session, product: Product, as_of: date) -> Decimal:
    qty = stock_quantity(session, as_of, product.code)
    if qty <= ZERO:
        return money(product.cost_price)
    return money(stock_value(session, as_of, product.code) / qty)


def record_stock_move(
    session: Session,
    *,
    move_date: date,
    product_code: str,
    warehouse_code: str,
    qty_in: Decimal,
    qty_out: Decimal,
    rate: Decimal,
    value: Decimal,
    voucher_id: int | None,
    move_type: str,
) -> StockMove:
    move = StockMove(
        move_date=move_date,
        product_code=product_code,
        warehouse_code=warehouse_code,
        qty_in=qty_in,
        qty_out=qty_out,
        rate=rate,
        value=value,
        voucher_id=voucher_id,
        move_type=move_type,
    )
    session.add(move)
    return move
