from __future__ import annotations

import random
from typing import Any

from ssdv.paths import load_company


def company_rng(company: dict[str, Any] | None = None) -> random.Random:
    cfg = company or load_company()
    return random.Random(int(cfg["generator"]["seed"]))
