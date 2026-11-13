# Copyright 2026 Capstone MCP contributors.
"""Protocol maturity contract tests for structured errors and workflow prompts."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ServerResult,
)

from capstone_mcp import server
from capstone_mcp.models import ToolErrorPayload
from capstone_mcp.server import (
    data_analysis_workflow,
    format_tool_error,
    run_comparison_workflow,
)


def test_format_tool_error_classification() -> None:
    """Verify classification and remediation suggestions for common error classes."""
    # 1. Unattached session error
    err = format_tool_error("Call capstone_attach first")
    assert isinstance(err, ToolErrorPayload)
    assert err.error_code == "SESSION_NOT_ATTACHED"
    assert "capstone_attach" in err.remediation
    assert "Call capstone_attach first" in err.message

    # 2. Control not found error
    err = format_tool_error("Error executing tool capstone_action: Control not found: btn_start")
    assert err.error_code == "CONTROL_NOT_FOUND"
    assert "capstone_snapshot" in err.remediation
    assert "Control not found" in err.message

    # 3. Graph operation error
    err = format_tool_error("Curve fit failed on graph display: no series found")
    assert err.error_code == "GRAPH_OPERATION_ERROR"
    assert "capstone_manage_graph" in err.remediation

    # 4. File error
    err = format_tool_error("Invalid file path: experiment.capstone not found")
    assert err.error_code == "FILE_NOT_FOUND"
    assert "file path exists" in err.remediation

    # 5. Invalid argument / validation error
    err = format_tool_error("Validation error: value -5 is out of allowed range [0, 100]")
    assert err.error_code == "INVALID_ARGUMENT"
    assert "argument" in err.remediation

    # 6. Timeout error
    err = format_tool_error("Native operation timed out; deadline exceeded")
    assert err.error_code == "TIMEOUT_ERROR"
    assert "timed out" in err.remediation

    # 7. Generic fallback
    err = format_tool_error("Unexpected OS socket interrupt")
    assert err.error_code == "AUTOMATION_ERROR"
    assert "capstone_windows" in err.remediation

    # 8. Preserves pre-structured JSON payload
    raw_payload = json.dumps({
        "error_code": "CUSTOM_ERROR",
        "message": "Custom message",
        "remediation": "Do something specific",
    })
    err = format_tool_error(f"Error executing tool my_tool: {raw_payload}")
    assert err.error_code == "CUSTOM_ERROR"
    assert err.message == "Custom message"
    assert err.remediation == "Do specific" or "Do something specific" in err.remediation


@pytest.mark.anyio
async def test_mcp_request_handler_returns_structured_error_envelope() -> None:
    """Verify MCP protocol handler returns CallToolResult(isError=True) with JSON payload."""
    handler = server.MCP._mcp_server.request_handlers[CallToolRequest]

    # Attempt calling capstone_snapshot without an attached Capstone process
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="capstone_snapshot", arguments={"handle": 12345}),
    )
    res = await handler(req)

    assert isinstance(res, ServerResult)
    tool_result = res.root
    assert isinstance(tool_result, CallToolResult)
    assert tool_result.isError is True
    assert tool_result.content is not None
    assert len(tool_result.content) == 1

    text_content = tool_result.content[0]
    payload_dict = json.loads(text_content.text)
    assert "error_code" in payload_dict
    assert "message" in payload_dict
    assert "remediation" in payload_dict
    assert payload_dict["error_code"] == "SESSION_NOT_ATTACHED"


@pytest.mark.anyio
async def test_fastmcp_call_tool_raises_structured_tool_error() -> None:
    """Verify direct MCP.call_tool raises ToolError with structured JSON."""
    with pytest.raises(ToolError) as exc_info:
        await server.MCP.call_tool("capstone_snapshot", {"handle": 12345})

    err_text = str(exc_info.value)
    data = json.loads(err_text)
    assert data["error_code"] == "SESSION_NOT_ATTACHED"
    assert "remediation" in data
    assert "message" in data


def test_data_analysis_workflow_prompt() -> None:
    """Verify data_analysis_workflow renders complete instructional guidance."""
    # Default parameters
    default_text = data_analysis_workflow()
    assert "data analysis workflow for 'generic'" in default_text
    assert "Linear" in default_text
    assert "capstone_manage_graph" in default_text
    assert "capstone_generate_lab_report" in default_text

    # Custom parameters
    custom_text = data_analysis_workflow(experiment_name="Boyle's Law", fit_model="Inverse")
    assert "data analysis workflow for 'Boyle's Law'" in custom_text
    assert "Inverse" in custom_text
    assert "capstone_windows" in custom_text


def test_run_comparison_workflow_prompt() -> None:
    """Verify run_comparison_workflow renders multi-run comparative guidance."""
    # Default parameters
    default_text = run_comparison_workflow()
    assert "Run #1" in default_text
    assert "Run #2" in default_text
    assert "capstone://runs/active" in default_text
    assert "toolbox_statistics" in default_text
    assert "percentage difference" in default_text

    # Custom parameters
    custom_text = run_comparison_workflow(run1="Trial A", run2="Trial B")
    assert "Trial A" in custom_text
    assert "Trial B" in custom_text
    assert "toolbox_statistics" in custom_text


def test_prompts_registered_on_fastmcp() -> None:
    """Verify prompts are registered and discoverable on FastMCP."""
    prompts = {p.name: p for p in server.MCP._prompt_manager.list_prompts()}
    assert "data_analysis_workflow" in prompts
    assert "run_comparison_workflow" in prompts
    assert "resonance_experiment_workflow" in prompts

    data_prompt = prompts["data_analysis_workflow"]
    assert "data analysis" in data_prompt.description.lower() or "curve fitting" in data_prompt.description.lower()

    comp_prompt = prompts["run_comparison_workflow"]
    assert "comparison" in comp_prompt.description.lower() or "percentage" in comp_prompt.description.lower()
