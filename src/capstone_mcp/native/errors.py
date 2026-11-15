# Copyright 2026 Capstone MCP contributors.
"""Structured native IPC error classification and remediation rules."""

from __future__ import annotations

from typing import Final

from capstone_mcp.graphs import GraphOperationError

_ERROR_RULES: Final[tuple[tuple[tuple[str, ...], str, str], ...]] = (
    (
        ("recording",),
        "RECORDING_NOT_INITIALIZED",
        "Initialize recording session before invoking recording operations.",
    ),
    (
        ("attach", "session", "not attached", "no running capstone"),
        "SESSION_NOT_ATTACHED",
        "Call capstone_attach(launch=True) to attach to or launch PASCO Capstone.",
    ),
    (
        (
            "display",
            "digits",
            "table",
            "scope",
            "fft",
            "page",
            "layout",
            "workbook",
        ),
        "DISPLAY_ERROR",
        (
            "Verify display widget container and workbook layout via "
            "capstone://displays/active or reconfigure using capstone_manage_display."
        ),
    ),
    (
        ("sensor", "instrument", "generator", "calibration", "hardware"),
        "INSTRUMENT_ERROR",
        (
            "Verify hardware connection via capstone://hardware/inventory or check "
            "sensor configuration using capstone_manage_instrument."
        ),
    ),
    (
        ("coordinates", "foreground", "drag endpoints", "scroll position"),
        "INVALID_ARGUMENT",
        "Check tool argument types, coordinates, and constraints before retrying.",
    ),
    (
        ("invalid", "validation", "unsupported"),
        "INVALID_ARGUMENT",
        "Check tool argument types, values, and schema constraints before retrying.",
    ),
    (
        ("time",),
        "TIMEOUT_ERROR",
        (
            "Operation timed out; inspect Capstone responsiveness and reattach "
            "if needed."
        ),
    ),
)


def classify_native_error(error: Exception) -> tuple[str, str]:
    """Return (error_code, remediation) tuple for native worker exceptions."""
    if isinstance(error, GraphOperationError):
        code = (
            error.failure.code
            if error.failure and error.failure.code
            else "GRAPH_OPERATION_ERROR"
        )
        return (
            code,
            (
                "Verify graph display exists using "
                "capstone_manage_graph(action='read') or snapshot."
            ),
        )

    lower = str(error).lower()
    if "control" in lower and ("not found" in lower or "missing" in lower):
        return (
            "CONTROL_NOT_FOUND",
            (
                "Inspect active window controls using capstone_snapshot to find "
                "valid references."
            ),
        )

    for keywords, code, remediation in _ERROR_RULES:
        if any(kw in lower for kw in keywords):
            return code, remediation

    return (
        "AUTOMATION_ERROR",
        "Check Capstone application state using capstone_windows and retry.",
    )
