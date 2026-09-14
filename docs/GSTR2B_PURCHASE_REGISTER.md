# GSTR-2B reconciliation on real / imported books

## Direct answer for a CA / GST expert

**Today’s Tally / generic connectors post day-book journals only.** They create GL vouchers — not `PurchaseBill` rows. GSTR-2B matching needs invoice-level purchase detail (supplier GSTIN + invoice number + taxable / CGST / SGST / IGST).

So for a live client:

1. Connect day-book as usual (`ssdv connect` / OfficeMitra Connect) — books & MIS stay as they are.
2. **Also** import a purchase register CSV (`ssdv purchase-bills`) — detail only, **no second GL posting**.
3. Load the portal GSTR-2B CSV (`ssdv gstr2b --recon`).
4. On Enterprise / CA Pack plans, the quality score’s GSTR-2B gate becomes meaningful.

Without step 2, recon would compare portal 2B against an empty purchase-bill table and falsely flag everything as “missing in books”.

## CLI

```text
# After journals are in the vault:
ssdv --db data/ssdv_connect.sqlite purchase-bills --csv examples/gstr2b_recon/purchase_register.csv
ssdv --db data/ssdv_connect.sqlite gstr2b --csv examples/gstr2b_recon/gstr2b_sample.csv --recon
```

## Purchase register CSV columns

Required (aliases accepted):

| Column | Aliases |
| :--- | :--- |
| supplier_gstin | gstin, vendor_gstin |
| invoice_no | bill_no, inv_no |
| invoice_date | bill_date, date (`DD-MM-YYYY` / `YYYY-MM-DD`) |
| taxable | taxable_value |
| cgst / sgst / igst | |

Optional: `supplier_name`, `vendor_state` / `state_code`

See `examples/gstr2b_recon/`.

## What this does **not** do

- Does not change Tally
- Does not re-post purchase journals (avoids double-counting)
- Does not replace a full Tally purchase-voucher XML pull (future enhancement)
