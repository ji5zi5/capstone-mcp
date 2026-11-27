# Copyright 2026 Capstone MCP contributors.
"""Unit tests verifying eradication of 1st-class runtime hazards in Phase 11 Ticket 1."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from capstone_mcp.desktop import AutomationError, Capstone, find_capstone_executable
from capstone_mcp.displays.harness import set_control_value
from capstone_mcp.graphs.inspection import _backup_clipboard, _restore_clipboard
from capstone_mcp.instruments.wireless import _extract_sensor_info
from capstone_mcp.models import Action, Bounds, Control
from capstone_mcp.repetition import RepeatPlan
from capstone_mcp.reports.generator import (
    _load_data_from_file_or_string,
    generate_report,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_find_capstone_executable_respects_env_var(tmp_path: Path) -> None:
    """Verify find_capstone_executable prioritizes CAPSTONE_EXECUTABLE."""
    fake_exe = tmp_path / "CustomCapstone.exe"
    fake_exe.touch()
    with patch.dict(os.environ, {"CAPSTONE_EXECUTABLE": str(fake_exe)}):
        resolved = find_capstone_executable()
        assert resolved == fake_exe


@pytest.mark.parametrize("kind", ["relative", "directory", "text", "missing"])
def test_executable_override_rejects_invalid_paths(tmp_path: Path, kind: str) -> None:
    path = tmp_path / ("program.txt" if kind == "text" else "program.exe")
    if kind == "directory":
        path.mkdir()
    elif kind == "text":
        path.touch()
    value = "program.exe" if kind == "relative" else str(path)
    with (
        patch.dict(os.environ, {"CAPSTONE_EXECUTABLE": value}),
        pytest.raises(ValueError, match=r"absolute \.exe file"),
    ):
        _ = find_capstone_executable()


def test_capstone_click_and_type_text_methods_exist() -> None:
    """Verify Capstone class defines click and type_text methods."""
    app = Capstone()
    assert hasattr(app, "click")
    assert hasattr(app, "type_text")

    with patch.object(app, "act") as mock_act:
        app.click(1234, "ref-test")
        mock_act.assert_called_once_with(
            "ref-test", Action.INVOKE, allow_foreground=True, double=False,
        )


def test_wireless_sensor_disconnected_not_evaluated_as_connected() -> None:
    """Verify sensor with 'Disconnected' in name is correctly marked connected=False."""
    ctrl = Control(
        ref="w-1",
        parent=None,
        name="Wireless Force Acceleration Sensor (Disconnected)",
        control_type="ListItem",
        automation_id="Sensor_Disconnected_42",
        enabled=True,
        visible=True,
        bounds=Bounds(left=0, top=0, right=100, bottom=50),
    )
    info = _extract_sensor_info(ctrl)
    assert info.connected is False
    assert "Disconnected" in info.name


def test_wireless_sensor_connected_evaluated_accurately() -> None:
    """Verify sensor with 'Connected' in name is marked connected=True."""
    ctrl = Control(
        ref="w-2",
        parent=None,
        name="Wireless Pressure Sensor Connected",
        control_type="ListItem",
        automation_id="Sensor_Connected_10",
        enabled=True,
        visible=True,
        bounds=Bounds(left=0, top=0, right=100, bottom=50),
    )
    info = _extract_sensor_info(ctrl)
    assert info.connected is True


def test_repetition_plan_debug_port_defaults_to_9222() -> None:
    """Verify RepeatPlan debug_port defaults to standard 9222."""
    plan = RepeatPlan(
        process_id=100,
        window_handle=200,
        duration_seconds=5.0,
    )
    assert plan.debug_port == 9222


def test_reports_generator_raises_file_not_found_on_missing_file() -> None:
    """Verify _load_data_from_file_or_string raises FileNotFoundError for non-existent path."""
    with pytest.raises(FileNotFoundError, match="Experiment data file does not exist"):
        _load_data_from_file_or_string("non_existent_experiment.cap")

    with pytest.raises(FileNotFoundError, match="Experiment data file does not exist"):
        generate_report(file_path_or_run="non_existent_path.csv")


def test_reports_generator_raises_value_error_for_empty_data() -> None:
    """Verify generate_report refuses to silently invent fake data for empty input."""
    with pytest.raises(ValueError, match="No experimental data provided"):
        generate_report(file_path_or_run=None, experiment_id="generic")


def test_harness_set_control_text_uses_literal_typing() -> None:
    """Verify shortcut syntax is never used to type arbitrary values."""
    app = MagicMock()
    ctrl = Control(
        ref="c-1",
        parent=None,
        name="FormulaEdit",
        control_type="Edit",
        automation_id="Formula",
        enabled=True,
        visible=True,
        bounds=Bounds(left=0, top=0, right=100, bottom=30),
    )
    app.control.return_value = MagicMock(iface_value=None)
    set_control_value(app, 1234, ctrl, "x = 42")
    app.type_text.assert_called_once_with("x = 42")


@pytest.mark.parametrize("sequence", [10, 11])
def test_clipboard_restores_only_its_own_copy(sequence: int) -> None:
    with patch("capstone_mcp.graphs.inspection.win32clipboard") as clipboard:
        clipboard.GetClipboardSequenceNumber.return_value = sequence

        _restore_clipboard({13: "previous text"}, copied_sequence=10, owner_handle=37)

        clipboard.OpenClipboard.assert_called_once_with(37)
        clipboard.CloseClipboard.assert_called_once()
        if sequence == 10:
            clipboard.EmptyClipboard.assert_called_once()
            clipboard.SetClipboardData.assert_called_once_with(13, "previous text")
        else:
            clipboard.EmptyClipboard.assert_not_called()
            clipboard.SetClipboardData.assert_not_called()


def test_clipboard_refuses_a_format_it_cannot_restore() -> None:
    with patch("capstone_mcp.graphs.inspection.win32clipboard") as clipboard:
        clipboard.EnumClipboardFormats.side_effect = [13, 2, 0]
        clipboard.GetClipboardData.return_value = "previous text"
        with pytest.raises(AutomationError, match="clipboard format"):
            _backup_clipboard()

        clipboard.CloseClipboard.assert_called_once()
        clipboard.EmptyClipboard.assert_not_called()


def test_clipboard_restores_an_empty_clipboard() -> None:
    with patch("capstone_mcp.graphs.inspection.win32clipboard") as clipboard:
        clipboard.GetClipboardSequenceNumber.return_value = 99

        _restore_clipboard({}, copied_sequence=99, owner_handle=37)

        clipboard.EmptyClipboard.assert_called_once()
        clipboard.SetClipboardData.assert_not_called()
