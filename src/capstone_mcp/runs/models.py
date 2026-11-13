# Copyright 2026 Capstone MCP contributors.
"""Data models for unified run management in Capstone."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from capstone_mcp.analysis import (
    AnalysisError,
    LinearFit,
    RunComparison,
)
from capstone_mcp.file_workflows import FileArtifact
from capstone_mcp.models import Model


class RunAction(StrEnum):
    """Supported operations on experimental runs."""

    RENAME = "rename"
    DELETE = "delete"
    SET_VISIBILITY = "set_visibility"
    CAPTURE = "capture"


# ---------------------------------------------------------------------------
# Rename Models
# ---------------------------------------------------------------------------


class RenameRunRequest(Model):
    """Specification of target run and replacement title."""

    old_name: str
    new_name: str
    handle: int = 0
    allow_foreground: bool = True


class RenameRunResult(Model):
    """Confirmation of verified run renaming."""

    old_name: str
    new_name: str
    verified: bool
    detail: str


# ---------------------------------------------------------------------------
# Delete Models
# ---------------------------------------------------------------------------


class DeleteRunRequest(Model):
    """Specification of target run to delete."""

    run_name: str = "last_run"
    handle: int = 0
    allow_foreground: bool = True


class DeleteRunResult(Model):
    """Confirmation of verified run deletion."""

    deleted_run: str
    verified: bool
    detail: str


# ---------------------------------------------------------------------------
# Visibility Models
# ---------------------------------------------------------------------------


class SetRunVisibilityRequest(Model):
    """Specification for run visibility toggling on displays."""

    runs: list[str]
    visible: bool = True
    target_displays: list[str] | None = None
    handle: int = 0
    allow_foreground: bool = True


class SetRunVisibilityResult(Model):
    """Outcome of run visibility adjustment."""

    visible_runs: list[str]
    target_displays: list[str]
    detail: str
    verified: bool = True


# ---------------------------------------------------------------------------
# Capture Models
# ---------------------------------------------------------------------------


class CaptureError(AnalysisError):
    """A saved cycle cannot be attributed or analyzed without guessing."""


class SourceFit(Model):
    """Explicit measurement source IDs remain stable while run dataset IDs change."""

    x_source_euid: str = Field(min_length=1)
    y_source_euid: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_sources(self) -> Self:
        """Reject a self-fit before starting acquisition."""
        if self.x_source_euid == self.y_source_euid:
            msg = "Select different x and y measurement sources."
            raise ValueError(msg)
        return self


class CapturePlan(Model):
    """Use an empty output directory; optionally fit every captured cycle."""

    directory: str = Field(min_length=1)
    fit: SourceFit | None = None


class DatasetChange(Model):
    """A saved dataset change; replacements have no claimed new-sample slice."""

    dataset_index: int
    dataset_id: str
    source_euid: str | None
    source_name: str | None
    unit_id: int | None
    kind: Literal["created", "appended", "replaced"]
    sample_start: int | None
    sample_count: int
    new_sample_count: int | None


class CapturedFit(Model):
    """A fit of only the newly attributed samples, not a previous run's data."""

    x: DatasetChange
    y: DatasetChange
    result: LinearFit


class DatasetIdentity(Model):
    """An unchanging identity key for a series across multiple runs."""

    euid: str
    name: str


class CapturedRun(Model):
    """One stopped cycle's saved artifact, changes, and optional analysis."""

    ordinal: int
    interrupted: bool
    artifact: FileArtifact
    datasets: list[DatasetChange]
    removed_datasets: list[DatasetIdentity]
    fit: CapturedFit | None
    analysis_error: str | None


class CaptureResult(Model):
    """Preserve completed artifacts even if a later measurement or analysis fails."""

    baseline: FileArtifact | None
    runs: list[CapturedRun]
    comparison: list[RunComparison]
    comparison_error: str | None


# ---------------------------------------------------------------------------
# Unified Seam Request & Result
# ---------------------------------------------------------------------------


class RunRequest(Model):
    """Unified request for run operations."""

    action: RunAction
    rename: RenameRunRequest | None = None
    delete: DeleteRunRequest | None = None
    visibility: SetRunVisibilityRequest | None = None
    capture_plan: CapturePlan | None = None


class RunResult(Model):
    """Unified result containing the outcome of the requested run action."""

    action: RunAction
    rename: RenameRunResult | None = None
    delete: DeleteRunResult | None = None
    visibility: SetRunVisibilityResult | None = None
    capture: CaptureResult | None = None
