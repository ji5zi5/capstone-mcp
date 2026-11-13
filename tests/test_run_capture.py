# Copyright 2026 Capstone MCP contributors.
"""Run attribution against real archives with a simulated native save boundary."""

import hashlib
import struct
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import pytest

from capstone_mcp.file_workflows import FileArtifact
from capstone_mcp.repetition import RunReceipt, run_sequence
from capstone_mcp.runs import (
    CaptureError,
    CapturePlan,
    CaptureSession,
    SourceFit,
)
from tests.test_repetition import (
    CancellationFake,
    RecordingBackendFake,
    clock_from,
    recording_status,
    repeat_plan,
)


@dataclass(frozen=True, slots=True)
class Series:
    identifier: str
    source: str
    values: list[float]


class ArchiveSaver:
    """Each native save produces a complete closed archive, not prebuilt results."""

    def __init__(self, snapshots: list[list[Series]]) -> None:
        self.snapshots: deque[list[Series]] = deque(snapshots)
        self.paths: list[Path] = []

    def __call__(self, destination: str) -> FileArtifact:
        path = Path(destination)
        series = self.snapshots.popleft()
        sources: list[str] = []
        with ZipFile(path, "x") as archive:
            for index, item in enumerate(series):
                payload = f"data/{index}.tmp"
                sources.append(f"""
<DataSource EUID="{item.source}" LongName="{item.source}"
 UserDataEvaluatedType="1" DefaultUnit="2048">
 <DataSet DataSetID="{item.identifier}" Name="{item.identifier}">
  <DataSegmentElement>
   <DependentStorageElement StorageType="0" FileName="{payload}"
    DataCacheDataSize="{len(item.values)}" DataOffsetValue="0"/>
   <IndependentStorageElement StorageType="4" CacheDataCount="{len(item.values)}"/>
  </DataSegmentElement>
 </DataSet>
</DataSource>
""")
                archive.writestr(
                    payload, b"".join(struct.pack("<Id", 1, v) for v in item.values),
                )
            archive.writestr(
                "main.xml",
                "<DSProExperiment>" + "".join(sources) + "</DSProExperiment>",
            )
        self.paths.append(path)
        return FileArtifact(
            path=str(path), format="cap", size_bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            document_title_before="scratch.cap", document_title_after=path.name,
            precision="native-cache",
        )


def test_measure_stop_save_fit_and_compare_keeps_each_cycle_distinct(
    tmp_path: Path,
) -> None:
    # Given
    old = [Series("x0", "X", [9, 10, 11]), Series("y0", "Y", [19, 21, 23])]
    first = [*old, Series("x1", "X", [0, 1, 2]), Series("y1", "Y", [1, 3, 5])]
    second = [*first, Series("x2", "X", [0, 1, 2]), Series("y2", "Y", [2, 4, 6])]
    saver = ArchiveSaver([old, first, second])
    capture = CaptureSession(CapturePlan(
        directory=str(tmp_path / "capture"),
        fit=SourceFit(x_source_euid="X", y_source_euid="Y"),
    ), saver)
    backend = RecordingBackendFake((
        recording_status(), recording_status(), recording_status(),
    ))
    capture.begin()

    def stopped_run(receipt: RunReceipt) -> None:
        assert not backend.current.recording
        capture.record(receipt.ordinal)

    # When
    outcome = run_sequence(
        backend, repeat_plan(repetitions=2), CancellationFake((False, False, False)),
        clock=clock_from(0, 1, 2, 3), on_run=stopped_run,
    )
    report = capture.result()
    # Then
    assert outcome.state == "completed"
    assert [path.name for path in saver.paths] == [
        "baseline.cap", "run-001.cap", "run-002.cap",
    ]
    assert all(path.is_file() for path in saver.paths)
    assert report.runs[0].fit is not None
    assert report.runs[1].fit is not None
    assert report.runs[0].fit.x.dataset_id == "x1"
    assert report.runs[1].fit.x.dataset_id == "x2"
    assert report.runs[0].fit.result.intercept == 1
    assert report.runs[1].fit.result.intercept == 2
    assert [summary.mean for summary in report.comparison] == [3, 4]
    assert report.comparison[1].mean_difference_from_first == 1


