from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ssdv.accounting.coa import load_coa
from ssdv.db import create_schema, make_engine, session_scope


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(tmp_path / "ssdv.sqlite")
    create_schema(engine)
    with session_scope(engine) as db:
        load_coa(db)
        yield db
