# SanMitra Synthetic Data Vault (SSDV)

Journal-first generator of internally consistent Indian trading-company books, and a **read-only connector** from any application's journals into OfficeMitra KPIs and AI notes.

v1 still ships a generated company — **ABC Industrial Supplies Pvt Ltd** — electrical & industrial trading — three complete Indian financial years. Every document is posted through a double-entry engine. Trial Balance, P&L, and Balance Sheet must reconcile before any invoice Faker loop is added. External apps (Tally, Zoho, Busy, MitraBooks, or anything that can export a journal CSV) are extracted the same way: canonical journals → `post()` → sidecar vault → Streamlit MIS. SSDV never writes back to the source application.

**Full user manual (PowerShell, Streamlit, connect/upload, CLI):** [docs/USER_MANUAL.md](docs/USER_MANUAL.md)

**Client install (non-technical, Windows):** [docs/CLIENT_INSTALL.md](docs/CLIENT_INSTALL.md) · run **`install.ps1`** · then **`Start-OfficeMitra.bat`**

**Client user manual (workflows, FAQs, support):** [docs/CLIENT_MANUAL.md](docs/CLIENT_MANUAL.md)

## Locked decisions

See [docs/BLUEPRINT.md](docs/BLUEPRINT.md) and [config/companies/abc_industrial.yaml](config/companies/abc_industrial.yaml).

- Valuation: weighted average
- GST: regular dealer, Maharashtra, CGST+SGST intra-state / IGST inter-state
- Books: FY 2023-24, FY 2024-25, FY 2025-26
- Database for v1: SQLite

## Setup

### Client PC (recommended — non-technical)

1. Unzip the SSDV folder.
2. Install [Python 3.11+](https://www.python.org/downloads/) (tick **Add to PATH**).
3. Right-click **`install.ps1`** → **Run with PowerShell**.
4. Double-click **`Start-OfficeMitra.bat`** → browser opens http://localhost:8501.

See **[docs/CLIENT_INSTALL.md](docs/CLIENT_INSTALL.md)** and **[docs/CLIENT_MANUAL.md](docs/CLIENT_MANUAL.md)**.  
Support: **contact@sanmitratech.in** · **https://www.sanmitratech.in**

### Developer setup

```powershell
cd D:\SSDV
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install -e ".[ui]"
```

## Commands

```powershell
ssdv init --force
ssdv purchases
ssdv sales
ssdv settle
ssdv books
ssdv aging --as-of 2026-03-31
ssdv tb --as-of 2026-03-31
ssdv equation --as-of 2026-03-31
ssdv validate --as-of 2026-03-31
ssdv ledger 130000 --as-of 2026-03-31
ssdv init --scenario customer_concentration
ssdv explain --scenario customer_concentration --as-of 2026-03-31
ssdv scenarios
ssdv explain --as-of 2026-03-31
ssdv mis --as-of 2026-03-31
ssdv mis --pack ceo --scenario cash_flow_crisis --as-of 2026-03-31
ssdv mis --pack board --json --as-of 2026-03-31
ssdv mis --pack ceo --as-of 2026-03-31
ssdv dashboard --as-of 2026-03-31
ssdv dashboard --pdf --as-of 2026-03-31
ssdv dashboard --as-of 2026-03-31 --ask
ssdv ui --as-of 2026-03-31
ssdv ask "why is AR over 90 days up" --as-of 2026-03-31
ssdv ask "why did sales fall in the last 6 months" --as-of 2026-03-31 --model llama3.1:8b
ssdv connect --list
ssdv connect --source generic --journals examples/generic_ingest/journals.csv --map examples/generic_ingest/ledger_map.csv --name "Sample Traders Pvt Ltd" --force
ssdv --db data/ssdv_connect.sqlite validate --as-of 2024-04-30
ssdv --db data/ssdv_connect.sqlite mis --as-of 2024-04-30 --pack ceo
ssdv --db data/ssdv_connect.sqlite ui --as-of 2024-04-30
ssdv ingest --source generic --journals examples/generic_ingest/journals.csv --map examples/generic_ingest/ledger_map.csv --name "Sample Traders Pvt Ltd" --force
ssdv --db data/ssdv_ingest.sqlite validate --as-of 2024-04-30
ssdv --db data/ssdv_ingest.sqlite mis --as-of 2024-04-30 --pack ceo
pytest
```

`ssdv init` creates `data/ssdv.sqlite`, loads the chart of accounts, generates masters, posts opening balances, then generates purchase bills, sales invoices, receipts, vendor payments, monthly expenses, bank charges, EMIs, GST settlements and year-end close. `ssdv init --scenario <name>` writes a separate database (`data/ssdv_<name>.sqlite`) with the known-cause knobs for OfficeMitra AI and does not touch the baseline vault. `ssdv explain` prints the golden explanation and the measured concentration, DSO, inventory and margin signals. `ssdv mis` prints CEO / CFO / Board KPI packs from posted journals (`--json` is the UI contract: 14 CEO tiles, 30/60/90 cash forecast, benchmarks vs SSDV policy / ABC baseline, recommend-only what-if scenarios, top overdue customers / vendor exposure, monthly series, aging charts including 120+, OfficeMitra insight / why lines, and Board red flags). `ssdv dashboard` writes `data/mis.html`. `ssdv dashboard --pdf` writes `data/board-pack.pdf` (Board pack from posted journals). Optional exports: `ssdv dashboard --pdf --ppt` (PPTX) and/or `ssdv dashboard --pdf --excel` (XLSX). `ssdv ui` opens the **Streamlit** OfficeMitra dashboard. The **Connect** tab is a read-only extract from any application (journal CSV + ledger map) into `data/ssdv_connect.sqlite`; CEO / CFO / Board / Charts then show KPIs and AI notes. SSDV never writes back to Tally, Zoho, Busy, or MitraBooks. Install with `pip install -e ".[ui]"` first. `ssdv mis --ask` / `ssdv dashboard --ask` also call local Ollama for a short paragraph if the app is running. `ssdv ask "why is 90+ AR up"` is the free-text harness on the same facts. Start Ollama first; default model `llama3.1:8b`. Imported books have no planted SSDV cause. `ssdv connect --source generic` (or the older `ssdv ingest` alias) loads a CSV journal export into a sidecar vault and does not touch the generator vault. Unbalanced files are rejected. Native Tally / Zoho / Busy adapters print an export hint until they are wired; until then use the sample CSV shape in `examples/generic_ingest/`.
