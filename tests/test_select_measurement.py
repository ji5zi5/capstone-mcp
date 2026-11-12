# Copyright 2026 Capstone MCP contributors.
"""Tests for atomic popup menu selection tool."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Point, Snapshot, Window
from capstone_mcp.popup_selection import (
    SelectMeasurementRequest,
    select_graph_measurement,
)


def test_select_measurement_rejects_empty_path() -> None:
    app = Capstone()
    req = SelectMeasurementRequest(handle=100, point=Point(x=50, y=50), menu_path=[])
    with pytest.raises(AutomationError, match="at least one item"):
        _ = select_graph_measurement(app, req)


def test_select_measurement_single_item_success() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])

    item_ctrl = Control(
        ref="ref:item1", parent=None, name="Position (m)",
        control_type="MenuItem", automation_id="item_pos", enabled=True,
        visible=True, bounds=Bounds(left=100, top=100, right=200, bottom=130),
    )

    call_count = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal call_count
        call_count += 1
        # First call has menu item, second call (verification) has closed menu
        controls = [item_ctrl] if call_count == 1 else []
        return Snapshot(window=mock_window, controls=controls, truncated=False)

    app.snapshot = mock_snapshot

    clicked_coords: list[tuple[int, int]] = []

    def mock_click_point(_handle: int, x: int, y: int, **_kwargs: object) -> None:
        clicked_coords.append((x, y))

    app.click_point = mock_click_point

    req = SelectMeasurementRequest(
        handle=100,
        point=Point(x=50, y=50),
        menu_path=["Position (m)"],
    )
    res = select_graph_measurement(app, req)

    assert res.selected_item == "Position (m)"
    assert res.traversed_path == ["Position (m)"]
    assert res.verified is True
    # First clicked initial point (50, 50), then center of item (150, 115)
    assert clicked_coords == [(50, 50), (150, 115)]


def test_select_measurement_rolls_back_on_missing_item() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[],
        truncated=False,
    ))

    keys_sent: list[str] = []

    def mock_keys(_handle: int, keys: str, **_kwargs: object) -> None:
        keys_sent.append(keys)

    app.click_point = MagicMock()
    app.keys = mock_keys

    req = SelectMeasurementRequest(
        handle=100,
        point=Point(x=50, y=50),
        menu_path=["Nonexistent Item"],
    )

    with pytest.raises(AutomationError, match="Safe rollback"):
        _ = select_graph_measurement(app, req)

    assert keys_sent == ["{ESC}"]
