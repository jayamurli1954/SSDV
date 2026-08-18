from __future__ import annotations

from sqlalchemy.orm import Session

from ssdv.models import Account
from ssdv.paths import coa_path, load_yaml


def load_coa(session: Session) -> int:
    payload = load_yaml(coa_path())
    count = 0
    for row in payload["accounts"]:
        code = str(row["code"])
        existing = session.get(Account, code)
        if existing is None:
            session.add(
                Account(
                    code=code,
                    name=row["name"],
                    type=row["type"],
                    subtype=row["subtype"],
                    postable=bool(row.get("postable", True)),
                    control=bool(row.get("control", False)),
                )
            )
            count += 1
        else:
            existing.name = row["name"]
            existing.type = row["type"]
            existing.subtype = row["subtype"]
            existing.postable = bool(row.get("postable", True))
            existing.control = bool(row.get("control", False))
    session.flush()
    return count
