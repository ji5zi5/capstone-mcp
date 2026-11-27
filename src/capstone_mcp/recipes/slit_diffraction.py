# Copyright 2026 Capstone MCP contributors.
"""Light Interference and Slit Diffraction experiment automation recipe."""

import math
from dataclasses import dataclass
from itertools import pairwise
from statistics import mean, median, stdev
from typing import Any, Final

from capstone_mcp.desktop import Capstone
from capstone_mcp.numerics.diffraction import fit_double_slit
from capstone_mcp.recipes.base import ExperimentRecipe, RecipePhaseResult


@dataclass(frozen=True)
class _DiffractionContext:
    wl: float
    l_dist: float
    params: dict[str, Any]
    data: dict[str, Any]

DEFAULT_LASER_WAVELENGTH_M: Final[float] = 650.0e-9  # Red diode laser (650 nm)
DEFAULT_SCREEN_DISTANCE_M: Final[float] = 1.0  # 1.0 m optics bench distance
DEFAULT_SLIT_WIDTH_M: Final[float] = 4.0e-5  # 0.04 mm single slit
DEFAULT_SLIT_SEPARATION_M: Final[float] = 2.5e-4  # 0.25 mm double slit

MIN_PROFILE_POINTS: Final[int] = 3
MIN_DIFFRACTION_POINTS: Final[int] = 5
SIDE_PEAK_THRESHOLD_MM: Final[float] = 0.05
MIN_SIDE_MAXIMA_COUNT: Final[int] = 2
EPSILON_BETA: Final[float] = 1e-9
DEFAULT_MIN_PROMINENCE_RATIO: Final[float] = 0.005
MAX_SMOOTHING_WINDOW: Final[int] = 9
MIN_MULTI_ORDER_COUNT: Final[int] = 2
ORDER_MATCH_TOLERANCE: Final[float] = 0.25
MISSING_ORDER_GAP_RATIO: Final[float] = 1.75
MIN_FRINGE_STATS_COUNT: Final[int] = 2


def _plateau_prominence(
    values: list[float],
    start: int,
    end: int,
    *,
    is_maximum: bool,
) -> float:
    """Compute exact 1D topological prominence for a contiguous plateau extremum."""
    level = values[start]
    n = len(values)
    if is_maximum:
        left = level
        for idx in range(start - 1, -1, -1):
            if values[idx] > level:
                break
            left = min(left, values[idx])
        right = level
        for idx in range(end + 1, n):
            if values[idx] > level:
                break
            right = min(right, values[idx])
        return level - max(left, right)

    left = level
    for idx in range(start - 1, -1, -1):
        if values[idx] < level:
            break
        left = max(left, values[idx])
    right = level
    for idx in range(end + 1, n):
        if values[idx] < level:
            break
        right = max(right, values[idx])
    return min(left, right) - level


def _smooth_intensities(values: list[float], window: int) -> list[float]:
    """Apply a symmetric triangular moving average without shifting coordinates."""
    if window <= 1:
        return values
    half = window // 2
    n = len(values)
    smoothed: list[float] = []
    for idx in range(n):
        lo = max(0, idx - half)
        hi = min(n - 1, idx + half)
        weighted = 0.0
        total_weight = 0.0
        for pos in range(lo, hi + 1):
            weight = float(half + 1 - abs(pos - idx))
            weighted += values[pos] * weight
            total_weight += weight
        smoothed.append(weighted / total_weight)
    return smoothed


def _parse_finite_number(raw: object, name: str) -> float:
    """Convert non-boolean input into a finite floating-point scalar."""
    if isinstance(raw, bool):
        msg = f"{name} must be numeric, not boolean."
        raise TypeError(msg)
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        msg = f"{name} must be a finite number."
        raise ValueError(msg) from exc
    if not math.isfinite(value):
        msg = f"{name} must be a finite number."
        raise ValueError(msg)
    return value


