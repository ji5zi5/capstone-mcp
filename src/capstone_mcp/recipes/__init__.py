# Copyright 2026 Capstone MCP contributors.
"""Physics Experiment Automation Macro Engine recipes."""

from capstone_mcp.recipes.adiabatic_gas import AdiabaticGasRecipe
from capstone_mcp.recipes.base import (
    REGISTRY,
    ExperimentMacroResult,
    ExperimentRecipe,
    RecipeAction,
    RecipePhase,
    RecipePhaseResult,
    RecipeRegistry,
    get_recipe,
    list_recipes,
    register_recipe,
    run_experiment_macro,
)
from capstone_mcp.recipes.forced_oscillation import ForcedOscillationRecipe
from capstone_mcp.recipes.photoelectric import PhotoelectricEffectRecipe
from capstone_mcp.recipes.rlc_resonance import RLCResonanceRecipe
from capstone_mcp.recipes.slit_diffraction import SlitDiffractionRecipe

# Register the 5 canonical physics experiment recipes
register_recipe(
    PhotoelectricEffectRecipe(),
    aliases=["photoelectric", "photoelectric_effect"],
)
register_recipe(
    RLCResonanceRecipe(),
    aliases=["rlc", "rlc_resonance"],
)
register_recipe(
    ForcedOscillationRecipe(),
    aliases=["forced_oscillation", "forced_harmonic_oscillation"],
)
register_recipe(
    AdiabaticGasRecipe(),
    aliases=["adiabatic", "adiabatic_gas", "heat_engine"],
)
register_recipe(
    SlitDiffractionRecipe(),
    aliases=["slit", "slit_diffraction", "diffraction"],
)

__all__ = [
    "REGISTRY",
    "AdiabaticGasRecipe",
    "ExperimentMacroResult",
    "ExperimentRecipe",
    "ForcedOscillationRecipe",
    "PhotoelectricEffectRecipe",
    "RLCResonanceRecipe",
    "RecipeAction",
    "RecipePhase",
    "RecipePhaseResult",
    "RecipeRegistry",
    "SlitDiffractionRecipe",
    "get_recipe",
    "list_recipes",
    "register_recipe",
    "run_experiment_macro",
]
