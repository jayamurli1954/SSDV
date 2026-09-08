# Enterprise Roadmap (Phases 5 & 6)

Goal: scale SSDV / OfficeMitra for production-grade installs, CA firms, and multi-entity enterprises.

## Current Status (so far)

- Phase 1–4: integrated
- **Multi-State GST**: implemented and unit-tested
- **TallyPrime HTTP live pull**: implemented (`--source tally-http`) — not a Phase 6 future item
- **CA Pack firm roster**: implemented (`ssdv firm` + Streamlit **All client books**) — per-vault revenue / AR 90+ / cash, gated by license `company_limit`. This is **not** group consolidation.

Still planned (not in this drop): 43B(h) depth, GSTR-2B, Schedule III, DuPont, Postgres/ClickHouse, inter-company consolidation, scheduled dispatch, live Zoho/Xero APIs.

## Mermaid Diagram

```mermaid
flowchart LR
    P4["Phase 4 (done)\nMulti-State GST + core hardening"] --> P5["Phase 5: Forensic Accounting & Statutory Compliance"]
    P5 --> P6["Phase 6: Enterprise Live-Sync & Production Hardening"]
    
    P5A["43B(h) MSME Overdue Analyzer"] --> P6
    P5B["GSTR-2B vs Inward ITC Reconciliation"] --> P6
    P5C["Schedule III Financial Statement Generator"] --> P6
    P5D["DuPont Diagnostic Engine"] --> P6
    
    P6A["Direct TallyPrime HTTP Listener"] --> P6
    P6B["Database Engine Switch\n(PostgreSQL / ClickHouse)"] --> P6
    P6C["Multi-Entity Group Consolidation"] --> P6
    P6D["Automated Scheduled Dispatch"] --> P6
```

## Detailed Breakdown of Proposed Phases

### Phase 5: Forensic Accounting & Statutory Compliance

1. **Section 43B(h) MSME Overdue Analyzer**
   - Requirement: flag payment disallowance risk for MSMEs not paid within statutory time windows:
     - 45 days when agreement exists
     - 15 days when no agreement exists
   - Proposed vNext:
     - party-level MSME classification tags (Micro, Small, Medium)
     - automated 43B(h) disallowance risk report in CFO pack

2. **GSTR-2B vs Inward ITC Reconciliation**
   - Requirement: ingest monthly GSTR-2B and reconcile it against inward purchase vouchers.
   - Proposed matching:
     - Invoice No + Date
     - tolerance matching on GST amount
   - Proposed flags:
     - uncredited ITC
     - missing vendor invoices
     - ineligible credits

3. **Schedule III Financial Statement Generator**
   - Requirement: standardized Balance Sheet + P&L grouping into Ind AS Schedule III format.
   - Proposed output:
     - Division I / Division II grouping
     - automated note numbering

4. **DuPont Diagnostic Engine**
   - Requirement: deconstruct ROE into operational vs financing drivers:
     - Profit Margin
     - Asset Turnover
     - Financial Leverage
   - Output:
     - executive “driver tree” explanation per period

### Phase 6: Enterprise Live-Sync & Production Hardening

1. **Direct TallyPrime HTTP Listener — done**
   - `ssdv connect --source tally-http --host http://localhost:9000`
   - Remaining Phase 6 items below are still planned.

2. **Database Engine Switch (PostgreSQL / ClickHouse)**
   - SQLAlchemy URL configuration support:
     - `postgresql+psycopg2://...`
   - Motivation:
     - multi-user concurrency
     - high transaction volume reporting

3. **Multi-Entity Group Consolidation**
   - Support multiple company vaults:
     - holding company + subsidiaries
   - Proposed approach:
     - inter-company elimination vouchers
     - consolidated Group MIS packs

4. **Automated Scheduled Dispatch**
   - Background worker (cron/task scheduler) to compile:
     - Board Pack PDFs
     - Excel workbooks
   - Dispatch:
     - SMTP email
     - secure webhook delivery

## Suggested Sequencing (Practical Monetization Order)

1. ~~CA Pack firm roster (cross-client revenue / AR 90+ / cash)~~ **shipped**
2. Phase 5.1 (43B(h) MSME risk) + Phase 5.2 (GSTR-2B reconciliation)
3. Schedule III + DuPont diagnostic
4. Consolidation + scheduled dispatch
5. Database engine switch once concurrency becomes a real constraint

