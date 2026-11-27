# Copyright 2026 Capstone MCP contributors.
"""Comprehensive unit and integration tests for Experiment Automation Macro Engine."""

import math
from typing import Any

import pytest

from capstone_mcp.desktop import Capstone
from capstone_mcp.recipes import (
    AdiabaticGasRecipe,
    ExperimentRecipe,
    ForcedOscillationRecipe,
    PhotoelectricEffectRecipe,
    RecipeRegistry,
    RLCResonanceRecipe,
    SlitDiffractionRecipe,
    get_recipe,
    list_recipes,
    run_experiment_macro,
)
from capstone_mcp.recipes.base import RecipePhaseResult
from capstone_mcp.recipes.slit_diffraction import _find_local_extrema
from capstone_mcp.server import capstone_run_experiment_macro

# ---------------------------------------------------------------------------
# Registry and Base Engine Tests
# ---------------------------------------------------------------------------


def test_list_canonical_recipes() -> None:
    """Verify all 5 canonical physics experiment recipes are registered."""
    recipes = list_recipes()
    assert len(recipes) >= 5
    ids = {r["experiment_id"] for r in recipes}
    assert "photoelectric_effect" in ids
    assert "rlc_resonance" in ids
    assert "forced_harmonic_oscillation" in ids
    assert "adiabatic_gas" in ids
    assert "slit_diffraction" in ids


def test_get_recipe_by_id_and_aliases() -> None:
    """Verify retrieval of recipes via canonical IDs and convenient aliases."""
    photo = get_recipe("photoelectric_effect")
    assert isinstance(photo, PhotoelectricEffectRecipe)
    assert get_recipe("photoelectric") is photo

    rlc = get_recipe("rlc_resonance")
    assert isinstance(rlc, RLCResonanceRecipe)
    assert get_recipe("rlc") is rlc

    forced = get_recipe("forced_harmonic_oscillation")
    assert isinstance(forced, ForcedOscillationRecipe)
    assert get_recipe("forced_oscillation") is forced

    gas = get_recipe("adiabatic_gas")
    assert isinstance(gas, AdiabaticGasRecipe)
    assert get_recipe("adiabatic") is gas
    assert get_recipe("heat_engine") is gas

    slit = get_recipe("slit_diffraction")
    assert isinstance(slit, SlitDiffractionRecipe)
    assert get_recipe("slit") is slit


def test_get_recipe_unknown_raises_key_error() -> None:
    """Verify KeyError with informative listing when requesting unknown recipe."""
    with pytest.raises(KeyError, match="Unknown experiment recipe"):
        get_recipe("quantum_teleportation")


def test_run_experiment_macro_unknown_action_raises() -> None:
    """Verify ValueError when requesting unsupported macro action."""
    with pytest.raises(ValueError, match="Unsupported action"):
        run_experiment_macro("photoelectric_effect", action="teleport")


def test_custom_recipe_registry_isolation() -> None:
    """Verify isolation and custom registration in an independent RecipeRegistry."""
    registry = RecipeRegistry()
    assert len(registry.list_all()) == 0

    class DummyRecipe(ExperimentRecipe):
        experiment_id = "dummy_exp"
        title = "Dummy Test Recipe"
        description = "Test recipe"

        def setup(
            self,
            parameters: dict[str, Any] | None = None,
            app: Capstone | None = None,
        ) -> RecipePhaseResult:
            del parameters, app
            return RecipePhaseResult(phase="setup", message="Setup done")

        def acquire(
            self,
            parameters: dict[str, Any] | None = None,
            app: Capstone | None = None,
        ) -> RecipePhaseResult:
            del parameters, app
            return RecipePhaseResult(phase="acquire", message="Acquire done")

        def analyze(
            self,
            parameters: dict[str, Any] | None = None,
        ) -> RecipePhaseResult:
            del parameters
            return RecipePhaseResult(phase="analyze", message="Analyze done")

    registry.register(DummyRecipe(), aliases=["dummy"])
    assert len(registry.list_all()) == 1
    assert registry.get("dummy").title == "Dummy Test Recipe"


# ---------------------------------------------------------------------------
# 1. PhotoelectricEffectRecipe Tests
# ---------------------------------------------------------------------------


