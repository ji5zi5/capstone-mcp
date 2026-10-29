# Copyright 2026 Capstone MCP contributors.
"""Native-only operation dispatch; imported after the worker owns its process job."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from PIL import Image
from pydantic import BaseModel, JsonValue, TypeAdapter

from capstone_mcp.acquisition import (
    observe_recording,
    request_recording,
    step_sampling_rate,
)
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.file_workflows import export_data, save_experiment
from capstone_mcp.graph_execution import (
    GRAPH_INPUT_OPERATIONS,
    GraphCapture,
    GraphFailure,
    GraphFrame,
    GraphOperationError,
    GraphProgress,
)
from capstone_mcp.graph_requests import GraphAnalysisRequest, GraphFitRequest
from capstone_mcp.graph_workflows import (
    analyze_graph,
    create_graph,
    read_graph,
    select_graph_measurement,
    set_graph_fits,
)
from capstone_mcp.models import Result
from capstone_mcp.repetition import NativeRecordingBackend, RepeatPlan
from capstone_mcp.sensor_settings import (
    SamplingRateRequest,
    SensorConfiguration,
    SensorSelectionRequest,
    select_sensor,
    target_sampling_rate,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from capstone_mcp.automation_models import NativeOperation, NativeRequest

JSON_VALUE: Final = TypeAdapter(JsonValue)


def _json(model: BaseModel) -> JsonValue:
    return JSON_VALUE.validate_json(model.model_dump_json())


class NativeDesktop:
    """Retain wrappers and snapshot references only inside one native process."""

    def __init__(self) -> None:
        """Create no application until explicit attachment or initialization."""
        self.app: Capstone = Capstone()
        self.recording: NativeRecordingBackend | None = None
        self.last_frame: GraphCapture | None = None
        self.graph_progress: GraphProgress | None = None
        self.handlers: Mapping[
            NativeOperation, Callable[[NativeRequest], JsonValue],
        ] = {
            "attach": lambda r: [
                _json(w) for w in self.app.attach(
                    launch=r.launch, process_id=r.process_id,
                )
            ],
            "windows": lambda _r: [_json(w) for w in self.app.windows()],
            "snapshot": lambda r: _json(
                self.app.snapshot(r.handle, r.depth, r.limit),
            ),
            "action": lambda r: _json(self.app.act(
                r.ref, r.action, allow_foreground=r.allow_foreground,
            )),
            "read_value": lambda r: self.app.control(r.ref).iface_value.CurrentValue,
            "set_value": lambda r: _json(self.app.set_value(r.ref, r.value)),
            "screenshot": lambda r: base64.b64encode(
                self.app.screenshot(r.handle),
            ).decode("ascii"),
            "observe_graph": self._observe_graph,
            "keys": lambda r: _json(self.app.keys(
                r.handle, r.value, allow_foreground=r.allow_foreground,
                unicode_input=r.unicode_input,
            )),
            "click": lambda r: _json(self._click(r)),
            "drag": lambda r: _json(self._drag(r)),
            "scroll": lambda r: _json(self._scroll(r)),
            "recording_status": lambda r: _json(
                observe_recording(self.app, r.handle)[0],
            ),
            "set_recording": lambda r: _json(request_recording(
                self.app, r.handle, recording=r.recording,
                allow_foreground=r.allow_foreground,
            )),
            "step_sampling_rate": lambda r: _json(step_sampling_rate(
                self.app, r.handle, r.direction, expected_sensor=r.sensor,
                allow_foreground=r.allow_foreground,
            )),
            "select_sensor": lambda r: _json(select_sensor(
                self.app, r.handle,
                SensorSelectionRequest(
                    sensor=r.sensor, allow_foreground=r.allow_foreground,
                ),
            )),
            "configure_sensor": self._configure_sensor,
            "recording_initialize": self._initialize_recording,
            "recording_observe": lambda _r: _json(self._recording().observe()),
            "recording_change": lambda r: _json(
                self._recording().change(recording=r.recording),
            ),
            "save_experiment": lambda r: _json(save_experiment(
                self.app, r.handle, r.value, allow_foreground=r.allow_foreground,
            )),
            "export_data": lambda r: _json(export_data(
                self.app, r.handle, r.value, allow_foreground=r.allow_foreground,
            )),
            "create_graph": lambda r: _json(create_graph(
                self.app, r.handle, allow_foreground=r.allow_foreground,
            )),
            "select_graph_measurement": lambda r: _json(select_graph_measurement(
                self.app, r.handle, r.point, r.menu_path,
                allow_foreground=r.allow_foreground,
            )),
            "read_graph": lambda r: _json(read_graph(
                self.app, r.handle, allow_foreground=r.allow_foreground,
            )),
            "set_graph_fits": lambda r: _json(set_graph_fits(
                self.app, r.handle,
                GraphFitRequest.model_validate(r.graph_request),
                progress=self.graph_progress,
            )),
            "analyze_graph": lambda r: _json(analyze_graph(
                self.app, r.handle,
                GraphAnalysisRequest.model_validate(r.graph_request),
                progress=self.graph_progress,
            )),
        }

    def dispatch(self, request: NativeRequest) -> JsonValue:
        """Route a validated allowlisted command on the owning COM thread."""
        if request.operation not in GRAPH_INPUT_OPERATIONS | {
            "read_graph", "observe_graph", "create_graph",
        }:
            return self.handlers[request.operation](request)
        self.graph_progress = GraphProgress()
        try:
            if request.operation in GRAPH_INPUT_OPERATIONS:
                self._verify_frame(request)
            if request.operation == "select_graph_measurement":
                self.graph_progress.begin_input("select_measurement")
            if request.operation == "create_graph":
                self.graph_progress.begin_input("create_graph")
            return self.handlers[request.operation](request)
        except GraphOperationError:
            raise
        except Exception as error:
            progress = self.graph_progress
            raise GraphOperationError(GraphFailure(
                code="UNVERIFIED_GRAPH_STATE" if progress.input_attempted
                else "GRAPH_OBSERVATION_FAILED",
                operation=request.operation, stage=progress.stage,
                completed_steps=progress.completed_steps,
                graph_input_may_have_been_sent=progress.input_attempted,
                next_action="read_graph" if progress.input_attempted
                else "inspect_windows",
                detail=f"{type(error).__name__}: {error}",
            )) from error
        finally:
            self.graph_progress = None

    def _observe_graph(self, request: NativeRequest) -> JsonValue:
        png = self.app.graph_screenshot(request.handle, activate=True)
        window = next(w for w in self.app.windows() if w.handle == request.handle)
        with Image.open(BytesIO(png)) as image:
            width, height = image.size
        self.last_frame = GraphCapture(
            frame=GraphFrame(
                frame_id=uuid4().hex, handle=request.handle, bounds=window.bounds,
                width=width, height=height,
            ),
            png_base64=base64.b64encode(png).decode("ascii"),
        )
        return _json(self.last_frame)

    def _verify_frame(self, request: NativeRequest) -> None:
        capture = self.last_frame
        self.last_frame = None
        if (
            capture is None or request.frame_id != capture.frame.frame_id
            or request.handle != capture.frame.handle
        ):
            raise GraphOperationError(GraphFailure(
                code="FRAME_REQUIRED", operation=request.operation, stage="preflight",
                graph_input_may_have_been_sent=False, next_action="observe_graph",
                detail="Capture a fresh graph frame in this session before input.",
            ))
        window = next(
            (w for w in self.app.windows() if w.handle == request.handle), None,
        )
        reason = None
        if window is None:
            reason = "The observed graph window is no longer visible."
        elif window.bounds != capture.frame.bounds:
            reason = "The graph window bounds changed."
        elif self.app.graph_screenshot(request.handle) != base64.b64decode(
            capture.png_base64,
        ):
            reason = "The visible graph image changed."
        if reason is not None:
            raise GraphOperationError(GraphFailure(
                code="STALE_FRAME", operation=request.operation, stage="preflight",
                graph_input_may_have_been_sent=False, next_action="observe_graph",
                detail=reason + " Reacquire coordinates.",
            ))

    def _configure_sensor(self, request: NativeRequest) -> JsonValue:
        selection = select_sensor(
            self.app, request.handle,
            SensorSelectionRequest(
                sensor=request.sensor, allow_foreground=request.allow_foreground,
            ),
        )
        rate = target_sampling_rate(
            self.app, request.handle,
            SamplingRateRequest(
                sensor=request.sensor, target=request.target,
                step_limit=request.step_limit,
                allow_foreground=request.allow_foreground,
            ),
        )
        return _json(SensorConfiguration(selection=selection, rate=rate))

    def _initialize_recording(self, request: NativeRequest) -> JsonValue:
        self.recording = NativeRecordingBackend(RepeatPlan.model_validate(request.plan))
        self.app = self.recording.app
        return _json(self.recording.observe())

    def _recording(self) -> NativeRecordingBackend:
        if self.recording is None:
            msg = "Recording session has not been initialized."
            raise AutomationError(msg)
        return self.recording

    def _click(self, request: NativeRequest) -> Result:
        if not request.allow_foreground:
            msg = "Foreground input is disabled."
            raise AutomationError(msg)
        window = self.app.focus_window(request.handle)
        rect = window.rectangle()
        x, y = request.point.x, request.point.y
        if not (0 <= x < rect.right - rect.left and 0 <= y < rect.bottom - rect.top):
            msg = "Coordinates must be inside the current window rectangle."
            raise AutomationError(msg)
        window.click_input(
            button=request.button.value, coords=(rect.left + x, rect.top + y),
            double=request.double, absolute=True,
        )
        self.app.refs.clear()
        return Result(detail="Click delivered; inspect the window to verify.")

    def _drag(self, request: NativeRequest) -> Result:
        if not request.allow_foreground:
            msg = "Foreground input is disabled."
            raise AutomationError(msg)
        window = self.app.focus_window(request.handle)
        rect = window.rectangle()
        for point in (request.point, request.end):
            if not (
                0 <= point.x < rect.right - rect.left
                and 0 <= point.y < rect.bottom - rect.top
            ):
                msg = "Both drag endpoints must be inside the window."
                raise AutomationError(msg)
        try:
            _ = window.drag_mouse_input(
                src=(rect.left + request.point.x, rect.top + request.point.y),
                dst=(rect.left + request.end.x, rect.top + request.end.y),
                absolute=True,
            )
        finally:
            _ = window.release_mouse_input(
                coords=(rect.left + request.end.x, rect.top + request.end.y),
                absolute=True,
            )
            self.app.refs.clear()
        return Result(detail="Drag delivered; inspect to verify.")

    def _scroll(self, request: NativeRequest) -> Result:
        if not request.allow_foreground:
            msg = "Foreground input is disabled."
            raise AutomationError(msg)
        window = self.app.focus_window(request.handle)
        rect = window.rectangle()
        if not (
            0 <= request.point.x < rect.right - rect.left
            and 0 <= request.point.y < rect.bottom - rect.top
        ):
            msg = "Scroll position must be inside the window."
            raise AutomationError(msg)
        _ = window.wheel_mouse_input(
            coords=(request.point.x, request.point.y), wheel_dist=request.notches,
        )
        self.app.refs.clear()
        return Result(detail="Scroll delivered; inspect to verify.")
