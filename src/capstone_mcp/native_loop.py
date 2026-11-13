# Copyright 2026 Capstone MCP contributors.
"""COM-owning command loop and native operation dispatcher."""

from __future__ import annotations

import base64
import logging
import sys
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
from capstone_mcp.automation_models import NativeReply, RequestPacket
from capstone_mcp.automation_worker import MAX_MESSAGE_BYTES
from capstone_mcp.calculator import CreateCalculationRequest, create_calculation
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import (
    AddPageRequest,
    CreateDigitsRequest,
    CreateFftRequest,
    CreateScopeRequest,
    CreateTableRequest,
    DisplayAction,
    DisplayRequest,
    ReadFftPeaksRequest,
    ReadTableRequest,
    SetPageLayoutRequest,
    SetScopeTriggerRequest,
    SetTableColumnsRequest,
    manage_display,
)
from capstone_mcp.file_workflows import (
    export_data,
    open_experiment,
    save_experiment,
)
from capstone_mcp.graphs import (
    GRAPH_INPUT_OPERATIONS,
    AnalyzeGraphRequest,
    FitGraphRequest,
    GraphCapture,
    GraphDeltaRequest,
    GraphFailure,
    GraphFrame,
    GraphOperationError,
    GraphProgress,
    GraphRequest,
    MeasureGraphAreaRequest,
    SetGraphFitsRequest,
    ToggleGraphStatisticsRequest,
    analyze_graph,
    create_graph,
    fit_graph,
    graph_delta,
    manage_graph,
    measure_graph_area,
    read_graph,
    select_graph_measurement,
    set_graph_fits,
    toggle_graph_statistics,
)
from capstone_mcp.instruments import (
    CalibrateSensorRequest,
    ConditionSpec,
    ConnectWirelessSensorRequest,
    InstrumentAction,
    InstrumentRequest,
    KeepSampleRequest,
    SamplingRateRequest,
    ScanWirelessSensorsRequest,
    SensorConfiguration,
    SensorSelectionRequest,
    SetRecordingConditionRequest,
    SetSamplingModeRequest,
    SetSignalGeneratorRequest,
    ZeroSensorRequest,
    manage_instrument,
    select_sensor,
    target_sampling_rate,
)
from capstone_mcp.models import Point, Result
from capstone_mcp.repetition import NativeRecordingBackend, RepeatPlan
from capstone_mcp.runs import (
    DeleteRunRequest,
    RenameRunRequest,
    SetRunVisibilityRequest,
    delete_run,
    rename_run,
    set_run_visibility,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from capstone_mcp.automation_models import NativeOperation, NativeRequest

LOGGER: Final = logging.getLogger(__name__)
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
            NativeOperation,
            Callable[[NativeRequest], JsonValue],
        ] = {
            "attach": lambda r: [
                _json(w)
                for w in self.app.attach(
                    launch=r.launch,
                    process_id=r.process_id,
                )
            ],
            "windows": lambda _r: [_json(w) for w in self.app.windows()],
            "snapshot": lambda r: _json(
                self.app.matching_snapshot(
                    r.handle,
                    r.depth,
                    r.limit,
                    query=r.query,
                    control_types=r.control_types,
                ),
            ),
            "action": lambda r: _json(
                self.app.act(
                    r.ref,
                    r.action,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "read_value": lambda r: self.app.control(
                r.ref,
            ).iface_value.CurrentValue,
            "set_value": lambda r: _json(self.app.set_value(r.ref, r.value)),
            "screenshot": lambda r: base64.b64encode(
                self.app.screenshot(
                    r.handle,
                    scale=r.scale,
                    crop_region=r.crop_region,
                ),
            ).decode("ascii"),
            "observe_graph": self._observe_graph,
            "keys": lambda r: _json(
                self.app.keys(
                    r.handle,
                    r.value,
                    allow_foreground=r.allow_foreground,
                    unicode_input=r.unicode_input,
                ),
            ),
            "click": lambda r: _json(self._click(r)),
            "drag": lambda r: _json(self._drag(r)),
            "scroll": lambda r: _json(self._scroll(r)),
            "recording_status": lambda r: _json(
                observe_recording(self.app, r.handle)[0],
            ),
            "set_recording": lambda r: _json(
                request_recording(
                    self.app,
                    r.handle,
                    recording=r.recording,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "step_sampling_rate": lambda r: _json(
                step_sampling_rate(
                    self.app,
                    r.handle,
                    r.direction,
                    expected_sensor=r.sensor,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "select_sensor": lambda r: _json(
                select_sensor(
                    self.app,
                    r.handle,
                    SensorSelectionRequest(
                        sensor=r.sensor,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "configure_sensor": self._configure_sensor,
            "recording_initialize": self._initialize_recording,
            "recording_observe": lambda _r: _json(self._recording().observe()),
            "recording_change": lambda r: _json(
                self._recording().change(recording=r.recording),
            ),
            "save_experiment": lambda r: _json(
                save_experiment(
                    self.app,
                    r.handle,
                    r.value,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "export_data": lambda r: _json(
                export_data(
                    self.app,
                    r.handle,
                    r.value,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "open_experiment": lambda r: _json(
                open_experiment(
                    self.app,
                    r.handle,
                    r.value,
                    discard_unsaved=r.discard_unsaved,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "manage_graph": lambda r: _json(
                manage_graph(
                    self.app,
                    GraphRequest.model_validate(r.graph_request),
                ),
            ),
            "manage_instrument": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest.model_validate(r.instrument_request),
                ),
            ),
            "manage_display": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest.model_validate(r.display_request),
                ),
            ),
            "create_graph": lambda r: _json(
                create_graph(
                    self.app,
                    r.handle,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "select_graph_measurement": lambda r: _json(
                select_graph_measurement(
                    self.app,
                    r.handle,
                    Point(x=r.point.x, y=r.point.y),
                    r.menu_path,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "read_graph": lambda r: _json(
                read_graph(
                    self.app,
                    r.handle,
                    allow_foreground=r.allow_foreground,
                ),
            ),
            "set_graph_fits": lambda r: _json(
                set_graph_fits(
                    self.app,
                    r.handle,
                    SetGraphFitsRequest.model_validate(r.graph_request),
                ),
            ),
            "analyze_graph": lambda r: _json(
                analyze_graph(
                    self.app,
                    r.handle,
                    AnalyzeGraphRequest.model_validate(r.graph_request),
                ),
            ),
            "fit_graph": lambda r: _json(
                fit_graph(
                    self.app,
                    FitGraphRequest(
                        handle=r.handle,
                        mode=r.mode,
                        graph_name=r.target,
                        offset=r.point,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "rename_run": lambda r: _json(
                rename_run(
                    self.app,
                    RenameRunRequest(
                        handle=r.handle,
                        old_name=r.old_name,
                        new_name=r.new_name,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "create_calculation": lambda r: _json(
                create_calculation(
                    self.app,
                    CreateCalculationRequest(
                        handle=r.handle,
                        expression=r.expression,
                        unit=r.unit,
                        allow_foreground=r.allow_foreground,
                        keep_open=r.keep_open,
                    ),
                ),
            ),
            "delete_run": lambda r: _json(
                delete_run(
                    self.app,
                    DeleteRunRequest(
                        handle=r.handle,
                        run_name=r.run_name,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "zero_sensor": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.ZERO_SENSOR,
                        zero_sensor=ZeroSensorRequest(
                            handle=r.handle,
                            sensor_name=r.sensor_name,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).zero_sensor,  # type: ignore[arg-type]
            ),
            "create_table": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.CREATE_TABLE,
                        create_table=CreateTableRequest(
                            handle=r.handle,
                            table_name=r.table_name,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).create_table,  # type: ignore[arg-type]
            ),
            "set_table_columns": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.SET_TABLE_COLUMNS,
                        set_table_columns=SetTableColumnsRequest(
                            handle=r.handle,
                            columns=r.columns,
                            table_name=r.table_name,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).set_table_columns,  # type: ignore[arg-type]
            ),
            "read_table": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.READ_TABLE,
                        read_table=ReadTableRequest(
                            handle=r.handle,
                            table_name=r.table_name,
                            page=r.page,
                            page_size=r.page_size,
                            include_statistics=r.include_statistics,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).read_table,  # type: ignore[arg-type]
            ),
            "create_digits": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.CREATE_DIGITS,
                        create_digits=CreateDigitsRequest(
                            handle=r.handle,
                            measurement=r.measurement,
                            digits_name=r.digits_name,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).create_digits,  # type: ignore[arg-type]
            ),
            "toggle_graph_statistics": lambda r: _json(
                toggle_graph_statistics(
                    self.app,
                    ToggleGraphStatisticsRequest(
                        handle=r.handle,
                        graph_name=r.graph_name,
                        enable=r.enable,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "measure_graph_area": lambda r: _json(
                measure_graph_area(
                    self.app,
                    MeasureGraphAreaRequest(
                        handle=r.handle,
                        graph_name=r.graph_name,
                        enable=r.enable,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "graph_delta": lambda r: _json(
                graph_delta(
                    self.app,
                    GraphDeltaRequest(
                        handle=r.handle,
                        graph_name=r.graph_name,
                        point1=r.point1,
                        point2=r.point2,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "set_run_visibility": lambda r: _json(
                set_run_visibility(
                    self.app,
                    SetRunVisibilityRequest(
                        handle=r.handle,
                        runs=r.runs,
                        visible=r.visible,
                        target_displays=r.target_displays,
                        allow_foreground=r.allow_foreground,
                    ),
                ),
            ),
            "set_signal_generator": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
                        configure_signal_generator=SetSignalGeneratorRequest(
                            handle=r.handle,
                            waveform=r.waveform,
                            frequency=r.frequency,
                            amplitude=r.amplitude,
                            enabled=r.enabled,
                            generator_name=r.generator_name,
                            allow_foreground=r.allow_foreground,
                            keep_open=r.keep_open,
                        ),
                    ),
                ).configure_signal_generator,  # type: ignore[arg-type]
            ),
            "read_signal_generator_status": (
                lambda r: _json(
                    manage_instrument(
                        self.app,
                        InstrumentRequest(
                            action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
                            configure_signal_generator=SetSignalGeneratorRequest(
                                handle=r.handle,
                                generator_name=r.generator_name,
                                allow_foreground=r.allow_foreground,
                                keep_open=r.keep_open,
                                read_only=True,
                            ),
                        ),
                    ).configure_signal_generator,  # type: ignore[arg-type]
                )
            ),
            "create_scope": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.CREATE_SCOPE,
                        create_scope=CreateScopeRequest(
                            handle=r.handle,
                            timebase=r.timebase,
                            channel=r.channel,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).create_scope,  # type: ignore[arg-type]
            ),
            "set_scope_trigger": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.SET_SCOPE_TRIGGER,
                        set_scope_trigger=SetScopeTriggerRequest(
                            handle=r.handle,
                            scope_id=r.scope_id,
                            trigger_level=r.trigger_level,
                            trigger_slope=r.trigger_slope,
                            trigger_mode=r.trigger_mode,
                            trigger_source=r.trigger_source,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).set_scope_trigger,  # type: ignore[arg-type]
            ),
            "create_fft": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.CREATE_FFT,
                        create_fft=CreateFftRequest(
                            handle=r.handle,
                            measurement=r.measurement,
                            frequency_range=r.frequency_range,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).create_fft,  # type: ignore[arg-type]
            ),
            "read_fft_peaks": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.READ_FFT_PEAKS,
                        read_fft_peaks=ReadFftPeaksRequest(
                            handle=r.handle,
                            fft_id=r.fft_id,
                            top_k=r.top_k,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).read_fft_peaks,  # type: ignore[arg-type]
            ),
            "set_recording_condition": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.SET_RECORDING_CONDITION,
                        set_recording_condition=SetRecordingConditionRequest(
                            handle=r.handle,
                            start_condition=(
                                ConditionSpec.model_validate(r.start_condition)
                                if r.start_condition is not None
                                else None
                            ),
                            stop_condition=(
                                ConditionSpec.model_validate(r.stop_condition)
                                if r.stop_condition is not None
                                else None
                            ),
                            allow_foreground=r.allow_foreground,
                            keep_open=r.keep_open,
                        ),
                    ),
                ).set_recording_condition,  # type: ignore[arg-type]
            ),
            "set_sampling_mode": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.SET_SAMPLING_MODE,
                        set_sampling_mode=SetSamplingModeRequest(
                            handle=r.handle,
                            mode=r.sampling_mode,  # type: ignore[arg-type]
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).set_sampling_mode,  # type: ignore[arg-type]
            ),
            "keep_sample": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.KEEP_SAMPLE,
                        keep_sample=KeepSampleRequest(
                            handle=r.handle,
                            value=r.sample_value,
                            variable_name=r.variable_name,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).keep_sample,  # type: ignore[arg-type]
            ),
            "scan_wireless_sensors": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.SCAN_WIRELESS,
                        scan_wireless=ScanWirelessSensorsRequest(
                            handle=r.handle,
                            timeout_seconds=r.timeout_seconds,
                            allow_foreground=r.allow_foreground,
                            keep_open=r.keep_open,
                        ),
                    ),
                ).scan_wireless,  # type: ignore[arg-type]
            ),
            "connect_wireless_sensor": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.CONNECT_WIRELESS,
                        connect_wireless=ConnectWirelessSensorRequest(
                            handle=r.handle,
                            sensor_id=r.sensor_id,
                            allow_foreground=r.allow_foreground,
                            keep_open=r.keep_open,
                        ),
                    ),
                ).connect_wireless,  # type: ignore[arg-type]
            ),
            "calibrate_sensor": lambda r: _json(
                manage_instrument(
                    self.app,
                    InstrumentRequest(
                        action=InstrumentAction.CALIBRATE_SENSOR,
                        calibrate_sensor=CalibrateSensorRequest(
                            handle=r.handle,
                            sensor_name=r.sensor_name or "",
                            measurement_type=r.measurement_type,
                            calibration_type=r.calibration_type,
                            standard_1=r.standard_1,
                            standard_2=r.standard_2,
                            allow_foreground=r.allow_foreground,
                            keep_open=r.keep_open,
                        ),
                    ),
                ).calibrate_sensor,  # type: ignore[arg-type]
            ),
            "add_page": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.ADD_PAGE,
                        add_page=AddPageRequest(
                            handle=r.handle,
                            title=r.title,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).add_page,  # type: ignore[arg-type]
            ),
            "set_page_layout": lambda r: _json(
                manage_display(
                    self.app,
                    DisplayRequest(
                        action=DisplayAction.SET_PAGE_LAYOUT,
                        set_page_layout=SetPageLayoutRequest(
                            handle=r.handle,
                            layout=r.layout,  # type: ignore[arg-type]
                            page_name=r.page_name,
                            allow_foreground=r.allow_foreground,
                        ),
                    ),
                ).set_page_layout,  # type: ignore[arg-type]
            ),
        }

    def dispatch(self, request: NativeRequest) -> JsonValue:
        """Route a validated allowlisted command on the owning COM thread."""
        if request.operation not in GRAPH_INPUT_OPERATIONS | {
            "read_graph",
            "observe_graph",
            "create_graph",
            "manage_graph",
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
            raise GraphOperationError(
                GraphFailure(
                    code=(
                        "UNVERIFIED_GRAPH_STATE"
                        if progress.input_attempted
                        else "GRAPH_OBSERVATION_FAILED"
                    ),
                    operation=request.operation,
                    stage=progress.stage,
                    completed_steps=progress.completed_steps,
                    graph_input_may_have_been_sent=progress.input_attempted,
                    next_action=(
                        "read_graph"
                        if progress.input_attempted
                        else "inspect_windows"
                    ),
                    detail=f"{type(error).__name__}: {error}",
                ),
            ) from error
        finally:
            self.graph_progress = None

    def _observe_graph(self, request: NativeRequest) -> JsonValue:
        png = self.app.graph_screenshot(request.handle, activate=True)
        window = next(
            w for w in self.app.windows() if w.handle == request.handle
        )
        with Image.open(BytesIO(png)) as image:
            width, height = image.size
        capture = GraphCapture(
            png_base64=base64.b64encode(png).decode("ascii"),
            frame=GraphFrame(
                frame_id=str(uuid4()),
                handle=request.handle,
                bounds=window.bounds,
                width=width,
                height=height,
            ),
        )
        self.last_frame = capture
        return _json(capture)

    def _verify_frame(self, request: NativeRequest) -> None:
        capture = self.last_frame
        self.last_frame = None
        if (
            capture is None
            or request.frame_id != capture.frame.frame_id
            or request.handle != capture.frame.handle
        ):
            raise GraphOperationError(
                GraphFailure(
                    code="FRAME_REQUIRED",
                    operation=request.operation,
                    stage="preflight",
                    graph_input_may_have_been_sent=False,
                    next_action="observe_graph",
                    detail=(
                        "Capture a fresh graph frame in this session before input."
                    ),
                ),
            )
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
            raise GraphOperationError(
                GraphFailure(
                    code="STALE_FRAME",
                    operation=request.operation,
                    stage="preflight",
                    graph_input_may_have_been_sent=False,
                    next_action="observe_graph",
                    detail=reason + " Reacquire coordinates.",
                ),
            )

    def _configure_sensor(self, request: NativeRequest) -> JsonValue:
        selection = select_sensor(
            self.app,
            request.handle,
            SensorSelectionRequest(
                sensor=request.sensor,
                allow_foreground=request.allow_foreground,
            ),
        )
        rate = target_sampling_rate(
            self.app,
            request.handle,
            SamplingRateRequest(
                sensor=request.sensor,
                target=request.target,
                step_limit=request.step_limit,
                allow_foreground=request.allow_foreground,
            ),
        )
        return _json(SensorConfiguration(selection=selection, rate=rate))

    def _initialize_recording(self, request: NativeRequest) -> JsonValue:
        self.recording = NativeRecordingBackend(
            RepeatPlan.model_validate(request.plan),
        )
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
        if not (
            0 <= x < rect.right - rect.left and 0 <= y < rect.bottom - rect.top
        ):
            msg = "Coordinates must be inside the current window rectangle."
            raise AutomationError(msg)
        window.click_input(
            button=request.button.value,
            coords=(rect.left + x, rect.top + y),
            double=request.double,
            absolute=True,
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
            coords=(request.point.x, request.point.y),
            wheel_dist=request.notches,
        )
        self.app.refs.clear()
        return Result(detail="Scroll delivered; inspect to verify.")


_ERROR_RULES: Final[tuple[tuple[tuple[str, ...], str, str], ...]] = (
    (
        ("recording",),
        "RECORDING_NOT_INITIALIZED",
        "Initialize recording session before invoking recording operations.",
    ),
    (
        ("attach", "session", "not attached", "no running capstone"),
        "SESSION_NOT_ATTACHED",
        "Call capstone_attach(launch=True) to attach to or launch PASCO Capstone.",
    ),
    (
        (
            "display",
            "digits",
            "table",
            "scope",
            "fft",
            "page",
            "layout",
            "workbook",
        ),
        "DISPLAY_ERROR",
        (
            "Verify display widget container and workbook layout via "
            "capstone://displays/active or reconfigure using capstone_manage_display."
        ),
    ),
    (
        ("sensor", "instrument", "generator", "calibration", "hardware"),
        "INSTRUMENT_ERROR",
        (
            "Verify hardware connection via capstone://hardware/inventory or check "
            "sensor configuration using capstone_manage_instrument."
        ),
    ),
    (
        ("coordinates", "foreground", "drag endpoints", "scroll position"),
        "INVALID_ARGUMENT",
        "Check tool argument types, coordinates, and constraints before retrying.",
    ),
    (
        ("invalid", "validation", "unsupported"),
        "INVALID_ARGUMENT",
        "Check tool argument types, values, and schema constraints before retrying.",
    ),
    (
        ("time",),
        "TIMEOUT_ERROR",
        (
            "Operation timed out; inspect Capstone responsiveness and reattach "
            "if needed."
        ),
    ),
)


def _classify_native_error(error: Exception) -> tuple[str, str]:
    """Return (error_code, remediation) for native exceptions."""
    if isinstance(error, GraphOperationError):
        code = (
            error.failure.code
            if error.failure and error.failure.code
            else "GRAPH_OPERATION_ERROR"
        )
        return (
            code,
            (
                "Verify graph display exists using "
                "capstone_manage_graph(action='read') or snapshot."
            ),
        )

    lower = str(error).lower()
    if "control" in lower and ("not found" in lower or "missing" in lower):
        return (
            "CONTROL_NOT_FOUND",
            (
                "Inspect active window controls using capstone_snapshot to find "
                "valid references."
            ),
        )

    for keywords, code, remediation in _ERROR_RULES:
        if any(kw in lower for kw in keywords):
            return code, remediation

    return (
        "AUTOMATION_ERROR",
        "Check Capstone application state using capstone_windows and retry.",
    )


def main() -> None:
    """Execute each request on the one thread owning this runtime's COM wrappers."""
    runtime = NativeDesktop()
    line = sys.stdin.readline(MAX_MESSAGE_BYTES + 1)
    while line:
        packet = RequestPacket.model_validate_json(line)
        try:
            result = runtime.dispatch(packet.command)
        except GraphOperationError as error:
            LOGGER.exception("Native graph operation failed")
            code, remediation = _classify_native_error(error)
            reply = NativeReply(
                identifier=packet.identifier,
                error=str(error),
                error_code=code,
                remediation=remediation,
                graph_failure=error.failure.model_copy(
                    update={
                        "request_id": packet.identifier,
                    },
                ),
            )
        except Exception as error:
            LOGGER.exception("Native Capstone operation failed")
            code, remediation = _classify_native_error(error)
            reply = NativeReply(
                identifier=packet.identifier,
                error=f"{type(error).__name__}: {error}",
                error_code=code,
                remediation=remediation,
            )
        else:
            reply = NativeReply(identifier=packet.identifier, result=result)
        _ = sys.stdout.write(reply.model_dump_json() + "\n")
        _ = sys.stdout.flush()
        line = sys.stdin.readline(MAX_MESSAGE_BYTES + 1)


if __name__ == "__main__":
    main()
