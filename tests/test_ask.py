from __future__ import annotations

import json
from datetime import date
from io import BytesIO

import pytest

from ssdv.ask.facts import compact_facts
from ssdv.ask.ollama import AskError, chat
from ssdv.ask.prompt import SYSTEM, user_prompt
from ssdv.cli import build_parser, main


def test_compact_facts_tails_months_and_hides_golden_for_imported() -> None:
    payload = {
        "company": "Sample",
        "as_of": "2024-04-30",
        "scenario": "imported",
        "known_cause": "should not leak",
        "golden": "planted text",
        "kpis": {"sales": "150000.00", "dso": 10},
        "fy": {"sales": "150000.00"},
        "prior": None,
        "scorecard": [],
        "series": {
            "grain": "month",
            "categories": [f"2023-{m:02d}" for m in range(1, 13)] + ["2024-01", "2024-02"],
            "labels": ["x"] * 14,
            "sales": [str(i) for i in range(14)],
            "cogs": ["0"] * 14,
            "gross_margin": ["0"] * 14,
            "purchases": ["0"] * 14,
            "receipts": ["0"] * 14,
            "payments": ["0"] * 14,
            "opex": ["0"] * 14,
        },
        "charts": {
            "ar_aging": {"type": "doughnut", "data": [{"label": "90+", "value": "1.00"}]},
            "ap_aging": {"type": "doughnut", "data": []},
            "pnl_mix": {"type": "pie", "data": []},
        },
    }
    facts = compact_facts(payload, months=12)
    assert facts["planted_ssdv_seed"] is False
    assert "ssdv_golden" not in facts
    assert len(facts["monthly"]["sales"]) == 12
    assert facts["monthly"]["sales"][0] == "2"
    assert facts["ar_aging"]["data"][0]["label"] == "90+"


def test_compact_facts_keeps_ssdv_cause_on_seed() -> None:
    facts = compact_facts(
        {
            "scenario": "cash_flow_crisis",
            "known_cause": "Sales up, DSO up, cash down",
            "golden": "Collections lag",
            "kpis": {},
            "series": {},
            "charts": {},
        }
    )
    assert facts["planted_ssdv_seed"] is True
    assert facts["ssdv_known_cause"] == "Sales up, DSO up, cash down"


def test_user_prompt_includes_question_and_facts() -> None:
    text = user_prompt("why is 90+ up", {"kpis": {"dso": 593}})
    assert "why is 90+ up" in text
    assert "593" in text
    assert "Answer ONLY from the FACTS JSON" in SYSTEM


def test_chat_reads_ollama_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    payload = json.dumps({"message": {"content": "90+ rose because receipts lagged sales."}})

    def fake_urlopen(request, timeout=0):
        assert "/api/chat" in request.full_url
        return FakeResponse(payload.encode("utf-8"))

    monkeypatch.setattr("ssdv.ask.ollama.urllib.request.urlopen", fake_urlopen)
    answer = chat([{"role": "user", "content": "hi"}], model="llama3.1:8b", host="http://127.0.0.1:11434")
    assert "receipts lagged" in answer


def test_chat_errors_when_ollama_down(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def boom(request, timeout=0):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr("ssdv.ask.ollama.urllib.request.urlopen", boom)
    with pytest.raises(AskError, match="Ollama is not running"):
        chat([{"role": "user", "content": "hi"}])


def test_ask_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["ask", "why", "is", "90+", "up", "--as-of", "2026-03-31", "--model", "qwen3:8b"]
    )
    assert args.question == ["why", "is", "90+", "up"]
    assert args.as_of == date(2026, 3, 31)
    assert args.model == "qwen3:8b"


def test_ask_cli_prints_ollama_down(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    def boom(*args, **kwargs):
        raise AskError("Ollama is not running on http://127.0.0.1:11434.")

    monkeypatch.setattr("ssdv.cli.ask_books", boom)
    code = main(["--db", str(tmp_path / "x.sqlite"), "ask", "why", "sales", "fell"])
    assert code == 1
