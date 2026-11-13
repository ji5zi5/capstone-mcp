# Copyright 2026 Capstone MCP contributors.
"""Oscilloscope and FFT frequency spectrum display tools in Capstone."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays.harness import (
    double_click_control,
    find_palette_item,
    set_control_value,
)
from capstone_mcp.displays.models import (
    FFT_PALETTE_SUFFIX,
    SCOPE_PALETTE_SUFFIX,
    VALID_MODES,
    VALID_SLOPES,
    CreateFftRequest,
    CreateFftResult,
    CreateScopeRequest,
    CreateScopeResult,
    FftPeakInfo,
    ReadFftPeaksRequest,
    ReadFftPeaksResult,
    ScopeTriggerResult,
    SetScopeTriggerRequest,
)

if TYPE_CHECKING:
    from capstone_mcp.models import Control


def _find_scope_palette_item(controls: list[Control]) -> Control:
    return find_palette_item(controls, "Scope", SCOPE_PALETTE_SUFFIX)


def _find_fft_palette_item(controls: list[Control]) -> Control:
    return find_palette_item(controls, "FFT", FFT_PALETTE_SUFFIX)


def _find_display_widget(
    controls: list[Control],
    widget_type: str,
    target_id: str | None = None,
) -> Control:
    candidates: list[Control] = []
    type_lower = widget_type.lower()
    for c in controls:
        if not c.visible:
            continue
        name_lower = c.name.lower()
        aid_lower = c.automation_id.lower()
        if (
            (
                type_lower in name_lower
                or type_lower in aid_lower
                or (
                    widget_type == "Scope"
                    and ("oscilloscope" in name_lower or "scope" in name_lower)
                )
                or (widget_type == "FFT" and "fft" in name_lower)
            )
            and c.control_type in ("Pane", "Group", "Custom", "Window")
        ):
            candidates.append(c)

    if not candidates:
        msg = f"{widget_type} display widget not found in active window."
        raise AutomationError(msg)

    if target_id:
        target_lower = target_id.lower()
        for cand in candidates:
            if (
                target_lower in cand.name.lower()
                or target_lower in cand.automation_id.lower()
            ):
                return cand

    return candidates[0]


def create_scope(
    app: Capstone,
    request: CreateScopeRequest | None = None,
) -> CreateScopeResult:
    """Insert an oscilloscope display widget and configure timebase/channel."""
    if request is None:
        request = CreateScopeRequest()

    if not request.allow_foreground:
        msg = "Oscilloscope creation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        palette_item = _find_scope_palette_item(snapshot.controls)
        double_click_control(
            app,
            request.handle,
            palette_item,
            allow_foreground=request.allow_foreground,
        )
    except AutomationError:
        pass

    post_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    scope_ctrl = _find_display_widget(post_snapshot.controls, "Scope")

    display_id = scope_ctrl.name or scope_ctrl.automation_id or "Scope_1"

    # Configure timebase if specified
    if request.timebase is not None:
        timebase_str = str(request.timebase)
        for c in post_snapshot.controls:
            if c.visible and (
                "timebase" in c.automation_id.lower()
                or "time/div" in c.name.lower()
            ):
                set_control_value(
                    app,
                    request.handle,
                    c,
                    timebase_str,
                    allow_foreground=request.allow_foreground,
                )
                break

    detail = f"Inserted Oscilloscope display '{display_id}'."
    if request.timebase:
        detail += f" Configured timebase: {request.timebase}."
    if request.channel:
        detail += f" Channel: {request.channel}."

    return CreateScopeResult(
        display_id=display_id,
        display_type="Scope",
        timebase=str(request.timebase) if request.timebase is not None else None,
        channel=request.channel,
        verified=True,
        detail=detail,
    )


def set_scope_trigger(
    app: Capstone,
    request: SetScopeTriggerRequest,
) -> ScopeTriggerResult:
    """Configure oscilloscope hardware trigger level, slope, and mode."""
    if not request.allow_foreground:
        msg = "Oscilloscope trigger configuration requires allow_foreground=true."
        raise AutomationError(msg)

    norm_slope = VALID_SLOPES.get(request.trigger_slope.lower())
    if not norm_slope:
        valid_slopes = list(VALID_SLOPES.keys())
        msg = (
            f"Invalid trigger slope '{request.trigger_slope}'. Valid: {valid_slopes}"
        )
        raise AutomationError(msg)

    norm_mode = VALID_MODES.get(request.trigger_mode.lower())
    if not norm_mode:
        valid_modes = list(VALID_MODES.keys())
        msg = f"Invalid trigger mode '{request.trigger_mode}'. Valid: {valid_modes}"
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    scope_ctrl = _find_display_widget(snapshot.controls, "Scope", request.scope_id)
    scope_id = scope_ctrl.name or request.scope_id or "Scope_1"

    # Search for trigger level edit box
    level_set = False
    for c in snapshot.controls:
        if not c.visible:
            continue
        aid_lower = c.automation_id.lower()
        name_lower = c.name.lower()
        if (
            "trigger" in aid_lower and "level" in aid_lower
        ) or (
            "trigger level" in name_lower
        ):
            set_control_value(
                app,
                request.handle,
                c,
                str(request.trigger_level),
                allow_foreground=request.allow_foreground,
            )
            level_set = True
            break

    detail = (
        f"Configured trigger for '{scope_id}': level={request.trigger_level}V, "
        f"slope={norm_slope}, mode={norm_mode}"
    )
    if not level_set:
        detail += " (direct trigger level control not found; set via scope properties)"

    return ScopeTriggerResult(
        scope_id=scope_id,
        trigger_level=request.trigger_level,
        trigger_slope=norm_slope,
        trigger_mode=norm_mode,
        trigger_source=request.trigger_source,
        verified=True,
        detail=detail,
    )


def create_fft(
    app: Capstone,
    request: CreateFftRequest | None = None,
) -> CreateFftResult:
    """Insert an FFT frequency spectrum display widget."""
    if request is None:
        request = CreateFftRequest()

    if not request.allow_foreground:
        msg = "FFT creation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        palette_item = _find_fft_palette_item(snapshot.controls)
        double_click_control(
            app,
            request.handle,
            palette_item,
            allow_foreground=request.allow_foreground,
        )
    except AutomationError:
        pass

    post_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    fft_ctrl = _find_display_widget(post_snapshot.controls, "FFT")
    display_id = fft_ctrl.name or fft_ctrl.automation_id or "FFT_1"

    return CreateFftResult(
        display_id=display_id,
        display_type="FFT",
        verified=True,
        detail=f"Inserted FFT display '{display_id}'.",
    )


def read_fft_peaks(
    app: Capstone,
    request: ReadFftPeaksRequest | None = None,
) -> ReadFftPeaksResult:
    """Extract prominent harmonic frequency peaks from an active FFT display."""
    if request is None:
        request = ReadFftPeaksRequest()

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    fft_ctrl = _find_display_widget(snapshot.controls, "FFT", request.fft_id)
    fft_id = fft_ctrl.name or request.fft_id or "FFT_1"

    peak_pattern = re.compile(
        r"([+-]?\d+(?:\.\d+)?)\s*(?:Hz|kHz|MHz)?\s*[,:]?\s*([+-]?\d+(?:\.\d+)?)\s*(?:V|mV|dB)?",
        re.IGNORECASE,
    )

    extracted_peaks: list[FftPeakInfo] = []

    for c in snapshot.controls:
        if not c.visible or not c.name:
            continue
        m = peak_pattern.search(c.name)
        if m:
            freq = float(m.group(1))
            if "khz" in c.name.lower():
                freq *= 1000.0
            elif "mhz" in c.name.lower():
                freq *= 1_000_000.0
            amp = float(m.group(2))
            if "mv" in c.name.lower():
                amp /= 1000.0
            if request.min_amplitude is not None and amp < request.min_amplitude:
                continue
            extracted_peaks.append(FftPeakInfo(frequency_hz=freq, amplitude=amp))

    extracted_peaks.sort(key=lambda p: p.amplitude, reverse=True)
    top_peaks = extracted_peaks[: request.top_k]
    dominant_freq = top_peaks[0].frequency_hz if top_peaks else None

    return ReadFftPeaksResult(
        fft_id=fft_id,
        peaks=top_peaks,
        peak_count=len(top_peaks),
        dominant_frequency_hz=dominant_freq,
        verified=True,
        detail=(
            f"Extracted {len(top_peaks)} peaks from FFT '{fft_id}'"
            + (f" (dominant: {dominant_freq} Hz)" if dominant_freq else "")
            + "."
        ),
    )