def _parse_smoothing_window(raw: object) -> int:
    """Validate optional odd moving-average window size."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        msg = "smoothing_window must be an odd integer."
        raise TypeError(msg)
    if not 1 <= raw <= MAX_SMOOTHING_WINDOW or raw % 2 == 0:
        msg = (
            f"smoothing_window must be an odd integer between 1 and "
            f"{MAX_SMOOTHING_WINDOW}."
        )
        raise ValueError(msg)
    return raw


def _parse_noise_filter(
    params: dict[str, Any],
    data: dict[str, Any],
    span: float,
) -> tuple[float, dict[str, float | int]]:
    """Resolve explicit or default prominence and smoothing settings."""
    has_ratio = "min_prominence_ratio" in params or "min_prominence_ratio" in data
    raw_ratio = params.get(
        "min_prominence_ratio",
        data.get("min_prominence_ratio", DEFAULT_MIN_PROMINENCE_RATIO),
    )
    ratio = _parse_finite_number(raw_ratio, "min_prominence_ratio")
    if not 0.0 <= ratio <= 1.0:
        msg = "min_prominence_ratio must be in [0, 1]."
        raise ValueError(msg)

    raw_abs = params.get("min_prominence", data.get("min_prominence"))
    abs_prominence: float | None = None
    if raw_abs is not None:
        abs_prominence = _parse_finite_number(raw_abs, "min_prominence")
        if abs_prominence < 0.0:
            msg = "min_prominence must be nonnegative."
            raise ValueError(msg)

    window = _parse_smoothing_window(
        params.get("smoothing_window", data.get("smoothing_window", 1)),
    )

    if abs_prominence is not None and not has_ratio:
        effective = abs_prominence
        effective_ratio = abs_prominence / span if span > 0 else 0.0
    elif abs_prominence is not None:
        effective = max(abs_prominence, span * ratio)
        effective_ratio = ratio
    else:
        effective = span * ratio
        effective_ratio = ratio

    return effective, {
        "min_prominence": effective,
        "min_prominence_ratio": effective_ratio,
        "smoothing_window": window,
    }


def _parabolic_vertex_x(
    positions: list[float],
    values: list[float],
    index: int,
    *,
    is_maximum: bool,
) -> float:
    """Estimate subpixel 3-point Lagrange quadratic vertex when curvature matches."""
    if index <= 0 or index >= len(positions) - 1:
        return positions[index]
    x0, x1, x2 = positions[index - 1], positions[index], positions[index + 1]
    u0, u2 = x0 - x1, x2 - x1
    denom = u0 * u2 * (u0 - u2)
    if u0 >= 0.0 or u2 <= 0.0 or denom == 0.0:
        return x1
    d0 = values[index - 1] - values[index]
    d2 = values[index + 1] - values[index]
    quad = (u2 * d0 - u0 * d2) / denom
    lin = (u0 * u0 * d2 - u2 * u2 * d0) / denom
    if (is_maximum and quad >= 0.0) or (not is_maximum and quad <= 0.0):
        return x1
    u_vertex = -lin / (2.0 * quad)
    bound = 0.5 * max(abs(u0), u2)
    if not math.isfinite(u_vertex) or abs(u_vertex) > bound:
        return x1
    candidate = x1 + u_vertex
    return candidate if x0 < candidate < x2 else x1


def _find_local_extrema(
    positions: list[float],
    values: list[float],
    *,
    min_prominence: float = 0.0,
    subpixel: bool = False,
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
            prom = _plateau_prominence(values, start, end, is_maximum=True)
            if min_prominence <= 0.0 or prom >= min_prominence:
                pos = (
                    _parabolic_vertex_x(positions, values, start, is_maximum=True)
                    if subpixel and start == end
                    else center
                )
                maxima.append((pos, level))
        elif level < min(previous, following):
            prom = _plateau_prominence(values, start, end, is_maximum=False)
            if min_prominence <= 0.0 or prom >= min_prominence:
                pos = (
                    _parabolic_vertex_x(positions, values, start, is_maximum=False)
                    if subpixel and start == end
                    else center
                )
                minima.append((pos, level))
        start = end + 1

    return maxima, minima


def _multi_order_slit_width(
    left_minima: list[float],
    right_minima: list[float],
    x_center_mm: float,
    wl: float,
    l_dist: float,
) -> dict[str, Any] | None:
    """Fit sin(theta_m) = m * lambda / a across resolved diffraction minimum orders."""
    pair_count = min(len(left_minima), len(right_minima))
    if pair_count >= MIN_MULTI_ORDER_COUNT:
        radii = [(right_minima[k] - left_minima[k]) / 2.0 for k in range(pair_count)]
    elif len(right_minima) >= MIN_MULTI_ORDER_COUNT:
        radii = [p - x_center_mm for p in right_minima]
    elif len(left_minima) >= MIN_MULTI_ORDER_COUNT:
        radii = [x_center_mm - p for p in left_minima]
    else:
        return None

    base = radii[0]
    if base <= 0.0:
        return None
    orders: list[int] = []
    sines: list[float] = []
    for radius in radii:
        order = round(radius / base)
        if (
            order < 1
            or abs(radius / base - order) > ORDER_MATCH_TOLERANCE
            or order in orders
        ):
            continue
        delta_m = radius * 1e-3
        sine = delta_m / math.hypot(l_dist, delta_m)
        if sine > 0.0:
            orders.append(order)
            sines.append(sine)

    if len(orders) < MIN_MULTI_ORDER_COUNT:
        return None
    denom = math.fsum(float(m * m) for m in orders)
    slope = math.fsum(m * s for m, s in zip(orders, sines, strict=True)) / denom
    if slope <= 0.0 or not math.isfinite(wl / slope * 1000.0):
        return None
    mean_s = mean(sines)
    ss_tot = math.fsum((s - mean_s) ** 2 for s in sines)
    ss_res = math.fsum((s - m * slope) ** 2 for m, s in zip(orders, sines, strict=True))
    r_squared = max(0.0, min(1.0, 1.0 - ss_res / ss_tot)) if ss_tot > 0 else 1.0
    return {
        "orders_used": orders,
        "derived_slit_width_mm": round((wl / slope) * 1000.0, 4),
        "r_squared": round(r_squared, 6),
    }


def _single_slit_uncertainty(
    slit_width_m: float,
    delta_x_m: float,
    positions_mm: list[float],
    *,
    paired_sides: bool,
    ctx: _DiffractionContext,
) -> dict[str, Any]:
    """Propagate GUM combined standard uncertainty u_c and U_95 for slit width a."""
    wl_unc = _optional_nonneg_float(
        ctx.params, ctx.data, "wavelength_uncertainty_m", 0.0,
    )
    dist_unc = _optional_nonneg_float(
        ctx.params, ctx.data, "screen_distance_uncertainty_m", 0.0,
    )
    default_step_m = median(b - a for a, b in pairwise(positions_mm)) * 1e-3
    pos_res_m = _optional_nonneg_float(
        ctx.params, ctx.data, "position_resolution_m", default_step_m,
    )
    u_x_m = pos_res_m / math.sqrt(12.0)
    if paired_sides:
        u_x_m /= math.sqrt(2.0)

    rel_wl = wl_unc / ctx.wl if ctx.wl > 0 else 0.0
    rel_l = dist_unc / ctx.l_dist if ctx.l_dist > 0 else 0.0
    # d(sin theta)/dx / sin(theta) = L^2 / (x * (L^2 + x^2)) for delta_x = x.
    angle_factor = (
        (ctx.l_dist * ctx.l_dist) / (ctx.l_dist * ctx.l_dist + delta_x_m * delta_x_m)
    )
    rel_x = angle_factor * (u_x_m / delta_x_m) if delta_x_m > 0 else 0.0
    rel_comb = math.sqrt(rel_wl * rel_wl + rel_l * rel_l + rel_x * rel_x)
    u_c_mm = slit_width_m * rel_comb * 1000.0
    return {
        "standard_uncertainty_mm": round(u_c_mm, 5),
        "expanded_uncertainty_95_mm": round(2.0 * u_c_mm, 5),
        "relative_uncertainty_pct": round(rel_comb * 100.0, 3),
        "coverage_factor": 2.0,
        "components": {
            "wavelength_rel": round(rel_wl, 6),
            "screen_distance_rel": round(rel_l, 6),
            "position_rel": round(rel_x, 6),
        },
    }


def _optional_nonneg_float(
    params: dict[str, Any],
    data: dict[str, Any],
    key: str,
    default: float,
) -> float:
    raw = params.get(key, data.get(key, default))
    val = _parse_finite_number(raw, key)
    if val < 0.0:
        msg = f"{key} must be nonnegative."
        raise ValueError(msg)
    return val


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


def _normalize_missing_orders(raw_spacings: list[float]) -> tuple[list[float], bool]:
    """Normalize integer-multiple gaps caused by missing interference orders."""
    base = min(raw_spacings)
    if base <= 0.0:
        return raw_spacings, False
    normalized: list[float] = []
    has_missing = False
    for spacing in raw_spacings:
        if spacing >= MISSING_ORDER_GAP_RATIO * base:
            order = round(spacing / base)
            if (
                order >= MIN_MULTI_ORDER_COUNT
                and abs(spacing / base - order) <= ORDER_MATCH_TOLERANCE
            ):
                normalized.extend([spacing / order] * order)
                has_missing = True
                continue
        normalized.append(spacing)
    return normalized, has_missing


def _derive_slit_separation(
    maxima_pts: list[tuple[float, float]],
    x_center_mm: float,
    wl: float,
    l_dist: float,
) -> tuple[float, dict[str, Any]] | None:
    """Calculate slit separation d with missing-order recovery and spacing stats."""
    side_maxima = [
        p for p, _ in maxima_pts if abs(p - x_center_mm) > SIDE_PEAK_THRESHOLD_MM
    ]
    if len(side_maxima) < MIN_SIDE_MAXIMA_COUNT:
        return None

    offsets = [(position - x_center_mm) * 1e-3 for position in side_maxima]
    peak_positions = sorted([0.0, *(x / math.hypot(l_dist, x) for x in offsets)])
    raw_spacings = [right - left for left, right in pairwise(peak_positions)]
    normalized, has_missing = _normalize_missing_orders(raw_spacings)
    angular_spacing = median(normalized)
    if angular_spacing <= 0:
        return None
    ang_mean = mean(normalized)
    ang_std = stdev(normalized) if len(normalized) >= MIN_FRINGE_STATS_COUNT else 0.0
    ang_sem = ang_std / math.sqrt(len(normalized))
    ang_cv = ang_std / ang_mean if ang_mean > 0 else 0.0
    return wl / angular_spacing, {
        "fringe_count": len(normalized),
        "fringe_angular_mean": round(ang_mean, 8),
        "fringe_angular_std": round(ang_std, 8),
        "fringe_angular_sem": round(ang_sem, 8),
        "fringe_spacing_cv": round(ang_cv, 5),
        "missing_order_gaps_detected": has_missing,
    }


def _analyze_double_slit(
    maxima: list[tuple[float, float]],
    center: float,
    ctx: _DiffractionContext,
    *,
    noise_filter: dict[str, float | int] | None = None,
) -> RecipePhaseResult:
    derived = _derive_slit_separation(maxima, center, ctx.wl, ctx.l_dist)
    if derived is None or not math.isfinite(derived[0] * 1000.0):
        msg = "Need resolved side fringes to estimate finite slit separation."
        raise ValueError(msg)
    separation, stats = derived
    ang_mean = float(stats["fringe_angular_mean"])
    ang_sem = float(stats["fringe_angular_sem"])
    wl_unc = _optional_nonneg_float(
        ctx.params, ctx.data, "wavelength_uncertainty_m", 0.0,
    )
    dist_unc = _optional_nonneg_float(
        ctx.params, ctx.data, "screen_distance_uncertainty_m", 0.0,
    )
    rel_ang = ang_sem / ang_mean if ang_mean > 0 else 0.0
    rel_wl = wl_unc / ctx.wl if ctx.wl > 0 else 0.0
    rel_l = dist_unc / ctx.l_dist if ctx.l_dist > 0 else 0.0
    rel_comb = math.sqrt(rel_ang * rel_ang + rel_wl * rel_wl + rel_l * rel_l)
    u_d_mm = separation * rel_comb * 1000.0
    details: dict[str, Any] = {
        "derived_slit_separation_mm": separation * 1000.0,
        "fringe_statistics": stats,
        "uncertainty": {
            "standard_uncertainty_mm": round(u_d_mm, 5),
            "expanded_uncertainty_95_mm": round(2.0 * u_d_mm, 5),
            "relative_uncertainty_pct": round(rel_comb * 100.0, 3),
            "coverage_factor": 2.0,
        },
    }
    if noise_filter is not None:
        details["noise_filter"] = noise_filter
    return RecipePhaseResult(
        phase="analyze", status="completed",
        message="Estimated slit separation from interference fringe spacing.",
        details=details,
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


def _extract_filtered_features(
    positions_mm: list[float],
    intensities: list[float],
    params: dict[str, Any],
    data: dict[str, Any],
) -> tuple[
    float,
    float,
    list[tuple[float, float]],
    list[tuple[float, float]],
    dict[str, float | int],
    list[float],
    float,
]:
    """Apply optional smoothing and prominence filtering before peak extraction."""
    raw_span = max(intensities) - min(intensities)
    min_prominence, noise_filter = _parse_noise_filter(params, data, raw_span)
    window = int(noise_filter["smoothing_window"])
    profile_values = _smooth_intensities(intensities, window)
    if window > 1:
        smoothed_span = max(profile_values) - min(profile_values)
        min_prominence, noise_filter = _parse_noise_filter(
            params, data, smoothed_span,
        )
    subpixel = bool(
        params.get("subpixel_interpolation", data.get("subpixel_interpolation", False)),
    )
    x_center_mm, max_i = _central_peak(positions_mm, profile_values)
    maxima_pts, minima_pts = _find_local_extrema(
        positions_mm,
        profile_values,
        min_prominence=min_prominence,
        subpixel=subpixel,
    )
    return (
        x_center_mm,
        max_i,
        maxima_pts,
        minima_pts,
        noise_filter,
        profile_values,
        min_prominence,
    )


def _analyze_single_slit(
    positions_mm: list[float],
    intensities: list[float],
    ctx: _DiffractionContext,
) -> RecipePhaseResult:
    """Run full single-slit diffraction extraction, multi-order, subpixel & GUM."""
    (
        x_center_mm,
        max_i,
        maxima_pts,
        minima_pts,
        noise_filter,
        profile_values,
        min_prominence,
    ) = _extract_filtered_features(positions_mm, intensities, ctx.params, ctx.data)
    left_minima = sorted([p for p, _ in minima_pts if p < x_center_mm], reverse=True)
    right_minima = sorted([p for p, _ in minima_pts if p > x_center_mm])
    _verify_peak_symmetry(positions_mm, x_center_mm, left_minima, right_minima)
    first_min_delta_mm, slit_width_a_m = _derive_slit_width(
        left_minima, right_minima, x_center_mm, ctx.wl, ctx.l_dist,
    )
    _, sub_minima = _find_local_extrema(
        positions_mm, profile_values, min_prominence=min_prominence, subpixel=True,
    )
    sub_left = sorted([p for p, _ in sub_minima if p < x_center_mm], reverse=True)
    sub_right = sorted([p for p, _ in sub_minima if p > x_center_mm])
    subpixel_info: dict[str, float] | None = None
    if sub_left or sub_right:
        sub_delta, sub_width_m = _derive_slit_width(
            sub_left, sub_right, x_center_mm, ctx.wl, ctx.l_dist,
        )
        subpixel_info = {
            "first_minimum_distance_mm": round(sub_delta, 4),
            "derived_slit_width_mm": round(sub_width_m * 1000.0, 4),
        }
        if bool(
            ctx.params.get(
                "subpixel_interpolation",
                ctx.data.get("subpixel_interpolation", False),
            ),
        ):
            first_min_delta_mm = sub_delta
            slit_width_a_m = sub_width_m

    multi_order_info = _multi_order_slit_width(
        left_minima, right_minima, x_center_mm, ctx.wl, ctx.l_dist,
    )
    if (
        bool(ctx.params.get("multi_order", ctx.data.get("multi_order", False)))
        and multi_order_info is not None
    ):
        slit_width_a_m = float(multi_order_info["derived_slit_width_mm"]) * 1e-3

    uncertainty = _single_slit_uncertainty(
        slit_width_a_m,
        first_min_delta_mm * 1e-3,
        positions_mm,
        paired_sides=bool(left_minima and right_minima),
        ctx=ctx,
    )
    comparison, reference_text = _compare_nominal(slit_width_a_m, ctx.params)
    details: dict[str, Any] = {
        "central_maximum": {
            "position_mm": round(x_center_mm, 3),
            "intensity": round(max_i, 4),
        },
        "diffraction_minima_count": len(minima_pts),
        "diffraction_maxima_count": len(maxima_pts),
        "first_minimum_distance_mm": round(first_min_delta_mm, 3),
        "derived_slit_width_mm": round(slit_width_a_m * 1000.0, 4),
        "wavelength_nm": round(ctx.wl * 1e9, 1),
        "screen_distance_m": ctx.l_dist,
        "slit_type": "single_slit",
        "noise_filter": noise_filter,
        "uncertainty": uncertainty,
        **comparison,
    }
    if multi_order_info is not None:
        details["multi_order_fit"] = multi_order_info
    if subpixel_info is not None:
        details["subpixel_refinement"] = subpixel_info
    return RecipePhaseResult(
        phase="analyze",
        status="completed",
        message=(
            f"Central peak at {x_center_mm:.2f} mm (I={max_i:.2f}), "
            f"Slit width a = {slit_width_a_m * 1000.0:.3f} mm{reference_text}"
        ),
        details=details,
    )


def _joint_double_slit_result(
    positions_mm: list[float],
    intensities: list[float],
    wl: float,
    l_dist: float,
) -> RecipePhaseResult:
    try:
        fit = fit_double_slit(
            [value * 1e-3 for value in positions_mm], intensities, wl, l_dist,
        )
    except ValueError as exc:
        return RecipePhaseResult(phase="analyze", status="failed", message=str(exc))
    return RecipePhaseResult(
        phase="analyze",
        status="completed",
        message="Fitted double-slit interference and diffraction envelope.",
        details={
            "slit_type": "double_slit",
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
        for key in (
            "min_prominence_ratio",
            "min_prominence",
            "smoothing_window",
            "subpixel_interpolation",
            "multi_order",
            "wavelength_uncertainty_m",
            "screen_distance_uncertainty_m",
            "position_resolution_m",
        ):
            if key in params:
                details["data"][key] = params[key]

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
            return _joint_double_slit_result(positions_mm, intensities, wl, l_dist)
        try:
            ctx = _DiffractionContext(wl=wl, l_dist=l_dist, params=params, data=data)
            if slit_type == "double_slit":
                (
                    x_center_mm, _, maxima_pts, _, noise_filter, _, _,
                ) = _extract_filtered_features(positions_mm, intensities, params, data)
                return _analyze_double_slit(
                    maxima_pts,
                    x_center_mm,
                    ctx,
                    noise_filter=noise_filter,
                )
            return _analyze_single_slit(positions_mm, intensities, ctx)
        except (TypeError, ValueError) as exc:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message=str(exc),
            )
