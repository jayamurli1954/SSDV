from __future__ import annotations

from datetime import date
from pathlib import Path

from ssdv.ingest import ingest_generic
from ssdv.officemitra.setup_flow import (
    SourceChoice,
    ingest_meta_as_of,
    validate_vault,
    vault_has_data,
    vault_voucher_count,
)
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"


def test_vault_has_data_false_on_missing_file(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    assert vault_voucher_count(db) == 0
    assert vault_has_data(db) is False


def test_vault_has_data_true_after_ingest(session, tmp_path: Path) -> None:
    db = tmp_path / "books.sqlite"
    from ssdv.db import make_engine
    from ssdv.db import session_scope as scope

    engine = make_engine(db)
    from ssdv.db import create_schema

    create_schema(engine)
    with scope(engine) as db_session:
        ingest_generic(
            db_session,
            EXAMPLE / "journals.csv",
            EXAMPLE / "ledger_map.csv",
            company_name="Test Co",
        )
    assert vault_voucher_count(db) > 0
    assert vault_has_data(db) is True


def test_ingest_meta_as_of(session, tmp_path: Path) -> None:
    db = tmp_path / "books.sqlite"
    from ssdv.db import create_schema, make_engine
    from ssdv.db import session_scope as scope

    engine = make_engine(db)
    create_schema(engine)
    with scope(engine) as db_session:
        ingest_generic(
            db_session,
            EXAMPLE / "journals.csv",
            EXAMPLE / "ledger_map.csv",
            company_name="Test Co",
        )
    assert ingest_meta_as_of(db) == date(2024, 4, 30)


def test_validate_vault_after_ingest(session, tmp_path: Path) -> None:
    db = tmp_path / "books.sqlite"
    from ssdv.db import create_schema, make_engine
    from ssdv.db import session_scope as scope

    engine = make_engine(db)
    create_schema(engine)
    with scope(engine) as db_session:
        ingest_generic(
            db_session,
            EXAMPLE / "journals.csv",
            EXAMPLE / "ledger_map.csv",
            company_name="Test Co",
        )
    ok, errors = validate_vault(db, date(2024, 4, 30))
    assert ok is True
    assert errors == []


def test_source_choice_flags() -> None:
    live = SourceChoice("tally-http", "Tally", "ready", "hint")
    upload = SourceChoice("generic", "CSV", "ready", "hint")
    assert live.is_live is True
    assert live.needs_upload is False
    assert upload.needs_upload is True
    assert upload.upload_journal_types == ["csv"]
