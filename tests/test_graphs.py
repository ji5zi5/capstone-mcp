# Copyright 2026 Capstone MCP contributors.
"""Unified test suite for the deep Graph domain module and manage_graph seam."""

from unittest.mock import MagicMock, patch

import pytest

from capstone_mcp.desktop import AutomationError
from capstone_mcp.graphs import (
    AnalyzeGraphRequest,
    CreateGraphRequest,
    FitGraphRequest,
    GraphAction,
    GraphAnalysisReport,
    GraphDeltaRequest,
    GraphFitOutcome,
    GraphRequest,
    GraphState,
    MeasureGraphAreaRequest,
    ReadGraphRequest,
    SelectMeasurementRequest,
    SetGraphFitsRequest,
    ToggleGraphStatisticsRequest,
    manage_graph,
)
from capstone_mcp.models import Bounds, Control, Point, Snapshot, Window


def _make_control(
    ref: str = "ref:1",
    name: str = "Graph",
    control_type: str = "Custom",
    bounds: Bounds | None = None,
    parent: str | None = None,
) -> Control:
    return Control(
        ref=ref,
        name=name,
        control_type=control_type,
        automation_id="aid:1",
        bounds=bounds or Bounds(left=100, top=100, right=500, bottom=400),
        enabled=True,
        visible=True,
        parent=parent,
    )


