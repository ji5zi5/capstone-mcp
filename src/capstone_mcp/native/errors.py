# Copyright 2026 Capstone MCP contributors.
"""Structured native IPC error classification and remediation rules."""

from __future__ import annotations

import re
from typing import Final

from pywinauto.uia_defines import NoPatternInterfaceError

from capstone_mcp.graphs import GraphOperationError

_ERROR_RULES: Final[tuple[tuple[tuple[str, ...], str, str], ...]] = (
    (
        ("timed out", "timeout", "deadline exceeded", "time exceeded"),
        "TIMEOUT_ERROR",
        (
            "Operation timed out; inspect Capstone responsiveness and reattach "
            "if needed."
        ),
    ),
    (
        ("recording session has not been initialized", "recording not initialized"),
        "RECORDING_NOT_INITIALIZED",
        "Initialize recording session before invoking recording operations.",
    ),
    (
        (
            "capstone_attach", "attach to capstone", "not attached",
            "no running capstone",
        ),
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
)


def classify_native_error(error: Exception) -> tuple[str, str]:
    """Return (error_code, remediation) tuple for native worker exceptions."""
    if isinstance(error, NoPatternInterfaceError):
        return (
            "CONTROL_PATTERN_UNAVAILABLE",
            "Inspect the control and choose a supported action.",
        )
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

    if isinstance(error, TimeoutError):
        return (
            "TIMEOUT_ERROR",
            (
                "Operation timed out; inspect Capstone responsiveness and reattach "
                "if needed."
            ),
        )

    lower = str(error).lower()
    if "foreground" in lower or "focus" in lower:
        return (
            "AUTOMATION_ERROR",
            (
                "Bring the intended Capstone window to the foreground and inspect "
                "its current state before retrying; do not change input coordinates."
            ),
        )
    if "control" in lower and ("not found" in lower or "missing" in lower):
        return (
            "CONTROL_NOT_FOUND",
            (
                "Inspect active window controls using capstone_snapshot to find "
                "valid references."
            ),
        )

    fallback = (
        "AUTOMATION_ERROR",
        "Check Capstone application state using capstone_windows and retry.",
    )
    for keywords, code, remediation in _ERROR_RULES:
        if any(re.search(r"\b" + re.escape(kw) + r"\b", lower) for kw in keywords):
            fallback = code, remediation
            break
    return fallback
