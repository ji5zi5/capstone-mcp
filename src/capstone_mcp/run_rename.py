# Copyright 2026 Capstone MCP contributors.
"""Dedicated run renaming in Capstone Data Summary."""

import contextlib

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Model


class RenameRunRequest(Model):
    """Specification of target run and replacement title."""

    old_name: str
    new_name: str
    handle: int = 0
    allow_foreground: bool = True


class RenameRunResult(Model):
    """Confirmation of verified run renaming."""

    old_name: str
    new_name: str
    verified: bool
    detail: str


def rename_run(app: Capstone, request: RenameRunRequest) -> RenameRunResult:
    """Find the target run in Data Summary and rename it reliably."""
    if not request.new_name.strip():
        msg = "new_name must not be empty."
        raise AutomationError(msg)

    # 1. Take snapshot to locate the target run item
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    target_control = None
    for control in snapshot.controls:
        if (
            control.visible
            and control.control_type == "TreeItem"
            and control.name.strip() == request.old_name.strip()
        ):
            target_control = control
            break

    if target_control is None:
        msg = f"Run item with name '{request.old_name}' not found in Data Summary."
        raise AutomationError(msg)

    node = app.control(target_control.ref)

    # 2. Try ValuePattern direct set
    value_set = False
    with contextlib.suppress(AttributeError, RuntimeError):
        node.iface_value.SetValue(request.new_name)
        value_set = True

    if not value_set:
        # Fallback: Select node, trigger edit key (F2), and set text
        if not request.allow_foreground:
            msg = "Renaming via inline editor requires allow_foreground=true."
            raise AutomationError(msg)
        with contextlib.suppress(AttributeError, RuntimeError):
            node.iface_selection_item.Select()
        _ = node.set_focus()
        _ = app.keys(request.handle, "{F2}", allow_foreground=True)
        # Type new name and hit Enter
        _ = app.keys(
            request.handle, f"^a{request.new_name}{{ENTER}}",
            allow_foreground=True, unicode_input=True,
        )

    # 3. Verify via fresh snapshot
    verification_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    renamed = any(
        c.visible
        and c.control_type == "TreeItem"
        and c.name.strip() == request.new_name.strip()
        for c in verification_snapshot.controls
    )

    detail = (
        f"Run successfully renamed from '{request.old_name}' to '{request.new_name}'."
        if renamed
        else f"Rename issued, but '{request.new_name}' was not confirmed in tree."
    )
    return RenameRunResult(
        old_name=request.old_name,
        new_name=request.new_name,
        verified=renamed,
        detail=detail,
    )
