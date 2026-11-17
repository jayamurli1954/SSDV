from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.mis.packs import board_pack, scorecard
from ssdv.mis.policy import (
    DEFAULT_POLICY,
    PolicyError,
    build_policy,
    load_policy,
    save_policy,
    thresholds_path,
)
from ssdv.mis.whatif import build_whatif
from ssdv.money import money
from ssdv.officemitra.firm import build_roster
from ssdv.officemitra.insights import build_red_flags
from ssdv.officemitra.risk import AMBER, GREEN, RED, assess_risk
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"
AS_OF = date(2024, 4, 30)


def test_build_policy_accepts_percentages_or_fractions_and_validates() -> None:
    from_ui = build_policy({"dso_days_max": 90, "customer_share_max": 50}, percent=True)
    assert from_ui.dso_days_max == 90
    assert from_ui.customer_share_max == money("0.50")
    from_file = build_policy({"customer_share_max": 0.5, "collection_efficiency_min": 70})
    assert from_file.customer_share_max == money("0.50")
    assert from_file.collection_efficiency_min == money("0.70")
    assert from_file.vendor_share_max == DEFAULT_POLICY.vendor_share_max

    with pytest.raises(PolicyError, match="between"):
        build_policy({"dso_days_max": 0})
    with pytest.raises(PolicyError, match="Unknown"):
        build_policy({"dso_limit": 90})
    with pytest.raises(PolicyError, match="number"):
        build_policy({"dso_days_max": "ninety"})
    with pytest.raises(PolicyError, match="red limit"):
        build_policy({"runway_red_months": 8, "runway_amber_months": 6})


def test_save_writes_only_changes_and_reset_removes_file(tmp_path: Path) -> None:
    db = tmp_path / "ssdv_client.sqlite"
    assert load_policy(db) == DEFAULT_POLICY
    saved = save_policy(db, build_policy({"dso_days_max": 90, "runway_amber_months": 9}))
    assert saved == thresholds_path(db)
    text = saved.read_text(encoding="utf-8")
    assert "dso_days_max: 90" in text and "runway_amber_months: 9.0" in text
    assert "customer_share_max" not in text
    assert load_policy(db).dso_days_max == 90
    assert save_policy(db, DEFAULT_POLICY) is None
    assert not thresholds_path(db).exists()


def _snap(**overrides) -> SimpleNamespace:
    series = SimpleNamespace(
        sales=(money("500000"),) * 3,
        cogs=(money("400000"),) * 3,
        opex=(money("200000"),) * 3,
    )
    base = dict(
        as_of=date(2026, 3, 31),
        series=series,
        cash=money("450000"),
        ar=money("600000"),
        dso=100,
        equity=money("1000000"),
        monthly_profit=money("-100000"),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_same_books_are_judged_by_each_clients_own_limits() -> None:
    snap = _snap()  # 4.5 months runway, DSO 100
    assert assess_risk(snap).band == AMBER
    assert build_red_flags(snap) == ()

    strict = build_policy({"dso_days_max": 60, "runway_red_months": 5, "runway_amber_months": 8})
    tight = assess_risk(_snap(policy=strict))
    assert tight.band == RED
    assert "below 5 months" in tight.top_alert
    flags = build_red_flags(_snap(policy=strict))
    assert [f.text for f in flags] == ["DSO 100 days exceeds 60-day policy."]

    relaxed = build_policy({"runway_red_months": 1, "runway_amber_months": 3})
    assert assess_risk(_snap(policy=relaxed)).band == GREEN


def test_whatif_wording_follows_the_policy() -> None:
    snap = SimpleNamespace(
        dso=154,
        ar=money("54600000"),
        fy=SimpleNamespace(
            sales=money("100000000"),
            cogs=money("80000000"),
            opex=money("5000000"),
            receipts=money("70000000"),
        ),
        ytd_profit=money("15000000"),
        cash_blocked_90=money("33400000"),
        dso_policy_gap_ar=money("12000000"),
        policy=build_policy({"dso_days_max": 90, "collection_efficiency_min": 75}),
    )
    rows = {row.id: row for row in build_whatif(snap)}
    assert "90 days" in rows["dso_to_120"].prompt
    assert "90-day policy" in rows["dso_to_120"].result
    assert "75%" in rows["collections_to_80"].prompt
    assert rows["collections_to_80"].delta_inr == money("5000000")


def test_vault_thresholds_flow_into_packs_payload_and_roster(tmp_path: Path) -> None:
    for name in ("alpha", "beta"):
        load_into_vault(
            tmp_path / f"ssdv_{name}.sqlite",
            source="generic",
            journals=EXAMPLE / "journals.csv",
            account_map=EXAMPLE / "ledger_map.csv",
            company_name=name.title(),
            force=True,
        )
    alpha = tmp_path / "ssdv_alpha.sqlite"
    save_policy(alpha, build_policy({"dso_days_max": 15, "customer_share_max": 20}, percent=True))

    engine = make_engine(alpha)
    create_schema(engine)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, AS_OF)
        assert snap.policy.dso_days_max == 15
        rows = {row.id: row for row in scorecard(snap)}
        assert rows["collections"].policy == "DSO <= 15 days"
        assert rows["customer_concentration"].policy == "Top customer < 20%"
        payload = snapshot_payload(snap, "all")
        fields = {f["name"]: f for f in payload["thresholds"]["fields"]}
        assert payload["thresholds"]["custom"] is True
        assert fields["dso_days_max"]["value"] == 15 and fields["dso_days_max"]["custom"]
        assert fields["customer_share_max"]["value"] == pytest.approx(20.0)
        assert not fields["vendor_share_max"]["custom"]
        assert any("15-day policy" in f for f in board_pack(snap).notes + tuple(
            item["text"] for item in payload["red_flags"]
        )) or snap.dso is None or snap.dso <= 15

    # The other client keeps the defaults.
    engine_b = make_engine(tmp_path / "ssdv_beta.sqlite")
    create_schema(engine_b)
    with session_scope(engine_b) as session:
        assert mis_snapshot(session, AS_OF).policy == DEFAULT_POLICY

    roster = build_roster(AS_OF, data_dir=tmp_path, limit=20)
    assert {row.company for row in roster.rows} == {"Alpha", "Beta"}
    assert Decimal
