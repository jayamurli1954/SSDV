from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ssdv.models import Base
from ssdv.paths import default_db_path


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def make_engine(db_path: Path | None = None) -> Engine:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(sqlite_url(path), future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _sqlite_columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {str(row[1]) for row in rows}


def upgrade_schema(engine: Engine) -> None:
    """Create tables and add columns introduced after first install (SQLite has no auto-migrate)."""
    Base.metadata.create_all(engine)
    if engine.dialect.name != "sqlite":
        return
    names = set(inspect(engine).get_table_names())
    if "vendors" in names:
        cols = _sqlite_columns(engine, "vendors")
        alters: list[str] = []
        if "msme_category" not in cols:
            alters.append("ALTER TABLE vendors ADD COLUMN msme_category VARCHAR(16)")
        if "msme_has_agreement" not in cols:
            alters.append(
                "ALTER TABLE vendors ADD COLUMN msme_has_agreement BOOLEAN NOT NULL DEFAULT 0"
            )
        if alters:
            with engine.begin() as conn:
                for stmt in alters:
                    conn.execute(text(stmt))


def create_schema(engine: Engine) -> None:
    upgrade_schema(engine)


def drop_schema(engine: Engine) -> None:
    Base.metadata.drop_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
