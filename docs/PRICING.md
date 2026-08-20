# OfficeMitra — Subscription & licensing plan

**SanMitra Technologies**

- Website: [https://www.sanmitratech.in](https://www.sanmitratech.in)
- Support: [contact@sanmitratech.in](mailto:contact@sanmitratech.in)

OfficeMitra uses a **one-time desktop license + annual maintenance (AMC)** model. Financial data stays on the customer’s PC — no mandatory cloud subscription.

---

## Plans (agreed)

| Plan | One-time | AMC / year | Companies | Best for |
| --- | ---: | ---: | ---: | --- |
| **Starter** | ₹3,999 | ₹1,299 | 1 | Very small business — CEO view + CSV import |
| **Professional** | ₹6,999 launch* | ₹2,999 | 1 | SME — full CEO/CFO/Board/Charts + forensics |
| **Enterprise** | ₹9,999 | ₹4,999 | 5 | One business group / multi-branch (same owner) |
| **CA Pack 5** | ₹12,999 | ₹4,999 | 5 | CA / consultant — 5 client companies |
| **CA Pack 20** | ₹15,999 | ₹6,999 | 20 | Mid-size CA practice |
| **CA Pack 50** | ₹39,999 | ₹9,999 | 50 | Large CA practice |

\* **Launch price** ₹6,999 for Professional; **regular price** ₹7,999 after early-adopter window.

**Do not show Professional “list” as ₹9,999** — Enterprise is ₹9,999 for **5 companies**. Showing ₹9,999 struck through on Professional implies the customer could pay the same amount and get five entities, which is misleading.

---

## Landing page copy (recommended)

| Plan | Show on website | Avoid |
| --- | --- | --- |
| **Professional** | **₹6,999** launch · Regular **₹7,999** · 1 company | ~~List: ₹9,999~~ strikethrough |
| **Enterprise** | **₹9,999** · **5 companies / branches** · Group consolidation, Tally live sync, GSTR-2B | Competing only on “more features” without mentioning 5 entities |

**One-line upgrade message:**  
*“On Professional you run **one company** with the full CFO toolkit. Step up to Enterprise at ₹9,999 when you need **five entities under one group** with live Tally sync and GSTR-2B.”*

---

## Feature matrix

| Feature | Starter | Professional | Enterprise | CA Packs |
| --- | :---: | :---: | :---: | :---: |
| CEO Pack | Yes | Yes | Yes | Yes |
| CFO Pack | — | Yes | Yes | Yes |
| Board Pack + PDF | — | Yes | Yes | Yes |
| Chart Pack | — | Yes | Yes | Yes |
| Connect — CSV (generic) | Yes | Yes | Yes | Yes |
| Connect — Tally XML upload | — | Yes | Yes | Yes |
| Connect — Tally live (HTTP) | — | — | Yes | Yes |
| What-if scenarios | — | Yes | Yes | Yes |
| Top overdue / vendor tables | — | Yes | Yes | Yes |
| Benchmarks | — | Yes | Yes | Yes |
| DuPont ROE (CFO) | — | Yes | Yes | Yes |
| MSME 43B(h) analyzer | — | Yes | Yes | Yes |
| GSTR-2B ITC reconciliation | — | — | Yes | Yes |
| Excel / PPT export | — | Yes | Yes | Yes |
| Ask Why (Ollama AI) | — | Optional | Optional | Yes |

**Included in all plans (not upsold):** multi-state GST in posting, setup wizard, desktop installer, validation gates, local SQLite vault.

**Ask Why** requires Ollama on the PC; SanMitra can sell setup help as a service, not as a forced SaaS fee.

---

## Positioning

| Plan | Positioning |
| --- | --- |
| **Starter** | “See your business in one screen.” |
| **Professional** | “Your AI CFO for a growing company.” |
| **Enterprise** | “One group, five entities — consolidated MIS.” |
| **CA Packs** | “Client portfolio dashboard for your practice.” |

**Enterprise vs Professional:** Professional is **one company**, full analytics. Enterprise is **five companies/branches (same owner)** plus group consolidation, Tally HTTP, and GSTR-2B — not “the same price for the same thing.”

**Enterprise vs CA Pack 5:** both allow 5 companies, but **Enterprise** is one owner / branch group; **CA Pack** is five **separate client** vaults with CA workflow.

---

## License delivery

After payment, the customer receives:

1. **Download:** `OfficeMitra-Setup.exe` (or licensed ZIP)
2. **License file:** `officemitra.license` (JSON — see [LICENSING.md](LICENSING.md))
3. **Fields:** customer name, GSTIN (optional), plan, company limit, AMC expiry

On first launch, OfficeMitra shows:

```text
License valid — Professional
Updates active until: 31-Mar-2027
Companies: 1 / 1
```

---

## AMC includes

- Bug fixes and security patches
- New KPIs and pack tiles
- New connectors (e.g. Tally HTTP)
- Compatibility updates (Python / Windows)

AMC does **not** include custom ledger mapping, data migration, or training (billable separately).

---

## Add-on services (consulting)

| Service | Indicative price |
| --- | ---: |
| OfficeMitra Health Check (cash, DSO, GST, WC report) | ₹15,000 |
| Tally / CSV mapping & first Connect | ₹5,000–15,000 |
| Half-day training (on-site / remote) | ₹8,000 |

Software is the entry ticket; consulting is margin.

---

## Implementation status

| Item | Status |
| --- | --- |
| Plan definitions (`config/licensing/plans.yaml`) | Done |
| License schema (`src/ssdv/licensing/`) | Done |
| UI enforcement (gate packs/connectors by plan) | Planned |
| Signed license keys | Planned (v2) |

See **[LICENSING.md](LICENSING.md)** for the license file format and plan IDs used in code.
