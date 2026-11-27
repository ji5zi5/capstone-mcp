# Copyright 2026 Capstone MCP contributors.
"""Unit and integration tests for Phase 2-3 numerics, recipes, and reports."""

from __future__ import annotations

import math

import pytest

from capstone_mcp.analysis import FitInput, _sample_cooks_distance, linear_fit
from capstone_mcp.recipes import get_recipe
from capstone_mcp.recipes.adiabatic_gas import AdiabaticGasRecipe
from capstone_mcp.recipes.polarization import PolarizationRecipe, fit_malus_law
from capstone_mcp.recipes.slit_diffraction import SlitDiffractionRecipe
from capstone_mcp.reports import generate_report, render_markdown


def test_cooks_distance_zero_variance_and_unit_leverage_safe() -> None:
    fit = linear_fit(FitInput(x=[1.0, 2.0, 3.0, 4.0], y=[3.0, 5.0, 7.0, 9.0]))
    assert fit.slope == pytest.approx(2.0)
    assert fit.r_squared == pytest.approx(1.0)
    assert all(dist is None for dist in fit.diagnostics.cooks_distance)
    assert _sample_cooks_distance(1e200, 1.0, 1.0 - 1e-13) is None
    assert _sample_cooks_distance(1e200, 1e-200, 0.5) is None


def test_polarization_recipe_aliases_and_malus_law_fit() -> None:
    recipe = get_recipe("polarization")
    assert isinstance(recipe, PolarizationRecipe)
    assert get_recipe("malus") is recipe
    assert get_recipe("polarization_light") is recipe

    angles = [0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 140.0, 160.0]
    intensities = [
        2.5 + 85.0 * (math.cos(math.radians(theta - 35.0)) ** 2)
        for theta in angles
    ]
    acq = recipe.acquire({"angles_deg": angles, "intensities": intensities})
    assert acq.status == "completed"

    res = recipe.analyze(acq.details)
    assert res.status == "completed"
    assert res.details["max_intensity"] == pytest.approx(85.0, abs=1e-4)
    assert res.details["background_intensity"] == pytest.approx(2.5, abs=1e-4)
    assert res.details["axis_offset_deg"] == pytest.approx(35.0, abs=1e-3)
    assert res.details["r_squared"] == pytest.approx(1.0, abs=1e-6)


def test_polarization_fit_rejects_degenerate_angles() -> None:
    with pytest.raises(ValueError, match="linearly independent"):
        fit_malus_law([0.0, 180.0, 360.0, 540.0], [10.0, 10.0, 10.0, 10.0])

    fail = PolarizationRecipe().analyze(
        {"angles_deg": [0.0, 45.0, 90.0], "intensities": [1.0, 0.5, 0.0]},
    )
    assert fail.status == "failed"


def test_polarization_report_generation_and_markdown() -> None:
    sample_report = generate_report(file_path_or_run="sample", experiment_id="polarization")
    assert sample_report.metadata.experiment_id == "polarization"
    assert sample_report.regression is not None
    assert sample_report.regression.slope == pytest.approx(100.0, abs=1e-3)
    assert sample_report.regression.intercept == pytest.approx(2.0, abs=1e-3)
    assert sample_report.regression.r_squared == pytest.approx(1.0, abs=1e-6)
    md = render_markdown(sample_report)
    assert "Malus" in md


def test_adiabatic_weighted_log_reduces_low_pressure_bias() -> None:
    # True P * V^1.40 = const, with additive pressure offset perturbing low-P point
    volumes = [20.0, 30.0, 40.0, 60.0, 90.0, 120.0]
    true_pressures = [250.0 * ((20.0 / v) ** 1.40) for v in volumes]
    perturbed = [*true_pressures[:-1], true_pressures[-1] + 4.0]

    ols_res = AdiabaticGasRecipe().analyze({
        "pressure_kpa": perturbed,
        "volume_cm3": volumes,
        "fit_method": "ols_log",
    })
    weighted_res = AdiabaticGasRecipe().analyze({
        "pressure_kpa": perturbed,
        "volume_cm3": volumes,
        "fit_method": "weighted_log",
        "pressure_uncertainty_kpa": 0.5,
    })
    assert ols_res.status == "completed"
    assert weighted_res.status == "completed"
    ols_err = abs(ols_res.details["adiabatic_index_gamma_exp"] - 1.40)
    w_err = abs(weighted_res.details["adiabatic_index_gamma_exp"] - 1.40)
    assert w_err < ols_err


def test_adiabatic_gamma_stability_and_sub_isothermal_handling() -> None:
    neg_res = AdiabaticGasRecipe().analyze({
        "pressure_kpa": [100.0, 115.0, 130.0, 150.0],
        "volume_cm3": [20.0, 30.0, 40.0, 50.0],
    })
    assert neg_res.status == "failed"
    assert "nonpositive" in neg_res.message

    sub_isothermal = {
        "pressure_kpa": [100.0, 120.0, 150.0, 200.0],
        "volume_cm3": [50.0, 40.0, 30.0, 20.0],
    }
    soft = AdiabaticGasRecipe().analyze(sub_isothermal)
    assert soft.status == "completed"
    assert soft.details["gamma_fit_status"] == "rejected_sub_isothermal"
    assert "adiabatic_index_gamma_exp" not in soft.details
    assert soft.details["polytropic_exponent_n"] < 1.0

    strict = AdiabaticGasRecipe().analyze({**sub_isothermal, "strict_adiabatic": True})
    assert strict.status == "failed"
    assert "gamma >= 1.0" in strict.message


