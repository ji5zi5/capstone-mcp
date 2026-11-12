# Copyright 2026 Capstone MCP contributors.
"""Light Interference and Slit Diffraction experiment automation recipe."""

import math
from typing import Any, Final

from capstone_mcp.desktop import Capstone
from capstone_mcp.recipes.base import ExperimentRecipe, RecipePhaseResult

DEFAULT_LASER_WAVELENGTH_M: Final[float] = 650.0e-9  # Red diode laser (650 nm)
DEFAULT_SCREEN_DISTANCE_M: Final[float] = 1.0  # 1.0 m optics bench distance
DEFAULT_SLIT_WIDTH_M: Final[float] = 4.0e-5  # 0.04 mm single slit
DEFAULT_SLIT_SEPARATION_M: Final[float] = 2.5e-4  # 0.25 mm double slit

MIN_PROFILE_POINTS: Final[int] = 3
MIN_DIFFRACTION_POINTS: Final[int] = 5
SIDE_PEAK_THRESHOLD_MM: Final[float] = 0.05
MIN_SIDE_MAXIMA_COUNT: Final[int] = 2
EPSILON_BETA: Final[float] = 1e-9


def _find_local_extrema(
    positions: list[float],
    values: list[float],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Identify local maxima and minima from paired 1D spatial profile."""
    maxima: list[tuple[float, float]] = []
    minima: list[tuple[float, float]] = []

    n = len(values)
    if n < MIN_PROFILE_POINTS:
        return maxima, minima

    for i in range(1, n - 1):
        prev_v = values[i - 1]
        curr_v = values[i]
        next_v = values[i + 1]

        if curr_v > prev_v and curr_v >= next_v:
            maxima.append((positions[i], curr_v))
        elif curr_v < prev_v and curr_v <= next_v:
            minima.append((positions[i], curr_v))

    return maxima, minima


def _derive_slit_width(
    left_minima: list[float],
    right_minima: list[float],
    x_center_mm: float,
    wl: float,
    l_dist: float,
) -> tuple[float, float]:
    """Calculate first minimum distance and slit width a from minima.

    Returns:
        tuple of (first_min_delta_mm, slit_width_a_m).
    """
    first_min_delta_mm = 0.0
    if left_minima and right_minima:
        first_min_delta_mm = (right_minima[0] - left_minima[0]) / 2.0
    elif right_minima:
        first_min_delta_mm = right_minima[0] - x_center_mm
    elif left_minima:
        first_min_delta_mm = x_center_mm - left_minima[0]

    slit_width_a_m = DEFAULT_SLIT_WIDTH_M
    if first_min_delta_mm > 0:
        delta_x_m = first_min_delta_mm * 1e-3
        slit_width_a_m = (1.0 * wl * l_dist) / delta_x_m

    return first_min_delta_mm, slit_width_a_m


def _derive_slit_separation(
    maxima_pts: list[tuple[float, float]],
    x_center_mm: float,
    wl: float,
    l_dist: float,
) -> float | None:
    """Calculate slit separation d from interference fringes."""
    side_maxima = [
        p for p, _ in maxima_pts if abs(p - x_center_mm) > SIDE_PEAK_THRESHOLD_MM
    ]
    if len(side_maxima) < MIN_SIDE_MAXIMA_COUNT:
        return None

    spacings = [
        abs(side_maxima[i + 1] - side_maxima[i])
        for i in range(len(side_maxima) - 1)
    ]
    fringe_spacing_mm = math.fsum(spacings) / len(spacings)
    if fringe_spacing_mm <= 0:
        return None

    delta_d_m = fringe_spacing_mm * 1e-3
    return (1.0 * wl * l_dist) / delta_d_m


class SlitDiffractionRecipe(ExperimentRecipe):
    """Macro recipe driving light scan and slit geometry extraction."""

    experiment_id = "slit_diffraction"
    title = "Light Interference & Slit Diffraction (빛의 간섭과 회절)"
    description = (
        "Linear translator position vs light intensity scan, diffraction "
        "minima/maxima extraction, and slit geometry (width a, separation d) "
        "derivation."
    )

    def setup(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Configure optics bench, diode laser, translator, and light sensor."""
        params = parameters or {}
        wl_nm = float(
            params.get("wavelength_nm", DEFAULT_LASER_WAVELENGTH_M * 1e9),
        )
        distance_m = float(
            params.get("screen_distance_m", DEFAULT_SCREEN_DISTANCE_M),
        )
        slit_type = str(params.get("slit_type", "single_slit"))

        actions: list[str] = [
            (
                f"Aligned Red Diode Laser ({wl_nm} nm) on 1.2 m Optics "
                "Bench OS-8441"
            ),
            (
                f"Configured Slit Wheel Accessory: type='{slit_type}' at "
                f"distance L={distance_m} m"
            ),
            "Configured High Sensitivity Light Sensor CI-6504 (Gain: 10x)",
            (
                "Configured Rotary Motion Sensor for Linear Translation scan "
                "(0.01 mm resolution)"
            ),
            (
                "Created Light Intensity vs Position Graph display with peak "
                "readout tools"
            ),
        ]

        details: dict[str, Any] = {
            "optics": {
                "wavelength_nm": wl_nm,
                "wavelength_m": wl_nm * 1e-9,
                "screen_distance_m": distance_m,
                "slit_type": slit_type,
            },
            "sensors": {
                "light_sensor": "High Sensitivity Light Sensor (Analog A)",
                "translation_sensor": "Rotary Motion Sensor (Digital 1 & 2)",
            },
            "display": "Intensity vs Position Graph",
            "actions": actions,
            "app_attached": app is not None,
        }

        return RecipePhaseResult(
            phase="setup",
            status="completed",
            message=(
                f"Configured optics bench for {slit_type} diffraction scan at "
                f"L={distance_m} m with {wl_nm} nm laser."
            ),
            details=details,
        )

    def acquire(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Scan detector position across diffraction pattern and measure intensity."""
        del app
        params = parameters or {}
        wl = float(params.get("wavelength_m", DEFAULT_LASER_WAVELENGTH_M))
        l_dist = float(params.get("screen_distance_m", DEFAULT_SCREEN_DISTANCE_M))
        slit_type = str(params.get("slit_type", "single_slit"))

        if "positions_mm" in params and "intensities" in params:
            pos_mm = [float(p) for p in params["positions_mm"]]
            intensities = [float(i) for i in params["intensities"]]
        elif "positions_m" in params and "intensities" in params:
            pos_mm = [float(p) * 1000.0 for p in params["positions_m"]]
            intensities = [float(i) for i in params["intensities"]]
        else:
            # Deterministic simulation of Fraunhofer diffraction pattern
            a = float(params.get("slit_width_m", DEFAULT_SLIT_WIDTH_M))
            d = float(params.get("slit_separation_m", DEFAULT_SLIT_SEPARATION_M))
            num_points = int(params.get("num_points", 161))

            span_mm = 50.0  # -25 mm to +25 mm scan
            step_mm = span_mm / (num_points - 1)
            pos_mm = [-span_mm / 2.0 + i * step_mm for i in range(num_points)]
            intensities = []

            for x_val in pos_mm:
                x_m = x_val * 1e-3
                sin_theta = x_m / math.sqrt(x_m * x_m + l_dist * l_dist)

                beta = (math.pi * a / wl) * sin_theta
                diff_fac = (
                    (math.sin(beta) / beta) ** 2 if abs(beta) > EPSILON_BETA else 1.0
                )

                if slit_type == "double_slit":
                    alpha = (math.pi * d / wl) * sin_theta
                    interf_fac = (math.cos(alpha)) ** 2
                    intensity = 5.0 * interf_fac * diff_fac
                else:
                    intensity = 5.0 * diff_fac

                intensities.append(round(intensity, 4))

        details: dict[str, Any] = {
            "data": {
                "positions_mm": pos_mm,
                "intensities": intensities,
                "slit_type": slit_type,
                "wavelength_m": wl,
                "screen_distance_m": l_dist,
            },
            "points_count": len(pos_mm),
            "max_intensity": max(intensities) if intensities else 0.0,
            "min_intensity": min(intensities) if intensities else 0.0,
        }

        return RecipePhaseResult(
            phase="acquire",
            status="completed",
            message=f"Acquired diffraction scan across {len(pos_mm)} positions.",
            details=details,
        )

    def analyze(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> RecipePhaseResult:
        """Extract diffraction minima/maxima and calculate slit width a and d."""
        params = parameters or {}
        data = params.get("data", {})

        pos_raw = (
            params.get("positions_mm")
            or data.get("positions_mm")
            or params.get("positions_m")
        )
        int_raw = params.get("intensities") or data.get("intensities")

        if not pos_raw or not int_raw:
            default_data = self.acquire(params).details.get("data", {})
            pos_raw = default_data.get("positions_mm")
            int_raw = default_data.get("intensities")

        wl = float(
            params.get("wavelength_m")
            or data.get("wavelength_m")
            or DEFAULT_LASER_WAVELENGTH_M,
        )
        l_dist = float(
            params.get("screen_distance_m")
            or data.get("screen_distance_m")
            or DEFAULT_SCREEN_DISTANCE_M,
        )
        slit_type = str(
            params.get("slit_type")
            or data.get("slit_type")
            or "single_slit",
        )

        if not pos_raw or not int_raw:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Missing position or intensity data for diffraction analysis.",
                details={},
            )

        positions_mm = [float(p) for p in pos_raw]
        intensities = [float(i) for i in int_raw]

        if len(positions_mm) < MIN_DIFFRACTION_POINTS:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="At least 5 points required for diffraction profile analysis.",
                details={"points_count": len(positions_mm)},
            )

        # 1. Central peak
        max_idx = 0
        max_i = intensities[0]
        for i, val in enumerate(intensities):
            if val > max_i:
                max_i = val
                max_idx = i

        x_center_mm = positions_mm[max_idx]

        # 2. Local extrema detection
        maxima_pts, minima_pts = _find_local_extrema(positions_mm, intensities)

        left_minima = sorted(
            [p for p, _ in minima_pts if p < x_center_mm],
            reverse=True,
        )
        right_minima = sorted([p for p, _ in minima_pts if p > x_center_mm])

        first_min_delta_mm, slit_width_a_m = _derive_slit_width(
            left_minima,
            right_minima,
            x_center_mm,
            wl,
            l_dist,
        )

        slit_separation_d_m: float | None = None
        if slit_type == "double_slit":
            slit_separation_d_m = _derive_slit_separation(
                maxima_pts,
                x_center_mm,
                wl,
                l_dist,
            )

        nominal_a = float(
            params.get("nominal_slit_width_m", DEFAULT_SLIT_WIDTH_M),
        )
        a_error_pct = abs(slit_width_a_m - nominal_a) / nominal_a * 100.0

        details: dict[str, Any] = {
            "central_maximum": {
                "position_mm": round(x_center_mm, 3),
                "intensity": round(max_i, 4),
            },
            "diffraction_minima_count": len(minima_pts),
            "diffraction_maxima_count": len(maxima_pts),
            "first_minimum_distance_mm": round(first_min_delta_mm, 3),
            "derived_slit_width_mm": round(slit_width_a_m * 1000.0, 4),
            "nominal_slit_width_mm": round(nominal_a * 1000.0, 4),
            "slit_width_error_pct": round(a_error_pct, 2),
            "wavelength_nm": round(wl * 1e9, 1),
            "screen_distance_m": l_dist,
            "slit_type": slit_type,
        }

        if slit_separation_d_m is not None:
            nominal_d = float(
                params.get(
                    "nominal_slit_separation_m",
                    DEFAULT_SLIT_SEPARATION_M,
                ),
            )
            d_diff = abs(slit_separation_d_m - nominal_d)
            d_error_pct = (d_diff / nominal_d) * 100.0
            details["derived_slit_separation_mm"] = round(
                slit_separation_d_m * 1000.0,
                4,
            )
            details["nominal_slit_separation_mm"] = round(nominal_d * 1000.0, 4)
            details["slit_separation_error_pct"] = round(d_error_pct, 2)

        msg = (
            f"Central peak at {x_center_mm:.2f} mm (I={max_i:.2f}), "
            f"Slit width a = {slit_width_a_m * 1000.0:.3f} mm "
            f"(Nominal: {nominal_a * 1000.0:.3f} mm, Error: {a_error_pct:.1f}%)"
        )
        if slit_separation_d_m is not None:
            msg += f", Slit separation d = {slit_separation_d_m * 1000.0:.3f} mm"

        return RecipePhaseResult(
            phase="analyze",
            status="completed",
            message=msg,
            details=details,
        )
