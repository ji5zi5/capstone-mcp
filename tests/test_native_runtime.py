# Copyright 2026 Capstone MCP contributors.
"""Unit tests verifying decomposed native runtime and error classification."""

from __future__ import annotations

from capstone_mcp.graphs import GraphFailure, GraphOperationError
from capstone_mcp.native.errors import classify_native_error


def test_classify_native_error_graph_failure() -> None:
    """Verify classification of GraphOperationError."""
    failure = GraphFailure(
        code="UNVERIFIED_GRAPH_STATE",
        operation="select_graph_measurement",
        stage="select_measurement",
        completed_steps=[],
        graph_input_may_have_been_sent=True,
        next_action="read_graph",
        detail="Graph state unverified",
    )
    error = GraphOperationError(failure)
    code, rem = classify_native_error(error)
    assert code == "UNVERIFIED_GRAPH_STATE"
    assert "capstone_manage_graph" in rem


def test_classify_native_error_control_missing() -> None:
    """Verify classification of missing control error."""
    error = RuntimeError("Control Palette.ObjNameRecord not found")
    code, rem = classify_native_error(error)
    assert code == "CONTROL_NOT_FOUND"
    assert "capstone_snapshot" in rem


def test_classify_native_error_session_unattached() -> None:
    """Verify classification of unattached session error."""
    error = RuntimeError("Session not attached to any running Capstone")
    code, rem = classify_native_error(error)
    assert code == "SESSION_NOT_ATTACHED"
    assert "capstone_attach" in rem


def test_classify_native_error_timeout() -> None:
    """Verify classification of timeout error."""
    error = TimeoutError("Wait for condition time exceeded")
    code, rem = classify_native_error(error)
    assert code == "TIMEOUT_ERROR"
    assert "responsiveness" in rem


def test_classify_native_error_fallback() -> None:
    """Verify fallback classification for unknown exceptions."""
    error = ZeroDivisionError("Unexpected math failure")
    code, rem = classify_native_error(error)
    assert code == "AUTOMATION_ERROR"
    assert "capstone_windows" in rem
