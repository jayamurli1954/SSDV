from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
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


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


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
