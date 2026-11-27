# Copyright 2026 Capstone MCP contributors.
"""Native round trip on a disposable Windows runner with its own clipboard."""

import os

import pytest
import win32clipboard
import win32con

from capstone_mcp.graphs import inspection
from capstone_mcp.ui_events import WindowEvents


@pytest.mark.skipif(
    os.environ.get("CAPSTONE_TEST_DISPOSABLE_CLIPBOARD") != "1",
    reason="requires a disposable Windows session with a dedicated clipboard",
)
def test_owned_clipboard_restores_formats_and_preserves_a_later_copy() -> None:
    graph_format = win32clipboard.RegisterClipboardFormat(inspection.GRAPH_MIME)
    pid = os.getpid()
    with WindowEvents(pid, clipboard=True) as events:
        hwnd = events.clipboard_handle
        assert hwnd

        def copy(text: str, payload: bytes) -> None:
            win32clipboard.OpenClipboard(hwnd)
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                win32clipboard.SetClipboardData(graph_format, payload)
            finally:
                win32clipboard.CloseClipboard()

        copy("측정 Δ", b"previous")
        original, before = inspection._backup_clipboard()
        assert original[win32con.CF_UNICODETEXT] == "측정 Δ"
        assert original[graph_format].startswith(b"previous")
        copy("Graph", b"current")
        observation = inspection._copied_graph(before, pid)
        assert observation is not None
        payload, copied = observation
        assert isinstance(payload, bytes)
        assert payload.startswith(b"current")
        inspection._restore_clipboard(original, copied_sequence=copied, owner_handle=hwnd)
        restored, _ = inspection._backup_clipboard()
        assert restored == original
        copy("More recent copy", b"newer")
        inspection._restore_clipboard(original, copied_sequence=copied, owner_handle=hwnd)
        recent, _ = inspection._backup_clipboard()
        assert recent[win32con.CF_UNICODETEXT] == "More recent copy"
