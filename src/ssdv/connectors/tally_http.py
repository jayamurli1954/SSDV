"""TallyPrime HTTP connector (Phase 6.1).

TallyPrime exposes an XML-over-HTTP interface on port 9000 (default).
This module sends TDL-style XML requests to pull:
  - DayBook (all vouchers for a date range)
  - Ledger Masters (chart of accounts / party list)

Usage from CLI:
    ssdv connect --source tally-http --host http://localhost:9000

The pulled XML is fed directly into the existing Tally DayBook parser
(``ingest_tally_daybook``), so all mapping, posting, and MIS flows work
identically to the file-based ``--source tally`` path.
"""

from __future__ import annotations

import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ssdv.connectors.base import ConnectorError
from ssdv.ingest.generic import IngestResult
from ssdv.ingest.tally_daybook import ingest_tally_daybook

DEFAULT_TALLY_HOST = "http://localhost:9000"


@dataclass(frozen=True)
class TallyConnection:
    host: str
    company: str | None = None


# ---------------------------------------------------------------------------
# TDL XML request templates
# ---------------------------------------------------------------------------

_DAYBOOK_REQUEST = """\
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Export</TALLYREQUEST>
  <TYPE>Data</TYPE>
  <ID>Day Book</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
    {company_tag}
    <SVCURRENTDATE>{to_date}</SVCURRENTDATE>
    <SVFROMDATE>{from_date}</SVFROMDATE>
    <SVTODATE>{to_date}</SVTODATE>
   </STATICVARIABLES>
  </DESC>
 </BODY>
</ENVELOPE>"""

_LEDGER_MASTER_REQUEST = """\
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Export</TALLYREQUEST>
  <TYPE>Data</TYPE>
  <ID>List of Ledgers</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
    {company_tag}
   </STATICVARIABLES>
  </DESC>
 </BODY>
</ENVELOPE>"""

_COMPANY_LIST_REQUEST = """\
<ENVELOPE>
 <HEADER>
  <VERSION>1</VERSION>
  <TALLYREQUEST>Export</TALLYREQUEST>
  <TYPE>Collection</TYPE>
  <ID>List of Companies</ID>
 </HEADER>
 <BODY>
  <DESC>
   <STATICVARIABLES>
    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
   </STATICVARIABLES>
   <TDL>
    <TDLMESSAGE>
     <COLLECTION NAME="List of Companies" ISMODIFY="No">
      <TYPE>Company</TYPE>
      <FETCH>NAME</FETCH>
     </COLLECTION>
    </TDLMESSAGE>
   </TDL>
  </DESC>
 </BODY>
</ENVELOPE>"""


# ---------------------------------------------------------------------------
# HTTP transport
# ---------------------------------------------------------------------------

def _post_xml(host: str, payload: str, *, timeout: int = 30) -> bytes:
    """Send an XML request to TallyPrime and return the raw response bytes."""
    data = payload.encode("utf-8")
    req = urllib.request.Request(
        host,
        data=data,
        headers={"Content-Type": "application/xml; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.URLError as exc:
        raise ConnectorError(
            f"Cannot reach TallyPrime at {host}. "
            f"Ensure TallyPrime is running with ODBC server enabled on that port.\n"
            f"Detail: {exc}"
        ) from exc


def _company_tag(company: str | None) -> str:
    if company:
        return f"<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>"
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ping(host: str = DEFAULT_TALLY_HOST) -> bool:
    """Return True if a TallyPrime instance responds at *host*."""
    try:
        _post_xml(host, _COMPANY_LIST_REQUEST, timeout=5)
        return True
    except ConnectorError:
        return False


def list_companies(host: str = DEFAULT_TALLY_HOST) -> list[str]:
    """Return the company names open in TallyPrime."""
    raw = _post_xml(host, _COMPANY_LIST_REQUEST, timeout=10)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ConnectorError(f"TallyPrime returned invalid XML: {exc}") from exc

    names: list[str] = []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag in ("COMPANY", "NAME"):
            text = (elem.text or "").strip()
            if text and text not in names:
                names.append(text)
    return names


def pull_daybook_xml(
    host: str = DEFAULT_TALLY_HOST,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    company: str | None = None,
    timeout: int = 120,
) -> bytes:
    """Pull the DayBook XML from TallyPrime over HTTP."""
    fd = from_date or date(2023, 4, 1)
    td = to_date or datetime.now(tz=timezone.utc).date()
    payload = _DAYBOOK_REQUEST.format(
        from_date=fd.strftime("%d-%m-%Y"),
        to_date=td.strftime("%d-%m-%Y"),
        company_tag=_company_tag(company),
    )
    return _post_xml(host, payload, timeout=timeout)


def pull_ledger_masters_xml(
    host: str = DEFAULT_TALLY_HOST,
    *,
    company: str | None = None,
    timeout: int = 60,
) -> bytes:
    """Pull the Ledger Master list from TallyPrime over HTTP."""
    payload = _LEDGER_MASTER_REQUEST.format(
        company_tag=_company_tag(company),
    )
    return _post_xml(host, payload, timeout=timeout)


def pull_and_ingest(
    session: Session,
    *,
    host: str = DEFAULT_TALLY_HOST,
    from_date: date | None = None,
    to_date: date | None = None,
    company: str | None = None,
    company_name: str | None = None,
    account_map: Path | None = None,
) -> IngestResult:
    """Pull DayBook from TallyPrime HTTP and ingest into the session.

    This is the main entry-point wired into the connector pipeline.
    """
    xml_bytes = pull_daybook_xml(
        host,
        from_date=from_date,
        to_date=to_date,
        company=company,
        timeout=180,
    )
    if not xml_bytes or len(xml_bytes) < 50:
        raise ConnectorError(
            "TallyPrime returned an empty or very short response. "
            "Check that the company has vouchers in the requested date range."
        )

    # Write to a temp file so the existing XML parser can read it.
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(xml_bytes)
        tmp_path = Path(tmp.name)

    try:
        return ingest_tally_daybook(
            session,
            tmp_path,
            account_map,
            company_name=company_name or company,
            source="tally-http",
        )
    finally:
        tmp_path.unlink(missing_ok=True)
