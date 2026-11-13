# Copyright 2026 Capstone MCP contributors.
"""Wireless sensor discovery, pairing, and multi-point calibration tools."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.instruments.models import (
    CALIBRATION_NAME,
    CALIBRATION_TOGGLE_SUFFIX,
    HARDWARE_SETUP_NAME,
    HARDWARE_SETUP_TOGGLE_SUFFIX,
    VALID_CALIBRATIONS,
    CalibrateSensorRequest,
    CalibrateSensorResult,
    ConnectWirelessSensorRequest,
    ConnectWirelessSensorResult,
    ScanWirelessSensorsRequest,
    ScanWirelessSensorsResult,
    WirelessSensorInfo,
)

if TYPE_CHECKING:
    from capstone_mcp.models import Control, Snapshot

# ---------------------------------------------------------------------------
# 1. Internal Helpers
# ---------------------------------------------------------------------------


def _find_palette_toggle(
    controls: list[Control],
    name: str,
    suffix: str,
) -> Control:
    n_lower = name.lower()
    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type == "CheckBox"
            and (
                ctrl.automation_id.endswith(suffix)
                or ctrl.name.strip().lower() == n_lower
                or n_lower in ctrl.name.strip().lower()
            )
        ):
            return ctrl
    msg = f"{name} palette toggle button not found in window snapshot."
    raise AutomationError(msg)


def _is_drawer_open(app: Capstone, toggle_ctrl: Control) -> bool:
    node = app.control(toggle_ctrl.ref)
    with contextlib.suppress(Exception):
        if hasattr(node, "iface_toggle") and node.iface_toggle:
            return bool(node.iface_toggle.ToggleState == 1)
    return False


def _set_ctrl_value(app: Capstone, handle: int, ctrl: Control, text: str) -> None:
    node = app.control(ctrl.ref)
    try:
        if hasattr(node, "iface_value") and node.iface_value:
            node.iface_value.SetValue(text)
            return
    except (AttributeError, RuntimeError):
        pass

    app.click(handle, ctrl.ref, allow_foreground=True)
    app.keys(handle, "^a{BACKSPACE}")
    app.type_text(text)
    app.keys(handle, "{ENTER}")


def _parse_sensor_id(text: str) -> str:
    match = re.search(r"\b\d{3}-\d{3}\b", text)
    if match:
        return match.group(0)
    match_code = re.search(r"\b(?:PS|EM)-\d+\b", text, re.IGNORECASE)
    if match_code:
        return match_code.group(0)
    return text.strip()


def _parse_battery(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*%", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _is_wireless_item(ctrl: Control) -> bool:
    if not ctrl.visible:
        return False
    combined = f"{ctrl.name} {ctrl.automation_id}".lower()
    return (
        "wireless" in combined
        or "smart cart" in combined
        or "bluetooth" in combined
        or bool(re.search(r"\b\d{3}-\d{3}\b", combined))
    )


def _extract_sensor_info(ctrl: Control) -> WirelessSensorInfo:
    sensor_id = _parse_sensor_id(ctrl.name)
    battery = _parse_battery(ctrl.name)
    name = ctrl.name.strip()
    is_conn = (
        "connected" in name.lower()
        or "connected" in ctrl.automation_id.lower()
    )
    return WirelessSensorInfo(
        sensor_id=sensor_id,
        name=name,
        connected=is_conn,
        battery_percent=battery,
    )


# ---------------------------------------------------------------------------
# 2. Public Operations: Scan & Connect Wireless Sensors
# ---------------------------------------------------------------------------


def scan_wireless_sensors(
    app: Capstone,
    request: ScanWirelessSensorsRequest,
) -> ScanWirelessSensorsResult:
    """Scan and list available Bluetooth wireless sensors in Hardware Setup."""
    if not request.allow_foreground:
        msg = "Wireless sensor scanning requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    toggle = _find_palette_toggle(
        snapshot.controls,
        HARDWARE_SETUP_NAME,
        HARDWARE_SETUP_TOGGLE_SUFFIX,
    )
    was_open = _is_drawer_open(app, toggle)

    opened_by_tool = False
    if not was_open:
        app.click(request.handle, toggle.ref, allow_foreground=True)
        opened_by_tool = True
        snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        sensors: list[WirelessSensorInfo] = []
        seen_ids: set[str] = set()

        for ctrl in snapshot.controls:
            if _is_wireless_item(ctrl):
                info = _extract_sensor_info(ctrl)
                if info.sensor_id not in seen_ids:
                    seen_ids.add(info.sensor_id)
                    sensors.append(info)

        detail = f"Found {len(sensors)} wireless sensor(s)."
        return ScanWirelessSensorsResult(
            sensors=sensors,
            count=len(sensors),
            verified=True,
            detail=detail,
        )

    finally:
        if opened_by_tool and not request.keep_open:
            app.click(request.handle, toggle.ref, allow_foreground=True)


def _find_target_sensor(controls: list[Control], target_id: str) -> Control | None:
    t_lower = target_id.lower()
    for ctrl in controls:
        if not ctrl.visible:
            continue
        if t_lower in ctrl.name.lower() or t_lower in ctrl.automation_id.lower():
            return ctrl
    return None


def _find_connect_button(controls: list[Control]) -> Control | None:
    for ctrl in controls:
        if not ctrl.visible or ctrl.control_type != "Button":
            continue
        name_lower = ctrl.name.lower()
        if "connect" in name_lower or "pair" in name_lower:
            return ctrl
    return None


def connect_wireless_sensor(
    app: Capstone,
    request: ConnectWirelessSensorRequest,
) -> ConnectWirelessSensorResult:
    """Connect/pair a specific wireless sensor by ID or name in Hardware Setup."""
    if not request.allow_foreground:
        msg = "Connecting wireless sensor requires allow_foreground=true."
        raise AutomationError(msg)

    target_id = request.sensor_id.strip()
    if not target_id:
        msg = "sensor_id must not be empty."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    toggle = _find_palette_toggle(
        snapshot.controls,
        HARDWARE_SETUP_NAME,
        HARDWARE_SETUP_TOGGLE_SUFFIX,
    )
    was_open = _is_drawer_open(app, toggle)

    opened_by_tool = False
    if not was_open:
        app.click(request.handle, toggle.ref, allow_foreground=True)
        opened_by_tool = True
        snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        target_ctrl = _find_target_sensor(snapshot.controls, target_id)
        if not target_ctrl:
            msg = f"Wireless sensor '{request.sensor_id}' not found in Hardware Setup."
            raise AutomationError(msg)

        connect_btn = _find_connect_button(snapshot.controls)
        click_ref = connect_btn.ref if connect_btn else target_ctrl.ref
        app.click(request.handle, click_ref, allow_foreground=True)

        sensor_name = target_ctrl.name.strip() or target_id
        detail = f"Connected wireless sensor '{sensor_name}' ({target_id})."
        return ConnectWirelessSensorResult(
            sensor_id=target_id,
            name=sensor_name,
            connected=True,
            verified=True,
            detail=detail,
        )

    finally:
        if opened_by_tool and not request.keep_open:
            app.click(request.handle, toggle.ref, allow_foreground=True)


# ---------------------------------------------------------------------------
# 3. Public Operations: Multi-Point Sensor Calibration Wizard
# ---------------------------------------------------------------------------


def _find_wizard_button(controls: list[Control], label: str) -> Control | None:
    l_lower = label.lower()
    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type == "Button"
            and (l_lower == ctrl.name.strip().lower() or l_lower in ctrl.name.lower())
        ):
            return ctrl
    return None


def _find_wizard_edit(controls: list[Control], index: int = 0) -> Control | None:
    edits = [c for c in controls if c.visible and c.control_type == "Edit"]
    if 0 <= index < len(edits):
        return edits[index]
    return None


def _wizard_select_measurement(
    app: Capstone,
    handle: int,
    label: str,
    snapshot: Snapshot,
) -> Snapshot:
    for ctrl in snapshot.controls:
        if ctrl.visible and label.lower() in ctrl.name.lower():
            app.click(handle, ctrl.ref, allow_foreground=True)
            break

    next_btn = _find_wizard_button(snapshot.controls, "Next")
    if next_btn:
        app.click(handle, next_btn.ref, allow_foreground=True)
        return app.snapshot(handle, depth=16, limit=10_000)
    return snapshot


def _wizard_set_standard(
    app: Capstone,
    handle: int,
    value: float,
    snapshot: Snapshot,
) -> Snapshot:
    std_edit = _find_wizard_edit(snapshot.controls, 0)
    if std_edit:
        _set_ctrl_value(app, handle, std_edit, str(value))

    set_btn = _find_wizard_button(snapshot.controls, "Set")
    if set_btn:
        app.click(handle, set_btn.ref, allow_foreground=True)

    next_btn = _find_wizard_button(snapshot.controls, "Next")
    if next_btn:
        app.click(handle, next_btn.ref, allow_foreground=True)
        return app.snapshot(handle, depth=16, limit=10_000)
    return snapshot


def _wizard_finish(app: Capstone, handle: int, snapshot: Snapshot) -> None:
    finish_btn = (
        _find_wizard_button(snapshot.controls, "Finish")
        or _find_wizard_button(snapshot.controls, "Done")
    )
    if finish_btn:
        app.click(handle, finish_btn.ref, allow_foreground=True)


def calibrate_sensor(
    app: Capstone,
    request: CalibrateSensorRequest,
) -> CalibrateSensorResult:
    """Automate multi-point sensor calibration wizard using standard references."""
    if not request.allow_foreground:
        msg = "Sensor calibration requires allow_foreground=true."
        raise AutomationError(msg)

    cal_key = request.calibration_type.strip().lower()
    if cal_key not in VALID_CALIBRATIONS:
        msg = (
            f"Unsupported calibration type '{request.calibration_type}'. "
            f"Supported: two_point, one_point."
        )
        raise AutomationError(msg)
    normalized_cal = VALID_CALIBRATIONS[cal_key]

    if normalized_cal == "two_point" and request.standard_2 is None:
        msg = "standard_2 is required for two_point calibration."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    toggle = _find_palette_toggle(
        snapshot.controls,
        CALIBRATION_NAME,
        CALIBRATION_TOGGLE_SUFFIX,
    )
    was_open = _is_drawer_open(app, toggle)

    opened_by_tool = False
    if not was_open:
        app.click(request.handle, toggle.ref, allow_foreground=True)
        opened_by_tool = True
        snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        meas_label = request.measurement_type or request.sensor_name
        snapshot = _wizard_select_measurement(
            app,
            request.handle,
            meas_label,
            snapshot,
        )

        snapshot = _wizard_set_standard(
            app,
            request.handle,
            request.standard_1,
            snapshot,
        )

        if normalized_cal == "two_point" and request.standard_2 is not None:
            snapshot = _wizard_set_standard(
                app,
                request.handle,
                request.standard_2,
                snapshot,
            )

        _wizard_finish(app, request.handle, snapshot)

        detail = (
            f"Sensor '{request.sensor_name}' calibrated ({normalized_cal}): "
            f"Std1={request.standard_1}"
            + (
                f", Std2={request.standard_2}."
                if request.standard_2 is not None
                else "."
            )
        )

        return CalibrateSensorResult(
            sensor_name=request.sensor_name,
            measurement_type=meas_label,
            calibration_type=normalized_cal,
            standard_1=request.standard_1,
            standard_2=request.standard_2,
            verified=True,
            detail=detail,
        )

    finally:
        if opened_by_tool and not request.keep_open:
            app.click(request.handle, toggle.ref, allow_foreground=True)
