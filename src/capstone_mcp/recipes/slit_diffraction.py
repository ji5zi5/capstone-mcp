# Copyright 2026 Capstone MCP contributors.
"""Light Interference and Slit Diffraction experiment automation recipe."""

import math
from itertools import pairwise
from statistics import median
from typing import Any, Final

from capstone_mcp.desktop import Capstone
from capstone_mcp.numerics.diffraction import fit_double_slit
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

    start = 1
    while start < n - 1:
        end = start
        level = values[start]
        while end + 1 < n and values[end + 1] == level:
            end += 1
        if end + 1 == n:
            break
        previous, following = values[start - 1], values[end + 1]
        center = positions[start] / 2 + positions[end] / 2
        if level > max(previous, following):
            maxima.append((center, level))
        elif level < min(previous, following):
            minima.append((center, level))
        start = end + 1

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

    if first_min_delta_mm <= 0:
        msg = "No resolvable diffraction minimum; slit width cannot be measured."
        raise ValueError(msg)
    delta_x_m = first_min_delta_mm * 1e-3
    sine = delta_x_m / math.hypot(l_dist, delta_x_m)
    if sine <= 0 or not math.isfinite(wl / sine * 1000):
        msg = "First minimum geometry exceeds finite numerical range."
        raise ValueError(msg)
    slit_width_a_m = wl / sine

    return first_min_delta_mm, slit_width_a_m


def _compare_nominal(
    width: float, params: dict[str, Any],
) -> tuple[dict[str, float], str]:
    if "nominal_slit_width_m" not in params:
        return {}, ""
    try:
        nominal = float(params["nominal_slit_width_m"])
    except (TypeError, ValueError, OverflowError) as exc:
        msg = "Nominal slit width must be positive and finite."
        raise ValueError(msg) from exc
    if not math.isfinite(nominal) or nominal <= 0:
        msg = "Nominal slit width must be positive and finite."
        raise ValueError(msg)
    deviation = abs(width - nominal) / nominal * 100
    if not math.isfinite(deviation) or not math.isfinite(nominal * 1000):
        msg = "Nominal comparison exceeds finite numerical range."
        raise ValueError(msg)
    return {
        "nominal_slit_width_mm": round(nominal * 1000, 4),
        "slit_width_error_pct": round(deviation, 2),
    }, f" (deviation from supplied nominal width: {deviation:.1f}%)"


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

    offsets = [(position - x_center_mm) * 1e-3 for position in side_maxima]
    peak_positions = sorted([0.0, *(x / math.hypot(l_dist, x) for x in offsets)])
    spacings = [right - left for left, right in pairwise(peak_positions)]
    angular_spacing = median(spacings)
    if angular_spacing <= 0:
        return None
    return wl / angular_spacing


def _analyze_double_slit(
    maxima: list[tuple[float, float]],
    center: float,
    wavelength: float,
    distance: float,
) -> RecipePhaseResult:
    separation = _derive_slit_separation(maxima, center, wavelength, distance)
    if separation is None or not math.isfinite(separation * 1000.0):
        msg = "Need resolved side fringes to estimate finite slit separation."
        raise ValueError(msg)
    return RecipePhaseResult(
        phase="analyze", status="completed",
        message="Estimated slit separation from interference fringe spacing.",
        details={"derived_slit_separation_mm": separation * 1000.0},
    )


def _verify_peak_symmetry(
    positions: list[float],
    center: float,
    left: list[float],
    right: list[float],
) -> None:
    """Require bracketing minima consistent with the measured spatial resolution."""
    if not left or not right:
        msg = "A minimum on each side is required to verify the central peak."
        raise ValueError(msg)
    resolution = max(b - a for a, b in pairwise(positions))
    if abs((center - left[0]) - (right[0] - center)) > resolution:
        msg = "Central peak and minima are asymmetric beyond sampling resolution."
        raise ValueError(msg)


