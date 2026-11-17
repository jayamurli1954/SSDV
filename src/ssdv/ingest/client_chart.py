"""Each client's own chart of accounts.

Companies number and name their ledgers differently (1001, 10001, 100001; "SBI Current
A/c" vs "HDFC Bank"). OfficeMitra keeps every client's ledgers exactly as they appear
in that client's books, classifies each one under a standard ledger for KPIs, and can
report back in the client's own codes, names and groups.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.ingest.errors import IngestError
from ssdv.ingest.mapping import resolve_account
from ssdv.models import ClientLedger

_CODE_KEYS = ("code", "account_code", "ledger_code", "gl_code")
_NAME_KEYS = ("name", "account_name", "ledger_name", "ledger", "account", "description")
_GROUP_KEYS = ("group", "group_name", "parent", "parent_group", "under")


@dataclass(frozen=True)
class ChartEntry:
    code: str | None
    name: str
    group: str | None = None


class ClientChart:
    """Lookup of a client's ledgers by their own code or their own name."""

    def __init__(self, entries: list[ChartEntry] | None = None) -> None:
        self.entries: list[ChartEntry] = list(entries or [])
        self._by_code = {e.code: e for e in self.entries if e.code}
        self._by_name = {e.name.casefold(): e for e in self.entries}

    def __bool__(self) -> bool:
        return bool(self.entries)

    def find(self, source: str) -> ChartEntry | None:
        raw = source.strip()
        return self._by_code.get(raw) or self._by_name.get(raw.casefold())

    def has_code(self, source: str) -> bool:
        return source.strip() in self._by_code


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def load_client_chart(path: Path | None) -> ClientChart:
    """CSV with the client's ledgers: ``code,name,group`` (code and group optional)."""
    if path is None:
        return ClientChart()
    if not path.is_file():
        raise IngestError(f"Client chart of accounts not found: {path}")
    entries: list[ChartEntry] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise IngestError(f"Client chart {path.name} has no header row")
        fields = {_norm(name): name for name in reader.fieldnames if name}
        code_col = next((fields[k] for k in _CODE_KEYS if k in fields), None)
        name_col = next((fields[k] for k in _NAME_KEYS if k in fields), None)
        group_col = next((fields[k] for k in _GROUP_KEYS if k in fields), None)
        if name_col is None:
            raise IngestError(
                f"Client chart {path.name} needs a name column (got {reader.fieldnames})"
            )
        seen_codes: set[str] = set()
        for row in reader:
            name = str(row.get(name_col) or "").strip()
            code = str(row.get(code_col) or "").strip() if code_col else ""
            if not name and not code:
                continue
            if code and code in seen_codes:
                raise IngestError(f"Client chart {path.name} repeats code {code!r}")
            seen_codes.add(code)
            group = str(row.get(group_col) or "").strip() if group_col else ""
            entries.append(ChartEntry(code=code or None, name=name or code, group=group or None))
    return ClientChart(entries)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].upper()


def parse_tally_ledger_masters(xml_bytes: bytes) -> ClientChart:
    """Ledger names and parent groups from a TallyPrime "List of Ledgers" export."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise IngestError("TallyPrime ledger list is not valid XML") from exc
    entries: list[ChartEntry] = []
    seen: set[str] = set()
    for elem in root.iter():
        if _local(elem.tag) != "LEDGER":
            continue
        name = (elem.get("NAME") or "").strip()
        parent = ""
        for child in elem:
            tag = _local(child.tag)
            if tag == "NAME" and not name:
                name = (child.text or "").strip()
            elif tag == "PARENT":
                parent = (child.text or "").strip()
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            entries.append(ChartEntry(code=None, name=name, group=parent or None))
    return ClientChart(entries)


def client_chart_path(db_path: Path) -> Path:
    """The client's chart kept beside the vault and reused on every import."""
    return db_path.with_name(f"{db_path.stem}.clientchart.csv")


def save_client_chart(db_path: Path, chart: ClientChart) -> Path | None:
    if not chart:
        return None
    path = client_chart_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["code", "name", "group"])
        for entry in chart.entries:
            writer.writerow([entry.code or "", entry.name, entry.group or ""])
    return path


def saved_client_chart(db_path: Path, uploaded: Path | None = None) -> ClientChart:
    """A chart uploaded for this import, else the one saved beside the vault."""
    if uploaded is not None:
        return load_client_chart(uploaded)
    saved = client_chart_path(db_path)
    return load_client_chart(saved) if saved.is_file() else ClientChart()


def map_lookup(source: str, entry: ChartEntry | None, mapping: dict[str, str]) -> str | None:
    """The ledger map may be keyed by the source text, the client's code, or its name."""
    keys = [source.strip()]
    if entry is not None:
        keys += [entry.code or "", entry.name]
    for key in keys:
        if not key:
            continue
        code = mapping.get(key) or mapping.get(key.casefold())
        if code:
            return code
    return None


def standard_code(
    source: str,
    *,
    chart: ClientChart,
    mapping: dict[str, str],
    known_codes: set[str],
) -> str:
    """Standard ledger for one source ledger. The map wins; a number that belongs to the
    client's own chart is never mistaken for a standard code of the same digits."""
    entry = chart.find(source)
    mapped = map_lookup(source, entry, mapping)
    if mapped:
        return mapped
    if chart.has_code(source):
        label = f"{source} ({entry.name})" if entry else source
        raise IngestError(
            f"Unmapped ledger {label!r}. Add it to the account map or confirm it in the app."
        )
    return resolve_account(source, {}, known_codes)


class LedgerRegistry:
    """Resolves source ledgers during an import and records each client ledger once."""

    def __init__(
        self,
        session: Session,
        *,
        chart: ClientChart,
        mapping: dict[str, str],
        known_codes: set[str],
    ) -> None:
        self.session = session
        self.chart = chart
        self.mapping = mapping
        self.known = known_codes
        self._cache: dict[str, tuple[str, int]] = {}
        for row in session.scalars(select(ClientLedger)):
            self._cache[row.source_key] = (row.account_code, row.id)

    def resolve(self, source: str) -> tuple[str, int]:
        key = source.strip()[:160]
        if not key:
            raise IngestError("Journal line has a blank account")
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        account_code = standard_code(
            key, chart=self.chart, mapping=self.mapping, known_codes=self.known
        )
        entry = self.chart.find(key)
        ledger = ClientLedger(
            source_key=key,
            code=entry.code if entry else None,
            name=(entry.name if entry else key)[:160],
            group_name=(entry.group[:160] if entry and entry.group else None),
            account_code=account_code,
        )
        self.session.add(ledger)
        self.session.flush()
        self._cache[key] = (account_code, ledger.id)
        return self._cache[key]
