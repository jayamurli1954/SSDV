from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from ssdv.db import create_schema, make_engine


def test_upgrade_schema_adds_msme_columns_to_existing_vendors_table(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite"
    engine = make_engine(db)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE vendors (
                    code VARCHAR(16) PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    is_active BOOLEAN DEFAULT 1
                )
                """
            )
        )

    create_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(vendors)")).fetchall()
    cols = {str(row[1]) for row in rows}
    assert "msme_category" in cols
    assert "msme_has_agreement" in cols

    # Idempotent on second run.
    create_schema(engine)
