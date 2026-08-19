from __future__ import annotations

from dataclasses import dataclass

BRANDS = (
    "Voltara",
    "InduSwitch",
    "CablePro",
    "LiteForge",
    "MotorHaus",
    "PanelCraft",
    "GridLine",
)

CUSTOMER_PREFIXES = (
    "Aarav",
    "Narmada",
    "Sahyadri",
    "Deccan",
    "Western",
    "Pioneer",
    "Summit",
    "Orbit",
    "Kaveri",
    "Godavari",
    "Shakti",
    "Navrang",
    "Prithvi",
    "Ujjwal",
    "Sagar",
    "Metro",
    "Horizon",
    "Vertex",
    "Anvil",
    "Beacon",
)

CUSTOMER_SUFFIXES = (
    "Electricals Pvt Ltd",
    "Switchgear Traders",
    "Industrial Supplies",
    "Power Solutions",
    "Cables & Conductors",
    "Engineering Co",
    "Agencies",
    "Enterprises",
    "Lighting House",
    "Panel Builders",
    "Contractors",
    "Distributors",
)

VENDOR_PREFIXES = (
    "Bharat",
    "National",
    "Prime",
    "Apex",
    "Sterling",
    "Universal",
    "Eastern",
    "Continental",
    "Reliable",
    "Precision",
)

VENDOR_SUFFIXES = (
    "Switchgear Works",
    "Cable Mills",
    "Lamp Components",
    "Motor Industries",
    "Copper Products",
    "Insulation Co",
    "Engineering Ltd",
    "Polymers Pvt Ltd",
)

INDUSTRIES = (
    "electrical_contractor",
    "oem",
    "retailer",
    "panel_builder",
    "industrial",
    "builder",
    "government",
    "trader",
)

FIRST_NAMES = (
    "Amit",
    "Priya",
    "Rahul",
    "Sneha",
    "Vikram",
    "Neha",
    "Sanjay",
    "Kavita",
    "Rohan",
    "Meera",
    "Anil",
    "Pooja",
    "Kiran",
    "Deepak",
    "Ananya",
    "Manoj",
    "Isha",
    "Nitin",
    "Shreya",
    "Ajay",
)

LAST_NAMES = (
    "Sharma",
    "Patil",
    "Kulkarni",
    "Deshmukh",
    "Joshi",
    "Reddy",
    "Nair",
    "Iyer",
    "Khan",
    "Singh",
    "Mehta",
    "Gupta",
    "Jadhav",
    "Kamble",
    "Pillai",
    "Banerjee",
)

DEPARTMENTS = (
    ("Management", 5, 80000, 160000, "CC-MGT"),
    ("Sales", 18, 22000, 55000, "CC-SALES"),
    ("Warehouse", 10, 18000, 28000, "CC-WH"),
    ("Accounts", 6, 25000, 45000, "CC-ACC"),
    ("Purchase", 5, 25000, 48000, "CC-PUR"),
    ("Admin", 6, 18000, 35000, "CC-ADM"),
)

BRANCHES = (
    ("BR01", "Pune HQ", "Pune", "27"),
    ("BR02", "Mumbai Branch", "Mumbai", "27"),
    ("BR03", "Nashik Branch", "Nashik", "27"),
    ("BR04", "Nagpur Branch", "Nagpur", "27"),
    ("BR05", "Aurangabad Branch", "Aurangabad", "27"),
)

WAREHOUSES = (
    ("WH-PUN", "Pune Central Warehouse", "BR01"),
    ("WH-MUM", "Mumbai Warehouse", "BR02"),
    ("WH-NGP", "Nagpur Warehouse", "BR04"),
)

COST_CENTRES = (
    ("CC-HO", "Head Office", "admin"),
    ("CC-SALES", "Sales", "sales"),
    ("CC-WH", "Warehousing", "ops"),
    ("CC-PUR", "Purchase", "ops"),
    ("CC-ACC", "Accounts", "finance"),
    ("CC-ADM", "Administration", "admin"),
    ("CC-MGT", "Management", "admin"),
    ("CC-BR02", "Mumbai Branch", "sales"),
    ("CC-BR03", "Nashik Branch", "sales"),
    ("CC-BR04", "Nagpur Branch", "sales"),
    ("CC-BR05", "Aurangabad Branch", "sales"),
    ("CC-SVC", "Service", "ops"),
    ("CC-PRJ", "Projects", "ops"),
    ("CC-LOG", "Logistics", "ops"),
    ("CC-QA", "Quality", "ops"),
)


@dataclass(frozen=True)
class ProductBlueprint:
    name: str
    category: str
    hsn: str
    gst_rate: str
    cost_lo: int
    cost_hi: int
    margin_lo: float
    margin_hi: float
    uom: str = "NOS"


