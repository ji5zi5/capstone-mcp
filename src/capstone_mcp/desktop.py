# Copyright 2026 Capstone MCP contributors.
"""Capstone-scoped Windows UI Automation adapter."""

from io import BytesIO
from itertools import islice
from pathlib import Path
from typing import Final, assert_never
from uuid import uuid4

import win32gui
from PIL import ImageGrab
from pywinauto import Application, Desktop
from pywinauto.application import ProcessNotFoundError, process_module
from pywinauto.controls.hwndwrapper import HwndWrapper
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import find_windows

from capstone_mcp.models import Action, Bounds, Control, Result, Snapshot, Window

EXECUTABLE: Final = Path("C:/Program Files/PASCO scientific/Capstone/Capstone.exe")


class AutomationError(RuntimeError):
    """An unmet precondition prevents input delivery."""


def bounds(control: UIAWrapper) -> Bounds:
    """Read physical screen coordinates from UIA."""
    rect = control.rectangle()
    return Bounds(left=rect.left, top=rect.top, right=rect.right, bottom=rect.bottom)


def describe(window: UIAWrapper) -> Window:
    """Serialize a top-level window."""
    return Window(
        handle=window.handle,
        title=window.window_text(),
        process_id=window.process_id(),
        bounds=bounds(window),
    )