def test_adiabatic_report_rejects_unphysical_gamma() -> None:
    with pytest.raises(ValueError, match=r"gamma >= 1\.0"):
        generate_report(
            experiment_id="adiabatic_gas",
            data_series={
                "Volume": [50.0, 40.0, 30.0, 20.0],
                "Pressure": [100.0, 120.0, 150.0, 200.0],
            },
        )


def test_adiabatic_multi_cycle_strokes_orientation_and_temperature() -> None:
    # Closed heat engine loop (clockwise in P-V: top expansion > bottom compression)
    volumes = [20.0, 40.0, 60.0, 80.0, 60.0, 40.0, 20.0]
    pressures = [220.0, 120.0, 85.0, 65.0, 55.0, 95.0, 220.0]
    temps_k = [420.0, 318.0, 270.0, 241.0, 225.0, 278.0, 420.0]

    cw = AdiabaticGasRecipe().analyze({
        "pressure_kpa": pressures,
        "volume_cm3": volumes,
        "temperatures_k": temps_k,
        "moles": 0.01,
    })
    assert cw.status == "completed"
    assert cw.details["cycle_orientation"] == "clockwise_heat_engine"
    assert cw.details["cyclic_work_joules"] > 0
    assert cw.details["gamma_fit_status"] == "requires_single_stroke"
    strokes = cw.details["strokes"]
    assert len(strokes) == 2
    assert strokes[0]["stroke_type"] == "expansion"
    assert strokes[1]["stroke_type"] == "compression"
    assert cw.details["temperature_analysis"]["temp_min_k"] == pytest.approx(225.0)
    assert cw.details["temperature_analysis"]["internal_energy_change_joules"] == 0.0

    # Reversed orientation is counterclockwise
    ccw = AdiabaticGasRecipe().analyze({
        "pressure_kpa": list(reversed(pressures)),
        "volume_cm3": list(reversed(volumes)),
    })
    assert ccw.status == "completed"
    assert ccw.details["cycle_orientation"] == "counterclockwise_refrigerator_or_loss"
    assert ccw.details["cyclic_work_joules"] < 0


def test_single_slit_subpixel_multi_order_and_gum_uncertainty() -> None:
    # Simulate clean Fraunhofer single slit a=0.05 mm, lambda=650 nm, L=1.0 m
    # First minimum at 13.0 mm (between 12 mm and 14 mm grid points), 2nd at 26.0 mm
    wavelength = 650e-9
    distance = 1.0
    a_true = 0.05e-3
    positions = [float(x) for x in range(-32, 33, 2)]
    intensities: list[float] = []
    for x_mm in positions:
        sin_t = (x_mm * 1e-3) / math.hypot(distance, x_mm * 1e-3)
        beta = math.pi * a_true * sin_t / wavelength
        val = 1.0 if abs(beta) < 1e-9 else (math.sin(beta) / beta) ** 2
        intensities.append(val)

    discrete = SlitDiffractionRecipe().analyze({
        "positions_mm": positions,
        "intensities": intensities,
        "wavelength_m": wavelength,
        "screen_distance_m": distance,
    })
    assert discrete.status == "completed"
    assert "multi_order_fit" in discrete.details
    assert discrete.details["multi_order_fit"]["orders_used"] == [1, 2]
    assert "subpixel_refinement" in discrete.details
    sub_width = discrete.details["subpixel_refinement"]["derived_slit_width_mm"]
    assert abs(sub_width - 0.05) <= abs(
        discrete.details["derived_slit_width_mm"] - 0.05,
    )

    refined = SlitDiffractionRecipe().analyze({
        "positions_mm": positions,
        "intensities": intensities,
        "wavelength_m": wavelength,
        "screen_distance_m": distance,
        "subpixel_interpolation": True,
        "wavelength_uncertainty_m": 1.0e-9,
        "screen_distance_uncertainty_m": 0.005,
    })
    assert refined.details["derived_slit_width_mm"] == sub_width
    unc = refined.details["uncertainty"]
    assert unc["coverage_factor"] == 2.0
    assert unc["expanded_uncertainty_95_mm"] == pytest.approx(
        2.0 * unc["standard_uncertainty_mm"], rel=1e-4,
    )
    assert unc["components"]["wavelength_rel"] > 0


def test_double_slit_missing_order_recovery_and_fringe_statistics() -> None:
    # Physical missing-order pattern: d = 0.325 mm (spacing 2.0 mm), a = d/2 = 0.1625 mm
    # First single-slit minimum at 4.0 mm suppresses m = +-2 orders at +-4.0 mm.
    wl = 650e-9
    dist = 1.0
    d_sep = 0.325e-3
    a_width = d_sep / 2.0
    positions = [x * 0.5 for x in range(-18, 19)]
    intensities: list[float] = []
    for x_mm in positions:
        sin_t = (x_mm * 1e-3) / math.hypot(dist, x_mm * 1e-3)
        beta = math.pi * a_width * sin_t / wl
        env = 1.0 if abs(beta) < 1e-9 else (math.sin(beta) / beta) ** 2
        alpha = math.pi * d_sep * sin_t / wl
        intensities.append(5.0 * env * (math.cos(alpha) ** 2))

    res = SlitDiffractionRecipe().analyze({
        "positions_mm": positions,
        "intensities": intensities,
        "slit_type": "double_slit",
        "wavelength_m": 650e-9,
        "screen_distance_m": 1.0,
        "min_prominence_ratio": 0.02,
    })
    assert res.status == "completed"
    assert res.details["derived_slit_separation_mm"] == pytest.approx(0.325, rel=1e-2)
    stats = res.details["fringe_statistics"]
    assert stats["missing_order_gaps_detected"] is True
    assert stats["fringe_count"] == 6
    assert res.details["uncertainty"]["coverage_factor"] == 2.0
