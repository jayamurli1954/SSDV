from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_no(session: Session, model: type, fy_column, fy: str) -> int:
    count = session.scalar(select(func.count()).select_from(model).where(fy_column == fy))
    return int(count or 0) + 1
