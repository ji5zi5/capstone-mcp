# Copyright 2026 Capstone MCP contributors.
"""Digits display creation and live numerical monitoring."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays.harness import (
    click_control,
    find_display_container,
    find_palette_item,
    is_within_bounds,
)
from capstone_mcp.displays.models import (
    DIGITS_PALETTE_NAME,
    FLOAT_PATTERN,
    CreateDigitsRequest,
    CreateDigitsResult,
)

if TYPE_CHECKING:
    from capstone_mcp.models import Control

MAX_UNIT_STR_LEN = 10


def _find_digits_palette_item(controls: list[Control]) -> Control:
    """Find Digits display item in the Displays palette."""
    return find_palette_item(controls, DIGITS_PALETTE_NAME, ".ObjNameDigits")


def _find_digits_control(
    controls: list[Control],
    digits_name: str | None = None,
) -> Control:
    """Locate the target Digits widget container in the active window."""
    return find_display_container(controls, "digits", digits_name)


def _find_measurement_selector(
    controls: list[Control],
    digits_ctrl: Control,
) -> Control | None:
    """Find the measurement selector button inside the Digits widget."""
    for c in controls:
        if not c.visible or c.ref == digits_ctrl.ref:
            continue
        if not is_within_bounds(c, digits_ctrl):
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
            len(text) <= MAX_UNIT_STR_LEN
            and not FLOAT_PATTERN.match(text)
            and any(ch.isalpha() for ch in text)
            and "digits" not in text.lower()
            and "select" not in text.lower()
        ):
            found_unit = text

    return found_value, found_unit


def create_digits(
    app: Capstone,
    request: CreateDigitsRequest | None = None,
) -> CreateDigitsResult:
    """Insert a Digits display widget on the active page and select measurement."""
    if request is None:
        request = CreateDigitsRequest()

    if not request.allow_foreground:
        msg = "Digits display creation requires allow_foreground=true."
        raise AutomationError(msg)

    # 1. Inspect window snapshot
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    # 2. Find and double-click Digits palette item
    try:
        palette_item = _find_digits_palette_item(snapshot.controls)
        click_control(
            app,
            request.handle,
            palette_item,
            double=True,
            allow_foreground=request.allow_foreground,
        )
    except AutomationError:
        pass

    # 3. Re-snapshot to find newly created Digits widget
    post_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    digits_ctrl = _find_digits_control(post_snapshot.controls, request.digits_name)

    result_name = digits_ctrl.name or request.digits_name or "Digits"
    val, unit = _extract_digits_value_and_unit(post_snapshot.controls, digits_ctrl)

    # 4. If measurement binding requested, click selector
    if request.measurement:
        selector = _find_measurement_selector(post_snapshot.controls, digits_ctrl)
        if selector:
            click_control(
                app,
                request.handle,
                selector,
                double=False,
                allow_foreground=request.allow_foreground,
            )

    detail = (
        f"Inserted Digits display '{result_name}'"
        + (f" with measurement '{request.measurement}'" if request.measurement else "")
        + (f" (current: {val} {unit or ''})".strip() if val is not None else "")
        + "."
    )

    return CreateDigitsResult(
        created=True,
        digits_name=result_name,
        measurement=request.measurement,
        current_value=val,
        unit=unit,
        verified=True,
        detail=detail,
    )
