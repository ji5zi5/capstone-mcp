# Copyright 2026 Capstone MCP contributors.
"""Read a real installed experiment through an actual MCP subprocess."""

import sys
from decimal import Decimal
from pathlib import Path
from typing import Final

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import Field, JsonValue

from capstone_mcp.analysis import LinearFit
from capstone_mcp.capfile_models import CapDatasetPage, CapDatasetSummary
from capstone_mcp.graphs import FitModel, GraphFailure
from capstone_mcp.models import Model

ROOT: Final = str(Path(__file__).resolve().parents[1])
EXAMPLE: Final = (
    "C:/Program Files/PASCO scientific/Capstone/Resources/Templates/QuickStart/"
    "Conservation of Momentum.cap"
)


class DatasetList(Model):
    result: list[CapDatasetSummary]


class FitChoices(Model):
    result: list[FitModel]


class RequestDefinition(Model):
    additional_properties: bool | None = Field(
        default=None, alias="additionalProperties",
    )
    properties: dict[str, JsonValue] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    enum: list[str] = Field(default_factory=list)


class RecoveryResult(Model):
    result: GraphFailure


class GraphToolSchema(Model):
    definitions: dict[str, RequestDefinition] = Field(alias="$defs")


async def exercise_file_tools() -> None:
    # Given: a real installed example, never modified by this test.
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "capstone_mcp.server"], cwd=ROOT,
    )
    with anyio.fail_after(45):
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            _ = await session.initialize()
            listed = await session.call_tool(
                "capstone_file_datasets", {"path": EXAMPLE},
            )
            assert not listed.isError
            datasets = DatasetList.model_validate(listed.structuredContent).result
            selected = next(d for d in datasets if d.name == "Init. Red v")
            # When: request only two values beginning at the third sample.
            extracted = await session.call_tool("capstone_extract_dataset", {
                "path": EXAMPLE, "dataset_index": selected.index,
                "offset": 2, "limit": 2,
            })
            # Then: actual values and indices match the stored example.
            assert not extracted.isError
            page = CapDatasetPage.model_validate(extracted.structuredContent)
            assert page.dataset.count == 6
            assert page.sample_indices == [2, 3]
            assert page.raw_values == ["0.434", "0.565"]
            assert page.numeric_values == [Decimal("0.434"), Decimal("0.565")]


async def exercise_fit_tool() -> None:
    # Given
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "capstone_mcp.server"], cwd=ROOT,
    )
    with anyio.fail_after(30):
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            _ = await session.initialize()
            # When
            response = await session.call_tool("capstone_linear_fit", {
                "samples": {"x": [0, 1, 2], "y": [1, 3, 5]},
            })
            # Then
            assert not response.isError
            fit = LinearFit.model_validate(response.structuredContent)
            assert fit.slope == 2
            assert fit.intercept == 1


@pytest.mark.skipif(
    not Path(EXAMPLE).exists(),
    reason=f"Capstone sample file not installed: {EXAMPLE}",
)
def test_saved_sample_extraction_over_mcp() -> None:
    anyio.run(exercise_file_tools)


def test_linear_fit_over_mcp() -> None:
    anyio.run(exercise_fit_tool)


async def exercise_ai_graph_contract() -> None:
    # Given: actual MCP metadata, without attaching to or changing a desktop.
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "capstone_mcp.server"], cwd=ROOT,
    )
    with anyio.fail_after(30):
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            _ = await session.initialize()
            listed = await session.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            graph_tool = tools["capstone_manage_graph"]
            assert graph_tool.annotations is not None
            assert graph_tool.annotations.destructiveHint is False
            schema = GraphToolSchema.model_validate(graph_tool.inputSchema)
            graph_req = schema.definitions["GraphRequest"]
            assert "action" in graph_req.required
            assert "create" in graph_req.properties
            assert "fit" in graph_req.properties
            assert "select_measurement" in graph_req.properties
            assert "analyze" in graph_req.properties
            fit_models = schema.definitions["FitModel"]
            assert FitModel.QUADRATIC.value in fit_models.enum

            # When: call manage_graph with invalid action
            invalid = await session.call_tool("capstone_manage_graph", {
                "request": {
                    "action": "invented_invalid_action",
                },
            })
            # Then: reject the invalid request before native app input.
            assert invalid.isError


def test_ai_graph_contract_over_mcp() -> None:
    anyio.run(exercise_ai_graph_contract)
