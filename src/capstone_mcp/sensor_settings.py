# Copyright 2026 Capstone MCP contributors.
"""Exact sensor selection and bounded native sampling-rate traversal."""

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import Field

from capstone_mcp.acquisition import observe_recording
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Control, Model, Snapshot


class SensorSelectionRequest(Model):
    """An exact observed sensor name and input-delivery policy."""

    sensor: str
    allow_foreground: bool = True


class SamplingRateRequest(Model):
    """A numeric rate and explicit display unit with a bounded step search."""

    sensor: str
    target: str
    step_limit: int = Field(default=128, ge=1, le=512)
    allow_foreground: bool = True


class SensorSelection(Model):
    """Observed sensor and native rate displays before and after selection."""

    requested_sensor: str
    before_sensor: str
    after_sensor: str
    before_sampling_rate: str
    after_sampling_rate: str
    changed: bool


class SamplingRateSelection(Model):
    """Observed native rate displays before and after bounded traversal."""

    sensor: str
    requested_rate: str
    before: str
    after: str
    changed: bool
    inputs_delivered: int


class SensorConfiguration(Model):
    """Confirmed sensor selection and the resulting supported sampling rate."""

    selection: SensorSelection
    rate: SamplingRateSelection


class _Settings(Model):
    """One fresh stopped-state observation of the native controls."""

    sensor: str
    sampling_rate: str


class _RateControls(Model):
    """Fresh rate label and step-control references from one snapshot."""

    display: str
    increase_ref: str
    increase_enabled: bool
    decrease_ref: str
    decrease_enabled: bool


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
    settings = _settings(app, handle)
    if settings.sensor != expected_sensor:
        msg = "Selected sampling sensor does not match the requested sensor."
        raise AutomationError(msg)
    snapshot = app.snapshot(handle, 16, 10_000)

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
    direction: Literal["increase", "decrease"],
) -> tuple[str, str]:
    before = _rate_controls(app, handle, request.sensor)
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
    return before.display, after.display


def _restore_rate(
    app: Capstone, handle: int, request: SamplingRateRequest,
    direction: Literal["increase", "decrease"], expected: list[str],
) -> None:
    for display in reversed(expected):
        _, after = _step_rate(app, handle, request, direction)
        if after != display:
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
    initial = _rate_controls(app, handle, request.sensor).display
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
            controls = _rate_controls(app, handle, request.sensor)
            enabled = (
                controls.increase_enabled if increasing else controls.decrease_enabled
            )
            if not enabled:
                break
            before, after = _step_rate(app, handle, request, direction)
            previous.append(before)
            value, after_unit = _rate_parts(after)
            if after_unit != unit:
                break
            if value == target:
                return _rate_result(request, initial, after, len(previous))
            if (
                (increasing and (value <= current or value > target))
                or (not increasing and (value >= current or value < target))
            ):
                break
            current = value
    except Exception as error:
        # A click may have succeeded even when its acknowledgement/read failed.
        # Replaying inverse clicks from an incomplete history is unsafe.
        msg = (
            f"Sampling-rate traversal failed; the rate may have changed from "
            f"{initial!r}. Restoration was not verified. Inspect Capstone before "
            "retrying; no automatic reverse inputs were sent."
        )
        raise AutomationError(msg) from error
    try:
        _restore_rate(app, handle, request, reverse, previous)
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
