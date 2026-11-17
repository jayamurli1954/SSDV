from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.ingest import IngestError
from ssdv.ingest.client_chart import (
    client_chart_path,
    load_client_chart,
    parse_tally_ledger_masters,
)
from ssdv.ingest.suggest import ledger_map_path
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.money import money
from ssdv.officemitra.client_view import client_pnl, client_trial_balance
from ssdv.officemitra.export import write_excel
from ssdv.officemitra.quality import enrich_payload
from ssdv.officemitra.setup_flow import review_mapping, save_confirmed_map

AS_OF = date(2024, 4, 30)

# Company A: 4-digit codes, two rent ledgers, SBI bank.
CHART_A = """code,name,group
1001,Cash in Hand,Cash-in-Hand
1101,SBI Current A/c,Bank Accounts
1201,Debtors - Trade,Sundry Debtors
3001,Proprietor Capital,Capital Account
4001,Sales - Domestic,Sales Accounts
6101,Office Rent,Indirect Expenses
6102,Shop Rent,Indirect Expenses
"""
JOURNALS_A = """voucher_id,date,voucher_type,account,debit,credit,party_type,party,narration
OPEN-1,2024-04-01,OPENING,1101,500000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,3001,0,500000.00,,,Opening
SAL-1,2024-04-10,SALE,1201,100000.00,0,customer,CUST-A,Sale
SAL-1,2024-04-10,SALE,4001,0,100000.00,,,Sale
EXP-1,2024-04-30,EXPENSE,6101,20000.00,0,,,Office rent
EXP-1,2024-04-30,EXPENSE,1101,0,20000.00,,,Office rent
EXP-2,2024-04-30,EXPENSE,6102,5000.00,0,,,Shop rent
EXP-2,2024-04-30,EXPENSE,1101,0,5000.00,,,Shop rent
"""
MAP_A = """source,account_code
1101,111000
1201,120000
3001,310000
4001,410000
6101,620000
6102,620000
"""

# Company B: 6-digit codes that collide with standard codes but mean other things.
CHART_B = """code,name,group
110000,HDFC Bank,Bank Accounts
310000,Sales,Sales Accounts
410000,Owner Capital,Capital Account
620000,Electricity,Indirect Expenses
"""
JOURNALS_B = """voucher_id,date,voucher_type,account,debit,credit,party_type,party,narration
OPEN-1,2024-04-01,OPENING,110000,300000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,410000,0,300000.00,,,Opening
SAL-1,2024-04-10,SALE,110000,50000.00,0,,,Cash sale
SAL-1,2024-04-10,SALE,310000,0,50000.00,,,Cash sale
EXP-1,2024-04-30,EXPENSE,620000,4000.00,0,,,Power bill
EXP-1,2024-04-30,EXPENSE,110000,0,4000.00,,,Power bill
"""


def _write(folder: Path, name: str, body: str) -> Path:
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def _snapshot(db: Path):
    engine = make_engine(db)
    create_schema(engine)
    return engine


def test_load_client_chart_reads_codes_names_groups(tmp_path: Path) -> None:
    chart = load_client_chart(_write(tmp_path, "a.csv", CHART_A))
    assert chart.find("1101").name == "SBI Current A/c"
    assert chart.find("sbi current a/c").code == "1101"
    assert chart.find("6102").group == "Indirect Expenses"
    assert chart.has_code("1101") and not chart.has_code("SBI Current A/c")
    with pytest.raises(IngestError, match="repeats code"):
        load_client_chart(_write(tmp_path, "dup.csv", "code,name\n1001,Cash\n1001,Bank\n"))


