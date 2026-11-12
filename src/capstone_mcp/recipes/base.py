# Copyright 2026 Capstone MCP contributors.
"""Base architecture and registry for experiment automation macro recipes."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, Field

from capstone_mcp.desktop import Capstone
from capstone_mcp.models import Model

RecipePhase = Literal["setup", "acquire", "analyze"]
RecipeAction = Literal["setup", "acquire", "analyze", "run"]


class RecipePhaseResult(Model):
    """Result of an individual experiment phase (setup, acquire, or analyze)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    phase: str
    status: Literal["completed", "pending", "failed"] = "completed"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ExperimentMacroResult(Model):
    """Structured outcome returned by capstone_run_experiment_macro."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    success: bool
    experiment_id: str
    action: str
    phase_results: dict[str, RecipePhaseResult] = Field(default_factory=dict)
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ExperimentRecipe(ABC):
    """Abstract base class defining the three-phase experiment recipe lifecycle."""

    experiment_id: str
    title: str
    description: str

    @abstractmethod
    def setup(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Configure hardware, sensors, displays, and sampling conditions."""

    @abstractmethod
    def acquire(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Drive excitation or guidance and collect experimental data samples."""

    @abstractmethod
    def analyze(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> RecipePhaseResult:
        """Perform numerical fitting, peak detection, and error calculations."""

    def run(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> ExperimentMacroResult:
        """Execute setup, acquire, and analyze phases sequentially."""
        params = dict(parameters or {})
        phase_results: dict[str, RecipePhaseResult] = {}

        # 1. Setup Phase
        setup_res = self.setup(params, app=app)
        phase_results["setup"] = setup_res
        if setup_res.status == "failed":
            return ExperimentMacroResult(
                success=False,
                experiment_id=self.experiment_id,
                action="run",
                phase_results=phase_results,
                summary=f"Setup phase failed: {setup_res.message}",
                error=setup_res.message,
            )

        # 2. Acquire Phase
        acquire_res = self.acquire(params, app=app)
        phase_results["acquire"] = acquire_res
        if acquire_res.status == "failed":
            return ExperimentMacroResult(
                success=False,
                experiment_id=self.experiment_id,
                action="run",
                phase_results=phase_results,
                summary=f"Acquisition phase failed: {acquire_res.message}",
                error=acquire_res.message,
            )

        # Merge acquired dataset into params if not already provided
        acquired_data = acquire_res.details.get("data")
        if acquired_data and isinstance(acquired_data, dict):
            for k, v in acquired_data.items():
                if k not in params:
                    params[k] = v

        # 3. Analyze Phase
        analyze_res = self.analyze(params)
        phase_results["analyze"] = analyze_res
        if analyze_res.status == "failed":
            return ExperimentMacroResult(
                success=False,
                experiment_id=self.experiment_id,
                action="run",
                phase_results=phase_results,
                summary=f"Analysis phase failed: {analyze_res.message}",
                error=analyze_res.message,
            )

        summary = (
            f"Successfully executed macro recipe for '{self.title}'. "
            f"Analysis: {analyze_res.message}"
        )
        combined_data: dict[str, Any] = {
            "setup": setup_res.details,
            "acquisition": acquire_res.details,
            "analysis": analyze_res.details,
        }
        return ExperimentMacroResult(
            success=True,
            experiment_id=self.experiment_id,
            action="run",
            phase_results=phase_results,
            summary=summary,
            data=combined_data,
        )


class RecipeRegistry:
    """Registry maintaining active experiment automation recipes."""

    def __init__(self) -> None:
        """Initialize empty registry mappings."""
        self._recipes: dict[str, ExperimentRecipe] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        recipe: ExperimentRecipe,
        aliases: list[str] | None = None,
    ) -> None:
        """Register a recipe instance with optional name aliases."""
        self._recipes[recipe.experiment_id] = recipe
        if aliases:
            for alias in aliases:
                self._aliases[alias] = recipe.experiment_id

    def get(self, experiment_id: str) -> ExperimentRecipe:
        """Retrieve a registered recipe by ID or alias."""
        target_id = self._aliases.get(experiment_id, experiment_id)
        if target_id not in self._recipes:
            all_ids = list(self._recipes.keys()) + list(self._aliases.keys())
            available = sorted(set(all_ids))
            msg = (
                f"Unknown experiment recipe: '{experiment_id}'. "
                f"Available recipes: {available}"
            )
            raise KeyError(msg)
        return self._recipes[target_id]

    def list_all(self) -> list[dict[str, str]]:
        """Return metadata list of all registered experiment recipes."""
        return [
            {
                "experiment_id": r.experiment_id,
                "title": r.title,
                "description": r.description,
            }
            for r in self._recipes.values()
        ]


REGISTRY = RecipeRegistry()


def register_recipe(
    recipe: ExperimentRecipe,
    aliases: list[str] | None = None,
) -> None:
    """Register an experiment recipe in the global registry."""
    REGISTRY.register(recipe, aliases=aliases)


def get_recipe(experiment_id: str) -> ExperimentRecipe:
    """Get an experiment recipe from the global registry."""
    return REGISTRY.get(experiment_id)


def list_recipes() -> list[dict[str, str]]:
    """List all registered experiment recipes."""
    return REGISTRY.list_all()


def run_experiment_macro(
    experiment_id: str,
    action: str = "run",
    parameters: dict[str, Any] | None = None,
    app: Capstone | None = None,
) -> ExperimentMacroResult:
    """Execute a single phase or full macro workflow for an experiment."""
    recipe = get_recipe(experiment_id)
    normalized_action = action.strip().lower()
    params = dict(parameters or {})

    if normalized_action == "run":
        return recipe.run(params, app=app)

    if normalized_action == "setup":
        res = recipe.setup(params, app=app)
        return ExperimentMacroResult(
            success=res.status != "failed",
            experiment_id=recipe.experiment_id,
            action="setup",
            phase_results={"setup": res},
            summary=res.message,
            data=res.details,
            error=res.message if res.status == "failed" else None,
        )

    if normalized_action == "acquire":
        res = recipe.acquire(params, app=app)
        return ExperimentMacroResult(
            success=res.status != "failed",
            experiment_id=recipe.experiment_id,
            action="acquire",
            phase_results={"acquire": res},
            summary=res.message,
            data=res.details,
            error=res.message if res.status == "failed" else None,
        )

    if normalized_action == "analyze":
        res = recipe.analyze(params)
        return ExperimentMacroResult(
            success=res.status != "failed",
            experiment_id=recipe.experiment_id,
            action="analyze",
            phase_results={"analyze": res},
            summary=res.message,
            data=res.details,
            error=res.message if res.status == "failed" else None,
        )

    msg = (
        f"Unsupported action '{action}'. "
        "Allowed actions are 'setup', 'acquire', 'analyze', or 'run'."
    )
    raise ValueError(msg)
