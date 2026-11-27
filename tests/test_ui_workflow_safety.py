# Copyright 2026 Capstone MCP contributors.
"""Offline regressions for unsafe UI target selection and false verification."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp import file_workflows
from capstone_mcp.desktop import AutomationError
from capstone_mcp.displays.digits import (
    _extract_digits_value_and_unit,
    _find_measurement_selector,
)
from capstone_mcp.displays.harness import find_display_container, set_control_value
from capstone_mcp.displays.models import SetScopeTriggerRequest
from capstone_mcp.displays.scope import _write_settings, set_scope_trigger
from capstone_mcp.displays.table import _find_add_column_button, _find_column_headers
from capstone_mcp.displays.workbook import (
    _find_add_page_button,
    _find_layout_template_control,
)
from capstone_mcp.graphs import inspection
from capstone_mcp.graphs.toolbox import _parse_delta
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.runs import (
    DeleteRunRequest,
    RenameRunRequest,
    SetRunVisibilityRequest,
)
from capstone_mcp.runs.manager import (
    delete_run,
    rename_run,
    set_run_visibility,
)


def _control(name: str, kind: str = "Pane", *, ref: str = "target", aid: str = "") -> Control:
    return Control(ref=ref, parent=None, name=name, control_type=kind,
                   automation_id=aid, enabled=True, visible=True,
                   bounds=Bounds(left=0, top=0, right=100, bottom=100))


def _snapshot(controls: list[Control]) -> Snapshot:
    return Snapshot(window=Window(handle=1, title="Capstone", process_id=1,
                    bounds=Bounds(left=0, top=0, right=800, bottom=600)),
                    controls=controls, truncated=False)


def test_digits_selector_never_chooses_close_button() -> None:
    container = _control("Digits")
    close = _control("Close", "Button", ref="close")
    assert _find_measurement_selector([container, close], container) is None


def test_delete_column_toolbar_button_is_not_a_header() -> None:
    table = _control("Table", "Table")
    delete = _control("Delete Column", "Button", ref="delete")
    assert _find_column_headers([table, delete], table) == []


def test_add_column_does_not_expand_into_neighbor_table() -> None:
    table = _control("Table", "Table")
    neighbor = _control("Add Column", "Button", ref="add").model_copy(
        update={"bounds": Bounds(left=110, top=0, right=140, bottom=30)},
    )
    assert _find_add_column_button([table, neighbor], table) is None


@pytest.mark.parametrize("name", [None, "1"])
def test_unrelated_panes_are_not_display_targets(name: str | None) -> None:
    ribbon = _control("Ribbon", aid="ribbon123")
    with pytest.raises(AutomationError, match="uniquely"):
        find_display_container([ribbon], "digits", name)


def test_multiple_displays_require_exact_target() -> None:
    with pytest.raises(AutomationError, match="Multiple"):
        find_display_container([_control("Digits 1"), _control("Digits 2")], "digits")


def test_zoom_plus_is_not_add_page() -> None:
    with pytest.raises(AutomationError, match="Add Page"):
        _find_add_page_button([_control("+", "Button")])


@pytest.mark.parametrize("name", ["grid", "gridlines", "template30"])
def test_ambiguous_layout_keywords_are_not_selected(name: str) -> None:
    with pytest.raises(AutomationError, match="Layout template"):
        _find_layout_template_control([_control(name, "Button", aid=name)], "four_grid")


def test_value_fallback_types_literal_shortcut_metacharacters() -> None:
    app = MagicMock()
    app.control.return_value.iface_value = None
    set_control_value(app, 1, _control("Input", "Edit"), "a+{b}^%")
    app.type_text.assert_called_once_with("a+{b}^%")
    assert [call.args[1] for call in app.keys.call_args_list] == ["^a{BACKSPACE}", "{ENTER}"]


def test_popup_selector_without_value_pattern_is_not_clicked() -> None:
    app = MagicMock()
    app.control.return_value.iface_value = None
    with pytest.raises(AutomationError, match="Value pattern"):
        set_control_value(app, 1, _control("Select Measurement", "Button"), "Voltage")
    app.click.assert_not_called()
    app.keys.assert_not_called()


def test_scope_timebase_cannot_modify_global_timestamp_control() -> None:
    app = MagicMock()
    app.snapshot.return_value = _snapshot([
        _control("Scope"), _control("Timestamp", "Edit", aid="global.time"),
    ])
    with pytest.raises(AutomationError, match="writable timebase"):
        _write_settings(app, app.snapshot.return_value, _control("Scope"), ((("timebase",), "2 ms/div"),))
    app.control.assert_not_called()


def test_collapsed_scope_trigger_is_not_verified_or_mutated() -> None:
    app = MagicMock()
    app.snapshot.return_value = _snapshot([_control("Scope")])
    with pytest.raises(AutomationError, match="identifiable Scope"):
        set_scope_trigger(app, SetScopeTriggerRequest(handle=1))
    app.control.assert_not_called()


def test_unicode_minus_digits_are_numeric() -> None:
    container = _control("Digits")
    value = _control("\u221212.5 V", "Text", ref="value")
    assert _extract_digits_value_and_unit([container, value], container) == (-12.5, "V")


def test_delta_coordinates_can_occupy_separate_labels() -> None:
    values = _parse_delta([_control("(1, 2)", "Text"), _control("(4, 6)", "Text")])
    assert values[:6] == (3.0, 4.0, 1.0, 2.0, 4.0, 6.0)


def test_delta_does_not_guess_among_three_crosshair_coordinates() -> None:
    values = _parse_delta([_control(f"({n}, {n})", "Text") for n in range(3)])
    assert values[:6] == (None,) * 6


def test_run_rename_rejects_multiline_before_snapshot() -> None:
    app = MagicMock()
    with pytest.raises(AutomationError, match="new_name"):
        rename_run(app, RenameRunRequest(new_name="one\ntwo", old_name="Run 1"))
    app.snapshot.assert_not_called()


def test_delete_requires_explicit_identity_and_observes_removal() -> None:
    app = MagicMock()
    run = _control("시행 하나", "TreeItem")
    app.snapshot.side_effect = [_snapshot([run]), _snapshot([])]
    with pytest.raises(AutomationError, match="by name"):
        delete_run(app, DeleteRunRequest(handle=1, run_name="시행 하나"))
    app.click.assert_not_called()


def test_visibility_does_not_fabricate_requested_state() -> None:
    app = MagicMock()
    app.snapshot.return_value = _snapshot([_control("실험 A", "CheckBox")])
    app.control.return_value.iface_toggle.CurrentToggleState = 0
    result = set_run_visibility(app, SetRunVisibilityRequest(handle=1, runs=["실험 A"]))
    assert not result.verified
    assert result.visible_runs == []
    app.control.return_value.iface_toggle.Toggle.assert_called_once()


def test_visibility_refreshes_references_between_mutations() -> None:
    app = MagicMock()
    states = {"실험 A": 0, "실험 B": 0}
    generation = 0

    def snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal generation
        generation += 1
        return _snapshot([_control(name, "CheckBox", ref=f"{generation}:{name}")
                          for name in states])

    def control(ref: str) -> MagicMock:
        epoch, name = ref.split(":")
        assert int(epoch) == generation, "stale snapshot reference"
        node = MagicMock()
        node.iface_toggle.CurrentToggleState = states[name]
        node.iface_toggle.Toggle.side_effect = lambda: states.update({name: 1})
        return node

    app.snapshot.side_effect = snapshot
    app.control.side_effect = control
    result = set_run_visibility(app, SetRunVisibilityRequest(handle=1, runs=list(states)))
    assert result.verified
    assert set(result.visible_runs) == set(states)


def test_clipboard_restore_preserves_newer_external_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    clipboard = MagicMock()
    clipboard.GetClipboardSequenceNumber.return_value = 11
    monkeypatch.setattr(inspection, "win32clipboard", clipboard)
    inspection._restore_clipboard({1: "original"}, copied_sequence=10, owner_handle=37)
    clipboard.EmptyClipboard.assert_not_called()
    clipboard.CloseClipboard.assert_called_once()


def test_empty_clipboard_can_be_restored_without_touching_external_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clipboard = MagicMock()
    clipboard.GetClipboardSequenceNumber.return_value = 10
    monkeypatch.setattr(inspection, "win32clipboard", clipboard)
    inspection._restore_clipboard({}, copied_sequence=10, owner_handle=37)
    clipboard.EmptyClipboard.assert_called_once()


def test_partial_clipboard_restore_attempts_remaining_formats_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clipboard = MagicMock()
    clipboard.GetClipboardSequenceNumber.return_value = 10
    clipboard.SetClipboardData.side_effect = [ValueError("unavailable"), None]
    monkeypatch.setattr(inspection, "win32clipboard", clipboard)
    with pytest.raises(AutomationError, match=r"clipboard formats \[1\]"):
        inspection._restore_clipboard({1: b"a", 13: "a"}, copied_sequence=10, owner_handle=37)
    assert clipboard.SetClipboardData.call_count == 2
    clipboard.CloseClipboard.assert_called_once()


def test_unsupported_clipboard_handle_fails_before_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    clipboard = MagicMock()
    clipboard.EnumClipboardFormats.side_effect = [2, 0]
    clipboard.GetClipboardData.return_value = 12345
    monkeypatch.setattr(inspection, "win32clipboard", clipboard)
    with pytest.raises(AutomationError, match="clipboard format"):
        inspection._backup_clipboard()
    clipboard.EmptyClipboard.assert_not_called()
    clipboard.CloseClipboard.assert_called_once()


def test_file_menu_failure_closes_menu_and_preserves_original_error() -> None:
    app, events = MagicMock(), MagicMock()
    app.windows.return_value = [_snapshot([]).window]
    app.snapshot.return_value = _snapshot([_control("File", "MenuItem")])
    events.changes.until.side_effect = AutomationError("menu timeout")
    app.keys.side_effect = AutomationError("cleanup failure")
    with pytest.raises(AutomationError, match="menu timeout"):
        file_workflows._open_command(app, events, 1, "Export")
    app.keys.assert_called_once_with(1, "{ESC}")


def test_export_cleanup_uses_known_handle_and_current_close_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, events = MagicMock(), MagicMock()
    app.windows.return_value = [_snapshot([]).window]
    close = _control("Close", "Button", ref="fresh-close")
    finder = MagicMock(return_value=close)
    monkeypatch.setattr(file_workflows, "_named_button", finder)
    file_workflows._close_export_dialog(app, events, 1, failing=True)
    finder.assert_called_once_with(app, 1, "STR_CLOSE")
    assert app.act.call_args.args[0] == "fresh-close"


def test_invalid_graph_payload_still_restores_owned_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, events, clipboard = MagicMock(), MagicMock(), MagicMock()
    events.clipboard_handle = 37
    app.windows.return_value = [_snapshot([]).window]
    app.snapshot.return_value = _snapshot([_control("Display", "MenuItem")])
    popup = _snapshot([_control("Copy Display", "MenuItem")])
    events.__enter__.return_value = events
    events.changes.until.side_effect = [popup, (b"invalid XML", 10)]
    clipboard.GetClipboardSequenceNumber.return_value = 5
    restore = MagicMock()
    monkeypatch.setattr(inspection, "WindowEvents", MagicMock(return_value=events))
    monkeypatch.setattr(inspection, "win32clipboard", clipboard)
    monkeypatch.setattr(inspection, "win32gui", MagicMock())
    monkeypatch.setattr(inspection, "win32process", MagicMock())
    monkeypatch.setattr(inspection, "_backup_clipboard", lambda: ({1: "original"}, 5))
    monkeypatch.setattr(inspection, "_restore_clipboard", restore)
    monkeypatch.setattr(inspection, "release_menu_bar", MagicMock())
    with pytest.raises(inspection.GraphStateError):
        inspection.read_graph(app, 1)
    restore.assert_called_once_with({1: "original"}, copied_sequence=10, owner_handle=37)


def test_export_cleanup_failure_reports_original_error_and_unresolved_dialog() -> None:
    app, events = MagicMock(), MagicMock()
    app.windows.return_value = [_snapshot([]).window]
    app.snapshot.side_effect = AutomationError("blocked by child dialog")

    def fail_and_cleanup() -> None:
        try:
            msg = "export timed out"
            raise AutomationError(msg)
        finally:
            file_workflows._close_export_dialog(app, events, 1, failing=True)

    with pytest.raises(AutomationError, match=r"export timed out.*unresolved native") as error:
        fail_and_cleanup()
    assert "blocked by child dialog" in str(error.value)
    assert isinstance(error.value.__cause__, AutomationError)
    app.act.assert_not_called()


def test_truncated_file_dialog_cannot_prove_unique_target() -> None:
    snapshot = _snapshot([_control("Save", "Button")]).model_copy(update={"truncated": True})
    with pytest.raises(AutomationError, match="truncated"):
        file_workflows._one(snapshot, lambda c: c.name == "Save")
