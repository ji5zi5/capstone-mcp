# Copyright 2026 Capstone MCP contributors.
"""Native-free requests and verified outcomes for graph analysis."""

from typing import ClassVar, Literal, Self

from pydantic import ConfigDict, Field, computed_field, model_validator

from capstone_mcp.graph_state import FitModel, GraphState
from capstone_mcp.models import Model, Point


class GraphRequest(Model):
    """Reject misspelled request keys instead of silently dropping instructions."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class GraphFitRequest(GraphRequest):
    """Set the exact selected model set on the currently selected native graph."""

    menu_point: Point = Field(description=(
        "Dropdown arrow in a fresh client-area screenshot, at original pixel scale."
    ))
    models: list[FitModel] = Field(description=(
        "Exact desired model set. Unlisted existing models are removed; [] removes all."
    ))
    master_point: Point | None = Field(default=None, description=(
        "Fit icon beside the dropdown; required when fit_enabled is false."
    ))
    allow_foreground: bool = True
    expected_data_signature: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$",
        description="Copy read_graph.data_signature to reject changed data bindings.",
    )

    @model_validator(mode="after")
    def unique_models(self) -> Self:
        """Reject duplicate model names before any application input."""
        if len(self.models) != len(set(self.models)):
            msg = "Choose each fitting model only once."
            raise ValueError(msg)
        return self


class GraphFitOutcome(Model):
    """Native configuration confirmation, distinct from numerical fit success."""

    changed: bool
    requested_models: list[FitModel]
    fits_successful: bool
    before: GraphState
    after: GraphState

    @computed_field
    @property
    def next_action(self) -> Literal[
        "inspect_graph", "inspect_fit_status", "no_fits_requested",
    ]:
        """Keep configured selection distinct from successful numerical analysis."""
        if not self.requested_models:
            return "no_fits_requested"
        return "inspect_graph" if self.fits_successful else "inspect_fit_status"


class GraphAxisRequest(GraphRequest):
    """A current screenshot anchor and the exact native measurement menu path."""

    point: Point
    menu_path: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def nonempty_labels(self) -> Self:
        """Refuse empty labels instead of selecting an unnamed menu item."""
        if any(not name for name in self.menu_path):
            msg = "Measurement menu labels must not be empty."
            raise ValueError(msg)
        return self


class GraphAnalysisRequest(GraphRequest):
    """Configure observed axes, then apply and read native fitting models."""

    fitting: GraphFitRequest
    x: GraphAxisRequest | None = None
    y: GraphAxisRequest | None = None