def test_photoelectric_analyze_user_supplied_data() -> None:
    """Verify Photoelectric analysis with explicit user data points."""
    recipe = PhotoelectricEffectRecipe()
    # 5 mercury lines: 365, 405, 436, 546, 577 nm
    params = {
        "wavelengths_nm": [365.0, 405.0, 436.0, 546.0, 577.0],
        "stopping_voltages_v": [1.45, 1.11, 0.89, 0.32, 0.20],
    }
    res = recipe.analyze(params)
    assert res.status == "completed"
    assert res.details["r_squared"] > 0.99
    assert abs(res.details["planck_constant_exp_js"] - 6.626e-34) < 5e-35


def test_photoelectric_insufficient_data_error() -> None:
    """Verify error reporting when fewer than 3 points provided."""
    recipe = PhotoelectricEffectRecipe()
    bad_params = {
        "wavelengths_nm": [365.0, 405.0],
        "stopping_voltages_v": [1.45, 1.11],
    }
    res = recipe.analyze(bad_params)
    assert res.status == "failed"
    assert "At least 3 data points required" in res.message


# ---------------------------------------------------------------------------
# 2. RLCResonanceRecipe Tests
# ---------------------------------------------------------------------------


def test_rlc_resonance_user_supplied_sweep() -> None:
    """Verify RLC resonance analysis with explicitly provided sweep data."""
    recipe = RLCResonanceRecipe()
    # Synthetic resonance curve centered at 500 Hz
    freqs = [100.0, 300.0, 450.0, 500.0, 550.0, 700.0, 1000.0]
    volts = [0.10, 0.45, 0.85, 1.00, 0.85, 0.45, 0.10]
    res = recipe.analyze({"frequencies_hz": freqs, "voltages_v": volts})
    assert res.status == "completed"
    assert res.details["resonant_frequency_exp_hz"] == 500.0
    assert res.details["peak_voltage_v"] == 1.00


# ---------------------------------------------------------------------------
# 3. ForcedOscillationRecipe Tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 4. AdiabaticGasRecipe Tests
# ---------------------------------------------------------------------------


def test_adiabatic_gas_user_data_cycle() -> None:
    """Verify area integration with a rectangular P-V cycle."""
    recipe = AdiabaticGasRecipe()
    # Simple rectangular cycle in (P in kPa, V in cm^3):
    # (100, 20) -> (200, 20) -> (200, 50) -> (100, 50) -> back to (100, 20)
    # Area = Delta P * Delta V = 100 kPa * 30 cm^3 = 3000 mJ = 3.0 J
    p_pts = [100.0, 200.0, 200.0, 100.0]
    v_pts = [20.0, 20.0, 50.0, 50.0]
    res = recipe.analyze({"pressure_kpa": p_pts, "volume_cm3": v_pts, "closed_cycle": True})
    assert res.status == "completed"
    assert abs(res.details["cyclic_work_joules"] - 3.0) < 1e-4
    assert abs(res.details["cyclic_work_mj"] - 3000.0) < 1e-1
    assert res.details["gamma_fit_status"] == "requires_single_stroke"
    assert "adiabatic_index_gamma_exp" not in res.details


def test_open_compression_integrates_only_measured_segments() -> None:
    result = AdiabaticGasRecipe().analyze({
        "pressure_kpa": [100, 120, 150, 200], "volume_cm3": [50, 40, 30, 20],
    })
    assert result.status == "completed"
    assert result.details["path_work_joules"] == pytest.approx(-4.2)
    assert "cyclic_work_joules" not in result.details


# ---------------------------------------------------------------------------
# 5. SlitDiffractionRecipe Tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Server MCP Tool Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_capstone_run_experiment_macro_unknown_exp_raises() -> None:
    """Verify FastMCP server tool raises KeyError on unknown experiment."""
    with pytest.raises(KeyError, match="Unknown experiment recipe"):
        await capstone_run_experiment_macro(experiment_id="nonexistent_phys_exp")


RECIPE_IDS = [r["experiment_id"] for r in list_recipes()]


@pytest.mark.parametrize("recipe_id", RECIPE_IDS)
@pytest.mark.parametrize("action", ["setup", "acquire", "analyze", "run"])
def test_recipes_without_measurements_never_claim_success(
    recipe_id: str, action: str,
) -> None:
    result = run_experiment_macro(recipe_id, action=action)
    assert result.success is False
    assert all(r.status == "failed" for r in result.phase_results.values())
    assert not result.data
    if action == "run":
        assert list(result.phase_results) == ["setup"]


@pytest.mark.anyio
@pytest.mark.parametrize("recipe_id", RECIPE_IDS)
async def test_mcp_recipe_no_data_fails(recipe_id: str) -> None:
    result = await capstone_run_experiment_macro(recipe_id, action="acquire")
    assert result.success is False
    assert "not implemented" in result.summary


