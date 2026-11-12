# Copyright 2026 Capstone MCP contributors.
"""The reported document title reflects the completed Save As."""

import time
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest

from capstone_mcp import file_workflows
from capstone_mcp.desktop import AutomationError
from capstone_mcp.models import Bounds, Window

if TYPE_CHECKING:
    from capstone_mcp.desktop import Capstone

HANDLE = 5
BOUNDS = Bounds(left=0, top=0, right=5, bottom=5)


def _app(titles: list[str]) -> tuple["Capstone", Mock]:
    windows = Mock(side_effect=[
        [Window(handle=HANDLE, title=title, process_id=7, bounds=BOUNDS)]
        for title in titles
    ])
    return cast("Capstone", cast("object", Mock(windows=windows))), windows


def test_saved_title_waits_for_capstone_to_rename_the_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the window still shows the previous name right after the save.
    monkeypatch.setattr(time, "sleep", Mock())
    app, windows = _app(["old.cap*", "old.cap*", "new.cap"])
    # When
    title = file_workflows.settled_title(
        app, HANDLE, Path("C:/out/new.cap"), "cap",
    )
    # Then
    assert title == "new.cap"
    assert windows.call_count == 3


def test_unrenamed_title_is_reported_as_observed_after_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the title never changes and the bound has already elapsed.
    monkeypatch.setattr(file_workflows, "TITLE_SECONDS", 0.0)
    app, _windows = _app(["old.cap*"])
    # When
    title = file_workflows.settled_title(
        app, HANDLE, Path("C:/out/new.cap"), "cap",
    )
    # Then: nothing is invented.
    assert title == "old.cap*"


def test_export_reads_the_title_once_because_it_never_renames() -> None:
    app, windows = _app(["experiment.cap*"])
    title = file_workflows.settled_title(
        app, HANDLE, Path("C:/out/data.csv"), "csv",
    )
    assert title == "experiment.cap*"
    windows.assert_called_once()


def _titled(handle: int, title: str) -> Window:
    return Window(handle=handle, title=title, process_id=7, bounds=BOUNDS)


def test_open_is_confirmed_only_after_the_loading_window_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the file dialog closes, a progress window appears, then it ends.
    monkeypatch.setattr(time, "sleep", Mock())
    monkeypatch.setattr(file_workflows, "OPEN_STABLE_SECONDS", 0.0)
    windows = Mock(side_effect=[
        [_titled(9, "PASCO Capstone"), _titled(HANDLE, "old.cap")],
        [_titled(HANDLE, "new.cap")],
    ])
    app = cast("Capstone", cast("object", Mock(windows=windows)))
    # When
    title = file_workflows.await_opened(app, HANDLE, Path("C:/in/new.cap"))
    # Then
    assert title == "new.cap"
    assert windows.call_count == 2


def test_open_that_never_shows_the_file_name_is_reported_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_workflows, "OPEN_SECONDS", 0.0)
    app, _windows = _app(["old.cap"])
    with pytest.raises(AutomationError, match="did not confirm"):
        _ = file_workflows.await_opened(app, HANDLE, Path("C:/in/new.cap"))


def test_open_refuses_to_drop_unsaved_changes_without_explicit_consent(
    tmp_path: Path,
) -> None:
    # Given: the current experiment's title marks unsaved changes.
    source = tmp_path / "next.cap"
    _ = source.write_bytes(b"cap")
    snapshot = Mock()
    windows = Mock(return_value=[_titled(HANDLE, "current.cap*")])
    app = cast("Capstone", cast("object", Mock(windows=windows, snapshot=snapshot)))
    # When / Then: no menu is opened and nothing is discarded.
    with pytest.raises(AutomationError, match=r"unsaved changes.*discard_unsaved"):
        _ = file_workflows.open_experiment(app, HANDLE, str(source))
    snapshot.assert_not_called()


def test_open_requires_an_existing_cap_file(tmp_path: Path) -> None:
    windows = Mock()
    app = cast("Capstone", cast("object", Mock(windows=windows)))
    with pytest.raises(AutomationError, match=r"existing \.cap"):
        _ = file_workflows.open_experiment(app, HANDLE, str(tmp_path / "none.cap"))
    windows.assert_not_called()