def product_blueprints(count: int = 350) -> list[ProductBlueprint]:
    items: list[ProductBlueprint] = []

    def add(
        name: str,
        category: str,
        hsn: str,
        gst: str,
        cost_lo: int,
        cost_hi: int,
        margin_lo: float = 1.18,
        margin_hi: float = 1.32,
        uom: str = "NOS",
    ) -> None:
        items.append(
            ProductBlueprint(name, category, hsn, gst, cost_lo, cost_hi, margin_lo, margin_hi, uom)
        )

    for brand in BRANDS:
        for amp in (6, 10, 16, 20, 25, 32, 40, 63):
            add(f"{brand} MCB {amp}A SP", "switchgear", "8536", "18.00", 80, 420)
            add(f"{brand} MCB {amp}A TP", "switchgear", "8536", "18.00", 220, 980)
        for amp in (25, 40, 63):
            add(f"{brand} RCCB {amp}A 30mA", "switchgear", "8536", "18.00", 900, 2800)
        for amp in (9, 12, 18, 25, 32):
            add(f"{brand} Contactor {amp}A", "switchgear", "8536", "18.00", 450, 3200)

    for brand in BRANDS:
        for size in ("1.0", "1.5", "2.5", "4.0", "6.0", "10.0"):
            add(
                f"{brand} House Wire {size} sqmm 90m",
                "wires",
                "8544",
                "18.00",
                700,
                4500,
                uom="COIL",
            )
        for size in ("2C", "3C", "4C"):
            add(
                f"{brand} Armoured Cable 4 sqmm {size}",
                "cables",
                "8544",
                "18.00",
                1800,
                9000,
                uom="MTR",
            )
        for watt in (9, 12, 18, 20, 36, 40):
            add(f"{brand} LED Panel {watt}W", "lighting", "9405", "12.00", 180, 1400)
        for watt in (20, 30, 50, 100):
            add(f"{brand} LED Street Light {watt}W", "lighting", "9405", "12.00", 650, 4200)

    for brand in ("MotorHaus", "GridLine", "Voltara"):
        for hp in ("0.5", "1.0", "2.0", "3.0", "5.0", "7.5", "10.0"):
            add(f"{brand} Induction Motor {hp} HP", "motors", "8501", "18.00", 3500, 28000)
        for kva in ("1", "2", "3", "5", "10"):
            add(
                f"{brand} Isolation Transformer {kva} kVA",
                "transformers",
                "8504",
                "18.00",
                4200,
                22000,
            )

    for brand in ("PanelCraft", "InduSwitch", "Voltara"):
        for size in ("4way", "8way", "12way", "16way"):
            add(f"{brand} TPN DB {size}", "panels", "8537", "18.00", 1200, 6500)
        add(f"{brand} Changeover 63A", "switchgear", "8536", "18.00", 1800, 5200)
        add(f"{brand} Changeover 125A", "switchgear", "8536", "18.00", 4200, 9800)
        add(f"{brand} Busbar Chamber 200A", "panels", "8537", "18.00", 3500, 11000)

    for brand in ("CablePro", "GridLine"):
        for size in ("16", "20", "25", "32"):
            add(f"{brand} PVC Conduit {size}mm 3m", "conduits", "3917", "18.00", 40, 180)
        for size in ("4", "6", "10", "16"):
            add(f"{brand} Cable Gland {size}mm", "accessories", "8538", "18.00", 15, 90)

    for brand in BRANDS[:4]:
        add(f"{brand} Digital Energy Meter 1Ph", "meters", "9028", "18.00", 700, 1800)
        add(f"{brand} Digital Energy Meter 3Ph", "meters", "9028", "18.00", 1800, 4200)
        add(f"{brand} Capacitor 5 kVAr", "power_factor", "8532", "18.00", 900, 2200)
        add(f"{brand} Capacitor 10 kVAr", "power_factor", "8532", "18.00", 1500, 3600)
        add(f"{brand} Industrial Plug 32A", "accessories", "8536", "18.00", 180, 650)
        add(f"{brand} Industrial Socket 32A", "accessories", "8536", "18.00", 180, 650)

    # A few higher-rate items so GST mix is not 18% only.
    add("PanelCraft ACB 630A", "switchgear", "8536", "18.00", 45000, 85000, 1.16, 1.22)
    add("LiteForge Flood Light 200W", "lighting", "9405", "12.00", 2800, 5200)
    add("GridLine HT Cable 11kV 3C 95 sqmm", "cables", "8544", "18.00", 22000, 48000, uom="MTR")

    unique: dict[str, ProductBlueprint] = {}
    for item in items:
        unique.setdefault(item.name, item)
    selected = list(unique.values())[:count]
    if len(selected) < count:
        raise RuntimeError(f"Only {len(selected)} unique product blueprints, need {count}")
    return selected
