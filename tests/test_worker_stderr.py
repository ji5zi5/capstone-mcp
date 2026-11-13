# Copyright 2026 Capstone MCP contributors.
"""Unit tests for subprocess stderr circular buffer and crash diagnostics."""

from __future__ import annotations

import collections
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker, NativeSessionError

if TYPE_CHECKING:
    from pathlib import Path


def test_worker_initializes_bounded_stderr_buffer() -> None:
    """Verify worker initializes an empty circular buffer with maxlen 200."""
    worker = AutomationWorker()
    assert isinstance(worker.stderr_buffer, collections.deque)
    assert worker.stderr_buffer.maxlen == 200
    assert len(worker.stderr_buffer) == 0


def test_worker_captures_stderr_and_bounds_line_length(tmp_path: Path) -> None:
    """Verify worker daemon reader captures stderr and clips lines to 4KB."""
    # Create a helper script that prints to stderr (including a line > 4KB) and waits
    script = tmp_path / "stderr_producer.py"
    script.write_text(
        "import sys, time\n"
        "sys.stderr.write('line 1: startup\\n')\n"
        "sys.stderr.write('line 2: initializing native COM\\n')\n"
        "sys.stderr.write('X' * 5000 + '\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )

    worker = AutomationWorker(timeout=5)

    # Override _spawn to run our helper script
    def custom_spawn() -> subprocess.Popen[str]:
        return subprocess.Popen(  # noqa: S603
            [sys.executable, "-u", str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

    worker._spawn = custom_spawn  # pyright: ignore[reportPrivateUsage]
    proc = worker._spawn()  # pyright: ignore[reportPrivateUsage]
    worker.process = proc
    worker._start_stderr_reader(proc.stderr)  # pyright: ignore[reportPrivateUsage]

    # Wait briefly for reader thread to consume stderr
    time.sleep(0.3)

    assert len(worker.stderr_buffer) >= 3
    assert worker.stderr_buffer[0] == "line 1: startup\n"
    assert worker.stderr_buffer[1] == "line 2: initializing native COM\n"
    # Long line must be clipped to at most 4096 characters per read
    assert len(worker.stderr_buffer[2]) <= 4096

    proc.terminate()
    _ = proc.wait(timeout=2)


def test_worker_caps_buffer_at_200_lines(tmp_path: Path) -> None:
    """Verify buffer caps at 200 lines and discards older lines."""
    script = tmp_path / "flood_stderr.py"
    script.write_text(
        "import sys, time\n"
        "for i in range(250):\n"
        "    sys.stderr.write(f'stderr message {i}\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(1)\n",
        encoding="utf-8",
    )

    worker = AutomationWorker(timeout=5)
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-u", str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    worker.process = proc
    worker._start_stderr_reader(proc.stderr)  # pyright: ignore[reportPrivateUsage]

    time.sleep(0.4)

    assert len(worker.stderr_buffer) == 200
    # Oldest messages (0..49) discarded; contains recent messages
    assert "stderr message 249\n" in worker.stderr_buffer[-1]

    proc.terminate()
    _ = proc.wait(timeout=2)


def test_worker_crash_attaches_stderr_to_native_session_error(
    tmp_path: Path,
) -> None:
    """Verify unexpected worker termination surfaces stderr traceback."""
    script = tmp_path / "crashing_worker.py"
    script.write_text(
        "import sys\n"
        "sys.stderr.write('Traceback (most recent call last):\\n')\n"
        "sys.stderr.write('  File \"worker.py\", line 42, in crash\\n')\n"
        "sys.stderr.write('RuntimeError: Fatal COM exception 0x80004005\\n')\n"
        "sys.stderr.flush()\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )

    worker = AutomationWorker(timeout=5)

    def crashing_spawn() -> subprocess.Popen[str]:
        return subprocess.Popen(  # noqa: S603
            [sys.executable, "-u", str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

    worker._spawn = crashing_spawn  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(NativeSessionError) as exc_info:
        worker.call(NativeRequest(operation="windows"))

    err = exc_info.value
    assert len(err.stderr_tail) > 0
    full_str = str(err)
    assert "Fatal COM exception 0x80004005" in full_str
    assert "[Worker stderr tail]" in full_str


def test_worker_reset_clears_stderr_buffer() -> None:
    """Verify calling worker.reset() clears any retained stderr buffer."""
    worker = AutomationWorker()
    worker.stderr_buffer.extend(["error 1\n", "error 2\n", "fatal crash\n"])
    assert len(worker.stderr_buffer) == 3

    worker.reset()

    assert len(worker.stderr_buffer) == 0
