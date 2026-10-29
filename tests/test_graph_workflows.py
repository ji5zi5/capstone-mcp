# Copyright 2026 Capstone MCP contributors.
"""Graph workflows reject unsafe or ambiguous input before changing the page."""

from unittest.mock import Mock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.graph_workflows import (
    create_graph,
    select_graph_measurement,
    toggle_linear_fit,
)
from capstone_mcp.models import Bounds, Control, Point, Snapshot, Window


def test_create_graph_refuses_disabled_foreground() -> None:
    app = Capstone()
    with pytest.raises(AutomationError):
        _ = create_graph(app, 1, allow_foreground=False)
    assert app.pid is None


def test_axis_selection_refuses_disabled_foreground() -> None:
    app = Capstone()
    with pytest.raises(AutomationError):
        _ = select_graph_measurement(
            app, 1, Point(x=1, y=1), ["Index"], allow_foreground=False,
        )
    assert app.pid is None


def test_fit_refuses_disabled_foreground() -> None:
    app = Capstone()
    with pytest.raises(AutomationError):
        _ = toggle_linear_fit(
            app, 1, Point(x=1, y=1), allow_foreground=False,
        )
    assert app.pid is None


@pytest.mark.parametrize("path", [[], [""], ["Constants", ""]])
def test_invalid_measurement_path_never_opens_axis(path: list[str]) -> None:
    app = Capstone()
    with pytest.raises(AutomationError):
        _ = select_graph_measurement(app, 1, Point(x=1, y=1), path)
    assert app.pid is None


@pytest.mark.parametrize("count", [0, 2])
def test_graph_creation_rejects_missing_or_ambiguous_palette(
    monkeypatch: pytest.MonkeyPatch, count: int,
) -> None:
    app = Capstone()
    bounds = Bounds(left=0, top=0, right=100, bottom=100)
    snapshot = Snapshot(
        window=Window(handle=1, title="scratch", process_id=1, bounds=bounds),
        controls=[
            Control(
                ref=str(index), parent=None, name="Graph", control_type="Text",
                automation_id="", enabled=True, visible=True, bounds=bounds,
            )
            for index in range(count)
        ],
        truncated=False,
    )
    monkeypatch.setattr(app, "snapshot", Mock(return_value=snapshot))
    focus = Mock()
    monkeypatch.setattr(app, "focus_window", focus)
    with pytest.raises(AutomationError):
        _ = create_graph(app, 1)
    focus.assert_not_called()
