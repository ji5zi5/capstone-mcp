# Copyright 2026 Capstone MCP contributors.
"""Maturity and protocol contract tests for instrument workflows and error envelopes."""

import json
from unittest.mock import patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ServerResult,
)

from capstone_mcp import server
from capstone_mcp.desktop import AutomationError
from capstone_mcp.models import ToolErrorPayload
from capstone_mcp.server import (
    format_tool_error,
    hardware_setup_workflow,
)


def test_hardware_setup_workflow_prompt_defaults() -> None:
    """Verify hardware_setup_workflow renders complete guidance with default arguments."""
    text = hardware_setup_workflow()
    assert "850 Universal Interface" in text
    assert "Force Sensor" in text
    assert "100 Hz" in text
    assert "capstone://hardware/inventory" in text
    assert "scan_wireless" in text
    assert "set_sampling_rate" in text
    assert "zero_sensor" in text
    assert "set_signal_generator" in text
    assert "read_signal_generator" in text


def test_hardware_setup_workflow_prompt_custom() -> None:
    """Verify hardware_setup_workflow renders properly with customized arguments."""
    text = hardware_setup_workflow(
        interface_type="550 Universal Interface",
        target_sensor="Motion Sensor",
        sampling_rate="50 Hz",
    )
    assert "550 Universal Interface" in text
    assert "Motion Sensor" in text
    assert "50 Hz" in text
    assert "capstone://hardware/inventory" in text
    assert "sensor_name='Motion Sensor'" in text
    assert "sampling_rate='50 Hz'" in text


def test_hardware_setup_workflow_registered_on_fastmcp() -> None:
    """Verify hardware_setup_workflow prompt is registered on FastMCP."""
    prompts = [p.name for p in server.MCP._prompt_manager.list_prompts()]
    assert "hardware_setup_workflow" in prompts


def test_format_tool_error_instrument_classification() -> None:
    """Verify classification and remediation for instrument and sensor error messages."""
    # Sensor error
    err1 = format_tool_error("Sensor not found in hardware tree: Rotary Motion Sensor")
    assert isinstance(err1, ToolErrorPayload)
    assert err1.error_code == "INSTRUMENT_ERROR"
    assert "capstone://hardware/inventory" in err1.remediation
    assert "capstone_manage_instrument" in err1.remediation

    # Signal generator error
    err2 = format_tool_error("Signal generator output level exceeds 10V limit")
    assert err2.error_code == "INSTRUMENT_ERROR"
    assert "hardware" in err2.remediation.lower()

    # Calibration error
    err3 = format_tool_error("Calibration wizard aborted: standard point out of range")
    assert err3.error_code == "INSTRUMENT_ERROR"
    assert "capstone_manage_instrument" in err3.remediation

    # Hardware connection error
    err4 = format_tool_error("Hardware interface communication lost on COM3")
    assert err4.error_code == "INSTRUMENT_ERROR"
    assert "capstone://hardware/inventory" in err4.remediation


@pytest.mark.anyio
async def test_instrument_mcp_request_handler_structured_error() -> None:
    """Verify unattached instrument tool calls return structured CallToolResult(isError=True)."""
    handler = server.MCP._mcp_server.request_handlers[CallToolRequest]

    # Call capstone_manage_instrument when Capstone session is unattached
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="capstone_manage_instrument",
            arguments={
                "request": {
                    "action": "zero_sensor",
                    "sensor_name": "Force Sensor",
                },
            },
        ),
    )
    res = await handler(req)

    assert isinstance(res, ServerResult)
    tool_result = res.root
    assert isinstance(tool_result, CallToolResult)
    assert tool_result.isError is True
    assert tool_result.content is not None
    assert len(tool_result.content) == 1

    payload_dict = json.loads(tool_result.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
    assert "error_code" in payload_dict
    assert "message" in payload_dict
    assert "remediation" in payload_dict
    assert payload_dict["error_code"] == "SESSION_NOT_ATTACHED"


@pytest.mark.anyio
async def test_instrument_fastmcp_call_tool_raises_structured_tool_error() -> None:
    """Verify MCP.call_tool raises ToolError containing structured JSON payload."""
    with pytest.raises(ToolError) as exc_info:
        await server.MCP.call_tool(
            "capstone_manage_instrument",
            {
                "request": {
                    "action": "zero_sensor",
                    "sensor_name": "Force Sensor",
                },
            },
        )

    err_text = str(exc_info.value)
    data = json.loads(err_text)
    assert data["error_code"] == "SESSION_NOT_ATTACHED"
    assert "remediation" in data
    assert "message" in data


@pytest.mark.anyio
async def test_instrument_simulated_automation_error_envelope() -> None:
    """Verify simulated instrument AutomationError results in INSTRUMENT_ERROR envelope."""
    handler = server.MCP._mcp_server.request_handlers[CallToolRequest]

    with (
        patch.object(
            server.WORKER,
            "call",
            side_effect=AutomationError("Sensor not detected on analog channel A"),
        ),
    ):
        req = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="capstone_manage_instrument",
                arguments={
                    "request": {
                        "action": "zero_sensor",
                        "sensor_name": "Force Sensor",
                    },
                },
            ),
        )
        res = await handler(req)

        assert isinstance(res, ServerResult)
        tool_result = res.root
        assert isinstance(tool_result, CallToolResult)
        assert tool_result.isError is True

        payload_dict = json.loads(tool_result.content[0].text)  # pyright: ignore[reportAttributeAccessIssue]
        assert payload_dict["error_code"] == "INSTRUMENT_ERROR"
        assert "Sensor not detected" in payload_dict["message"]
        assert "capstone://hardware/inventory" in payload_dict["remediation"]
