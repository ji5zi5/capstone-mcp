# Copyright 2026 Capstone MCP contributors.
"""Native graph parsing, saved graph reads, and fit catalog coverage."""

import re
from pathlib import Path
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from mcp.server.fastmcp import FastMCP

from capstone_mcp.graphs import (
    FIT_ROWS,
    FIT_TYPES,
    FitModel,
    GraphAction,
    GraphRequest,
    GraphStateError,
    ReadGraphRequest,
    parse_graph_xml,
)
from capstone_mcp.tools.displays import register_display_tools


def _fit(
    native_type: int,
    name: str,
    *,
    status: int = 0,
    descriptor_indices: tuple[int, int] = (1, 0),
) -> str:
    first_index, second_index = descriptor_indices
    return f"""
    <ZRSCurveFit ZCFDICurveFitType="{native_type}"
      ZCFDICurveFitName="{name}" ZCFDICurveFitExpresson="mIndex + b"
      ZCFDICurveFitCurveFitErrorStatus="{status}"
      ZCFDICurveFitCountOfParameters="2"
      ZCFDICurveFitCountOfParameterDescriptions="2"
      ZCFDICurveFitCountOfResults="2">
      <ZCFDICurveFitParameterDescriptionDefinition
        ZCFDICurveFitParameterAbbreviation="m"
        ZCFDICurveFitParameterDescriptionIndexToActual="{first_index}" />
      <ZCFDICurveFitParameterDescriptionDefinition
        ZCFDICurveFitParameterAbbreviation="b"
        ZCFDICurveFitParameterDescriptionIndexToActual="{second_index}" />
      <ZCFDICurveFitParameterDefinition
        ZCFDICurveFitParameterResultValue="-32.618866666666662"
        ZCFDICurveFitParameterFitGoodness="29.305441439449968"
        ZCFDICurveParameterIsLocked="0" />
      <ZCFDICurveFitParameterDefinition
        ZCFDICurveFitParameterResultValue="15.004985714285713"
        ZCFDICurveFitParameterFitGoodness="7.5249426910060349"
        ZCFDICurveParameterIsLocked="1" />
      <ZCFDICurveFitResultsDefinition
        ZCFDICurveFitResultsName="Correlation Coefficient"
        ZCFDICurveFitResultsAbbreviation="r"
        ZCFDICurveFitResultsValue="0.70604963011341959"
        ZCFDICurveFitResultsValidity="1" />
      <ZCFDICurveFitResultsDefinition
        ZCFDICurveFitResultsName="Unused stale metric"
        ZCFDICurveFitResultsAbbreviation="stale"
        ZCFDICurveFitResultsValue="999"
        ZCFDICurveFitResultsValidity="0" />
    </ZRSCurveFit>
    """


def _renderer(
    renderer_id: str,
    *,
    source_id: str,
    dataset_id: str,
    unit: str | None,
    fits: str,
) -> str:
    adapter = (
        ""
        if unit is None
        else f'<DataAdapter ConverterConverterUnit="{unit}" />'
    )
    return f"""
    <ZRSIndividualRenederer ZTDDRUniqueId="{renderer_id}">
      <BundleInput BundleIndex="0" BundleMeasID="{source_id}"
        BundleDataSetID="{dataset_id}">{adapter}</BundleInput>
      <RenderSet><Plot>{fits}</Plot></RenderSet>
    </ZRSIndividualRenederer>
    """


def _payload(
    body: str = "",
    *,
    state: str = "TRUE",
    selections: tuple[int, ...] = (1,),
) -> bytes:
    checked = "".join(
        f'<LineGraphCurveFitChecked LineGraphCurveFitType="{native_type}" />'
        for native_type in selections
    )
    return f"""
    <PasteRoot>
      <WorkbookItem GUID="CSLineGraph">
        <CSLineGraph LineGraphSavedCurveFitTypeNotMenuIndex="1">
          <LineGraphCurveFitSelections LineGraphCurveFitState="{state}">
            {checked}
          </LineGraphCurveFitSelections>
          <GraphPlot><RendererSet>{body}</RendererSet></GraphPlot>
        </CSLineGraph>
      </WorkbookItem>
    </PasteRoot>
    """.encode()