def test_colliding_client_codes_are_never_read_as_standard_codes(tmp_path: Path) -> None:
    journals = _write(tmp_path, "journals_b.csv", JOURNALS_B)
    chart = _write(tmp_path, "chart_b.csv", CHART_B)
    db = tmp_path / "ssdv_company-b.sqlite"

    # With the client's chart, 110000 is "HDFC Bank", not standard 110000 Cash: stop and ask.
    with pytest.raises(IngestError, match="HDFC Bank"):
        load_into_vault(
            db, source="generic", journals=journals, client_chart=chart, company_name="B", force=True
        )

    review = review_mapping(
        source="generic", journals=journals, account_map=None, db_path=db, client_chart=chart
    )
    pending = {row.ledger: row for row in review.pending}
    assert set(pending) == {"110000", "310000", "410000", "620000"}
    assert pending["110000"].status != "mapped"
    assert pending["110000"].client_name == "HDFC Bank"
    assert pending["110000"].client_group == "Bank Accounts"
    assert pending["110000"].proposed == "111000"
    assert pending["310000"].proposed == "410000"
    assert pending["410000"].proposed == "310000"
    assert pending["620000"].proposed == "621000"

    saved = save_confirmed_map(
        db, review.base_map, {row.ledger: str(row.proposed) for row in review.pending}
    )
    assert saved == ledger_map_path(db)
    load_into_vault(
        db, source="generic", journals=journals, client_chart=chart, company_name="B", force=True
    )
    assert client_chart_path(db).is_file()

    engine = _snapshot(db)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, AS_OF)
        assert snap.fy.sales == money("50000")
        assert snap.hdfc == money("346000")
        assert snap.fy.opex == money("4000")
        tb = {row.client_code: row for row in client_trial_balance(session, AS_OF)}
    assert tb["110000"].client_name == "HDFC Bank"
    assert tb["110000"].standard_code == "111000"
    assert tb["110000"].balance == money("346000")
    assert tb["620000"].standard_code == "621000"

    # Re-import reuses the saved chart and map: nothing to review, same books.
    again = review_mapping(source="generic", journals=journals, account_map=None, db_path=db)
    assert again.pending == []
    load_into_vault(db, source="generic", journals=journals, company_name="B", force=True)
    with session_scope(_snapshot(db)) as session:
        assert mis_snapshot(session, AS_OF).hdfc == money("346000")


def test_two_companies_keep_their_own_charts_and_report_in_them(tmp_path: Path) -> None:
    db_a = tmp_path / "ssdv_company-a.sqlite"
    load_into_vault(
        db_a,
        source="generic",
        journals=_write(tmp_path, "journals_a.csv", JOURNALS_A),
        account_map=_write(tmp_path, "map_a.csv", MAP_A),
        client_chart=_write(tmp_path, "chart_a.csv", CHART_A),
        company_name="Company A",
        force=True,
    )
    engine = _snapshot(db_a)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, AS_OF)
        # KPIs use the standard chart: both rents land in standard Rent.
        assert snap.fy.opex == money("25000")
        pnl = client_pnl(session, AS_OF)
        payload = enrich_payload(snapshot_payload(snap, "all"), session, db_a, AS_OF)

    # The client's own view keeps Office Rent and Shop Rent apart, under their own group.
    expenses = next(b for b in pnl if b["type"] == "expense")
    assert expenses["group"] == "Indirect Expenses"
    assert expenses["total"] == "25000.00"
    assert [(i["client_code"], i["client_name"], i["amount"]) for i in expenses["ledgers"]] == [
        ("6101", "Office Rent", "20000.00"),
        ("6102", "Shop Rent", "5000.00"),
    ]
    income = next(b for b in pnl if b["type"] == "income")
    assert income["group"] == "Sales Accounts"
    assert income["ledgers"][0]["client_name"] == "Sales - Domestic"

    client = payload["client_chart"]
    assert client["tb_total_debit"] == client["tb_total_credit"]
    codes = [row["client_code"] for row in client["trial_balance"]]
    assert codes == ["1101", "1201", "3001", "4001", "6101", "6102"]

    out = tmp_path / "pack.xlsx"
    write_excel(payload, out)
    book = load_workbook(out)
    tb_rows = [[c.value for c in r] for r in book["TB (client chart)"].iter_rows()]
    assert ["1101", "SBI Current A/c", "Bank Accounts", "500000.00", "25000.00", "475000.00", "111000", "HDFC Bank Current"] in tb_rows
    pl_rows = [[c.value for c in r] for r in book["P&L (client chart)"].iter_rows()]
    assert ["expense", "Indirect Expenses", "6102", "Shop Rent", "5000.00", "620000"] in pl_rows


def test_generated_books_have_no_client_chart(session) -> None:
    from ssdv.officemitra.client_view import client_chart_payload

    assert client_chart_payload(session, AS_OF) is None


def test_old_vault_gets_client_ledger_column(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite"
    engine = make_engine(db)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE journal_lines (id INTEGER PRIMARY KEY, voucher_id INTEGER, "
                "line_no INTEGER, account_code VARCHAR(16), debit NUMERIC, credit NUMERIC)"
            )
        )
    create_schema(engine)
    create_schema(engine)
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(journal_lines)"))}
    assert "client_ledger_id" in cols


