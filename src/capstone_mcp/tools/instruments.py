# Copyright 2026 Capstone MCP contributors.
"""Tool router for physical and virtual instruments, sensors, and acquisition."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal
from uuid import UUID

import anyio
from mcp.server.fastmcp import FastMCP
from pydantic import Field, JsonValue

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
from capstone_mcp.oscilloscope_fft import (
    CreateFftResult,
    CreateScopeResult,
    ReadFftPeaksResult,
    ScopeTriggerResult,
)
from capstone_mcp.repetition import AcquisitionJobs, JobStatus, RepeatPlan
from capstone_mcp.sensor_settings import (
    SamplingRateRequest,
    SensorConfiguration,
    SensorSelection,
    SensorSelectionRequest,
)
from capstone_mcp.sensor_zero import ZeroSensorResult
from capstone_mcp.signal_generator import (
    SetSignalGeneratorResult,
    SignalGeneratorStatusResult,
)
from capstone_mcp.smart_triggers import (
    KeepSampleResult,
    SamplingMode,
    SetRecordingConditionResult,
    SetSamplingModeResult,
)
from capstone_mcp.wireless_calibration import (
    CalibrateSensorResult,
    ConnectWirelessSensorResult,
    ScanWirelessSensorsResult,
)

type NativeCaller = Callable[..., Awaitable[Any]]


def register_instrument_tools(
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

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
    async def capstone_repeat_acquisition(plan: RepeatPlan) -> JobStatus:
        """Start bounded repeated runs, confirming native start/stop events each cycle.

        Requires the debug endpoint and UI to belong to the same Capstone process,
        and an enabled recording source. Foreground input is enabled by default.
        With plan.capture, saves a baseline and each stopped run to a new directory.
        Optional source-ID fitting analyzes only newly attributed samples and compares
        completed runs. Without capture, results remain in Capstone.
        """
        return await anyio.to_thread.run_sync(_get_jobs().start, plan)

    @mcp.tool()
    def capstone_acquisition_job(job_id: str) -> JobStatus:
        """Read a repeat job's completion and confirmed-cycle receipts."""
        return _get_jobs().status(job_id)

    @mcp.tool()
    def capstone_cancel_acquisition(job_id: str) -> JobStatus:
        """Request cancellation; completion requires the worker to stop recording."""
        return _get_jobs().cancel(job_id)

    @mcp.tool()
    async def capstone_zero_sensor(
        handle: int = 0,
        *,
        sensor_name: str | None = None,
        allow_foreground: bool = True,
    ) -> ZeroSensorResult:
        """Execute zero/tare for all connected sensors or a specified target sensor.

        Args:
            handle: Capstone main window handle (0 for active window).
            sensor_name: Target sensor to zero (e.g. 'Force Sensor', None for all).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            ZeroSensorResult with zeroed sensor list and confirmation status.
        """
        return ZeroSensorResult.model_validate(
            await native(
                NativeRequest(
                    operation="zero_sensor",
                    handle=handle,
                    sensor_name=sensor_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_live_configuration(
        debug_port: Annotated[int, Field(ge=1024, le=65535)] = 9223,
    ) -> NativeInventory:
        """Read native sensor/measurement metadata without screen scraping.

        Requires Capstone started with QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:PORT.
        This returns the application's configured metadata, not proof that every
        listed sensor is physically connected.
        """
        return await anyio.to_thread.run_sync(read_inventory, debug_port)

    @mcp.tool()
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

    @mcp.tool()
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

        Args:
            handle: Capstone main window handle (0 for active window).
            waveform: Shape ('Sine', 'Square', 'Triangle', 'Ramp Up', 'Ramp Down', 'DC').
            frequency: Target frequency in Hertz (Hz).
            amplitude: Target peak amplitude in Volts (V).
            enabled: Turn signal output On (True) or Off (False).
            generator_name: Target generator channel ('Output 1', None for default).
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Keep signal generator side drawer open after configuration.

        Returns:
            SetSignalGeneratorResult with applied parameters and output status.
        """
        return SetSignalGeneratorResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_signal_generator",
                    handle=handle,
                    waveform=waveform,
                    frequency=frequency,
                    amplitude=amplitude,
                    enabled=enabled,
                    generator_name=generator_name,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_read_signal_generator_status(
        handle: int = 0,
        *,
        generator_name: str | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> SignalGeneratorStatusResult:
        """Read current waveform, frequency, amplitude, and power of signal generator.

        Args:
            handle: Capstone main window handle (0 for active window).
            generator_name: Target generator channel (e.g. 'Output 1', None for default).
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Keep signal generator side drawer open after reading.

        Returns:
            SignalGeneratorStatusResult with waveform, frequency, amplitude, and enabled.
        """
        return SignalGeneratorStatusResult.model_validate(
            await native(
                NativeRequest(
                    operation="read_signal_generator_status",
                    handle=handle,
                    generator_name=generator_name,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
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

    @mcp.tool()
    async def capstone_set_recording_condition(
        handle: int = 0,
        *,
        start_condition: dict[str, JsonValue] | None = None,
        stop_condition: dict[str, JsonValue] | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> SetRecordingConditionResult:
        """Configure start/stop recording conditions based on time or threshold.

        Args:
            handle: Capstone main window handle (0 for active window).
            start_condition: Start criteria (e.g. {'type': 'threshold', 'value': 0.5}).
            stop_condition: Stop criteria (e.g. {'type': 'time', 'duration_seconds': 5.0}).
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Leave recording condition drawer open.

        Returns:
            SetRecordingConditionResult with applied start/stop conditions.
        """
        return SetRecordingConditionResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_recording_condition",
                    handle=handle,
                    start_condition=start_condition,
                    stop_condition=stop_condition,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_set_sampling_mode(
        mode: SamplingMode = "continuous",
        handle: int = 0,
        *,
        allow_foreground: bool = True,
    ) -> SetSamplingModeResult:
        """Switch sampling mode between continuous, keep_sample, and fast_monitor.

        Args:
            mode: Sampling mode ('continuous', 'keep_sample', or 'fast_monitor').
            handle: Capstone main window handle (0 for active window).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            SetSamplingModeResult with active mode and description.
        """
        return SetSamplingModeResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_sampling_mode",
                    handle=handle,
                    sampling_mode=mode,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_keep_sample(
        handle: int = 0,
        *,
        value: float | None = None,
        variable_name: str | None = None,
        allow_foreground: bool = True,
    ) -> KeepSampleResult:
        """Record one manual sample point in keep_sample mode.

        Args:
            handle: Capstone main window handle (0 for active window).
            value: Optional manual independent variable value (e.g. mass, concentration).
            variable_name: Name of the independent variable being recorded.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            KeepSampleResult with recorded sample index, values, and total points.
        """
        return KeepSampleResult.model_validate(
            await native(
                NativeRequest(
                    operation="keep_sample",
                    handle=handle,
                    sample_value=value,
                    variable_name=variable_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_scan_wireless_sensors(
        handle: int = 0,
        *,
        timeout_seconds: float = 5.0,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> ScanWirelessSensorsResult:
        """Scan for nearby wireless Bluetooth PASCO sensors.

        Args:
            handle: Capstone main window handle (0 for active window).
            timeout_seconds: Duration in seconds to scan for advertising devices.
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Leave hardware setup drawer open after scan.

        Returns:
            ScanWirelessSensorsResult with discovered sensor IDs and names.
        """
        return ScanWirelessSensorsResult.model_validate(
            await native(
                NativeRequest(
                    operation="scan_wireless_sensors",
                    handle=handle,
                    timeout_seconds=timeout_seconds,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_connect_wireless_sensor(
        sensor_id: str,
        handle: int = 0,
        *,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> ConnectWirelessSensorResult:
        """Pair and connect a discovered wireless sensor by sensor_id.

        Args:
            sensor_id: Discovered sensor hardware ID or Bluetooth name.
            handle: Capstone main window handle (0 for active window).
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Leave hardware setup drawer open after pairing.

        Returns:
            ConnectWirelessSensorResult with connection status and battery level.
        """
        return ConnectWirelessSensorResult.model_validate(
            await native(
                NativeRequest(
                    operation="connect_wireless_sensor",
                    handle=handle,
                    sensor_id=sensor_id,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
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

        Args:
            sensor_name: Target sensor to calibrate (e.g. 'Force Sensor', 'pH Sensor').
            handle: Capstone main window handle (0 for active window).
            measurement_type: Measurement to calibrate (e.g. 'Force', 'pH').
            calibration_type: Calibration wizard type ('one_point' or 'two_point').
            standard_1: First reference standard physical value.
            standard_2: Second reference standard physical value (required for two_point).
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Leave calibration dialog/drawer open.

        Returns:
            CalibrateSensorResult with calibration status, slope, and offset.
        """
        return CalibrateSensorResult.model_validate(
            await native(
                NativeRequest(
                    operation="calibrate_sensor",
                    handle=handle,
                    sensor_name=sensor_name,
                    measurement_type=measurement_type,
                    calibration_type=calibration_type,
                    standard_1=standard_1,
                    standard_2=standard_2,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    return {
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

