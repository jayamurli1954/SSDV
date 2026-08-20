"""OfficeMitra brand assets for Streamlit and installers."""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from ssdv.paths import repo_root


def brand_banner_path() -> Path:
    return repo_root() / "assets" / "officemitra-logo-banner.png"


def brand_icon_path() -> Path:
    icon = repo_root() / "assets" / "officemitra-app-icon.png"
    if icon.is_file():
        return icon
    return repo_root() / "assets" / "officemitra.png"


def render_brand_header(*, subtitle: str | None = None) -> None:
    """Logo banner at the top of every OfficeMitra screen."""
    banner = brand_banner_path()
    if banner.is_file():
        encoded = base64.b64encode(banner.read_bytes()).decode("ascii")
        st.markdown(
            f'<img class="om-brand-img" src="data:image/png;base64,{encoded}" '
            f'alt="OfficeMitra — Your AI CFO Dashboard" />',
            unsafe_allow_html=True,
        )
    else:
        st.title("OfficeMitra")
        st.caption("Your AI CFO Dashboard")
    if subtitle:
        st.caption(subtitle)
