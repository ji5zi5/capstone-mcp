# Copyright 2026 Capstone MCP contributors.
"""Native-free messages for the private automation worker channel."""

from typing import Literal

from pydantic import Field, JsonValue

from capstone_mcp.graphs import GraphFailure
from capstone_mcp.models import Action, Button, Model, Point

type NativeOperation = Literal[
    "attach", "windows", "snapshot", "action", "read_value", "set_value",
    "screenshot", "click", "drag", "scroll", "keys",
    "recording_status", "set_recording", "step_sampling_rate",
    "select_sensor", "configure_sensor",
    "recording_initialize", "recording_observe", "recording_change",
    "save_experiment", "export_data", "open_experiment",
    "manage_graph", "manage_instrument",
    "create_graph", "select_graph_measurement",
    "read_graph", "set_graph_fits", "analyze_graph", "observe_graph",
    "rename_run", "fit_graph", "create_calculation", "delete_run", "zero_sensor",
    "create_table", "set_table_columns", "read_table",
    "create_digits",
    "toggle_graph_statistics", "measure_graph_area", "graph_delta",
    "set_run_visibility",
    "set_signal_generator", "read_signal_generator_status",
    "create_scope", "set_scope_trigger", "create_fft", "read_fft_peaks",
    "set_recording_condition", "set_sampling_mode", "keep_sample",
    "scan_wireless_sensors", "connect_wireless_sensor", "calibrate_sensor",
    "add_page", "set_page_layout",
]


class NativeRequest(Model):
    """Internal command envelope; only the enumerated operations are accepted."""

    operation: NativeOperation
    handle: int = 0
    process_id: int | None = None
    launch: bool = False
    depth: int = 12
    limit: int = 800
    query: str = ""
    control_types: list[str] = Field(default_factory=list)
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
    old_name: str = ""
    new_name: str = ""
    step_limit: int = 128
    allow_foreground: bool = True
    discard_unsaved: bool = False
    scale: float = 1.0
    crop_region: list[int] | None = None
    plan: JsonValue = None
    menu_path: list[str] = Field(default_factory=list)
    graph_request: JsonValue = None
    instrument_request: JsonValue = None
    frame_id: str = ""
    mode: str = "scale_to_fit"
    offset_x: int = 20
    offset_y: int = 20
    graph_name: str | None = None
    expression: str = ""
    unit: str | None = None
    keep_open: bool = False
    run_name: str = "last_run"
    sensor_name: str | None = None
    table_name: str | None = None
    columns: list[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = 50
    include_statistics: bool = True
    digits_name: str | None = None
    measurement: str | None = None
    enable: bool | None = None
    point1: Point | None = None
    point2: Point | None = None
    runs: list[str] = Field(default_factory=list)
    visible: bool = True
    target_displays: list[str] | None = None
    waveform: str = "Sine"
    frequency: float | None = 1000.0
    amplitude: float | None = 1.0
    enabled: bool = True
    generator_name: str | None = None
    timebase: str | float | None = None
    channel: str | None = None
    scope_id: str | None = None
    trigger_level: float = 0.0
    trigger_slope: str = "rising"
    trigger_mode: str = "auto"
    trigger_source: str | None = None
    frequency_range: str | None = None
    fft_id: str | None = None
    top_k: int = 5
    start_condition: JsonValue = None
    stop_condition: JsonValue = None
    sampling_mode: str = "continuous"
    sample_value: float | None = None
    variable_name: str | None = None
    timeout_seconds: float = 5.0
    sensor_id: str = ""
    measurement_type: str | None = None
    calibration_type: str = "two_point"
    standard_1: float = 0.0
    standard_2: float | None = None
    title: str = "New Page"
    layout: str = "two_vertical"
    page_name: str | None = None


class RequestPacket(Model):
    """One uniquely identified request on a worker's private channel."""

    identifier: str
    command: NativeRequest


class NativeReply(Model):
    """Native results and ordinary operation errors are distinct from IPC failures."""

    identifier: str
    result: JsonValue = None
    error: str | None = None
    graph_failure: GraphFailure | None = None
