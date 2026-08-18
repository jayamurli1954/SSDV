from datetime import date
from pathlib import Path

import pytest

from ssdv.cli import main
from ssdv.connectors import (
    ConnectorNotReady,
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
    with pytest.raises(ConnectorNotReady, match="CSV"):
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


def test_connect_tally_is_not_ready() -> None:
    assert main(["connect", "--source", "tally", "--journals", "x.csv"]) == 2


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