@pytest.mark.parametrize("invalid", [0.0, -1.0, float("nan"), float("inf")])
def test_adiabatic_invalid_pressure_fails(invalid: float) -> None:
    result = AdiabaticGasRecipe().analyze(
        {
            "pressure_kpa": [100.0, invalid, 200.0, 250.0],
            "volume_cm3": [40.0, 30.0, 20.0, 10.0],
        },
    )
    assert result.status == "failed"
    assert "finite positive" in result.message
    assert not result.details


def test_adiabatic_constant_volume_does_not_return_theory() -> None:
    result = AdiabaticGasRecipe().analyze(
        {
            "pressure_kpa": [100.0, 150.0, 200.0, 250.0],
            "volume_cm3": [10.0] * 4,
        },
    )
    assert result.status == "failed"
    assert "distinct volumes" in result.message


@pytest.mark.parametrize("expanding", [False, True])
def test_adiabatic_measured_power_law(*, expanding: bool) -> None:
    volumes = [50.0, 40.0, 30.0, 20.0, 10.0]
    if expanding:
        volumes.reverse()
    pressures = [1000.0 / v**1.25 for v in volumes]
    result = AdiabaticGasRecipe().analyze(
        {"pressure_kpa": pressures, "volume_cm3": volumes},
    )
    assert result.status == "completed"
    assert result.details["adiabatic_index_gamma_exp"] == pytest.approx(1.25)
    assert result.details["gamma_error_pct"] > 0


def test_photoelectric_acquire_alias_is_caller_data() -> None:
    result = PhotoelectricEffectRecipe().acquire(
        {"stopping_voltages": [1.45, 1.11, 0.89, 0.32, 0.20]},
    )
    assert result.status == "completed"
    assert result.details["acquisition_mode"] == "user_provided"


def test_diffraction_without_minima_does_not_return_nominal_width() -> None:
    result = SlitDiffractionRecipe().analyze(
        {"positions_mm": [-2, -1, 0, 1, 2], "intensities": [1, 2, 3, 2, 1]},
    )
    assert result.status == "failed"
    assert "minimum" in result.message
    assert not result.details


def test_double_slit_does_not_misidentify_interference_minima() -> None:
    result = SlitDiffractionRecipe().analyze(
        {
            "slit_type": "double_slit",
            "positions_mm": [-2, -1, 0, 1, 2],
            "intensities": [2, 0, 3, 0, 2],
        },
    )
    assert result.status == "failed"
    assert "derived_slit_width_mm" not in result.details


def test_single_slit_first_minimum_uses_measured_angle() -> None:
    result = SlitDiffractionRecipe().analyze({
        "positions_mm": [-15, -10, -5, 0, 5, 10, 15],
        "intensities": [1, 0, 3, 5, 3, 0, 1],
        "screen_distance_m": 0.01, "wavelength_m": 1e-5,
    })
    assert result.status == "completed"
    assert result.details["derived_slit_width_mm"] == pytest.approx(0.0141)


def test_single_slit_input_units_match() -> None:
    recipe = SlitDiffractionRecipe()
    positions = [-20, -16.25, -8, 0, 8, 16.25, 20]
    intensity = [0.1, 0, 2, 5, 2, 0, 0.1]
    mm = recipe.analyze({"positions_mm": positions, "intensities": intensity})
    metres = recipe.analyze(
        {"positions_m": [x / 1000 for x in positions], "intensities": intensity},
    )
    assert mm.status == metres.status == "completed"
    assert mm.details == metres.details
    assert mm.details["derived_slit_width_mm"] == pytest.approx(0.04)
    assert "nominal_slit_width_mm" not in mm.details
    assert "slit_width_error_pct" not in mm.details
    with_nominal = {"positions_mm": positions, "intensities": intensity, "nominal_slit_width_m": 8e-5}
    assert recipe.analyze(with_nominal).details["slit_width_error_pct"] == pytest.approx(50, abs=0.1)
    assert recipe.analyze({**with_nominal, "nominal_slit_width_m": 0}).status == "failed"


