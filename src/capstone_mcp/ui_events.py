# Copyright 2026 Capstone MCP contributors.
"""Bounded state confirmation driven by native window/accessibility events."""

import ctypes
import time
from collections.abc import Callable
from ctypes import wintypes
from threading import Condition, Event, Thread
from types import TracebackType
from typing import Final, Self

import win32gui

from capstone_mcp.desktop import AutomationError

EVENT_MIN: Final = 1
EVENT_MAX: Final = 0x7FFFFFFF
WM_QUIT: Final = 0x0012
WM_CLIPBOARDUPDATE: Final = 0x031D
READY_TIMEOUT: Final = 5


class _User32(ctypes.WinDLL):
    """Typed result for the hook pointer returned by the configured native ABI."""

    def __init__(self) -> None:
        super().__init__("user32", use_last_error=True)
        function = self["SetWinEventHook"]
        function.argtypes = (
            wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        )
        function.restype = wintypes.HANDLE
        self.SetWinEventHook: Callable[
            [int, int, int | None, ctypes.c_void_p, int, int, int], int | None,
        ] = function


class StateChanges:
    """A generation counter prevents lost signals during predicate evaluation."""

    def __init__(self) -> None:
        """Allocate a condition without an initial notification."""
        self.condition: Condition = Condition()
        self.generation: int = 0

    def notify(self) -> None:
        """Wake all predicates after an observed native event."""
        with self.condition:
            self.generation += 1
            self.condition.notify_all()

    def until[T](
        self, predicate: Callable[[], T | None], timeout: float,
        *, description: str = "Expected Capstone state",
    ) -> T:
        """Evaluate immediately, then only after events, until a bounded deadline."""
        deadline = time.monotonic() + timeout
        while True:
            with self.condition:
                generation = self.generation
            result = predicate()
            if result is not None:
                return result
            with self.condition:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.condition.wait_for(
                    lambda previous=generation: self.generation != previous,
                    timeout=remaining,
                ):
                    msg = f"{description} was not confirmed before timeout."
                    raise AutomationError(msg)


class WindowEvents:
    """Subscribe before input; own the hook and message loop on one native thread."""

    def __init__(self, process_id: int, *, clipboard: bool = False) -> None:
        """Filter native events to one attached process."""
        self.process_id: int = process_id
        self.changes: StateChanges = StateChanges()
        self.ready: Event = Event()
        self.thread: Thread = Thread(target=self._pump, daemon=True)
        self.thread_id: int = 0
        self.error: str | None = None
        self.clipboard: bool = clipboard
        self.clipboard_handle: int = 0

    def __enter__(self) -> Self:
        """Wait for hook registration before permitting the caller's input."""
        self.thread.start()
        if not self.ready.wait(READY_TIMEOUT):
            msg = "Native event listener did not start."
            raise AutomationError(msg)
        if self.error is not None:
            raise AutomationError(self.error)
        return self

    def __exit__(
        self, _kind: type[BaseException] | None,
        _error: BaseException | None, _traceback: TracebackType | None,
    ) -> None:
        """Stop the message loop; the registering thread removes its own hook."""
        user32 = _User32()
        user32.PostThreadMessageW.argtypes = (
            wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        )
        user32.PostThreadMessageW.restype = wintypes.BOOL
        if not user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        self.thread.join(READY_TIMEOUT)
        if self.thread.is_alive():
            msg = "Native event listener did not stop."
            raise AutomationError(msg)

    def _pump(self) -> None:
        """Receive out-of-context accessibility events without calling UIA here."""
        user32 = _User32()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self.thread_id = kernel32.GetCurrentThreadId()
        callback_type = ctypes.WINFUNCTYPE(
            None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
            wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
        )

        def changed(
            _hook: int, _event: int, _window: int, _object: int,
            _child: int, _thread: int, _time: int,
        ) -> None:
            self.changes.notify()

        callback = callback_type(changed)
        user32.UnhookWinEvent.argtypes = (wintypes.HANDLE,)
        user32.UnhookWinEvent.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
        )
        user32.GetMessageW.restype = wintypes.BOOL
        user32.PeekMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG), wintypes.HWND,
            wintypes.UINT, wintypes.UINT, wintypes.UINT,
        )
        user32.PeekMessageW.restype = wintypes.BOOL
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        hook: int | None = user32.SetWinEventHook(
            EVENT_MIN, EVENT_MAX, None, ctypes.cast(callback, ctypes.c_void_p),
            self.process_id, 0, 0,
        )
        if not hook:
            self.error = str(ctypes.WinError(ctypes.get_last_error()))
            self.ready.set()
            return
        if self.clipboard:
            user32.AddClipboardFormatListener.argtypes = (wintypes.HWND,)
            user32.AddClipboardFormatListener.restype = wintypes.BOOL
            user32.RemoveClipboardFormatListener.argtypes = (wintypes.HWND,)
            user32.RemoveClipboardFormatListener.restype = wintypes.BOOL
            self.clipboard_handle = win32gui.CreateWindowEx(
                0, "STATIC", "Capstone clipboard observer", 0,
                0, 0, 0, 0, -3, 0, 0, None,
            )
            if not user32.AddClipboardFormatListener(self.clipboard_handle):
                self.error = str(ctypes.WinError(ctypes.get_last_error()))
                win32gui.DestroyWindow(self.clipboard_handle)
                user32.UnhookWinEvent(hook)
                self.ready.set()
                return
        self.ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_CLIPBOARDUPDATE:
                    self.changes.notify()
        finally:
            if self.clipboard_handle:
                user32.RemoveClipboardFormatListener(self.clipboard_handle)
                win32gui.DestroyWindow(self.clipboard_handle)
            user32.UnhookWinEvent(hook)
