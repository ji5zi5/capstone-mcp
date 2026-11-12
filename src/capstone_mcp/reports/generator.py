# Copyright 2026 Capstone MCP contributors.
"""Computation engine for physics statistics, curve fits, and ASCII plots."""

from __future__ import annotations

import contextlib
import csv
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from capstone_mcp.numerics import (
    compute_series_summary,
    fit_linear_series,
)
from capstone_mcp.reports.models import (
    DataSummary,
    ErrorAnalysisRow,
    ExperimentMetadata,
    LabReport,
    RegressionSummary,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from capstone_mcp.capfile_models import CapDataSet

# Fundamental physical constants (CODATA 2018 / 2022)
PLANCK_CONSTANT: Final[float] = 6.62607015e-34  # J * s
ELEMENTARY_CHARGE: Final[float] = 1.602176634e-19  # C
SPEED_OF_LIGHT: Final[float] = 2.99792458e8  # m / s
ADIABATIC_INDEX_AIR: Final[float] = 1.40  # dimensionless
STANDARD_GRAVITY: Final[float] = 9.80665  # m / s^2
ELECTRON_MASS: Final[float] = 9.1093837e-31  # kg

MIN_REGRESSION_POINTS: Final[int] = 2
MIN_PREVIEW_POINTS: Final[int] = 6
DECIMAL_EXPONENT_LOW: Final[float] = 0.01
DECIMAL_EXPONENT_HIGH: Final[float] = 10000.0
DEFAULT_ASCII_WIDTH: Final[int] = 50
DEFAULT_ASCII_HEIGHT: Final[int] = 15
MIN_ASCII_WIDTH: Final[int] = 20
MAX_ASCII_WIDTH: Final[int] = 80
MIN_ASCII_HEIGHT: Final[int] = 8
MAX_ASCII_HEIGHT: Final[int] = 30
AXIS_PADDING_RATIO: Final[float] = 0.05


def compute_data_summary(
    values: Sequence[float],
    variable_name: str,
    unit: str = "",
) -> DataSummary:
    """Calculate descriptive statistics for an array of measured values."""
    if not values:
        return DataSummary(
            variable_name=variable_name,
            unit=unit,
            count=0,
            mean=0.0,
            std_dev=None,
            min=0.0,
            max=0.0,
            peak_value=0.0,
            samples_preview=[],
        )

    summary = compute_series_summary(values)
    preview = [float(v) for v in values[:MIN_PREVIEW_POINTS]]

    return DataSummary(
        variable_name=variable_name,
        unit=unit,
        count=summary.count,
        mean=summary.mean,
        std_dev=summary.std_dev if summary.count > 1 else None,
        min=summary.min_val,
        max=summary.max_val,
        peak_value=summary.peak_val,
        samples_preview=preview,
    )


def _format_coeff(val: float) -> str:
    if val == 0.0:
        return "0.0"
    abs_v = abs(val)
    if abs_v < DECIMAL_EXPONENT_LOW or abs_v >= DECIMAL_EXPONENT_HIGH:
        return f"{val:.3e}"
    return f"{val:.4f}"


def compute_linear_regression(
    x: Sequence[float],
    y: Sequence[float],
    *,
    variable_names: tuple[str, str] = ("x", "y"),
    units: tuple[str, str] = ("", ""),
) -> RegressionSummary:
    """Perform ordinary least squares (OLS) linear fit and compute errors."""
    if len(x) != len(y):
        msg = f"x and y must have the same length (got {len(x)} and {len(y)})"
        raise ValueError(msg)
    if len(x) < MIN_REGRESSION_POINTS:
        msg = (
            f"At least {MIN_REGRESSION_POINTS} points required for linear "
            f"regression (got {len(x)})"
        )
        raise ValueError(msg)

    fit = fit_linear_series(x, y)
    slope = fit.slope
    intercept = fit.intercept
    r_squared = fit.r_squared
    slope_error = fit.std_err_slope if len(x) > MIN_REGRESSION_POINTS else 0.0
    intercept_error = (
        fit.std_err_intercept if len(x) > MIN_REGRESSION_POINTS else 0.0
    )

    x_var, y_var = variable_names
    x_unit, y_unit = units
    slope_str = _format_coeff(slope)
    if intercept >= 0:
        eq_str = f"{y_var} = {slope_str} * {x_var} + {_format_coeff(intercept)}"
    else:
        eq_str = (
            f"{y_var} = {slope_str} * {x_var} - {_format_coeff(abs(intercept))}"
        )

    return RegressionSummary(
        model_name="Linear Fit (y = mx + b)",
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        slope_error=slope_error,
        intercept_error=intercept_error,
        equation=eq_str,
        x_variable=x_var,
        y_variable=y_var,
        x_unit=x_unit,
        y_unit=y_unit,
    )


def compute_error_analysis(
    accepted_value: float,
    experimental_value: float,
    parameter_name: str,
    symbol: str = "",
    unit: str = "",
) -> ErrorAnalysisRow:
    """Calculate error against accepted physical constant."""
    absolute_error = abs(experimental_value - accepted_value)
    if accepted_value != 0.0:
        relative_error_percent = (absolute_error / abs(accepted_value)) * 100.0
    else:
        relative_error_percent = 0.0

    return ErrorAnalysisRow(
        parameter_name=parameter_name,
        symbol=symbol,
        accepted_value=accepted_value,
        experimental_value=experimental_value,
        unit=unit,
        absolute_error=absolute_error,
        relative_error_percent=relative_error_percent,
    )


def _plot_bounds(
    x: Sequence[float],
    y: Sequence[float],
    fit: tuple[float, float] | None,
) -> tuple[float, float, float, float]:
    min_x, max_x = min(x), max(x)
    min_y, max_y = min(y), max(y)

    if fit is not None:
        slope, intercept = fit
        y_fit_start = slope * min_x + intercept
        y_fit_end = slope * max_x + intercept
        min_y = min(min_y, y_fit_start, y_fit_end)
        max_y = max(max_y, y_fit_start, y_fit_end)

    span_x = max_x - min_x
    span_y = max_y - min_y

    pad_x = span_x * AXIS_PADDING_RATIO if span_x > 0 else 1.0
    pad_y = span_y * AXIS_PADDING_RATIO if span_y > 0 else 1.0

    return (min_x - pad_x, max_x + pad_x, min_y - pad_y, max_y + pad_y)


def _draw_canvas(
    x: Sequence[float],
    y: Sequence[float],
    bounds: tuple[float, float, float, float],
    grid_dim: tuple[int, int],
    fit: tuple[float, float] | None,
) -> list[list[str]]:
    x_lo, x_hi, y_lo, y_hi = bounds
    grid_w, grid_h = grid_dim
    canvas = [[" " for _ in range(grid_w)] for _ in range(grid_h)]

    if fit is not None and (x_hi - x_lo) > 0 and (y_hi - y_lo) > 0:
        slope, intercept = fit
        for col in range(grid_w):
            cur_x = x_lo + (col / (grid_w - 1)) * (x_hi - x_lo)
            cur_y = slope * cur_x + intercept
            row = round((grid_h - 1) * (1.0 - (cur_y - y_lo) / (y_hi - y_lo)))
            if 0 <= row < grid_h:
                canvas[row][col] = "·"

    if (x_hi - x_lo) > 0 and (y_hi - y_lo) > 0:
        for px, py in zip(x, y, strict=True):
            col = round((grid_w - 1) * (px - x_lo) / (x_hi - x_lo))
            row = round((grid_h - 1) * (1.0 - (py - y_lo) / (y_hi - y_lo)))
            if 0 <= row < grid_h and 0 <= col < grid_w:
                canvas[row][col] = "*"

    return canvas


def generate_ascii_plot(
    x: Sequence[float],
    y: Sequence[float],
    *,
    fit: tuple[float, float] | None = None,
    size: tuple[int, int] = (DEFAULT_ASCII_WIDTH, DEFAULT_ASCII_HEIGHT),
    labels: tuple[str, str] = ("x", "y"),
) -> str:
    """Render an ASCII scatter plot with optional linear regression line."""
    if not x or not y or len(x) != len(y):
        return "[Insufficient data for ASCII plot]"

    bounds = _plot_bounds(x, y, fit)
    x_lo, x_hi, y_lo, y_hi = bounds
    width, height = size
    x_label, y_label = labels

    grid_w = max(MIN_ASCII_WIDTH, min(MAX_ASCII_WIDTH, width))
    grid_h = max(MIN_ASCII_HEIGHT, min(MAX_ASCII_HEIGHT, height))

    canvas = _draw_canvas(x, y, bounds, (grid_w, grid_h), fit)

    lines: list[str] = [f"[{y_label}]"]
    for r in range(grid_h):
        y_val = y_hi - (r / (grid_h - 1)) * (y_hi - y_lo)
        if r in (0, grid_h // 2, grid_h - 1):
            tick = f"{y_val:8.2e} | "
        else:
            tick = "         | "
        lines.append(tick + "".join(canvas[r]))

    lines.append("         +-" + "-" * grid_w)
    lines.append(
        f"          {x_lo:<10.2e}"
        + " " * max(0, grid_w - 24)
        + f"{x_hi:>10.2e}",
    )
    lines.append(" " * (grid_w // 2 + 5) + f"[{x_label}]")

    return "\n".join(lines)


def _load_csv_data(path: Path) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        if headers:
            cols: list[list[float]] = [[] for _ in headers]
            for row in reader:
                for i, val in enumerate(row):
                    if i < len(cols):
                        with contextlib.suppress(ValueError):
                            cols[i].append(float(val.strip()))
            for h, col_data in zip(headers, cols, strict=False):
                if col_data:
                    series[h.strip()] = col_data
    return series


def _load_cap_data(path: Path) -> tuple[dict[str, list[float]], dict[str, str]]:
    series: dict[str, list[float]] = {}
    channels: dict[str, str] = {}
    with contextlib.suppress(Exception):
        from capstone_mcp.capfiles import (  # noqa: PLC0415
            extract_cap_datasets,
            read_cap_configuration,
        )

        datasets: list[CapDataSet] = extract_cap_datasets(path)
        for ds in datasets:
            name = ds.name or ds.source_name or f"Series_{ds.data_set_id}"
            if ds.numeric_values:
                nums = [float(v) for v in ds.numeric_values if v is not None]
                if nums:
                    series[name] = nums
        cfg = read_cap_configuration(path)
        for iface in cfg.hardware_interfaces:
            channels[f"Interface_{iface.euid}"] = iface.name or "PASCO Interface"
    return series, channels


def _load_json_data(path: Path) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    with contextlib.suppress(Exception), path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if isinstance(v, list) and all(
                    isinstance(n, (int, float)) for n in v
                ):
                    series[k] = [float(n) for n in v]
    return series


def _load_json_string(text: str) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    with contextlib.suppress(Exception):
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if isinstance(v, list) and all(
                    isinstance(n, (int, float)) for n in v
                ):
                    series[k] = [float(n) for n in v]
    return series


def _load_data_from_file_or_string(
    file_path_or_run: str | None,
) -> tuple[dict[str, list[float]], dict[str, str]]:
    """Parse numeric series and channel metadata from a path, JSON, or CSV."""
    if not file_path_or_run:
        return {}, {}

    path = Path(file_path_or_run)
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".cap":
            return _load_cap_data(path)
        if suffix == ".csv":
            with contextlib.suppress(Exception):
                return _load_csv_data(path), {}
        if suffix == ".json":
            return _load_json_data(path), {}

    if file_path_or_run.startswith("{") and file_path_or_run.endswith("}"):
        return _load_json_string(file_path_or_run), {}

    return {}, {}


def _get_curriculum_info(
    experiment_id: str,
) -> tuple[str, str, list[str], str, list[str], dict[str, str], list[str]]:
    """Retrieve title, domain, apparatus, theory, and discussion questions."""
    with contextlib.suppress(Exception):
        from capstone_mcp.tutor.curriculum import CANONICAL_EXPERIMENTS  # noqa: PLC0415

        if experiment_id in CANONICAL_EXPERIMENTS:
            cur = CANONICAL_EXPERIMENTS[experiment_id]
            questions = [q.question for q in cur.quiz_questions]
            return (
                cur.title,
                cur.domain,
                list(cur.equipment),
                cur.theory_summary,
                list(cur.governing_equations),
                dict(cur.capstone_setup),
                questions,
            )

    titles = {
        "photoelectric_effect": "Photoelectric Effect & Planck Constant Measurement",
        "rlc_resonance": "LRC Series Circuit Resonance & Impedance Analysis",
        "forced_harmonic_oscillation": "Driven Damped Harmonic Oscillation & Resonance",
        "adiabatic_gas": "Adiabatic Gas Law & Thermodynamic Cycle Work",
        "slit_diffraction": "Fraunhofer Slit Diffraction Measurement",
        "generic": "Physics Laboratory Experiment",
    }
    title = titles.get(experiment_id, f"Physics Experiment: {experiment_id}")
    return (
        title,
        "Physics Laboratory",
        ["PASCO 850 Universal Interface", "Sensors and Lab Apparatus"],
        (
            "Automated experimental measurement and verification of theoretical "
            "physics relations."
        ),
        [],
        {},
        [
            "How do experimental uncertainties influence derived physical constants?",
            "What systematic physical effects cause deviations from ideal theory?",
        ],
    )


def _canonical_fallback_series(experiment_id: str) -> dict[str, list[float]]:
    active_series: dict[str, list[float]] = {}
    if experiment_id == "photoelectric_effect":
        freqs = [8.214e14, 7.402e14, 6.876e14, 5.490e14, 5.196e14]
        h_over_e = PLANCK_CONSTANT / ELEMENTARY_CHARGE
        phi = 1.85
        voltages = [h_over_e * f - phi for f in freqs]
        active_series["Frequency"] = freqs
        active_series["Stopping Voltage"] = voltages
    elif experiment_id == "rlc_resonance":
        frequencies = [50.0, 100.0, 150.0, 175.0, 200.0, 250.0, 300.0, 400.0, 500.0]
        f0_th = 175.8
        q_factor = 3.5
        voltages = [
            1.0
            / math.sqrt(
                1.0 + q_factor * q_factor * ((f / f0_th) - (f0_th / f)) ** 2,
            )
            for f in frequencies
        ]
        active_series["Frequency"] = frequencies
        active_series["Resistor Voltage"] = voltages
    elif experiment_id == "adiabatic_gas":
        volumes = [100.0, 90.0, 80.0, 70.0, 60.0, 50.0]
        pressures = [101.3 * ((100.0 / v) ** 1.40) for v in volumes]
        active_series["Volume"] = volumes
        active_series["Pressure"] = pressures
    elif experiment_id == "forced_harmonic_oscillation":
        frequencies = [0.5, 0.8, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8]
        amplitudes = [0.02, 0.05, 0.12, 0.28, 0.15, 0.09, 0.04, 0.02]
        active_series["Driver Frequency"] = frequencies
        active_series["Amplitude"] = amplitudes
    elif experiment_id == "slit_diffraction":
        positions = [-0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04]
        intensities = [0.05, 0.15, 0.35, 0.80, 1.0, 0.80, 0.35, 0.15, 0.05]
        active_series["Position"] = positions
        active_series["Light Intensity"] = intensities
    else:
        active_series["x"] = [1.0, 2.0, 3.0, 4.0, 5.0]
        active_series["y"] = [2.0, 4.0, 6.0, 8.0, 10.0]
    return active_series


def _analyze_constants(
    experiment_id: str,
    x_vals: list[float],
    y_vals: list[float],
    regression: RegressionSummary,
) -> list[ErrorAnalysisRow]:
    error_analysis: list[ErrorAnalysisRow] = []
    if experiment_id == "photoelectric_effect":
        exp_h = regression.slope * ELEMENTARY_CHARGE
        error_analysis.append(
            compute_error_analysis(
                accepted_value=PLANCK_CONSTANT,
                experimental_value=exp_h,
                parameter_name="Planck's Constant (h)",
                symbol="h",
                unit="J*s",
            ),
        )
        phi_ev = -regression.intercept
        error_analysis.append(
            compute_error_analysis(
                accepted_value=1.85,
                experimental_value=phi_ev,
                parameter_name="Cathode Work Function (phi)",
                symbol="phi",
                unit="eV",
            ),
        )
    elif experiment_id == "rlc_resonance":
        max_v = max(y_vals)
        max_idx = y_vals.index(max_v)
        peak_freq = x_vals[max_idx]
        f0_th = 175.8
        error_analysis.append(
            compute_error_analysis(
                accepted_value=f0_th,
                experimental_value=peak_freq,
                parameter_name="Resonant Frequency (f_0)",
                symbol="f_0",
                unit="Hz",
            ),
        )
    return error_analysis


def _fit_adiabatic(
    x_vals: list[float],
    y_vals: list[float],
) -> tuple[RegressionSummary, list[ErrorAnalysisRow], str]:
    ln_v = [math.log(v) for v in x_vals]
    ln_p = [math.log(p) for p in y_vals]
    reg = compute_linear_regression(
        ln_v,
        ln_p,
        variable_names=("ln(V)", "ln(P)"),
    )
    exp_gamma = -reg.slope
    errs = [
        compute_error_analysis(
            accepted_value=ADIABATIC_INDEX_AIR,
            experimental_value=exp_gamma,
            parameter_name="Adiabatic Index (gamma)",
            symbol="gamma",
            unit="",
        ),
    ]
    plot = generate_ascii_plot(
        ln_v,
        ln_p,
        fit=(reg.slope, reg.intercept),
        labels=("ln(V)", "ln(P)"),
    )
    return reg, errs, plot


def _fit_general(
    experiment_id: str,
    x_key: str,
    y_key: str,
    active_series: dict[str, list[float]],
    units_map: dict[str, str],
) -> tuple[RegressionSummary, list[ErrorAnalysisRow], str]:
    x_vals = active_series[x_key]
    y_vals = active_series[y_key]
    reg = compute_linear_regression(
        x_vals,
        y_vals,
        variable_names=(x_key, y_key),
        units=(units_map.get(x_key, ""), units_map.get(y_key, "")),
    )
    plot = generate_ascii_plot(
        x_vals,
        y_vals,
        fit=(reg.slope, reg.intercept),
        labels=(x_key, y_key),
    )
    errs = _analyze_constants(experiment_id, x_vals, y_vals, reg)
    return reg, errs, plot


def _compute_fit(
    experiment_id: str,
    active_series: dict[str, list[float]],
    units_map: dict[str, str],
) -> tuple[RegressionSummary | None, list[ErrorAnalysisRow], str]:
    series_keys = list(active_series.keys())
    if len(series_keys) < MIN_REGRESSION_POINTS:
        return None, [], ""

    x_key, y_key = series_keys[0], series_keys[1]
    x_vals, y_vals = active_series[x_key], active_series[y_key]
    if len(x_vals) < MIN_REGRESSION_POINTS or len(x_vals) != len(y_vals):
        return None, [], ""

    if (
        experiment_id == "adiabatic_gas"
        and all(v > 0 for v in x_vals)
        and all(p > 0 for p in y_vals)
    ):
        return _fit_adiabatic(x_vals, y_vals)

    return _fit_general(experiment_id, x_key, y_key, active_series, units_map)


def generate_report(
    file_path_or_run: str | None = None,
    experiment_id: str = "generic",
    *,
    data_series: dict[str, Sequence[float]] | None = None,
    title: str | None = None,
    apparatus: list[str] | None = None,
) -> LabReport:
    """Generate a complete, structured laboratory report with statistics."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    parsed_series, parsed_channels = _load_data_from_file_or_string(file_path_or_run)
    active_series: dict[str, list[float]] = {
        k: list(v) for k, v in parsed_series.items()
    }
    if data_series:
        for k, v in data_series.items():
            active_series[k] = list(v)

    (
        cur_title,
        cur_domain,
        cur_equip,
        cur_theory,
        cur_eqs,
        cur_channels,
        cur_questions,
    ) = _get_curriculum_info(experiment_id)

    final_title = title or cur_title
    final_apparatus = apparatus or cur_equip
    final_channels = {**cur_channels, **parsed_channels}

    if not active_series:
        active_series = _canonical_fallback_series(experiment_id)

    units_map = {
        "Frequency": "Hz",
        "Stopping Voltage": "V",
        "Resistor Voltage": "V",
        "Volume": "mL",
        "Pressure": "kPa",
        "Driver Frequency": "Hz",
        "Amplitude": "m",
        "Position": "m",
        "Light Intensity": "V",
        "x": "",
        "y": "",
    }
    data_summaries = [
        compute_data_summary(vals, name, units_map.get(name, ""))
        for name, vals in active_series.items()
    ]

    regression, error_analysis, ascii_plot = _compute_fit(
        experiment_id,
        active_series,
        units_map,
    )

    is_file = file_path_or_run and Path(file_path_or_run).is_file()
    run_name = file_path_or_run if file_path_or_run and not is_file else None

    metadata = ExperimentMetadata(
        experiment_id=experiment_id,
        title=final_title,
        date=now_str,
        apparatus=final_apparatus,
        domain=cur_domain,
        description=cur_theory,
        channels_or_sensors=final_channels,
        run_name=run_name,
    )

    conclusion = f"Experimental data for {final_title} was analyzed with OLS. "
    if regression and regression.r_squared is not None:
        conclusion += f"The fit achieved R^2 = {regression.r_squared:.4f}. "
    if error_analysis:
        primary = error_analysis[0]
        conclusion += (
            f"Derived {primary.parameter_name}: {primary.experimental_value:.3e} "
            f"(accepted: {primary.accepted_value:.3e} {primary.unit}, "
            f"error: {primary.relative_error_percent:.2f}%)."
        )

    return LabReport(
        metadata=metadata,
        theory_summary=cur_theory,
        governing_equations=cur_eqs,
        data_summaries=data_summaries,
        regression=regression,
        error_analysis=error_analysis,
        ascii_plot=ascii_plot,
        raw_data_points={k: list(v) for k, v in active_series.items()},
        discussion_questions=cur_questions,
        conclusion=conclusion,
    )