def test_parse_tally_ledger_list() -> None:
    xml = b"""<ENVELOPE><BODY><DATA><COLLECTION>
      <LEDGER NAME="SBI Current A/c"><PARENT>Bank Accounts</PARENT></LEDGER>
      <LEDGER NAME="Office Rent"><PARENT>Indirect Expenses</PARENT></LEDGER>
      <LEDGER><NAME>Acme Traders</NAME><PARENT>Sundry Debtors</PARENT></LEDGER>
    </COLLECTION></DATA></BODY></ENVELOPE>"""
    chart = parse_tally_ledger_masters(xml)
    assert [(e.name, e.group) for e in chart.entries] == [
        ("SBI Current A/c", "Bank Accounts"),
        ("Office Rent", "Indirect Expenses"),
        ("Acme Traders", "Sundry Debtors"),
    ]
    assert all(e.code is None for e in chart.entries)
    assert chart.find("office rent").group == "Indirect Expenses"



# Company C: four banks of its own plus cash in hand and an overdraft.
CHART_C = """code,name,group
10001,Cash in Hand,Cash-in-Hand
10101,SBI Current A/c,Bank Accounts
10102,Axis Current A/c,Bank Accounts
10103,Kotak Current A/c,Bank Accounts
10201,SBI OD A/c,Bank OD A/c
30001,Partners Capital,Capital Account
"""
JOURNALS_C = """voucher_id,date,voucher_type,account,debit,credit,party_type,party,narration
OPEN-1,2024-04-01,OPENING,10001,10000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,10101,200000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,10102,150000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,10103,50000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,10201,0,80000.00,,,Opening
OPEN-1,2024-04-01,OPENING,30001,0,330000.00,,,Opening
"""
MAP_C = """source,account_code
10001,110000
10101,111000
10102,112000
10103,112000
10201,113000
30001,310000
"""


def test_bank_position_uses_client_bank_names_and_own_od_limit(tmp_path: Path) -> None:
    from ssdv.mis.packs import cfo_pack
    from ssdv.officemitra.quality import budget_sidecar_path

    db = tmp_path / "ssdv_company-c.sqlite"
    load_into_vault(
        db,
        source="generic",
        journals=_write(tmp_path, "journals_c.csv", JOURNALS_C),
        account_map=_write(tmp_path, "map_c.csv", MAP_C),
        client_chart=_write(tmp_path, "chart_c.csv", CHART_C),
        company_name="Company C",
        force=True,
    )
    engine = _snapshot(db)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, AS_OF)
        banks = [(b.label, b.balance) for b in snap.banks]
        # Each client bank keeps its own name and balance, even when two share a slot.
        assert banks == [
            ("Cash in Hand", money("10000")),
            ("SBI Current A/c", money("200000")),
            ("Axis Current A/c", money("150000")),
            ("Kotak Current A/c", money("50000")),
            ("SBI OD A/c", money("-80000")),
        ]
        # Cash in hand counts as cash for imported clients.
        assert snap.cash == money("330000")
        # No limit given: utilisation is not invented from the sample company.
        assert snap.od_limit_known is False
        tiles = {t.id: t for t in cfo_pack(snap).tiles}
        assert tiles["od"].value == "Limit not set"
        notes = " ".join(cfo_pack(snap).notes)
        assert "HDFC" not in notes and "ICICI" not in notes
        assert "SBI Current A/c" in notes and "OD limit not set" in notes
        payload = snapshot_payload(snap, "all")
        assert [b["label"] for b in payload["banks"]][1] == "SBI Current A/c"

    budget_sidecar_path(db).write_text("od_limit: 200000\n", encoding="utf-8")
    with session_scope(engine) as session:
        snap = mis_snapshot(session, AS_OF)
        assert snap.od_limit == money("200000")
        assert snap.od_utilisation == Decimal("0.4")
        assert {t.id: t for t in cfo_pack(snap).tiles}["od"].value == "40.0%"


def test_generated_books_keep_standard_bank_names(session) -> None:
    from ssdv.ingest import ingest_generic
    from ssdv.paths import repo_root

    example = repo_root() / "examples" / "generic_ingest"
    ingest_generic(session, example / "journals.csv", example / "ledger_map.csv", company_name="S")
    snap = mis_snapshot(session, AS_OF)
    # Lines mapped without a client chart show the source ledger text as the name.
    assert [b.label for b in snap.banks] == ["HDFC Bank"]
