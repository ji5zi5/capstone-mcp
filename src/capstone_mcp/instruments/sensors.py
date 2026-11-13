# Copyright 2026 Capstone MCP contributors.
"""Sensor selection, sampling-rate traversal, and zero/tare automation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

from capstone_mcp.acquisition import observe_recording
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.instruments.models import (
    SamplingRateRequest,
    SamplingRateSelection,
    SensorSelection,
    SensorSelectionRequest,
    ZeroSensorRequest,
    ZeroSensorResult,
    _RateControls,
    _Settings,
)
from capstone_mcp.models import Action, Control, Snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# 1. Internal Helpers for Sampling Rate Controls
# ---------------------------------------------------------------------------


def _unique_suffix(snapshot: Snapshot, suffix: str) -> Control:
    controls = [
        control for control in snapshot.controls
        if control.visible and control.automation_id.endswith(suffix)
    ]
    if len(controls) != 1:
        msg = f"No unique visible control ending in {suffix}."
        raise AutomationError(msg)
    return controls[0]


def _settings(app: Capstone, handle: int) -> _Settings:
    recording, _ = observe_recording(app, handle)
    if recording.recording:
        msg = "Stop recording before changing sensor settings."
        raise AutomationError(msg)
    snapshot = app.snapshot(handle, 16, 10_000)
    selector = _unique_suffix(snapshot, ".SamplingRateTargetSelector")
    if recording.sampling_rate_display is None:
        msg = "The current sampling rate is not visible."
        raise AutomationError(msg)
    return _Settings(
        sensor=selector.name,
        sampling_rate=recording.sampling_rate_display,
    )


def _rate_controls(
    app: Capstone, handle: int, expected_sensor: str,
) -> _RateControls:
    recording, _ = observe_recording(app, handle)
    if recording.recording:
        msg = "Stop recording before changing sensor settings."
        raise AutomationError(msg)
    snapshot = app.snapshot(handle, 16, 10_000)
    selector = _unique_suffix(snapshot, ".SamplingRateTargetSelector")
    if selector.name != expected_sensor:
        msg = "Selected sampling sensor does not match the requested sensor."
        raise AutomationError(msg)
    increase = _unique_suffix(snapshot, ".IncreaseSampleRateButton")
    decrease = _unique_suffix(snapshot, ".DecreaseSampleRateButton")
    label = _unique_suffix(snapshot, ".SamplingRateLabel")
    return _RateControls(
        display=label.name,
        increase_ref=increase.ref,
        increase_enabled=increase.enabled,
        decrease_ref=decrease.ref,
        decrease_enabled=decrease.enabled,
    )


def _close_menu(
    app: Capstone, handle: int, popup_handles: set[int], *,
    allow_foreground: bool,
) -> None:
    _ = app.keys(handle, "{ESC}", allow_foreground=allow_foreground)
    visible_handles = {window.handle for window in app.windows()}
    if popup_handles & visible_handles:
        msg = "Sensor menu remained open after Escape; inspect Capstone."
        raise AutomationError(msg)


def _sensor_result(
    requested: str, before: _Settings, after: _Settings,
) -> SensorSelection:
    return SensorSelection(
        requested_sensor=requested, before_sensor=before.sensor,
        after_sensor=after.sensor, before_sampling_rate=before.sampling_rate,
        after_sampling_rate=after.sampling_rate,
        changed=before.sensor != after.sensor,
    )


# ---------------------------------------------------------------------------
# 2. Public Sensor Selection & Sampling Rate Operations
# ---------------------------------------------------------------------------


def select_sensor(
    app: Capstone, handle: int, request: SensorSelectionRequest,
) -> SensorSelection:
    """Select one unique menu item by exact observed name and verify the result."""
    before = _settings(app, handle)
    if before.sensor == request.sensor:
        return _sensor_result(request.sensor, before, before)

    before_handles = {window.handle for window in app.windows()}
    snapshot = app.snapshot(handle, 16, 10_000)
    selector = _unique_suffix(snapshot, ".SamplingRateTargetSelector")
    if not selector.enabled:
        msg = "The sampling sensor selector is unavailable."
        raise AutomationError(msg)
    _ = app.act(
        selector.ref, Action.INVOKE,
        allow_foreground=request.allow_foreground,
    )

    popup_handles = {
        window.handle for window in app.windows()
        if window.handle not in before_handles
    }
    menu_handles: list[int] = []
    for popup_handle in popup_handles:
        popup = app.snapshot(popup_handle, 4, 256)
        if any(
            control.visible and control.control_type == "MenuItem"
            for control in popup.controls
        ):
            menu_handles.append(popup_handle)
    if len(menu_handles) != 1:
        _close_menu(
            app, handle, popup_handles,
            allow_foreground=request.allow_foreground,
        )
        msg = "No unique Capstone sensor menu appeared."
        raise AutomationError(msg)

    menu = app.snapshot(menu_handles[0], 4, 256)
    matches = [
        control for control in menu.controls
        if control.visible
        and control.control_type == "MenuItem"
        and control.name == request.sensor
    ]
    if len(matches) != 1 or not matches[0].enabled:
        _close_menu(
            app, handle, popup_handles,
            allow_foreground=request.allow_foreground,
        )
        msg = "Requested sensor name is unavailable or not unique."
        raise AutomationError(msg)
    _ = app.act(
        matches[0].ref, Action.INVOKE,
        allow_foreground=request.allow_foreground,
    )
    after = _settings(app, handle)
    if after.sensor != request.sensor:
        msg = "Requested sensor was not selected after input delivery."
        raise AutomationError(msg)
    return _sensor_result(request.sensor, before, after)


def _step_rate(
    app: Capstone, handle: int, request: SamplingRateRequest,
    direction: Literal["increase", "decrease"], before: _RateControls,
) -> _RateControls:
    """Click one step from the controls just observed and return the new ones."""
    match direction:
        case "increase":
            ref, enabled = before.increase_ref, before.increase_enabled
        case "decrease":
            ref, enabled = before.decrease_ref, before.decrease_enabled
    if not enabled:
        msg = f"The {direction} sampling-rate step is unavailable."
        raise AutomationError(msg)
    _ = app.act(ref, Action.INVOKE, allow_foreground=request.allow_foreground)
    after = _rate_controls(app, handle, request.sensor)
    if after.display == before.display:
        msg = "Sampling-rate input was delivered but the display did not change."
        raise AutomationError(msg)
    return after


def _restore_rate(
    step: Callable[[_RateControls], _RateControls], expected: list[str],
    controls: _RateControls,
) -> None:
    for display in reversed(expected):
        controls = step(controls)
        if controls.display != display:
            msg = "Sampling rate could not be restored after bounded traversal."
            raise AutomationError(msg)


def _rate_parts(display: str) -> tuple[Decimal, str]:
    try:
        numeric, unit = display.strip().split(maxsplit=1)
        value = Decimal(numeric)
    except (InvalidOperation, ValueError) as error:
        msg = "Provide a decimal sampling rate and its displayed unit, such as 100 Hz."
        raise AutomationError(msg) from error
    if not value.is_finite() or value <= 0:
        msg = "Sampling rate must be finite and positive."
        raise AutomationError(msg)
    return value, unit


def _rate_result(
    request: SamplingRateRequest, before: str, after: str, inputs: int,
) -> SamplingRateSelection:
    return SamplingRateSelection(
        sensor=request.sensor, requested_rate=request.target,
        before=before, after=after, changed=before != after,
        inputs_delivered=inputs,
    )


def target_sampling_rate(
    app: Capstone, handle: int, request: SamplingRateRequest,
) -> SamplingRateSelection:
    """Reach a supported rate without requiring identical decimal formatting."""
    controls = _rate_controls(app, handle, request.sensor)
    initial = controls.display
    current, unit = _rate_parts(initial)
    target, target_unit = _rate_parts(request.target)
    if unit != target_unit:
        msg = "Target rate must use the current display unit; no conversion is implied."
        raise AutomationError(msg)
    if current == target:
        return _rate_result(request, initial, initial, 0)
    increasing = current < target
    direction = "increase" if increasing else "decrease"
    reverse = "decrease" if increasing else "increase"
    previous: list[str] = []
    try:
        for _ in range(request.step_limit):
            enabled = (
                controls.increase_enabled if increasing else controls.decrease_enabled
            )
            if not enabled:
                break
            before = controls.display
            controls = _step_rate(app, handle, request, direction, controls)
            previous.append(before)
            value, after_unit = _rate_parts(controls.display)
            if after_unit != unit:
                break
            if value == target:
                return _rate_result(
                    request, initial, controls.display, len(previous),
                )
            if (
                (increasing and (value <= current or value > target))
                or (not increasing and (value >= current or value < target))
            ):
                break
            current = value
    except Exception as error:
        msg = (
            f"Sampling-rate traversal failed; the rate may have changed from "
            f"{initial!r}. Restoration was not verified. Inspect Capstone before "
            "retrying; no automatic reverse inputs were sent."
        )
        raise AutomationError(msg) from error
    try:
        _restore_rate(
            lambda before: _step_rate(app, handle, request, reverse, before),
            previous, controls,
        )
    except Exception as error:
        msg = (
            f"Sampling-rate restoration to {initial!r} failed or is unverified. "
            "The rate may have changed; inspect Capstone before retrying."
        )
        raise AutomationError(msg) from error
    msg = (
        f"Sampling rate {request.target!r} is unsupported or exceeds the step limit "
        f"for sensor {request.sensor!r}; the original rate was restored."
    )
    raise AutomationError(msg)


# ---------------------------------------------------------------------------
# 3. Sensor Zero / Tare Operations
# ---------------------------------------------------------------------------


def _is_zero_button(ctrl: Control) -> bool:
    """Check if a control represents a Zero or Tare action."""
    if not ctrl.visible or ctrl.control_type not in ("Button", "CheckBox"):
        return False
    name_lower = ctrl.name.strip().lower()
    aid_lower = ctrl.automation_id.lower()
    return (
        "zero" in name_lower
        or "tare" in name_lower
        or "zero" in aid_lower
        or "tare" in aid_lower
        or name_lower == "0"
    )


def zero_sensor(app: Capstone, request: ZeroSensorRequest) -> ZeroSensorResult:
    """Execute zero/tare for a specified sensor or all zeroable sensors."""
    if not request.allow_foreground:
        msg = "Sensor zeroing requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    zero_buttons = [c for c in snapshot.controls if _is_zero_button(c)]

    if not zero_buttons:
        msg = "No zeroable sensors or Zero buttons found in the active window."
        raise AutomationError(msg)

    target_buttons: list[Control] = []
    if request.sensor_name:
        s_lower = request.sensor_name.strip().lower()
        target_buttons.extend([
            btn for btn in zero_buttons
            if s_lower in btn.name.lower() or s_lower in btn.automation_id.lower()
        ])
        if not target_buttons:
            if len(zero_buttons) == 1:
                target_buttons.append(zero_buttons[0])
            else:
                msg = f"Zero button for sensor '{request.sensor_name}' not found."
                raise AutomationError(msg)
    else:
        target_buttons = zero_buttons

    zeroed_names: list[str] = []
    for btn in target_buttons:
        app.click(request.handle, btn.ref, allow_foreground=True)
        zeroed_names.append(btn.name.strip() or btn.automation_id)

    detail = (
        f"Zero/Tare executed for {len(zeroed_names)} sensor(s): "
        f"{', '.join(zeroed_names)}."
    )

    return ZeroSensorResult(
        zeroed_sensors=zeroed_names,
        verified=True,
        detail=detail,
    )
