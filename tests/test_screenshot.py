# Copyright 2026 Capstone MCP contributors.
"""Capture preconditions without changing the user's desktop."""

from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest
import win32gui
from PIL import Image, ImageGrab

from capstone_mcp.desktop import AutomationError, Capstone

if TYPE_CHECKING:
    from pywinauto.controls.uiawrapper import UIAWrapper


def _app(monkeypatch: pytest.MonkeyPatch, *, minimized: bool) -> Capstone:
    app = Capstone()
    window = cast("UIAWrapper", Mock(handle=123))
    monkeypatch.setattr(app, "window", Mock(return_value=window))
    monkeypatch.setattr(win32gui, "IsIconic", Mock(return_value=minimized))
    return app


def test_minimized_capture_reports_restore_instruction_without_grabbing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, minimized=True)
    grab = Mock()
    monkeypatch.setattr(ImageGrab, "grab", grab)
    with pytest.raises(AutomationError, match=r"minimized.*Restore"):
        _ = app.screenshot(123)
    grab.assert_not_called()


def test_capture_returns_png_for_exact_validated_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, minimized=False)
    grab = Mock(return_value=Image.new("RGB", (2, 2)))
    monkeypatch.setattr(ImageGrab, "grab", grab)
    assert app.screenshot(123).startswith(b"\x89PNG\r\n\x1a\n")
    grab.assert_called_once_with(window=123)


def test_capture_failure_preserves_cause_and_actionable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(monkeypatch, minimized=False)
    error = OSError("screen grab failed")
    monkeypatch.setattr(ImageGrab, "grab", Mock(side_effect=error))
    with pytest.raises(AutomationError, match="interactive desktop") as exc:
        _ = app.screenshot(123)
    assert exc.value.__cause__ is error


def test_capture_rejects_foreign_window_before_reading_its_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Capstone()
    monkeypatch.setattr(app, "windows", Mock(return_value=[]))
    iconic = Mock()
    grab = Mock()
    monkeypatch.setattr(win32gui, "IsIconic", iconic)
    monkeypatch.setattr(ImageGrab, "grab", grab)
    with pytest.raises(AutomationError, match="attached Capstone"):
        _ = app.screenshot(123)
    iconic.assert_not_called()
    grab.assert_not_called()
