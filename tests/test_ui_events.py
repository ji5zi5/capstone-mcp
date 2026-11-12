# Copyright 2026 Capstone MCP contributors.
"""Verify event-driven predicates without sleeps or timing-dependent retries."""

import ctypes
import os
from ctypes import wintypes

import pytest
import win32gui

from capstone_mcp.desktop import AutomationError
from capstone_mcp.ui_events import WM_CLIPBOARDUPDATE, StateChanges, WindowEvents


def test_notification_during_predicate_is_not_lost() -> None:
    # Given
    changes = StateChanges()
    calls = 0

    def predicate() -> str | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            changes.notify()
            return None
        return "ready"

    # When
    result = changes.until(predicate, 1)
    # Then
    assert result == "ready"
    assert calls == 2


def test_unconfirmed_state_expires_at_deadline() -> None:
    # Given
    changes = StateChanges()

    def absent() -> str | None:
        return None

    # When / Then
    with pytest.raises(AutomationError):
        _ = changes.until(absent, 0)


def test_real_native_event_reaches_process_filtered_listener() -> None:
    # Given: an owned invisible window, not the user's Capstone window.
    handle = win32gui.CreateWindowEx(
        0, "STATIC", "event-test", 0, 0, 0, 1, 1, 0, 0, 0, None,
    )
    user32 = ctypes.WinDLL("user32")
    user32.NotifyWinEvent.argtypes = (
        wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG,
    )
    user32.NotifyWinEvent.restype = None
    try:
        with WindowEvents(os.getpid()) as events:
            generation = events.changes.generation
            # When: the listener is armed before this exact native event.
            user32.NotifyWinEvent(0x800C, handle, 0, 0)
            observed = events.changes.until(
                lambda: True if events.changes.generation > generation else None, 5,
            )
            # Then
            assert observed
        assert not events.thread.is_alive()
    finally:
        win32gui.DestroyWindow(handle)


def test_clipboard_listener_receives_message_without_polling() -> None:
    # Given: an owned message window; the user's clipboard is never modified.
    user32 = ctypes.WinDLL("user32")
    user32.PostMessageW.argtypes = (
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    )
    user32.PostMessageW.restype = wintypes.BOOL
    with WindowEvents(os.getpid(), clipboard=True) as events:
        generation = events.changes.generation
        # When: deliver the exact clipboard-update message after subscription.
        assert user32.PostMessageW(
            events.clipboard_handle, WM_CLIPBOARDUPDATE, 0, 0,
        )
        observed = events.changes.until(
            lambda: True if events.changes.generation > generation else None, 5,
        )
        # Then: the native message wakes the state observer.
        assert observed
    assert not events.thread.is_alive()
