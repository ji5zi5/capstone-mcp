# Copyright 2026 Capstone MCP contributors.
"""Tool router for file workflows, dataset inspection, and export."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.capfile_models import (
    CapConfigurationView,
    CapDatasetPage,
    CapDatasetSummary,
    CapSection,
)
from capstone_mcp.capfiles import (
    extract_cap_datasets,
    read_cap_configuration,
    select_configuration,
)
from capstone_mcp.csv_data import CsvPage, read_csv_page
from capstone_mcp.desktop import AutomationError
from capstone_mcp.experiment_analysis import (
    CapLinearFitRequest,
    CapLinearFitResult,
    CapRunComparisonRequest,
    CapRunComparisonResult,
    compare_cap_datasets,
    fit_cap_datasets,
)
from capstone_mcp.file_workflows import FileArtifact, OpenedExperiment
from capstone_mcp.models import Model

type NativeCaller = Callable[..., Awaitable[Any]]


class ExportedData(Model):
    """Verified native export and a bounded page of its actual text values."""

    artifact: FileArtifact
    data: CsvPage


def register_file_tools(mcp: FastMCP, native: NativeCaller) -> dict[str, Any]:
    """Register all file inspection, dataset extraction, and export tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Save experiment as .cap",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_save_experiment(
        handle: int,
        path: str,
        *,
        allow_foreground: bool = True,
    ) -> FileArtifact:
        """Save As to a new .cap path and verify the completed archive.

        Never overwrites an existing file. The active experiment adopts the new path.
        Close existing dialogs before calling.
        """
        return FileArtifact.model_validate(
            await native(
                NativeRequest(
                    operation="save_experiment",
                    handle=handle,
                    value=path,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Open experiment file",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_open_experiment(
        handle: int,
        path: str,
        *,
        discard_unsaved: bool = False,
        allow_foreground: bool = True,
    ) -> OpenedExperiment:
        """Open an existing .cap in the attached Capstone, replacing its document.

        Uses File > Open Experiment and confirms the result by the window title.
        Prefer this to typing Ctrl+O and a path, which Capstone can ignore while it
        is still starting. Refuses when the current experiment has unsaved changes
        (title ends with *) unless discard_unsaved=true, which answers the save
        prompt with Discard. Close existing dialogs before calling.
        """
        return OpenedExperiment.model_validate(
            await native(
                NativeRequest(
                    operation="open_experiment",
                    handle=handle,
                    value=path,
                    discard_unsaved=discard_unsaved,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Export data to CSV",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_export_data(
        handle: int,
        path: str,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=10_000)] = 1000,
        *,
        allow_foreground: bool = True,
    ) -> ExportedData:
        """Read unsaved data by native CSV export to a new path, without saving .cap.

        Selects all data and aligns by index. CSV uses Capstone's configured display
        precision, not lossless cache values. Headers preserve native labels; source
        IDs and time alignment are not inferred. The entire CSV remains at path.
        """
        artifact = FileArtifact.model_validate(
            await native(
                NativeRequest(
                    operation="export_data",
                    handle=handle,
                    value=path,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )
        data = await anyio.to_thread.run_sync(
            read_csv_page, artifact.path, offset, limit,
        )
        return ExportedData(artifact=artifact, data=data)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read CSV page",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_csv_page(
        path: str,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=10_000)] = 1000,
    ) -> CsvPage:
        """Read another page of an existing CSV without repeating native export."""
        return await anyio.to_thread.run_sync(
            read_csv_page, path, offset, limit,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Inspect .cap file configuration",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_inspect_file(
        path: str,
        sections: list[CapSection] | None = None,
    ) -> CapConfigurationView:
        """Read saved .cap hardware/settings, source metadata, pages and calculations.

        Does not open the file in Capstone or infer live hardware connectivity.
        Array decoding is independent, so unknown recorded storage types do not
        prevent configuration inspection.

        The complete result is often several hundred thousand characters, mostly
        workspace (page layout) and data_sources. Pass sections to read only what
        is needed, e.g. ["hardware_interfaces", "experiment_settings"]. Sections
        not requested are null and named in omitted_sections; omit sections for all.
        """
        return select_configuration(read_cap_configuration(path), sections)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="List datasets in .cap file",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_file_datasets(path: str) -> list[CapDatasetSummary]:
        """List decodable saved datasets with source IDs, unit IDs and sample counts.

        run_name/run_number identify the recorded run a dataset belongs to; datasets
        of one run share its dataset_id across sources. Pair x and y by that run.

        Supports type-7 strings and type-0 tagged doubles, with stored, interval,
        or implicit-index independent coordinates.
        Unsupported array encodings raise an error instead of reporting empty data.
        """
        return [
            CapDatasetSummary(
                index=index,
                dataset_id=dataset.data_set_id,
                source_euid=dataset.source_euid,
                name=dataset.source_name,
                run_name=dataset.run_name,
                run_number=dataset.run_number,
                unit_id=dataset.unit_id,
                value_kind=dataset.value_kind,
                count=len(dataset.raw_values),
            )
            for index, dataset in enumerate(extract_cap_datasets(path))
        ]

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Extract dataset samples",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_extract_dataset(
        path: str,
        dataset_index: Annotated[int, Field(ge=0)],
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=10_000)] = 1000,
    ) -> CapDatasetPage:
        """Extract one sample page from a saved dataset, preserving original text.

        Numeric decimals are serialized losslessly as decimal strings. Implicit
        sample_indices are indices, not seconds. Use list tools to select the dataset.
        """
        datasets = extract_cap_datasets(path)
        if dataset_index >= len(datasets):
            msg = "Dataset index is outside this file's dataset list."
            raise AutomationError(msg)
        dataset = datasets[dataset_index]
        end = offset + limit
        return CapDatasetPage(
            dataset=CapDatasetSummary(
                index=dataset_index,
                dataset_id=dataset.data_set_id,
                source_euid=dataset.source_euid,
                name=dataset.source_name,
                run_name=dataset.run_name,
                run_number=dataset.run_number,
                unit_id=dataset.unit_id,
                value_kind=dataset.value_kind,
                count=len(dataset.raw_values),
            ),
            offset=offset,
            sample_indices=dataset.sample_indices[offset:end],
            raw_values=dataset.raw_values[offset:end],
            numeric_values=(
                None
                if dataset.numeric_values is None
                else dataset.numeric_values[offset:end]
            ),
            independent_values=dataset.independent_values[offset:end],
            independent_kind=dataset.independent_kind,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Fit datasets from file",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_fit_file(
        path: str,
        request: CapLinearFitRequest,
    ) -> CapLinearFitResult:
        """Extract and fit two explicit saved datasets, returning their full provenance."""
        return fit_cap_datasets(path, request)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Compare datasets from file",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_compare_file(
        path: str,
        request: CapRunComparisonRequest,
    ) -> CapRunComparisonResult:
        """Extract and compare saved datasets with matching declared unit IDs."""
        return compare_cap_datasets(path, request)

    return {
        "capstone_save_experiment": capstone_save_experiment,
        "capstone_open_experiment": capstone_open_experiment,
        "capstone_export_data": capstone_export_data,
        "capstone_csv_page": capstone_csv_page,
        "capstone_inspect_file": capstone_inspect_file,
        "capstone_file_datasets": capstone_file_datasets,
        "capstone_extract_dataset": capstone_extract_dataset,
        "capstone_fit_file": capstone_fit_file,
        "capstone_compare_file": capstone_compare_file,
    }

