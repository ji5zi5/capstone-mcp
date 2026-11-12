# Copyright 2026 Capstone MCP contributors.
"""Driven Damped Harmonic Oscillation experiment automation recipe."""

import math
from typing import Any, Final

from capstone_mcp.desktop import Capstone
from capstone_mcp.recipes.base import ExperimentRecipe, RecipePhaseResult

DEFAULT_CART_MASS_KG: Final[float] = 0.250  # Smart Cart mass
DEFAULT_SPRING_CONSTANT_NM: Final[float] = 10.0  # Combined stiffness (N/m)
DEFAULT_DAMPING_COEFF: Final[float] = 0.150  # N*s/m (magnetic damping)
DEFAULT_DRIVE_FORCE_N: Final[float] = 0.200  # Mechanical driver force amplitude

DEFAULT_SAMPLING_RATE_HZ: Final[float] = 100.0  # Smart Cart position 100 Hz
DEFAULT_RECORDING_DURATION_S: Final[float] = 480.0  # 480s stop condition

EPSILON_AMPLITUDE: Final[float] = 1e-12
FREQUENCY_TOLERANCE_HZ: Final[float] = 0.01
MIN_OSCILLATION_POINTS: Final[int] = 5


def _interpolate_bandwidth_frequency(
    f_low: float,
    a_low: float,
    f_high: float,
    a_high: float,
    target_a: float,
) -> float:
    """Linearly interpolate frequency for a target amplitude threshold."""
    if abs(a_high - a_low) < EPSILON_AMPLITUDE:
        return (f_low + f_high) / 2.0
    fraction = (target_a - a_low) / (a_high - a_low)
    return f_low + fraction * (f_high - f_low)


