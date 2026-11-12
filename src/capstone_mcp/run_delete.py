# Copyright 2026 Capstone MCP contributors.
"""Dedicated run deletion in Capstone Data Summary with modal auto-dismiss."""

import contextlib
import re

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Control, Model


class DeleteRunRequest(Model):
    """Specification of target run to delete."""

    run_name: str = "last_run"
    handle: int = 0
    allow_foreground: bool = True


class DeleteRunResult(Model):
    """Confirmation of verified run deletion."""

    deleted_run: str
    verified: bool
    detail: str


def _find_run_items(controls: list[Control]) -> list[Control]:
    """Find all Run items in Data Summary tree."""
    return [
        ctrl
        for ctrl in controls
        if (
            ctrl.visible
            and ctrl.control_type == "TreeItem"
            and re.search(r"run\s*#?\d+", ctrl.name, re.IGNORECASE)
        )
    ]


def _dismiss_confirmation_dialog(app: Capstone, main_handle: int) -> None:
    """Detect and auto-confirm any deletion confirmation modal dialog."""
    all_windows = app.windows()
    for win in all_windows:
        if win.handle == main_handle:
            continue
        # Inspect dialog controls
        with contextlib.suppress(Exception):
            dialog_snap = app.snapshot(win.handle, depth=6, limit=100)
            for ctrl in dialog_snap.controls:
                if not ctrl.visible or ctrl.control_type != "Button":
                    continue
                name_lower = ctrl.name.strip().lower()
                aid_lower = ctrl.automation_id.lower()
                if name_lower in ("yes", "ok", "confirm") or "yes" in aid_lower:
                    app.click(win.handle, ctrl.ref, allow_foreground=True)
                    return
            # If no named button matched, send ENTER to dialog
            app.keys(win.handle, "{ENTER}", allow_foreground=True)


def delete_run(app: Capstone, request: DeleteRunRequest) -> DeleteRunResult:
    """Delete a target run or the latest run from Data Summary safely."""
    if not request.allow_foreground:
        msg = "Run deletion requires allow_foreground=true."
        raise AutomationError(msg)

    # 1. Take snapshot of main window
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    all_runs = _find_run_items(snapshot.controls)

    target_run_ctrl: Control | None = None
    target_name: str = ""

    if request.run_name.strip().lower() == "last_run":
        if not all_runs:
            msg = "No runs found to delete in Data Summary."
            raise AutomationError(msg)
        target_run_ctrl = all_runs[-1]
        target_name = target_run_ctrl.name.strip()
    else:
        for ctrl in snapshot.controls:
            if (
                ctrl.visible
                and ctrl.control_type == "TreeItem"
                and ctrl.name.strip() == request.run_name.strip()
            ):
                target_run_ctrl = ctrl
                target_name = ctrl.name.strip()
                break
        if not target_run_ctrl:
            msg = f"Run with name '{request.run_name}' not found in Data Summary."
            raise AutomationError(msg)

    # 2. Trigger deletion on target control
    node = app.control(target_run_ctrl.ref)
    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_selection_item") and node.iface_selection_item:
            node.iface_selection_item.Select()
    with contextlib.suppress(AttributeError, RuntimeError):
        node.set_focus()

    app.keys(request.handle, "{DELETE}", allow_foreground=True)

    # 3. Check and auto-dismiss confirmation modal if opened
    _dismiss_confirmation_dialog(app, request.handle)

    # 4. Verify deletion via fresh snapshot
    verify_snap = app.snapshot(request.handle, depth=16, limit=10_000)
    still_present = any(
        ctrl.visible
        and ctrl.control_type == "TreeItem"
        and ctrl.name.strip() == target_name
        for ctrl in verify_snap.controls
    )

    verified = not still_present
    detail = (
        f"Run '{target_name}' successfully deleted."
        if verified
        else f"Delete command issued for '{target_name}', but item is still present."
    )

    return DeleteRunResult(
        deleted_run=target_name,
        verified=verified,
        detail=detail,
    )
