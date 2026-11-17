"""Partner approval (maker-checker) for OfficeMitra desktop.

A preparer marks the books reviewed; a partner then approves with a PIN. When a firm
has set a partner PIN, the Board PPT stays blocked until the partner approves the same
as-of date and voucher count that were reviewed.

This is a local sign-off gate, not access control: the PIN is stored only as a salted
hash, but anyone who can edit files in the OfficeMitra data folder can remove the gate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ssdv.paths import user_data_dir

MIN_PIN_LENGTH = 4
_ITERATIONS = 200_000
NOT_APPROVED_REASON = "Books are reviewed but not yet approved by the partner"


class ApprovalError(Exception):
    """Partner approval could not be set up, given, or withdrawn."""


@dataclass(frozen=True)
class ApprovalStatus:
    required: bool
    approved: bool
    approved_by: str | None = None
    approved_at: str | None = None
    partner_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "partner_name": self.partner_name,
        }


def firm_approval_path() -> Path:
    return user_data_dir() / "approval.json"


def approval_sidecar_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.stem}.approval.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _hash_pin(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERATIONS).hex()


def _firm_config() -> dict[str, Any] | None:
    data = _read_json(firm_approval_path())
    if not data or not data.get("pin_hash") or not data.get("pin_salt"):
        return None
    return data


def approval_required() -> bool:
    return _firm_config() is not None


def partner_name() -> str | None:
    config = _firm_config()
    return str(config.get("partner_name") or "") or None if config else None


def verify_pin(pin: str) -> bool:
    config = _firm_config()
    if config is None:
        return False
    try:
        salt = bytes.fromhex(str(config["pin_salt"]))
    except ValueError:
        return False
    return hmac.compare_digest(_hash_pin(pin, salt), str(config["pin_hash"]))


def set_partner_pin(name: str, pin: str, *, current_pin: str | None = None) -> None:
    """Turn partner approval on, or change the partner / PIN (needs the current PIN)."""
    partner = name.strip()
    if not partner:
        raise ApprovalError("Enter the partner's name.")
    if len(pin) < MIN_PIN_LENGTH:
        raise ApprovalError(f"The PIN needs at least {MIN_PIN_LENGTH} characters.")
    if approval_required() and not verify_pin(current_pin or ""):
        raise ApprovalError("The current partner PIN is not correct.")
    salt = secrets.token_bytes(16)
    payload = {
        "partner_name": partner,
        "pin_salt": salt.hex(),
        "pin_hash": _hash_pin(pin, salt),
        "set_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    firm_approval_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def disable_partner_approval(pin: str) -> None:
    if not approval_required():
        return
    if not verify_pin(pin):
        raise ApprovalError("The partner PIN is not correct.")
    firm_approval_path().unlink(missing_ok=True)


def read_approval(db_path: Path, as_of: date, *, voucher_count: int) -> dict[str, Any] | None:
    """The stored approval, or None when it is missing or stale for these books."""
    data = _read_json(approval_sidecar_path(db_path))
    if data is None:
        return None
    if str(data.get("as_of") or "") != as_of.isoformat():
        return None
    if int(data.get("voucher_count") or -1) != voucher_count:
        return None
    return data


def approval_status(
    db_path: Path, as_of: date, *, voucher_count: int, reviewed: bool
) -> ApprovalStatus:
    required = approval_required()
    data = read_approval(db_path, as_of, voucher_count=voucher_count) if reviewed else None
    return ApprovalStatus(
        required=required,
        approved=data is not None,
        approved_by=str(data.get("approved_by")) if data else None,
        approved_at=str(data.get("approved_at")) if data else None,
        partner_name=partner_name(),
    )


def approve(
    db_path: Path, as_of: date, *, voucher_count: int, reviewed: bool, pin: str
) -> dict[str, Any]:
    if not approval_required():
        raise ApprovalError("Partner approval is not set up for this firm.")
    if not reviewed:
        raise ApprovalError("Mark the books reviewed for this as-of date before approving.")
    if not verify_pin(pin):
        raise ApprovalError("The partner PIN is not correct.")
    payload = {
        "as_of": as_of.isoformat(),
        "voucher_count": voucher_count,
        "approved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "approved_by": partner_name() or "partner",
    }
    approval_sidecar_path(db_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def withdraw_approval(db_path: Path, *, pin: str) -> None:
    if not verify_pin(pin):
        raise ApprovalError("The partner PIN is not correct.")
    approval_sidecar_path(db_path).unlink(missing_ok=True)
