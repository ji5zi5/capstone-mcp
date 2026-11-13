# Copyright 2026 Capstone MCP contributors.
"""Unit tests for typed IPC error contracts, classification, and DPI awareness."""

from __future__ import annotations

import json

import pytest

from capstone_mcp.automation_models import NativeReply, NativeRequest
from capstone_mcp.automation_worker import AutomationWorker, NativeSessionError
from capstone_mcp.desktop import AutomationError
from capstone_mcp.graphs.models import GraphFailure, GraphOperationError
from capstone_mcp.native_loop import (  # pyright: ignore[reportPrivateUsage]
    _classify_native_error,
)
from capstone_mcp.native_main import init_dpi_awareness
from capstone_mcp.server import ToolErrorPayload, format_tool_error


def test_native_reply_model_includes_error_code_and_remediation() -> None:
    """Verify NativeReply includes error_code and remediation in serialization."""
    reply = NativeReply(
        identifier="req-123",
        error="AutomationError: Control not found",
        error_code="CONTROL_NOT_FOUND",
        remediation=(
            "Inspect active window controls using capstone_snapshot to find "
            "valid references."
        ),
    )
    raw_json = reply.model_dump_json()
    data = json.loads(raw_json)

    assert data["identifier"] == "req-123"
    assert data["error_code"] == "CONTROL_NOT_FOUND"
    assert "capstone_snapshot" in data["remediation"]

    deserialized = NativeReply.model_validate_json(raw_json)
    assert deserialized.error_code == "CONTROL_NOT_FOUND"
    assert deserialized.remediation == reply.remediation


def test_classify_native_error_mappings() -> None:
    """Verify _classify_native_error maps domain exceptions to structured codes."""
    # 1. Session not attached
    c1, r1 = _classify_native_error(
        AutomationError("Attach to Capstone before accessing controls."),
    )
    assert c1 == "SESSION_NOT_ATTACHED"
    assert "capstone_attach" in r1

    # 2. Control not found
    c2, r2 = _classify_native_error(
        AutomationError("Control ref 42 not found in active window"),
    )
    assert c2 == "CONTROL_NOT_FOUND"
    assert "capstone_snapshot" in r2

    # 3. Recording not initialized
    c3, r3 = _classify_native_error(
        AutomationError("Recording session has not been initialized."),
    )
    assert c3 == "RECORDING_NOT_INITIALIZED"
    assert "recording" in r3.lower()

    # 4. Graph operation error
    failure = GraphFailure(
        code="GRAPH_CREATION_FAILED",
        request_id="g-1",
        operation="create_graph",
        stage="validation",
        graph_input_may_have_been_sent=False,
        next_action="inspect_windows",
        detail="No display found",
    )
    c4, r4 = _classify_native_error(GraphOperationError(failure))
    assert c4 == "GRAPH_CREATION_FAILED"
    assert "capstone_manage_graph" in r4

    # 5. Invalid argument / coordinates
    c5, _ = _classify_native_error(
        AutomationError("Coordinates must be inside the current window rectangle."),
    )
    assert c5 == "INVALID_ARGUMENT"

    # 6. Fallback generic automation error
    c6, r6 = _classify_native_error(RuntimeError("Unexpected internal glitch"))
    assert c6 == "AUTOMATION_ERROR"
    assert "capstone_windows" in r6


def test_automation_worker_raises_native_session_error_with_structured_contract() -> (
    None
):
    """Verify worker unpacks error_code and remediation onto NativeSessionError."""
    worker = AutomationWorker()
    reply = NativeReply(
        identifier="req-test",
        error="AutomationError: Control not found: btn_start",
        error_code="CONTROL_NOT_FOUND",
        remediation=(
            "Inspect active window controls using capstone_snapshot to find "
            "valid references."
        ),
    )

    # Mock exchange to return this structured reply
    worker._exchange = lambda _req, _ident: reply  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(NativeSessionError) as exc_info:
        worker.call(NativeRequest(operation="action", ref="10", action="invoke"))

    err = exc_info.value
    assert err.error_code == "CONTROL_NOT_FOUND"
    assert "capstone_snapshot" in (err.remediation or "")


def test_format_tool_error_consumes_native_session_error_directly() -> None:
    """Verify format_tool_error directly extracts payload from NativeSessionError."""
    exc = NativeSessionError(
        "Control not found: btn_run",
        error_code="CONTROL_NOT_FOUND",
        remediation="Use capstone_snapshot to locate control.",
    )
    payload = format_tool_error(exc)
    assert isinstance(payload, ToolErrorPayload)
    assert payload.error_code == "CONTROL_NOT_FOUND"
    assert payload.remediation == "Use capstone_snapshot to locate control."
    assert "Control not found" in payload.message


def test_init_dpi_awareness_safe_execution() -> None:
    """Verify init_dpi_awareness executes without unhandled exception."""
    # Should execute safely on Windows and no-op on non-Windows
    init_dpi_awareness()
