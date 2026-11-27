# Copyright 2026 Capstone MCP contributors.
"""Adiabatic Gas Law and Heat Engine Cycle experiment automation recipe."""

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Final

from capstone_mcp.desktop import Capstone
from capstone_mcp.numerics.regression import (
    fit_weighted_linear_series,
    strictly_monotonic,
)
from capstone_mcp.recipes.base import ExperimentRecipe, RecipePhaseResult

DEFAULT_SAMPLING_RATE_HZ: Final[float] = 1000.0  # 1000 Hz high-speed sampling
GAMMA_AIR_THEORY: Final[float] = 1.400  # Theoretical diatomic gas gamma (7/5)
MIN_CYCLE_POINTS: Final[int] = 3
MIN_ANALYSIS_POINTS: Final[int] = 4
MIN_PHYSICAL_GAMMA: Final[float] = 1.0
R_GAS_CONSTANT_J_MOL_K: Final[float] = 8.314462618
DEFAULT_CV_DIATOMIC_J_MOL_K: Final[float] = 2.5 * R_GAS_CONSTANT_J_MOL_K


def _pressure_volume_work(
    pressure_kpa: list[float],
    volume_cm3: list[float],
    *, closed: object,
) -> dict[str, Any]:
    """Integrate P dV along consecutive observations and classify cycle sign."""
    if not isinstance(closed, bool):
        msg = "closed_cycle must be a boolean."
        raise TypeError(msg)
    work = math.fsum(
        (p0 * 0.5 + p1 * 0.5) * (v1 - v0)
        for (p0, v0), (p1, v1) in pairwise(zip(pressure_kpa, volume_cm3, strict=True))
    )
    result: dict[str, Any] = {"path_work_mj": work, "path_work_joules": work * 1e-3}
    if closed:
        mean_pressure = pressure_kpa[-1] * 0.5 + pressure_kpa[0] * 0.5
        cycle = work + mean_pressure * (volume_cm3[0] - volume_cm3[-1])
        if cycle > 0:
            orientation = "clockwise_heat_engine"
        elif cycle < 0:
            orientation = "counterclockwise_refrigerator_or_loss"
        else:
            orientation = "zero_net_work"
        result.update(
            cyclic_work_mj=cycle,
            cyclic_work_joules=cycle * 1e-3,
            cycle_orientation=orientation,
        )
    if not all(
        math.isfinite(value)
        for key, value in result.items()
        if key != "cycle_orientation"
    ):
        msg = "Pressure-volume work exceeds finite numerical range."
        raise ValueError(msg)
    return result


@dataclass(frozen=True)
class _GammaFitOptions:
    method: str
    weighted: bool
    pressure_uncertainty_kpa: float | None
    strict_adiabatic: bool = False


@dataclass(frozen=True)
class _StrokeSlice:
    start: int
    end: int
    direction: int


def _validate_gamma_stability(gamma_exp: float, *, strict: bool = False) -> bool:
    """Reject nonpositive gamma; flag 0 < gamma < 1 as sub-isothermal/unphysical."""
    if not math.isfinite(gamma_exp) or gamma_exp <= 0.0:
        msg = "Fitted slope implies nonpositive adiabatic index."
        raise ValueError(msg)
    if gamma_exp < MIN_PHYSICAL_GAMMA:
        if strict:
            msg = (
                f"Fitted adiabatic index gamma={gamma_exp:.4f} violates "
                "thermodynamic stability (gamma >= 1.0 required)."
            )
            raise ValueError(msg)
        return False
    return True


def _fit_stroke_gamma(
    pressures: list[float],
    volumes: list[float],
    options: _GammaFitOptions,
) -> tuple[float, float, float, float, bool]:
    """Fit gamma for one strictly monotonic stroke with OLS and weighted diagnostics."""
    ln_v = [math.log(v) for v in volumes]
    ln_p = [math.log(p) for p in pressures]
    n = len(ln_v)
    mean_x = math.fsum(ln_v) / n
    mean_y = math.fsum(ln_p) / n
    dx = [x - mean_x for x in ln_v]
    dy = [y - mean_y for y in ln_p]
    sxx = math.fsum(x * x for x in dx)
    sxy = math.fsum(x * y for x, y in zip(dx, dy, strict=True))
    syy = math.fsum(y * y for y in dy)
    if sxx <= 0:
        msg = "Adiabatic fitting requires nonconstant volume measurements."
        raise ValueError(msg)
    ols_gamma = -(sxy / sxx)
    ols_r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 1.0

    # With uniform pressure error dP, Var(ln P) ~= (dP / P)^2 -> weight w_i = P_i^2.
    sigma_p = options.pressure_uncertainty_kpa or 1.0
    weights = [(p / sigma_p) ** 2 for p in pressures]
    weighted_fit = fit_weighted_linear_series(ln_v, ln_p, weights)
    weighted_gamma = -weighted_fit.slope

    gamma_exp = weighted_gamma if options.weighted else ols_gamma
    r_squared = weighted_fit.r_squared if options.weighted else ols_r2
    physical = _validate_gamma_stability(gamma_exp, strict=options.strict_adiabatic)
    err_diff = abs(gamma_exp - GAMMA_AIR_THEORY)
    gamma_error_pct = (err_diff / GAMMA_AIR_THEORY) * 100.0
    return gamma_exp, r_squared, gamma_error_pct, weighted_gamma, physical


