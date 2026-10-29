# Copyright 2026 Capstone MCP contributors.
"""Native-free requests and verified outcomes for graph analysis."""

from typing import Self

from pydantic import Field, model_validator

from capstone_mcp.graph_state import FitModel, GraphState
from capstone_mcp.models import Model, Point


class GraphFitRequest(Model):
    """Set the exact selected model set on the currently selected native graph."""

    menu_point: Point
    models: list[FitModel]
    master_point: Point | None = None
    allow_foreground: bool = True

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


class GraphAxisRequest(Model):
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


class GraphAnalysisRequest(Model):
    """Configure observed axes, then apply and read native fitting models."""

    fitting: GraphFitRequest
    x: GraphAxisRequest | None = None
    y: GraphAxisRequest | None = None
