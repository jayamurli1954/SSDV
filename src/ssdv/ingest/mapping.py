from __future__ import annotations

from pathlib import Path

from ssdv.ingest.errors import IngestError
from ssdv.paths import load_yaml

_SOURCE_KEYS = ("source", "ledger", "ledger_name", "account", "name")
_CODE_KEYS = ("account_code", "code", "gl_code", "canonical")


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def load_account_map(path: Path | None) -> dict[str, str]:
    """Map source ledger name/code -> canonical chart code.

    CSV columns: source, account_code (aliases accepted).
    YAML: {ledgers: {name: code}} or a flat {name: code} mapping.
    """
    if path is None:
        return {}
    if not path.exists():
        raise IngestError(f"Account map not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return _from_yaml(path)
    if suffix in {".csv", ".txt"}:
        return _from_csv(path)
    raise IngestError(f"Account map must be CSV or YAML, not {path.suffix}")


def _from_yaml(path: Path) -> dict[str, str]:
    data = load_yaml(path)
    raw = data.get("ledgers", data)
    if not isinstance(raw, dict):
        raise IngestError(f"YAML map in {path} must be a mapping of ledger -> account_code")
    out: dict[str, str] = {}
    for source, code in raw.items():
        key = str(source).strip()
        if not key:
            continue
        out[key] = str(code).strip()
        out[key.casefold()] = str(code).strip()
    return out


def _from_csv(path: Path) -> dict[str, str]:
    import csv

    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise IngestError(f"Account map {path} has no header row")
        fields = {_norm(name): name for name in reader.fieldnames if name}
        source_col = next((fields[k] for k in _SOURCE_KEYS if k in fields), None)
        code_col = next((fields[k] for k in _CODE_KEYS if k in fields), None)
        if source_col is None or code_col is None:
            raise IngestError(
                f"Account map {path} needs source and account_code columns (got {reader.fieldnames})"
            )
        for row in reader:
            source = str(row.get(source_col) or "").strip()
            code = str(row.get(code_col) or "").strip()
            if not source:
                continue
            if not code:
                raise IngestError(f"Account map {path} has no code for {source!r}")
            out[source] = code
            out[source.casefold()] = code
    return out


def resolve_account(source: str, mapping: dict[str, str], known_codes: set[str]) -> str:
    raw = source.strip()
    if not raw:
        raise IngestError("Journal line has a blank account")
    if raw in known_codes:
        return raw
    mapped = mapping.get(raw) or mapping.get(raw.casefold())
    if mapped:
        return mapped
    raise IngestError(
        f"Unmapped ledger {raw!r}. Add it to the account map or use a canonical COA code."
    )
