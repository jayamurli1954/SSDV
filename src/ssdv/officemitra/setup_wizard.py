"""Streamlit setup wizard UI for OfficeMitra."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ssdv.connectors import ConnectorError, ConnectorNotReady
from ssdv.connectors.tally_http import DEFAULT_TALLY_HOST, list_companies, ping
from ssdv.ingest import IngestError
from ssdv.officemitra.firm import assert_can_add_vault, client_vault_path
from ssdv.officemitra.setup_flow import (
    connect_vault_path,
    friendly_status,
    ingest_meta_as_of,
    run_import,
    source_choices,
    validate_vault,
    vault_has_data,
    vault_voucher_count,
)


def _write_upload(upload, suffix: str) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="ssdv_setup_"))
    path = folder / f"export{suffix}"
    path.write_bytes(upload.getvalue())
    return path


def _render_overwrite_confirm(*, voucher_count: int) -> bool:
    st.warning(
        f"**Existing data will be overwritten.**\n\n"
        f"This vault already has **{voucher_count:,} voucher(s)**. "
        f"Importing again will **replace** all previous books, KPIs, and reports. "
        f"This cannot be undone."
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, overwrite and continue", type="primary", key="setup_overwrite_yes"):
            return True
    with col2:
        if st.button("Cancel", key="setup_overwrite_no"):
            st.session_state.pop("setup_pending", None)
            st.rerun()
    return False


def _execute_pending_import() -> None:
    pending = st.session_state.get("setup_pending")
    if not pending:
        return

    source = str(pending["source"])
    force = bool(pending.get("force", False))
    company_name = pending.get("company_name") or None
    tally_host = pending.get("tally_host") or None
    journal_path = Path(pending["journal_path"]) if pending.get("journal_path") else None
    map_path = Path(pending["map_path"]) if pending.get("map_path") else None
    vault = Path(pending["vault"]) if pending.get("vault") else connect_vault_path()

    with st.spinner("Importing books…"):
        try:
            result = run_import(
                source=source,
                journals=journal_path,
                account_map=map_path,
                company_name=company_name,
                tally_host=tally_host,
                force=force,
                db_path=vault,
            )
        except ConnectorNotReady as exc:
            st.error(str(exc))
            st.session_state.pop("setup_pending", None)
            return
        except ConnectorError as exc:
            st.error(f"Connection failed: {exc}")
            st.session_state.pop("setup_pending", None)
            return
        except IngestError as exc:
            st.error(f"Import failed: {exc}")
            st.session_state.pop("setup_pending", None)
            return

    with st.spinner("Checking books…"):
        ok, errors = validate_vault(vault, result.last_date)

    if not ok:
        st.error("Books were imported but validation failed. Please fix the export and try again.")
        for msg in errors[:8]:
            st.markdown(f"- {msg}")
        if len(errors) > 8:
            st.caption(f"…and {len(errors) - 8} more checks.")
        st.session_state.pop("setup_pending", None)
        return

    st.success(
        f"Import complete — {result.vouchers} vouchers, "
        f"{result.first_date.isoformat()} to {result.last_date.isoformat()}."
    )
    st.session_state["setup_complete"] = True
    st.session_state["pending_vault"] = str(vault)
    st.session_state["pending_as_of"] = result.last_date
    st.session_state["pending_screen"] = "CEO"
    st.session_state.pop("setup_pending", None)
    st.session_state.pop("show_setup", None)
    st.cache_data.clear()
    st.rerun()


def render_setup_wizard() -> None:
    """Render the setup flow. Main app should return immediately after calling this."""

    st.header("Connect your accounts data")
    st.write(
        "Choose where your books come from. OfficeMitra reads data only — "
        "it never writes back to Tally, Zoho, Busy, or any other application."
    )

    if st.session_state.get("setup_pending"):
        pending = st.session_state["setup_pending"]
        if pending.get("needs_confirm"):
            if not _render_overwrite_confirm(voucher_count=int(pending["voucher_count"])):
                return
            pending["needs_confirm"] = False
            pending["force"] = True
            st.session_state["setup_pending"] = pending
        _execute_pending_import()
        return

    choices = source_choices()
    labels = [f"{c.title} — {friendly_status(c.status)}" for c in choices]
    by_label = dict(zip(labels, choices, strict=True))

    selected_label = st.radio(
        "Data source",
        labels,
        index=0,
        help="Live connectors pull directly. Others need an export file from your accounting app.",
    )
    choice = by_label[selected_label]

    st.info(choice.hint)

    company_name = st.text_input("Company name (shown on reports)", value="")

    journal_path: Path | None = None
    map_path: Path | None = None
    tally_host: str | None = None
    import_source = choice.id

    if choice.is_live:
        tally_host = st.text_input(
            "TallyPrime address",
            value=DEFAULT_TALLY_HOST,
            help="TallyPrime must be running with ODBC/HTTP server enabled (port 9000).",
        )
        if st.button("Test connection", key="setup_ping"):
            if ping(tally_host):
                companies = list_companies(tally_host)
                if companies:
                    st.success(f"Connected. Open companies: {', '.join(companies)}")
                else:
                    st.success("Connected to TallyPrime.")
            else:
                st.error(
                    "Cannot reach TallyPrime. Check that it is running and the address is correct. "
                    "You can still upload a DayBook XML file using the **Tally / TallyPrime** option."
                )
    else:
        if choice.status == "export_csv":
            st.caption(
                f"No live login for {choice.title}. "
                "Export a journal register and upload it below "
                "(same CSV columns as Any ERP)."
            )

        journal_upload = st.file_uploader(
            choice.journal_label,
            type=choice.upload_journal_types,
            help="Required",
        )
        map_upload = st.file_uploader(
            "Ledger map (optional CSV or YAML)",
            type=["csv", "yml", "yaml"],
            help="Maps your ledger names to SSDV account codes. Auto-mapping works for common names.",
        )

        if journal_upload is None:
            st.caption("Upload a file to continue.")
            if vault_has_data():
                st.divider()
                if st.button("Continue to dashboard with existing books", key="setup_skip"):
                    vault = connect_vault_path()
                    as_of = ingest_meta_as_of(vault)
                    st.session_state["setup_complete"] = True
                    st.session_state["pending_vault"] = str(vault)
                    if as_of is not None:
                        st.session_state["pending_as_of"] = as_of
                    st.session_state["pending_screen"] = "CEO"
                    st.session_state.pop("show_setup", None)
                    st.rerun()
            return

        suffix = Path(str(journal_upload.name)).suffix.lower() or (
            ".xml" if choice.id == "tally" else ".csv"
        )
        journal_path = _write_upload(journal_upload, suffix)
        if map_upload is not None:
            map_suffix = Path(str(map_upload.name)).suffix.lower() or ".csv"
            map_path = _write_upload(map_upload, map_suffix)

    import_label = "Connect and import" if choice.is_live else "Upload and import"
    if st.button(import_label, type="primary", key="setup_import"):
        if choice.is_live and not tally_host:
            st.error("Enter the TallyPrime address.")
            return
        if choice.needs_upload and journal_path is None:
            st.error("Upload a data file first.")
            return

        vault = (
            client_vault_path(company_name.strip())
            if company_name.strip()
            else connect_vault_path()
        )
        try:
            assert_can_add_vault(vault)
        except ConnectorError as exc:
            st.error(str(exc))
            return
        existing = vault_voucher_count(vault)
        st.session_state["setup_pending"] = {
            "source": import_source,
            "company_name": company_name.strip() or None,
            "tally_host": tally_host,
            "journal_path": str(journal_path) if journal_path else None,
            "map_path": str(map_path) if map_path else None,
            "vault": str(vault),
            "force": existing > 0,
            "needs_confirm": existing > 0,
            "voucher_count": existing,
        }
        st.rerun()

    if vault_has_data():
        st.divider()
        st.caption(
            f"Books already loaded ({vault_voucher_count(connect_vault_path()):,} vouchers). "
            "Import again only if you want to replace them."
        )
        if st.button("Continue to dashboard with existing books", key="setup_skip"):
            vault = connect_vault_path()
            as_of = ingest_meta_as_of(vault)
            st.session_state["setup_complete"] = True
            st.session_state["pending_vault"] = str(vault)
            if as_of is not None:
                st.session_state["pending_as_of"] = as_of
            st.session_state["pending_screen"] = "CEO"
            st.session_state.pop("show_setup", None)
            st.rerun()
