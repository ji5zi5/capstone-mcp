# Copyright 2026 Capstone MCP contributors.
"""The reported document title reflects the completed Save As."""

import time
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest

from capstone_mcp import file_workflows, ui_strings
from capstone_mcp.desktop import AutomationError
from capstone_mcp.models import Action, Bounds, Control, Snapshot, Window

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


def test_saved_title_tolerates_transient_missing_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", Mock())
    windows = Mock(side_effect=[[], [_titled(HANDLE, "new.cap")]])
    app = cast("Capstone", cast("object", Mock(windows=windows)))
    assert file_workflows.settled_title(app, HANDLE, Path("new.cap"), "cap") == "new.cap"


def test_missing_saved_window_raises_domain_error_at_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_workflows, "TITLE_SECONDS", 0.0)
    app = cast("Capstone", cast("object", Mock(windows=Mock(return_value=[]))))
    with pytest.raises(AutomationError, match="title is unavailable"):
        _ = file_workflows.settled_title(app, HANDLE, Path("new.cap"), "cap")


def test_save_and_open_title_match_canonical_unicode(monkeypatch: pytest.MonkeyPatch) -> None:
    title = "한글실험.cap"
    path = Path(unicodedata.normalize("NFD", title))
    app, _ = _app([title, title])
    monkeypatch.setattr(file_workflows, "OPEN_STABLE_SECONDS", 0.0)
    assert file_workflows.settled_title(app, HANDLE, path, "cap") == title
    assert file_workflows.await_opened(app, HANDLE, path) == title


def test_open_confirmation_allows_existing_palette_when_target_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_workflows, "OPEN_STABLE_SECONDS", 0.0)
    app = Mock(windows=Mock(return_value=[_titled(99, "Palette"), _titled(HANDLE, "new.cap")]))
    assert file_workflows.await_opened(app, HANDLE, Path("new.cap")) == "new.cap"
    app.require_input_ready.assert_called_once_with(HANDLE)


def test_prepare_uses_requested_window_and_checks_modal_guard(tmp_path: Path) -> None:
    app = Mock(windows=Mock(return_value=[_titled(99, "Palette"), _titled(HANDLE, "document.cap")]))
    _, title, _ = file_workflows._prepare(app, HANDLE, str(tmp_path / "new.cap"), ".cap", allow_foreground=True)
    assert title == "document.cap"
    app.require_input_ready.assert_called_once_with(HANDLE)
    app.require_input_ready.side_effect = AutomationError("blocked by modal")
    with pytest.raises(AutomationError, match="blocked by modal"):
        _ = file_workflows._prepare(app, HANDLE, str(tmp_path / "new.cap"), ".cap", allow_foreground=True)


def _titled(handle: int, title: str) -> Window:
    return Window(handle=handle, title=title, process_id=7, bounds=BOUNDS)


def test_output_validation_checks_the_directory_entry_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    exists = Mock(return_value=True)
    monkeypatch.setattr(Path, "exists", exists)
    with pytest.raises(AutomationError, match="never overwritten"):
        _ = file_workflows._new_output_path(str(tmp_path / "trial.cap"), ".cap")
    exists.assert_called_once_with(follow_symlinks=False)


def test_output_validation_refuses_a_directory_name_ending_in_a_space(tmp_path: Path) -> None:
    with pytest.raises(AutomationError, match="ordinary Windows file name"):
        _ = file_workflows._new_output_path(str(tmp_path / "trial " / "data.csv"), ".csv")


def test_localized_file_menu_keeps_using_the_native_command_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources = tmp_path / "Resources" / "Strings"
    resources.mkdir(parents=True)
    (resources / "Capstone_dex.txt").write_text(
        "STR_MENU_FILE\t10415\t&Datei\n"
        "STR_MENU_DISPLAY_COPY_DISPLAY\t12998\tAnzeige kopieren\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui_strings, "EXECUTABLE", tmp_path / "Capstone.exe")
    ui_strings._labels.cache_clear()
    try:
        frame = _titled(HANDLE, "experiment.cap")
        file_menu = Control(
            ref="file", name="Datei", automation_id="", control_type="MenuItem",
            bounds=BOUNDS, parent=None, visible=True, enabled=True,
        )
        save = file_menu.model_copy(update={"ref": "save", "automation_id": "mActionSaveAs"})
        popup = Snapshot(window=_titled(9, ""), controls=[save], truncated=False)
        app = Mock(windows=Mock(return_value=[frame]))
        app.snapshot.return_value = Snapshot(
            window=frame, controls=[file_menu], truncated=False,
        )
        events = Mock()
        events.changes.until.return_value = popup

        assert file_workflows._open_command(app, events, HANDLE, "mActionSaveAs") == {HANDLE}
        assert [call.args for call in app.act.call_args_list] == [
            ("file", Action.INVOKE), ("save", Action.INVOKE),
        ]
        assert ui_strings.label_matches("Anzeige kopieren", "STR_MENU_DISPLAY_COPY_DISPLAY")
        assert not ui_strings.label_matches("Anzeige kopieren?", "STR_MENU_DISPLAY_COPY_DISPLAY")
    finally:
        ui_strings._labels.cache_clear()


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
