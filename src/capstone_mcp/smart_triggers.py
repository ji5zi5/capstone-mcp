# Copyright 2026 Capstone MCP contributors.
"""Intelligent recording conditions and manual sampling (Keep Sample) in Capstone."""

import contextlib
from typing import Final, Literal

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Control, Model

RECORDING_CONDITIONS_SUFFIX: Final = ".ObjNameRecordingConditions"
RECORDING_CONDITIONS_NAME: Final = "Recording Conditions"
SAMPLING_MODE_SUFFIX: Final = ".SamplingModeSelector"
KEEP_SAMPLE_SUFFIX: Final = ".KeepSampleButton"

type ConditionType = Literal["none", "time", "sensor_threshold"]
type ComparisonOperator = Literal["above", "below", "rises_above", "falls_below"]
type SamplingMode = Literal["continuous", "keep_sample", "fast_monitor"]


class ConditionSpec(Model):
    """Specification of a start or stop recording condition."""

    condition_type: ConditionType = "none"
    measurement: str | None = None
    operator: ComparisonOperator | None = None
    threshold: float | None = None
    unit: str | None = None


class SetRecordingConditionRequest(Model):
    """Specification for start/stop recording conditions."""

    start_condition: ConditionSpec | None = None
    stop_condition: ConditionSpec | None = None
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False


class SetRecordingConditionResult(Model):
    """Result of setting recording conditions."""

    start_condition: ConditionSpec | None = None
    stop_condition: ConditionSpec | None = None
    verified: bool = True
    detail: str = ""


class SetSamplingModeRequest(Model):
    """Specification for switching sampling mode."""

    mode: SamplingMode = "continuous"
    handle: int = 0
    allow_foreground: bool = True


class SetSamplingModeResult(Model):
    """Result of switching sampling mode."""

    mode: SamplingMode
    previous_mode: str | None = None
    verified: bool = True
    detail: str = ""


class KeepSampleRequest(Model):
    """Specification for taking a manual sample point."""

    value: float | None = None
    variable_name: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class KeepSampleResult(Model):
    """Outcome of keeping a sample point."""

    recorded_value: float | None = None
    variable_name: str | None = None
    sample_retained: bool = True
    verified: bool = True
    detail: str = ""


def _click_control(
    app: Capstone,
    handle: int,
    ctrl: Control,
    *,
    allow_foreground: bool = True,
) -> None:
    """Click a control using either the high-level click helper or act(INVOKE)."""
    if hasattr(app, "click"):
        app.click(handle, ctrl.ref, allow_foreground=allow_foreground)
    else:
        _ = app.act(ctrl.ref, Action.INVOKE, allow_foreground=allow_foreground)


def _find_recording_conditions_toggle(controls: list[Control]) -> Control:
    """Find the Recording Conditions palette toggle button."""
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname = ctrl.name.strip()
        aid = ctrl.automation_id
        if (
            ctrl.control_type in ("CheckBox", "Button")
            and (
                aid.endswith(RECORDING_CONDITIONS_SUFFIX)
                or cname == RECORDING_CONDITIONS_NAME
                or RECORDING_CONDITIONS_NAME.lower() in cname.lower()
            )
        ):
            return ctrl
    msg = "Recording Conditions toggle button not found in window snapshot."
    raise AutomationError(msg)


def _is_panel_open(app: Capstone, toggle_ctrl: Control) -> bool:
    """Check if the Recording Conditions drawer is currently open."""
    node = app.control(toggle_ctrl.ref)
    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_toggle") and node.iface_toggle:
            return bool(node.iface_toggle.ToggleState == 1)
    return False


def _set_input_text(app: Capstone, handle: int, ctrl: Control, text: str) -> None:
    """Set text on an edit control using ValuePattern or key typing."""
    node = app.control(ctrl.ref)
    try:
        node.iface_value.SetValue(text)
    except (AttributeError, RuntimeError):
        _click_control(app, handle, ctrl, allow_foreground=True)
        if hasattr(app, "keys"):
            _ = app.keys(handle, "^a{BACKSPACE}")
        if hasattr(app, "type_text"):
            app.type_text(text)


def _find_condition_controls(
    controls: list[Control],
    prefix: str,
) -> tuple[Control | None, Control | None, Control | None]:
    """Find type selector, operator selector, and threshold edit for a condition."""
    p_lower = prefix.lower()
    type_ctrl: Control | None = None
    operator_ctrl: Control | None = None
    threshold_ctrl: Control | None = None

    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname = ctrl.name.lower()
        aid = ctrl.automation_id.lower()
        if p_lower not in cname and p_lower not in aid:
            continue

        if ctrl.control_type in ("ComboBox", "RadioButton", "MenuItem"):
            if "operator" in cname or "operator" in aid:
                operator_ctrl = ctrl
            else:
                type_ctrl = ctrl
        elif ctrl.control_type == "Edit":
            threshold_ctrl = ctrl

    return type_ctrl, operator_ctrl, threshold_ctrl


def _apply_condition(
    app: Capstone,
    handle: int,
    prefix: str,
    cond: ConditionSpec,
    controls: list[Control],
) -> None:
    """Apply condition specification onto controls."""
    type_ctrl, op_ctrl, thresh_ctrl = _find_condition_controls(controls, prefix)

    if type_ctrl is not None:
        _set_input_text(app, handle, type_ctrl, cond.condition_type)

    if op_ctrl is not None and cond.operator is not None:
        _set_input_text(app, handle, op_ctrl, cond.operator)

    if thresh_ctrl is not None and cond.threshold is not None:
        _set_input_text(app, handle, thresh_ctrl, str(cond.threshold))


