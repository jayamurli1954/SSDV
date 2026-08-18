"""GSTIN / PAN helpers for Indian GST-registered parties."""

from __future__ import annotations

import random
import re

GSTN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHLJPTK][A-Z][0-9]{4}[A-Z]$")
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_check_digit(body14: str) -> str:
    """Checksum for the first 14 characters of a GSTIN (GSTN algorithm)."""
    body = body14.upper()
    if len(body) != 14:
        raise ValueError("GSTIN body must be 14 characters")
    factor = 1
    total = 0
    for char in body:
        code_point = GSTN_CHARS.index(char)
        addend = factor * code_point
        factor = 2 if factor == 1 else 1
        total += addend // 36 + addend % 36
    check_point = (36 - (total % 36)) % 36
    return GSTN_CHARS[check_point]


def make_gstin(state_code: str, pan: str, entity: str = "1") -> str:
    pan = pan.upper()
    if not PAN_RE.match(pan):
        raise ValueError(f"Invalid PAN {pan}")
    if len(state_code) != 2 or not state_code.isdigit():
        raise ValueError(f"Invalid state code {state_code}")
    body = f"{state_code}{pan}{entity}Z"
    return body + gstin_check_digit(body)


def is_valid_gstin(gstin: str) -> bool:
    gstin = gstin.upper()
    if len(gstin) != 15 or not GSTIN_RE.match(gstin):
        return False
    return gstin[-1] == gstin_check_digit(gstin[:14])


def random_pan(rng: random.Random, fourth: str = "C", used: set[str] | None = None) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    used = used if used is not None else set()
    while True:
        pan = (
            "".join(rng.choice(letters) for _ in range(3))
            + fourth
            + rng.choice(letters)
            + f"{rng.randint(0, 9999):04d}"
            + rng.choice(letters)
        )
        if pan not in used:
            used.add(pan)
            return pan
