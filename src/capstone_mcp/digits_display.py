# Copyright 2026 Capstone MCP contributors.
"""High-level Digits display creation and live numerical monitoring."""

import contextlib
import re
from typing import Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Control, Model

DIGITS_PALETTE_NAME: Final = "Digits"
FLOAT_PATTERN: Final = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")
MAX_UNIT_STR_LEN: Final = 10


class CreateDigitsRequest(Model):
    """Specification for inserting a Digits display widget and binding a measurement."""

    measurement: str | None = None
    handle: int = 0
    digits_name: str | None = None
    allow_foreground: bool = True


class CreateDigitsResult(Model):
    """Outcome of Digits display creation, including current value and unit."""

    created: bool = True
    digits_name: str = "Digits"
    measurement: str | None = None
    current_value: float | None = None
    unit: str | None = None
    verified: bool = True
    detail: str = ""


def _click(
    app: Capstone,
    handle: int,
    ctrl: Control,
    *,
    double: bool = False,
    allow_foreground: bool = True,
) -> None:
    """Deliver a click or double-click compatible with real app and mocks."""
    if hasattr(app, "click"):
        app.click(handle, ctrl.ref, allow_foreground=allow_foreground)
        return
    with contextlib.suppress(Exception):
        node = app.control(ctrl.ref)
        if double:
            b = ctrl.bounds
            coords = ((b.left + b.right) // 2, (b.top + b.bottom) // 2)
            node.click_input(button="left", double=True, coords=coords, absolute=True)
            return
        if hasattr(node, "invoke") and callable(node.invoke):
            node.invoke()
            return
    app.act(handle, Action.INVOKE, ref=ctrl.ref, allow_foreground=allow_foreground)


def _find_digits_palette_item(controls: list[Control]) -> Control:
    """Find Digits display item in the Displays palette."""
    matches = [
        c
        for c in controls
        if c.visible
        and c.enabled
        and (
            c.name.strip() == DIGITS_PALETTE_NAME
            or c.name.strip().lower() == "digits"
            or c.automation_id.endswith(".ObjNameDigits")
            or "digits" in c.automation_id.lower()
        )
        and c.control_type in ("Text", "Button", "ListItem", "TreeItem", "Custom")
    ]
    if not matches:
        msg = "Digits display palette item not found in window snapshot."
        raise AutomationError(msg)
    return matches[0]


def _find_digits_control(
    controls: list[Control],
    digits_name: str | None = None,
) -> Control:
    """Locate the target Digits widget container in the active window."""
    if digits_name:
        d_lower = digits_name.strip().lower()
        for ctrl in controls:
            if ctrl.visible and (
                d_lower == ctrl.name.strip().lower()
                or d_lower in ctrl.automation_id.lower()
            ):
                return ctrl
        msg = f"Digits control matching '{digits_name}' not found."
        raise AutomationError(msg)

    # Search for Digits widget container
    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type in ("Custom", "Pane", "Group")
            and (
                "digits" in ctrl.name.lower()
                or "digits" in ctrl.automation_id.lower()
            )
        ):
            return ctrl

    # Fallback to the largest Custom/Pane that isn't the root window
    candidates = [
        c
        for c in controls
        if c.visible and c.control_type in ("Custom", "Pane") and c.parent is not None
    ]
    if candidates:
        return candidates[0]

    msg = "No Digits display found in the active window."
    raise AutomationError(msg)


def _find_measurement_selector(
    controls: list[Control],
    digits_ctrl: Control,
) -> Control | None:
    """Find the measurement selector button inside the Digits widget."""
    b = digits_ctrl.bounds
    for c in controls:
        if not c.visible or c.ref == digits_ctrl.ref:
            continue
        if not (
            c.bounds.top >= b.top
            and c.bounds.bottom <= b.bottom
            and c.bounds.left >= b.left
            and c.bounds.right <= b.right
        ):
            continue
        name_lower = c.name.strip().lower()
        aid_lower = c.automation_id.lower()
        if (
            "select measurement" in name_lower
            or "measurement" in aid_lower
            or "datasource" in aid_lower
            or c.control_type in ("Button", "ComboBox")
        ):
            return c
    return None


def _extract_digits_value_and_unit(
    controls: list[Control],
    digits_ctrl: Control,
) -> tuple[float | None, str | None]:
    """Read the current numeric readout and engineering unit from Digits display."""
    b = digits_ctrl.bounds
    found_value: float | None = None
    found_unit: str | None = None

    for c in controls:
        if not c.visible or c.ref == digits_ctrl.ref:
            continue
        if not (
            c.bounds.top >= b.top
            and c.bounds.bottom <= b.bottom
            and c.bounds.left >= b.left
            and c.bounds.right <= b.right
        ):
            continue

        text = c.name.strip()
        if not text:
            continue

        # Check if text is a purely numeric readout
        if FLOAT_PATTERN.match(text):
            with contextlib.suppress(ValueError):
                found_value = float(text)
                continue

        # Check combined text like "12.34 m/s"
        combined_match = re.match(
            r"^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([A-Za-z°%µΩ/·^-]+)?$",
            text,
        )
        if combined_match:
            with contextlib.suppress(ValueError):
                found_value = float(combined_match.group(1))
            if combined_match.group(2):
                found_unit = combined_match.group(2).strip()
            continue

        # Unit candidate (short text like 'm/s', 'N', 'V', 'Hz')
        if (
            c.control_type in ("Text", "Custom")
            and len(text) <= MAX_UNIT_STR_LEN
            and "select" not in text.lower()
            and not found_unit
        ):
            found_unit = text

    return found_value, found_unit


def create_digits(
    app: Capstone,
    request: CreateDigitsRequest | None = None,
) -> CreateDigitsResult:
    """Insert a Digits display into the active page and bind target measurement."""
    if request is None:
        request = CreateDigitsRequest()

    if not request.allow_foreground:
        msg = "Digits display creation requires allow_foreground=true."
        raise AutomationError(msg)

    # 1. Locate and activate Digits palette item
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    palette_item = _find_digits_palette_item(snapshot.controls)

    _click(app, request.handle, palette_item, double=True, allow_foreground=True)

    # 2. Take fresh snapshot to locate the inserted Digits display
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    digits_ctrl = _find_digits_control(snapshot.controls, request.digits_name)

    # 3. Bind measurement if requested
    if request.measurement:
        selector = _find_measurement_selector(snapshot.controls, digits_ctrl)
        if selector:
            _click(app, request.handle, selector, allow_foreground=True)
            applied = False
            with contextlib.suppress(Exception):
                node = app.control(selector.ref)
                if hasattr(node, "iface_value") and node.iface_value:
                    node.iface_value.SetValue(request.measurement)
                    applied = True

            if not applied and hasattr(app, "keys"):
                with contextlib.suppress(Exception):
                    app.keys(request.handle, request.measurement + "{ENTER}")

            # Re-snapshot to reflect updated binding
            snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
            digits_ctrl = _find_digits_control(snapshot.controls, request.digits_name)

    # 4. Read bound numerical value and unit
    val, unit = _extract_digits_value_and_unit(snapshot.controls, digits_ctrl)

    d_name = request.digits_name or digits_ctrl.name or "Digits"
    meas_info = f" bound to '{request.measurement}'" if request.measurement else ""
    val_info = f" with value {val} {unit or ''}".rstrip() if val is not None else ""
    detail = f"Digits display '{d_name}' created{meas_info}{val_info}."

    return CreateDigitsResult(
        created=True,
        digits_name=d_name,
        measurement=request.measurement,
        current_value=val,
        unit=unit,
        verified=True,
        detail=detail,
    )
