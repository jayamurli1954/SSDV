from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ssdv.licensing.plans import PlanSpec, load_plans, plan_for
from ssdv.paths import install_dir as default_install_dir
from ssdv.paths import repo_root, user_data_dir


class LicenseError(Exception):
    """Invalid or missing license file."""


@dataclass(frozen=True)
class License:
    schema_version: int
    license_id: str
    customer_name: str
    plan_id: str
    company_limit: int
    issued_at: date
    amc_expires_at: date
    gstin: str | None = None
    machine_id: str | None = None
    feature_overrides: dict[str, bool] | None = None
    source_path: Path | None = None

    @property
    def amc_active(self) -> bool:
        return self.amc_expires_at >= date.today()

    def plan(self) -> PlanSpec:
        return plan_for(self.plan_id)

    def allows(self, feature: str) -> bool:
        if self.feature_overrides and feature in self.feature_overrides:
            return bool(self.feature_overrides[feature])
        return self.plan().features.get(feature, False)

    def summary_line(self) -> str:
        plan_name = self.plan().name
        amc = "active" if self.amc_active else "expired"
        return (
            f"License valid — {plan_name}  |  "
            f"Updates {amc} until {self.amc_expires_at.isoformat()}  |  "
            f"Companies: up to {self.company_limit}"
        )


def resolve_license_paths(install_dir: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    home = Path.home() / ".officemitra" / "officemitra.license"
    paths.append(home)
    paths.append(user_data_dir() / "officemitra.license")
    bundled = install_dir if install_dir is not None else default_install_dir()
    paths.append(bundled / "officemitra.license")
    paths.append(repo_root() / "officemitra.license")
    return paths


def _parse_date(raw: str, *, field: str) -> date:
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError as exc:
        raise LicenseError(f"{field} must be ISO date (YYYY-MM-DD), got {raw!r}") from exc


def parse_license_payload(data: dict, *, source: Path | None = None) -> License:
    if not isinstance(data, dict):
        raise LicenseError("License file must be a JSON object")

    schema_version = int(data.get("schema_version", 0))
    if schema_version != 1:
        raise LicenseError(f"Unsupported schema_version {schema_version}")

    plan_id = str(data.get("plan_id") or "").strip()
    if not plan_id:
        raise LicenseError("plan_id is required")

    catalog = load_plans()
    try:
        plan = plan_for(plan_id, plans=catalog)
    except KeyError as exc:
        raise LicenseError(str(exc)) from exc

    company_limit = int(data.get("company_limit", plan.company_limit))
    if company_limit > plan.company_limit:
        raise LicenseError(
            f"company_limit {company_limit} exceeds plan maximum {plan.company_limit} for {plan_id}"
        )

    license_id = str(data.get("license_id") or "").strip()
    customer_name = str(data.get("customer_name") or "").strip()
    if not license_id or not customer_name:
        raise LicenseError("license_id and customer_name are required")

    overrides_raw = data.get("features")
    overrides: dict[str, bool] | None = None
    if overrides_raw is not None:
        if not isinstance(overrides_raw, dict):
            raise LicenseError("features override must be an object")
        overrides = {str(k): bool(v) for k, v in overrides_raw.items()}

    gstin = data.get("gstin")
    machine_id = data.get("machine_id")

    return License(
        schema_version=schema_version,
        license_id=license_id,
        customer_name=customer_name,
        plan_id=plan_id,
        company_limit=company_limit,
        issued_at=_parse_date(str(data["issued_at"]), field="issued_at"),
        amc_expires_at=_parse_date(str(data["amc_expires_at"]), field="amc_expires_at"),
        gstin=str(gstin).strip() if gstin else None,
        machine_id=str(machine_id).strip() if machine_id else None,
        feature_overrides=overrides,
        source_path=source,
    )


def load_license(
    *,
    install_dir: Path | None = None,
    explicit_path: Path | None = None,
) -> License | None:
    """Load the first valid license file found, or None if unlicensed (dev/demo)."""
    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    candidates.extend(resolve_license_paths(install_dir))

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        explicit = explicit_path is not None and path.resolve() == explicit_path.resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            license_obj = parse_license_payload(data, source=path)
        except (OSError, json.JSONDecodeError):
            continue
        except LicenseError:
            if explicit:
                raise
            continue
        if license_obj.machine_id:
            host = os.environ.get("COMPUTERNAME", "") or os.environ.get("HOSTNAME", "")
            if host and license_obj.machine_id.casefold() not in (host.casefold(),):
                raise LicenseError(
                    f"License is bound to another machine ({license_obj.machine_id!r})"
                )
        return license_obj
    return None
