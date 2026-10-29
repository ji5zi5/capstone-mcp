# Copyright 2026 Capstone MCP contributors.
"""Graph workflows reject unsafe or ambiguous input before changing the page."""

from unittest.mock import Mock

import pytest
import win32gui
import win32process
from pydantic import ValidationError

from capstone_mcp import graph_workflows
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.graph_requests import GraphFitRequest
from capstone_mcp.graph_state import (
    FitModel,
    GraphSeries,
    GraphState,
    NativeFit,
)
from capstone_mcp.graph_workflows import (
    create_graph,
    select_graph_measurement,
    set_graph_fits,
)
from capstone_mcp.models import Bounds, Control, Point, Result, Snapshot, Window


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
        _ = set_graph_fits(
            app, 1, GraphFitRequest(
                frame_id="test-frame",
                menu_point=Point(x=1, y=1), models=[], allow_foreground=False,
            ),
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


@pytest.mark.parametrize(
    ("enabled", "visible", "ready"),
    [(False, True, False), (True, False, False), (True, True, True)],
)
def test_native_menu_is_not_ready_until_entry_is_enabled_and_visible(
    monkeypatch: pytest.MonkeyPatch, *,
    enabled: bool, visible: bool, ready: bool,
) -> None:
    # Given: Qt has created its menu before completing action-state updates.
    app = Capstone()
    bounds = Bounds(left=0, top=0, right=100, bottom=100)
    window = Window(handle=2, title="menu", process_id=1, bounds=bounds)
    snapshot = Snapshot(
        window=window, truncated=False,
        controls=[Control(
            ref="copy", parent=None, name="Copy Display", control_type="MenuItem",
            automation_id="", enabled=enabled, visible=visible, bounds=bounds,
        )],
    )
    monkeypatch.setattr(app, "windows", Mock(return_value=[window]))
    monkeypatch.setattr(app, "snapshot", Mock(return_value=snapshot))
    # When
    observed = graph_workflows.ready_graph_menu(app, {1}, "Copy Display")
    # Then: event-driven callers keep waiting until the entry is usable.
    assert (observed is not None) == ready


def test_disappearing_popup_does_not_hide_the_ready_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a Qt shadow disappeared after window enumeration.
    app = Capstone()
    bounds = Bounds(left=0, top=0, right=100, bottom=100)
    vanished = Window(handle=2, title="", process_id=1, bounds=bounds)
    current = Window(handle=3, title="menu", process_id=1, bounds=bounds)
    snapshot = Snapshot(
        window=current, truncated=False,
        controls=[Control(
            ref="copy", parent=None, name="Copy Display", control_type="MenuItem",
            automation_id="", enabled=True, visible=True, bounds=bounds,
        )],
    )
    monkeypatch.setattr(app, "windows", Mock(return_value=[vanished, current]))
    monkeypatch.setattr(app, "snapshot", Mock(
        side_effect=[AutomationError("popup disappeared"), snapshot],
    ))
    # When / Then: only observation is repeated; no application input is sent.
    assert graph_workflows.ready_graph_menu(app, {1}, "Copy Display") == snapshot


def test_menu_click_does_not_reactivate_the_transient_popup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: activating a Qt popup as a top-level window can dismiss it.
    app = Capstone()
    app.pid = 7
    click = Mock()
    control = Mock(
        rectangle=Mock(return_value=Bounds(left=10, top=20, right=90, bottom=80)),
        click_input=click,
    )
    monkeypatch.setattr(app, "control", Mock(return_value=control))
    focus = Mock()
    monkeypatch.setattr(app, "focus_window", focus)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", Mock(return_value=1))
    monkeypatch.setattr(
        win32process, "GetWindowThreadProcessId", Mock(return_value=(1, 7)),
    )
    # When
    graph_workflows.invoke_graph_menu(app, "menu")
    # Then: click the actual item without changing popup activation.
    focus.assert_not_called()
    click.assert_called_once_with(
        button="left", coords=(50, 50), absolute=True,
    )


def test_menu_click_stops_when_another_application_takes_focus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = Capstone()
    app.pid = 7
    lookup = Mock()
    monkeypatch.setattr(app, "control", lookup)
    monkeypatch.setattr(win32gui, "GetForegroundWindow", Mock(return_value=1))
    monkeypatch.setattr(
        win32process, "GetWindowThreadProcessId", Mock(return_value=(1, 99)),
    )
    # When / Then
    with pytest.raises(AutomationError):
        graph_workflows.invoke_graph_menu(app, "menu")
    lookup.assert_not_called()


def _fit_state(types: list[int], *, error_status: int = 0) -> GraphState:
    return GraphState(
        fit_enabled=True, selected_types=types,
        series=[GraphSeries(
            renderer_id="run-1", inputs=[],
            fits=[
                NativeFit(
                    native_type=kind, name=str(kind), expression="native",
                    error_status=error_status, parameters=[], metrics=[],
                )
                for kind in types
            ],
        )],
    )


def test_model_set_changes_only_difference_and_repeat_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a native-state fake, with actual state transitions at the UI seam.
    state = _fit_state([1])
    changes: list[int] = []

    def read_graph(
        _app: Capstone, _handle: int, *, allow_foreground: bool = True,
    ) -> GraphState:
        assert allow_foreground
        return state

    def toggle(
        _app: Capstone, _handle: int, _point: Point, native_type: int,
    ) -> Result:
        nonlocal state
        changes.append(native_type)
        state = _fit_state(sorted(set(state.selected_types) ^ {native_type}))
        return Result(detail="native state changed")

    monkeypatch.setattr(graph_workflows, "read_graph", read_graph)
    monkeypatch.setattr(graph_workflows, "_toggle_fit", toggle)
    request = GraphFitRequest(
        frame_id="test-frame",
        menu_point=Point(x=10, y=20),
        models=[FitModel.LINEAR, FitModel.QUADRATIC],
    )
    # When: apply the same desired state twice.
    first = set_graph_fits(Capstone(), 1, request)
    repeated = set_graph_fits(Capstone(), 1, request)
    # Then: quadratic is added once; linear is never toggled away.
    assert changes == [2]
    assert first.changed
    assert not repeated.changed
    assert repeated.after.selected_types == [1, 2]
    assert repeated.fits_successful


def test_unconfirmed_model_change_stops_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: delivered input that did not change native state.
    monkeypatch.setattr(graph_workflows, "read_graph", Mock(
        return_value=_fit_state([1]),
    ))
    toggle = Mock(return_value=Result(detail="delivered"))
    monkeypatch.setattr(graph_workflows, "_toggle_fit", toggle)
    request = GraphFitRequest(
        frame_id="test-frame",
        menu_point=Point(x=10, y=20), models=[FitModel.QUADRATIC],
    )
    # When / Then: no second click or compensating input is sent.
    with pytest.raises(AutomationError):
        _ = set_graph_fits(Capstone(), 1, request)
    assert toggle.call_count == 1


def test_selected_model_with_native_fit_error_is_not_numerical_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the desired model is selected, but Capstone reports a fit failure.
    monkeypatch.setattr(graph_workflows, "read_graph", Mock(
        return_value=_fit_state([1], error_status=7),
    ))
    request = GraphFitRequest(
        frame_id="test-frame",
        menu_point=Point(x=10, y=20), models=[FitModel.LINEAR],
    )
    # When
    result = set_graph_fits(Capstone(), 1, request)
    # Then
    assert not result.changed
    assert not result.fits_successful
    assert result.after.series[0].fits[0].error_status == 7
    assert result.next_action == "inspect_fit_status"


def test_stale_data_signature_prevents_fit_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the graph selection changed after the AI inspected it.
    original = _fit_state([1])
    changed = GraphState(
        fit_enabled=True, selected_types=[1],
        series=[GraphSeries(renderer_id="different-run", inputs=[], fits=[])],
    )
    monkeypatch.setattr(
        graph_workflows, "read_graph", Mock(return_value=changed),
    )
    toggle = Mock()
    monkeypatch.setattr(graph_workflows, "_toggle_fit", toggle)
    request = GraphFitRequest(
        frame_id="test-frame",
        menu_point=Point(x=10, y=20), models=[FitModel.QUADRATIC],
        expected_data_signature=original.data_signature,
    )
    # When / Then: an outdated plan cannot modify the newly selected run.
    with pytest.raises(AutomationError):
        _ = set_graph_fits(Capstone(), 1, request)
    toggle.assert_not_called()


def test_data_signature_survives_model_changes() -> None:
    # Given / When: only the selected fits changed, not their input bindings.
    before = _fit_state([1])
    after = _fit_state([1, 2])
    # Then: repeating the same guarded request remains valid.
    assert before.data_signature == after.data_signature


def test_misspelled_graph_request_keys_are_rejected() -> None:
    # Given: silently ignoring this typo would remove existing models.
    request = {
        "frame_id": "test-frame",
        "menu_point": {"x": 10, "y": 20}, "models": ["linear"],
        "preserve_existing_models": True,
    }
    # When / Then: the AI must resolve the contract instead of guessing an option.
    with pytest.raises(ValidationError):
        _ = GraphFitRequest.model_validate(request)
