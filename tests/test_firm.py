from datetime import date
from pathlib import Path

import pytest

from ssdv.cli import main
from ssdv.connectors.base import ConnectorError
from ssdv.connectors.pipeline import load_into_vault
from ssdv.officemitra.firm import (
    apply_company_limit,
    assert_can_add_vault,
    build_roster,
    client_slug,
    client_vault_path,
    discover_vaults,
    render_firm_html,
)
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def _load_client(path: Path, name: str) -> None:
    load_into_vault(
        path,
        source="generic",
        journals=EXAMPLE / "journals.csv",
        account_map=EXAMPLE / "ledger_map.csv",
        company_name=name,
        force=True,
    )


def test_client_slug_and_vault_path(tmp_path: Path) -> None:
    assert client_slug("Acme Trading Pvt Ltd") == "acme-trading-pvt-ltd"
    path = client_vault_path("Acme Trading Pvt Ltd", data_dir=tmp_path)
    assert path == tmp_path / "ssdv_acme-trading-pvt-ltd.sqlite"


def test_firm_roster_summarises_two_vaults(tmp_path: Path) -> None:
    first = tmp_path / "ssdv_alpha.sqlite"
    second = tmp_path / "ssdv_beta.sqlite"
    _load_client(first, "Alpha Traders")
    _load_client(second, "Beta Traders")
    roster = build_roster(date(2024, 4, 30), data_dir=tmp_path, limit=20)
    names = {row.company for row in roster.rows}
    assert names == {"Alpha Traders", "Beta Traders"}
    assert all(row.sales > 0 for row in roster.rows)
    assert roster.hidden == 0
    html = render_firm_html(roster)
    assert "Alpha Traders" in html
    assert "Firm roster" in html


def test_company_limit_hides_overflow(tmp_path: Path) -> None:
    paths = []
    for i in range(3):
        path = tmp_path / f"ssdv_c{i}.sqlite"
        _load_client(path, f"Client {i}")
        paths.append(path)
    visible, hidden = apply_company_limit(discover_vaults(tmp_path), limit=2)
    assert len(visible) == 2
    assert hidden == 1
    assert_can_add_vault(paths[0], limit=2, data_dir=tmp_path)
    with pytest.raises(ConnectorError, match="allows 2 companies"):
        assert_can_add_vault(tmp_path / "ssdv_new.sqlite", limit=2, data_dir=tmp_path)


def test_firm_cli_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("OFFICEMITRA_HOME", str(tmp_path))
    data = tmp_path / "data"
    data.mkdir()
    _load_client(data / "ssdv_one.sqlite", "One Co")
    _load_client(data / "ssdv_two.sqlite", "Two Co")
    assert main(["firm", "--json", "--as-of", "2024-04-30"]) == 0
    out = capsys.readouterr().out
    assert "One Co" in out
    assert "Two Co" in out
    assert '"sales"' in out
