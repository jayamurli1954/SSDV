# OfficeMitra license file format

License files gate **which packs, connectors, and company count** a installation may use. Validation runs locally — no phone-home required for v1.

---

## File location

| Path | Purpose |
| --- | --- |
| `%USERPROFILE%\.officemitra\officemitra.license` | Per-user license (recommended) |
| `{install_dir}\officemitra.license` | Fallback next to the app |

---

## JSON schema (v1)

```json
{
  "schema_version": 1,
  "license_id": "OM-2026-00042",
  "customer_name": "ABC Traders Pvt Ltd",
  "gstin": "29AABCU9603R1ZM",
  "plan_id": "professional",
  "company_limit": 1,
  "issued_at": "2026-04-01",
  "amc_expires_at": "2027-03-31",
  "machine_id": "optional-host-fingerprint",
  "features": {}
}
```

| Field | Required | Description |
| --- | --- | --- |
| `schema_version` | Yes | Always `1` for this format |
| `license_id` | Yes | SanMitra serial (support reference) |
| `customer_name` | Yes | Shown in MIS / Board pack |
| `gstin` | No | 15-char GSTIN if B2B |
| `plan_id` | Yes | One of: `starter`, `professional`, `enterprise`, `ca_5`, `ca_20`, `ca_50` |
| `company_limit` | Yes | Max active company vaults |
| `issued_at` | Yes | ISO date |
| `amc_expires_at` | Yes | ISO date — updates/support valid until |
| `machine_id` | No | Optional bind to one PC (empty = any) |
| `features` | No | Overrides; normally derived from `plan_id` |

---

## Plan IDs (code)

Defined in `config/licensing/plans.yaml` and loaded via `ssdv.licensing`.

| `plan_id` | Display name | Companies |
| --- | --- | ---: |
| `starter` | Starter | 1 |
| `professional` | Professional | 1 |
| `enterprise` | Enterprise | 5 |
| `ca_5` | CA Pack (5) | 5 |
| `ca_20` | CA Pack (20) | 20 |
| `ca_50` | CA Pack (50) | 50 |

---

## Feature flags (derived from plan)

| Flag | Meaning |
| --- | --- |
| `ceo_pack` | CEO dashboard |
| `cfo_pack` | CFO dashboard |
| `board_pack` | Board dashboard + PDF |
| `chart_pack` | Chart pack |
| `connect_csv` | Generic CSV connect |
| `connect_tally_xml` | Tally DayBook XML |
| `connect_tally_http` | TallyPrime live HTTP |
| `whatif` | What-if scenarios |
| `parties_intel` | Top overdue / vendor tables |
| `benchmarks` | ABC baseline benchmarks |
| `dupont_roe` | DuPont ROE tile |
| `msme_43bh` | MSME 43B(h) analyzer |
| `gstr2b_recon` | GSTR-2B ITC reconciliation |
| `export_excel_ppt` | Excel / PPT export |
| `ask_why` | Ollama Ask Why |

Optional add-ons can set `features.ask_why: true` on Starter/Professional via SanMitra-issued override.

---

## Validation rules (v1)

1. `plan_id` must exist in `plans.yaml`.
2. `company_limit` must match the plan (unless support override in `features`).
3. If `amc_expires_at` is in the past → app runs in **read-only** or **grace** mode (product decision; not enforced in code yet).
4. If `machine_id` is set, it must match the current host fingerprint.

---

## Example — Starter

```json
{
  "schema_version": 1,
  "license_id": "OM-2026-00100",
  "customer_name": "Shree Enterprises",
  "plan_id": "starter",
  "company_limit": 1,
  "issued_at": "2026-04-15",
  "amc_expires_at": "2027-03-31"
}
```

## Example — CA Pack 20

```json
{
  "schema_version": 1,
  "license_id": "OM-2026-00201",
  "customer_name": "Patel & Associates",
  "gstin": "24AAAAA0000A1Z5",
  "plan_id": "ca_20",
  "company_limit": 20,
  "issued_at": "2026-05-01",
  "amc_expires_at": "2027-03-31"
}
```

---

## Generating licenses (SanMitra internal)

Until signing is implemented, issue JSON files manually or via an internal script. Fields must match `plans.yaml`.

Future v2: HMAC-signed payload embedded in `license_key` string for tamper resistance.

---

## Related docs

- [PRICING.md](PRICING.md) — customer-facing prices and matrix
- [CLIENT_INSTALL.md](CLIENT_INSTALL.md) — install steps
