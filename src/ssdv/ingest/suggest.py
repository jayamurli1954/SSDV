"""Assisted ledger mapping: review a source export before import, suggest chart codes,
and keep the confirmed map beside the client vault for the next import.

Deterministic and offline. Suggestions are only proposals: nothing is posted until a
person confirms a code for every ledger that the saved map does not already cover.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from ssdv.gl import AP_CONTROL, AR_CONTROL
from ssdv.ingest.client_chart import ClientChart, map_lookup
from ssdv.ingest.errors import IngestError
from ssdv.ingest.journals import SourceLine, load_journal_csv
from ssdv.ingest.mapping import load_account_map, resolve_account
from ssdv.money import ZERO, money
from ssdv.paths import coa_path, load_yaml

MAPPED = "mapped"
GUESSED = "guessed"
UNMAPPED = "unmapped"
MAX_SUGGESTIONS = 3
_MIN_NAME_SCORE = 0.45
# Only suggestions at least this strong are pre-selected for the reviewer.
CONFIDENT_SCORE = 0.6
_WORD_RE = re.compile(r"[a-z0-9]+")

# Phrase -> chart code. A phrase matches on whole words, never inside another word.
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("cash in hand", "110000"),
    ("petty cash", "110000"),
    ("cash", "110000"),
    ("stock", "130000"),
    ("inventory", "130000"),
    ("tds receivable", "151000"),
    ("prepaid", "152000"),
    ("furniture", "161000"),
    ("computer", "162000"),
    ("laptop", "162000"),
    ("tds payable", "231000"),
    ("tds", "231000"),
    ("salary payable", "232000"),
    ("outstanding expenses", "233000"),
    ("expenses payable", "233000"),
    ("term loan", "241000"),
    ("loan", "241000"),
    ("capital", "310000"),
    ("reserves", "320000"),
    ("sales return", "410100"),
    ("sales returns", "410100"),
    ("interest received", "421000"),
    ("interest income", "421000"),
    ("discount received", "422000"),
    ("other income", "420000"),
    ("miscellaneous income", "420000"),
    ("cost of goods sold", "510000"),
    ("freight inward", "520000"),
    ("carriage inward", "520000"),
    ("purchase return", "521000"),
    ("purchase returns", "521000"),
    ("salary", "610000"),
    ("salaries", "610000"),
    ("wages", "610000"),
    ("staff welfare", "611000"),
    ("rent", "620000"),
    ("electricity", "621000"),
    ("power", "621000"),
    ("telephone", "622000"),
    ("internet", "622000"),
    ("mobile", "622000"),
    ("insurance", "623000"),
    ("repairs", "624000"),
    ("repair", "624000"),
    ("maintenance", "624000"),
    ("fuel", "625000"),
    ("petrol", "625000"),
    ("diesel", "625000"),
    ("conveyance", "625000"),
    ("travelling", "625000"),
    ("travel", "625000"),
    ("printing", "626000"),
    ("stationery", "626000"),
    ("office expenses", "626000"),
    ("professional", "627000"),
    ("legal", "627000"),
    ("audit", "627000"),
    ("consultancy", "627000"),
    ("packing", "628000"),
    ("freight outward", "629000"),
    ("carriage outward", "629000"),
    ("discount allowed", "630000"),
    ("bad debts", "631000"),
    ("bad debt", "631000"),
    ("bank charges", "640000"),
    ("interest on loan", "641000"),
    ("interest on od", "642000"),
    ("depreciation", "650000"),
    ("late fee", "660000"),
)


# The client's own group / parent for a ledger (e.g. Tally "Under" groups).
_GROUP_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("cash in hand", "110000"),
    ("bank od", "113000"),
    ("bank occ", "113000"),
    ("bank overdraft", "113000"),
    ("bank accounts", "111000"),
    ("sundry debtors", "120000"),
    ("trade receivables", "120000"),
    ("sundry creditors", "210000"),
    ("trade payables", "210000"),
    ("stock in hand", "130000"),
    ("purchase accounts", "130000"),
    ("sales accounts", "410000"),
    ("revenue from operations", "410000"),
    ("indirect incomes", "420000"),
    ("other income", "420000"),
    ("capital account", "310000"),
    ("reserves and surplus", "320000"),
    ("secured loans", "241000"),
    ("unsecured loans", "241000"),
    ("loans liability", "241000"),
)
_GROUP_SCORE = 0.66


@dataclass(frozen=True)
class ChartAccount:
    code: str
    name: str
    type: str

    @property
    def label(self) -> str:
        return f"{self.code} — {self.name}"


@dataclass(frozen=True)
class Suggestion:
    code: str
    name: str
    reason: str
    score: float


@dataclass(frozen=True)
class LedgerReview:
    ledger: str
    lines: int
    debit: Decimal
    credit: Decimal
    status: str
    code: str | None
    suggestions: tuple[Suggestion, ...]
    client_code: str | None = None
    client_name: str | None = None
    client_group: str | None = None

    @property
    def proposed(self) -> str | None:
        """Code to pre-select: the resolved one, else a confident best suggestion."""
        if self.code:
            return self.code
        if self.suggestions and self.suggestions[0].score >= CONFIDENT_SCORE:
            return self.suggestions[0].code
        return None

    @property
    def reason(self) -> str:
        if self.status == MAPPED:
            return "Saved map"
        if self.status == GUESSED:
            return "Auto-matched by keyword — please check"
        if not self.suggestions:
            return "No suggestion — choose a ledger"
        best = self.suggestions[0]
        if best.score >= CONFIDENT_SCORE:
            return best.reason
        return f"No confident match — closest is {best.name} ({best.code}); choose a ledger"


def postable_chart() -> list[ChartAccount]:
    rows = load_yaml(coa_path())["accounts"]
    return [
        ChartAccount(code=str(row["code"]), name=str(row["name"]), type=str(row["type"]))
        for row in rows
        if bool(row.get("postable", True))
    ]


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.casefold().replace("&", " and "))


def _has_phrase(words: list[str], phrase: str) -> bool:
    target = phrase.split()
    span = len(target)
    return any(words[i : i + span] == target for i in range(len(words) - span + 1))


def suggest_codes(
    ledger: str,
    chart: list[ChartAccount],
    *,
    party_type: str | None = None,
    group: str | None = None,
) -> tuple[Suggestion, ...]:
    by_code = {item.code: item for item in chart}
    found: dict[str, Suggestion] = {}

    def offer(code: str, reason: str, score: float) -> None:
        account = by_code.get(code)
        if account is None:
            return
        current = found.get(code)
        if current is None or score > current.score:
            found[code] = Suggestion(code=code, name=account.name, reason=reason, score=score)

    if party_type == "customer":
        offer(AR_CONTROL, "Party ledger on sales / receipt vouchers", 0.9)
    elif party_type == "vendor":
        offer(AP_CONTROL, "Party ledger on purchase / payment vouchers", 0.9)

    group_words = _words(group or "")
    for phrase, code in _GROUP_KEYWORDS:
        if _has_phrase(group_words, phrase):
            offer(code, f"Client group '{group}'", _GROUP_SCORE)

    words = _words(ledger)
    for phrase, code in _KEYWORDS:
        if _has_phrase(words, phrase):
            # Longer phrases are more specific, so they outrank single words.
            offer(code, f"Keyword '{phrase}'", 0.7 + 0.05 * min(len(phrase.split()), 4))

    joined = " ".join(words)
    word_set = set(words)
    for account in chart:
        target = _words(account.name)
        if not target or not words:
            continue
        ratio = SequenceMatcher(None, joined, " ".join(target)).ratio()
        overlap = len(word_set & set(target)) / len(word_set | set(target))
        score = max(ratio, overlap)
        if score >= _MIN_NAME_SCORE:
            offer(account.code, f"Name is close to '{account.name}'", round(score * 0.75, 3))

    ranked = sorted(found.values(), key=lambda item: (-item.score, item.code))
    return tuple(ranked[:MAX_SUGGESTIONS])


def review_ledgers(
    lines: list[SourceLine],
    mapping: dict[str, str],
    chart: list[ChartAccount] | None = None,
    client_chart: ClientChart | None = None,
) -> list[LedgerReview]:
    """One row per distinct source ledger: already mapped, keyword-guessed, or unmapped."""
    accounts = chart if chart is not None else postable_chart()
    known = {item.code for item in accounts}
    totals: dict[str, list] = {}
    for row in lines:
        name = row.account.strip()
        slot = totals.setdefault(name, [0, ZERO, ZERO, Counter()])
        slot[0] += 1
        slot[1] = money(slot[1] + row.debit)
        slot[2] = money(slot[2] + row.credit)
        if row.party_type:
            slot[3][row.party_type] += 1

    out: list[LedgerReview] = []
    for name, (count, debit, credit, parties) in totals.items():
        party_type = parties.most_common(1)[0][0] if parties else None
        cchart = client_chart or ClientChart()
        entry = cchart.find(name)
        # A number from the client's own chart is never read as a standard code.
        own_code = cchart.has_code(name)
        saved = map_lookup(name, entry, mapping)
        label = entry.name if entry else name
        if saved and saved in known:
            status, code = MAPPED, saved
        elif name in known and not own_code:
            status, code = MAPPED, name
        else:
            try:
                status, code = GUESSED, resolve_account(label, {}, known)
            except IngestError:
                status, code = UNMAPPED, None
        suggestions = (
            ()
            if status == MAPPED
            else suggest_codes(
                label,
                accounts,
                party_type=party_type,
                group=entry.group if entry else None,
            )
        )
        out.append(
            LedgerReview(
                ledger=name,
                lines=count,
                debit=debit,
                credit=credit,
                status=status,
                code=code,
                suggestions=suggestions,
                client_code=entry.code if entry else None,
                client_name=entry.name if entry else None,
                client_group=entry.group if entry else None,
            )
        )
    order = {UNMAPPED: 0, GUESSED: 1, MAPPED: 2}
    return sorted(out, key=lambda item: (order[item.status], item.ledger.casefold()))


def needs_review(rows: list[LedgerReview]) -> list[LedgerReview]:
    return [row for row in rows if row.status != MAPPED]


def load_source_lines(source: str, journals: Path) -> list[SourceLine]:
    if source in {"tally", "tally-http"}:
        from ssdv.ingest.tally_daybook import load_journal_tally_daybook

        return load_journal_tally_daybook(journals)
    return load_journal_csv(journals)


def ledger_map_path(db_path: Path) -> Path:
    """Confirmed ledger map kept beside the client vault and reused on every import."""
    return db_path.with_name(f"{db_path.stem}.ledgermap.yaml")


def _original_keys(mapping: dict[str, str]) -> dict[str, str]:
    """``load_account_map`` adds a casefolded twin of every key; keep one spelling each."""
    out: dict[str, str] = {}
    spelling: dict[str, str] = {}
    for key, code in mapping.items():
        folded = key.casefold()
        current = spelling.get(folded)
        if current is None or (current == folded and key != folded):
            if current is not None:
                out.pop(current, None)
            spelling[folded] = key
            out[key] = code
    return out


def effective_map(db_path: Path, uploaded: Path | None = None) -> dict[str, str]:
    """Saved client map, overridden by a map file uploaded for this import."""
    saved = ledger_map_path(db_path)
    merged = _original_keys(load_account_map(saved)) if saved.is_file() else {}
    if uploaded is not None:
        for key, code in _original_keys(load_account_map(uploaded)).items():
            twin = next((k for k in merged if k.casefold() == key.casefold()), None)
            if twin is not None:
                del merged[twin]
            merged[key] = code
    return merged


def save_ledger_map(db_path: Path, mapping: dict[str, str]) -> Path:
    path = ledger_map_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {key: str(mapping[key]) for key in sorted(mapping, key=str.casefold)}
    header = (
        "# Confirmed ledger map for this client book. OfficeMitra reuses it on every import.\n"
        "# source ledger name: chart account code\n"
    )
    body = yaml.safe_dump({"ledgers": ordered}, allow_unicode=True, sort_keys=False)
    path.write_text(header + body, encoding="utf-8")
    return path


def confirm_map(
    db_path: Path,
    base: dict[str, str],
    choices: dict[str, str],
    chart: list[ChartAccount] | None = None,
) -> Path:
    """Validate the reviewer's choices and write the merged map beside the vault."""
    known = {item.code for item in (chart if chart is not None else postable_chart())}
    merged = dict(base)
    for ledger, code in choices.items():
        value = str(code or "").strip()
        if value not in known:
            raise IngestError(f"Choose a chart ledger for {ledger!r} before importing.")
        twin = next((k for k in merged if k.casefold() == ledger.casefold()), None)
        if twin is not None:
            del merged[twin]
        merged[ledger] = value
    return save_ledger_map(db_path, merged)