def _segment_monotonic_strokes(
    pressures: list[float],
    volumes: list[float],
    options: _GammaFitOptions,
) -> list[dict[str, Any]]:
    """Segment multi-cycle recordings into monotonic compression/expansion strokes."""
    strokes: list[dict[str, Any]] = []
    start = 0
    direction = 0
    n = len(volumes)
    idx = 1
    while idx < n:
        diff = volumes[idx] - volumes[idx - 1]
        step_dir = 1 if diff > 0 else (-1 if diff < 0 else 0)
        if step_dir == 0:
            if idx - start >= MIN_CYCLE_POINTS and direction != 0:
                _append_stroke(
                    pressures,
                    volumes,
                    strokes,
                    _StrokeSlice(start=start, end=idx - 1, direction=direction),
                    options,
                )
            start = idx
            direction = 0
        elif direction == 0:
            direction = step_dir
        elif step_dir != direction:
            if idx - start >= MIN_CYCLE_POINTS:
                _append_stroke(
                    pressures,
                    volumes,
                    strokes,
                    _StrokeSlice(start=start, end=idx - 1, direction=direction),
                    options,
                )
            start = idx - 1
            direction = step_dir
        idx += 1
    if n - start >= MIN_CYCLE_POINTS and direction != 0:
        _append_stroke(
            pressures,
            volumes,
            strokes,
            _StrokeSlice(start=start, end=n - 1, direction=direction),
            options,
        )
    return strokes


def _append_stroke(
    pressures: list[float],
    volumes: list[float],
    strokes: list[dict[str, Any]],
    stroke: _StrokeSlice,
    options: _GammaFitOptions,
) -> None:
    seg_p = pressures[stroke.start : stroke.end + 1]
    seg_v = volumes[stroke.start : stroke.end + 1]
    if not all(math.isfinite(v) and v > 0 for v in (*seg_p, *seg_v)):
        return
    try:
        gamma_exp, r_sq, err_pct, w_gamma, physical = _fit_stroke_gamma(
            seg_p, seg_v, options,
        )
    except ValueError:
        return
    entry: dict[str, Any] = {
        "start_index": stroke.start,
        "end_index": stroke.end,
        "stroke_type": "expansion" if stroke.direction > 0 else "compression",
        "r_squared": round(r_sq, 4),
    }
    if physical:
        entry.update(
            gamma_fit_status="fitted",
            adiabatic_index_gamma_exp=round(gamma_exp, 4),
            weighted_gamma_exp=round(w_gamma, 4),
            gamma_error_pct=round(err_pct, 2),
        )
    else:
        entry.update(
            gamma_fit_status="rejected_sub_isothermal",
            polytropic_exponent_n=round(gamma_exp, 4),
        )
    strokes.append(entry)


