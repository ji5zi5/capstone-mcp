# Copyright 2026 Capstone MCP contributors.
"""Comprehensive unit and integration tests for Experiment Automation Macro Engine."""

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


def test_photoelectric_setup_phase() -> None:
    """Verify Photoelectric Effect setup phase hardware configuration."""
    recipe = PhotoelectricEffectRecipe()
    res = recipe.setup()
    assert res.phase == "setup"
    assert res.status == "completed"
    assert "wavelengths_nm" in res.details
    assert len(res.details["wavelengths_nm"]) == 5
    assert res.details["sampling_mode"] == "keep_sample"
    assert "DC Current Amplifier" in res.details["channels"]["analog_a"]
    assert "DC Power Supply" in res.details["channels"]["analog_b"]


def test_photoelectric_acquire_phase_simulation() -> None:
    """Verify Photoelectric Effect acquisition phase with simulated lines."""
    recipe = PhotoelectricEffectRecipe()
    res = recipe.acquire()
    assert res.phase == "acquire"
    assert res.status == "completed"
    assert res.details["sample_count"] == 5
    data = res.details["data"]
    assert len(data["frequencies_hz"]) == 5
    assert len(data["stopping_voltages_v"]) == 5
    # Shorter wavelength (higher frequency) should require higher stopping voltage
    assert data["stopping_voltages_v"][0] > data["stopping_voltages_v"][-1]


def test_photoelectric_analyze_h_over_e_fit() -> None:
    """Verify Planck's constant extraction and linear fit convergence."""
    recipe = PhotoelectricEffectRecipe()
    acquire_res = recipe.acquire()
    res = recipe.analyze(acquire_res.details)

    assert res.phase == "analyze"
    assert res.status == "completed"
    det = res.details

    # Physical convergence checks (Planck's constant order ~10^-34 J*s)
    h_exp = det["planck_constant_exp_js"]
    assert 6.0e-34 < h_exp < 7.2e-34
    assert det["planck_constant_error_pct"] < 5.0  # within 5% of theoretical

    # Work function and cutoff frequency
    assert 1.5 < det["work_function_ev"] < 2.5
    assert det["cutoff_frequency_hz"] > 0
    assert 400 < det["cutoff_wavelength_nm"] < 800
    assert det["r_squared"] > 0.98


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


def test_photoelectric_run_end_to_end() -> None:
    """Verify full end-to-end execution of PhotoelectricEffectRecipe."""
    macro_res = run_experiment_macro("photoelectric_effect", action="run")
    assert macro_res.success is True
    assert "setup" in macro_res.phase_results
    assert "acquire" in macro_res.phase_results
    assert "analyze" in macro_res.phase_results
    assert "Planck's constant" in macro_res.summary


# ---------------------------------------------------------------------------
# 2. RLCResonanceRecipe Tests
# ---------------------------------------------------------------------------


def test_rlc_resonance_setup_phase() -> None:
    """Verify RLC resonance setup phase configuration."""
    recipe = RLCResonanceRecipe()
    res = recipe.setup()
    assert res.phase == "setup"
    assert res.status == "completed"
    sg = res.details["signal_generator"]
    assert sg["sweep_start_hz"] == 10.0
    assert sg["sweep_stop_hz"] == 10000.0
    assert sg["waveform"] == "Sine"
    assert "Scope" in res.details["displays"]
    assert "FFT Spectrum" in res.details["displays"]


def test_rlc_resonance_acquire_and_analyze() -> None:
    """Verify RLC resonance frequency sweep acquisition and Q factor analysis."""
    recipe = RLCResonanceRecipe()
    acquire_res = recipe.acquire()
    assert acquire_res.status == "completed"
    assert acquire_res.details["sweep_points"] >= 80

    res = recipe.analyze(acquire_res.details)
    assert res.status == "completed"
    det = res.details

    # Resonant frequency for L=8.2mH, C=10uF: f0 ~ 556.1 Hz
    assert 540.0 < det["resonant_frequency_exp_hz"] < 575.0
    assert det["resonant_frequency_error_pct"] < 3.0

    # Quality factor Q = (1/R)*sqrt(L/C) ~ 2.86
    assert 2.0 < det["q_factor_exp"] < 4.0
    assert det["bandwidth_hz"] > 0
    f0 = det["resonant_frequency_exp_hz"]
    assert det["f1_lower_cutoff_hz"] < f0 < det["f2_upper_cutoff_hz"]


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


