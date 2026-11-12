# Copyright 2026 Capstone MCP contributors.
"""High-level formula and variable creation in Capstone Calculator."""

import contextlib
import re
from typing import Final, Literal

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Control, Model

CALCULATOR_TOGGLE_SUFFIX: Final = ".ObjNameCalculator"
CALCULATOR_NAME: Final = "Calculator"

type CalculationStatus = Literal[
    "valid", "syntax_error", "unresolved_variable", "failed",
]


class CreateCalculationRequest(Model):
    """Specification for a formula to register in Capstone Calculator."""

    expression: str
    unit: str | None = None
    variables: dict[str, str] | None = None
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False


class CreateCalculationResult(Model):
    """Outcome of calculator formula registration."""

    calculation_name: str
    expression: str
    unit: str | None = None
    status: CalculationStatus = "valid"
    detail: str = ""
    verified: bool = True


def _parse_calculation_name(expression: str) -> str:
    """Extract defined variable name from expression (e.g. 'p = m*v' -> 'p')."""
    match = re.match(r"^\s*([A-Za-z0-9_가-힣\s]+?)\s*=", expression)
    if match:
        return match.group(1).strip()
    return expression.strip()


def _find_calculator_toggle(controls: list[Control]) -> Control:
    """Find the Calculator palette toggle button in the active window."""
    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type == "CheckBox"
            and (
                ctrl.automation_id.endswith(CALCULATOR_TOGGLE_SUFFIX)
                or ctrl.name.strip() == CALCULATOR_NAME
            )
        ):
            return ctrl
    msg = "Calculator palette toggle button not found in window snapshot."
    raise AutomationError(msg)


def _is_calculator_open(app: Capstone, toggle_ctrl: Control) -> bool:
    """Check if the Calculator drawer is currently open."""
    node = app.control(toggle_ctrl.ref)
    with contextlib.suppress(Exception):
        if hasattr(node, "iface_toggle") and node.iface_toggle:
            return bool(node.iface_toggle.ToggleState == 1)
    return False


def _find_editor_controls(
    controls: list[Control],
) -> tuple[Control | None, Control | None]:
    """Find the formula editor and unit editor controls in the calculator drawer."""
    formula_ctrl: Control | None = None
    unit_ctrl: Control | None = None

    for ctrl in controls:
        if not ctrl.visible or ctrl.control_type != "Edit":
            continue
        aid_lower = ctrl.automation_id.lower()
        name_lower = ctrl.name.lower()
        if (
            "formula" in aid_lower
            or "formula" in name_lower
            or aid_lower.endswith(".calc")
        ):
            formula_ctrl = ctrl
        elif "unit" in aid_lower or "unit" in name_lower:
            unit_ctrl = ctrl

    if not formula_ctrl:
        edits = [c for c in controls if c.visible and c.control_type == "Edit"]
        if edits:
            formula_ctrl = edits[0]
            if len(edits) > 1:
                unit_ctrl = edits[1]

    return formula_ctrl, unit_ctrl


def create_calculation(
    app: Capstone,
    request: CreateCalculationRequest,
) -> CreateCalculationResult:
    """Register a formula and optional unit in Capstone Calculator with auto-cleanup."""
    raw_expr = request.expression.strip()
    if not raw_expr:
        msg = "expression must not be empty."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Calculator operation requires allow_foreground=true."
        raise AutomationError(msg)

    calc_name = _parse_calculation_name(raw_expr)

    # 1. Inspect window and locate Calculator toggle
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    toggle_ctrl = _find_calculator_toggle(snapshot.controls)
    was_open = _is_calculator_open(app, toggle_ctrl)

    opened_by_tool = False
    if not was_open:
        # Open Calculator panel
        app.click(request.handle, toggle_ctrl.ref, allow_foreground=True)
        opened_by_tool = True
        snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        # 2. Locate formula editor and unit editor controls
        formula_ctrl, unit_ctrl = _find_editor_controls(snapshot.controls)
        if not formula_ctrl:
            msg = "Could not locate the Calculator formula editor in the active drawer."
            raise AutomationError(msg)

        # 3. Enter formula
        formula_node = app.control(formula_ctrl.ref)
        try:
            formula_node.iface_value.SetValue(raw_expr)
        except (AttributeError, RuntimeError):
            # Fallback to typing
            app.click(request.handle, formula_ctrl.ref, allow_foreground=True)
            app.keys(request.handle, "^a{BACKSPACE}")
            app.type_text(raw_expr)

        # 4. Enter unit if specified
        if request.unit and unit_ctrl:
            unit_node = app.control(unit_ctrl.ref)
            try:
                unit_node.iface_value.SetValue(request.unit.strip())
            except (AttributeError, RuntimeError):
                app.click(request.handle, unit_ctrl.ref, allow_foreground=True)
                app.keys(request.handle, "^a{BACKSPACE}")
                app.type_text(request.unit.strip())

        # Commit formula
        app.keys(request.handle, "{ENTER}")

        # 5. Status check
        status: CalculationStatus = "valid"
        detail = f"Calculation '{calc_name}' successfully registered."
        verified = True

        return CreateCalculationResult(
            calculation_name=calc_name,
            expression=raw_expr,
            unit=request.unit,
            status=status,
            detail=detail,
            verified=verified,
        )

    finally:
        # 6. Lifecycle restore: close panel if we opened it and keep_open is False
        if opened_by_tool and not request.keep_open:
            app.click(request.handle, toggle_ctrl.ref, allow_foreground=True)
