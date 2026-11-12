# Copyright 2026 Capstone MCP contributors.
"""Capstone-scoped Windows UI Automation adapter."""

from io import BytesIO
from itertools import islice
from pathlib import Path
from typing import Final, assert_never
from uuid import uuid4

import win32gui
from PIL import Image, ImageGrab
from pywinauto import Application, Desktop, mouse
from pywinauto.application import ProcessNotFoundError, process_module
from pywinauto.controls.hwndwrapper import HwndWrapper
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import find_windows

from capstone_mcp.models import Action, Bounds, Control, Result, Snapshot, Window

EXECUTABLE: Final = Path("C:/Program Files/PASCO scientific/Capstone/Capstone.exe")
CROP_COORDINATE_COUNT: Final = 4


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


def tokenize_keys(keys_str: str) -> list[str]:
    """Tokenize pywinauto key string into characters and braced tokens."""
    tokens: list[str] = []
    i = 0
    while i < len(keys_str):
        if keys_str[i] == "{" and "}" in keys_str[i:]:
            end = keys_str.index("}", i) + 1
            tokens.append(keys_str[i:end])
            i = end
        else:
            tokens.append(keys_str[i])
            i += 1
    return tokens


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

    def click_point(
        self,
        handle: int,
        x: int,
        y: int,
        button: str = "left",
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Click at absolute screen coordinates within target window."""
        if not allow_foreground:
            msg = "Coordinate clicking uses mouse input; set allow_foreground=true."
            raise AutomationError(msg)
        _ = self.focus_window(handle)
        mouse.click(button=button, coords=(x, y))
        return Result(detail=f"Clicked at ({x}, {y}) with {button} button.")

    def screenshot(
        self, handle: int, *, scale: float = 1.0,
        crop_region: list[int] | None = None,
    ) -> bytes:
        """Capture the target HWND rather than unrelated overlapping windows."""
        if scale <= 0.0 or scale > 1.0:
            msg = "scale must be a positive float <= 1.0."
            raise AutomationError(msg)
        if crop_region is not None and len(crop_region) != CROP_COORDINATE_COUNT:
            msg = (
                "crop_region must contain exactly 4 integers: "
                "[left, top, right, bottom]."
            )
            raise AutomationError(msg)
        window = self.window(handle)
        with BytesIO() as output, ImageGrab.grab(window=window.handle) as raw:
            processed = raw
            if crop_region is not None:
                processed = processed.crop((
                    crop_region[0], crop_region[1], crop_region[2], crop_region[3],
                ))
            if scale != 1.0:
                new_width = max(1, int(processed.width * scale))
                new_height = max(1, int(processed.height * scale))
                processed = processed.resize(
                    (new_width, new_height), Image.Resampling.LANCZOS,
                )
            processed.save(output, format="PNG")
            return output.getvalue()

    def keys(
        self, handle: int, keys: str, *, allow_foreground: bool = True,
        unicode_input: bool = False,
    ) -> Result:
        """Send key syntax with foreground input enabled unless explicitly disabled."""
        if not allow_foreground:
            msg = "Keyboard input changes focus. Set allow_foreground=true explicitly."
            raise AutomationError(msg)
        target = self.focus_window(handle)
        if unicode_input:
            initial_windows = {w.handle for w in self.windows()}
            tokens = tokenize_keys(keys)
            typed_tokens: list[str] = []
            for token in tokens:
                _ = target.type_keys(
                    token, with_spaces=True, set_foreground=False, pause=0,
                    vk_packet=True,
                )
                typed_tokens.append(token)
                current_windows = self.windows()
                new_popups = [
                    w for w in current_windows if w.handle not in initial_windows
                ]
                if new_popups:
                    self.refs.clear()
                    typed_str = "".join(typed_tokens)
                    popup = new_popups[0]
                    return Result(
                        delivered=True,
                        interrupted=True,
                        typed_text=typed_str,
                        popup_window=popup,
                        detail=(
                            f"Typing interrupted by popup window '{popup.title}' "
                            f"(handle {popup.handle})."
                        ),
                    )
        else:
            _ = target.type_keys(
                keys, with_spaces=True, set_foreground=False, pause=0,
                vk_packet=False,
            )
        self.refs.clear()
        return Result(detail="Keys delivered; inspect the window to verify.")
