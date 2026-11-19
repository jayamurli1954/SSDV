"""Issue a signed OfficeMitra licence (SanMitra internal).

The private signing key lives OUTSIDE this repository, by default at
%USERPROFILE%\\.officemitra-issuer\\license_signing_key.pem. Back it up somewhere safe:
without it no new licences can be issued, and anyone holding it can issue them.

Examples:
  python scripts/issue_license.py keygen
  python scripts/issue_license.py issue --plan ca_20 --customer "ASVA & Associates LLP" \
      --gstin 29AAAAA0000A1Z5 --amc-months 12 --out ASVA.officemitra.license
  python scripts/issue_license.py verify ASVA.officemitra.license
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ssdv.licensing import load_plans, parse_license_payload
from ssdv.licensing.signing import public_key_b64_for, sign_payload, verify_signature

DEFAULT_KEY = Path.home() / ".officemitra-issuer" / "license_signing_key.pem"
SIGNING_MODULE = ROOT / "src" / "ssdv" / "licensing" / "signing.py"


def _load_key(path: Path) -> Ed25519PrivateKey:
    if not path.is_file():
        raise SystemExit(f"Signing key not found: {path}. Run 'keygen' once, or pass --key.")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("Signing key is not an Ed25519 key")
    return key


def cmd_keygen(args: argparse.Namespace) -> int:
    path = Path(args.key)
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists. Refusing to overwrite (that would orphan issued licences).")
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public = public_key_b64_for(key)
    text = SIGNING_MODULE.read_text(encoding="utf-8")
    marker = 'PUBLIC_KEY_B64 = "'
    start = text.index(marker) + len(marker)
    end = text.index('"', start)
    SIGNING_MODULE.write_text(text[:start] + public + text[end:], encoding="utf-8")
    print(f"Private key written to {path} (keep it secret, back it up).")
    print(f"Public key embedded in {SIGNING_MODULE.relative_to(ROOT)}: {public}")
    return 0


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    for candidate in (day.day, 30, 29, 28):
        try:
            return date(year, month, candidate)
        except ValueError:
            continue
    raise ValueError("bad date")


def cmd_issue(args: argparse.Namespace) -> int:
    plans = load_plans()
    if args.plan not in plans:
        raise SystemExit(f"Unknown plan {args.plan!r}. Choose one of: {', '.join(sorted(plans))}")
    plan = plans[args.plan]
    issued = date.fromisoformat(args.issued) if args.issued else date.today()  # noqa: DTZ011 (issuer local date)
    payload = {
        "schema_version": 2,
        "license_id": args.license_id or f"OM-{issued.year}-{uuid4().hex[:8].upper()}",
        "customer_name": args.customer.strip(),
        "plan_id": args.plan,
        "company_limit": int(args.company_limit or plan.company_limit),
        "issued_at": issued.isoformat(),
        "amc_expires_at": _add_months(issued, args.amc_months).isoformat(),
    }
    if args.gstin:
        payload["gstin"] = args.gstin.strip().upper()
    if args.machine:
        payload["machine_id"] = args.machine.strip()
    signed = sign_payload(payload, _load_key(Path(args.key)))
    parse_license_payload(signed)  # same checks the app runs
    out = Path(args.out or f"{payload['license_id']}.officemitra.license")
    out.write_text(json.dumps(signed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}  ({plan.name}, {payload['company_limit']} companies, AMC to {payload['amc_expires_at']})")
    print("Customer copies it to %USERPROFILE%\\.officemitra\\officemitra.license (Windows)")
    print("or ~/.officemitra/officemitra.license (Mac), then restarts OfficeMitra.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    ok = verify_signature(data)
    print("signature:", "VALID" if ok else "INVALID")
    if ok:
        lic = parse_license_payload(data)
        print(lic.summary_line())
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key", default=str(DEFAULT_KEY), help="Private signing key (PEM)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    keygen = sub.add_parser("keygen", help="Create the signing key once and embed its public half")
    keygen.add_argument("--force", action="store_true")
    keygen.set_defaults(func=cmd_keygen)

    issue = sub.add_parser("issue", help="Issue a signed licence")
    issue.add_argument("--plan", required=True)
    issue.add_argument("--customer", required=True)
    issue.add_argument("--company-limit", type=int)
    issue.add_argument("--amc-months", type=int, default=12)
    issue.add_argument("--issued", help="YYYY-MM-DD (default today)")
    issue.add_argument("--gstin")
    issue.add_argument("--machine", help="Bind to this Windows computer name (optional)")
    issue.add_argument("--license-id")
    issue.add_argument("--out")
    issue.set_defaults(func=cmd_issue)

    verify = sub.add_parser("verify", help="Check a licence file")
    verify.add_argument("file")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
