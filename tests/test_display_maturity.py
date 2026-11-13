# Copyright 2026 Capstone MCP contributors.
"""Protocol maturity and structured error handling tests for Displays subsystem."""

import json
from unittest.mock import patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolRequest, CallToolRequestParams

from capstone_mcp import server
from capstone_mcp.server import MCP, format_tool_error


def test_display_layout_workflow_prompt_registration() -> None:
    """Verify display_layout_workflow prompt is registered on FastMCP."""
    prompts = {p.name for p in server.MCP._prompt_manager.list_prompts()}
    assert "display_layout_workflow" in prompts


def test_display_layout_workflow_rendered_content() -> None:
    """Verify display_layout_workflow renders instructional guidance with arguments."""
    content_default = server.display_layout_workflow()
    assert "New Analysis" in content_default
    assert "two_vertical" in content_default
    assert "capstone://displays/active" in content_default
    assert "capstone_manage_display" in content_default

    content_custom = server.display_layout_workflow(
        page_title="Spectroscopy",
        layout="four_grid",
        target_measurements="Frequency, Intensity",
    )
    assert "Spectroscopy" in content_custom
    assert "four_grid" in content_custom
    assert "Frequency, Intensity" in content_custom
    assert "create_fft" in content_custom


@pytest.mark.parametrize(
    ("err_msg", "expected_code"),
    [
        ("Table display widget not found in active window.", "DISPLAY_ERROR"),
        ("Digits display creation requires allow_foreground=true.", "DISPLAY_ERROR"),
        ("Oscilloscope display widget not found in active window.", "DISPLAY_ERROR"),
        ("FFT display widget not found in active window.", "DISPLAY_ERROR"),
        ("Add Page button not found in active window.", "DISPLAY_ERROR"),
        ("Failed to apply split layout template 'four_grid'.", "DISPLAY_ERROR"),
        ("Workbook page container missing.", "DISPLAY_ERROR"),
    ],
)
def test_format_tool_error_classifies_display_errors(
    err_msg: str,
    expected_code: str,
) -> None:
    """Verify display-related exceptions map to DISPLAY_ERROR with actionable remediation."""
    payload = format_tool_error(err_msg)
    assert payload.error_code == expected_code
    assert (
        "capstone://displays/active" in payload.remediation
        or "capstone_manage_display" in payload.remediation
    )


@pytest.mark.anyio
async def test_call_tool_wraps_display_error_in_structured_payload() -> None:
    """Verify FastMCP call_tool wraps display exceptions in structured JSON ToolError."""
    req = CallToolRequest(
        params=CallToolRequestParams(
            name="capstone_manage_display",
            arguments={
                "request": {
                    "action": "create_table",
                    "table_name": "Test Table",
                },
            },
        ),
    )

    with patch.object(server.WORKER, "call") as mock_worker_call:
        mock_worker_call.side_effect = RuntimeError(
            "Table display widget not found in active window.",
        )
        with pytest.raises(ToolError) as exc_info:
            await MCP.call_tool(req.params.name, req.params.arguments or {})

    error_str = str(exc_info.value)
    data = json.loads(error_str)
    assert data["error_code"] == "DISPLAY_ERROR"
    assert "Table display widget not found" in data["message"]
    assert "capstone://displays/active" in data["remediation"]
