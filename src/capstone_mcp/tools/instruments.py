# Copyright 2026 Capstone MCP contributors.
"""Tool router for physical and virtual instruments, sensors, and acquisition."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final, Literal
from uuid import UUID

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, JsonValue, TypeAdapter

from capstone_mcp.acquisition import (
    RecordingRequest,
    RecordingStatus,
    SamplingRateChange,
)
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.bridge import (
    NativeInventory,
    read_inventory,
    read_measurement,
)
from capstone_mcp.instruments import (
    CalibrateSensorRequest,
    CalibrateSensorResult,
    ConditionSpec,
    ConnectWirelessSensorRequest,
    ConnectWirelessSensorResult,
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
    KeepSampleRequest,
    KeepSampleResult,
    SamplingMode,
    SamplingRateRequest,
    ScanWirelessSensorsRequest,
    ScanWirelessSensorsResult,
    SensorConfiguration,
    SensorSelection,
    SensorSelectionRequest,
    SetRecordingConditionRequest,
    SetRecordingConditionResult,
    SetSamplingModeRequest,
    SetSamplingModeResult,
    SetSignalGeneratorRequest,
    SetSignalGeneratorResult,
    SignalGeneratorStatusResult,
    ZeroSensorRequest,
    ZeroSensorResult,
)
from capstone_mcp.oscilloscope_fft import (
    CreateFftResult,
    CreateScopeResult,
    ReadFftPeaksResult,
    ScopeTriggerResult,
)
from capstone_mcp.repetition import AcquisitionJobs, JobStatus, RepeatPlan

type NativeCaller = Callable[..., Awaitable[Any]]
JSON_VALUE: Final = TypeAdapter(JsonValue)


def _json_dict(model: BaseModel) -> JsonValue:
    return JSON_VALUE.validate_json(model.model_dump_json())


def register_instrument_tools(  # noqa: PLR0915
    mcp: FastMCP,
    native: NativeCaller,
    jobs: AcquisitionJobs | Callable[[], AcquisitionJobs] | None = None,
) -> dict[str, Any]:
    """Register all sensor, recording, oscilloscope, and instrument tools."""

    def _get_jobs() -> AcquisitionJobs:
        if callable(jobs):
            return jobs()
        if jobs is not None:
            return jobs
        return AcquisitionJobs()

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Manage sensors, hardware, and instruments",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_manage_instrument(
        request: InstrumentRequest,
    ) -> InstrumentResult:
        """Unified compound entry point for all Capstone instrument operations.

        Supported actions (request.action):
        - set_sampling_rate: Navigate sensor rate or select sensor (request.set_sampling_rate)
        - zero_sensor: Zero or tare connected sensors (request.zero_sensor)
        - configure_signal_generator: Configure generator or read status (request.configure_signal_generator)
        - set_recording_condition: Configure start/stop threshold triggers (request.set_recording_condition)
        - set_sampling_mode: Switch sampling mode (continuous, keep_sample) (request.set_sampling_mode)
        - keep_sample: Log discrete point in manual sampling mode (request.keep_sample)
        - scan_wireless: Discover nearby Bluetooth PASCO sensors (request.scan_wireless)
        - connect_wireless: Pair and connect a wireless sensor (request.connect_wireless)
        - calibrate_sensor: Guided 1-point or 2-point sensor calibration (request.calibrate_sensor)
        """
        is_read_only = (
            request.action == InstrumentAction.SCAN_WIRELESS
            or (
                request.action == InstrumentAction.CONFIGURE_SIGNAL_GENERATOR
                and request.configure_signal_generator is not None
                and request.configure_signal_generator.read_only
            )
        )
        return InstrumentResult.model_validate(
            await native(
                NativeRequest(
                    operation="manage_instrument",
                    instrument_request=_json_dict(request),
                ),
                mutates=not is_read_only,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read recording status",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_recording_status(handle: int) -> RecordingStatus:
        """Read actual recording toggle, enabled state, and displayed time/rate."""
        return RecordingStatus.model_validate(
            await native(
                NativeRequest(
                    operation="recording_status",
                    handle=handle,
                ),
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set recording state",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_set_recording(
        handle: int,
        *,
        recording: bool,
        allow_foreground: bool = True,
    ) -> RecordingRequest:
        """Request start/stop only when the observed state differs from the request.

        Requires configured hardware/data sources. Foreground input is enabled by default.
        transition_pending=true means the requested state has not yet been observed;
        it is not a claim that acquisition succeeded.
        """
        return RecordingRequest.model_validate(
            await native(
                NativeRequest(
                    operation="set_recording",
                    handle=handle,
                    recording=recording,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Step sampling rate",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_step_sampling_rate(
        handle: int,
        direction: Literal["increase", "decrease"],
        expected_sensor: str,
        *,
        allow_foreground: bool = True,
    ) -> SamplingRateChange:
        """Move one supported rate step for the explicitly named selected sensor.

        Read the sensor name from a fresh snapshot. Uses Capstone's native discrete
        rate buttons, not a guessed frequency setter; recording must be stopped.
        """
        return SamplingRateChange.model_validate(
            await native(
                NativeRequest(
                    operation="step_sampling_rate",
                    handle=handle,
                    direction=direction,
                    sensor=expected_sensor,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Select sensor",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_select_sensor(
        handle: int,
        request: SensorSelectionRequest,
    ) -> SensorSelection:
        """Select one exact sensor name from the current sampling menu and verify it."""
        return SensorSelection.model_validate(
            await native(
                NativeRequest(
                    operation="select_sensor",
                    handle=handle,
                    sensor=request.sensor,
                    allow_foreground=request.allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Configure sensor sampling rate",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_configure_sensor(
        handle: int,
        request: SamplingRateRequest,
    ) -> SensorConfiguration:
        """Select the named sensor and reach a supported rate such as 100 Hz.

        The target unit must match the native display. Unsupported targets restore
        the selected sensor's original rate rather than silently rounding.
        """
        return SensorConfiguration.model_validate(
            await native(
                NativeRequest(
                    operation="configure_sensor",
                    handle=handle,
                    sensor=request.sensor,
                    target=request.target,
                    step_limit=request.step_limit,
                    allow_foreground=request.allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Repeat acquisition",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_repeat_acquisition(plan: RepeatPlan) -> JobStatus:
        """Start bounded repeated runs, confirming native start/stop events each cycle.

        Requires the debug endpoint and UI to belong to the same Capstone process,
        and an enabled recording source. Foreground input is enabled by default.
        With plan.capture, saves a baseline and each stopped run to a new directory.
        Optional source-ID fitting analyzes only newly attributed samples and compares
        completed runs. Without capture, results remain in Capstone.
        """
        return await anyio.to_thread.run_sync(_get_jobs().start, plan)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read acquisition job status",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_acquisition_job(job_id: str) -> JobStatus:
        """Read a repeat job's completion and confirmed-cycle receipts."""
        return _get_jobs().status(job_id)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Cancel acquisition job",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_cancel_acquisition(job_id: str) -> JobStatus:
        """Request cancellation; completion requires the worker to stop recording."""
        return _get_jobs().cancel(job_id)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Zero or tare sensor",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_zero_sensor(
        handle: int = 0,
        *,
        sensor_name: str | None = None,
        allow_foreground: bool = True,
    ) -> ZeroSensorResult:
        """Execute zero/tare for all connected sensors or a specified target sensor.

        Delegates to capstone_manage_instrument(action='zero_sensor').
        """
        req = InstrumentRequest(
            action=InstrumentAction.ZERO_SENSOR,
            zero_sensor=ZeroSensorRequest(
                handle=handle,
                sensor_name=sensor_name,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.zero_sensor is None:
            msg = "Expected zero_sensor result from manage_instrument"
            raise RuntimeError(msg)
        return res.zero_sensor

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read native live configuration",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_live_configuration(
        debug_port: Annotated[int, Field(ge=1024, le=65535)] = 9223,
    ) -> NativeInventory:
        """Read native sensor/measurement metadata without screen scraping.

        Requires Capstone started with QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:PORT.
        This returns the application's configured metadata, not proof that every
        listed sensor is physically connected.
        """
        return await anyio.to_thread.run_sync(read_inventory, debug_port)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read current measurement value",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_current_value(
        measurement_euid: UUID,
        unit_type: Annotated[int, Field(ge=0)],
        debug_port: Annotated[int, Field(ge=1024, le=65535)] = 9223,
    ) -> float:
        """Read one native current value using IDs returned by live configuration.

        Unavailable values raise an error rather than returning a fabricated zero.
        This is not an extraction of an entire recorded run.
        """
        return await anyio.to_thread.run_sync(
            read_measurement,
            debug_port,
            "{" + str(measurement_euid) + "}",
            unit_type,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Configure signal generator",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_set_signal_generator(  # noqa: PLR0913
        handle: int = 0,
        *,
        waveform: str = "Sine",
        frequency: float | None = 1000.0,
        amplitude: float | None = 1.0,
        enabled: bool = True,
        generator_name: str | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> SetSignalGeneratorResult:
        """Configure signal generator waveform, frequency, amplitude, and power.

        Delegates to capstone_manage_instrument(action='configure_signal_generator').
        """
        req = InstrumentRequest(
            action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
            configure_signal_generator=SetSignalGeneratorRequest(
                handle=handle,
                waveform=waveform,
                frequency=frequency,
                amplitude=amplitude,
                enabled=enabled,
                generator_name=generator_name,
                allow_foreground=allow_foreground,
                keep_open=keep_open,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.configure_signal_generator is None or not isinstance(
            res.configure_signal_generator, SetSignalGeneratorResult,
        ):
            msg = "Expected set_signal_generator result from manage_instrument"
            raise RuntimeError(msg)
        return res.configure_signal_generator

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read signal generator status",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_read_signal_generator_status(
        handle: int = 0,
        *,
        generator_name: str | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> SignalGeneratorStatusResult:
        """Read current waveform, frequency, amplitude, and power of signal generator.

        Delegates to capstone_manage_instrument(action='configure_signal_generator', read_only=True).
        """
        req = InstrumentRequest(
            action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
            configure_signal_generator=SetSignalGeneratorRequest(
                handle=handle,
                generator_name=generator_name,
                allow_foreground=allow_foreground,
                keep_open=keep_open,
                read_only=True,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.configure_signal_generator is None or not isinstance(
            res.configure_signal_generator, SignalGeneratorStatusResult,
        ):
            msg = "Expected read_signal_generator_status result from manage_instrument"
            raise RuntimeError(msg)
        return res.configure_signal_generator

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create oscilloscope display",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_create_scope(
        handle: int = 0,
        *,
        timebase: str | float | None = None,
        channel: str | None = None,
        allow_foreground: bool = True,
    ) -> CreateScopeResult:
        """Create an Oscilloscope display widget on the active page.

        Args:
            handle: Capstone main window handle (0 for active window).
            timebase: Timebase setting (e.g. '1 ms/div', '100 us/div').
            channel: Input sensor channel or measurement name.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            CreateScopeResult with scope_id, channel, and timebase.
        """
        return CreateScopeResult.model_validate(
            await native(
                NativeRequest(
                    operation="create_scope",
                    handle=handle,
                    timebase=str(timebase) if timebase is not None else None,
                    channel=channel,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set oscilloscope trigger",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_set_scope_trigger(  # noqa: PLR0913
        handle: int = 0,
        *,
        scope_id: str | None = None,
        trigger_level: float = 0.0,
        trigger_slope: str = "rising",
        trigger_mode: str = "auto",
        trigger_source: str | None = None,
        allow_foreground: bool = True,
    ) -> ScopeTriggerResult:
        """Configure oscilloscope trigger level, slope edge, mode, and source.

        Args:
            handle: Capstone main window handle (0 for active window).
            scope_id: Specific scope display ID (None targets active scope).
            trigger_level: Threshold voltage level for trigger (Volts).
            trigger_slope: Slope edge ('rising' or 'falling').
            trigger_mode: Trigger mode ('auto', 'normal', or 'single').
            trigger_source: Channel name to trigger from.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            ScopeTriggerResult with applied trigger configuration.
        """
        return ScopeTriggerResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_scope_trigger",
                    handle=handle,
                    scope_id=scope_id,
                    trigger_level=trigger_level,
                    trigger_slope=trigger_slope,
                    trigger_mode=trigger_mode,
                    trigger_source=trigger_source,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create FFT display",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_create_fft(
        handle: int = 0,
        *,
        measurement: str | None = None,
        frequency_range: str | None = None,
        allow_foreground: bool = True,
    ) -> CreateFftResult:
        """Create an FFT frequency spectrum display widget.

        Args:
            handle: Capstone main window handle (0 for active window).
            measurement: Input sensor channel or signal measurement to analyze.
            frequency_range: Maximum frequency span (e.g. '1000 Hz', '20 kHz').
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            CreateFftResult with fft_id, measurement, and frequency_range.
        """
        return CreateFftResult.model_validate(
            await native(
                NativeRequest(
                    operation="create_fft",
                    handle=handle,
                    measurement=measurement,
                    frequency_range=frequency_range,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read FFT peaks",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_read_fft_peaks(
        handle: int = 0,
        *,
        fft_id: str | None = None,
        top_k: int = 5,
        allow_foreground: bool = True,
    ) -> ReadFftPeaksResult:
        """Read top peak frequencies and amplitudes from FFT display.

        Args:
            handle: Capstone main window handle (0 for active window).
            fft_id: Specific FFT display ID (None targets active FFT).
            top_k: Number of highest harmonic peaks to extract (default 5).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            ReadFftPeaksResult with list of detected frequency peaks and amplitudes.
        """
        return ReadFftPeaksResult.model_validate(
            await native(
                NativeRequest(
                    operation="read_fft_peaks",
                    handle=handle,
                    fft_id=fft_id,
                    top_k=top_k,
                    allow_foreground=allow_foreground,
                ),
                mutates=False,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set recording conditions",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_set_recording_condition(
        handle: int = 0,
        *,
        start_condition: dict[str, JsonValue] | None = None,
        stop_condition: dict[str, JsonValue] | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> SetRecordingConditionResult:
        """Configure start/stop recording conditions based on time or threshold.

        Delegates to capstone_manage_instrument(action='set_recording_condition').
        """
        start_cond = (
            ConditionSpec.model_validate(start_condition)
            if start_condition is not None
            else None
        )
        stop_cond = (
            ConditionSpec.model_validate(stop_condition)
            if stop_condition is not None
            else None
        )
        req = InstrumentRequest(
            action=InstrumentAction.SET_RECORDING_CONDITION,
            set_recording_condition=SetRecordingConditionRequest(
                handle=handle,
                start_condition=start_cond,
                stop_condition=stop_cond,
                allow_foreground=allow_foreground,
                keep_open=keep_open,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.set_recording_condition is None:
            msg = "Expected set_recording_condition result from manage_instrument"
            raise RuntimeError(msg)
        return res.set_recording_condition

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set sampling mode",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_set_sampling_mode(
        mode: SamplingMode = "continuous",
        handle: int = 0,
        *,
        allow_foreground: bool = True,
    ) -> SetSamplingModeResult:
        """Switch sampling mode between continuous, keep_sample, and fast_monitor.

        Delegates to capstone_manage_instrument(action='set_sampling_mode').
        """
        req = InstrumentRequest(
            action=InstrumentAction.SET_SAMPLING_MODE,
            set_sampling_mode=SetSamplingModeRequest(
                handle=handle,
                mode=mode,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.set_sampling_mode is None:
            msg = "Expected set_sampling_mode result from manage_instrument"
            raise RuntimeError(msg)
        return res.set_sampling_mode

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Keep manual sample point",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_keep_sample(
        handle: int = 0,
        *,
        value: float | None = None,
        variable_name: str | None = None,
        allow_foreground: bool = True,
    ) -> KeepSampleResult:
        """Record one manual sample point in keep_sample mode.

        Delegates to capstone_manage_instrument(action='keep_sample').
        """
        req = InstrumentRequest(
            action=InstrumentAction.KEEP_SAMPLE,
            keep_sample=KeepSampleRequest(
                handle=handle,
                value=value,
                variable_name=variable_name,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.keep_sample is None:
            msg = "Expected keep_sample result from manage_instrument"
            raise RuntimeError(msg)
        return res.keep_sample

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Scan wireless sensors",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_scan_wireless_sensors(
        handle: int = 0,
        *,
        timeout_seconds: float = 5.0,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> ScanWirelessSensorsResult:
        """Scan for nearby wireless Bluetooth PASCO sensors.

        Delegates to capstone_manage_instrument(action='scan_wireless').
        """
        req = InstrumentRequest(
            action=InstrumentAction.SCAN_WIRELESS,
            scan_wireless=ScanWirelessSensorsRequest(
                handle=handle,
                timeout_seconds=timeout_seconds,
                allow_foreground=allow_foreground,
                keep_open=keep_open,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.scan_wireless is None:
            msg = "Expected scan_wireless result from manage_instrument"
            raise RuntimeError(msg)
        return res.scan_wireless

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Connect wireless sensor",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_connect_wireless_sensor(
        sensor_id: str,
        handle: int = 0,
        *,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> ConnectWirelessSensorResult:
        """Pair and connect a discovered wireless sensor by sensor_id.

        Delegates to capstone_manage_instrument(action='connect_wireless').
        """
        req = InstrumentRequest(
            action=InstrumentAction.CONNECT_WIRELESS,
            connect_wireless=ConnectWirelessSensorRequest(
                handle=handle,
                sensor_id=sensor_id,
                allow_foreground=allow_foreground,
                keep_open=keep_open,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.connect_wireless is None:
            msg = "Expected connect_wireless result from manage_instrument"
            raise RuntimeError(msg)
        return res.connect_wireless

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Calibrate sensor",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_calibrate_sensor(  # noqa: PLR0913
        sensor_name: str,
        handle: int = 0,
        *,
        measurement_type: str | None = None,
        calibration_type: str = "two_point",
        standard_1: float = 0.0,
        standard_2: float | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> CalibrateSensorResult:
        """Execute sensor calibration wizard with standard reference points.

        Delegates to capstone_manage_instrument(action='calibrate_sensor').
        """
        req = InstrumentRequest(
            action=InstrumentAction.CALIBRATE_SENSOR,
            calibrate_sensor=CalibrateSensorRequest(
                handle=handle,
                sensor_name=sensor_name,
                measurement_type=measurement_type,
                calibration_type=calibration_type,
                standard_1=standard_1,
                standard_2=standard_2,
                allow_foreground=allow_foreground,
                keep_open=keep_open,
            ),
        )
        res = await capstone_manage_instrument(req)
        if res.calibrate_sensor is None:
            msg = "Expected calibrate_sensor result from manage_instrument"
            raise RuntimeError(msg)
        return res.calibrate_sensor

    return {
        "capstone_manage_instrument": capstone_manage_instrument,
        "capstone_recording_status": capstone_recording_status,
        "capstone_set_recording": capstone_set_recording,
        "capstone_step_sampling_rate": capstone_step_sampling_rate,
        "capstone_select_sensor": capstone_select_sensor,
        "capstone_configure_sensor": capstone_configure_sensor,
        "capstone_repeat_acquisition": capstone_repeat_acquisition,
        "capstone_acquisition_job": capstone_acquisition_job,
        "capstone_cancel_acquisition": capstone_cancel_acquisition,
        "capstone_zero_sensor": capstone_zero_sensor,
        "capstone_live_configuration": capstone_live_configuration,
        "capstone_current_value": capstone_current_value,
        "capstone_set_signal_generator": capstone_set_signal_generator,
        "capstone_read_signal_generator_status": capstone_read_signal_generator_status,
        "capstone_create_scope": capstone_create_scope,
        "capstone_set_scope_trigger": capstone_set_scope_trigger,
        "capstone_create_fft": capstone_create_fft,
        "capstone_read_fft_peaks": capstone_read_fft_peaks,
        "capstone_set_recording_condition": capstone_set_recording_condition,
        "capstone_set_sampling_mode": capstone_set_sampling_mode,
        "capstone_keep_sample": capstone_keep_sample,
        "capstone_scan_wireless_sensors": capstone_scan_wireless_sensors,
        "capstone_connect_wireless_sensor": capstone_connect_wireless_sensor,
        "capstone_calibrate_sensor": capstone_calibrate_sensor,
    }