@pytest.mark.parametrize(
    ("recipe_id", "parameters"),
    [
        ("adiabatic_gas", {"pressure_kpa": [], "volume_cm3": []}),
        (
            "forced_harmonic_oscillation",
            {"driver_frequencies_hz": [1], "amplitudes_m": []},
        ),
        ("rlc_resonance", {"frequencies_hz": [1], "voltages_v": [float("inf")]}),
        ("slit_diffraction", {"positions_mm": [0], "intensities": [float("nan")]}),
        ("photoelectric_effect", {"wavelengths_nm": [0], "stopping_voltages_v": [1]}),
    ],
)
def test_acquisition_rejects_invalid_supplied_data(
    recipe_id: str, parameters: dict[str, Any],
) -> None:
    assert get_recipe(recipe_id).acquire(parameters).status == "failed"


def test_forced_oscillation_uses_supplied_resonance_curve() -> None:
    result = ForcedOscillationRecipe().analyze({
        "driver_frequencies_hz": [0.4, 0.7, 0.9, 1.0, 1.1, 1.3, 1.6],
        "amplitudes_m": [0.01, 0.04, 0.08, 0.1, 0.08, 0.04, 0.01],
    })
    assert result.status == "completed"
    assert result.details["resonant_frequency_hz"] == 1.0
    assert result.details["q_factor"] > 0


def test_pending_setup_does_not_execute_later_phases(monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = get_recipe("photoelectric_effect")

    def pending_setup(parameters: dict[str, Any] | None = None, app: Capstone | None = None) -> RecipePhaseResult:
        del parameters, app
        return RecipePhaseResult(phase="setup", status="pending", message="Awaiting configuration")

    monkeypatch.setattr(recipe, "setup", pending_setup)
    result = run_experiment_macro("photoelectric_effect", action="run")
    assert result.success is False
    assert list(result.phase_results) == ["setup"]
    assert run_experiment_macro("photoelectric_effect", action="setup").success is False

@pytest.mark.parametrize(("recipe_id", "response_key"), [
    ("rlc_resonance", "voltages_v"),
    ("forced_harmonic_oscillation", "amplitudes_m"),
])
@pytest.mark.parametrize("response", [[1.0], [1.0, 2.0, float("nan"), 2.0, 1.0]])
def test_resonance_analysis_rejects_incomplete_or_nonfinite_data(
    recipe_id: str,
    response_key: str,
    response: list[float],
) -> None:
    result = get_recipe(recipe_id).analyze({
        "frequencies_hz": [1, 2, 3, 4, 5], response_key: response,
    })
    assert result.status == "failed"
    assert "matching finite" in result.message
def test_slit_separation_counts_spacing_through_central_fringe() -> None:
    result = SlitDiffractionRecipe().analyze({
        "positions_mm": list(range(-5, 6)),
        "intensities": [0, 2, 0, 3, 1, 5, 1, 3, 0, 2, 0],
        "slit_type": "double_slit",
    })
    assert result.status == "completed"
    assert "derived_slit_width_mm" not in result.details
    # The second-order fringe is 4 mm from center on a screen 1 m away.
    expected_mm = 2 * 650e-6 / math.sin(math.atan(4 / 1000))
    assert result.details["derived_slit_separation_mm"] == pytest.approx(expected_mm)


# ---------------------------------------------------------------------------
# Server MCP Tool Integration Tests
# ---------------------------------------------------------------------------


def test_diffraction_flat_maximum_uses_plateau_midpoint() -> None:
    result = SlitDiffractionRecipe().analyze({
        "positions_mm": [-4, -3, -2, -1, 0, 1, 2, 3, 4],
        "intensities": [0.2, 0, 2, 5, 5, 5, 2, 0, 0.2],
    })
    assert result.status == "completed"
    assert result.details["central_maximum"]["position_mm"] == 0


def test_diffraction_isolated_outer_spike_is_rejected() -> None:
    result = SlitDiffractionRecipe().analyze({
        "positions_mm": list(range(-6, 7)),
        "intensities": [0.1, 20, 0.1, 0, 2, 4, 5, 4, 2, 0, 0.1, 0.2, 0.1],
    })
    assert result.status == "failed"
    assert "spike" in result.message
    assert not result.details


def test_quantized_diffraction_profiles_have_only_two_sided_extrema() -> None:
    positions = [0.0, 1.0, 3.0, 4.0, 6.0, 8.0, 9.0, 10.0]
    levels = [0.0, 1.0, 1.0, 2.0, 2.0, 0.0, 0.0, 1.0]
    assert _find_local_extrema(positions, levels) == ([(5.0, 2.0)], [(8.5, 0.0)])
    assert _find_local_extrema(positions[:4], [0.0, 1.0, 1.0, 1.0]) == ([], [])
