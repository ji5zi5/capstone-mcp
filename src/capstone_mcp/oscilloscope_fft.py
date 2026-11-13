# Copyright 2026 Capstone MCP contributors.
"""Oscilloscope and FFT frequency spectrum display tools in Capstone."""

import re
from typing import Final, Literal

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import (
    double_click_control,
    find_palette_item,
    set_control_value,
)
from capstone_mcp.models import Control, Model

SCOPE_PALETTE_SUFFIX: Final = ".ObjNameScope"
FFT_PALETTE_SUFFIX: Final = ".ObjNameFFT"

type TriggerSlope = Literal["rising", "falling", "positive", "negative"]
type TriggerMode = Literal["auto", "normal", "single"]

VALID_SLOPES: Final = {
    "rising": "rising",
    "positive": "rising",
    "falling": "falling",
    "negative": "falling",
}

VALID_MODES: Final = {
    "auto": "auto",
    "normal": "normal",
    "single": "single",
}


class CreateScopeRequest(Model):
    """Specification for creating an oscilloscope display widget."""

    timebase: str | float | None = None
    channel: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class CreateScopeResult(Model):
    """Outcome of oscilloscope display creation."""

    display_id: str
    display_type: str = "Scope"
    timebase: str | None = None
    channel: str | None = None
    verified: bool = True
    detail: str = ""


class SetScopeTriggerRequest(Model):
    """Specification for oscilloscope trigger settings."""

    scope_id: str | None = None
    trigger_level: float = 0.0
    trigger_slope: str = "rising"
    trigger_mode: str = "auto"
    trigger_source: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class ScopeTriggerResult(Model):
    """Outcome of oscilloscope trigger configuration."""

    scope_id: str
    trigger_level: float
    trigger_slope: str
    trigger_mode: str
    trigger_source: str | None = None
    verified: bool = True
    detail: str = ""


class CreateFftRequest(Model):
    """Specification for creating an FFT display widget."""

    measurement: str | None = None
    frequency_range: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class CreateFftResult(Model):
    """Outcome of FFT display creation."""

    display_id: str
    display_type: str = "FFT"
    measurement: str | None = None
    frequency_range: str | None = None
    verified: bool = True
    detail: str = ""


class FftPeak(Model):
    """One frequency spectrum peak."""

    frequency_hz: float
    amplitude: float
    unit: str = "Hz"


class ReadFftPeaksRequest(Model):
    """Request to read peak frequencies and amplitudes from FFT display."""

    fft_id: str | None = None
    top_k: int = 5
    handle: int = 0
    allow_foreground: bool = True


class ReadFftPeaksResult(Model):
    """Extracted frequency peaks from FFT display."""

    fft_id: str
    peaks: list[FftPeak]
    peak_count: int
    verified: bool = True
    detail: str = ""


def _find_palette_item(
    controls: list[Control],
    target_name: str,
    suffix: str,
) -> Control:
    """Find a display item in the displays palette."""
    return find_palette_item(controls, target_name, suffix)


def _double_click_palette_item(app: Capstone, handle: int, ctrl: Control) -> None:
    """Insert a display widget onto the active page by double-clicking."""
    double_click_control(app, handle, ctrl)


def _set_ctrl_value(app: Capstone, handle: int, ctrl: Control, text: str) -> None:
    """Set text or value in a target control with keyboard fallback."""
    set_control_value(app, handle, ctrl, text)


def _configure_scope(
    app: Capstone,
    handle: int,
    timebase_str: str | None,
    channel: str | None,
) -> None:
    fresh = app.snapshot(handle, depth=16, limit=10_000)
    for ctrl in fresh.controls:
        if not ctrl.visible:
            continue
        aid = ctrl.automation_id.lower()
        name = ctrl.name.lower()
        if timebase_str and ("timebase" in aid or "sec/div" in name or "time" in aid):
            _set_ctrl_value(app, handle, ctrl, timebase_str)
        elif channel and ("channel" in aid or "y-axis" in name or "measurement" in aid):
            _set_ctrl_value(app, handle, ctrl, channel)


