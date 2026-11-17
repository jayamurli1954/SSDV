import json
from datetime import date
from pathlib import Path

import pytest
from pptx import Presentation

from ssdv.connectors.pipeline import load_into_vault
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.mis import mis_snapshot, snapshot_payload
from ssdv.officemitra.approval import (
    NOT_APPROVED_REASON,
    ApprovalError,
    approval_required,
    approval_sidecar_path,
    approve,
    disable_partner_approval,
    firm_approval_path,
    set_partner_pin,
    verify_pin,
    withdraw_approval,
)
from ssdv.officemitra.export import write_ppt
from ssdv.officemitra.firm import build_roster, voucher_count
from ssdv.officemitra.quality import (
    ExportBlocked,
    assess_session,
    budget_sidecar_path,
    enrich_payload,
    mark_reviewed,
)
from ssdv.paths import repo_root

EXAMPLE = repo_root() / "examples" / "generic_ingest"
AS_OF = date(2024, 4, 30)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OFFICEMITRA_HOME", str(tmp_path))
    (tmp_path / "data").mkdir()
    return tmp_path


def _client(home: Path) -> Path:
    db = home / "data" / "ssdv_client.sqlite"
    load_into_vault(
        db,
        source="generic",
        journals=EXAMPLE / "journals.csv",
        account_map=EXAMPLE / "ledger_map.csv",
        company_name="Client Co",
        force=True,
    )
    budget_sidecar_path(db).write_text("sales: 180000\n", encoding="utf-8")
    return db


def _report(db: Path):
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        return assess_session(session, AS_OF, db)


def _payload(db: Path) -> dict:
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        snap = mis_snapshot(session, AS_OF)
        return enrich_payload(snapshot_payload(snap, "all"), session, db, AS_OF)


def _review(db: Path, name: str | None = None) -> None:
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        mark_reviewed(db, AS_OF, session=session, reviewed_by=name)


def test_pin_setup_rules_and_hashing(home: Path) -> None:
    assert approval_required() is False
    assert verify_pin("anything") is False
    with pytest.raises(ApprovalError, match="name"):
        set_partner_pin("  ", "2468")
    with pytest.raises(ApprovalError, match="at least 4"):
        set_partner_pin("CA Partner", "12")

    set_partner_pin("CA Partner", "2468")
    assert approval_required() is True
    assert verify_pin("2468") is True
    assert verify_pin("2469") is False
    stored = firm_approval_path().read_text(encoding="utf-8")
    assert "2468" not in stored
    assert set(json.loads(stored)) == {"partner_name", "pin_salt", "pin_hash", "set_at"}

    # Changing the PIN or turning the gate off needs the current PIN.
    with pytest.raises(ApprovalError, match="current partner PIN"):
        set_partner_pin("Someone Else", "9999", current_pin="0000")
    set_partner_pin("CA Partner", "1357", current_pin="2468")
    assert verify_pin("1357") is True
    with pytest.raises(ApprovalError):
        disable_partner_approval("2468")
    disable_partner_approval("1357")
    assert approval_required() is False


def test_without_a_pin_review_alone_unlocks_ppt(home: Path) -> None:
    db = _client(home)
    _review(db)
    report = _report(db)
    assert report.approval_required is False
    assert report.ppt_allowed is True


def test_partner_approval_gates_ppt_and_goes_stale(home: Path) -> None:
    db = _client(home)
    set_partner_pin("CA Partner", "2468")
    count = voucher_count(db)

    # Approval cannot come before review.
    with pytest.raises(ApprovalError, match="reviewed"):
        approve(db, AS_OF, voucher_count=count, reviewed=False, pin="2468")

    _review(db, "Asha (Analyst)")
    waiting = _report(db)
    assert waiting.reviewed is True
    assert waiting.approved is False
    assert waiting.ppt_allowed is False
    assert waiting.ppt_block_reason == NOT_APPROVED_REASON
    with pytest.raises(ExportBlocked):
        write_ppt(_payload(db), home / "blocked.pptx")

    with pytest.raises(ApprovalError, match="PIN"):
        approve(db, AS_OF, voucher_count=count, reviewed=True, pin="0000")
    assert not approval_sidecar_path(db).exists()

    approve(db, AS_OF, voucher_count=count, reviewed=True, pin="2468")
    done = _report(db)
    assert done.approved is True
    assert done.approved_by == "CA Partner"
    assert done.ppt_allowed is True

    payload = _payload(db)
    assert payload["reviewed_by"] == "Asha (Analyst)"
    assert payload["approval"]["approved"] is True
    out = home / "board.pptx"
    write_ppt(payload, out)
    title_text = "\n".join(
        shape.text_frame.text
        for shape in Presentation(out).slides[0].shapes
        if shape.has_text_frame
    )
    assert "Prepared by: Asha (Analyst)" in title_text
    assert "Approved by: CA Partner" in title_text

    roster = build_roster(AS_OF, data_dir=home / "data", limit=20)
    assert roster.rows[0].approved is True

    # A different as-of date is a different sign-off.
    engine = make_engine(db)
    create_schema(engine)
    with session_scope(engine) as session:
        other = assess_session(session, date(2024, 4, 29), db)
    assert other.approved is False

    with pytest.raises(ApprovalError):
        withdraw_approval(db, pin="0000")
    withdraw_approval(db, pin="2468")
    assert _report(db).ppt_allowed is False


def test_re_review_after_new_vouchers_voids_approval(home: Path) -> None:
    db = _client(home)
    set_partner_pin("CA Partner", "2468")
    _review(db)
    approve(db, AS_OF, voucher_count=voucher_count(db), reviewed=True, pin="2468")
    assert _report(db).approved is True

    # Simulate books changing after sign-off: the stored count no longer matches.
    sidecar = approval_sidecar_path(db)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["voucher_count"] = data["voucher_count"] - 1
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    stale = _report(db)
    assert stale.approved is False
    assert stale.ppt_block_reason == NOT_APPROVED_REASON
