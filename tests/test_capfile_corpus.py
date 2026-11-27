# Copyright 2026 Capstone MCP contributors.
"""Read-only parser contracts over an optional, recursively discovered real corpus."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest
from defusedxml.ElementTree import fromstring

from capstone_mcp.capfiles import (
    list_cap_datasets,
    read_cap_configuration,
    read_cap_dataset_page,
    read_cap_file,
)
from capstone_mcp.graphs.inspection import read_saved_graph
from tests.golden_samples import GOLDEN_MASTER_DIR

if TYPE_CHECKING:
    from pathlib import Path
    from xml.etree.ElementTree import Element

    from capstone_mcp.capfile_models import CapDataSet

_ARCHIVES = sorted(GOLDEN_MASTER_DIR.rglob("*.cap"))


def _assert_saved_run_labels(root: Element, dataset: CapDataSet) -> None:
    # Templates and manual data need not have a saved run label.
    for parameters in root.iter("RunParameterSet"):
        if parameters.get("RunParameterID") == dataset.data_set_id:
            for value in parameters.iter("ParameterValue"):
                if "RunName" in value.attrib:
                    assert dataset.run_name == value.attrib["RunName"]
                if "RunNumber" in value.attrib:
                    assert dataset.run_number == int(value.attrib["RunNumber"])


@pytest.mark.parametrize(
    "path",
    _ARCHIVES or [None],
    ids=[str(path.relative_to(GOLDEN_MASTER_DIR)) for path in _ARCHIVES] or None,
)
def test_real_archive_arrays_match_native_metadata_without_modification(
    path: Path | None,
) -> None:
    if path is None:
        pytest.skip("Set CAPSTONE_GOLDEN_MASTER_DIR to a directory containing .cap files.")
    before = hashlib.sha256(path.read_bytes()).digest()
    cap = read_cap_file(path)
    configuration = read_cap_configuration(path)
    with ZipFile(path) as archive:
        root = fromstring(archive.read("main.xml"))
    graphs = root.findall(".//Workspace//WorkbookItem[@GUID='CSLineGraph']")
    for index, item in enumerate(graphs):
        graph = read_saved_graph(str(path), index)
        assert graph.graph_count == len(graphs)
        assert [s.renderer_id for s in graph.state.series] == [
            r.attrib["ZTDDRUniqueId"] for r in item.iter("ZRSIndividualRenederer")
        ]
    native_datasets = list(root.iter("DataSet"))
    assert len(cap.datasets) == len(native_datasets)
    assert cap.data_sources == configuration.data_sources
    assert cap.experiment_settings == configuration.experiment_settings
    summaries = list_cap_datasets(path)
    assert len(summaries) == len(cap.datasets)
    for index, (dataset, native) in enumerate(zip(cap.datasets, native_datasets, strict=True)):
        storage = native.find("./DataSegmentElement/DependentStorageElement")
        assert storage is not None
        count = int(storage.attrib["DataCacheDataSize"])
        assert summaries[index].count == count
        offset = max(0, count - 3)
        page = read_cap_dataset_page(path, index, offset, 3)
        assert page.raw_values == dataset.raw_values[offset:offset + 3]
        assert page.independent_values == dataset.independent_values[offset:offset + 3]
        assert page.sample_indices == dataset.sample_indices[offset:offset + 3]
        assert page.numeric_values == (
            dataset.numeric_values[offset:offset + 3]
            if dataset.numeric_values is not None else None
        )
        assert dataset.data_set_id == native.get("DataSetID")
        assert len(dataset.raw_values) == count
        assert dataset.sample_indices == list(range(count))
        assert len(dataset.independent_values) == count
        if dataset.numeric_values is not None:
            assert len(dataset.numeric_values) == count
        if dataset.text_values is not None:
            assert len(dataset.text_values) == count
        if dataset.scalar_attributes is not None:
            assert len(dataset.scalar_attributes) == count
        _assert_saved_run_labels(root, dataset)
    assert hashlib.sha256(path.read_bytes()).digest() == before
