"""Multi-client firm roster for CA Pack / Enterprise (one SQLite vault per company)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from ssdv.connectors.base import ConnectorError
from ssdv.db import create_schema, make_engine, session_scope
from ssdv.mis import mis_snapshot
from ssdv.mis.runway import runway_text
from ssdv.models import Voucher
from ssdv.money import ZERO, money
from ssdv.officemitra.quality import assess_session
from ssdv.officemitra.risk import RISK_ORDER, assess_risk
from ssdv.paths import user_data_dir

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class ClientSummary:
    db_path: Path
    vault_label: str
    company: str
    sales: Decimal
    cash: Decimal
    ar_90: Decimal
    working_capital: Decimal
    ar: Decimal
    error: str | None = None
    score: int | None = None
    reviewed: bool = False
    ppt_allowed: bool = False
    approved: bool = False
    risk: str = ""
    runway_months: Decimal | None = None
    monthly_burn: Decimal = ZERO
    top_alert: str = ""


@dataclass(frozen=True)
class FirmRoster:
    as_of: date
    rows: tuple[ClientSummary, ...]
    hidden: int
    company_limit: int | None


def vault_data_dir(data_dir: Path | None = None) -> Path:
    folder = data_dir if data_dir is not None else user_data_dir() / "data"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def client_slug(company_name: str) -> str:
    slug = _SLUG_RE.sub("-", company_name.strip().casefold()).strip("-")
    return slug[:48] or "client"


def client_vault_path(company_name: str, *, data_dir: Path | None = None) -> Path:
    return vault_data_dir(data_dir) / f"ssdv_{client_slug(company_name)}.sqlite"


def voucher_count(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    try:
        engine = make_engine(db_path)
        create_schema(engine)
        with session_scope(engine) as session:
            return int(session.scalar(select(func.count()).select_from(Voucher)) or 0)
    except (OSError, SQLAlchemyError, ValueError):
        return 0


def discover_vaults(data_dir: Path | None = None) -> list[Path]:
    folder = vault_data_dir(data_dir)
    found = [path for path in sorted(folder.glob("*.sqlite")) if voucher_count(path) > 0]
    return found


def effective_company_limit() -> int | None:
    from ssdv.officemitra.entitlements import current_entitlements

    return current_entitlements().company_limit


def apply_company_limit(
    paths: list[Path],
    *,
    limit: int | None = None,
) -> tuple[list[Path], int]:
    from ssdv.officemitra.demo import is_demo_vault

    cap = effective_company_limit() if limit is None else limit
    # Shipped demo books are synthetic and never count against the client limit.
    clients = [path for path in paths if not is_demo_vault(path)]
    demos = [path for path in paths if path not in clients]
    if cap is None or len(clients) <= cap:
        return clients + demos, 0
    return clients[:cap] + demos, len(clients) - cap


def assert_can_add_vault(
    dest: Path,
    *,
    limit: int | None = None,
    data_dir: Path | None = None,
) -> None:
    cap = effective_company_limit() if limit is None else limit
    if cap is None:
        return
    from ssdv.officemitra.demo import is_demo_vault

    existing = [path for path in discover_vaults(data_dir or dest.parent) if not is_demo_vault(path)]
    dest_resolved = dest.resolve()
    if any(path.resolve() == dest_resolved for path in existing):
        return
    if len(existing) >= cap:
        raise ConnectorError(
            f"This license allows {cap} companies. "
            "Open an existing client book or upgrade the CA Pack."
        )


def summarize_vault(db_path: Path, as_of: date) -> ClientSummary:
    label = db_path.stem
    try:
        engine = make_engine(db_path)
        create_schema(engine)
        with session_scope(engine) as session:
            snap = mis_snapshot(session, as_of)
            quality = assess_session(session, as_of, db_path)
            risk = assess_risk(snap)
        aging = snap.ar_aging or {}
        ar_90 = money(aging.get("90+", ZERO))
        return ClientSummary(
            db_path=db_path,
            vault_label=label,
            company=str(snap.company_name or label),
            sales=money(snap.fy.sales),
            cash=money(snap.cash),
            ar_90=ar_90,
            working_capital=money(snap.working_capital),
            ar=money(snap.ar),
            score=quality.score,
            reviewed=quality.reviewed,
            ppt_allowed=quality.ppt_allowed,
            approved=quality.approved,
            risk=risk.band,
            runway_months=risk.runway,
            monthly_burn=risk.base.burn,
            top_alert=risk.top_alert,
        )
    except (OSError, SQLAlchemyError, ValueError, KeyError) as exc:
        return ClientSummary(
            db_path=db_path,
            vault_label=label,
            company=label,
            sales=ZERO,
            cash=ZERO,
            ar_90=ZERO,
            working_capital=ZERO,
            ar=ZERO,
            error=str(exc),
        )


def _triage_key(row: ClientSummary) -> tuple[int, int, Decimal, Decimal, str]:
    """Unreadable books first, then red / amber / green, shortest runway, largest burn."""
    runway = row.runway_months if row.runway_months is not None else Decimal(9999)
    return (0 if row.error else 1, RISK_ORDER.get(row.risk, 3), runway, -row.monthly_burn, row.company.casefold())


def build_roster(
    as_of: date,
    *,
    data_dir: Path | None = None,
    limit: int | None = None,
) -> FirmRoster:
    visible, hidden = apply_company_limit(discover_vaults(data_dir), limit=limit)
    rows = tuple(sorted((summarize_vault(path, as_of) for path in visible), key=_triage_key))
    cap = effective_company_limit() if limit is None else limit
    return FirmRoster(as_of=as_of, rows=rows, hidden=hidden, company_limit=cap)


def roster_as_dicts(roster: FirmRoster) -> list[dict[str, str | int | None]]:
    out: list[dict[str, str | int | None]] = []
    for row in roster.rows:
        out.append(
            {
                "db_path": str(row.db_path),
                "vault": row.vault_label,
                "company": row.company,
                "sales": str(row.sales),
                "cash": str(row.cash),
                "ar_90": str(row.ar_90),
                "working_capital": str(row.working_capital),
                "ar": str(row.ar),
                "score": None if row.score is None else str(row.score),
                "reviewed": "yes" if row.reviewed else "no",
                "approved": "yes" if row.approved else "no",
                "risk": row.risk or None,
                "runway_months": None if row.runway_months is None else str(row.runway_months),
                "monthly_burn": str(row.monthly_burn),
                "top_alert": row.top_alert or None,
                "error": row.error,
            }
        )
    return out


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_firm_html(roster: FirmRoster) -> str:
    rows_html = []
    for row in roster.rows:
        err = f'<td class="err">{_esc(row.error)}</td>' if row.error else "<td></td>"
        runway = "" if row.error else runway_text(row.runway_months)
        rows_html.append(
            "<tr>"
            f"<td class='risk {_esc(row.risk)}'>{_esc(row.risk.upper())}</td>"
            f"<td>{_esc(row.company)}</td>"
            f"<td class='num'>{_esc(runway)}</td>"
            f"<td class='num'>{row.sales:,.2f}</td>"
            f"<td class='num'>{row.ar_90:,.2f}</td>"
            f"<td class='num'>{row.cash:,.2f}</td>"
            f"<td class='num'>{row.working_capital:,.2f}</td>"
            f"<td class='num'>{'' if row.score is None else row.score}</td>"
            f"<td>{'approved' if row.approved else 'yes' if row.reviewed else 'no'}</td>"
            f"<td>{_esc(row.top_alert)}</td>"
            f"<td>{_esc(row.vault_label)}</td>"
            f"{err}"
            "</tr>"
        )
    hidden_note = (
        f"<p class='meta'>{roster.hidden} further vault(s) hidden by the company limit "
        f"({roster.company_limit}).</p>"
        if roster.hidden
        else ""
    )
    body = "\n".join(rows_html) or "<tr><td colspan='12'>No client books found.</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>OfficeMitra firm roster</title>
<style>
body {{ font-family: Georgia, serif; margin: 2rem; color: #1C1917; background: #FAF7F2; }}
h1 {{ letter-spacing: -0.03em; }}
.meta {{ color: #44403C; }}
table {{ border-collapse: collapse; width: 100%; background: #fff; }}
th, td {{ border: 1px solid #E4DCCB; padding: 0.55rem 0.7rem; text-align: left; }}
th {{ background: #F3F0E8; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td.err {{ color: #B42318; }}
td.risk {{ font-weight: 700; }}
td.risk.red {{ color: #B42318; }}
td.risk.amber {{ color: #B54708; }}
td.risk.green {{ color: #067647; }}
</style></head>
<body>
<p class="meta">OfficeMitra · client books</p>
<h1>Firm roster</h1>
<p class="meta">As of { _esc(roster.as_of.isoformat()) } · {len(roster.rows)} shown</p>
{hidden_note}
<table>
<thead><tr>
<th>Risk</th><th>Client</th><th class="num">Runway</th>
<th class="num">Revenue</th><th class="num">AR 90+</th>
<th class="num">Cash</th><th class="num">Working capital</th>
<th class="num">Score</th><th>Reviewed</th><th>Top alert</th><th>Vault</th><th></th>
</tr></thead>
<tbody>
{body}
</tbody>
</table>
<p class="meta">Sorted by risk, then shortest cash runway. Risk combines the board red flags with runway.</p>
<p class="meta">Each row is a separate SQLite vault. Open a book in OfficeMitra for the full CEO pack.</p>
</body></html>
"""
