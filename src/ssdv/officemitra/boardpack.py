from __future__ import annotations

from typing import Any

from ssdv.officemitra.dashboard import _esc

PAGE_W = 595.28
PAGE_H = 841.89
MARGIN = 48.0
BODY_SIZE = 10.0
HEAD_SIZE = 14.0
LINE = 13.0
WRAP = 92


def _ascii(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\u20b9", "INR ")
    return text.encode("ascii", "replace").decode("ascii")


def _pdf_escape(text: str) -> str:
    return _ascii(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int = WRAP) -> list[str]:
    raw = _ascii(text).replace("\n", " ").strip()
    if not raw:
        return [""]
    words = raw.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if len(trial) <= width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def render_board_html(payload: dict[str, Any]) -> str:
    """Printable Board pack. Same facts as MIS JSON. No CDN."""
    kpis = payload.get("kpis") or {}
    board = next((p for p in payload.get("packs") or [] if p.get("id") == "board"), None)
    tiles = (board or {}).get("tiles") or []
    tile_html = "".join(
        f'<div class="tile tone-{_esc(t.get("tone") or "neutral")}">'
        f'<div class="tile-val">{_esc(t.get("value"))}</div>'
        f'<div class="tile-lab">{_esc(t.get("label"))}</div></div>'
        for t in tiles
    )
    flags = payload.get("red_flags") or []
    flag_html = (
        "".join(
            f'<p class="insight tone-{_esc(item.get("tone") or "danger")}">{_esc(item.get("text"))}</p>'
            for item in flags
        )
        or "<p>No Board red flags on DSO policy, cash, equity, or last-month profit.</p>"
    )
    score_rows = "".join(
        f"<tr><td>{_esc(row.get('name'))}</td><td class='num'>{_esc(row.get('actual'))}</td>"
        f"<td>{_esc(row.get('status'))}</td><td>{_esc(row.get('policy'))}</td></tr>"
        for row in payload.get("scorecard") or []
    )
    bench_rows = "".join(
        f"<tr><td>{_esc(row.get('name'))}</td><td class='num'>{_esc(row.get('actual'))}</td>"
        f"<td>{_esc(row.get('policy_status'))}</td><td>{_esc(row.get('vs_peer'))}</td></tr>"
        for row in payload.get("benchmarks") or []
    )
    whatif_rows = "".join(
        f"<tr><td>{_esc(row.get('prompt'))}</td><td>{_esc(row.get('result'))}</td>"
        f"<td class='num'>{_esc(row.get('delta_inr'))}</td></tr>"
        for row in payload.get("whatif") or []
    )
    parties = payload.get("parties") or {}
    overdue_rows = "".join(
        f"<tr><td>{_esc(row.get('name'))}</td><td class='num'>{_esc(row.get('overdue_90'))}</td>"
        f"<td class='num'>{_esc(row.get('outstanding'))}</td>"
        f"<td class='num'>{_esc(row.get('unaged'))}</td>"
        f"<td>{_esc(row.get('oldest_days') if row.get('oldest_days') is not None else 'unaged')}</td></tr>"
        for row in parties.get("overdue_customers") or []
    )
    vendor_rows = "".join(
        f"<tr><td>{_esc(row.get('name'))}</td><td class='num'>{_esc(row.get('outstanding'))}</td>"
        f"<td class='num'>{_esc(row.get('overdue_90'))}</td>"
        f"<td class='num'>{_esc(row.get('unaged'))}</td>"
        f"<td>{_esc(row.get('oldest_days') if row.get('oldest_days') is not None else 'unaged')}</td></tr>"
        for row in parties.get("vendor_exposure") or []
    )
    fc = payload.get("cash_forecast") or {}
    forecast_rows = "".join(
        f"<tr><td>{_esc(row.get('label'))}</td><td class='num'>{_esc(row.get('cash'))}</td>"
        f"<td class='num'>{_esc(row.get('net'))}</td></tr>"
        for row in fc.get("horizons") or []
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>OfficeMitra Board pack</title>
<style>
body {{ font-family: Segoe UI, sans-serif; margin: 24px; color: #1a1a1a; }}
h1 {{ font-size: 22px; margin: 0 0 4px; }}
h2 {{ font-size: 15px; margin: 16px 0 8px; }}
.meta {{ color: #555; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
.tile {{ border: 1px solid #ddd; padding: 12px; }}
.tile-val {{ font-size: 16px; font-weight: 600; }}
.tile-lab {{ font-size: 12px; color: #555; }}
.insight {{ margin: 0 0 8px; }}
.tone-danger {{ color: #8b1e1e; }}
.tone-success {{ color: #1e5a32; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
td, th {{ border-bottom: 1px solid #eee; padding: 6px 0; text-align: left; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
@media print {{ body {{ margin: 12mm; }} }}
</style>
</head>
<body>
<h1>{_esc(payload.get("company"))}</h1>
<p class="meta">OfficeMitra Board pack · {_esc(payload.get("scenario"))} · as of {_esc(payload.get("as_of"))} · equity {_esc(kpis.get("equity"))} · cash {_esc(kpis.get("cash"))} · quality {_esc(payload.get("data_quality_score"))} {_esc(payload.get("data_quality_band"))} · reviewed {_esc("yes" if payload.get("reviewed") else "no")}</p>
<h2>Red flags</h2>
{flag_html}
<h2>Board tiles</h2>
<div class="grid">{tile_html}</div>
<h2>Policy scorecard</h2>
<table><thead><tr><th>Policy</th><th class="num">Actual</th><th>Status</th><th>Rule</th></tr></thead><tbody>{score_rows}</tbody></table>
<h2>Benchmarks</h2>
<p class="meta">{_esc(payload.get("benchmark_source") or "")}</p>
<table><thead><tr><th>KPI</th><th class="num">Actual</th><th>Policy</th><th>vs ABC</th></tr></thead><tbody>{bench_rows}</tbody></table>
<h2>Cash forecast</h2>
<p class="meta">{_esc(fc.get("method") or "")}</p>
<table><thead><tr><th>Horizon</th><th class="num">Cash</th><th class="num">Net</th></tr></thead><tbody>{forecast_rows}</tbody></table>
<h2>What-if (recommend-only)</h2>
<p class="meta">{_esc(payload.get("whatif_method") or "")}</p>
<table><thead><tr><th>Scenario</th><th>Result</th><th class="num">Delta INR</th></tr></thead><tbody>{whatif_rows}</tbody></table>
<h2>Top overdue customers</h2>
<p class="meta">{_esc(parties.get("method") or "")}</p>
<table><thead><tr><th>Customer</th><th class="num">AR 90+</th><th class="num">Outstanding</th><th class="num">Unaged</th><th>Oldest</th></tr></thead><tbody>{overdue_rows}</tbody></table>
<h2>Top vendor exposure</h2>
<table><thead><tr><th>Vendor</th><th class="num">Outstanding</th><th class="num">AP 90+</th><th class="num">Unaged</th><th>Oldest</th></tr></thead><tbody>{vendor_rows}</tbody></table>
<p class="meta">Posted journals only. SSDV never writes back to Tally, Zoho, Busy, or MitraBooks. PPT is not in this pack.</p>
</body>
</html>
"""


def _emit_page(lines: list[tuple[float, str]], page_no: int, page_count: int) -> bytes:
    y = PAGE_H - MARGIN
    x = MARGIN
    chunks = [
        "BT",
        "/F1 8 Tf",
        f"1 0 0 1 {x:.2f} {MARGIN - 18:.2f} Tm",
        f"({_pdf_escape(f'OfficeMitra Board pack  page {page_no} of {page_count}  posted journals only')}) Tj",
        "ET",
    ]
    for size, text in lines:
        if y < MARGIN + 24:
            break
        chunks.append("BT")
        chunks.append(f"/F1 {size:.1f} Tf")
        chunks.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        chunks.append(f"({_pdf_escape(text)}) Tj")
        chunks.append("ET")
        y -= LINE if size <= BODY_SIZE else LINE + 4
    return "\n".join(chunks).encode("latin-1", "replace")


def render_board_pdf(payload: dict[str, Any]) -> bytes:
    """A4 PDF Board pack from MIS JSON. Helvetica only. No extra library."""
    kpis = payload.get("kpis") or {}
    board = next((p for p in payload.get("packs") or [] if p.get("id") == "board"), None)
    rows: list[tuple[float, str]] = [
        (HEAD_SIZE, _ascii(payload.get("company") or "OfficeMitra")),
        (
            BODY_SIZE,
            (
                f"Board pack  {payload.get('scenario')}  as of {payload.get('as_of')}  "
                f"equity {kpis.get('equity')}  cash {kpis.get('cash')}"
            ),
        ),
        (BODY_SIZE, ""),
        (HEAD_SIZE, "Red flags"),
    ]
    flags = payload.get("red_flags") or []
    if flags:
        for item in flags:
            for line in _wrap(f"- {item.get('text')}"):
                rows.append((BODY_SIZE, line))
    else:
        rows.append((BODY_SIZE, "No Board red flags on DSO, cash, equity, or last-month profit."))

    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "Board tiles"))
    for tile in (board or {}).get("tiles") or []:
        rows.append((BODY_SIZE, f"{tile.get('label')}: {tile.get('value')}"))

    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "Policy scorecard"))
    for row in payload.get("scorecard") or []:
        for line in _wrap(
            f"{row.get('name')}  {row.get('actual')}  {row.get('status')}  {row.get('policy')}"
        ):
            rows.append((BODY_SIZE, line))

    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "Benchmarks (SSDV policy; ABC baseline is not industry)"))
    for row in payload.get("benchmarks") or []:
        for line in _wrap(
            f"{row.get('name')}  {row.get('actual')}  {row.get('policy_status')}  {row.get('vs_peer')}"
        ):
            rows.append((BODY_SIZE, line))

    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "Cash forecast 30 / 60 / 90"))
    fc = payload.get("cash_forecast") or {}
    for item in fc.get("horizons") or []:
        rows.append(
            (BODY_SIZE, f"{item.get('label')}: cash {item.get('cash')}  net {item.get('net')}")
        )

    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "What-if (recommend-only; books are not changed)"))
    for item in payload.get("whatif") or []:
        for line in _wrap(
            f"{item.get('prompt')}  {item.get('result')}  delta {item.get('delta_inr')}"
        ):
            rows.append((BODY_SIZE, line))

    parties = payload.get("parties") or {}
    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "Top overdue customers"))
    overdue = list(parties.get("overdue_customers") or [])
    if overdue:
        for item in overdue[:10]:
            oldest = item.get("oldest_days")
            age = f"{oldest} d" if oldest is not None else "unaged"
            rows.append(
                (
                    BODY_SIZE,
                    (
                        f"{item.get('name')}: 90+ {item.get('overdue_90')}  "
                        f"AR {item.get('outstanding')}  oldest {age}"
                    ),
                )
            )
    else:
        rows.append((BODY_SIZE, "No open customer balances."))
    rows.append((BODY_SIZE, ""))
    rows.append((HEAD_SIZE, "Top vendor exposure"))
    vendors = list(parties.get("vendor_exposure") or [])
    if vendors:
        for item in vendors[:10]:
            oldest = item.get("oldest_days")
            age = f"{oldest} d" if oldest is not None else "unaged"
            rows.append(
                (
                    BODY_SIZE,
                    (
                        f"{item.get('name')}: AP {item.get('outstanding')}  "
                        f"90+ {item.get('overdue_90')}  oldest {age}"
                    ),
                )
            )
    else:
        rows.append((BODY_SIZE, "No open vendor balances."))

    rows.append((BODY_SIZE, ""))
    rows.append(
        (
            BODY_SIZE,
            "SSDV never writes back to Tally, Zoho, Busy, or MitraBooks. PPT is not in this pack.",
        )
    )

    usable = int((PAGE_H - MARGIN * 2 - 24) / LINE)
    pages: list[list[tuple[float, str]]] = []
    chunk: list[tuple[float, str]] = []
    used = 0
    for row in rows:
        cost = 2 if row[0] > BODY_SIZE else 1
        if used + cost > usable and chunk:
            pages.append(chunk)
            chunk = []
            used = 0
        chunk.append(row)
        used += cost
    if chunk:
        pages.append(chunk)
    if not pages:
        pages = [[(BODY_SIZE, "No Board pack lines.")]]
    return _assemble_pdf(pages)


def _assemble_pdf(pages: list[list[tuple[float, str]]]) -> bytes:
    n = len(pages)
    page_ids = list(range(3, 3 + n))
    content_ids = list(range(3 + n, 3 + 2 * n))
    font_id = 3 + 2 * n

    streams = [_emit_page(page, i + 1, n) for i, page in enumerate(pages)]
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("ascii"),
    ]
    for _pid, cid in zip(page_ids, content_ids, strict=True):
        objs.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
                f"/Contents {cid} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
            ).encode("ascii")
        )
    for stream in streams:
        objs.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objs) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode(
            "ascii"
        )
    )
    return bytes(out)
