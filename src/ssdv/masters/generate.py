from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ssdv.geo import HOME_STATE, OTHER_STATES, cities
from ssdv.gstin import make_gstin, random_pan
from ssdv.masters.catalog import (
    BRANCHES,
    COST_CENTRES,
    CUSTOMER_PREFIXES,
    CUSTOMER_SUFFIXES,
    DEPARTMENTS,
    FIRST_NAMES,
    INDUSTRIES,
    LAST_NAMES,
    VENDOR_PREFIXES,
    VENDOR_SUFFIXES,
    WAREHOUSES,
    product_blueprints,
)
from ssdv.models import (
    Branch,
    CostCentre,
    Customer,
    Employee,
    Product,
    Vendor,
    Warehouse,
)
from ssdv.money import money
from ssdv.paths import load_company
from ssdv.rng import company_rng


@dataclass(frozen=True)
class MastersSummary:
    branches: int
    warehouses: int
    cost_centres: int
    customers: int
    vendors: int
    products: int
    employees: int
    skipped: bool


def _count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _pick_state(rng: random.Random, home_pct: int) -> str:
    if rng.randint(1, 100) <= home_pct:
        return HOME_STATE
    return rng.choice(OTHER_STATES)


def _unique_name(rng: random.Random, prefixes: tuple[str, ...], suffixes: tuple[str, ...], used: set[str]) -> str:
    for _ in range(5000):
        name = f"{rng.choice(prefixes)} {rng.choice(suffixes)}"
        if rng.random() < 0.35:
            name = f"{name} {rng.choice(cities(HOME_STATE))}"
        if name not in used:
            used.add(name)
            return name
    raise RuntimeError("Could not allocate a unique party name")


def seed_org_units(session: Session) -> None:
    for code, name, city, state_code in BRANCHES:
        if session.get(Branch, code) is None:
            session.add(Branch(code=code, name=name, city=city, state_code=state_code))
    for code, name, branch_code in WAREHOUSES:
        if session.get(Warehouse, code) is None:
            session.add(Warehouse(code=code, name=name, branch_code=branch_code))
    for code, name, kind in COST_CENTRES:
        if session.get(CostCentre, code) is None:
            session.add(CostCentre(code=code, name=name, kind=kind))
    session.flush()


def generate_customers(session: Session, cfg: dict[str, Any], rng: random.Random) -> int:
    target = int(cfg["scale"]["customers"])
    existing = _count(session, Customer)
    if existing >= target:
        return 0

    mix = cfg["customer_mix"]
    n_core = round(target * int(mix["core_pct"]) / 100)
    n_regular = round(target * int(mix["regular_pct"]) / 100)
    n_occasional = target - n_core - n_regular
    tiers = ["core"] * n_core + ["regular"] * n_regular + ["occasional"] * n_occasional
    rng.shuffle(tiers)

    pans: set[str] = set()
    names: set[str] = set()
    branch_codes = [row[0] for row in BRANCHES]
    created = 0
    for i, tier in enumerate(tiers, start=1):
        state = _pick_state(rng, 60)
        fourth = "C" if rng.random() < 0.75 else "P"
        pan = random_pan(rng, fourth=fourth, used=pans)
        if tier == "core":
            credit_limit = money(rng.randint(500_000, 2_500_000))
            credit_days = rng.choice([45, 60, 75])
        elif tier == "regular":
            credit_limit = money(rng.randint(100_000, 500_000))
            credit_days = rng.choice([30, 45])
        else:
            credit_limit = money(rng.randint(25_000, 100_000))
            credit_days = rng.choice([7, 15, 21])
        session.add(
            Customer(
                code=f"CUST{i:04d}",
                name=_unique_name(rng, CUSTOMER_PREFIXES, CUSTOMER_SUFFIXES, names),
                city=rng.choice(cities(state)),
                state_code=state,
                pan=pan,
                gstin=make_gstin(state, pan),
                credit_limit=credit_limit,
                credit_days=credit_days,
                industry=rng.choice(INDUSTRIES),
                tier=tier,
                branch_code=rng.choice(branch_codes),
                is_active=True,
            )
        )
        created += 1
    session.flush()
    return created


