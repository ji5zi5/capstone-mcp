# Copyright 2026 Capstone MCP contributors.
"""Tests for IDA-informed graph axis scale to fit tool."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.graphs import FitGraphRequest, fit_graph
from capstone_mcp.models import Bounds, Control, Point, Snapshot, Window


def test_fit_graph_rejects_unsupported_mode() -> None:
    app = Capstone()
    req = FitGraphRequest(handle=100, mode="invalid_mode")
    with pytest.raises(AutomationError, match="Unsupported mode"):
        _ = fit_graph(app, req)


def test_fit_graph_raises_when_graph_not_found() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=800, bottom=600),
    )
    app.windows = MagicMock(return_value=[mock_window])
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[
            Control(
                ref="ref:btn", parent=None, name="Record",
                control_type="Button", automation_id="record_btn", enabled=True,
                visible=True, bounds=Bounds(left=10, top=10, right=50, bottom=30),
            ),
        ],
        truncated=False,
    ))

    req = FitGraphRequest(handle=100, mode="scale_to_fit", graph_name="Missing Graph")
    with pytest.raises(AutomationError, match="Target graph control not found"):
        _ = fit_graph(app, req)


def test_fit_graph_scale_to_fit_success() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])

    graph_control = Control(
        ref="ref:graph1", parent=None, name="Graph 1",
        control_type="Custom", automation_id="graph_display_0", enabled=True,
        visible=True, bounds=Bounds(left=100, top=100, right=800, bottom=600),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[graph_control],
        truncated=False,
    ))

    clicked_coords: list[tuple[int, int]] = []

    def mock_click_point(_handle: int, x: int, y: int, **_kwargs: object) -> None:
        clicked_coords.append((x, y))

    app.click_point = mock_click_point

    req = FitGraphRequest(handle=100, mode="scale_to_fit", graph_name="Graph 1")
    res = fit_graph(app, req)

    assert res.mode == "scale_to_fit"
    assert res.target_ref == "ref:graph1"
    assert res.clicked_point == (120, 120)
    assert clicked_coords == [(120, 120)]
    assert res.verified is True


def test_fit_graph_with_custom_offsets() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])

    graph_control = Control(
        ref="ref:graph1", parent=None, name="Graph Display",
        control_type="Pane", automation_id="graph_pane", enabled=True,
        visible=True, bounds=Bounds(left=200, top=150, right=700, bottom=550),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[graph_control],
        truncated=False,
    ))

    clicked_coords: list[tuple[int, int]] = []

    def mock_click_point(_handle: int, x: int, y: int, **_kwargs: object) -> None:
        clicked_coords.append((x, y))

    app.click_point = mock_click_point

    req = FitGraphRequest(
        handle=100,
        mode="scale_to_fit",
        graph_name="Graph Display",
        offset=Point(x=28, y=24),
    )
    res = fit_graph(app, req)

    assert res.clicked_point == (228, 174)
    assert clicked_coords == [(228, 174)]
    assert res.verified is True
