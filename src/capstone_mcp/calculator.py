# Copyright 2026 Capstone MCP contributors.
"""High-level formula and variable creation in Capstone Calculator."""

import ast
import contextlib
import re
import sys
from typing import Final, Literal

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Control, Model, Snapshot

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
    status: CalculationStatus = "failed"
    detail: str = ""
    verified: bool = False


def _parse_calculation_name(expression: str) -> str:
    """Extract defined variable name from expression (e.g. 'p = m*v' -> 'p')."""
    match = re.match(r"^\s*([\w\s]+?)\s*=(?!=)", expression)
    if match:
        return match.group(1).strip()
    return expression.strip()


def _validate_delimiters(expression: str) -> None:
    """Reject unbalanced grouping without pretending to parse Capstone's language."""
    tokens = re.findall(
        r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\[[^\]]*\]|[()\[\]"']""",
        expression,
    )
    depth = 0
    for fragment in tokens:
        if len(fragment) > 1:
            continue
        if fragment == "(":
            depth += 1
        elif fragment == ")" and depth:
            depth -= 1
        else:
            msg = "Calculator expression has unbalanced parentheses or brackets."
            raise AutomationError(msg)
    if depth:
        msg = "Calculator expression has unbalanced parentheses, brackets, or quotes."
        raise AutomationError(msg)


def _validate_arithmetic(expression: str) -> None:
    """Check numeric operators while preserving native functions and unit syntax."""
    assignment = re.match(r"^\s*[\w\s]+?\s*=(?!=)", expression)
    body = expression[assignment.end():].strip() if assignment else expression
    if not body:
        msg = "Calculator assignment requires a right-hand expression."
        raise AutomationError(msg)
    numeric = re.sub(r"\[[^\]]+\]", "1", body)
    if not re.fullmatch(r"[0-9eE.\s()+*/^\-]+", numeric):
        return
    # Capstone numeric literals can have leading zeroes that Python integers reject.
    numeric = re.sub(r"(?<![\w.])0+(?=\d)", "", numeric)
    try:
        _ = ast.parse(numeric.replace("^", "**"), mode="eval")
    except (SyntaxError, RecursionError) as exc:
        msg = "Invalid arithmetic expression; check operands and operators."
        raise AutomationError(msg) from exc


def _find_calculator_toggle(snapshot: Snapshot) -> Control:
    """Find the Calculator palette toggle button in the active window."""
    if snapshot.truncated:
        msg = "Calculator window snapshot is incomplete; no toggle can be selected."
        raise AutomationError(msg)
    matches = [
        ctrl for ctrl in snapshot.controls
        if ctrl.visible and ctrl.enabled and ctrl.control_type == "CheckBox"
        and (
            ctrl.automation_id.endswith(CALCULATOR_TOGGLE_SUFFIX)
            or ctrl.name.strip() == CALCULATOR_NAME
        )
    ]
    if len(matches) != 1:
        msg = "Expected exactly one enabled Calculator palette toggle."
        raise AutomationError(msg)
    return matches[0]


def _is_calculator_open(app: Capstone, toggle_ctrl: Control) -> bool:
    """Check if the Calculator drawer is currently open."""
    node = app.control(toggle_ctrl.ref)
    with contextlib.suppress(Exception):
        if hasattr(node, "iface_toggle") and node.iface_toggle:
            toggle = node.iface_toggle
            v = getattr(toggle, "ToggleState", None)
            if isinstance(v, int):
                return bool(v == 1)
            v_curr = getattr(toggle, "CurrentToggleState", None)
            if isinstance(v_curr, int):
                return bool(v_curr == 1)
    return False


def _find_editor_controls(
    snapshot: Snapshot,
    *,
    require_unit: bool,
) -> tuple[Control, Control | None]:
    """Find the formula editor and unit editor controls in the calculator drawer."""
    if snapshot.truncated:
        msg = "Calculator window snapshot is incomplete; no editor can be selected."
        raise AutomationError(msg)
    formulas: list[Control] = []
    units: list[Control] = []

    for ctrl in snapshot.controls:
        if not ctrl.visible or not ctrl.enabled or ctrl.control_type != "Edit":
            continue
        aid_lower = ctrl.automation_id.lower()
        name_lower = ctrl.name.lower()
        if (
            "formula" in aid_lower
            or "formula" in name_lower
            or aid_lower.endswith(".calc")
        ):
            formulas.append(ctrl)
        elif "unit" in aid_lower or "unit" in name_lower:
            units.append(ctrl)

    if len(formulas) != 1:
        msg = "Expected exactly one enabled Calculator formula editor."
        raise AutomationError(msg)
    if require_unit and len(units) != 1:
        msg = "Expected exactly one enabled Calculator unit editor."
        raise AutomationError(msg)
    return formulas[0], units[0] if len(units) == 1 else None


def _set_editor_value(app: Capstone, handle: int, control: Control, value: str) -> None:
    node = app.control(control.ref)
    try:
        node.iface_value.SetValue(value)
    except (AttributeError, RuntimeError):
        app.click(handle, control.ref, allow_foreground=True)
        app.keys(handle, "^a{BACKSPACE}")
        app.type_text(value)


def _restore_calculator(app: Capstone, handle: int, *, failing: bool) -> None:
    try:
        fresh = app.snapshot(handle, depth=16, limit=10_000)
        toggle = _find_calculator_toggle(fresh)
        app.click(handle, toggle.ref, allow_foreground=True)
    except Exception:
        if not failing:
            raise


def _write_unit(app: Capstone, handle: int, unit: str) -> None:
    snapshot = app.snapshot(handle, depth=16, limit=10_000)
    _, unit_control = _find_editor_controls(snapshot, require_unit=True)
    if unit_control is None:
        msg = "Calculator unit editor disappeared after formula entry."
        raise AutomationError(msg)
    _set_editor_value(app, handle, unit_control, unit.strip())


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

    _validate_delimiters(raw_expr)
    _validate_arithmetic(raw_expr)
    if request.variables:
        msg = "Calculator variable bindings are not implemented; no input was sent."
        raise AutomationError(msg)

    calc_name = _parse_calculation_name(raw_expr)

    # 1. Inspect window and locate Calculator toggle
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    toggle_ctrl = _find_calculator_toggle(snapshot)
    was_open = _is_calculator_open(app, toggle_ctrl)

    opened_by_tool = False
    if not was_open:
        # Open Calculator panel
        app.click(request.handle, toggle_ctrl.ref, allow_foreground=True)
        opened_by_tool = True

    try:
        if opened_by_tool:
            snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
        # 2. Locate formula editor and unit editor controls
        formula_ctrl, _ = _find_editor_controls(
            snapshot, require_unit=bool(request.unit),
        )

        # 3. Enter formula
        _set_editor_value(app, request.handle, formula_ctrl, raw_expr)

        # 4. Enter unit if specified
        if request.unit:
            _write_unit(app, request.handle, request.unit)

        # Commit formula
        app.keys(request.handle, "{ENTER}")

        # 5. Status check
        status: CalculationStatus = "failed"
        detail = (
            f"Calculation '{calc_name}' was submitted, but registration and "
            "syntax validity could not be verified from Capstone. Inspect the "
            "Calculator before using this expression."
        )
        verified = False

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
            _restore_calculator(
                app, request.handle, failing=sys.exception() is not None,
            )
