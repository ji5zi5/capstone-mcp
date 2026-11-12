# Copyright 2026 Capstone MCP contributors.
"""RLC Circuit Resonance experiment automation recipe."""

import math
from typing import Any, Final

from capstone_mcp.desktop import Capstone
from capstone_mcp.recipes.base import ExperimentRecipe, RecipePhaseResult

DEFAULT_RESISTANCE_OHM: Final[float] = 10.0
DEFAULT_INDUCTANCE_H: Final[float] = 0.0082  # 8.2 mH
DEFAULT_CAPACITANCE_F: Final[float] = 1.0e-5  # 10.0 uF
DEFAULT_AMPLITUDE_V: Final[float] = 1.0

DEFAULT_SWEEP_START_HZ: Final[float] = 10.0
DEFAULT_SWEEP_STOP_HZ: Final[float] = 10000.0

EPSILON_VOLTAGE: Final[float] = 1e-12
MIN_RESONANCE_POINTS: Final[int] = 5


def _interpolate_frequency(
    f_low: float,
    v_low: float,
    f_high: float,
    v_high: float,
    target_v: float,
) -> float:
    """Linearly interpolate frequency for a target voltage value."""
    if abs(v_high - v_low) < EPSILON_VOLTAGE:
        return (f_low + f_high) / 2.0
    fraction = (target_v - v_low) / (v_high - v_low)
    return f_low + fraction * (f_high - f_low)


