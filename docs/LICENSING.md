# OfficeMitra licence files

A licence file decides **which packs, connectors and how many client books** an installation may use. Each licence is **signed by SanMitra**. The app checks the signature with a public key built into it, so a licence cannot be created or edited by hand. Checking runs locally; nothing is sent over the internet.

---

## File location

| Path | Purpose |
| --- | --- |
| `%USERPROFILE%\.officemitra\officemitra.license` (Windows) | Per-user licence (recommended) |
| `~/.officemitra/officemitra.license` (Mac) | Per-user licence (recommended) |
| `{install_dir}\officemitra.license` | Fallback next to the app |

Copy the file there and restart OfficeMitra. The sidebar shows the plan, AMC date and client limit, or why a licence file was not accepted.

---

## Without a licence

| How OfficeMitra runs | No valid licence means |
| --- | --- |
| Installed app (Windows/Mac installer) | **Free trial**: 1 client book, Professional features (`trial` plan) |
| Any mode | Demo books (`demo_*.sqlite` loaded with **Load demo books**) never count against the client limit |
| From source (developers, tests) | Developer mode: everything, no limit. Set `OFFICEMITRA_FORCE_TRIAL=1` to see trial behaviour |

---

## JSON schema (v2, signed)

```json
{
  "schema_version": 2,
  "license_id": "OM-2026-1A2B3C4D",
  "customer_name": "ABC Traders Pvt Ltd",
  "gstin": "29AABCU9603R1ZM",
  "plan_id": "professional",
  "company_limit": 1,
  "issued_at": "2026-04-01",
  "amc_expires_at": "2027-03-31",
  "machine_id": "OPTIONAL-PC-NAME",
  "signature": "base64 Ed25519 signature"
}
```

| Field | Required | Description |
| --- | --- | --- |
| `schema_version` | Yes | Always `2`. Old unsigned `1` files are refused: issue a new licence |
| `license_id` | Yes | SanMitra serial (support reference) |
| `customer_name` | Yes | Shown in the app |
| `gstin` | No | 15-character GSTIN |
| `plan_id` | Yes | `starter`, `professional`, `enterprise`, `ca_5`, `ca_20`, `ca_50` (or `trial` for an extended trial) |
| `company_limit` | Yes | Max client books; cannot exceed the plan's limit |
| `issued_at` | Yes | ISO date |
| `amc_expires_at` | Yes | ISO date; updates/support valid until |
| `machine_id` | No | Binds the licence to one Windows computer name |
| `features` | No | Per-customer overrides, e.g. `{"ask_why": true}` |
| `signature` | Yes | Ed25519 signature over every other field (sorted, compact JSON) |

Changing any field breaks the signature and the app falls back to the trial.

---

## Plan IDs and features

Defined in `config/licensing/plans.yaml`. The app enforces them per screen and per feature.

| Flag | What it unlocks |
| --- | --- |
| `ceo_pack` | CEO pack |
| `cfo_pack` | CFO pack screen |
| `board_pack` | Board pack screen, Board PDF |
| `chart_pack` | Chart pack screen |
| `connect_csv` | CSV import |
| `connect_tally_xml` | Tally DayBook XML import |
| `connect_tally_http` | Live TallyPrime connection |
| `whatif` | What-if scenarios and runway sandbox |
| `parties_intel` | Customer / supplier tables |
| `benchmarks` | Industry benchmarks |
| `dupont_roe` | DuPont ROE tile |
| `msme_43bh` | MSME 43B(h) analyser |
| `gstr2b_recon` | GSTR-2B ITC reconciliation in the quality score |
| `export_excel_ppt` | Excel and Board PPT downloads |
| `ask_why` | Ask why |
| `budget_variance` | Account-level budget vs actual |
| `alert_thresholds` | Per-client alert thresholds |
| `partner_approval` | Partner approval (maker-checker) before the Board PPT |

Client chart of accounts and assisted ledger mapping are in every plan.

---

## Issuing licences (SanMitra internal)

The private signing key lives **outside the repository**, at
`%USERPROFILE%\.officemitra-issuer\license_signing_key.pem`. Keep a backup offline (for example an encrypted USB drive). If it is lost, no new licences can be issued until a new key is made and a new app version ships; if it leaks, anyone can issue licences.

```powershell
# once only: creates the key and writes its public half into src/ssdv/licensing/signing.py
.venv\Scripts\python.exe scripts\issue_license.py keygen

# issue a licence
.venv\Scripts\python.exe scripts\issue_license.py issue --plan ca_20 --customer "Patel & Associates" --gstin 24AAAAA0000A1Z5 --amc-months 12 --out patel.officemitra.license

# check a licence
.venv\Scripts\python.exe scripts\issue_license.py verify patel.officemitra.license
```

Options: `--company-limit` (lower than the plan), `--machine` (bind to a PC name), `--issued YYYY-MM-DD`, `--license-id`.

`examples/licensing/professional.license.json` shows the format only; its signature is deliberately invalid.

---

## Related docs

- [PRICING.md](PRICING.md): customer-facing prices and matrix
- [CLIENT_INSTALL.md](CLIENT_INSTALL.md): install steps
