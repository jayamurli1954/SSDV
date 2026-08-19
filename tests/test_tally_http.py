"""Tests for the TallyPrime HTTP connector (Phase 6.1).

All HTTP calls are mocked — no running TallyPrime instance needed.
"""

from __future__ import annotations

from unittest.mock import patch

from ssdv.connectors.registry import get_connector, require_ready
from ssdv.connectors.tally_http import (
    list_companies,
    ping,
    pull_daybook_xml,
)

# -- Registry wiring ---------------------------------------------------------

def test_tally_http_connector_is_registered() -> None:
    info = get_connector("tally-http")
    assert info.status == "ready"
    assert "HTTP" in info.title


def test_tally_http_require_ready_does_not_raise() -> None:
    info = require_ready("tally-http")
    assert info.id == "tally-http"


# -- ping / list_companies with mocked HTTP -----------------------------------

_COMPANY_XML = b"""\
<ENVELOPE>
 <BODY>
  <DATA>
   <COLLECTION>
    <COMPANY>
     <NAME>ABC Traders Pvt Ltd</NAME>
    </COMPANY>
    <COMPANY>
     <NAME>XYZ Industries</NAME>
    </COMPANY>
   </COLLECTION>
  </DATA>
 </BODY>
</ENVELOPE>"""


def _mock_post_xml_ok(host: str, payload: str, *, timeout: int = 30) -> bytes:
    return _COMPANY_XML


def _mock_post_xml_fail(host: str, payload: str, *, timeout: int = 30) -> bytes:
    from ssdv.connectors.base import ConnectorError

    raise ConnectorError("connection refused")


def test_ping_success() -> None:
    with patch("ssdv.connectors.tally_http._post_xml", _mock_post_xml_ok):
        assert ping() is True


def test_ping_failure() -> None:
    with patch("ssdv.connectors.tally_http._post_xml", _mock_post_xml_fail):
        assert ping() is False


def test_list_companies() -> None:
    with patch("ssdv.connectors.tally_http._post_xml", _mock_post_xml_ok):
        names = list_companies()
        assert "ABC Traders Pvt Ltd" in names
        assert "XYZ Industries" in names


# -- pull_daybook_xml with mocked HTTP ----------------------------------------

_DAYBOOK_XML = b"""\
<ENVELOPE>
 <BODY>
  <DATA>
   <TALLYMESSAGE>
    <VOUCHER>
     <VCHTYPE>Sales</VCHTYPE>
     <VCHDATE>15-06-2024</VCHDATE>
     <VCHNO>V001</VCHNO>
     <NARRATION>Test sale</NARRATION>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Sundry Debtors</LEDGERNAME>
      <AMOUNT>-11800</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Sales Account</LEDGERNAME>
      <AMOUNT>10000</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Output CGST</LEDGERNAME>
      <AMOUNT>900</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
     <ALLLEDGERENTRIES.LIST>
      <LEDGERNAME>Output SGST</LEDGERNAME>
      <AMOUNT>900</AMOUNT>
     </ALLLEDGERENTRIES.LIST>
    </VOUCHER>
   </TALLYMESSAGE>
  </DATA>
 </BODY>
</ENVELOPE>"""


def _mock_daybook(host: str, payload: str, *, timeout: int = 30) -> bytes:
    return _DAYBOOK_XML


def test_pull_daybook_xml_returns_bytes() -> None:
    with patch("ssdv.connectors.tally_http._post_xml", _mock_daybook):
        raw = pull_daybook_xml()
        assert b"VOUCHER" in raw
        assert b"Sales Account" in raw


def test_cli_parser_accepts_tally_http_source() -> None:
    from ssdv.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "connect",
        "--source", "tally-http",
        "--host", "http://192.168.1.10:9000",
        "--name", "My Company",
    ])
    assert args.source == "tally-http"
    assert args.host == "http://192.168.1.10:9000"
    assert args.name == "My Company"
