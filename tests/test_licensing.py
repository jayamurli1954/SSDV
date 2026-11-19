from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ssdv.licensing import LicenseError, feature_allowed, load_license, load_plans, signing
from ssdv.licensing.signing import public_key_b64_for, sign_payload


@pytest.fixture()
def test_key(monkeypatch: pytest.MonkeyPatch) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(signing, "PUBLIC_KEY_B64", public_key_b64_for(key))
    return key


def _payload(**overrides: object) -> dict:
    data = {
        "schema_version": 2,
        "license_id": "OM-TEST-001",
        "customer_name": "Demo Traders",
        "plan_id": "professional",
        "company_limit": 1,
        "issued_at": "2026-04-01",
        "amc_expires_at": "2027-03-31",
    }
    data.update(overrides)
    return data


def _write(tmp_path: Path, data: dict, name: str = "officemitra.license") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_plans_has_agreed_tiers() -> None:
    plans = load_plans()
    assert set(plans) >= {"trial", "starter", "professional", "enterprise", "ca_5", "ca_20", "ca_50"}
    assert plans["starter"].price_inr == 3999
    assert plans["professional"].price_inr == 6999
    assert plans["ca_5"].price_inr == 12999
    assert plans["enterprise"].company_limit == 5
    assert plans["trial"].company_limit == 1


def test_every_plan_lists_every_feature() -> None:
    plans = load_plans()
    keys = set(plans["ca_50"].features)
    for plan in plans.values():
        assert set(plan.features) == keys, plan.id


def test_feature_matrix() -> None:
    assert feature_allowed("starter", "ceo_pack") is True
    assert feature_allowed("starter", "cfo_pack") is False
    assert feature_allowed("starter", "budget_variance") is False
    assert feature_allowed("professional", "cfo_pack") is True
    assert feature_allowed("professional", "budget_variance") is True
    assert feature_allowed("professional", "partner_approval") is False
    assert feature_allowed("professional", "connect_tally_http") is False
    assert feature_allowed("enterprise", "connect_tally_http") is True
    assert feature_allowed("enterprise", "partner_approval") is True
    assert feature_allowed("professional", "gstr2b_recon") is False
    assert feature_allowed("ca_5", "ask_why") is True


def test_signed_license_loads(tmp_path: Path, test_key: Ed25519PrivateKey) -> None:
    path = _write(tmp_path, sign_payload(_payload(), test_key))
    lic = load_license(explicit_path=path)
    assert lic is not None
    assert lic.customer_name == "Demo Traders"
    assert lic.allows("board_pack") is True
    assert lic.allows("connect_tally_http") is False
    assert "Professional" in lic.summary_line()


def test_edited_license_is_rejected(tmp_path: Path, test_key: Ed25519PrivateKey) -> None:
    signed = sign_payload(_payload(), test_key)
    signed["plan_id"] = "ca_50"
    signed["company_limit"] = 50
    with pytest.raises(LicenseError, match="signature"):
        load_license(explicit_path=_write(tmp_path, signed))


def test_license_signed_by_another_key_is_rejected(tmp_path: Path, test_key: Ed25519PrivateKey) -> None:
    other = Ed25519PrivateKey.generate()
    with pytest.raises(LicenseError, match="signature"):
        load_license(explicit_path=_write(tmp_path, sign_payload(_payload(), other)))


def test_unsigned_license_is_rejected(tmp_path: Path, test_key: Ed25519PrivateKey) -> None:
    with pytest.raises(LicenseError, match="signature"):
        load_license(explicit_path=_write(tmp_path, _payload()))


def test_old_unsigned_v1_license_asks_for_new_one(tmp_path: Path) -> None:
    with pytest.raises(LicenseError, match="old unsigned"):
        load_license(explicit_path=_write(tmp_path, _payload(schema_version=1)))


def test_license_rejects_unknown_plan(tmp_path: Path, test_key: Ed25519PrivateKey) -> None:
    path = _write(tmp_path, sign_payload(_payload(plan_id="nonexistent"), test_key))
    with pytest.raises(LicenseError):
        load_license(explicit_path=path)


def test_license_company_limit_cap(tmp_path: Path, test_key: Ed25519PrivateKey) -> None:
    path = _write(tmp_path, sign_payload(_payload(plan_id="starter", company_limit=99), test_key))
    with pytest.raises(LicenseError):
        load_license(explicit_path=path)


def test_shipped_example_license_is_not_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    for example in (root / "examples" / "licensing").glob("*.json"):
        with pytest.raises(LicenseError):
            load_license(explicit_path=example)


def test_entitlements_trial_when_installed_without_licence(monkeypatch: pytest.MonkeyPatch) -> None:
    from ssdv.officemitra import entitlements as ent_mod

    monkeypatch.setattr(ent_mod, "license_status", lambda: (None, None))
    monkeypatch.setattr(ent_mod, "is_frozen", lambda: True)
    ent = ent_mod.current_entitlements()
    assert ent.mode == "trial"
    assert ent.company_limit == 1
    assert ent.allows("cfo_pack") is True
    assert ent.allows("partner_approval") is False
    assert "not included" in ent_mod.upgrade_note("partner_approval", ent)


def test_entitlements_developer_mode_from_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from ssdv.officemitra import entitlements as ent_mod

    monkeypatch.setattr(ent_mod, "license_status", lambda: (None, None))
    monkeypatch.setattr(ent_mod, "is_frozen", lambda: False)
    monkeypatch.delenv("OFFICEMITRA_FORCE_TRIAL", raising=False)
    ent = ent_mod.current_entitlements()
    assert ent.mode == "developer"
    assert ent.company_limit is None
    assert ent.allows("partner_approval") is True


def test_entitlements_follow_licence(
    tmp_path: Path, test_key: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssdv.officemitra import entitlements as ent_mod

    lic = load_license(explicit_path=_write(tmp_path, sign_payload(_payload(plan_id="starter"), test_key)))
    monkeypatch.setattr(ent_mod, "license_status", lambda: (lic, None))
    ent = ent_mod.current_entitlements()
    assert ent.mode == "licensed"
    assert ent.company_limit == 1
    assert ent.allows("ceo_pack") is True
    assert ent.allows("cfo_pack") is False
