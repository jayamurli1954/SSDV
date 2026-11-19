from __future__ import annotations

import gzip
from datetime import date
from pathlib import Path

import pytest

from ssdv.connectors.base import ConnectorError
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.models import IngestMeta
from ssdv.officemitra import demo
from ssdv.officemitra.firm import apply_company_limit, assert_can_add_vault


def _vault(path: Path, *, imported: bool) -> Path:
    engine = make_engine(path)
    create_schema(engine)
    if imported:
        with session_scope(engine) as session:
            session.add(
                IngestMeta(
                    id=1,
                    source="generic",
                    company_name="Client",
                    first_date=date(2025, 4, 1),
                    last_date=date(2026, 3, 31),
                )
            )
    engine.dispose()
    return path


def _archives(folder: Path, source: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for book in demo.DEMO_BOOKS:
        with gzip.open(folder / f"{book.stem}.sqlite.gz", "wb") as out:
            out.write(source.read_bytes())
    return folder


def test_load_demo_books_unpacks_once(tmp_path: Path) -> None:
    source = _vault(tmp_path / "src.sqlite", imported=False)
    archive_dir = _archives(tmp_path / "assets", source)
    data = tmp_path / "data"
    assert demo.demo_available(archive_dir)
    assert not demo.demo_loaded(data)

    paths = demo.load_demo_books(data, archive_dir=archive_dir)
    assert [p.name for p in paths] == [f"{b.stem}.sqlite" for b in demo.DEMO_BOOKS]
    assert all(p.read_bytes() == source.read_bytes() for p in paths)
    assert demo.demo_loaded(data)

    paths[0].write_bytes(b"kept")
    demo.load_demo_books(data, archive_dir=archive_dir)
    assert paths[0].read_bytes() == b"kept"


def test_no_archives_means_no_demo(tmp_path: Path) -> None:
    assert not demo.demo_available(tmp_path / "missing")
    assert demo.load_demo_books(tmp_path / "data", archive_dir=tmp_path / "missing") == []


def test_demo_vault_detection(tmp_path: Path) -> None:
    assert demo.is_demo_vault(_vault(tmp_path / "demo_abc.sqlite", imported=False))
    # A client's imported books renamed demo_ still count as a client.
    assert not demo.is_demo_vault(_vault(tmp_path / "demo_renamed.sqlite", imported=True))
    assert not demo.is_demo_vault(_vault(tmp_path / "client.sqlite", imported=False))


def test_demo_books_do_not_use_the_client_limit(tmp_path: Path) -> None:
    demos = [_vault(tmp_path / f"demo_{i}.sqlite", imported=False) for i in range(3)]
    clients = [_vault(tmp_path / f"ssdv_c{i}.sqlite", imported=True) for i in range(2)]

    visible, hidden = apply_company_limit(clients + demos, limit=1)
    assert visible == [clients[0], *demos]
    assert hidden == 1

    visible, hidden = apply_company_limit(demos, limit=1)
    assert visible == demos
    assert hidden == 0


def test_demo_books_do_not_block_adding_a_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demos = [_vault(tmp_path / f"demo_{i}.sqlite", imported=False) for i in range(3)]
    monkeypatch.setattr("ssdv.officemitra.firm.discover_vaults", lambda _folder=None: list(demos))
    assert_can_add_vault(tmp_path / "ssdv_first_client.sqlite", limit=1, data_dir=tmp_path)

    client = _vault(tmp_path / "ssdv_client.sqlite", imported=True)
    monkeypatch.setattr("ssdv.officemitra.firm.discover_vaults", lambda _folder=None: [*demos, client])
    with pytest.raises(ConnectorError, match="allows 1 companies"):
        assert_can_add_vault(tmp_path / "ssdv_second.sqlite", limit=1, data_dir=tmp_path)
