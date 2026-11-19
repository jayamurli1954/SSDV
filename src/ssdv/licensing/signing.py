"""Ed25519 signatures for OfficeMitra licence files.

SanMitra signs each licence with a private key that never leaves the issuing PC
(see scripts/issue_license.py). The app only holds the public key below, so it can
check a licence but cannot create one. Changing any field of a signed licence
(plan, company limit, AMC date, machine) breaks the signature.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# Public half of SanMitra's licence-signing key (raw 32 bytes, base64).
PUBLIC_KEY_B64 = "rUJIdM14DdWDFlREtJCNL74q8HTEHSk8eKs49JRF/jU="

SIGNATURE_FIELD = "signature"


def canonical_payload(data: dict[str, Any]) -> bytes:
    """Bytes that are signed: every field except the signature, in a fixed order."""
    body = {key: value for key, value in data.items() if key != SIGNATURE_FIELD}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _public_key(public_key_b64: str | None = None) -> Ed25519PublicKey:
    raw = base64.b64decode(public_key_b64 or PUBLIC_KEY_B64)
    return Ed25519PublicKey.from_public_bytes(raw)


def verify_signature(data: dict[str, Any], *, public_key_b64: str | None = None) -> bool:
    signature = data.get(SIGNATURE_FIELD)
    if not isinstance(signature, str) or not signature.strip():
        return False
    try:
        _public_key(public_key_b64).verify(base64.b64decode(signature), canonical_payload(data))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def sign_payload(data: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    """Return a copy of ``data`` with its signature added (issuer side only)."""
    signed = {key: value for key, value in data.items() if key != SIGNATURE_FIELD}
    signed[SIGNATURE_FIELD] = base64.b64encode(private_key.sign(canonical_payload(signed))).decode("ascii")
    return signed


def public_key_b64_for(private_key: Ed25519PrivateKey) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")