@pytest.mark.parametrize("converter_first", [True, False])
def test_bundle_unit_is_independent_of_other_data_adapters(*, converter_first: bool) -> None:
    converter = '<DataAdapter DataAdapterType="1003" DataAdapterRank="50" ConverterConverterUnit="1536" />'
    adapter = '<DataAdapter DataAdapterType="1002" DataAdapterRank="10" />'
    children = converter + adapter if converter_first else adapter + converter
    renderer = _renderer("r", source_id="channel", dataset_id="run", unit=None, fits="")
    xml = _payload(renderer.replace("</BundleInput>", children + "</BundleInput>"))
    binding = parse_graph_xml(xml).series[0].inputs[0]
    assert (binding.source_id, binding.dataset_id, binding.unit_id) == ("channel", "run", 1536)


def test_bundle_rejects_ambiguous_unit_converters() -> None:
    renderer = _renderer("r", source_id="channel", dataset_id="run", unit="256", fits="")
    xml = _payload(renderer.replace("</BundleInput>", '<DataAdapter ConverterConverterUnit="1536"/></BundleInput>'))
    with pytest.raises(GraphStateError, match="multiple unit converters"):
        parse_graph_xml(xml)


def test_failed_fit_can_omit_unavailable_result_values() -> None:
    fit = re.sub(
        r'\s+(?:ZCFDICurveFitParameterResultValue|ZCFDICurveFitParameterFitGoodness|ZCFDICurveFitResultsValue)="[^"]*"',
        "", _fit(1, "Linear", status=10),
    )
    state = parse_graph_xml(_payload(_renderer(
        "renderer", source_id="x", dataset_id="run", unit="0", fits=fit,
    )))
    native = state.series[0].fits[0]
    assert native.error_status == 10
    assert all(p.value is None and p.uncertainty is None for p in native.parameters)
    assert all(m.value is None and not m.valid for m in native.metrics)


def test_successful_fit_still_requires_result_values() -> None:
    fit = re.sub(r'\s+ZCFDICurveFitParameterResultValue="[^"]*"', "", _fit(1, "Linear"))
    with pytest.raises(GraphStateError, match="missing attribute"):
        _ = parse_graph_xml(_payload(_renderer(
            "renderer", source_id="x", dataset_id="run", unit="0", fits=fit,
        )))