def _make_window(handle: int = 10) -> Window:
    return Window(
        handle=handle,
        title="PASCO Capstone",
        process_id=100,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_manage_graph_create_action() -> None:
    # Given: Capstone snapshot with Graph display palette item
    graph_palette = _make_control(
        ref="ref:palette_graph",
        name="Graph",
        control_type="Text",
    )
    app = MagicMock()
    app.snapshot.return_value = Snapshot(
        window=_make_window(10),
        controls=[graph_palette],
        depth=12,
        limit=800,
        truncated=False,
    )
    node_mock = MagicMock()
    app.control.return_value = node_mock

    # When: execute CREATE action
    result = manage_graph(
        app,
        GraphRequest(
            action=GraphAction.CREATE,
            create=CreateGraphRequest(handle=10, allow_foreground=True),
        ),
    )

    # Then:
    assert result.action == GraphAction.CREATE
    assert result.create is not None
    assert result.create.verified is True
    assert "Graph inserted" in result.create.detail
    app.click.assert_called_once_with(
        10,
        "ref:palette_graph",
        allow_foreground=True,
    )


def test_manage_graph_fit_action() -> None:
    # Given: Target graph in snapshot
    graph_ctrl = _make_control(
        ref="ref:graph1",
        name="Graph 1",
        control_type="Custom",
        bounds=Bounds(left=50, top=50, right=600, bottom=400),
    )
    app = MagicMock()
    app.snapshot.return_value = Snapshot(
        window=_make_window(10),
        controls=[graph_ctrl],
        depth=16,
        limit=10_000,
        truncated=False,
    )

    # When: execute FIT action (scale_to_fit)
    result = manage_graph(
        app,
        GraphRequest(
            action=GraphAction.FIT,
            fit=FitGraphRequest(handle=10, mode="scale_to_fit"),
        ),
    )

    # Then:
    assert result.action == GraphAction.FIT
    assert result.fit is not None
    assert result.fit.verified is True
    assert result.fit.mode == "scale_to_fit"
    app.click_point.assert_called_once()


def test_manage_graph_toolbox_statistics_action() -> None:
    # Given: Target graph and statistics button/box in snapshot
    graph_ctrl = _make_control(
        ref="ref:graph1",
        name="Graph 1",
        control_type="Custom",
        bounds=Bounds(left=50, top=50, right=600, bottom=400),
    )
    sigma_btn = _make_control(
        ref="ref:sigma_btn",
        name="Statistics",
        control_type="Button",
        bounds=Bounds(left=60, top=60, right=80, bottom=80),
    )
    stat_text = _make_control(
        ref="ref:stat_text",
        name="Mean = 5.23\nStd. Dev. = 0.42\nSamples = 100",
        control_type="Text",
        bounds=Bounds(left=100, top=100, right=250, bottom=180),
    )
    app = MagicMock()
    app.snapshot.return_value = Snapshot(
        window=_make_window(10),
        controls=[graph_ctrl, sigma_btn, stat_text],
        depth=16,
        limit=10_000,
        truncated=False,
    )
    node_mock = MagicMock()
    app.control.return_value = node_mock

    # When: execute TOOLBOX_STATISTICS action
    result = manage_graph(
        app,
        GraphRequest(
            action=GraphAction.TOOLBOX_STATISTICS,
            toolbox_statistics=ToggleGraphStatisticsRequest(handle=10, enable=True),
        ),
    )

    # Then:
    assert result.action == GraphAction.TOOLBOX_STATISTICS
    assert result.toolbox_statistics is not None
    assert result.toolbox_statistics.visible is True
    assert result.toolbox_statistics.statistics is not None
    assert result.toolbox_statistics.statistics.mean == 5.23
    assert result.toolbox_statistics.statistics.std_dev == 0.42
    assert result.toolbox_statistics.statistics.count == 100


def test_manage_graph_toolbox_delta_action() -> None:
    # Given: Graph and delta tool in snapshot
    graph_ctrl = _make_control(
        ref="ref:graph1",
        name="Graph 1",
        control_type="Custom",
        bounds=Bounds(left=50, top=50, right=600, bottom=400),
    )
    delta_btn = _make_control(
        ref="ref:delta_btn",
        name="Delta",
        control_type="Button",
        bounds=Bounds(left=60, top=60, right=80, bottom=80),
    )
    delta_box = _make_control(
        ref="ref:delta_box",
        name="Δx = 1.25 s, Δy = 3.40 m",
        control_type="Text",
        bounds=Bounds(left=150, top=150, right=300, bottom=200),
    )
    app = MagicMock()
    app.snapshot.return_value = Snapshot(
        window=_make_window(10),
        controls=[graph_ctrl, delta_btn, delta_box],
        depth=16,
        limit=10_000,
        truncated=False,
    )
    node_mock = MagicMock()
    app.control.return_value = node_mock

    # When: execute TOOLBOX_DELTA action
    result = manage_graph(
        app,
        GraphRequest(
            action=GraphAction.TOOLBOX_DELTA,
            toolbox_delta=GraphDeltaRequest(handle=10),
        ),
    )

    # Then:
    assert result.action == GraphAction.TOOLBOX_DELTA
    assert result.toolbox_delta is not None
    assert result.toolbox_delta.visible is True
    assert result.toolbox_delta.dx == 1.25
    assert result.toolbox_delta.dy == 3.40


def test_manage_graph_toolbox_area_action() -> None:
    # Given: Graph and area tool in snapshot
    graph_ctrl = _make_control(
        ref="ref:graph1",
        name="Graph 1",
        control_type="Custom",
        bounds=Bounds(left=50, top=50, right=600, bottom=400),
    )
    area_btn = _make_control(
        ref="ref:area_btn",
        name="Area",
        control_type="Button",
        bounds=Bounds(left=60, top=60, right=80, bottom=80),
    )
    area_box = _make_control(
        ref="ref:area_box",
        name="Area = 14.85 N·s",
        control_type="Text",
        bounds=Bounds(left=150, top=150, right=300, bottom=200),
    )
    app = MagicMock()
    app.snapshot.return_value = Snapshot(
        window=_make_window(10),
        controls=[graph_ctrl, area_btn, area_box],
        depth=16,
        limit=10_000,
        truncated=False,
    )
    node_mock = MagicMock()
    app.control.return_value = node_mock

    # When: execute TOOLBOX_AREA action
    result = manage_graph(
        app,
        GraphRequest(
            action=GraphAction.TOOLBOX_AREA,
            toolbox_area=MeasureGraphAreaRequest(handle=10),
        ),
    )

    # Then:
    assert result.action == GraphAction.TOOLBOX_AREA
    assert result.toolbox_area is not None
    assert result.toolbox_area.visible is True
    assert result.toolbox_area.area == 14.85
    assert result.toolbox_area.unit == "N·s"


def test_manage_graph_read_action() -> None:
    app = MagicMock()
    mock_state = GraphState(fit_enabled=True, selected_types=[], series=[])
    with patch("capstone_mcp.graphs.manager.read_graph", return_value=mock_state):
        result = manage_graph(
            app,
            GraphRequest(
                action=GraphAction.READ,
                read=ReadGraphRequest(handle=10, allow_foreground=True),
            ),
        )
        assert result.action == GraphAction.READ
        assert result.read is not None
        assert result.read.state.fit_enabled is True
        assert result.read.verified is True


def test_manage_graph_select_measurement_action() -> None:
    app = MagicMock()
    mock_res = MagicMock(detail="Selected ['Time (s)']; ok.")
    with patch(
        "capstone_mcp.graphs.manager.select_graph_measurement",
        return_value=mock_res,
    ):
        result = manage_graph(
            app,
            GraphRequest(
                action=GraphAction.SELECT_MEASUREMENT,
                select_measurement=SelectMeasurementRequest(
                    handle=10,
                    point=Point(x=10, y=20),
                    path=["Time (s)"],
                ),
            ),
        )
        assert result.action == GraphAction.SELECT_MEASUREMENT
        assert result.select_measurement is not None
        assert result.select_measurement.verified is True
        assert "Time (s)" in result.select_measurement.detail


def test_manage_graph_analyze_action() -> None:
    app = MagicMock()
    state = GraphState(fit_enabled=True, selected_types=[], series=[])
    mock_outcome = GraphFitOutcome(
        changed=False,
        requested_models=[],
        fits_successful=True,
        before=state,
        after=state,
    )
    mock_report = GraphAnalysisReport(renderers=[], overall_limitations=[])
    with (
        patch("capstone_mcp.graphs.manager.analyze_graph", return_value=mock_outcome),
        patch("capstone_mcp.graphs.manager.summarize_graph", return_value=mock_report),
    ):
        result = manage_graph(
            app,
            GraphRequest(
                action=GraphAction.ANALYZE,
                analyze=AnalyzeGraphRequest(
                    handle=10,
                    fitting=SetGraphFitsRequest(
                        menu_point=Point(x=10, y=20),
                        frame_id="frame:1",
                        models=[],
                    ),
                ),
            ),
        )
        assert result.action == GraphAction.ANALYZE
        assert result.analyze is not None
        assert result.analyze.outcome.fits_successful is True
        assert result.analyze.report is not None


def test_manage_graph_missing_subrequest_raises() -> None:
    app = MagicMock()
    with pytest.raises(AutomationError, match="create request must be provided"):
        manage_graph(app, GraphRequest(action=GraphAction.CREATE))