def test_rlc_resonance_run_end_to_end() -> None:
    """Verify full end-to-end execution of RLCResonanceRecipe."""
    macro_res = run_experiment_macro("rlc_resonance", action="run")
    assert macro_res.success is True
    assert "Resonance f_0" in macro_res.summary


# ---------------------------------------------------------------------------
# 3. ForcedOscillationRecipe Tests
# ---------------------------------------------------------------------------


def test_forced_oscillation_setup_phase() -> None:
    """Verify Forced Oscillation setup parameters (100Hz position, 480s stop)."""
    recipe = ForcedOscillationRecipe()
    res = recipe.setup()
    assert res.phase == "setup"
    assert res.status == "completed"
    assert res.details["sensors"]["smart_cart_position_rate_hz"] == 100.0
    assert res.details["recording_condition"]["duration_s"] == 480.0
    assert res.details["recording_condition"]["condition_type"] == "time_duration"


def test_forced_oscillation_acquire_and_analyze() -> None:
    """Verify Forced Oscillation resonance curve peak and damping extraction."""
    recipe = ForcedOscillationRecipe()
    acquire_res = recipe.acquire()
    assert acquire_res.status == "completed"
    assert acquire_res.details["frequencies_count"] >= 30

    res = recipe.analyze(acquire_res.details)
    assert res.status == "completed"
    det = res.details

    # Natural frequency f0 = sqrt(k/m) / (2*pi) ~ 1.007 Hz
    assert 0.90 < det["resonant_frequency_hz"] < 1.15
    assert det["frequency_error_pct"] < 5.0
    assert det["max_amplitude_m"] > 0
    assert det["q_factor"] > 0
    assert det["damping_coefficient_b_ns_m"] > 0


def test_forced_oscillation_run_end_to_end() -> None:
    """Verify full end-to-end execution of ForcedOscillationRecipe."""
    macro_res = run_experiment_macro("forced_harmonic_oscillation", action="run")
    assert macro_res.success is True
    assert "Resonance peak f_res" in macro_res.summary


# ---------------------------------------------------------------------------
# 4. AdiabaticGasRecipe Tests
# ---------------------------------------------------------------------------


def test_adiabatic_gas_setup_phase() -> None:
    """Verify Adiabatic Gas setup parameters (1000Hz sampling, P vs V area tool)."""
    recipe = AdiabaticGasRecipe()
    res = recipe.setup()
    assert res.phase == "setup"
    assert res.status == "completed"
    assert res.details["sampling_rate_hz"] == 1000.0
    assert "Area Integral" in res.details["display"]


def test_adiabatic_gas_acquire_and_analyze_cyclic_work() -> None:
    """Verify 1000Hz sampling, cyclic work oint P dV, and gamma index fit."""
    recipe = AdiabaticGasRecipe()
    acquire_res = recipe.acquire()
    assert acquire_res.status == "completed"
    assert acquire_res.details["sample_count"] >= 100

    res = recipe.analyze(acquire_res.details)
    assert res.status == "completed"
    det = res.details

    # Positive clockwise work integration: oint P dV > 0
    assert det["cyclic_work_joules"] > 0.0
    assert det["cyclic_work_mj"] > 0.0

    # Adiabatic index gamma fit near 1.40 (diatomic air)
    assert 1.30 < det["adiabatic_index_gamma_exp"] < 1.50
    assert det["gamma_error_pct"] < 5.0
    assert det["compression_ratio"] > 1.5


def test_adiabatic_gas_user_data_cycle() -> None:
    """Verify area integration with a rectangular P-V cycle."""
    recipe = AdiabaticGasRecipe()
    # Simple rectangular cycle in (P in kPa, V in cm^3):
    # (100, 20) -> (200, 20) -> (200, 50) -> (100, 50) -> back to (100, 20)
    # Area = Delta P * Delta V = 100 kPa * 30 cm^3 = 3000 mJ = 3.0 J
    p_pts = [100.0, 200.0, 200.0, 100.0]
    v_pts = [20.0, 20.0, 50.0, 50.0]
    res = recipe.analyze({"pressure_kpa": p_pts, "volume_cm3": v_pts})
    assert res.status == "completed"
    assert abs(res.details["cyclic_work_joules"] - 3.0) < 1e-4
    assert abs(res.details["cyclic_work_mj"] - 3000.0) < 1e-1


def test_adiabatic_gas_run_end_to_end() -> None:
    """Verify full end-to-end execution of AdiabaticGasRecipe."""
    macro_res = run_experiment_macro("adiabatic_gas", action="run")
    assert macro_res.success is True
    assert "Cyclic Work oint P dV" in macro_res.summary