def _central_peak(positions: list[float], values: list[float]) -> tuple[float, float]:
    """Locate a contiguous maximum plateau and reject unresolved isolated spikes."""
    if any(b <= a for a, b in pairwise(positions)):
        msg = "Diffraction positions must be strictly increasing."
        raise ValueError(msg)
    peak = max(values)
    indices = [i for i, value in enumerate(values) if value == peak]
    first, last = indices[0], indices[-1]
    if peak <= 0 or first == 0 or last == len(values) - 1:
        msg = "Central peak is not resolved inside the diffraction scan."
        raise ValueError(msg)
    if last - first + 1 != len(indices):
        msg = "Several disconnected maxima make the central peak ambiguous."
        raise ValueError(msg)
    if first == last and max(values[first - 1], values[last + 1]) <= peak * 0.1:
        msg = "Isolated intensity spike is not a resolved diffraction peak."
        raise ValueError(msg)
    return (positions[first] + positions[last]) / 2.0, peak


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
        """Report that automatic hardware configuration is not implemented."""
        del parameters, app
        return RecipePhaseResult(
            phase="setup",
            status="failed",
            message="Automatic hardware setup is not implemented. Configure the "
            "experiment manually and provide recorded data for analysis.",
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
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Live acquisition is not implemented. Provide recorded "
                "measurement arrays; synthetic data is not generated.",
            )

        if (
            not pos_mm
            or len(pos_mm) != len(intensities)
            or not all(math.isfinite(v) for v in (*pos_mm, *intensities))
        ):
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Provide nonempty, matching, finite measurement arrays.",
            )

        details: dict[str, Any] = {
            "data": {
                "positions_mm": pos_mm,
                "intensities": intensities,
                "slit_type": slit_type,
                "analysis_mode": params.get("analysis_mode", "separation_only"),
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
            message=f"Accepted {len(pos_mm)} caller-provided diffraction samples.",
            details=details,
        )

    def analyze(  # noqa: PLR0911
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

        wl = float(params.get(
            "wavelength_m", data.get("wavelength_m", DEFAULT_LASER_WAVELENGTH_M),
        ))
        l_dist = float(params.get(
            "screen_distance_m",
            data.get("screen_distance_m", DEFAULT_SCREEN_DISTANCE_M),
        ))
        slit_type = str(
            params.get("slit_type") or data.get("slit_type") or "single_slit",
        )

        if not pos_raw or not int_raw:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Missing position or intensity data for diffraction analysis.",
                details={},
            )

        positions_mm = [float(p) for p in pos_raw]
        if "positions_m" in params and not (
            params.get("positions_mm") or data.get("positions_mm")
        ):
            positions_mm = [p * 1000.0 for p in positions_mm]
        intensities = [float(i) for i in int_raw]
        if (
            len(positions_mm) < MIN_DIFFRACTION_POINTS
            or len(positions_mm) != len(intensities)
            or not all(math.isfinite(v) for v in (*positions_mm, *intensities))
        ):
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Need 5 matching finite position/intensity samples.",
            )

        if slit_type not in {"single_slit", "double_slit"} or any(
            not math.isfinite(value) or value <= 0 for value in (wl, l_dist)
        ):
            return RecipePhaseResult(
                phase="analyze", status="failed",
                message="Use a supported slit type and positive finite optics values.",
            )

        mode = str(params.get(
            "analysis_mode", data.get("analysis_mode", "separation_only"),
        ))
        if mode not in {"separation_only", "joint_envelope"}:
            return RecipePhaseResult(
                phase="analyze", status="failed", message="Unknown analysis_mode.",
            )
        if slit_type == "double_slit" and mode == "joint_envelope":
            try:
                fit = fit_double_slit(
                    [value * 1e-3 for value in positions_mm],
                    intensities,
                    wl,
                    l_dist,
                )
            except ValueError as exc:
                return RecipePhaseResult(
                    phase="analyze", status="failed", message=str(exc),
                )
            return RecipePhaseResult(
                phase="analyze",
                status="completed",
                message="Fitted double-slit interference and diffraction envelope.",
                details={
                    "slit_type": slit_type,
                    "derived_slit_width_mm": fit.width_m * 1000,
                    "derived_slit_separation_mm": fit.separation_m * 1000,
                    "central_maximum": {"position_mm": fit.center_m * 1000},
                    "amplitude": fit.amplitude,
                    "background": fit.background,
                    "normalized_rms": fit.normalized_rms,
                    "model": "equal-width Fraunhofer double slit + constant background",
                    "wavelength_nm": wl * 1e9,
                    "screen_distance_m": l_dist,
                },
            )
        try:
            x_center_mm, max_i = _central_peak(positions_mm, intensities)
            maxima_pts, minima_pts = _find_local_extrema(positions_mm, intensities)
            if slit_type == "double_slit":
                return _analyze_double_slit(maxima_pts, x_center_mm, wl, l_dist)
            left_minima = sorted(
                [p for p, _ in minima_pts if p < x_center_mm],
                reverse=True,
            )
            right_minima = sorted([p for p, _ in minima_pts if p > x_center_mm])
            _verify_peak_symmetry(positions_mm, x_center_mm, left_minima, right_minima)
            first_min_delta_mm, slit_width_a_m = _derive_slit_width(
                left_minima,
                right_minima,
                x_center_mm,
                wl,
                l_dist,
            )
            comparison, reference_text = _compare_nominal(slit_width_a_m, params)
        except ValueError as exc:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message=str(exc),
            )

        details: dict[str, Any] = {
            "central_maximum": {
                "position_mm": round(x_center_mm, 3),
                "intensity": round(max_i, 4),
            },
            "diffraction_minima_count": len(minima_pts),
            "diffraction_maxima_count": len(maxima_pts),
            "first_minimum_distance_mm": round(first_min_delta_mm, 3),
            "derived_slit_width_mm": round(slit_width_a_m * 1000.0, 4),
            "wavelength_nm": round(wl * 1e9, 1),
            "screen_distance_m": l_dist,
            "slit_type": slit_type,
            **comparison,
        }

        msg = (
            f"Central peak at {x_center_mm:.2f} mm (I={max_i:.2f}), "
            f"Slit width a = {slit_width_a_m * 1000.0:.3f} mm{reference_text}"
        )

        return RecipePhaseResult(
            phase="analyze",
            status="completed",
            message=msg,
            details=details,
        )