def test_appended_samples_are_not_mixed_with_baseline(tmp_path: Path) -> None:
    # Given
    saver = ArchiveSaver([
        [Series("x", "X", [0, 1, 2]), Series("y", "Y", [1, 3, 5])],
        [Series("x", "X", [0, 1, 2, 3, 4, 5]),
         Series("y", "Y", [1, 3, 5, 7, 9, 11])],
    ])
    capture = CaptureSession(CapturePlan(
        directory=str(tmp_path / "capture"),
        fit=SourceFit(x_source_euid="X", y_source_euid="Y"),
    ), saver)
    capture.begin()
    # When
    capture.record(1)
    report = capture.result()
    # Then
    fit = report.runs[0].fit
    assert fit is not None
    assert fit.y.sample_start == 3
    assert fit.y.new_sample_count == 3
    assert fit.result.count == 3
    assert fit.result.slope == 2


def test_replaced_samples_fail_analysis_but_preserve_saved_artifact(
    tmp_path: Path,
) -> None:
    # Given
    saver = ArchiveSaver([
        [Series("x", "X", [0, 1, 2]), Series("y", "Y", [1, 3, 5])],
        [Series("x", "X", [0, 1, 2]), Series("y", "Y", [2, 4, 6])],
    ])
    capture = CaptureSession(CapturePlan(
        directory=str(tmp_path / "capture"),
        fit=SourceFit(x_source_euid="X", y_source_euid="Y"),
    ), saver)
    capture.begin()
    # When / Then
    with pytest.raises(CaptureError):
        capture.record(1)
    report = capture.result()
    saved = report.runs[0]
    assert Path(saved.artifact.path).is_file()
    assert saved.fit is None
    assert saved.analysis_error
    assert saved.datasets[0].kind == "replaced"
    assert saved.datasets[0].new_sample_count is None


def test_nonempty_capture_directory_is_preserved(tmp_path: Path) -> None:
    # Given
    original = tmp_path / "user.txt"
    _ = original.write_text("keep", encoding="utf-8")
    saver = ArchiveSaver([])
    capture = CaptureSession(CapturePlan(directory=str(tmp_path)), saver)
    # When / Then
    with pytest.raises(CaptureError):
        capture.begin()
    assert original.read_text(encoding="utf-8") == "keep"
    assert not saver.paths


def test_dataset_identity_is_scoped_to_source(tmp_path: Path) -> None:
    # Given
    old = [Series("old", "X", [0]), Series("old", "Y", [1])]
    current = [*old, Series("new", "X", [0, 1, 2]), Series("new", "Y", [1, 3, 5])]
    capture = CaptureSession(CapturePlan(
        directory=str(tmp_path / "capture"),
        fit=SourceFit(x_source_euid="X", y_source_euid="Y"),
    ), ArchiveSaver([old, current]))
    capture.begin()
    # When
    capture.record(1)
    fit = capture.result().runs[0].fit
    # Then
    assert fit is not None
    assert fit.x.dataset_id == fit.y.dataset_id == "new"
    assert fit.x.source_euid == "X"
    assert fit.y.source_euid == "Y"
    assert fit.result.slope == 2


def test_interrupted_capture_preserves_short_run_without_forcing_fit(
    tmp_path: Path,
) -> None:
    # Given
    old = [Series("x0", "X", [0]), Series("y0", "Y", [1])]
    current = [*old, Series("x1", "X", [0]), Series("y1", "Y", [2])]
    capture = CaptureSession(CapturePlan(
        directory=str(tmp_path / "capture"),
        fit=SourceFit(x_source_euid="X", y_source_euid="Y"),
    ), ArchiveSaver([old, current]))
    capture.begin()
    # When
    capture.record(1, interrupted=True)
    saved = capture.result().runs[0]
    # Then
    assert saved.interrupted
    assert saved.fit is None
    assert saved.analysis_error is None
    assert Path(saved.artifact.path).is_file()
