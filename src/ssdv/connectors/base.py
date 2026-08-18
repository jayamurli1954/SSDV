from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorInfo:
    """Read-only adapter from an external system into canonical journals."""

    id: str
    title: str
    status: str
    hint: str


class ConnectorError(Exception):
    """Extract failed, vault occupied, or source is not wired yet."""


class ConnectorNotReady(ConnectorError):
    """Named source exists but native extract is not built. Export CSV instead."""