# ---------------------------------------------------------------------------
# 5. SlitDiffractionRecipe Tests
# ---------------------------------------------------------------------------


def test_slit_diffraction_setup_phase() -> None:
    """Verify Slit Diffraction setup parameters (optics bench, 650nm laser)."""
    recipe = SlitDiffractionRecipe()
    res = recipe.setup()
    assert res.phase == "setup"
    assert res.status == "completed"
    assert res.details["optics"]["wavelength_nm"] == 650.0
    assert res.details["optics"]["screen_distance_m"] == 1.0


def test_slit_diffraction_acquire_and_analyze_single_slit() -> None:
    """Verify single slit diffraction minima detection and slit width extraction."""
    recipe = SlitDiffractionRecipe()
    acquire_res = recipe.acquire({
        "slit_type": "single_slit",
        "slit_width_m": 4.0e-5,
    })
    assert acquire_res.status == "completed"
    assert acquire_res.details["points_count"] >= 100

    res = recipe.analyze(acquire_res.details)
    assert res.status == "completed"
    det = res.details

    # Central maximum at center
    assert abs(det["central_maximum"]["position_mm"]) < 1.0
    assert det["diffraction_minima_count"] >= 2

    # Slit width derivation near 0.04 mm
    derived_a_mm = det["derived_slit_width_mm"]
    assert 0.035 < derived_a_mm < 0.045
    assert det["slit_width_error_pct"] < 5.0


def test_slit_diffraction_acquire_and_analyze_double_slit() -> None:
    """Verify double slit interference fringes and slit separation derivation."""
    recipe = SlitDiffractionRecipe()
    acquire_res = recipe.acquire({
        "slit_type": "double_slit",
        "slit_width_m": 4.0e-5,
        "slit_separation_m": 2.5e-4,
    })
    assert acquire_res.status == "completed"

    res = recipe.analyze(acquire_res.details)
    assert res.status == "completed"
    det = res.details

    # Slit separation derivation near 0.25 mm
    assert "derived_slit_separation_mm" in det
    derived_d_mm = det["derived_slit_separation_mm"]
    assert 0.20 < derived_d_mm < 0.30
    assert det["slit_separation_error_pct"] < 10.0


def test_slit_diffraction_run_end_to_end() -> None:
    """Verify full end-to-end execution of SlitDiffractionRecipe."""
    macro_res = run_experiment_macro("slit_diffraction", action="run")
    assert macro_res.success is True
    assert "Slit width a" in macro_res.summary


# ---------------------------------------------------------------------------
# Server MCP Tool Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_capstone_run_experiment_macro_all_experiments() -> None:
    """Verify the FastMCP server tool across all 5 canonical recipes."""
    canonical_ids = [
        "photoelectric_effect",
        "rlc_resonance",
        "forced_harmonic_oscillation",
        "adiabatic_gas",
        "slit_diffraction",
    ]

    for exp_id in canonical_ids:
        # 1. Test setup action
        setup_result = await capstone_run_experiment_macro(
            experiment_id=exp_id,
            action="setup",
        )
        assert setup_result.success is True
        assert setup_result.action == "setup"
        assert "setup" in setup_result.phase_results

        # 2. Test acquire action
        acq_result = await capstone_run_experiment_macro(
            experiment_id=exp_id,
            action="acquire",
        )
        assert acq_result.success is True
        assert acq_result.action == "acquire"
        assert "acquire" in acq_result.phase_results

        # 3. Test analyze action
        ana_result = await capstone_run_experiment_macro(
            experiment_id=exp_id,
            action="analyze",
        )
        assert ana_result.success is True
        assert ana_result.action == "analyze"
        assert "analyze" in ana_result.phase_results

        # 4. Test run action (sequential 3 phases)
        run_result = await capstone_run_experiment_macro(
            experiment_id=exp_id,
            action="run",
        )
        assert run_result.success is True
        assert run_result.action == "run"
        assert len(run_result.phase_results) == 3
        assert len(run_result.summary) > 0


@pytest.mark.anyio
async def test_capstone_run_experiment_macro_unknown_exp_raises() -> None:
    """Verify FastMCP server tool raises KeyError on unknown experiment."""
    with pytest.raises(KeyError, match="Unknown experiment recipe"):
        await capstone_run_experiment_macro(experiment_id="nonexistent_phys_exp")
