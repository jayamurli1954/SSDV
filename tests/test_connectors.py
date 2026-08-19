from datetime import date
from pathlib import Path

from ssdv.cli import main
from ssdv.connectors import (
    list_connectors,
    load_into_vault,
    require_ready,
    source_ids,
)
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.mis import mis_snapshot
from ssdv.money import money
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def test_generic_connector_is_ready() -> None:
    ids = source_ids()
    assert "generic" in ids
    assert "tally" in ids
    assert "mitrabooks" in ids
    require_ready("generic")
    require_ready("tally")
    titles = {item.id: item.title for item in list_connectors()}
    assert "Any ERP" in titles["generic"]


def test_connect_cli_list() -> None:
    assert main(["connect", "--list"]) == 0


def test_connect_cli_writes_sidecar_db(tmp_path: Path) -> None:
    db = tmp_path / "connected.sqlite"
    code = main(
        [
            "--db",
            str(db),
            "connect",
            "--source",
            "generic",
            "--journals",
            str(EXAMPLE / "journals.csv"),
            "--map",
            str(EXAMPLE / "ledger_map.csv"),
            "--name",
            "Connected Traders",
        ]
    )
    assert code == 0
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        mis = mis_snapshot(session, date(2024, 4, 30))
        assert mis.company_name == "Connected Traders"
        assert mis.fy.sales == money("150000")
        assert mis.scenario_id == "imported"


def test_connect_tally_invalid_input_returns_error() -> None:
    # `tally` is wired now, so a missing/invalid file should be an ingest error (code 1)
    assert main(["connect", "--source", "tally", "--journals", "x.csv"]) == 1


def test_load_into_vault_pipeline(tmp_path: Path) -> None:
    db = tmp_path / "vault.sqlite"
    result = load_into_vault(
        db,
        source="generic",
        journals=EXAMPLE / "journals.csv",
        account_map=EXAMPLE / "ledger_map.csv",
        company_name="Pipeline Co",
        force=True,
    )
    assert result.vouchers == 7
    assert result.source == "generic"


def test_load_into_vault_tally_daybook(tmp_path: Path) -> None:
    db = tmp_path / "tally.sqlite"
    xml = tmp_path / "daybook.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<ENVELOPE>
  <BODY>
    <DATA>
      <TALLYMESSAGE>
        <VOUCHER>
          <VCHTYPE>Sales</VCHTYPE>
          <VCHDATE>2024-04-01</VCHDATE>
          <VOUCHERNUMBER>1</VOUCHERNUMBER>
          <NARRATION>Demo sales</NARRATION>
          <PARTYLEDGERNAME>Customer A</PARTYLEDGERNAME>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sundry Debtors</LEDGERNAME>
            <AMOUNT>100.00</AMOUNT>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Sales Account</LEDGERNAME>
            <AMOUNT>100.00</AMOUNT>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>
""",
        encoding="utf-8",
    )

    result = load_into_vault(
        db,
        source="tally",
        journals=xml,
        account_map=None,
        company_name="Tally Co",
        force=True,
    )
    assert result.vouchers == 1
    assert result.lines >= 2

    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        mis = mis_snapshot(session, date(2024, 4, 30))
        assert mis.company_name == "Tally Co"
        assert mis.scenario_id == "imported"
        assert mis.fy.sales == money("100")