def _analyze_temperatures(
    params: dict[str, Any],
    data: dict[str, Any],
    volumes: list[float],
    gamma_exp: float | None,
    path_work_joules: float,
) -> dict[str, Any] | None:
    """Validate temperature channel and check adiabatic/First-Law consistency."""
    raw_k = params.get("temperatures_k") or data.get("temperatures_k")
    raw_c = params.get("temperatures_c") or data.get("temperatures_c")
    if raw_k is not None:
        temps_k = [float(t) for t in raw_k]
    elif raw_c is not None:
        temps_k = [float(t) + 273.15 for t in raw_c]
    else:
        return None
    if len(temps_k) != len(volumes):
        msg = "Temperature array length must match pressure and volume arrays."
        raise ValueError(msg)
    if not all(math.isfinite(t) and t > 0.0 for t in temps_k):
        msg = "Gas temperatures must be finite and above absolute zero (> 0 K)."
        raise ValueError(msg)

    delta_t = temps_k[-1] - temps_k[0]
    summary: dict[str, Any] = {
        "temp_min_k": round(min(temps_k), 2),
        "temp_max_k": round(max(temps_k), 2),
        "delta_temp_k": round(delta_t, 3),
    }
    if gamma_exp is not None and all(v > 0 for v in volumes):
        constants = [
            t * (v ** (gamma_exp - 1.0))
            for t, v in zip(temps_k, volumes, strict=True)
        ]
        mean_c = math.fsum(constants) / len(constants)
        if mean_c > 0:
            var_c = math.fsum((c - mean_c) ** 2 for c in constants) / len(constants)
            summary["tv_invariant_cv_pct"] = round(math.sqrt(var_c) / mean_c * 100.0, 3)
    moles = params.get("moles", data.get("moles"))
    if moles is not None:
        n_mol = float(moles)
        raw_cv = params.get("cv_j_mol_k", data.get("cv_j_mol_k"))
        cv = float(DEFAULT_CV_DIATOMIC_J_MOL_K if raw_cv is None else raw_cv)
        if not math.isfinite(n_mol) or n_mol <= 0 or not math.isfinite(cv) or cv <= 0:
            msg = "Gas moles and molar heat capacity Cv must be finite positive."
            raise ValueError(msg)
        delta_u_j = n_mol * cv * delta_t
        q_inferred_j = delta_u_j + path_work_joules
        summary.update(
            internal_energy_change_joules=round(delta_u_j, 4),
            inferred_heat_transfer_joules=round(q_inferred_j, 4),
        )
    return summary


def _fit_adiabatic_index(
    pressures: list[float],
    volumes: list[float],
    options: _GammaFitOptions,
) -> tuple[float, float, float, float, bool] | None:
    """Fit every observation on one compression or expansion stroke."""
    if not all(math.isfinite(v) and v > 0 for v in (*pressures, *volumes)):
        msg = "Adiabatic fitting requires finite positive pressure and volume."
        raise ValueError(msg)
    valid_pairs = list(zip(pressures, volumes, strict=True))
    if len(valid_pairs) < MIN_CYCLE_POINTS:
        msg = "Adiabatic fitting requires at least three measured pairs."
        raise ValueError(msg)
    ln_v = [math.log(v) for _, v in valid_pairs]

    if len(set(ln_v)) < 2:  # noqa: PLR2004
        msg = "Adiabatic fitting requires positive data at distinct volumes."
        raise ValueError(msg)
    if not strictly_monotonic(volumes):
        return None
    return _fit_stroke_gamma(pressures, volumes, options)


def _parse_fit_options(
    params: dict[str, Any],
    data: dict[str, Any],
) -> _GammaFitOptions:
    fit_method = str(params.get("fit_method", data.get("fit_method", "ols_log")))
    if fit_method not in {"ols_log", "weighted_log"}:
        msg = "fit_method must be 'ols_log' or 'weighted_log'."
        raise ValueError(msg)
    raw_unc = params.get(
        "pressure_uncertainty_kpa", data.get("pressure_uncertainty_kpa"),
    )
    pressure_unc = float(raw_unc) if raw_unc is not None else None
    if pressure_unc is not None and (
        not math.isfinite(pressure_unc) or pressure_unc <= 0
    ):
        msg = "pressure_uncertainty_kpa must be finite and positive."
        raise ValueError(msg)
    strict = bool(params.get("strict_adiabatic", data.get("strict_adiabatic", False)))
    return _GammaFitOptions(
        method=fit_method,
        weighted=fit_method == "weighted_log",
        pressure_uncertainty_kpa=pressure_unc,
        strict_adiabatic=strict,
    )


