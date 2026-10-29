# Copyright 2026 Capstone MCP contributors.
"""Native-free messages for the private automation worker channel."""

from typing import Literal

from pydantic import Field, JsonValue

from capstone_mcp.models import Action, Button, Model, Point

type NativeOperation = Literal[
    "attach", "windows", "snapshot", "action", "read_value", "set_value",
    "screenshot", "click", "drag", "scroll", "keys",
    "recording_status", "set_recording", "step_sampling_rate",
    "select_sensor", "configure_sensor",
    "recording_initialize", "recording_observe", "recording_change",
    "save_experiment", "export_data",
    "create_graph", "select_graph_measurement",
    "read_graph", "set_graph_fits", "analyze_graph",
]


class NativeRequest(Model):
    """Internal command envelope; only the enumerated operations are accepted."""

    operation: NativeOperation
    handle: int = 0
    process_id: int | None = None
    launch: bool = False
    depth: int = 12
    limit: int = 800
    ref: str = ""
    action: Action = Action.INVOKE
    value: str = ""
    point: Point = Point(x=0, y=0)
    end: Point = Point(x=0, y=0)
    button: Button = Button.LEFT
    double: bool = False
    notches: int = 0
    unicode_input: bool = False
    recording: bool = False
    direction: Literal["increase", "decrease"] = "increase"
    sensor: str = ""
    target: str = ""
    step_limit: int = 128
    allow_foreground: bool = True
    plan: JsonValue = None
    menu_path: list[str] = Field(default_factory=list)
    graph_request: JsonValue = None


class RequestPacket(Model):
    """One uniquely identified request on a worker's private channel."""

    identifier: str
    command: NativeRequest


class NativeReply(Model):
    """Native results and ordinary operation errors are distinct from IPC failures."""

    identifier: str
    result: JsonValue = None
    error: str | None = None