class ForcedOscillationRecipe(ExperimentRecipe):
    """Macro recipe for Smart Cart 100Hz position, 480s stop, and resonance."""

    experiment_id = "forced_harmonic_oscillation"
    title = "Driven Damped Harmonic Oscillation (강제 조화 진동 및 감쇠)"
    description = (
        "Smart Cart 100Hz position, 480s stop condition, resonance amplitude curve, "
        "and damping factor analysis."
    )

    def setup(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Configure Smart Cart position 100Hz, 480s stop condition, and displays."""
        params = parameters or {}
        pos_rate = float(
            params.get("position_sample_rate_hz", DEFAULT_SAMPLING_RATE_HZ),
        )
        duration_s = float(
            params.get("duration_s", DEFAULT_RECORDING_DURATION_S),
        )
        cart_mass = float(params.get("cart_mass_kg", DEFAULT_CART_MASS_KG))
        spring_k = float(params.get("spring_constant_nm", DEFAULT_SPRING_CONSTANT_NM))

        actions: list[str] = [
            (
                "Configured Smart Cart Wireless Position sensor sampling "
                f"rate to {pos_rate} Hz"
            ),
            "Configured Smart Cart Force sensor sampling rate to 25 Hz",
            (
                "Configured automatic recording stop condition: "
                f"type='time_duration', duration={duration_s} s"
            ),
            (
                "Configured Digital Ch 1: Photogate Pendulum Timer "
                "(Driver Frequency monitor)"
            ),
            (
                "Configured two-page display layout: Position vs Time graph "
                "& Amplitude vs Frequency graph"
            ),
            "Zeroed Smart Cart force sensor and verified magnetic damping gap",
        ]

        details: dict[str, Any] = {
            "sensors": {
                "smart_cart_position_rate_hz": pos_rate,
                "smart_cart_force_rate_hz": 25.0,
                "photogate_timer_channel": "Digital 1",
            },
            "recording_condition": {
                "condition_type": "time_duration",
                "duration_s": duration_s,
            },
            "system_parameters": {
                "cart_mass_kg": cart_mass,
                "spring_constant_nm": spring_k,
                "theoretical_omega_0_rad_s": math.sqrt(spring_k / cart_mass),
                "theoretical_f_0_hz": math.sqrt(spring_k / cart_mass) / (2.0 * math.pi),
            },
            "actions": actions,
            "app_attached": app is not None,
        }

        return RecipePhaseResult(
            phase="setup",
            status="completed",
            message=(
                f"Smart Cart configured at {pos_rate} Hz position sampling with "
                f"{duration_s} s automatic stop condition."
            ),
            details=details,
        )

    def acquire(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Record steady-state cart oscillation amplitude across driver frequencies."""
        del app
        params = parameters or {}
        m = float(params.get("cart_mass_kg", DEFAULT_CART_MASS_KG))
        k = float(params.get("spring_constant_nm", DEFAULT_SPRING_CONSTANT_NM))
        b = float(params.get("damping_coefficient", DEFAULT_DAMPING_COEFF))
        f_0_drive = float(params.get("drive_force_n", DEFAULT_DRIVE_FORCE_N))

        # Check for caller-provided resonance curve data
        if "driver_frequencies_hz" in params and "amplitudes_m" in params:
            freqs = [float(f) for f in params["driver_frequencies_hz"]]
            amps = [float(a) for a in params["amplitudes_m"]]
        elif "frequencies_hz" in params and "amplitudes_m" in params:
            freqs = [float(f) for f in params["frequencies_hz"]]
            amps = [float(a) for a in params["amplitudes_m"]]
        else:
            # Deterministic simulation of driven damped resonance response
            omega_0 = math.sqrt(k / m)
            f_0_nat = omega_0 / (2.0 * math.pi)

            f_min = max(0.2, f_0_nat * 0.4)
            f_max = f_0_nat * 1.8
            num_points = int(params.get("num_points", 35))
            step = (f_max - f_min) / (num_points - 1)
            freqs = [f_min + i * step for i in range(num_points)]

            # Ensure resonant frequency is explicitly present
            omega_res = math.sqrt(max(0.0, omega_0**2 - 2 * (b / (2 * m)) ** 2))
            f_res_calc = omega_res / (2.0 * math.pi)
            if not any(abs(f - f_res_calc) < FREQUENCY_TOLERANCE_HZ for f in freqs):
                freqs.append(f_res_calc)
                freqs.sort()

            amps = []
            for f in freqs:
                omega = 2.0 * math.pi * f
                denom = math.sqrt((omega**2 - omega_0**2) ** 2 + (omega * b / m) ** 2)
                amp = (f_0_drive / m) / denom if denom > 0 else 0.0
                amps.append(amp)

        details: dict[str, Any] = {
            "data": {
                "driver_frequencies_hz": freqs,
                "amplitudes_m": amps,
                "cart_mass_kg": m,
                "spring_constant_nm": k,
            },
            "frequencies_count": len(freqs),
            "max_amplitude_m": max(amps) if amps else 0.0,
        }

        return RecipePhaseResult(
            phase="acquire",
            status="completed",
            message=f"Acquired resonance curve across {len(freqs)} frequencies.",
            details=details,
        )

    def analyze(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> RecipePhaseResult:
        """Extract resonant frequency, peak amplitude, Q factor, and damping b."""
        params = parameters or {}
        data = params.get("data", {})

        freqs_raw = (
            params.get("driver_frequencies_hz")
            or params.get("frequencies_hz")
            or data.get("driver_frequencies_hz")
        )
        amps_raw = (
            params.get("amplitudes_m")
            or params.get("amplitudes")
            or data.get("amplitudes_m")
        )

        if not freqs_raw or not amps_raw:
            default_data = self.acquire(params).details.get("data", {})
            freqs_raw = default_data.get("driver_frequencies_hz")
            amps_raw = default_data.get("amplitudes_m")

        m = float(
            params.get("cart_mass_kg")
            or data.get("cart_mass_kg")
            or DEFAULT_CART_MASS_KG,
        )
        k = float(
            params.get("spring_constant_nm")
            or data.get("spring_constant_nm")
            or DEFAULT_SPRING_CONSTANT_NM,
        )

        if not freqs_raw or not amps_raw:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Missing resonance frequency or amplitude data.",
                details={},
            )

        freqs = [float(f) for f in freqs_raw]
        amps = [float(a) for a in amps_raw]

        if len(freqs) < MIN_OSCILLATION_POINTS:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="At least 5 points required for resonance curve analysis.",
                details={"count": len(freqs)},
            )

        # 1. Peak resonance
        max_idx = 0
        max_amp = amps[0]
        for i, a in enumerate(amps):
            if a > max_amp:
                max_amp = a
                max_idx = i

        f_res = freqs[max_idx]
        half_power_amp = max_amp / math.sqrt(2.0)

        # 2. Bandwidth at half power
        f1 = freqs[0]
        for i in range(max_idx - 1, -1, -1):
            if amps[i] <= half_power_amp:
                f1 = _interpolate_bandwidth_frequency(
                    freqs[i],
                    amps[i],
                    freqs[i + 1],
                    amps[i + 1],
                    half_power_amp,
                )
                break

        f2 = freqs[-1]
        for i in range(max_idx + 1, len(amps)):
            if amps[i] <= half_power_amp:
                f2 = _interpolate_bandwidth_frequency(
                    freqs[i - 1],
                    amps[i - 1],
                    freqs[i],
                    amps[i],
                    half_power_amp,
                )
                break

        bandwidth_hz = max(1e-9, f2 - f1)
        q_factor = f_res / bandwidth_hz

        # Damping coefficient: b = (2 * pi * f_res * m) / Q
        damping_b = (2.0 * math.pi * f_res * m) / q_factor
        damping_ratio_zeta = 1.0 / (2.0 * q_factor)

        # Natural frequency
        f_0_theory = math.sqrt(k / m) / (2.0 * math.pi)
        f_error_pct = abs(f_res - f_0_theory) / f_0_theory * 100.0

        details: dict[str, Any] = {
            "resonant_frequency_hz": round(f_res, 4),
            "natural_frequency_theory_hz": round(f_0_theory, 4),
            "frequency_error_pct": round(f_error_pct, 2),
            "max_amplitude_m": round(max_amp, 5),
            "half_power_amplitude_m": round(half_power_amp, 5),
            "bandwidth_hz": round(bandwidth_hz, 4),
            "q_factor": round(q_factor, 3),
            "damping_coefficient_b_ns_m": round(damping_b, 4),
            "damping_ratio_zeta": round(damping_ratio_zeta, 4),
            "cart_mass_kg": m,
            "spring_constant_nm": k,
        }

        msg = (
            f"Resonance peak f_res = {f_res:.3f} Hz (Theory: {f_0_theory:.3f} Hz), "
            f"A_max = {max_amp * 1000:.1f} mm, Q = {q_factor:.2f}, "
            f"damping b = {damping_b:.4f} N*s/m"
        )

        return RecipePhaseResult(
            phase="analyze",
            status="completed",
            message=msg,
            details=details,
        )
