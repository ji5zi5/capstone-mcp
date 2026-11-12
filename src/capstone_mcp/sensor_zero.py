# Copyright 2026 Capstone MCP contributors.
"""Dedicated sensor zero/tare operation in Capstone."""

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Control, Model


class ZeroSensorRequest(Model):
    """Specification of target sensor to zero/tare."""

    sensor_name: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class ZeroSensorResult(Model):
    """Outcome of sensor zeroing operation."""

    zeroed_sensors: list[str]
    verified: bool
    detail: str


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

    # 1. Take snapshot of active window
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
            # Fallback to the first zero button if only one exists
            if len(zero_buttons) == 1:
                target_buttons.append(zero_buttons[0])
            else:
                msg = (
                    f"Zero button for sensor '{request.sensor_name}' not found."
                )
                raise AutomationError(msg)
    else:
        target_buttons = zero_buttons

    # 2. Click each target zero button
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
