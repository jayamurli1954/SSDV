# SSDV user manual

SanMitra Synthetic Data Vault (SSDV) is a **journal-first** tool. It either **generates** internally consistent Indian trading-company books, or **reads** journals exported from another application, then shows **CEO / CFO / Board KPIs**, charts, and AI notes.

GitHub (private): [https://github.com/jayamurli1954/SSDV](https://github.com/jayamurli1954/SSDV)

## 1. What SSDV is and is not

**SSDV is**

- A double-entry vault. Every voucher is posted through `post()`. Debit must equal credit or the voucher is rejected.
- A **read-only connector**. It copies journals *into* SSDV. It never writes back to Tally, Zoho, Busy, or MitraBooks.
- An OfficeMitra MIS screen (Streamlit) plus a PowerShell CLI.

**SSDV is not**

- MitraBooks ERP, Tally, or a live login to any accounting product.
- A replacement for statutory books of record.
- Something you install into **global** Python (that broke `sanmitra_unified-Next` preflight once, because of a pytest version clash).

Two kinds of data:

| Fuel | What it is | Typical vault | Typical as-of date |
| --- | --- | --- | --- |
| Generated books | ABC Industrial Supplies Pvt Ltd, FY 2023-24 to 2025-26 | `data\ssdv.sqlite` | **2026-03-31** |
| Connected books | Your CSV day book / journal register | `data\ssdv_connect.sqlite` | Last date in that CSV (sample: **2024-04-30**) |

## 2. Install (once, PowerShell)

Use **only** the project virtual environment.

```powershell
cd D:\SSDV
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install -e ".[ui]"
```

Do **not** run `pip install -e ".[ui]"` against `C:\Users\...\Python311\python.exe`.

### 2.1 Always call the venv `ssdv`

On this PC, typing `ssdv` often runs **global** Python, which has **no Streamlit**.

Use this instead, every time:

```powershell
cd D:\SSDV
.\.venv\Scripts\ssdv.exe --help
```

Optional: activate the venv so `ssdv` in that window is the venv one:

```powershell
cd D:\SSDV
.\.venv\Scripts\Activate.ps1
ssdv --help
```

If Activate is blocked, keep using `.\.venv\Scripts\ssdv.exe`.

### 2.2 Do not paste command *output* back into PowerShell

After `ssdv connect`, the tool prints lines like `Vouchers 7`, `Next: ssdv ...`. Those are messages, not commands. Only type lines you intend to run.

## 3. Fast start — ABC Industrial on screen

Generate (only if you do not already have `data\ssdv.sqlite`; **do not add `--force` unless you want to wipe the vault**):

```powershell
cd D:\SSDV
.\.venv\Scripts\ssdv.exe init
.\.venv\Scripts\ssdv.exe validate --as-of 2026-03-31
```

Open the browser dashboard:

```powershell
.\.venv\Scripts\ssdv.exe --db data/ssdv.sqlite ui --as-of 2026-03-31
```

Leave that window open. Open [http://localhost:8501](http://localhost:8501) if the browser does not appear.

In the sidebar:

1. **Vault** → `D:\SSDV\data\ssdv.sqlite` (not `ssdv_connect.sqlite`).
2. Click **Use ABC year-end 31 Mar 2026**.
3. **Screen** → **CEO** (then CFO, Board, Charts as needed).

Stop the UI with **Ctrl+C** in that PowerShell window.

## 4. Fast start — sample connected books

This does **not** touch ABC Industrial.

```powershell
cd D:\SSDV
.\.venv\Scripts\ssdv.exe connect --source generic --journals examples/generic_ingest/journals.csv --map examples/generic_ingest/ledger_map.csv --name "Sample Traders Pvt Ltd" --force
.\.venv\Scripts\ssdv.exe --db data/ssdv_connect.sqlite ui --as-of 2024-04-30
```

Sidebar: vault `ssdv_connect.sqlite`, as of **2024-04-30**, screen **CEO**.

## 5. Streamlit screens

| Screen | What you see |
| --- | --- |
| **CEO** | OfficeMitra notes, 14 KPI tiles, benchmarks vs SSDV policy, **what-if scenarios (recommend-only)**, sales vs COGS, gross margin, collections, P&L mix, monthly profit, why-notes, why chips, optional typed question |
| **CFO** | Cash forecast 30/60/90 from open AR/AP (no sales plan), GST input/output/net, bank position, aging 0-30 through 120+, DSO / DIO / DPO / CCC |
| **Board** | Red flags first, then assets / liabilities / equity, working-capital parts, policy scorecard, **benchmarks vs SSDV policy and ABC trading baseline** (not an industry survey), cash-cycle days |
| **Charts** | Activity, sales vs COGS, cash movement, margin, P&L mix, monthly profit, aging |
| **Connect** | Upload a journal CSV + optional ledger map (read-only extract) |

**Download Board pack (PDF)** writes an A4 pack (red flags, Board tiles, scorecard, benchmarks, 30/60/90 cash, what-if). Journals are not changed. PPT is not in this pack. **Download full report (HTML)** is the CEO screen; open it in Edge and **Ctrl+P** if you want a print of that page.

All numbers come from **posted journals**. Unbalanced books never get a chart.

## 6. Connect another application (read-only)

SSDV does **not** log into Tally / Zoho / Busy / MitraBooks. You **export** a journal / day book to CSV, map ledger names to SSDV account codes, then SSDV posts into a **sidecar** vault.

```
Any app  --export CSV-->  journals.csv + ledger_map.csv
                         --ssdv connect-->  data\ssdv_connect.sqlite
                         --ssdv ui / mis-->  KPIs, charts, AI notes
```

### 6.1 Which sources are ready

```powershell
.\.venv\Scripts\ssdv.exe connect --list
```

| id | Status today | What you do |
| --- | --- | --- |
| `generic` | **ready** | Use this. CSV journals + map. |
| `tally` | export CSV | Export vouchers from Tally, then `--source generic`. |
| `zoho` | export CSV | Export journals from Zoho Books, then `--source generic`. |
| `busy` | export CSV | Export vouchers from Busy, then `--source generic`. |
| `mitrabooks` | export CSV | Export journals, or open an existing SSDV `.sqlite` in the Vault list. |

### 6.2 Upload in the browser

1. Start the UI (any vault is fine).
2. Sidebar **Screen** → **Connect**.
3. **Journal CSV** — required. Shape: section 7.
4. **Ledger map** — recommended (CSV or YAML). Shape: section 7.
5. **Company name** — appears on packs (for example `Acme Trading Pvt Ltd`).
6. Tick **Replace books already in the connect vault** if `ssdv_connect.sqlite` already has data.
7. **Extract and post into SSDV**.
8. Sidebar **Screen** → **CEO**. Set **As of** to the last date in your file.

SSDV writes only to `data\ssdv_connect.sqlite`. It does not change `ssdv.sqlite`.

### 6.3 Connect from PowerShell

```powershell
cd D:\SSDV
.\.venv\Scripts\ssdv.exe connect --source generic --journals C:\Exports\journals.csv --map C:\Exports\ledger_map.csv --name "Your Company Pvt Ltd" --force
.\.venv\Scripts\ssdv.exe --db data/ssdv_connect.sqlite validate --as-of 2025-03-31
.\.venv\Scripts\ssdv.exe --db data/ssdv_connect.sqlite mis --as-of 2025-03-31 --pack ceo
.\.venv\Scripts\ssdv.exe --db data/ssdv_connect.sqlite ui --as-of 2025-03-31
```

Change `--as-of` to the last voucher date in *your* CSV.

`--force` wipes the connect vault and reloads. Without `--force`, a vault that already has vouchers is refused.

`ssdv ingest` is the same pipeline but writes `data\ssdv_ingest.sqlite` (older name). Prefer `ssdv connect`.

### 6.4 Tally / Zoho / Busy / MitraBooks in practice

Until native adapters exist, export a **journal register / day book** with one **row per debit or credit line** (not one row per voucher).

Typical Tally path: Display → Account Books → Journal / Day Book → export CSV. Rename columns to the names in section 7, or keep aliases SSDV already accepts (`ledger`, `dr`, `cr`, `vch_date`, …).

Then:

```powershell
.\.venv\Scripts\ssdv.exe connect --source generic --journals .\tally_daybook.csv --map .\ledger_map.csv --name "Your Tally Company" --force
```

`--source tally` (or zoho / busy / mitrabooks) only prints the export hint and exits. That is expected.

Imported books have **no planted SSDV cause**. OfficeMitra may only explain numbers that are in the posted ledger.

## 7. File formats

Sample files: `examples\generic_ingest\journals.csv` and `examples\generic_ingest\ledger_map.csv`.

### 7.1 Journal CSV (required)

One row = one debit **or** one credit line. Lines that share the same `voucher_id` must **balance**.

**Preferred columns**

`voucher_id, date, voucher_type, account, debit, credit, party_type, party, narration`

| Column | Required | Notes |
| --- | --- | --- |
| `voucher_id` | yes | Same id on every line of one voucher. Aliases: `voucher`, `id`, `vch_id`. |
| `date` | yes | `YYYY-MM-DD`. Aliases: `voucher_date`, `vch_date`. |
| `voucher_type` | yes | See table below. Aliases: `type`, `vch_type`. |
| `account` | yes | Ledger name **or** SSDV account code. Aliases: `ledger`, `ledger_name`, `account_code`. |
| `debit` | yes | Amount or 0. Aliases: `dr`, `debit_amount`. Commas allowed. |
| `credit` | yes | Amount or 0. Aliases: `cr`, `credit_amount`. |
| `party_type` | no | `customer` or `vendor` on AR/AP lines. |
| `party` | no | Party code/name. Aliases: `party_code`, `party_name`. |
| `narration` | no | Aliases: `voucher_narration`. |

**Voucher types** (aliases in brackets)

`OPENING`, `PURCHASE` (purchases), `SALE` (sales), `RECEIPT` (receipts), `PAYMENT` (payments), `EXPENSE` (expenses), `JOURNAL`, `CONTRA`, `CREDIT_NOTE`, `DEBIT_NOTE`, `DEPRECIATION`, `CLOSING`, `GST_PAYMENT` (gst).

**Example (two-line opening)**

```text
voucher_id,date,voucher_type,account,debit,credit,party_type,party,narration
OPEN-1,2024-04-01,OPENING,HDFC Bank,500000.00,0,,,Opening
OPEN-1,2024-04-01,OPENING,Capital Account,0,500000.00,,,Opening
```

Rejected if:

- a voucher does not balance
- a ledger name is not in the map and is not a known account code
- the file path does not exist

### 7.2 Ledger map (strongly recommended)

CSV columns: `source,account_code`

`source` is the name as it appears in the journal CSV. `account_code` is an SSDV code from the chart of accounts.

```text
source,account_code
HDFC Bank,111000
Sundry Debtors,120000
Sales Account,410000
Rent,620000
Capital Account,310000
```

YAML is also accepted (`ledger: code`). If you omit the map, every `account` value must already be a postable SSDV code (for example `111000`).

### 7.3 Chart of accounts (map targets)

Headers (`100000` Assets, `200000` Liabilities, …) are **not** postable.

| Code | Name |
| --- | --- |
| 110000 | Cash |
| 111000 | HDFC Bank Current |
| 112000 | ICICI Bank Current |
| 113000 | HDFC Bank OD |
| 120000 | Sundry Debtors |
| 130000 | Inventory |
| 141000 / 141100 / 141200 | Input CGST / SGST / IGST |
| 151000 | TDS Receivable |
| 152000 | Prepaid Expenses |
| 161000 / 161100 | Furniture / Accum. dep. furniture |
| 162000 / 162100 | Computers / Accum. dep. computers |
| 210000 | Sundry Creditors |
| 221000 / 221100 / 221200 | Output CGST / SGST / IGST |
| 222000 | GST Payable |
| 231000 | TDS Payable |
| 232000 | Salary Payable |
| 233000 | Expenses Payable |
| 241000 | Term Loan |
| 310000 | Share Capital |
| 320000 | Reserves & Surplus |
| 330000 | Profit & Loss Account |
| 410000 | Sales |
| 410100 | Sales Returns |
| 420000 / 421000 / 422000 | Other income / Interest / Discount received |
| 510000 | Cost of Goods Sold |
| 520000 / 521000 | Freight inward / Purchase returns |
| 610000 | Salaries |
| 620000 | Rent |
| 621000–631000 | Other operating expenses (electricity, insurance, bad debts, …) |
| 640000 / 641000 / 642000 | Bank charges / Interest term loan / Interest OD |
| 650000 | Depreciation |
| 660000 | GST late fee |

Full list: `src/ssdv/data/coa.yaml`.

## 8. PowerShell CLI reference

Global flag (before the subcommand):

```powershell
.\.venv\Scripts\ssdv.exe --db PATH\file.sqlite <command> ...
```

If you omit `--db`, generator commands use `data\ssdv.sqlite`. `connect` with no `--db` uses `data\ssdv_connect.sqlite`. `ingest` with no `--db` uses `data\ssdv_ingest.sqlite`.

`--scenario NAME` on generator commands writes `data\ssdv_NAME.sqlite` and does not overwrite the baseline vault.

### 8.1 Generate ABC books

```powershell
.\.venv\Scripts\ssdv.exe init
.\.venv\Scripts\ssdv.exe purchases
.\.venv\Scripts\ssdv.exe sales
.\.venv\Scripts\ssdv.exe settle
.\.venv\Scripts\ssdv.exe books
```

`init` already runs purchases, sales, settlements, and period books. The extra commands are additive if you run them later.

**Danger:** `init --force` **drops all tables** in that database. Do not use `--force` on the baseline vault unless you intend to rebuild ABC from scratch.

### 8.2 Check the books

```powershell
.\.venv\Scripts\ssdv.exe validate --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe tb --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe equation --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe aging --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe ledger 130000 --as-of 2026-03-31
```

### 8.3 KPIs and dashboard without the browser

```powershell
.\.venv\Scripts\ssdv.exe mis --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe mis --pack ceo --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe mis --pack cfo --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe mis --pack board --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe mis --pack ceo --json --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe dashboard --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe dashboard --pdf --as-of 2026-03-31
```

`dashboard` writes `data\mis.html`. Open that file in a browser.

`dashboard --pdf` writes `data\board-pack.pdf` (Board pack from posted journals).

`--json` is the contract for any other UI: tiles, monthly series, aging, insights.

### 8.4 Scenarios (known-cause seeds for OfficeMitra)

These are **separate** databases. They do not change `ssdv.sqlite`.

```powershell
.\.venv\Scripts\ssdv.exe scenarios
.\.venv\Scripts\ssdv.exe init --scenario customer_concentration
.\.venv\Scripts\ssdv.exe explain --scenario customer_concentration --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe --db data/ssdv_customer_concentration.sqlite ui --as-of 2026-03-31
```

| Scenario | Known cause |
| --- | --- |
| `baseline` | Healthy growth |
| `customer_concentration` | Top customer about 40% of revenue |
| `cash_flow_crisis` | Sales up, DSO up, cash down |
| `inventory_buildup` | Inventory up, sales flat |
| `vendor_dependency` | One vendor dominates purchases |
| `margin_erosion` | Purchase cost up, selling price lags |

On **imported** books, ignore planted causes. Explain only the measured KPIs.

### 8.5 Ask (local Ollama)

Start the **Ollama** app first so it listens on `http://127.0.0.1:11434`. Default model: `llama3.1:8b`.

```powershell
.\.venv\Scripts\ssdv.exe ask "why is AR over 90 days up" --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe mis --pack ceo --ask --as-of 2026-03-31
.\.venv\Scripts\ssdv.exe dashboard --as-of 2026-03-31 --ask
```

The model may use only the MIS JSON (posted facts). It must not invent a cause that is not in the books.

In Streamlit, CEO why chips (`Why did profit fall?`, `Why is cash negative?`, `Why is inventory rising?`, `Why is AR over 90 days up?`, `Which customers drive concentration?`) call the same harness. A typed question still works. The chips and notes use posted journals only; they do not invent a customer or a cause.

### 8.6 Tests

```powershell
cd D:\SSDV
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 9. Glossary (what you see on the screen)

| Term | Meaning |
| --- | --- |
| **COGS** | Cost of goods sold — cost of stock that was sold. |
| **Opex / operating expenses** | Running costs: salaries, rent, electricity, bank charges, depreciation. Not COGS. |
| **YTD profit (sales − COGS − operating expenses)** | Trading profit for the year to the as-of date from those flows. Not “cash in the bank”. |
| **DSO** | Days sales outstanding. How long customers take to pay. **AR ÷ FY sales × days**. Policy: within 120 days. |
| **DIO** | Days inventory outstanding. How long stock sits. **Inventory ÷ FY COGS × days**. |
| **DPO** | Days payable outstanding. How long you take to pay vendors. **AP ÷ FY purchases × days**. |
| **Cash conversion cycle** | **DSO + DIO − DPO**. Days **your** cash is tied up. Shorter is better. |
| **Current ratio** | Current assets ÷ current liabilities (term loan excluded). |
| **Quick ratio** | (Cash + AR) ÷ current liabilities. |
| **Last-month net cash** | Last month receipts − last month payments. Negative is a cash drain, not an opex guess. |
| **Cash forecast (30 / 60 / 90)** | Starting cash plus AR 0-30 / 31-60 / 61-90 minus AP in the same buckets. GST net liability and salary payable leave at 30 days. AR 90+ and AR with no invoice aging are not timed. No future sales. |
| **GST net liability** | Output GST − input GST from the trial balance (falls back to GST payable if those ledgers are empty). |
| **Benchmarks** | Hold / Breach vs SSDV policy bands. Optional peer is **ABC Industrial generated baseline**, not a surveyed industry average. |
| **What-if** | Recommend-only levers from posted books (DSO to 120, sales +15% at same margin, collect AR 90+, collections to 80%). Journals are not changed. |
| **Collection efficiency** | Receipts ÷ sales for the period. |
| **Operating working capital** | AR + inventory − AP. |
| **As of** | The date of the snapshot. For ABC full books use **31 Mar 2026**. A date *after* year-end (for example 30 Apr 2026) shows an empty new year (sales 0, “revenue decreased 100%”). |

## 10. Files on disk

| Path | Role |
| --- | --- |
| `data\ssdv.sqlite` | ABC Industrial generated vault |
| `data\ssdv_connect.sqlite` | Connected / uploaded journals |
| `data\ssdv_ingest.sqlite` | Older ingest sidecar |
| `data\ssdv_<scenario>.sqlite` | Scenario vaults |
| `data\mis.html` | Static CEO HTML from `ssdv dashboard` |
| `data\board-pack.pdf` | Board pack PDF from `ssdv dashboard --pdf` |
| `examples\generic_ingest\` | Sample CSV + map |
| `.venv\` | Python environment (not in Git) |

SQLite files are **gitignored**. They stay on your PC; they are not on GitHub.

## 11. Troubleshooting

| What you see | What to do |
| --- | --- |
| `Streamlit is not installed` | You used global `ssdv`. Run `.\.venv\Scripts\ssdv.exe ui ...` |
| Browser does not open | Leave the CLI window running; open http://localhost:8501 |
| `cannot import name 'kpi_points'` | Old Streamlit process. Ctrl+C, start UI again with the venv exe |
| `as_of cannot be modified after the widget` | Fixed in current code; refresh or restart UI, then use the year-end button |
| Notes say revenue decreased 100% / profit 0 | As-of is after ABC year-end. Use **31 Mar 2026** |
| Connect / sample numbers on CEO | Vault is `ssdv_connect.sqlite`. Switch to `ssdv.sqlite` for ABC |
| `Unmapped ledger` | Add that name to the ledger map |
| `Unbalanced` | Debits ≠ credits for that `voucher_id` |
| Connect vault already has vouchers | Add `--force` or tick **Replace books** |
| `generic` / `Vouchers` / `Next:` errors in PowerShell | You pasted program output. Ignore it; type only real commands |
| Unified-Next preflight pytest mismatch | Do not pip-install SSDV or Streamlit into global Python |
| Edge screenshot is only the window | Download HTML report → open file → Ctrl+P → Save as PDF |

## 12. Safety

- SSDV **never** posts into Tally, Zoho, Busy, or MitraBooks.
- Do not run `ssdv init --force` on the baseline vault unless you intend to rebuild it.
- Keep SSDV’s `.venv` and `D:\sanmitra_unified-Next\.venv` separate.
- OfficeMitra answers only from posted facts. On imported books it must not claim an SSDV “planted” scenario.

## 13. Command cheat sheet

```powershell
cd D:\SSDV

# ABC Industrial
.\.venv\Scripts\ssdv.exe init
.\.venv\Scripts\ssdv.exe --db data/ssdv.sqlite ui --as-of 2026-03-31

# Sample CSV company
.\.venv\Scripts\ssdv.exe connect --source generic --journals examples/generic_ingest/journals.csv --map examples/generic_ingest/ledger_map.csv --name "Sample Traders Pvt Ltd" --force
.\.venv\Scripts\ssdv.exe --db data/ssdv_connect.sqlite ui --as-of 2024-04-30

# Your export
.\.venv\Scripts\ssdv.exe connect --source generic --journals C:\Exports\journals.csv --map C:\Exports\ledger_map.csv --name "Your Company" --force
.\.venv\Scripts\ssdv.exe --db data/ssdv_connect.sqlite mis --pack ceo --as-of YYYY-MM-DD
```

Blueprint (locked company rules): [BLUEPRINT.md](BLUEPRINT.md).
