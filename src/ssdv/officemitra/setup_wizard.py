"""Streamlit setup wizard UI for OfficeMitra."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ssdv.connectors import ConnectorError, ConnectorNotReady
from ssdv.connectors.tally_http import DEFAULT_TALLY_HOST, list_companies, ping
from ssdv.ingest import IngestError
from ssdv.ingest.suggest import GUESSED, UNMAPPED, postable_chart
from ssdv.officemitra.firm import assert_can_add_vault, client_vault_path
from ssdv.officemitra.setup_flow import (
    connect_vault_path,
    friendly_status,
    ingest_meta_as_of,
    pull_tally_chart,
    pull_tally_daybook,
    review_mapping,
    run_import,
    save_confirmed_map,
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


def _render_mapping_step() -> None:
    """Show ledgers the saved client map does not cover; import only after a person confirms."""
    import pandas as pd

    state = st.session_state["setup_mapping"]
    rows = list(state["rows"])
    chart = postable_chart()
    label_by_code = {item.code: item.label for item in chart}
    code_by_label = {item.label: item.code for item in chart}

    unmapped = sum(1 for row in rows if row["status"] == UNMAPPED)
    guessed = sum(1 for row in rows if row["status"] == GUESSED)
    st.subheader("Confirm ledger mapping")
    st.write(
        f"**{len(rows)} ledger(s)** in this export are not in the saved map for this client: "
        f"**{unmapped}** new and **{guessed}** matched by keyword. "
        "Check the suggested ledger in the last column and change it where needed. "
        "Nothing is imported until you confirm, and your choices are remembered for the next import."
    )
    frame = pd.DataFrame(
        [
            {
                "Ledger in your books": row["ledger"],
                "Client name": row.get("client_name") or "",
                "Client group": row.get("client_group") or "",
                "Lines": row["lines"],
                "Debit": row["debit"],
                "Credit": row["credit"],
                "Why": row["reason"],
                "Map to": label_by_code.get(row["proposed"] or ""),
            }
            for row in rows
        ]
    )
    edited = st.data_editor(
        frame,
        column_config={
            "Map to": st.column_config.SelectboxColumn(
                "Map to", options=list(code_by_label), required=False, width="large"
            )
        },
        disabled=[
            "Ledger in your books",
            "Client name",
            "Client group",
            "Lines",
            "Debit",
            "Credit",
            "Why",
        ],
        hide_index=True,
        use_container_width=True,
        key="setup_mapping_editor",
    )
    choices: dict[str, str] = {}
    missing: list[str] = []
    for ledger, label in zip(edited["Ledger in your books"], edited["Map to"], strict=True):
        code = code_by_label.get(str(label)) if label is not None else None
        if code is None:
            missing.append(str(ledger))
        else:
            choices[str(ledger)] = code
    if missing:
        shown = ", ".join(missing[:5]) + ("…" if len(missing) > 5 else "")
        st.warning(f"{len(missing)} ledger(s) still need a choice: {shown}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "Save mapping and import",
            type="primary",
            disabled=bool(missing),
            key="setup_mapping_save",
        ):
            pending = dict(state["pending"])
            try:
                saved = save_confirmed_map(Path(pending["vault"]), dict(state["base_map"]), choices)
            except IngestError as exc:
                st.error(str(exc))
                return
            pending["map_path"] = str(saved)
            st.session_state["setup_pending"] = pending
            st.session_state.pop("setup_mapping", None)
            st.rerun()
    with col2:
        if st.button("Cancel", key="setup_mapping_cancel"):
            st.session_state.pop("setup_mapping", None)
            st.rerun()


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
    chart_path = Path(pending["chart_path"]) if pending.get("chart_path") else None
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
                client_chart=chart_path,
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

    if st.session_state.get("setup_mapping"):
        _render_mapping_step()
        return

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

    gate = {"tally": "connect_tally_xml", "tally-http": "connect_tally_http"}.get(choice.id)
    if gate:
        from ssdv.officemitra.entitlements import current_entitlements, upgrade_note

        ent = current_entitlements()
        if not ent.allows(gate):
            st.warning(upgrade_note(gate, ent))
            return

    st.info(choice.hint)

    company_name = st.text_input("Company name (shown on reports)", value="")

    journal_path: Path | None = None
    map_path: Path | None = None
    chart_path: Path | None = None
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
        chart_upload = st.file_uploader(
            "Your chart of accounts (optional CSV: code, name, group)",
            type=["csv"],
            help=(
                "Your own ledger codes (any length), names and groups. Reports can then be "
                "shown and exported in your chart. Saved for the next import of this client."
            ),
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
        if chart_upload is not None:
            chart_path = _write_upload(chart_upload, ".csv")

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
        try:
            if choice.is_live:
                with st.spinner("Reading TallyPrime…"):
                    journal_path = pull_tally_daybook(str(tally_host))
                    chart_path = pull_tally_chart(str(tally_host))
            with st.spinner("Checking ledgers…"):
                review = review_mapping(
                    source=import_source,
                    journals=journal_path,
                    account_map=map_path,
                    db_path=vault,
                    client_chart=chart_path,
                )
        except ConnectorError as exc:
            st.error(f"Connection failed: {exc}")
            return
        except (IngestError, ValueError) as exc:
            st.error(f"Could not read the export: {exc}")
            return
        pending = {
            "source": import_source,
            "company_name": company_name.strip() or None,
            "tally_host": tally_host,
            "journal_path": str(journal_path) if journal_path else None,
            "map_path": str(map_path) if map_path else None,
            "chart_path": str(chart_path) if chart_path else None,
            "vault": str(vault),
            "force": existing > 0,
            "needs_confirm": existing > 0,
            "voucher_count": existing,
        }
        if review.pending:
            st.session_state["setup_mapping"] = {
                "pending": pending,
                "base_map": review.base_map,
                "rows": [
                    {
                        "ledger": row.ledger,
                        "lines": row.lines,
                        "debit": f"{row.debit:,.2f}",
                        "credit": f"{row.credit:,.2f}",
                        "status": row.status,
                        "client_name": row.client_name,
                        "client_group": row.client_group,
                        "reason": row.reason,
                        "proposed": row.proposed,
                    }
                    for row in review.pending
                ],
            }
        else:
            if review.base_map:
                pending["map_path"] = str(save_confirmed_map(vault, review.base_map, {}))
            st.session_state["setup_pending"] = pending
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
