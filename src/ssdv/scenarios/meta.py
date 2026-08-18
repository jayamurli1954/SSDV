from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ssdv.models import ScenarioMeta
from ssdv.scenarios.spec import GOLDEN


def record_scenario(session: Session, company: dict[str, Any]) -> ScenarioMeta:
    sid = str(company["generator"]["scenario"])
    meta = GOLDEN[sid]
    row = session.get(ScenarioMeta, sid)
    if row is None:
        row = ScenarioMeta(
            scenario_id=sid,
            title=meta["title"],
            known_cause=meta["known_cause"],
            golden_explanation=meta["golden"],
        )
        session.add(row)
    else:
        row.title = meta["title"]
        row.known_cause = meta["known_cause"]
        row.golden_explanation = meta["golden"]
    session.flush()
    return row


def load_recorded_scenario(session: Session) -> ScenarioMeta | None:
    return session.scalars(select(ScenarioMeta)).first()