@pytest.mark.anyio
async def test_manage_graph_reads_saved_workbook_without_native_worker(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workbook.cap"
    first = _payload(selections=(0,)).split(b"<PasteRoot>")[1].split(b"</PasteRoot>")[0]
    second = first.replace(b'LineGraphCurveFitType="0"', b'LineGraphCurveFitType="1"')
    with ZipFile(path, "x") as archive:
        archive.writestr(
            "main.xml",
            b"<DSProExperiment><Workspace>"
            + first + second + b"</Workspace></DSProExperiment>",
        )
    native = AsyncMock(side_effect=AssertionError("Archive reads must bypass native IPC"))
    read_graph_tool = register_display_tools(FastMCP("saved-graph-test"), native)[
        "capstone_manage_graph"
    ]

    with pytest.raises(GraphStateError, match="contains 2 graphs"):
        _ = await read_graph_tool(GraphRequest(
            action=GraphAction.READ, read=ReadGraphRequest(cap_file=str(path)),
        ))
    result = await read_graph_tool(GraphRequest(
        action=GraphAction.READ,
        read=ReadGraphRequest(cap_file=str(path), graph_index=1, allow_foreground=False),
    ))

    assert result.read is not None
    assert result.read.state.selected_types == [1]
    assert result.read.cap_file == str(path)
    assert result.read.graph_index == 1
    assert result.read.graph_count == 2
    native.assert_not_awaited()


def test_catalog_matches_native_rows_and_excludes_user_defined() -> None:
    # Given
    native_types = [
        0, 1, 21, 2, 18, 3, 4, 23, 5, 24, 6, 7,
        8, 9, 10, 11, 12, 13, 14, 20, 22, 15, 19,
    ]
    # When
    choices = list(FitModel)
    # Then
    assert [FIT_TYPES[model] for model in choices] == native_types
    assert [model.value for model in choices] == [
        "proportional", "linear", "weighted_linear", "quadratic", "cubic",
        "polynomial", "power", "inverse_no_offset", "inverse",
        "inverse_square_no_offset", "inverse_square", "inverse_power",
        "natural_exponential", "natural_logarithm", "base10_exponential",
        "base10_logarithm", "inverse_exponential", "sine", "sine_series",
        "damped_sine", "cosine_squared", "gaussian", "normalized_gaussian",
    ]
    assert {
        native_type: row
        for row, native_type in enumerate([*native_types, 16])
    } == FIT_ROWS


def test_parse_preserves_native_values_and_descriptor_order() -> None:
    # Given
    xml = _payload(
        _renderer(
            "renderer-a", source_id="x", dataset_id="run", unit="0",
            fits=_fit(1, "Linear"),
        ),
    )
    # When
    state = parse_graph_xml(xml)
    # Then
    assert state.fit_enabled is True
    assert state.selected_types == [1]
    series = state.series[0]
    assert series.renderer_id == "renderer-a"
    assert series.inputs[0].model_dump() == {
        "index": 0, "source_id": "x", "dataset_id": "run", "unit_id": 0,
    }
    fit = series.fits[0]
    assert (fit.native_type, fit.name, fit.expression, fit.error_status) == (
        1, "Linear", "mIndex + b", 0,
    )
    assert [parameter.name for parameter in fit.parameters] == ["m", "b"]
    assert [parameter.value for parameter in fit.parameters] == [
        "15.004985714285713", "-32.618866666666662",
    ]
    assert [parameter.uncertainty for parameter in fit.parameters] == [
        "7.5249426910060349", "29.305441439449968",
    ]
    assert [parameter.locked for parameter in fit.parameters] == [True, False]
    assert fit.metrics[0].value == "0.70604963011341959"
    assert fit.metrics[0].valid is True
    assert fit.metrics[1].value is None
    assert fit.metrics[1].valid is False


def test_multiple_models_and_renderers_remain_associated() -> None:
    # Given
    xml = _payload(
        _renderer(
            "first", source_id="x", dataset_id="run-a", unit=None,
            fits=_fit(1, "Linear") + _fit(2, "Quadratic"),
        )
        + _renderer(
            "second", source_id="y", dataset_id="run-b", unit="2048",
            fits=_fit(15, "Gaussian"),
        ),
        selections=(1, 2, 15),
    )
    # When
    state = parse_graph_xml(xml)
    # Then
    assert [series.renderer_id for series in state.series] == ["first", "second"]
    assert [[fit.name for fit in series.fits] for series in state.series] == [
        ["Linear", "Quadratic"], ["Gaussian"],
    ]
    assert [series.inputs[0].dataset_id for series in state.series] == [
        "run-a", "run-b",
    ]
    assert [series.inputs[0].unit_id for series in state.series] == [None, 2048]


@pytest.mark.parametrize("status", [0, 1, 2, 3])
def test_all_native_convergence_statuses_preserve_results(status: int) -> None:
    # Given: native nonlinear solvers report success using statuses 1..3 too.
    xml = _payload(_renderer(
        "converged", source_id="x", dataset_id="run", unit="0",
        fits=_fit(2, "Quadratic", status=status),
    ))
    # When
    fit = parse_graph_xml(xml).series[0].fits[0]
    # Then
    assert fit.parameters[0].value == "15.004985714285713"
    assert fit.metrics[0].valid


@pytest.mark.parametrize("status", [-1, 4, 7, 10, 11, 12, 99])
def test_failed_fit_hides_stale_numerical_results(status: int) -> None:
    # Given
    xml = _payload(
        _renderer(
            "failed", source_id="x", dataset_id="run", unit="0",
            fits=_fit(1, "Linear", status=status),
        ),
    )
    # When
    fit = parse_graph_xml(xml).series[0].fits[0]
    # Then
    assert fit.error_status == status
    assert all(parameter.value is None for parameter in fit.parameters)
    assert all(parameter.uncertainty is None for parameter in fit.parameters)
    assert all(metric.value is None and not metric.valid for metric in fit.metrics)


def test_empty_new_graph_is_legitimate() -> None:
    # Given
    xml = _payload("", state="FALSE", selections=())
    # When
    state = parse_graph_xml(xml)
    # Then
    assert state.fit_enabled is False
    assert state.selected_types == []
    assert state.series == []


def test_legacy_menu_indices_are_not_mistaken_for_native_types() -> None:
    # Given: row 21 means Gaussian, but native type 21 means Weighted Linear.
    xml = _payload(selections=(21,)).replace(
        b'LineGraphSavedCurveFitTypeNotMenuIndex="1"',
        b'LineGraphSavedCurveFitTypeNotMenuIndex="0"',
    )
    # When / Then
    with pytest.raises(GraphStateError):
        _ = parse_graph_xml(xml)


def test_existing_user_expression_can_be_read_without_editing_it() -> None:
    # Given: custom models serialize their expression under a different key.
    fit = _fit(16, "User Defined").replace(
        'ZCFDICurveFitExpresson="mIndex + b"',
        'ZCFDICurveFitUserExpression="a*x+b"',
    )
    xml = _payload(_renderer(
        "custom", source_id="x", dataset_id="run", unit="0", fits=fit,
    ), selections=(16,))
    # When
    state = parse_graph_xml(xml)
    # Then
    assert state.series[0].fits[0].expression == "a*x+b"
    assert state.selected_types == [16]


@pytest.mark.parametrize(
    "xml",
    [
        b"<PasteRoot>",
        b"""<!DOCTYPE PasteRoot [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
        <PasteRoot>&xxe;</PasteRoot>""",
        _payload(_renderer(
            "bad", source_id="x", dataset_id="run", unit="0",
            fits=_fit(1, "Linear", descriptor_indices=(1, 1)),
        )),
        _payload().replace(
            b'LineGraphCurveFitState="TRUE"',
            b'LineGraphCurveFitState="MAYBE"',
        ),
        _payload().replace(b'GUID="CSLineGraph"', b'GUID="Other"'),
    ],
)
def test_invalid_or_unsafe_graph_xml_fails_closed(xml: bytes) -> None:
    # Given / When / Then
    with pytest.raises(GraphStateError):
        _ = parse_graph_xml(xml)


def test_declared_counts_and_required_fit_fields_are_enforced() -> None:
    # Given
    fit = _fit(1, "Linear").replace(
        'ZCFDICurveFitCountOfParameters="2"',
        'ZCFDICurveFitCountOfParameters="3"',
    )
    missing_expression = _fit(1, "Linear").replace(
        ' ZCFDICurveFitExpresson="mIndex + b"', "",
    )
    # When / Then
    with pytest.raises(GraphStateError):
        _ = parse_graph_xml(_payload(_renderer(
            "count", source_id="x", dataset_id="run", unit="0", fits=fit,
        )))
    with pytest.raises(GraphStateError):
        _ = parse_graph_xml(_payload(_renderer(
            "field", source_id="x", dataset_id="run", unit="0",
            fits=missing_expression,
        )))


def test_multiple_workbook_items_or_graphs_are_refused() -> None:
    # Given
    workbook = _payload().decode().split("<PasteRoot>", 1)[1].rsplit(
        "</PasteRoot>", 1,
    )[0]
    multiple_workbooks = f"<PasteRoot>{workbook}{workbook}</PasteRoot>".encode()
    extra_graph = b"".join([
        b'<CSLineGraph LineGraphSavedCurveFitTypeNotMenuIndex="1">',
        b'<LineGraphCurveFitSelections LineGraphCurveFitState="TRUE" />',
        b"</CSLineGraph></WorkbookItem>",
    ])
    multiple_graphs = _payload().replace(b"</WorkbookItem>", extra_graph)
    # When / Then
    with pytest.raises(GraphStateError):
        _ = parse_graph_xml(multiple_workbooks)
    with pytest.raises(GraphStateError):
        _ = parse_graph_xml(multiple_graphs)