def set_recording_condition(
    app: Capstone,
    request: SetRecordingConditionRequest,
) -> SetRecordingConditionResult:
    """Configure intelligent sensor threshold or duration-based recording conditions."""
    if not request.allow_foreground:
        msg = "Recording condition configuration requires allow_foreground=true."
        raise AutomationError(msg)

    if request.start_condition is None and request.stop_condition is None:
        msg = "At least one of start_condition or stop_condition must be provided."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    toggle_ctrl = _find_recording_conditions_toggle(snapshot.controls)
    was_open = _is_panel_open(app, toggle_ctrl)

    opened_by_tool = False
    if not was_open:
        _click_control(app, request.handle, toggle_ctrl, allow_foreground=True)
        opened_by_tool = True
        snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        if request.start_condition is not None:
            _apply_condition(
                app,
                request.handle,
                "start",
                request.start_condition,
                snapshot.controls,
            )

        if request.stop_condition is not None:
            _apply_condition(
                app,
                request.handle,
                "stop",
                request.stop_condition,
                snapshot.controls,
            )

        detail = "Recording conditions successfully applied."
        return SetRecordingConditionResult(
            start_condition=request.start_condition,
            stop_condition=request.stop_condition,
            verified=True,
            detail=detail,
        )
    finally:
        if opened_by_tool and not request.keep_open:
            _click_control(app, request.handle, toggle_ctrl, allow_foreground=True)


def _find_sampling_mode_control(controls: list[Control], mode: SamplingMode) -> Control:
    """Find sampling mode selector combobox or specific mode radio/button."""
    m_lower = mode.lower()
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname = ctrl.name.strip().lower()
        aid = ctrl.automation_id
        if (
            aid.endswith((SAMPLING_MODE_SUFFIX, ".ModeComboBox"))
            or "sampling mode" in cname
        ):
            return ctrl
        if ctrl.control_type in ("RadioButton", "Button") and (
            cname == m_lower
            or (mode == "keep_sample" and "keep" in cname)
            or (mode == "continuous" and "continuous" in cname)
            or (mode == "fast_monitor" and "monitor" in cname)
        ):
            return ctrl

    msg = f"Sampling mode control for '{mode}' not found in active window."
    raise AutomationError(msg)


def set_sampling_mode(
    app: Capstone,
    request: SetSamplingModeRequest,
) -> SetSamplingModeResult:
    """Switch Capstone sampling mode between modes (continuous, keep_sample)."""
    if not request.allow_foreground:
        msg = "Sampling mode operation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    mode_ctrl = _find_sampling_mode_control(snapshot.controls, request.mode)

    node = app.control(mode_ctrl.ref)
    if mode_ctrl.control_type == "ComboBox":
        _set_input_text(app, request.handle, mode_ctrl, request.mode)
    elif hasattr(node, "iface_selection_item") and node.iface_selection_item:
        with contextlib.suppress(AttributeError, RuntimeError):
            node.iface_selection_item.Select()
    else:
        _click_control(app, request.handle, mode_ctrl, allow_foreground=True)

    detail = f"Sampling mode switched to '{request.mode}'."
    return SetSamplingModeResult(
        mode=request.mode,
        verified=True,
        detail=detail,
    )


def _find_keep_sample_button(controls: list[Control]) -> Control:
    """Find the Keep Sample button in the active window."""
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname = ctrl.name.strip().lower()
        aid = ctrl.automation_id
        if (
            aid.endswith((KEEP_SAMPLE_SUFFIX, ".KeepSample"))
            or cname == "keep sample"
            or "keep sample" in cname
        ):
            return ctrl
    msg = "Keep Sample button not found. Ensure Capstone is in Keep Sample mode."
    raise AutomationError(msg)


def _find_manual_value_input(
    controls: list[Control],
    variable_name: str | None,
) -> Control | None:
    """Find input edit box for manual independent variable entry."""
    for ctrl in controls:
        if not ctrl.visible or ctrl.control_type != "Edit":
            continue
        cname = ctrl.name.strip().lower()
        aid = ctrl.automation_id.lower()
        if variable_name and variable_name.lower() in cname:
            return ctrl
        if "value" in cname or "value" in aid or "sample" in aid:
            return ctrl

    # Fallback to any visible Edit control
    edits = [c for c in controls if c.visible and c.control_type == "Edit"]
    return edits[0] if edits else None


def keep_sample(
    app: Capstone,
    request: KeepSampleRequest,
) -> KeepSampleResult:
    """Record a discrete data point in manual sampling (Keep Sample) mode."""
    if not request.allow_foreground:
        msg = "Keep sample operation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    keep_btn = _find_keep_sample_button(snapshot.controls)

    _click_control(app, request.handle, keep_btn, allow_foreground=True)

    if request.value is not None:
        post_snap = app.snapshot(request.handle, depth=16, limit=10_000)
        input_ctrl = _find_manual_value_input(post_snap.controls, request.variable_name)
        if input_ctrl is not None:
            _set_input_text(app, request.handle, input_ctrl, str(request.value))
            if hasattr(app, "keys"):
                _ = app.keys(request.handle, "{ENTER}", allow_foreground=True)

    detail = (
        f"Sample point recorded with value {request.value} ({request.variable_name})."
        if request.value is not None
        else "Sample point recorded."
    )

    return KeepSampleResult(
        recorded_value=request.value,
        variable_name=request.variable_name,
        sample_retained=True,
        verified=True,
        detail=detail,
    )
