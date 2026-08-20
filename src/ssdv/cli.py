from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from ssdv.accounting.equation import accounting_equation
from ssdv.accounting.opening import bootstrap_books
from ssdv.accounting.trial_balance import ledger_balance, tb_totals, trial_balance
from ssdv.ask import AskError, ask_books, default_model
from ssdv.cash.aging import aging_totals, ap_aging, ar_aging
from ssdv.cash.generate import generate_settlements
from ssdv.cash.parties import customer_vendor_tops
from ssdv.connectors import (
    ConnectorError,
    ConnectorNotReady,
    list_connectors,
    load_into_vault,
    source_ids,
)
from ssdv.db import create_schema, drop_schema, make_engine, session_scope
from ssdv.ingest import IngestError
from ssdv.mis import PACK_IDS, mis_snapshot, render_mis, snapshot_payload
from ssdv.models import (
    Customer,
    Employee,
    Payment,
    Product,
    PurchaseBill,
    Receipt,
    SalesInvoice,
    Vendor,
)
from ssdv.officemitra import render_board_pdf, render_dashboard
from ssdv.paths import (
    connect_db_path,
    default_board_pack_path,
    default_dashboard_path,
    default_db_path,
    ingest_db_path,
    is_frozen,
    load_company,
    repo_root,
    user_data_dir,
)
from ssdv.period import generate_books
from ssdv.purchases.generate import generate_purchases
from ssdv.sales.generate import generate_sales
from ssdv.scenarios import (
    apply_scenario,
    record_scenario,
    scenario_ids,
    scenario_metrics,
    signal_holds,
)
from ssdv.scenarios.meta import load_recorded_scenario
from ssdv.scenarios.spec import GOLDEN
from ssdv.validate import run_gates


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _company(args: argparse.Namespace, session=None) -> dict:
    requested = getattr(args, "scenario", None)
    if requested:
        return apply_scenario(load_company(), requested)
    if session is not None:
        row = load_recorded_scenario(session)
        if row is not None:
            return apply_scenario(load_company(), row.scenario_id)
    return apply_scenario(load_company(), str(load_company()["generator"]["scenario"]))


def _db(args: argparse.Namespace) -> Path:
    db: Path = args.db
    scenario = getattr(args, "scenario", None)
    if scenario and scenario != "baseline" and db.resolve() == default_db_path().resolve():
        path = user_data_dir() / "data" / f"ssdv_{scenario}.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return db


def cmd_init(args: argparse.Namespace) -> int:
    db_path = _db(args)
    cfg = _company(args)
    engine = make_engine(db_path)
    if args.force:
        drop_schema(engine)
    create_schema(engine)
    with session_scope(engine) as session:
        voucher = bootstrap_books(session, company=cfg)
        created = generate_purchases(session, company=cfg)
        sold = generate_sales(session, company=cfg)
        receipts, payments = generate_settlements(session, company=cfg)
        books = generate_books(session, company=cfg)
        record_scenario(session, cfg)
        customers = session.scalar(select(func.count()).select_from(Customer))
        vendors = session.scalar(select(func.count()).select_from(Vendor))
        products = session.scalar(select(func.count()).select_from(Product))
        employees = session.scalar(select(func.count()).select_from(Employee))
        bills = session.scalar(select(func.count()).select_from(PurchaseBill))
        invoices = session.scalar(select(func.count()).select_from(SalesInvoice))
        receipt_n = session.scalar(select(func.count()).select_from(Receipt))
        payment_n = session.scalar(select(func.count()).select_from(Payment))
        print(f"Database: {db_path}")
        print(f"Scenario: {cfg['generator']['scenario']}")
        print(f"Opening voucher {voucher.voucher_type}/{voucher.fy_code}/{voucher.voucher_no:06d}")
        print(
            f"Customers {customers}  Vendors {vendors}  Products {products}  Employees {employees}"
        )
        print(f"Purchase bills {bills} (+{created} this run)")
        print(f"Sales invoices {invoices} (+{sold} this run)")
        print(f"Receipts {receipt_n} (+{receipts} this run)")
        print(f"Payments {payment_n} (+{payments} this run)")
        print(
            f"Opex +{books.expenses}  Charges +{books.charges}  EMI +{books.emis}  "
            f"GST +{books.gst}  Opex paid +{books.opex_paid}  "
            f"Depreciation +{books.depreciation}  Closing +{books.closing}"
        )
        print(cfg["scenario_meta"]["golden"])
    return 0


