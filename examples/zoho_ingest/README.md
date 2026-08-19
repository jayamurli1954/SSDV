# Zoho CSV Template (for `--source generic`)

SSDV does not yet read Zoho journals via native API/XML. The recommended workflow today is:

1. Export Zoho day book / journal register as CSV
2. Conform headers to SSDV’s expected columns
3. Provide `--map ledger_map.csv` (Zoho ledger name → SSDV `account_code`)
4. Ingest using `--source generic`

## Expected CSV columns

SSDV’s generic ingester expects these columns (extra columns are ignored):

- `voucher_id` (or `voucher_no`)
- `date` (`YYYY-MM-DD` or `DD/MM/YYYY`)
- `voucher_type` (e.g. `SALE`, `PURCHASE`, `RECEIPT`, `PAYMENT`, `EXPENSE`)
- `account` (Zoho ledger name)
- `debit`, `credit` (one must be zero per line)
- `party_type`, `party` (optional, but needed for customer/vendor intelligence)
- `narration` (optional)

## Example usage

```bash
ssdv ingest --source generic \
  --journals examples/zoho_ingest/journals.csv \
  --map examples/zoho_ingest/ledger_map.csv \
  --name "Zoho Imported Co"
```

