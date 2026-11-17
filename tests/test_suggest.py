from datetime import date
from pathlib import Path

import pytest

from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.ingest import IngestError
from ssdv.ingest.suggest import (
    GUESSED,
    MAPPED,
    UNMAPPED,
    confirm_map,
    effective_map,
    ledger_map_path,
    load_source_lines,
    needs_review,
    postable_chart,
    review_ledgers,
    suggest_codes,
)
from ssdv.mis import mis_snapshot
from ssdv.money import money
from ssdv.officemitra.setup_flow import review_mapping, save_confirmed_map
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"

CSV = """voucher_id,date,voucher_type,account,debit,credit,party_type,party,narration
OPEN-1,2024-04-01,OPENING,111000,500000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,Proprietor Capital,0,500000.00,,,Opening
EXP-1,2024-04-30,EXPENSE,Office Rent Paid,20000.00,0,,,April rent
EXP-1,2024-04-30,EXPENSE,111000,0,20000.00,,,April rent
EXP-2,2024-04-30,EXPENSE,Zebra Sundries,500.00,0,,,Misc
EXP-2,2024-04-30,EXPENSE,111000,0,500.00,,,Misc
"""

TALLY_XML = """<?xml version="1.0" encoding="utf-8"?>
<ENVELOPE><BODY><DATA><TALLYMESSAGE>
  <VOUCHER>
    <VCHTYPE>Sales</VCHTYPE>
    <VCHDATE>2024-04-01</VCHDATE>
    <VOUCHERNUMBER>1</VOUCHERNUMBER>
    <NARRATION>Demo sale</NARRATION>
    <PARTYLEDGERNAME>Acme Traders</PARTYLEDGERNAME>
    <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Acme Traders</LEDGERNAME>
      <AMOUNT>100.00</AMOUNT>
      <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
    </ALLLEDGERENTRIES.LIST>
    <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Sales Account</LEDGERNAME>
      <AMOUNT>100.00</AMOUNT>
      <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
    </ALLLEDGERENTRIES.LIST>
  </VOUCHER>
</TALLYMESSAGE></DATA></BODY></ENVELOPE>
"""


def _codes(ledger: str, **kwargs) -> list[str]:
    return [item.code for item in suggest_codes(ledger, postable_chart(), **kwargs)]


def test_keywords_match_whole_words_only() -> None:
    assert _codes("Office Rent Paid")[0] == "620000"
    assert _codes("Staff Salaries & Wages")[0] == "610000"
    assert _codes("Carriage Inward")[0] == "520000"
    # "rent" inside "Current" and "od" inside "Goods" must not trigger a keyword.
    current = suggest_codes("Current Liabilities Misc", postable_chart())
    assert all("Keyword 'rent'" not in item.reason for item in current)
    # The longer phrase outranks the single word it contains.
    assert _codes("Interest on Loan - SBI")[0] == "641000"


def test_party_ledger_suggests_control_account() -> None:
    assert _codes("Acme Traders", party_type="customer")[0] == "120000"
    assert _codes("Bharat Suppliers", party_type="vendor")[0] == "210000"
    assert _codes("Zzqx") == []


def test_review_splits_mapped_guessed_and_unmapped(tmp_path: Path) -> None:
    lines = load_source_lines("generic", EXAMPLE / "journals.csv")
    with_map = review_ledgers(lines, effective_map(tmp_path / "x.sqlite", EXAMPLE / "ledger_map.csv"))
    assert needs_review(with_map) == []
    assert {row.status for row in with_map} == {MAPPED}

    without = {row.ledger: row for row in review_ledgers(lines, {})}
    assert without["Sundry Debtors"].status == GUESSED
    assert without["Sundry Debtors"].proposed == "120000"
    assert without["Capital Account"].status == UNMAPPED
    assert without["Capital Account"].proposed == "310000"
    assert without["Rent"].lines == 1
    assert without["Rent"].debit == money("20000")


def test_confirmed_map_is_saved_and_reused_on_next_import(tmp_path: Path) -> None:
    journals = tmp_path / "journals.csv"
    journals.write_text(CSV, encoding="utf-8")
    db = tmp_path / "ssdv_client.sqlite"

    with pytest.raises(IngestError, match="Unmapped ledger"):
        load_into_vault(db, source="generic", journals=journals, company_name="Client", force=True)

    review = review_mapping(source="generic", journals=journals, account_map=None, db_path=db)
    pending = {row.ledger: row for row in review.pending}
    assert set(pending) == {"Office Rent Paid", "Proprietor Capital", "Zebra Sundries"}
    assert pending["Office Rent Paid"].proposed == "620000"
    assert pending["Proprietor Capital"].proposed == "310000"
    assert pending["Zebra Sundries"].proposed is None

    # A ledger with no choice blocks the save.
    with pytest.raises(IngestError, match="Zebra Sundries"):
        save_confirmed_map(db, review.base_map, {"Zebra Sundries": ""})
    assert not ledger_map_path(db).exists()

    choices = {row.ledger: row.proposed or "626000" for row in review.pending}
    saved = save_confirmed_map(db, review.base_map, choices)
    assert saved == ledger_map_path(db)
    assert effective_map(db) == {
        "Office Rent Paid": "620000",
        "Proprietor Capital": "310000",
        "Zebra Sundries": "626000",
    }

    # No map passed: the saved client map is picked up automatically.
    result = load_into_vault(db, source="generic", journals=journals, company_name="Client", force=True)
    assert result.vouchers == 3
    again = review_mapping(source="generic", journals=journals, account_map=None, db_path=db)
    assert again.pending == []

    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        assert mis_snapshot(session, date(2024, 4, 30)).fy.opex == money("20500")


def test_uploaded_map_overrides_saved_spelling(tmp_path: Path) -> None:
    db = tmp_path / "ssdv_client.sqlite"
    confirm_map(db, {}, {"office rent paid": "626000", "Proprietor Capital": "310000"})
    upload = tmp_path / "map.csv"
    upload.write_text("source,account_code\nOffice Rent Paid,620000\n", encoding="utf-8")
    assert effective_map(db, upload) == {
        "Proprietor Capital": "310000",
        "Office Rent Paid": "620000",
    }


def test_tally_party_ledger_is_reviewed_then_imported_from_pulled_file(tmp_path: Path) -> None:
    xml = tmp_path / "daybook.xml"
    xml.write_text(TALLY_XML, encoding="utf-8")
    db = tmp_path / "ssdv_tally.sqlite"

    review = review_mapping(source="tally-http", journals=xml, account_map=None, db_path=db)
    pending = {row.ledger: row for row in review.pending}
    assert pending["Acme Traders"].status == UNMAPPED
    assert pending["Acme Traders"].proposed == "120000"
    assert "Party ledger" in pending["Acme Traders"].reason

    saved = save_confirmed_map(
        db, review.base_map, {row.ledger: str(row.proposed) for row in review.pending}
    )
    # tally-http with an already-pulled DayBook imports that file; no second pull.
    result = load_into_vault(
        db, source="tally-http", journals=xml, account_map=saved, company_name="Tally Co", force=True
    )
    assert result.source == "tally-http"
    assert result.vouchers == 1
