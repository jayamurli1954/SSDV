from collections import Counter
from datetime import date

from sqlalchemy import select

from ssdv.accounting.opening import bootstrap_books
from ssdv.geo import HOME_STATE
from ssdv.gstin import is_valid_gstin
from ssdv.masters.catalog import product_blueprints
from ssdv.models import Customer, Employee, Product, Vendor
from ssdv.paths import load_company


def test_product_catalog_covers_v1_volume() -> None:
    specs = product_blueprints(350)
    assert len(specs) == 350
    assert len({s.name for s in specs}) == 350
    assert all(s.hsn for s in specs)


def test_master_counts_and_gstin(session) -> None:
    bootstrap_books(session)
    cfg = load_company()
    customers = list(session.scalars(select(Customer)).all())
    vendors = list(session.scalars(select(Vendor)).all())
    products = list(session.scalars(select(Product)).all())
    employees = list(session.scalars(select(Employee)).all())

    assert len(customers) == cfg["scale"]["customers"]
    assert len(vendors) == cfg["scale"]["vendors"]
    assert len(products) == cfg["scale"]["products"]
    assert len(employees) == cfg["scale"]["employees"]

    assert all(c.gstin and is_valid_gstin(c.gstin) for c in customers)
    assert all(c.gstin and c.gstin[:2] == c.state_code for c in customers)
    assert all(v.gstin and is_valid_gstin(v.gstin) for v in vendors)
    assert len({c.gstin for c in customers}) == len(customers)
    assert len({v.gstin for v in vendors}) == len(vendors)
    assert all(p.hsn and p.selling_price > p.cost_price for p in products)

    tiers = Counter(c.tier for c in customers)
    assert tiers["core"] == 180
    assert tiers["regular"] == 420
    assert tiers["occasional"] == 600

    home_share = sum(1 for c in customers if c.state_code == HOME_STATE) / len(customers)
    assert 0.55 <= home_share <= 0.65

    assert all(e.joining_date is not None and e.joining_date < date(2023, 4, 1) for e in employees)
