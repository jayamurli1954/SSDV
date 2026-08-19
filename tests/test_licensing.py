from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ssdv.licensing import License, LicenseError, feature_allowed, load_license, load_plans, plan_for


def test_load_plans_has_agreed_tiers() -> None:
    plans = load_plans()
    assert set(plans) >= {"starter", "professional", "enterprise", "ca_5", "ca_20", "ca_50"}
    assert plans["starter"].price_inr == 3999
    assert plans["professional"].price_inr == 6999
    assert plans["ca_5"].price_inr == 12999
    assert plans["enterprise"].company_limit == 5


def test_feature_matrix_starter_vs_professional() -> None:
    assert feature_allowed("starter", "ceo_pack") is True
    assert feature_allowed("starter", "cfo_pack") is False
    assert feature_allowed("professional", "cfo_pack") is True
    assert feature_allowed("professional", "connect_tally_http") is False
    assert feature_allowed("enterprise", "connect_tally_http") is True
    assert feature_allowed("professional", "gstr2b_recon") is False
    assert feature_allowed("ca_5", "ask_why") is True


def test_parse_license_json(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "license_id": "OM-TEST-001",
        "customer_name": "Demo Traders",
        "plan_id": "professional",
        "company_limit": 1,
        "issued_at": "2026-04-01",
        "amc_expires_at": "2027-03-31",
    }
    path = tmp_path / "officemitra.license"
    path.write_text(json.dumps(payload), encoding="utf-8")

    lic = load_license(explicit_path=path)
    assert lic is not None
    assert lic.customer_name == "Demo Traders"
    assert lic.allows("board_pack") is True
    assert lic.allows("connect_tally_http") is False
    assert "Professional" in lic.summary_line()


def test_license_rejects_unknown_plan(tmp_path: Path) -> None:
    path = tmp_path / "bad.license"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "license_id": "X",
                "customer_name": "Y",
                "plan_id": "nonexistent",
                "company_limit": 1,
                "issued_at": "2026-04-01",
                "amc_expires_at": "2027-03-31",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LicenseError):
        load_license(explicit_path=path)


def test_license_company_limit_cap(tmp_path: Path) -> None:
    path = tmp_path / "cap.license"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "license_id": "X",
                "customer_name": "Y",
                "plan_id": "starter",
                "company_limit": 99,
                "issued_at": "2026-04-01",
                "amc_expires_at": "2027-03-31",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LicenseError):
        load_license(explicit_path=path)
