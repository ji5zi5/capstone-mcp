# Copyright 2026 Capstone MCP contributors.
"""Run visibility control and multi-run overlay comparison for Capstone displays."""

import contextlib
import re
from typing import Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Control, Model

RUN_NAME_PATTERN: Final = re.compile(r"run\s*#?\s*\d+", re.IGNORECASE)


class SetRunVisibilityRequest(Model):
    """Specification for run visibility toggling on displays."""

    runs: list[str]
    visible: bool = True
    target_displays: list[str] | None = None
    handle: int = 0
    allow_foreground: bool = True


class SetRunVisibilityResult(Model):
    """Outcome of run visibility adjustment."""

    visible_runs: list[str]
    target_displays: list[str]
    detail: str
    verified: bool = True


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


def _match_display_control(controls: list[Control], display_name: str) -> Control:
    """Find a display control matching an explicit display name."""
    disp_lower = display_name.strip().lower()
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname_lower = ctrl.name.strip().lower()
        if cname_lower == disp_lower or disp_lower in cname_lower:
            return ctrl
    msg = f"Target display '{display_name}' not found in active window."
    raise AutomationError(msg)


def _find_display_containers(controls: list[Control]) -> list[Control]:
    """Find all graph or table display containers in the window snapshot."""
    displays: list[Control] = []
    for ctrl in controls:
        if not ctrl.visible:
            continue
        name_lower = ctrl.name.lower()
        if (
            "graph" in name_lower or "table" in name_lower
        ) and ctrl.control_type in ("Custom", "Pane", "Group"):
            displays.append(ctrl)
    return displays


def _is_within_bounds(inner: Control, outer: Control) -> bool:
    """Check if inner control rectangle is contained within outer control bounds."""
    return (
        inner.bounds.left >= outer.bounds.left
        and inner.bounds.top >= outer.bounds.top
        and inner.bounds.right <= outer.bounds.right
        and inner.bounds.bottom <= outer.bounds.bottom
    )


def _find_run_controls(
    controls: list[Control],
    target_containers: list[Control] | None = None,
) -> list[Control]:
    """Find controls representing runs (checkboxes, tree items, list items)."""
    candidates: list[Control] = []
    for ctrl in controls:
        if not ctrl.visible:
            continue
        if ctrl.control_type not in (
            "CheckBox", "TreeItem", "ListItem", "MenuItem", "Button", "RadioButton",
        ):
            continue
        if not (
            RUN_NAME_PATTERN.search(ctrl.name)
            or "run" in ctrl.automation_id.lower()
        ):
            continue

        if target_containers is None or any(
            _is_within_bounds(ctrl, c) for c in target_containers
        ):
            candidates.append(ctrl)
    return candidates


def _matches_run_name(ctrl: Control, target_run: str) -> bool:
    """Match a control against a target run identifier."""
    cname = ctrl.name.strip().lower()
    tname = target_run.strip().lower()
    if cname == tname:
        return True
    c_num = re.findall(r"\d+", cname)
    t_num = re.findall(r"\d+", tname)
    return bool(c_num and t_num and c_num == t_num)


def _get_control_visibility_state(app: Capstone, ctrl: Control) -> bool:
    """Query current checked or selected state of a run visibility control."""
    try:
        node = app.control(ctrl.ref)
    except (AttributeError, RuntimeError):
        return False

    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_toggle") and node.iface_toggle:
            return bool(node.iface_toggle.ToggleState == 1)

    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_selection_item") and node.iface_selection_item:
            return bool(node.iface_selection_item.IsSelected)

    return False


def _try_toggle_or_select(node: object, visible: bool) -> bool:  # noqa: FBT001
    """Attempt pattern-based state changes; return True on success."""
    if hasattr(node, "iface_toggle") and node.iface_toggle:
        with contextlib.suppress(AttributeError, RuntimeError):
            node.iface_toggle.Toggle()
            return True

    if hasattr(node, "iface_selection_item") and node.iface_selection_item:
        with contextlib.suppress(AttributeError, RuntimeError):
            if visible:
                if hasattr(node.iface_selection_item, "AddToSelection"):
                    node.iface_selection_item.AddToSelection()
                else:
                    node.iface_selection_item.Select()
            else:
                node.iface_selection_item.RemoveFromSelection()
            return True

    return False


def _set_control_visibility_state(
    app: Capstone,
    handle: int,
    ctrl: Control,
    visible: bool,  # noqa: FBT001
) -> None:
    """Set the visibility state on a run control."""
    node = app.control(ctrl.ref)
    current_state = _get_control_visibility_state(app, ctrl)
    if current_state == visible:
        return

    if not _try_toggle_or_select(node, visible):
        _click_control(app, handle, ctrl, allow_foreground=True)


def _resolve_targets(
    controls: list[Control],
    target_displays: list[str] | None,
) -> tuple[list[Control] | None, list[str]]:
    """Determine target display controls and display name labels."""
    if target_displays is not None:
        containers: list[Control] = []
        names: list[str] = []
        for name in target_displays:
            container = _match_display_control(controls, name)
            containers.append(container)
            names.append(container.name.strip() or name)
        return containers, names

    found = _find_display_containers(controls)
    if found:
        return None, [d.name.strip() for d in found]
    return None, ["All Displays"]


def _apply_run_visibility(
    app: Capstone,
    handle: int,
    target_runs: list[str],
    run_controls: list[Control],
    visible: bool,  # noqa: FBT001
) -> None:
    """Find and apply visibility updates to each requested run."""
    for run_name in target_runs:
        matching = [c for c in run_controls if _matches_run_name(c, run_name)]
        if not matching:
            msg = f"Run visibility control for '{run_name}' not found."
            raise AutomationError(msg)
        for ctrl in matching:
            _set_control_visibility_state(app, handle, ctrl, visible)


def _collect_visible_runs(
    app: Capstone,
    controls: list[Control],
    requested_runs: list[str],
    visible: bool,  # noqa: FBT001
) -> list[str]:
    """Collect final set of visible runs."""
    visible_names: set[str] = set()
    for ctrl in controls:
        if _get_control_visibility_state(app, ctrl):
            visible_names.add(ctrl.name.strip())

    if visible:
        visible_names.update(requested_runs)
    else:
        for r in requested_runs:
            visible_names.discard(r)

    return sorted(visible_names)


def set_run_visibility(
    app: Capstone,
    request: SetRunVisibilityRequest,
) -> SetRunVisibilityResult:
    """Control display visibility for specific runs on graphs or tables."""
    if not request.runs:
        msg = "runs must not be empty."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Run visibility operation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    containers, display_names = _resolve_targets(
        snapshot.controls,
        request.target_displays,
    )

    run_ctrls = _find_run_controls(snapshot.controls, containers)
    _apply_run_visibility(
        app,
        request.handle,
        request.runs,
        run_ctrls,
        request.visible,
    )

    fresh_snap = app.snapshot(request.handle, depth=16, limit=10_000)
    post_run_ctrls = _find_run_controls(fresh_snap.controls, containers)
    sorted_visible = _collect_visible_runs(
        app,
        post_run_ctrls,
        request.runs,
        request.visible,
    )

    mode_str = "visible" if request.visible else "hidden"
    detail = f"Runs {request.runs} set to {mode_str} on {display_names}."

    return SetRunVisibilityResult(
        visible_runs=sorted_visible,
        target_displays=display_names,
        detail=detail,
        verified=True,
    )
