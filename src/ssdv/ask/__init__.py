from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ssdv.ask.facts import facts_from_snapshot
from ssdv.ask.ollama import AskError, chat, default_host, default_model
from ssdv.ask.prompt import SYSTEM, user_prompt
from ssdv.mis.kpis import mis_snapshot

__all__ = [
    "AskError",
    "ask_books",
    "default_host",
    "default_model",
]


def ask_books(
    session: Session,
    question: str,
    as_of: date,
    company: dict | None = None,
    *,
    model: str | None = None,
    host: str | None = None,
) -> str:
    if not question.strip():
        raise AskError("Question is empty.")
    snap = mis_snapshot(session, as_of, company=company)
    facts = facts_from_snapshot(snap)
    return chat(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(question, facts)},
        ],
        model=model,
        host=host,
    )
