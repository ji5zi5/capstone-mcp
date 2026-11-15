# Copyright 2026 Capstone MCP contributors.
"""Complete in-memory fake backend simulating 50+ Capstone RPC protocols."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from pydantic import JsonValue

    from capstone_mcp.automation_models import NativeRequest

from capstone_mcp.backend_protocol import ICapstoneBackend
from capstone_mcp.displays.models import (
    AddPageResult,
    CreateDigitsResult,
    CreateFftResult,
    CreateScopeResult,
    CreateTableResult,
    DisplayAction,
    DisplayRequest,
    DisplayResult,
    ReadFftPeaksResult,
    ReadTableResult,
    ScopeTriggerResult,
    SetPageLayoutResult,
    SetTableColumnsResult,
)
from capstone_mcp.graphs.models import (
    AnalyzeGraphResult,
    FitGraphResult,
    FitModel,
    GraphAction,
    GraphDeltaResult,
    GraphFitOutcome,
    GraphRequest,
    GraphResult,
    GraphState,
    GraphStatistics,
    MeasureGraphAreaResult,
    ReadGraphResult,
    ToggleGraphStatisticsResult,
)
from capstone_mcp.instruments.models import (
    CalibrateSensorResult,
    ConnectWirelessSensorResult,
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
    KeepSampleResult,
    ScanWirelessSensorsResult,
    SetRecordingConditionResult,
    SetSamplingModeResult,
    SetSignalGeneratorResult,
    WirelessSensorInfo,
    ZeroSensorResult,
)
from capstone_mcp.models import (
    Action,
    Bounds,
    Control,
    Result,
    Snapshot,
    Window,
)
from capstone_mcp.runs.models import (
    DeleteRunResult,
    RenameRunResult,
    RunAction,
    RunRequest,
    RunResult,
    SetRunVisibilityResult,
)


class InMemoryFakeBackend(ICapstoneBackend):
    """Deterministic, side-effect-free in-memory Capstone simulation engine."""

    def __init__(self, *, default_pid: int = 4242) -> None:
        """Initialize default virtual state."""
        self._default_pid: int = default_pid
        self._pid: int | None = default_pid
        self._attached: bool = True
        self._main_handle: int = 10001

        # Windows and Controls
        self._windows: list[Window] = [
            Window(
                handle=self._main_handle,
                title="PASCO Capstone - [Untitled.cap*]",
                process_id=self._default_pid,
                bounds=Bounds(left=0, top=0, right=1920, bottom=1080),
            ),
        ]
        self._controls: dict[str, Control] = {}
        self._control_values: dict[str, str] = {}
        self._init_default_controls()

        # Recording & Session State
        self._recording: bool = False
        self._sampling_rate: str = "100 Hz"
        self._sampling_mode: str = "continuous"
        self._runs: dict[str, dict[str, Any]] = {
            "Run 1": {"visible": True, "created_at": 1700000000.0},
            "Run 2": {"visible": True, "created_at": 1700000100.0},
        }

        # Domain instruments state
        self._signal_gen_state: dict[str, Any] = {
            "generator_name": "Output 1",
            "waveform": "Sine",
            "frequency": 440.0,
            "amplitude": 1.5,
            "enabled": True,
            "detail": "Signal generator configured",
        }
        self._wireless_devices: list[WirelessSensorInfo] = [
            WirelessSensorInfo(
                sensor_id="642-108",
                name="Wireless Force Sensor",
                connected=False,
                battery_percent=85,
            ),
            WirelessSensorInfo(
                sensor_id="024-511",
                name="Wireless Motion Sensor",
                connected=True,
                battery_percent=92,
            ),
        ]
        self._recording_conditions: dict[str, Any] = {
            "start_condition": "none",
            "stop_condition": "time",
        }

        # Displays & Pages state
        self._pages: list[str] = ["Page 1"]
        self._active_page_layout: str = "two_vertical"
        self._table_data: list[list[float]] = [
            [float(i) * 0.1, round(float(i) * 0.98, 2)] for i in range(10)
        ]
        self._table_columns: list[str] = ["Time (s)", "Position (m)"]

    def _init_default_controls(self) -> None:
        """Seed simulated UIA controls for Capstone main window."""
        defs = [
            ("ref:btn_record", "Record", "Button", "Palette.ObjNameRecord"),
            ("ref:btn_stop", "Stop", "Button", "Palette.ObjNameStop"),
            (
                "ref:hw_toggle",
                "Hardware Setup",
                "CheckBox",
                "Palette.ObjNameHardware",
            ),
            (
                "ref:sig_toggle",
                "Signal Generator",
                "CheckBox",
                "Palette.ObjNameSignalGen",
            ),
            (
                "ref:calc_toggle",
                "Calculator",
                "CheckBox",
                "Palette.ObjNameCalculator",
            ),
        ]
        for ref, name, c_type, auto_id in defs:
            self._controls[ref] = Control(
                ref=ref,
                parent=None,
                name=name,
                control_type=c_type,
                automation_id=auto_id,
                enabled=True,
                visible=True,
                bounds=Bounds(left=10, top=10, right=100, bottom=40),
            )
            self._control_values[ref] = "off"

    # -----------------------------------------------------------------------
    # ICapstoneBackend Core UI Surface
    # -----------------------------------------------------------------------

    @property
    @override
    def process_id(self) -> int | None:
        """Return running process ID or None."""
        return self._pid

    @override
    def attach(
        self,
        *,
        launch: bool = False,
        process_id: int | None = None,
    ) -> list[Window]:
        """Attach to virtual Capstone instance."""
        if process_id is not None:
            self._pid = process_id
        elif launch or self._pid is None:
            self._pid = self._default_pid
        self._attached = True
        return self._windows

    @override
    def windows(self) -> list[Window]:
        """Return active virtual windows."""
        return self._windows

    @override
    def snapshot(
        self,
        handle: int,
        depth: int = 12,
        limit: int = 200,
        *,
        query: str | None = None,
        control_types: list[str] | None = None,
    ) -> Snapshot:
        """Return virtual UI control snapshot."""
        del depth
        win = self._windows[0] if not handle else next(
            (w for w in self._windows if w.handle == handle),
            self._windows[0],
        )
        ctrls = list(self._controls.values())
        if query:
            q = query.lower()
            ctrls = [
                c for c in ctrls
                if q in c.name.lower() or q in c.automation_id.lower()
            ]
        if control_types:
            types_set = set(control_types)
            ctrls = [c for c in ctrls if c.control_type in types_set]
        return Snapshot(
            window=win,
            controls=ctrls[:limit],
            truncated=len(ctrls) > limit,
        )

    @override
    def act(
        self,
        ref: str,
        action: Action,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Simulate UI action invocation."""
        del allow_foreground
        if ref not in self._controls:
            return Result(
                delivered=False,
                detail=f"Control {ref} not found",
            )
        if ref == "ref:btn_record":
            self._recording = True
        elif ref == "ref:btn_stop":
            self._recording = False
        elif ref in self._control_values:
            cur = self._control_values[ref]
            self._control_values[ref] = "off" if cur == "on" else "on"
        return Result(delivered=True, detail=f"Action {action} on {ref}")

    @override
    def click(
        self,
        handle: int,
        ref: str,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Simulate clicking a control."""
        del handle
        return self.act(ref, Action.INVOKE, allow_foreground=allow_foreground)

    @override
    def type_text(self, text: str) -> None:
        """Simulate typing text into the focused control."""
        self._control_values["focused"] = text
        self._control_values["ref:focused"] = text

    @override
    def screenshot(
        self,
        handle: int,
        *,
        scale: float = 1.0,
        crop_region: list[int] | None = None,
    ) -> bytes:
        """Return 1x1 simulated PNG byte array."""
        del handle, scale, crop_region
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    # -----------------------------------------------------------------------
    # Graph Domain Seam Dispatch
    # -----------------------------------------------------------------------

    @override
    def manage_graph(self, request: GraphRequest) -> GraphResult:
        """Handle graph compound domain actions."""
        handlers = {
            GraphAction.READ: self._graph_read,
            GraphAction.FIT: self._graph_fit,
            GraphAction.TOOLBOX_STATISTICS: self._graph_stats,
            GraphAction.TOOLBOX_DELTA: self._graph_delta,
            GraphAction.TOOLBOX_AREA: self._graph_area,
            GraphAction.ANALYZE: self._graph_analyze,
        }
        handler = handlers.get(request.action)
        if handler:
            return handler(request)
        return GraphResult(action=request.action)

    def _graph_read(self, request: GraphRequest) -> GraphResult:
        res = ReadGraphResult(
            state=GraphState(
                fit_enabled=True,
                selected_types=[1],
                series=[],
            ),
            verified=True,
        )
        return GraphResult(action=request.action, read=res)

    def _graph_fit(self, request: GraphRequest) -> GraphResult:
        fit_res = FitGraphResult(
            mode="scale_to_fit",
            target_ref="ref:graph",
            clicked_point=(20, 20),
            verified=True,
            detail="Graph scaled to fit data bounds",
        )
        return GraphResult(action=request.action, fit=fit_res)

    def _graph_stats(self, request: GraphRequest) -> GraphResult:
        stats_res = ToggleGraphStatisticsResult(
            visible=True,
            statistics=GraphStatistics(
                mean=2.39,
                std_dev=1.75,
                min=0.0,
                max=4.71,
                count=6,
            ),
            verified=True,
            detail="Statistics overlay toggled",
        )
        return GraphResult(action=request.action, toolbox_statistics=stats_res)

    def _graph_delta(self, request: GraphRequest) -> GraphResult:
        delta_res = GraphDeltaResult(
            visible=True,
            active=True,
            dx=0.5,
            dy=1.2,
            delta_x=0.5,
            delta_y=1.2,
            verified=True,
            detail="Delta crosshair positioned",
        )
        return GraphResult(action=request.action, toolbox_delta=delta_res)

    def _graph_area(self, request: GraphRequest) -> GraphResult:
        area_res = MeasureGraphAreaResult(
            visible=True,
            area=1.18,
            verified=True,
            detail="Integral area computed",
        )
        return GraphResult(action=request.action, toolbox_area=area_res)

    def _graph_analyze(self, request: GraphRequest) -> GraphResult:
        state = GraphState(
            fit_enabled=True,
            selected_types=[1],
            series=[],
        )
        outcome = GraphFitOutcome(
            changed=True,
            requested_models=[FitModel.LINEAR],
            fits_successful=True,
            before=state,
            after=state,
        )
        res = AnalyzeGraphResult(outcome=outcome)
        return GraphResult(action=request.action, analyze=res)

    # -----------------------------------------------------------------------
    # Instrument Domain Seam Dispatch
    # -----------------------------------------------------------------------

    @override
    def manage_instrument(self, request: InstrumentRequest) -> InstrumentResult:
        """Handle instrument compound domain actions."""
        handlers = {
            InstrumentAction.SCAN_WIRELESS: self._inst_scan,
            InstrumentAction.CONNECT_WIRELESS: self._inst_connect,
            InstrumentAction.CONFIGURE_SIGNAL_GENERATOR: self._inst_sig_gen,
            InstrumentAction.SET_SAMPLING_MODE: self._inst_sampling_mode,
            InstrumentAction.ZERO_SENSOR: self._inst_zero,
            InstrumentAction.CALIBRATE_SENSOR: self._inst_calibrate,
            InstrumentAction.KEEP_SAMPLE: self._inst_keep_sample,
            InstrumentAction.SET_RECORDING_CONDITION: self._inst_condition,
        }
        handler = handlers.get(request.action)
        if handler:
            return handler(request)
        return InstrumentResult(action=request.action)

    def _inst_scan(self, request: InstrumentRequest) -> InstrumentResult:
        return InstrumentResult(
            action=request.action,
            scan_wireless=ScanWirelessSensorsResult(
                sensors=self._wireless_devices,
                count=len(self._wireless_devices),
                detail="Wireless sensors enumerated",
            ),
        )

    def _inst_connect(self, request: InstrumentRequest) -> InstrumentResult:
        sid = (
            request.connect_wireless.sensor_id
            if request.connect_wireless
            else "642-108"
        )
        return InstrumentResult(
            action=request.action,
            connect_wireless=ConnectWirelessSensorResult(
                sensor_id=sid,
                name="Wireless Sensor",
                connected=True,
                detail="Wireless sensor connected",
            ),
        )

    def _inst_sig_gen(self, request: InstrumentRequest) -> InstrumentResult:
        if request.configure_signal_generator:
            sg = request.configure_signal_generator
            self._signal_gen_state["waveform"] = sg.waveform
            self._signal_gen_state["frequency"] = sg.frequency
            self._signal_gen_state["amplitude"] = sg.amplitude
            self._signal_gen_state["enabled"] = sg.enabled
        return InstrumentResult(
            action=request.action,
            configure_signal_generator=SetSignalGeneratorResult(
                **self._signal_gen_state,
            ),
        )

    def _inst_sampling_mode(self, req: InstrumentRequest) -> InstrumentResult:
        mode = (
            req.set_sampling_mode.mode
            if req.set_sampling_mode
            else "continuous"
        )
        self._sampling_mode = mode
        return InstrumentResult(
            action=req.action,
            set_sampling_mode=SetSamplingModeResult(
                mode=mode,
                detail=f"Sampling mode set to {mode}",
            ),
        )

    def _inst_zero(self, request: InstrumentRequest) -> InstrumentResult:
        sname = (
            request.zero_sensor.sensor_name
            if request.zero_sensor and request.zero_sensor.sensor_name
            else "Force"
        )
        return InstrumentResult(
            action=request.action,
            zero_sensor=ZeroSensorResult(
                zeroed_sensors=[sname],
                verified=True,
                detail=f"Sensor {sname} zeroed",
            ),
        )

    def _inst_calibrate(self, request: InstrumentRequest) -> InstrumentResult:
        sname = (
            request.calibrate_sensor.sensor_name
            if request.calibrate_sensor
            else "Force"
        )
        return InstrumentResult(
            action=request.action,
            calibrate_sensor=CalibrateSensorResult(
                sensor_name=sname,
                measurement_type="Force",
                calibration_type="two_point",
                standard_1=0.0,
                detail=f"Sensor {sname} calibrated",
            ),
        )

    def _inst_keep_sample(self, req: InstrumentRequest) -> InstrumentResult:
        return InstrumentResult(
            action=req.action,
            keep_sample=KeepSampleResult(
                sample_retained=True,
                detail="Manual sample preserved",
            ),
        )

    def _inst_condition(self, req: InstrumentRequest) -> InstrumentResult:
        return InstrumentResult(
            action=req.action,
            set_recording_condition=SetRecordingConditionResult(
                detail="Recording condition configured",
            ),
        )

    # -----------------------------------------------------------------------
    # Displays Domain Seam Dispatch
    # -----------------------------------------------------------------------

    @override
    def manage_display(self, request: DisplayRequest) -> DisplayResult:
        """Handle display compound domain actions."""
        handlers = {
            DisplayAction.CREATE_SCOPE: self._disp_scope,
            DisplayAction.SET_SCOPE_TRIGGER: self._disp_scope_trigger,
            DisplayAction.CREATE_FFT: self._disp_fft,
            DisplayAction.READ_FFT_PEAKS: self._disp_fft_peaks,
            DisplayAction.CREATE_TABLE: self._disp_create_table,
            DisplayAction.READ_TABLE: self._disp_read_table,
            DisplayAction.SET_TABLE_COLUMNS: self._disp_set_columns,
            DisplayAction.CREATE_DIGITS: self._disp_digits,
            DisplayAction.ADD_PAGE: self._disp_add_page,
            DisplayAction.SET_PAGE_LAYOUT: self._disp_layout,
        }
        handler = handlers.get(request.action)
        if handler:
            return handler(request)
        return DisplayResult(action=request.action)

    def _disp_scope(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            create_scope=CreateScopeResult(
                display_id="Scope 1",
                display_type="Scope",
                detail="Scope display inserted",
            ),
        )

    def _disp_scope_trigger(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            set_scope_trigger=ScopeTriggerResult(
                scope_id="Scope 1",
                trigger_level=0.0,
                trigger_slope="rising",
                trigger_mode="auto",
                detail="Scope trigger configured",
            ),
        )

    def _disp_fft(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            create_fft=CreateFftResult(
                display_id="FFT 1",
                display_type="FFT",
                detail="FFT display inserted",
            ),
        )

    def _disp_fft_peaks(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            read_fft_peaks=ReadFftPeaksResult(
                fft_id="FFT 1",
                peaks=[],
                detail="FFT peaks extracted",
            ),
        )

    def _disp_create_table(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            create_table=CreateTableResult(
                table_name="Table 1",
                created=True,
                detail="Table display inserted",
            ),
        )

    def _disp_read_table(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            read_table=ReadTableResult(
                table_name="Table 1",
                columns=self._table_columns,
                rows=self._table_data,
                row_count=len(self._table_data),
                total_rows=len(self._table_data),
                detail="Table rows read",
            ),
        )

    def _disp_set_columns(self, request: DisplayRequest) -> DisplayResult:
        cols = (
            request.set_table_columns.columns
            if request.set_table_columns
            else ["Time (s)"]
        )
        self._table_columns = cols
        return DisplayResult(
            action=request.action,
            set_table_columns=SetTableColumnsResult(
                table_name="Table 1",
                columns=cols,
                column_count=len(cols),
                detail="Table columns bound",
            ),
        )

    def _disp_digits(self, request: DisplayRequest) -> DisplayResult:
        return DisplayResult(
            action=request.action,
            create_digits=CreateDigitsResult(
                digits_name="Digits 1",
                created=True,
                detail="Digits display inserted",
            ),
        )

    def _disp_add_page(self, request: DisplayRequest) -> DisplayResult:
        title = (
            request.add_page.title
            if request.add_page
            else f"Page {len(self._pages) + 1}"
        )
        self._pages.append(title)
        return DisplayResult(
            action=request.action,
            add_page=AddPageResult(
                page_index=len(self._pages),
                title=title,
                detail="Workbook page created",
            ),
        )

    def _disp_layout(self, request: DisplayRequest) -> DisplayResult:
        lay = (
            request.set_page_layout.layout
            if request.set_page_layout
            else "single"
        )
        self._active_page_layout = lay
        return DisplayResult(
            action=request.action,
            set_page_layout=SetPageLayoutResult(
                layout=lay,
                areas_created=2,
                detail="Workbook page layout applied",
            ),
        )

    # -----------------------------------------------------------------------
    # Runs Domain Seam Dispatch
    # -----------------------------------------------------------------------

    @override
    def manage_run(self, request: RunRequest) -> RunResult:
        """Handle run lifecycle compound domain actions."""
        handlers = {
            RunAction.RENAME: self._run_rename,
            RunAction.DELETE: self._run_delete,
            RunAction.SET_VISIBILITY: self._run_visibility,
        }
        handler = handlers.get(request.action)
        if handler:
            return handler(request)
        return RunResult(action=request.action)

    def _run_rename(self, request: RunRequest) -> RunResult:
        old_name = request.rename.old_name if request.rename else "Run #1"
        new_name = request.rename.new_name if request.rename else "Trial A"
        if old_name in self._runs:
            val = self._runs.pop(old_name)
            self._runs[new_name] = val
        return RunResult(
            action=request.action,
            rename=RenameRunResult(
                old_name=old_name,
                new_name=new_name,
                verified=True,
                detail="Run renamed",
            ),
        )

    def _run_delete(self, request: RunRequest) -> RunResult:
        run_name = request.delete.run_name if request.delete else "Run #2"
        self._runs.pop(run_name, None)
        return RunResult(
            action=request.action,
            delete=DeleteRunResult(
                deleted_run=run_name,
                verified=True,
                detail="Run deleted",
            ),
        )

    def _run_visibility(self, request: RunRequest) -> RunResult:
        runs = (
            request.visibility.runs
            if request.visibility
            else ["Run #1"]
        )
        vis = (
            request.visibility.visible
            if request.visibility
            else True
        )
        for r in runs:
            if r in self._runs:
                self._runs[r]["visible"] = vis
        return RunResult(
            action=request.action,
            visibility=SetRunVisibilityResult(
                visible_runs=runs,
                target_displays=[],
                detail="Run visibility updated",
                verified=True,
            ),
        )

    # -----------------------------------------------------------------------
    # Low-level Native IPC Simulation Dispatch
    # -----------------------------------------------------------------------

    @override
    def call(self, request: NativeRequest) -> JsonValue:
        """Simulate low-level worker IPC call dispatch."""
        op = request.operation
        result = (
            self._call_ui_ops(op, request)
            or self._call_ui_actions(op, request)
            or self._call_recording_ops(op, request)
            or self._call_domain_ops(op, request)
            or self._call_legacy_graph_table_ops(op, request)
            or self._call_legacy_run_ops(op, request)
        )
        if result is not None:
            return result
        return {"status": "ok", "operation": op}

    def _call_ui_ops(
        self,
        op: str,
        request: NativeRequest,
    ) -> JsonValue | None:
        """Dispatch core UI automation operations."""
        if op == "attach":
            wins = self.attach(
                launch=request.launch,
                process_id=request.process_id,
            )
            return [w.model_dump() for w in wins]
        if op == "windows":
            return [w.model_dump() for w in self.windows()]
        if op == "snapshot":
            return self.snapshot(
                handle=request.handle,
                depth=request.depth,
                limit=request.limit,
                query=request.query,
                control_types=request.control_types,
            ).model_dump()
        return None

    def _call_ui_actions(
        self,
        op: str,
        request: NativeRequest,
    ) -> JsonValue | None:
        """Dispatch UI action and click operations."""
        if op == "action":
            return self.act(
                request.ref,
                request.action,
                allow_foreground=request.allow_foreground,
            ).model_dump()
        if op == "click":
            return self.click(
                request.handle,
                request.ref,
                allow_foreground=request.allow_foreground,
            ).model_dump()
        if op == "screenshot":
            raw = self.screenshot(
                request.handle,
                scale=request.scale,
                crop_region=request.crop_region,
            )
            return base64.b64encode(raw).decode("ascii")
        return None

    def _call_recording_ops(
        self,
        op: str,
        request: NativeRequest,
    ) -> JsonValue | None:
        """Dispatch recording and rate control operations."""
        if op == "start_recording" or (op == "set_recording" and request.recording):
            self._recording = True
            return {"recording": True, "status": "started"}
        if op == "stop_recording" or (op == "set_recording" and not request.recording):
            self._recording = False
            return {"recording": False, "status": "stopped"}
        if op in ("recording_status", "recording_observe"):
            return {
                "recording": self._recording,
                "sampling_rate": self._sampling_rate,
                "sampling_mode": self._sampling_mode,
            }
        if op == "step_sampling_rate":
            self._sampling_rate = (
                "200 Hz" if request.direction == "increase" else "50 Hz"
            )
            return {
                "sampling_rate": self._sampling_rate,
                "direction": request.direction,
            }
        return None

    def _call_domain_ops(
        self,
        op: str,
        request: NativeRequest,
    ) -> JsonValue | None:
        """Dispatch 4-domain compound seam operations."""
        if op == "manage_graph":
            req_g = GraphRequest.model_validate(request.graph_request)
            return self.manage_graph(req_g).model_dump()
        if op == "manage_instrument":
            req_i = InstrumentRequest.model_validate(request.instrument_request)
            return self.manage_instrument(req_i).model_dump()
        if op == "manage_display":
            req_d = DisplayRequest.model_validate(request.display_request)
            return self.manage_display(req_d).model_dump()
        if op == "manage_run":
            req_r = RunRequest.model_validate(request.run_request)
            return self.manage_run(req_r).model_dump()
        return None

    def _call_legacy_graph_table_ops(
        self,
        op: str,
        request: NativeRequest,
    ) -> JsonValue | None:
        """Dispatch legacy unbundled graph & table operations."""
        del request
        if op == "read_graph":
            res = self.manage_graph(GraphRequest(action=GraphAction.READ))
            return res.model_dump()["read"]
        if op == "fit_graph":
            res = self.manage_graph(
                GraphRequest(action=GraphAction.FIT),
            )
            return res.model_dump()["fit"]
        if op == "create_table":
            res = self.manage_display(
                DisplayRequest(
                    action=DisplayAction.CREATE_TABLE,
                ),
            )
            return res.model_dump()["create_table"]
        if op == "read_table":
            res = self.manage_display(
                DisplayRequest(
                    action=DisplayAction.READ_TABLE,
                ),
            )
            return res.model_dump()["read_table"]
        return None

    def _call_legacy_run_ops(
        self,
        op: str,
        request: NativeRequest,
    ) -> JsonValue | None:
        """Dispatch legacy unbundled run operations."""
        del request
        if op == "rename_run":
            res = self.manage_run(
                RunRequest(action=RunAction.RENAME),
            )
            return res.model_dump()["rename"]
        if op == "delete_run":
            res = self.manage_run(
                RunRequest(action=RunAction.DELETE),
            )
            return res.model_dump()["delete"]
        return None