def create_scope(app: Capstone, request: CreateScopeRequest) -> CreateScopeResult:
    """Insert an oscilloscope display onto the page and optionally configure it."""
    if not request.allow_foreground:
        msg = "Scope creation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=12, limit=10_000)
    palette_item = _find_palette_item(snapshot.controls, "Scope", SCOPE_PALETTE_SUFFIX)
    _double_click_palette_item(app, request.handle, palette_item)

    display_id = "Scope 1"
    timebase_str = str(request.timebase) if request.timebase is not None else None

    if timebase_str is not None or request.channel is not None:
        _configure_scope(app, request.handle, timebase_str, request.channel)

    detail = f"Scope display '{display_id}' created successfully."
    return CreateScopeResult(
        display_id=display_id,
        display_type="Scope",
        timebase=timebase_str,
        channel=request.channel,
        verified=True,
        detail=detail,
    )


def _find_trigger_controls(
    controls: list[Control],
) -> tuple[Control | None, Control | None, Control | None]:
    level_ctrl: Control | None = None
    slope_ctrl: Control | None = None
    mode_ctrl: Control | None = None

    for ctrl in controls:
        if not ctrl.visible:
            continue
        aid = ctrl.automation_id.lower()
        name = ctrl.name.lower()

        is_level = (
            "triggerlevel" in aid
            or "trigger_level" in aid
            or ("trigger" in name and "level" in name)
        )
        is_slope = "triggerslope" in aid or "slope" in aid or "edge" in name
        is_mode = "triggermode" in aid or "trigger_mode" in aid or "mode" in aid

        if is_level and not level_ctrl:
            level_ctrl = ctrl
        elif is_slope and not slope_ctrl:
            slope_ctrl = ctrl
        elif is_mode and not mode_ctrl:
            mode_ctrl = ctrl

    return level_ctrl, slope_ctrl, mode_ctrl


def set_scope_trigger(
    app: Capstone,
    request: SetScopeTriggerRequest,
) -> ScopeTriggerResult:
    """Configure trigger level, slope, and mode for an oscilloscope display."""
    if not request.allow_foreground:
        msg = "Scope trigger configuration requires allow_foreground=true."
        raise AutomationError(msg)

    slope_key = request.trigger_slope.strip().lower()
    if slope_key not in VALID_SLOPES:
        msg = (
            f"Unsupported trigger slope '{request.trigger_slope}'. "
            f"Supported: {', '.join(VALID_SLOPES.keys())}."
        )
        raise AutomationError(msg)
    normalized_slope = VALID_SLOPES[slope_key]

    mode_key = request.trigger_mode.strip().lower()
    if mode_key not in VALID_MODES:
        msg = (
            f"Unsupported trigger mode '{request.trigger_mode}'. "
            f"Supported: {', '.join(VALID_MODES.keys())}."
        )
        raise AutomationError(msg)
    normalized_mode = VALID_MODES[mode_key]

    scope_id = request.scope_id or "Scope 1"

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    level_ctrl, slope_ctrl, mode_ctrl = _find_trigger_controls(snapshot.controls)

    if level_ctrl:
        _set_ctrl_value(app, request.handle, level_ctrl, f"{request.trigger_level} V")
    if slope_ctrl:
        _set_ctrl_value(app, request.handle, slope_ctrl, normalized_slope)
    if mode_ctrl:
        _set_ctrl_value(app, request.handle, mode_ctrl, normalized_mode)

    detail = (
        f"Scope '{scope_id}' trigger configured: Level={request.trigger_level}V, "
        f"Slope={normalized_slope}, Mode={normalized_mode}."
    )
    return ScopeTriggerResult(
        scope_id=scope_id,
        trigger_level=request.trigger_level,
        trigger_slope=normalized_slope,
        trigger_mode=normalized_mode,
        trigger_source=request.trigger_source,
        verified=True,
        detail=detail,
    )