def generate_vendors(session: Session, cfg: dict[str, Any], rng: random.Random) -> int:
    target = int(cfg["scale"]["vendors"])
    if _count(session, Vendor) >= target:
        return 0
    pans: set[str] = set()
    names: set[str] = set()
    created = 0
    for i in range(1, target + 1):
        state = _pick_state(rng, 50)
        pan = random_pan(rng, fourth="C", used=pans)
        session.add(
            Vendor(
                code=f"VEND{i:04d}",
                name=_unique_name(rng, VENDOR_PREFIXES, VENDOR_SUFFIXES, names),
                city=rng.choice(cities(state)),
                state_code=state,
                pan=pan,
                gstin=make_gstin(state, pan),
                payment_days=rng.choice([21, 30, 45, 60]),
                lead_time_days=rng.choice([3, 7, 10, 14, 21]),
                is_active=True,
            )
        )
        created += 1
    session.flush()
    return created


def generate_products(session: Session, cfg: dict[str, Any], rng: random.Random) -> int:
    target = int(cfg["scale"]["products"])
    if _count(session, Product) >= target:
        return 0
    created = 0
    for i, spec in enumerate(product_blueprints(target), start=1):
        cost = money(rng.randint(spec.cost_lo, spec.cost_hi))
        margin = spec.margin_lo + rng.random() * (spec.margin_hi - spec.margin_lo)
        selling = money(cost * Decimal(str(round(margin, 4))))
        if selling <= cost:
            selling = money(cost * money("1.18"))
        session.add(
            Product(
                code=f"PROD{i:04d}",
                name=spec.name,
                category=spec.category,
                uom=spec.uom,
                hsn=spec.hsn,
                gst_rate=money(spec.gst_rate),
                cost_price=cost,
                selling_price=selling,
                reorder_level=money(max(5, rng.randint(8, 40))),
                is_active=True,
            )
        )
        created += 1
    session.flush()
    return created


def generate_employees(session: Session, cfg: dict[str, Any], rng: random.Random) -> int:
    target = int(cfg["scale"]["employees"])
    if _count(session, Employee) >= target:
        return 0
    books_start = date.fromisoformat(str(cfg["calendar"]["books_start"]))
    branch_codes = [row[0] for row in BRANCHES]
    seq = 1
    created = 0
    used_names: set[str] = set()
    for department, headcount, lo, hi, cost_centre in DEPARTMENTS:
        for _ in range(headcount):
            if seq > target:
                break
            while True:
                name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                if name not in used_names:
                    used_names.add(name)
                    break
            offset = rng.randint(30, 1800)
            session.add(
                Employee(
                    code=f"EMP{seq:04d}",
                    name=name,
                    department=department,
                    monthly_salary=money(rng.randint(lo, hi)),
                    joining_date=books_start - timedelta(days=offset),
                    branch_code=rng.choice(branch_codes) if department != "Management" else "BR01",
                    cost_centre=cost_centre,
                    is_active=True,
                )
            )
            seq += 1
            created += 1
    if created != target:
        raise RuntimeError(f"Employee template produced {created}, expected {target}")
    session.flush()
    return created


def generate_all_masters(session: Session, company: dict[str, Any] | None = None) -> MastersSummary:
    cfg = company or load_company()
    already = (
        _count(session, Customer) >= int(cfg["scale"]["customers"])
        and _count(session, Vendor) >= int(cfg["scale"]["vendors"])
        and _count(session, Product) >= int(cfg["scale"]["products"])
        and _count(session, Employee) >= int(cfg["scale"]["employees"])
    )
    seed_org_units(session)
    if already:
        return MastersSummary(
            branches=_count(session, Branch),
            warehouses=_count(session, Warehouse),
            cost_centres=_count(session, CostCentre),
            customers=_count(session, Customer),
            vendors=_count(session, Vendor),
            products=_count(session, Product),
            employees=_count(session, Employee),
            skipped=True,
        )
    rng = company_rng(cfg)
    generate_customers(session, cfg, rng)
    generate_vendors(session, cfg, rng)
    generate_products(session, cfg, rng)
    generate_employees(session, cfg, rng)
    return MastersSummary(
        branches=_count(session, Branch),
        warehouses=_count(session, Warehouse),
        cost_centres=_count(session, CostCentre),
        customers=_count(session, Customer),
        vendors=_count(session, Vendor),
        products=_count(session, Product),
        employees=_count(session, Employee),
        skipped=False,
    )
