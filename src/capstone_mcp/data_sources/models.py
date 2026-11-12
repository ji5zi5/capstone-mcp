# Copyright 2026 Capstone MCP contributors.
"""Domain models for unified experiment data series and sources."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DataSeries:
    """A 1D numerical data series with associated units and metadata."""

    name: str
    units: str
    values: list[float | None]

    def clean_floats(self) -> list[float]:
        """Return values filtered of None and NaN."""
        return [float(v) for v in self.values if v is not None]


@dataclass(frozen=True)
class ExperimentSeries:
    """Paired independent (x) and dependent (y) series for analysis and reporting."""

    x: DataSeries
    y: DataSeries
    run_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetMetadata:
    """Metadata describing an available dataset within an experiment source."""

    name: str
    units: str
    run_id: str | None
    sample_count: int