class Capstone:
    """Keep references for the latest snapshot; all calls run on one MCP thread."""

    def __init__(self) -> None:
        """Start detached; never launch a program merely by importing the server."""
        self.pid: int | None = None
        self.session_id: str = uuid4().hex
        self.generation: int = 0
        self.refs: dict[str, UIAWrapper] = {}
        self.window_cache: dict[int, UIAWrapper] = {}

    def attach(
        self, *, launch: bool = False, process_id: int | None = None,
    ) -> list[Window]:
        """Attach by exact executable path, optionally starting Capstone."""
        app = Application(backend="uia")
        if process_id is not None:
            if launch or Path(process_module(process_id)) != EXECUTABLE:
                msg = (
                    "Explicit process must be installed Capstone; launch must be false."
                )
                raise AutomationError(msg)
            _ = app.connect(process=process_id)
        else:
            try:
                _ = app.connect(path=str(EXECUTABLE))
            except ProcessNotFoundError:
                if not launch:
                    raise
                _ = app.start(
                    f'"{EXECUTABLE}"', work_dir=str(EXECUTABLE.parent), timeout=30,
                )
        self.pid = app.process
        self.refs.clear()
        self.window_cache.clear()
        return self.windows()

    def windows(self) -> list[Window]:
        """List visible windows only within the attached process."""
        if self.pid is None:
            msg = "Call capstone_attach first."
            raise AutomationError(msg)
        handles = find_windows(process=self.pid, backend="win32", visible_only=True)
        result: list[Window] = []
        for handle in handles:
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            result.append(Window(
                handle=handle, title=win32gui.GetWindowText(handle),
                process_id=self.pid,
                bounds=Bounds(left=left, top=top, right=right, bottom=bottom),
            ))
        return result

    def window(self, handle: int) -> UIAWrapper:
        """Reject handles outside the attached application."""
        if not any(w.handle == handle for w in self.windows()):
            msg = "Window is not a visible window of the attached Capstone process."
            raise AutomationError(msg)
        if handle not in self.window_cache:
            self.window_cache[handle] = (
                Desktop(backend="uia").window(handle=handle).wrapper_object()
            )
        return self.window_cache[handle]

    def snapshot(self, handle: int, depth: int, limit: int) -> Snapshot:
        """Traverse a bounded tree and invalidate previous control references."""
        root = self.window(handle)
        self.generation += 1
        self.refs.clear()
        controls: list[Control] = []
        pending: list[tuple[UIAWrapper, str | None, int]] = [(root, None, 0)]
        truncated = False
        while pending and len(controls) < limit:
            node, parent, level = pending.pop()
            ref = f"{self.session_id}:{self.generation}:{len(controls)}"
            self.refs[ref] = node
            info = node.element_info
            controls.append(Control(
                ref=ref, parent=parent, name=info.name,
                control_type=info.control_type, automation_id=info.automation_id,
                enabled=node.is_enabled(), visible=node.is_visible(),
                bounds=bounds(node),
            ))
            child_budget = 1 if level >= depth else limit - len(controls) + 1
            children = list(islice(node.iter_children(), child_budget))
            if level < depth:
                pending.extend((child, ref, level + 1) for child in reversed(children))
            elif children:
                truncated = True
        return Snapshot(
            window=describe(root), controls=controls,
            truncated=truncated or bool(pending),
        )

    def focus_window(self, handle: int) -> UIAWrapper:
        """Activate the native HWND; UIA SetFocus alone may not activate Qt."""
        window = self.window(handle)
        _ = HwndWrapper(handle).set_focus()
        return window

    def control(self, ref: str) -> UIAWrapper:
        """Resolve only current references and recheck process and enabled state."""
        if ref not in self.refs:
            msg = "Unknown or stale ref. Take a new snapshot."
            raise AutomationError(msg)
        node = self.refs[ref]
        if node.process_id() != self.pid or not node.is_enabled():
            msg = "Control is disabled or no longer belongs to Capstone."
            raise AutomationError(msg)
        return node

    def act(
        self, ref: str, action: Action, *, allow_foreground: bool = True,
    ) -> Result:
        """Activate by physical click; use UIA for non-invoke control patterns."""
        node = self.control(ref)
        self.refs.clear()
        match action:
            case Action.INVOKE:
                if not allow_foreground:
                    msg = "Activation uses mouse input; set allow_foreground=true."
                    raise AutomationError(msg)
                _ = HwndWrapper(node.top_level_parent().handle).set_focus()
                rect = node.rectangle()
                node.click_input(
                    button="left",
                    coords=((rect.left + rect.right) // 2,
                            (rect.top + rect.bottom) // 2),
                    absolute=True,
                )
                return Result(detail="Control clicked; inspect to verify.")
            case Action.TOGGLE:
                node.iface_toggle.Toggle()
                return Result(detail="Toggle delivered; inspect to verify.")
            case Action.SELECT:
                node.iface_selection_item.Select()
                return Result(detail="Selection delivered; inspect to verify.")
            case Action.EXPAND:
                _ = node.expand()
                return Result(detail="Expand delivered; inspect to verify.")
            case Action.COLLAPSE:
                _ = node.collapse()
                return Result(detail="Collapse delivered; inspect to verify.")
            case Action.FOCUS:
                _ = node.set_focus()
                return Result(detail="Focus delivered; inspect to verify.")
        assert_never(action)

    def set_value(self, ref: str, value: str) -> Result:
        """Set a control through its Value pattern, preserving literal text."""
        self.control(ref).iface_value.SetValue(value)
        self.refs.clear()
        return Result(detail="Value delivered; take a snapshot to verify.")

    def screenshot(self, handle: int) -> bytes:
        """Capture the target HWND rather than unrelated overlapping windows."""
        window = self.window(handle)
        if win32gui.IsIconic(window.handle):
            msg = (
                "Capstone window is minimized. "
                "Restore it before requesting a screenshot."
            )
            raise AutomationError(msg)
        try:
            with BytesIO() as output, ImageGrab.grab(window=window.handle) as image:
                image.save(output, format="PNG")
                return output.getvalue()
        except OSError as error:
            msg = (
                "Capstone window capture failed. Ensure the window is restored "
                "and the interactive desktop is available, then retry."
            )
            raise AutomationError(msg) from error

    def keys(
        self, handle: int, keys: str, *, allow_foreground: bool = True,
        unicode_input: bool = False,
    ) -> Result:
        """Send key syntax with foreground input enabled unless explicitly disabled."""
        if not allow_foreground:
            msg = "Keyboard input changes focus. Set allow_foreground=true explicitly."
            raise AutomationError(msg)
        _ = self.focus_window(handle).type_keys(
            keys, with_spaces=True, set_foreground=False, pause=0,
            vk_packet=unicode_input,
        )
        self.refs.clear()
        return Result(detail="Keys delivered; inspect the window to verify.")