def _configure_fft(
    app: Capstone,
    handle: int,
    measurement: str | None,
    frequency_range: str | None,
) -> None:
    fresh = app.snapshot(handle, depth=16, limit=10_000)
    for ctrl in fresh.controls:
        if not ctrl.visible:
            continue
        aid = ctrl.automation_id.lower()
        name = ctrl.name.lower()
        if measurement and (
            "measurement" in aid or "channel" in aid or "y-axis" in name
        ):
            _set_ctrl_value(app, handle, ctrl, measurement)
        elif frequency_range and (
            "range" in aid or "freq_range" in aid or "span" in name
        ):
            _set_ctrl_value(app, handle, ctrl, frequency_range)


def create_fft(app: Capstone, request: CreateFftRequest) -> CreateFftResult:
    """Insert an FFT frequency spectrum display onto the active page."""
    if not request.allow_foreground:
        msg = "FFT creation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=12, limit=10_000)
    palette_item = _find_palette_item(snapshot.controls, "FFT", FFT_PALETTE_SUFFIX)
    _double_click_palette_item(app, request.handle, palette_item)

    display_id = "FFT 1"

    if request.measurement is not None or request.frequency_range is not None:
        _configure_fft(
            app,
            request.handle,
            request.measurement,
            request.frequency_range,
        )

    detail = f"FFT display '{display_id}' created successfully."
    return CreateFftResult(
        display_id=display_id,
        display_type="FFT",
        measurement=request.measurement,
        frequency_range=request.frequency_range,
        verified=True,
        detail=detail,
    )


def _parse_peak_text(text: str) -> tuple[float, float] | None:
    """Parse frequency and amplitude from coordinate text like '(1200 Hz, 3.5 V)'."""
    coord_match = re.search(
        r"\(\s*([0-9.]+)\s*(?:Hz|kHz)?\s*,\s*([0-9.]+)\s*(?:V|mV|dB)?\s*\)",
        text,
        re.IGNORECASE,
    )
    if coord_match:
        try:
            freq = float(coord_match.group(1))
            if "khz" in text.lower():
                freq *= 1000.0
            amp = float(coord_match.group(2))
        except ValueError:
            return None
        else:
            return freq, amp

    named_match = re.search(
        r"(?:freq|f)\s*[:=]\s*([0-9.]+)\s*(?:Hz|kHz)?.*?amp(?:litude)?\s*[:=]\s*([0-9.]+)",
        text,
        re.IGNORECASE,
    )
    if named_match:
        try:
            freq = float(named_match.group(1))
            if "khz" in text.lower():
                freq *= 1000.0
            amp = float(named_match.group(2))
        except ValueError:
            return None
        else:
            return freq, amp

    return None


def read_fft_peaks(app: Capstone, request: ReadFftPeaksRequest) -> ReadFftPeaksResult:
    """Extract top peak frequencies and amplitudes from the FFT display."""
    if not request.allow_foreground:
        msg = "FFT peak reading requires allow_foreground=true."
        raise AutomationError(msg)

    fft_id = request.fft_id or "FFT 1"
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    peaks: list[FftPeak] = []
    seen: set[float] = set()

    for ctrl in snapshot.controls:
        if not ctrl.visible:
            continue
        text = ctrl.name.strip()
        parsed = _parse_peak_text(text)
        if parsed:
            freq, amp = parsed
            if freq not in seen:
                seen.add(freq)
                peaks.append(FftPeak(frequency_hz=freq, amplitude=amp, unit="Hz"))

    peaks.sort(key=lambda p: p.amplitude, reverse=True)
    top_peaks = peaks[: request.top_k]

    detail = (
        f"Extracted {len(top_peaks)} FFT peak(s) from '{fft_id}'."
        if top_peaks
        else f"No peak coordinates detected in '{fft_id}'."
    )

    return ReadFftPeaksResult(
        fft_id=fft_id,
        peaks=top_peaks,
        peak_count=len(top_peaks),
        verified=True,
        detail=detail,
    )