def cmd_tb(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    with session_scope(engine) as session:
        rows = trial_balance(session, args.as_of)
        debit, credit = tb_totals(rows)
        print(f"Trial Balance as of {args.as_of.isoformat()}")
        print(f"{'Code':<10} {'Account':<42} {'Debit':>16} {'Credit':>16}")
        for row in rows:
            print(
                f"{row.account_code:<10} {row.account_name:<42} "
                f"{row.debit:>16,.2f} {row.credit:>16,.2f}"
            )
        print(f"{'':<10} {'Total':<42} {debit:>16,.2f} {credit:>16,.2f}")
        if debit != credit:
            print("WARNING: trial balance does not tie")
            return 1
    return 0


def cmd_equation(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    with session_scope(engine) as session:
        snap = accounting_equation(session, args.as_of)
        print(f"Accounting equation as of {snap.as_of.isoformat()}")
        print(f"  Assets       {snap.assets:>16,.2f}")
        print(f"  Liabilities  {snap.liabilities:>16,.2f}")
        print(f"  Equity       {snap.equity:>16,.2f}")
        print(f"  Income       {snap.income:>16,.2f}")
        print(f"  Expenses     {snap.expenses:>16,.2f}")
        print(f"  Delta        {snap.delta:>16,.2f}")
        print("Holds" if snap.holds else "BROKEN")
        return 0 if snap.holds else 1


def cmd_ledger(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    with session_scope(engine) as session:
        balance = ledger_balance(session, args.account, args.as_of)
        print(f"{args.account} net debit balance as of {args.as_of.isoformat()}: {balance:,.2f}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    with session_scope(engine) as session:
        cfg = _company(args, session)
        gates = run_gates(session, args.as_of, company=cfg)
        failed = 0
        for gate in gates:
            status = "OK" if gate.ok else "FAIL"
            if not gate.ok:
                failed += 1
            print(f"{status:<4} {gate.name:<22} {gate.detail}")
        return 1 if failed else 0


def cmd_purchases(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    with session_scope(engine) as session:
        created = generate_purchases(session, company=_company(args, session))
        total = session.scalar(select(func.count()).select_from(PurchaseBill))
        print(f"Database: {_db(args)}")
        print(f"Purchase bills +{created} this run, total {total}")
    return 0


def cmd_sales(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    with session_scope(engine) as session:
        created = generate_sales(session, company=_company(args, session))
        total = session.scalar(select(func.count()).select_from(SalesInvoice))
        print(f"Database: {_db(args)}")
        print(f"Sales invoices +{created} this run, total {total}")
    return 0


def cmd_settle(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    with session_scope(engine) as session:
        created_r, created_p = generate_settlements(session, company=_company(args, session))
        receipts = session.scalar(select(func.count()).select_from(Receipt))
        payments = session.scalar(select(func.count()).select_from(Payment))
        print(f"Database: {_db(args)}")
        print(f"Receipts +{created_r} this run, total {receipts}")
        print(f"Payments +{created_p} this run, total {payments}")
    return 0


def cmd_aging(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    with session_scope(engine) as session:
        ar_rows = ar_aging(session, args.as_of)
        ap_rows = ap_aging(session, args.as_of)
        ar = aging_totals(ar_rows)
        ap = aging_totals(ap_rows)
        print(f"AR aging as of {args.as_of.isoformat()}  ({len(ar_rows)} open items)")
        for name in ("0-30", "31-60", "61-90", "91-120", "120+", "90+", "total"):
            print(f"  {name:<8} {ar[name]:>16,.2f}")
        print(f"AP aging as of {args.as_of.isoformat()}  ({len(ap_rows)} open items)")
        for name in ("0-30", "31-60", "61-90", "91-120", "120+", "90+", "total"):
            print(f"  {name:<8} {ap[name]:>16,.2f}")
        customers, rank, vendors = customer_vendor_tops(session, args.as_of)
        print(f"Top overdue customers ({rank})")
        for row in customers:
            days = f"{row.oldest_days} d" if row.oldest_days is not None else "unaged"
            print(
                f"  {row.name:<28} 90+ {row.overdue_90:>14,.2f}  AR {row.outstanding:>14,.2f}  {days}"
            )
        print("Top vendor exposure")
        for row in vendors:
            days = f"{row.oldest_days} d" if row.oldest_days is not None else "unaged"
            print(
                f"  {row.name:<28} AP {row.outstanding:>14,.2f}  90+ {row.overdue_90:>14,.2f}  {days}"
            )
    return 0


def cmd_books(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    with session_scope(engine) as session:
        books = generate_books(session, company=_company(args, session))
        print(f"Database: {_db(args)}")
        print(f"Opex entries +{books.expenses}")
        print(f"Bank charges +{books.charges}")
        print(f"Loan EMIs +{books.emis}")
        print(f"GST settlements +{books.gst}")
        print(f"Opex paid from bank +{books.opex_paid}")
        print(f"Depreciation +{books.depreciation}")
        print(f"Year-end close +{books.closing}")
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    for sid in scenario_ids():
        meta = GOLDEN[sid]
        print(f"{sid:<24} {meta['title']:<24} {meta['known_cause']}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    as_of = args.as_of
    with session_scope(engine) as session:
        cfg = _company(args, session)
        record_scenario(session, cfg)
        metrics = scenario_metrics(session, as_of, cfg)
        ok, detail = signal_holds(metrics, cfg)
        print(f"Database: {_db(args)}")
        print(f"Scenario: {cfg['generator']['scenario']}")
        print(f"Cause:    {cfg['scenario_meta']['known_cause']}")
        print(cfg["scenario_meta"]["golden"])
        print(f"Top customer {metrics.top_customer} share {metrics.top_customer_share}")
        print(f"Top vendor   {metrics.top_vendor} share {metrics.top_vendor_share}")
        print(
            f"AR/sales {metrics.ar_to_sales}  inventory/sales {metrics.inventory_to_sales}  COGS/sales {metrics.cogs_ratio}"
        )
        print("Signal OK" if ok else f"Signal FAIL {detail}")
        return 0 if ok else 1


def cmd_mis(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    pack = args.pack
    with session_scope(engine) as session:
        cfg = _company(args, session)
        snap = mis_snapshot(session, args.as_of, company=cfg)
        peer = None
        if snap.scenario_id != "baseline":
            from ssdv.mis.benchmarks import load_baseline_peer

            peer = load_baseline_peer(snap.as_of, exclude=_db(args))
        analyst = None
        analyst_error = None
        if args.ask:
            try:
                analyst = ask_books(
                    session,
                    "Summarise this company's health in four short sentences. Use only FACTS.",
                    args.as_of,
                    company=cfg,
                    model=args.model,
                    host=args.host,
                )
            except AskError as exc:
                analyst_error = str(exc)
        if args.json:
            payload = snapshot_payload(snap, pack, peer=peer)
            if analyst:
                payload["analyst"] = analyst
            if analyst_error:
                payload["analyst_error"] = analyst_error
            print(json.dumps(payload, indent=2))
        else:
            print(f"Database: {_db(args)}")
            print(render_mis(snap, pack, peer=peer))
            if analyst:
                print()
                print("OfficeMitra (Ollama)")
                print(analyst)
            elif analyst_error:
                print()
                print(analyst_error)
        return 0 if snap.equation.holds else 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with session_scope(engine) as session:
        cfg = _company(args, session)
        snap = mis_snapshot(session, args.as_of, company=cfg)
        peer = None
        if snap.scenario_id != "baseline":
            from ssdv.mis.benchmarks import load_baseline_peer

            peer = load_baseline_peer(snap.as_of, exclude=_db(args))
        payload = snapshot_payload(snap, "all" if args.pdf else "ceo", peer=peer)
        if args.ask:
            try:
                payload["analyst"] = ask_books(
                    session,
                    "Summarise this company's health in four short sentences. Use only FACTS.",
                    args.as_of,
                    company=cfg,
                    model=args.model,
                    host=args.host,
                )
            except AskError as exc:
                payload["analyst_error"] = str(exc)
        if args.pdf:
            out = args.out
            if out.suffix.lower() != ".pdf":
                out = (
                    default_board_pack_path()
                    if out == default_dashboard_path()
                    else out.with_suffix(".pdf")
                )
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(render_board_pdf(payload))
            print(f"Database: {_db(args)}")
            print(f"Wrote:    {out}")
            print("Board pack PDF from posted journals.")
            if getattr(args, "excel", False):
                from ssdv.officemitra.export import write_excel

                excel_out = out.with_suffix(".xlsx")
                write_excel(payload, excel_out)
                print(f"Wrote:    {excel_out}")
            if getattr(args, "ppt", False):
                from ssdv.officemitra.export import write_ppt

                ppt_out = out.with_suffix(".pptx")
                write_ppt(payload, ppt_out)
                print(f"Wrote:    {ppt_out}")
        else:
            out.write_text(render_dashboard(payload), encoding="utf-8")
            print(f"Database: {_db(args)}")
            print(f"Wrote:    {out}")
            print("Open the HTML file in a browser. OfficeMitra lines sit on the CEO screen.")
            if getattr(args, "excel", False):
                from ssdv.officemitra.export import write_excel

                excel_out = out.with_suffix(".xlsx")
                write_excel(payload, excel_out)
                print(f"Wrote:    {excel_out}")
            if getattr(args, "ppt", False):
                from ssdv.officemitra.export import write_ppt

                ppt_out = out.with_suffix(".pptx")
                write_ppt(payload, ppt_out)
                print(f"Wrote:    {ppt_out}")
        return 0 if snap.equation.holds else 1


def cmd_ui(args: argparse.Namespace) -> int:
    import importlib.util
    import os
    import subprocess
    import sys

    if is_frozen():
        os.environ["OFFICEMITRA_DB"] = str(_db(args))
        from ssdv.officemitra.desktop import main as desktop_main

        return int(desktop_main() or 0)

    def _streamlit_python() -> Path | None:
        if importlib.util.find_spec("streamlit") is not None:
            return Path(sys.executable)
        if os.name == "nt":
            candidate = repo_root() / ".venv" / "Scripts" / "python.exe"
        else:
            candidate = repo_root() / ".venv" / "bin" / "python"
        if not candidate.is_file():
            return None
        probe = subprocess.run(
            [str(candidate), "-c", "import streamlit"],
            capture_output=True,
            text=True,
        )
        return candidate if probe.returncode == 0 else None

    python = _streamlit_python()
    if python is None:
        print("Streamlit is not installed in this Python.")
        print("Do not pip-install into global Python (that broke sanmitra_unified-Next preflight).")
        print(r"Use the SSDV venv:")
        print(r'  D:\SSDV\.venv\Scripts\python.exe -m pip install -e ".[ui]"')
        print(r"  D:\SSDV\.venv\Scripts\ssdv.exe ui --as-of 2026-03-31")
        return 2
    app = Path(__file__).resolve().parent / "officemitra" / "app.py"
    cmd = [
        str(python),
        "-m",
        "streamlit",
        "run",
        str(app),
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",
        "--",
        "--db",
        str(_db(args)),
        "--as-of",
        args.as_of.isoformat(),
    ]
    print(f"Database: {_db(args)}")
    print(f"Python:   {python}")
    print("Opening OfficeMitra at http://localhost:8501")
    print("Leave this window open. Press Ctrl+C to stop.")
    return int(subprocess.call(cmd))


def cmd_ask(args: argparse.Namespace) -> int:
    engine = make_engine(_db(args))
    create_schema(engine)
    question = " ".join(args.question).strip()
    model = args.model or default_model()
    with session_scope(engine) as session:
        cfg = _company(args, session)
        print(f"Database: {_db(args)}")
        print(f"Model:    {model}")
        print("Calling local Ollama. First answer can take a few minutes...")
        try:
            answer = ask_books(
                session,
                question,
                args.as_of,
                company=cfg,
                model=model,
                host=args.host,
            )
        except AskError as exc:
            print(exc)
            return 1
        if args.json:
            print(
                json.dumps(
                    {
                        "question": question,
                        "as_of": args.as_of.isoformat(),
                        "model": model,
                        "answer": answer,
                    },
                    indent=2,
                )
            )
        else:
            print(f"Question: {question}")
            print()
            print(answer)
        return 0


def _sidecar_db(args: argparse.Namespace, sidecar: Path) -> Path:
    db: Path = args.db
    if db.resolve() == default_db_path().resolve():
        return sidecar
    return db


def _print_connectors() -> int:
    print(f"{'id':<14} {'status':<12} title")
    for item in list_connectors():
        print(f"{item.id:<14} {item.status:<12} {item.title}")
        print(f"{'':14} {item.hint}")
    print()
    print("SSDV reads exports only. It never writes back to Tally, Zoho, Busy, or MitraBooks.")
    print(
        "Ready paths: journal CSV (--source generic), TallyPrime XML (--source tally), "
        "or live TallyPrime pull (--source tally-http --host http://localhost:9000)."
    )
    return 0


def _cmd_load_external(args: argparse.Namespace, sidecar: Path, verb: str) -> int:
    if getattr(args, "list", False):
        return _print_connectors()
    source = args.source
    if source != "tally-http" and args.journals is None:
        print(f"ssdv {verb} needs --journals PATH (or use --list).")
        return 1
    db_path = _sidecar_db(args, sidecar)
    try:
        result = load_into_vault(
            db_path,
            source=source,
            journals=args.journals,
            account_map=args.map,
            company_name=args.name,
            force=args.force,
            tally_host=getattr(args, "host", None),
        )
    except ConnectorNotReady as exc:
        print(str(exc))
        return 2
    except ConnectorError as exc:
        print(str(exc))
        return 1
    except IngestError as exc:
        print(f"{verb.capitalize()} failed: {exc}")
        return 1
    print(f"Database: {db_path}")
    print(f"Source:   {result.source}")
    print(f"Vouchers  {result.vouchers}  lines {result.lines}")
    print(f"Dates     {result.first_date.isoformat()} to {result.last_date.isoformat()}")
    print("Read-only extract. Books posted through post(). Unbalanced files are rejected.")
    print(f"Next: ssdv --db {db_path} validate --as-of {result.last_date.isoformat()}")
    print(f"      ssdv --db {db_path} mis --as-of {result.last_date.isoformat()} --pack ceo")
    print(f"      ssdv --db {db_path} ui --as-of {result.last_date.isoformat()}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    return _cmd_load_external(args, ingest_db_path(), "ingest")


def cmd_connect(args: argparse.Namespace) -> int:
    return _cmd_load_external(args, connect_db_path(), "connect")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ssdv", description="SanMitra Synthetic Data Vault")
    parser.add_argument(
        "--db",
        type=Path,
        default=default_db_path(),
        help="SQLite path (default: data/ssdv.sqlite)",
    )
    parser.add_argument(
        "--scenario",
        choices=list(scenario_ids()),
        default=None,
        help="AI scenario seed (writes data/ssdv_<scenario>.sqlite unless --db is set)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init",
        help="Create schema, masters, opening, purchases, sales, settlements and period books",
    )
    init.add_argument("--force", action="store_true", help="Drop and recreate all tables")
    init.add_argument(
        "--scenario",
        choices=list(scenario_ids()),
        default=None,
        help="AI scenario seed (default DB becomes data/ssdv_<scenario>.sqlite)",
    )
    init.set_defaults(func=cmd_init)

    tb = sub.add_parser("tb", help="Print trial balance")
    tb.add_argument("--as-of", type=_parse_date, default=date(2023, 4, 1))
    tb.set_defaults(func=cmd_tb)

    eq = sub.add_parser("equation", help="Check assets = liabilities + equity + YTD P&L")
    eq.add_argument("--as-of", type=_parse_date, default=date(2023, 4, 1))
    eq.set_defaults(func=cmd_equation)

    led = sub.add_parser("ledger", help="Net debit balance of one account")
    led.add_argument("account")
    led.add_argument("--as-of", type=_parse_date, default=date(2023, 4, 1))
    led.set_defaults(func=cmd_ledger)

    val = sub.add_parser("validate", help="Run v1 consistency gates")
    val.add_argument("--as-of", type=_parse_date, default=date(2023, 4, 1))
    val.add_argument("--scenario", choices=list(scenario_ids()), default=None)
    val.set_defaults(func=cmd_validate)

    pur = sub.add_parser("purchases", help="Generate purchase bills, GRN and input GST")
    pur.set_defaults(func=cmd_purchases)

    sales = sub.add_parser("sales", help="Generate sales invoices, COGS and output GST")
    sales.set_defaults(func=cmd_sales)

    settle = sub.add_parser("settle", help="Generate receipts and vendor payments")
    settle.set_defaults(func=cmd_settle)

    aging = sub.add_parser("aging", help="Print AR/AP aging buckets")
    aging.add_argument("--as-of", type=_parse_date, default=date(2026, 3, 31))
    aging.set_defaults(func=cmd_aging)

    books = sub.add_parser("books", help="Post expenses, bank charges, EMI, GST and year-end close")
    books.set_defaults(func=cmd_books)

    scn = sub.add_parser("scenarios", help="List OfficeMitra AI scenario seeds")
    scn.set_defaults(func=cmd_scenarios)

    explain = sub.add_parser("explain", help="Print the golden explanation and measured cause")
    explain.add_argument("--as-of", type=_parse_date, default=date(2026, 3, 31))
    explain.add_argument("--scenario", choices=list(scenario_ids()), default=None)
    explain.set_defaults(func=cmd_explain)

    mis = sub.add_parser("mis", help="CEO / CFO / Board KPI packs from posted journals")
    mis.add_argument("--as-of", type=_parse_date, default=date(2026, 3, 31))
    mis.add_argument("--pack", choices=list(PACK_IDS), default="all")
    mis.add_argument("--scenario", choices=list(scenario_ids()), default=None)
    mis.add_argument("--json", action="store_true", help="Print the KPI dictionary as JSON")
    mis.add_argument(
        "--ask",
        action="store_true",
        help="Also call local Ollama for an in-line paragraph (needs Ollama running)",
    )
    mis.add_argument("--model", default=None, help="Ollama model when using --ask")
    mis.add_argument("--host", default=None, help="Ollama host when using --ask")
    mis.set_defaults(func=cmd_mis)

    dash = sub.add_parser(
        "dashboard",
        help="Write a CEO HTML screen, or a Board pack PDF (--pdf)",
    )
    dash.add_argument("--as-of", type=_parse_date, default=date(2026, 3, 31))
    dash.add_argument("--scenario", choices=list(scenario_ids()), default=None)
    dash.add_argument(
        "--out",
        type=Path,
        default=default_dashboard_path(),
        help="HTML path (default: data/mis.html). With --pdf, default is data/board-pack.pdf",
    )
    dash.add_argument(
        "--pdf", action="store_true", help="Write a Board pack PDF instead of CEO HTML"
    )
    dash.add_argument("--excel", action="store_true", help="Also write an executive .xlsx")
    dash.add_argument("--ppt", action="store_true", help="Also write an executive .pptx")
    dash.add_argument("--ask", action="store_true", help="Add an Ollama paragraph if Ollama is up")
    dash.add_argument("--model", default=None)
    dash.add_argument("--host", default=None)
    dash.set_defaults(func=cmd_dashboard)

    ui = sub.add_parser("ui", help="Open the Streamlit OfficeMitra dashboard in a browser")
    ui.add_argument("--as-of", type=_parse_date, default=date(2026, 3, 31))
    ui.add_argument("--scenario", choices=list(scenario_ids()), default=None)
    ui.set_defaults(func=cmd_ui)

    ask = sub.add_parser(
        "ask",
        help="Ask a question; local Ollama answers from MIS JSON only",
    )
    ask.add_argument("question", nargs="+", help="Plain-language question")
    ask.add_argument("--as-of", type=_parse_date, default=date(2026, 3, 31))
    ask.add_argument("--scenario", choices=list(scenario_ids()), default=None)
    ask.add_argument(
        "--model",
        default=None,
        help="Ollama model (default: llama3.1:8b or SSDV_OLLAMA_MODEL)",
    )
    ask.add_argument(
        "--host",
        default=None,
        help="Ollama host (default: http://127.0.0.1:11434)",
    )
    ask.add_argument("--json", action="store_true", help="Print question and answer as JSON")
    ask.set_defaults(func=cmd_ask)

    sources = source_ids()
    ing = sub.add_parser(
        "ingest",
        help="Alias of connect: read-only journal CSV into data/ssdv_ingest.sqlite",
    )
    ing.add_argument("--list", action="store_true", help="Print connectors and exit")
    ing.add_argument(
        "--source",
        choices=sources,
        default="generic",
        help="generic CSV is ready; other names print the export hint",
    )
    ing.add_argument("--journals", type=Path, default=None, help="CSV journal lines")
    ing.add_argument("--map", type=Path, default=None, help="CSV or YAML ledger -> account_code")
    ing.add_argument("--name", default=None, help="Company legal name for MIS packs")
    ing.add_argument("--force", action="store_true", help="Replace an existing ingest vault")
    ing.add_argument(
        "--host", default=None, help="TallyPrime HTTP URL (default: http://localhost:9000)"
    )
    ing.set_defaults(func=cmd_ingest)

    conn = sub.add_parser(
        "connect",
        help="Read-only extract from any app into data/ssdv_connect.sqlite, then MIS/UI",
    )
    conn.add_argument("--list", action="store_true", help="Print connectors and exit")
    conn.add_argument(
        "--source",
        choices=sources,
        default="generic",
        help="generic CSV is the universal adapter until native extracts exist",
    )
    conn.add_argument("--journals", type=Path, default=None, help="CSV journal / day-book export")
    conn.add_argument("--map", type=Path, default=None, help="CSV or YAML ledger -> account_code")
    conn.add_argument("--name", default=None, help="Company legal name for MIS packs")
    conn.add_argument("--force", action="store_true", help="Replace an existing connect vault")
    conn.add_argument(
        "--host", default=None, help="TallyPrime HTTP URL (default: http://localhost:9000)"
    )
    conn.set_defaults(func=cmd_connect)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
