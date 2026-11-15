# Copyright 2026 Capstone MCP contributors.
"""Telemetry ring buffer and streaming sample aggregator for Capstone sessions."""

from __future__ import annotations

import time
from collections import deque
from typing import Final

DEFAULT_BUFFER_CAPACITY: Final = 1000


class TelemetryBuffer:
    """Thread-safe, bounded ring buffer for streaming sensor samples."""

    def __init__(self, capacity: int = DEFAULT_BUFFER_CAPACITY) -> None:
        """Initialize telemetry buffer with bounded capacity per measurement."""
        self._capacity = max(1, capacity)
        self._buffers: dict[str, deque[tuple[float, float]]] = {}

    def push_sample(
        self,
        euid: str,
        value: float,
        timestamp: float | None = None,
    ) -> None:
        """Record a single timestamped measurement sample."""
        ts = timestamp if timestamp is not None else time.monotonic()
        if euid not in self._buffers:
            self._buffers[euid] = deque(maxlen=self._capacity)
        self._buffers[euid].append((ts, value))

    def get_samples(
        self,
        euid: str,
        limit: int | None = None,
    ) -> list[tuple[float, float]]:
        """Retrieve recent samples as (timestamp, value) pairs."""
        buf = self._buffers.get(euid)
        if not buf:
            return []
        samples = list(buf)
        if limit is not None and limit > 0:
            return samples[-limit:]
        return samples

    def get_latest(self, euid: str) -> float | None:
        """Get the most recent value for a given measurement EUID."""
        buf = self._buffers.get(euid)
        if not buf:
            return None
        return buf[-1][1]

    def clear(self, euid: str | None = None) -> None:
        """Clear recorded samples for a specific EUID or all buffers."""
        if euid is not None:
            self._buffers.pop(euid, None)
        else:
            self._buffers.clear()

    def compute_stats(self, euid: str) -> dict[str, float]:
        """Compute basic summary statistics for buffered samples."""
        buf = self._buffers.get(euid)
        if not buf:
            return {"count": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
        vals = [v for _, v in buf]
        count = len(vals)
        mean_val = sum(vals) / count
        return {
            "count": float(count),
            "mean": mean_val,
            "min": min(vals),
            "max": max(vals),
        }
