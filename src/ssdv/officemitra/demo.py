"""Demo client books shipped with the desktop app.

The installer build generates a few ABC Industrial scenarios (scripts/build_demo_books.py)
and packs them gzip-compressed under assets/demo. "Load demo books" unpacks them into
the user's data folder in seconds. Demo books are synthetic, so they never count
against the licence's client limit.
"""

from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from ssdv.paths import resource_root, user_data_dir

DEMO_PREFIX = "demo_"


@dataclass(frozen=True)
class DemoBook:
    scenario: str
    stem: str
    label: str


DEMO_BOOKS: tuple[DemoBook, ...] = (
    DemoBook("baseline", "demo_abc_healthy_growth", "Healthy growth"),
    DemoBook("cash_flow_crisis", "demo_abc_cash_crunch", "Cash-flow crisis"),
    DemoBook("customer_concentration", "demo_abc_customer_risk", "Customer concentration"),
)


def demo_archive_dir() -> Path:
    return resource_root() / "assets" / "demo"


def demo_archives(archive_dir: Path | None = None) -> list[Path]:
    folder = archive_dir or demo_archive_dir()
    return [folder / f"{book.stem}.sqlite.gz" for book in DEMO_BOOKS if (folder / f"{book.stem}.sqlite.gz").is_file()]


def demo_available(archive_dir: Path | None = None) -> bool:
    return bool(demo_archives(archive_dir))


def _data_dir(data_dir: Path | None) -> Path:
    folder = data_dir or (user_data_dir() / "data")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def demo_loaded(data_dir: Path | None = None) -> bool:
    folder = data_dir or (user_data_dir() / "data")
    return any((folder / f"{book.stem}.sqlite").is_file() for book in DEMO_BOOKS)


def load_demo_books(data_dir: Path | None = None, *, archive_dir: Path | None = None) -> list[Path]:
    """Unpack the shipped demo books (skipping ones already present). Returns their paths."""
    folder = _data_dir(data_dir)
    loaded: list[Path] = []
    for archive in demo_archives(archive_dir):
        dest = folder / archive.name[: -len(".gz")]
        if not dest.exists():
            tmp = dest.with_suffix(".sqlite.part")
            with gzip.open(archive, "rb") as src, tmp.open("wb") as out:
                shutil.copyfileobj(src, out)
            tmp.replace(dest)
        loaded.append(dest)
    return loaded


def is_demo_vault(path: Path) -> bool:
    """A shipped demo book: demo_ name and generated (never imported from a client's books)."""
    if not path.stem.startswith(DEMO_PREFIX):
        return False
    from ssdv.db import make_engine, session_scope
    from ssdv.models import IngestMeta

    try:
        engine = make_engine(path)
        with session_scope(engine) as session:
            return session.get(IngestMeta, 1) is None
    except (OSError, SQLAlchemyError):
        return False
