# Copyright 2026 Capstone MCP contributors.
"""Read Capstone's observed native data bridge through its local Qt debug port."""

import json
import logging
import socket
import time
from typing import Final
from urllib.parse import urlsplit

import httpx2
from pydantic import Field, FiniteFloat, JsonValue, TypeAdapter
from websockets.sync.client import connect

from capstone_mcp.models import Model

LOGGER: Final = logging.getLogger(__name__)
REQUEST_TIMEOUT: Final = 15.0
TARGET_SUFFIX: Final = "/Capstone/Resources/www/index.html"


class BridgeError(RuntimeError):
    """The configured local Capstone bridge could not produce a valid result."""


class DebugTarget(Model):
    """A target from Qt's local Chrome DevTools discovery endpoint."""

    id: str
    type: str
    url: str
    websocket_url: str = Field(alias="webSocketDebuggerUrl")


class RemoteValue(Model):
    """A CDP Runtime remote value returned by value."""

    type: str
    value: JsonValue = None
    description: str | None = None


class Evaluation(Model):
    """Runtime.evaluate result, including JavaScript exceptions."""

    result: RemoteValue
    exception_details: JsonValue = Field(default=None, alias="exceptionDetails")


class ProtocolError(Model):
    """CDP protocol failure."""

    code: int
    message: str


class Reply(Model):
    """CDP response or event; only matching response IDs are consumed."""

    id: int | None = None
    result: Evaluation | None = None
    error: ProtocolError | None = None


class NativeInventory(Model):
    """Native metadata retained without inventing units or sensor fields.

    Only sensors and measurements are common to every observed Capstone build.
    A category the running build does not report stays null, not an empty list.
    """

    accessories: list[JsonValue] | None = None
    codable_interfaces: list[JsonValue] | None = Field(
        default=None, alias="codableInterfaces",
    )
    code_nodes: list[JsonValue] | None = Field(default=None, alias="codeNodes")
    control_nodes: list[JsonValue] | None = Field(default=None, alias="controlNodes")
    measurements: list[JsonValue]
    outputs: list[JsonValue] | None = None
    sensors: list[JsonValue]


class MeasurementReply(Model):
    """Native success flag is independent from the numeric return value."""

    value: FiniteFloat = Field(alias="ReturnValue")
    succeeded: bool = Field(alias="cmdResult")


def log_request(request: httpx2.Request) -> None:
    """Log discovery requests to stderr through the configured logger."""
    LOGGER.debug("Capstone discovery %s %s", request.method, request.url)


def discover_target(port: int) -> DebugTarget:
    """Resolve exactly one Capstone page on the explicit loopback debug port."""
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=httpx2.Limits(
            max_connections=50, max_keepalive_connections=20,
            keepalive_expiry=60,
        ),
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    with httpx2.Client(
        transport=transport,
        timeout=httpx2.Timeout(connect=5, read=10, write=10, pool=10),
        trust_env=False,
        follow_redirects=False,
        event_hooks={"request": [log_request]},
    ) as client:
        response = client.get(f"http://127.0.0.1:{port}/json/list")
        _ = response.raise_for_status()
        targets = TypeAdapter(list[DebugTarget]).validate_json(response.content)
    matches = [
        target for target in targets
        if target.type == "page" and target.url.endswith(TARGET_SUFFIX)
    ]
    if len(matches) != 1:
        msg = "Expected one Capstone Sense and Control page on the debug port."
        raise BridgeError(msg)
    target = matches[0]
    endpoint = urlsplit(target.websocket_url)
    if endpoint.scheme != "ws" or endpoint.hostname != "127.0.0.1":
        msg = "The Capstone debug WebSocket must remain on loopback."
        raise BridgeError(msg)
    if endpoint.port != port:
        msg = "The discovered WebSocket does not match the selected port."
        raise BridgeError(msg)
    return target


def evaluate(port: int, expression: str) -> JsonValue:
    """Evaluate a fixed internal request with a bounded response deadline."""
    target = discover_target(port)
    request = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
    }
    deadline = time.monotonic() + REQUEST_TIMEOUT
    with connect(
        target.websocket_url, proxy=None, open_timeout=5,
        close_timeout=2, max_size=8 * 1024 * 1024,
    ) as websocket:
        websocket.send(json.dumps(request))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                msg = "Capstone bridge response deadline exceeded."
                raise TimeoutError(msg)
            reply = Reply.model_validate_json(websocket.recv(timeout=remaining))
            if reply.id != 1:
                continue
            if reply.error is not None:
                raise BridgeError(reply.error.message)
            if reply.result is None:
                msg = "Capstone returned no evaluation result."
                raise BridgeError(msg)
            result = reply.result
            if result.exception_details is not None:
                msg = "Capstone JavaScript bridge raised: " + json.dumps(
                    result.exception_details, ensure_ascii=False,
                )
                raise BridgeError(msg)
            return result.result.value


def read_inventory(port: int) -> NativeInventory:
    """Read actual sensor and measurement metadata from the running application."""
    result = evaluate(
        port,
        "window.app.mSenseAndControlView.mServices.RequestSensorsAndMeasurements()",
    )
    return NativeInventory.model_validate(result)


def read_measurement(port: int, measurement_euid: str, unit_type: int) -> float:
    """Read a current value, refusing the provider's unavailable-value sentinel."""
    expression = (
        "window.app.mSenseAndControlView.mServices.RequestReadMeasurement("
        + json.dumps(measurement_euid) + "," + str(unit_type) + ")"
    )
    reply = MeasurementReply.model_validate(evaluate(port, expression))
    if not reply.succeeded:
        msg = "Capstone reports no current value for this measurement and unit."
        raise BridgeError(msg)
    return reply.value