class AdiabaticGasRecipe(ExperimentRecipe):
    """Macro recipe executing 1000Hz sampling & cyclic work area integration."""

    experiment_id = "adiabatic_gas"
    title = "Adiabatic Gas Law & Heat Engine Cycle (단열 기체 및 열기관)"
    description = (
        "1000Hz sampling, P-V cycle area integration (oint P dV), and "
        "adiabatic index gamma (PV^gamma = const) curve fitting."
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
        """Acquire 1000Hz pressure and volume datasets during thermodynamic cycle."""
        del app
        params = parameters or {}

        if "pressure_kpa" in params and "volume_cm3" in params:
            p_data = [float(p) for p in params["pressure_kpa"]]
            v_data = [float(v) for v in params["volume_cm3"]]
        else:
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Live acquisition is not implemented. Provide recorded "
                "measurement arrays; synthetic data is not generated.",
            )

        if (
            not p_data
            or len(p_data) != len(v_data)
            or not all(math.isfinite(v) for v in (*p_data, *v_data))
        ):
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Provide nonempty, matching, finite measurement arrays.",
            )

        details: dict[str, Any] = {
            "data": {
                "pressure_kpa": p_data,
                "volume_cm3": v_data,
            },
            "sample_count": len(p_data),
            "p_max_kpa": max(p_data) if p_data else 0.0,
            "p_min_kpa": min(p_data) if p_data else 0.0,
            "v_max_cm3": max(v_data) if v_data else 0.0,
            "v_min_cm3": min(v_data) if v_data else 0.0,
        }

        return RecipePhaseResult(
            phase="acquire",
            status="completed",
            message=f"Accepted caller-provided {len(p_data)} P-V samples.",
            details=details,
        )

    def analyze(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> RecipePhaseResult:
        """Calculate cyclic work oint P dV and fit adiabatic index gamma."""
        params = parameters or {}
        data = params.get("data", {})

        p_raw = params.get("pressure_kpa") or data.get("pressure_kpa")
        v_raw = params.get("volume_cm3") or data.get("volume_cm3")

        if not p_raw or not v_raw:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Missing pressure or volume data for adiabatic gas analysis.",
                details={},
            )

        pressures = [float(p) for p in p_raw]
        volumes = [float(v) for v in v_raw]

        if len(pressures) != len(volumes):
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Pressure and volume array lengths do not match.",
                details={"p_count": len(pressures), "v_count": len(volumes)},
            )

        if len(pressures) < MIN_ANALYSIS_POINTS:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="At least 4 data points required for cycle area integration.",
                details={"points_count": len(pressures)},
            )

        same_endpoint = (pressures[0], volumes[0]) == (pressures[-1], volumes[-1])
        closed = params.get("closed_cycle", same_endpoint)
        # 2. Adiabatic Index Gamma Fit: ln(P) = -gamma * ln(V) + ln(C)
        try:
            options = _parse_fit_options(params, data)
            fit = _fit_adiabatic_index(pressures, volumes, options)
            work = _pressure_volume_work(pressures, volumes, closed=closed)
            gamma_for_temp = fit[0] if fit is not None and fit[4] else None
            temp_summary = _analyze_temperatures(
                params, data, volumes, gamma_for_temp, float(work["path_work_joules"]),
            )
        except (OverflowError, TypeError, ValueError) as exc:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message=str(exc),
            )

        p_max = max(pressures)
        p_min = min(pressures)
        v_max = max(volumes)
        v_min = min(volumes)
        compression_ratio = v_max / v_min if v_min > 0 else 1.0

        details: dict[str, Any] = {
            **work,
            "p_max_kpa": round(p_max, 2),
            "p_min_kpa": round(p_min, 2),
            "v_max_cm3": round(v_max, 2),
            "v_min_cm3": round(v_min, 2),
            "compression_ratio": round(compression_ratio, 2),
            "cycle_points_count": len(pressures),
            "fit_method": options.method,
        }
        if temp_summary is not None:
            details["temperature_analysis"] = temp_summary

        msg = (
            f"Measured path work P dV = {work['path_work_joules']:.4f} J, "
            f"Compression ratio = {compression_ratio:.1f}:1"
        )
        if fit is None:
            msg += ". Supply one monotonic adiabatic stroke to estimate gamma."
            details["gamma_fit_status"] = "requires_single_stroke"
            strokes = _segment_monotonic_strokes(pressures, volumes, options)
            if strokes:
                details["strokes"] = strokes
        else:
            gamma_exp, r_squared, gamma_error_pct, weighted_gamma, physical = fit
            if physical:
                details.update(
                    gamma_fit_status="fitted",
                    adiabatic_index_gamma_exp=round(gamma_exp, 4),
                    weighted_adiabatic_index_gamma_exp=round(weighted_gamma, 4),
                    adiabatic_index_gamma_theory=GAMMA_AIR_THEORY,
                    gamma_error_pct=round(gamma_error_pct, 2),
                    r_squared=round(r_squared, 4),
                )
                msg += f", gamma = {gamma_exp:.3f}, R^2 = {r_squared:.4f}."
            else:
                details.update(
                    gamma_fit_status="rejected_sub_isothermal",
                    polytropic_exponent_n=round(gamma_exp, 4),
                    r_squared=round(r_squared, 4),
                )
                msg += (
                    f". Polytropic exponent n = {gamma_exp:.3f} < 1.0 "
                    "is sub-isothermal; omitted adiabatic gamma."
                )

        return RecipePhaseResult(
            phase="analyze",
            status="completed",
            message=msg,
            details=details,
        )