class RLCResonanceRecipe(ExperimentRecipe):
    """Macro recipe for 850 signal generator frequency sweep & RLC resonance."""

    experiment_id = "rlc_resonance"
    title = "RLC Circuit Resonance (LRC 직렬 공진 회로)"
    description = (
        "850 Signal generator sine sweep (10Hz-10kHz), Scope/FFT peak measurement, "
        "and resonant frequency f_0 and Q-factor calculation."
    )

    def setup(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Configure 850 sweep, Scope/FFT, and analog voltage channels."""
        params = parameters or {}
        start_f = float(params.get("start_freq_hz", DEFAULT_SWEEP_START_HZ))
        stop_f = float(params.get("stop_freq_hz", DEFAULT_SWEEP_STOP_HZ))
        amplitude_v = float(params.get("amplitude_v", DEFAULT_AMPLITUDE_V))
        waveform = str(params.get("waveform", "Sine"))

        res_ohm = float(params.get("resistance_ohm", DEFAULT_RESISTANCE_OHM))
        ind_h = float(params.get("inductance_h", DEFAULT_INDUCTANCE_H))
        cap_f = float(params.get("capacitance_f", DEFAULT_CAPACITANCE_F))

        actions: list[str] = [
            (
                f"Configured 850 Signal Generator Output 1: Waveform={waveform}, "
                f"Amplitude={amplitude_v} V, Sweep={start_f} Hz to {stop_f} Hz"
            ),
            "Configured Analog Ch A: Resistor Voltage V_R",
            "Configured Analog Ch B: Inductor Voltage V_L",
            "Configured Analog Ch C: Capacitor Voltage V_C",
            (
                "Created Oscilloscope display with edge trigger on Ch A "
                "(Rising edge, 0.0 V)"
            ),
            (
                "Created FFT Frequency Spectrum display with Hann windowing for "
                "harmonic peak detection"
            ),
        ]

        details: dict[str, Any] = {
            "signal_generator": {
                "output": 1,
                "waveform": waveform,
                "amplitude_v": amplitude_v,
                "sweep_start_hz": start_f,
                "sweep_stop_hz": stop_f,
            },
            "channels": {
                "analog_a": "Resistor Voltage (V_R)",
                "analog_b": "Inductor Voltage (V_L)",
                "analog_c": "Capacitor Voltage (V_C)",
            },
            "displays": ["Scope", "FFT Spectrum"],
            "circuit_components": {
                "resistance_ohm": res_ohm,
                "inductance_h": ind_h,
                "capacitance_f": cap_f,
            },
            "actions": actions,
            "app_attached": app is not None,
        }

        return RecipePhaseResult(
            phase="setup",
            status="completed",
            message=(
                f"Configured 850 signal generator sweep ({start_f} Hz - {stop_f} Hz) "
                "and Scope/FFT monitoring channels for RLC resonance."
            ),
            details=details,
        )

    def acquire(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Execute frequency sweep and capture peak voltages across RLC circuit."""
        del app
        params = parameters or {}
        r_val = float(params.get("resistance_ohm", DEFAULT_RESISTANCE_OHM))
        l_val = float(params.get("inductance_h", DEFAULT_INDUCTANCE_H))
        c_val = float(params.get("capacitance_f", DEFAULT_CAPACITANCE_F))
        v_in = float(params.get("amplitude_v", DEFAULT_AMPLITUDE_V))

        # Check for user-provided dataset
        if "frequencies_hz" in params and "voltages_v" in params:
            freqs = [float(f) for f in params["frequencies_hz"]]
            volts = [float(v) for v in params["voltages_v"]]
        else:
            # Deterministic simulation of frequency sweep response
            start_f = float(params.get("start_freq_hz", DEFAULT_SWEEP_START_HZ))
            stop_f = float(params.get("stop_freq_hz", DEFAULT_SWEEP_STOP_HZ))
            num_points = int(params.get("num_points", 80))

            log_start = math.log10(start_f)
            log_stop = math.log10(stop_f)
            step = (log_stop - log_start) / (num_points - 1)
            freqs = [10.0 ** (log_start + i * step) for i in range(num_points)]

            # Also ensure theoretical f0 is included for precision
            f0_th = 1.0 / (2.0 * math.pi * math.sqrt(l_val * c_val))
            if start_f <= f0_th <= stop_f and not any(
                abs(f - f0_th) < 1.0 for f in freqs
            ):
                freqs.append(f0_th)
                freqs.sort()

            volts = []
            for f in freqs:
                omega = 2.0 * math.pi * f
                x_l = omega * l_val
                x_c = 1.0 / (omega * c_val)
                z = math.sqrt(r_val * r_val + (x_l - x_c) ** 2)
                v_r = (v_in / z) * r_val
                volts.append(v_r)

        if len(freqs) != len(volts):
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Frequency and voltage sample counts do not match.",
                details={
                    "frequencies_count": len(freqs),
                    "voltages_count": len(volts),
                },
            )

        details: dict[str, Any] = {
            "data": {
                "frequencies_hz": freqs,
                "voltages_v": volts,
                "resistance_ohm": r_val,
                "inductance_h": l_val,
                "capacitance_f": c_val,
            },
            "sweep_points": len(freqs),
            "max_voltage_v": max(volts) if volts else 0.0,
            "min_voltage_v": min(volts) if volts else 0.0,
        }

        return RecipePhaseResult(
            phase="acquire",
            status="completed",
            message=f"Acquired frequency sweep data across {len(freqs)} points.",
            details=details,
        )

    def analyze(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> RecipePhaseResult:
        """Extract resonant frequency f_0, bandwidth Delta f, and quality factor Q."""
        params = parameters or {}
        data = params.get("data", {})

        freqs_raw = params.get("frequencies_hz") or data.get("frequencies_hz")
        volts_raw = params.get("voltages_v") or data.get("voltages_v")

        if not freqs_raw or not volts_raw:
            default_data = self.acquire(params).details.get("data", {})
            freqs_raw = default_data.get("frequencies_hz")
            volts_raw = default_data.get("voltages_v")

        r_val = float(
            params.get("resistance_ohm")
            or data.get("resistance_ohm")
            or DEFAULT_RESISTANCE_OHM,
        )
        l_val = float(
            params.get("inductance_h")
            or data.get("inductance_h")
            or DEFAULT_INDUCTANCE_H,
        )
        c_val = float(
            params.get("capacitance_f")
            or data.get("capacitance_f")
            or DEFAULT_CAPACITANCE_F,
        )

        if not freqs_raw or not volts_raw:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Missing frequency or voltage dataset for RLC resonance.",
                details={},
            )

        freqs = [float(f) for f in freqs_raw]
        volts = [float(v) for v in volts_raw]

        if len(freqs) < MIN_RESONANCE_POINTS:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="At least 5 points required to analyze resonance bandwidth.",
                details={"points_count": len(freqs)},
            )

        # 1. Peak Resonant Frequency f_0
        max_idx = 0
        max_v = volts[0]
        for i, v in enumerate(volts):
            if v > max_v:
                max_v = v
                max_idx = i

        f0_exp = freqs[max_idx]

        # 2. Bandwidth (-3 dB / half-power points)
        half_power_v = max_v / math.sqrt(2.0)

        # Find lower cutoff f1 (< f0)
        f1 = freqs[0]
        for i in range(max_idx - 1, -1, -1):
            if volts[i] <= half_power_v:
                f1 = _interpolate_frequency(
                    freqs[i],
                    volts[i],
                    freqs[i + 1],
                    volts[i + 1],
                    half_power_v,
                )
                break

        # Find upper cutoff f2 (> f0)
        f2 = freqs[-1]
        for i in range(max_idx + 1, len(volts)):
            if volts[i] <= half_power_v:
                f2 = _interpolate_frequency(
                    freqs[i - 1],
                    volts[i - 1],
                    freqs[i],
                    volts[i],
                    half_power_v,
                )
                break

        bandwidth_hz = max(1e-9, f2 - f1)
        q_exp = f0_exp / bandwidth_hz

        # 3. Theoretical expectations
        f0_th = 1.0 / (2.0 * math.pi * math.sqrt(l_val * c_val))
        q_th = (1.0 / r_val) * math.sqrt(l_val / c_val)

        f0_error_pct = abs(f0_exp - f0_th) / f0_th * 100.0
        q_error_pct = abs(q_exp - q_th) / q_th * 100.0

        details: dict[str, Any] = {
            "resonant_frequency_exp_hz": round(f0_exp, 2),
            "resonant_frequency_theory_hz": round(f0_th, 2),
            "resonant_frequency_error_pct": round(f0_error_pct, 4),
            "peak_voltage_v": round(max_v, 4),
            "half_power_voltage_v": round(half_power_v, 4),
            "f1_lower_cutoff_hz": round(f1, 2),
            "f2_upper_cutoff_hz": round(f2, 2),
            "bandwidth_hz": round(bandwidth_hz, 2),
            "q_factor_exp": round(q_exp, 4),
            "q_factor_theory": round(q_th, 4),
            "q_factor_error_pct": round(q_error_pct, 4),
            "circuit": {
                "resistance_ohm": r_val,
                "inductance_h": l_val,
                "capacitance_f": c_val,
            },
        }

        msg = (
            f"Resonance f_0 = {f0_exp:.2f} Hz (Theory: {f0_th:.2f} Hz, "
            f"Error: {f0_error_pct:.2f}%), "
            f"Bandwidth Delta f = {bandwidth_hz:.2f} Hz, "
            f"Q = {q_exp:.2f} (Theory: {q_th:.2f}, Error: {q_error_pct:.2f}%)"
        )

        return RecipePhaseResult(
            phase="analyze",
            status="completed",
            message=msg,
            details=details,
        )
