# Copyright 2026 Capstone MCP contributors.
"""Tests for typing interruption guard on unexpected popups."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Window


def test_keys_rejects_without_foreground() -> None:
    app = Capstone()
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = app.keys(0, "text", allow_foreground=False)


def test_keys_normal_typing_without_interruption() -> None:
    app = Capstone()
    mock_ctrl = MagicMock()
    app.focus_window = MagicMock(return_value=mock_ctrl)
    app.windows = MagicMock(return_value=[
        Window(
            handle=100, title="Capstone", process_id=1,
            bounds=Bounds(left=0, top=0, right=800, bottom=600),
        ),
    ])

    result = app.keys(100, "NormalText", unicode_input=True)

    assert result.delivered is True
    assert result.interrupted is False
    assert result.popup_window is None
    assert mock_ctrl.type_keys.call_count == 10  # 10 characters


def test_keys_interrupted_by_popup_window() -> None:
    app = Capstone()
    mock_ctrl = MagicMock()
    app.focus_window = MagicMock(return_value=mock_ctrl)

    initial_win = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=800, bottom=600),
    )
    popup_win = Window(
        handle=200, title="InsertMeasMenu", process_id=1,
        bounds=Bounds(left=200, top=200, right=400, bottom=500),
    )

    # Simulate: after 3 characters ('a', 'b', '['), popup appears
    call_count = 0

    def fake_windows() -> list[Window]:
        nonlocal call_count
        if call_count >= 3:
            return [initial_win, popup_win]
        return [initial_win]

    def on_type_keys(*_args: object, **_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1

    mock_ctrl.type_keys.side_effect = on_type_keys
    app.windows = fake_windows

    # We send "ab[remaining"
    result = app.keys(100, "ab[remaining", unicode_input=True)

    assert result.delivered is True
    assert result.interrupted is True
    assert result.typed_text == "ab["
    assert result.popup_window is not None
    assert result.popup_window.handle == 200
    assert result.popup_window.title == "InsertMeasMenu"
    # Typing must have halted at 3 characters!
    assert call_count == 3

