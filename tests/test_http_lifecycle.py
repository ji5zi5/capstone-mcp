# Copyright 2026 Capstone MCP contributors.
"""Exercise multiple HTTP sessions in memory without launching any native app."""

import os
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import anyio
import httpx
import pytest

from capstone_mcp import bridge, server


@pytest.mark.anyio
async def test_http_session_delete_does_not_close_shared_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = Mock()
    worker = Mock()
    close_pool = Mock()
    monkeypatch.setattr(server, "JOBS", jobs)
    monkeypatch.setattr(server, "WORKER", worker)
    monkeypatch.setattr(bridge, "close_connections", close_pool)
    mcp = server.CapstoneMCP("lifecycle-fixture", lifespan=server._lifespan)
    app = mcp.streamable_http_app()
    headers = {"Accept": "application/json, text/event-stream"}
    initialize = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "offline-test", "version": "1"},
        },
    }
    async with app.router.lifespan_context(app):  # noqa: SIM117
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000",
            headers=headers,
        ) as client:
            first = await client.post("/mcp", json=initialize)
            second = await client.post("/mcp", json=initialize)
            assert first.status_code == second.status_code == 200
            first_id = first.headers["mcp-session-id"]
            second_id = second.headers["mcp-session-id"]
            assert first_id != second_id
            for session_id in (first_id, second_id):
                initialized = await client.post("/mcp", headers={"mcp-session-id": session_id}, json={
                    "jsonrpc": "2.0", "method": "notifications/initialized",
                })
                assert initialized.status_code == 202
            response = await client.delete("/mcp", headers={"mcp-session-id": first_id})
            assert response.status_code == 200
            response = await client.post("/mcp", headers={"mcp-session-id": second_id}, json={
                "jsonrpc": "2.0", "id": 2, "method": "ping",
            })
            assert response.status_code == 200
            jobs.close.assert_not_called()
            worker.close.assert_not_called()
            close_pool.assert_not_called()
    jobs.close.assert_called_once_with()
    worker.close.assert_called_once_with()
    close_pool.assert_called_once_with()


@pytest.mark.anyio
async def test_cancelled_lifespan_still_releases_owned_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = Mock()
    worker = Mock()
    close_pool = Mock()
    monkeypatch.setattr(server, "JOBS", jobs)
    monkeypatch.setattr(server, "WORKER", worker)
    monkeypatch.setattr(bridge, "close_connections", close_pool)
    with anyio.CancelScope() as scope:
        async with server._lifespan(server.MCP):
            scope.cancel()
            await anyio.lowlevel.checkpoint()
    jobs.close.assert_called_once_with()
    worker.close.assert_called_once_with()
    close_pool.assert_called_once_with()


def test_http_occupied_port_exits_with_nonzero_diagnostic() -> None:
    root = Path(__file__).resolve().parents[1]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]
        proc = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-c",
                "from capstone_mcp.server import http_main; http_main()",
                "--port",
                str(port),
            ],
            cwd=str(root),
            env={**os.environ, "PYTHONPATH": str(root / "src")},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert proc.returncode != 0
        combined = proc.stderr + proc.stdout
        assert combined.strip()
