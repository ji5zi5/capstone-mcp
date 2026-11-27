# Copyright 2026 Capstone MCP contributors.
"""Observed native save/export dialogs with event-confirmed output completion."""

from __future__ import annotations

import hashlib
import sys
import time
import unicodedata
from _ctypes import COMError
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from capstone_mcp.capfiles import read_cap_configuration
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.file_events import FileEvents
from capstone_mcp.file_workflow_models import FileWorkflowLabels
from capstone_mcp.models import Action, Control, Model, Snapshot
from capstone_mcp.ui_events import WindowEvents
from capstone_mcp.ui_strings import label_matches

if TYPE_CHECKING:
    from collections.abc import Callable

    from capstone_mcp.models import Window

MAX_OUTPUT_BYTES: Final = 64 * 1024 * 1024
TRANSITION_SECONDS: Final = 15
TITLE_SECONDS: Final = 3.0
TITLE_POLL_SECONDS: Final = 0.1
OPEN_SECONDS: Final = 40.0
OPEN_STABLE_SECONDS: Final = 1.0
OPEN_FIELD_ID: Final = "1148"


class FileArtifact(Model):
    """A closed, confirmed native output; the document itself may remain unsaved."""

    path: str
    format: Literal["cap", "csv"]
    size_bytes: int
    sha256: str
    document_title_before: str
    document_title_after: str
    precision: Literal["native-cache", "capstone-export"]


class OpenedExperiment(Model):
    """A document opened through the native dialog and confirmed by its title."""

    path: str
    document_title_before: str
    document_title_after: str
    discarded_unsaved_changes: bool


class _ResourceLabel(str):
    """Internal marker for a default installed-resource label, never user input."""

    __slots__ = ()


_DEFAULT_CLOSE: Final = _ResourceLabel("STR_CLOSE")
_DEFAULT_FILE_MENU: Final = _ResourceLabel("STR_MENU_FILE")


def _workflow_labels(provided: FileWorkflowLabels | None) -> FileWorkflowLabels:
    labels = provided or FileWorkflowLabels()
    keys = {
        "file_menu": "STR_MENU_FILE",
        "export_format": "STR_EXPORT_DATA_EXPORT_FORMAT_BUTTON_LABEL",
        "csv_format": "STR_EXPORT_DATA_EXPORT_FORMAT_CSV_MENU_ITEM",
        "alignment_options": "STR_EXPORT_DATA_DIALOG_OPTIONS",
        "align_by_index": "STR_TABLE_DATA_ALIGNMENT_MODE_INDEX",
        "select_all": "STR_EXPORT_DATA_DIALOG_SELECT_ALL",
        "export_to_file": "STR_EXPORT_DATA_DIALOG_EXPORT",
        "close": "STR_CLOSE",
    }
    return labels.model_copy(update={
        field: _ResourceLabel(key) for field, key in keys.items()
        if field not in labels.model_fields_set
    })


def _matches_label(actual: str, expected: str) -> bool:
    return (
        label_matches(actual, expected)
        if isinstance(expected, _ResourceLabel) else actual == expected
    )


def _one(snapshot: Snapshot, predicate: Callable[[Control], bool]) -> Control:
    if snapshot.truncated:
        msg = "Native dialog snapshot is truncated; target uniqueness is unknown."
        raise AutomationError(msg)
    matches = [c for c in snapshot.controls if c.visible and predicate(c)]
    if len(matches) != 1 or not matches[0].enabled:
        msg = "Expected one enabled native control; inspect the current dialog."
        raise AutomationError(msg)
    return matches[0]


def _new_snapshot(
    app: Capstone, before: set[int], predicate: Callable[[Snapshot], bool],
    *, depth: int = 16,
) -> Snapshot | None:
    matches: list[int] = []
    for window in app.windows():
        if window.handle in before:
            continue
        try:
            snapshot = app.snapshot(window.handle, depth, 10_000)
        except (COMError, AutomationError):
            continue
        if not snapshot.truncated and predicate(snapshot):
            matches.append(window.handle)
    if len(matches) > 1:
        msg = "Multiple new native dialogs match; no dialog target was selected."
        raise AutomationError(msg)
    if not matches:
        return None
    # Inspecting another window replaces snapshot-scoped control references.
    try:
        fresh = app.snapshot(matches[0], depth, 10_000)
    except (COMError, AutomationError):
        return None
    return fresh if not fresh.truncated and predicate(fresh) else None


def _named_button(app: Capstone, handle: int, name: str) -> Control:
    return _one(
        app.snapshot(handle, 16, 10_000),
        lambda c: c.control_type == "Button" and _matches_label(c.name, name),
    )


def _open_command(
    app: Capstone, events: WindowEvents, handle: int, command_id: str,
    *, file_menu_label: str = _DEFAULT_FILE_MENU,
) -> set[int]:
    before = {w.handle for w in app.windows()}
    file_menu = _one(
        app.snapshot(handle, 16, 10_000),
        lambda c: c.control_type == "MenuItem"
        and _matches_label(c.name, file_menu_label),
    )
    _ = app.act(file_menu.ref, Action.INVOKE)
    try:
        menu = events.changes.until(
            lambda: _new_snapshot(
                app, before,
                lambda s: any(c.automation_id == command_id for c in s.controls),
            ),
            TRANSITION_SECONDS,
        )
        command = _one(menu, lambda c: c.automation_id == command_id)
        _ = app.act(command.ref, Action.INVOKE)
    except Exception:
        with suppress(Exception):
            _ = app.keys(handle, "{ESC}")
        raise
    return before


def _choose_export_option(
    app: Capstone, events: WindowEvents, handle: int, button: str, option: str,
) -> None:
    before = {w.handle for w in app.windows()}
    control = _named_button(app, handle, button)
    _ = app.act(control.ref, Action.INVOKE)
    menu = events.changes.until(
        lambda: _new_snapshot(
            app, before,
            lambda s: any(
                c.control_type == "MenuItem" and _matches_label(c.name, option)
                for c in s.controls
            ),
        ),
        TRANSITION_SECONDS,
    )
    control = _one(
        menu, lambda c: c.control_type == "MenuItem" and _matches_label(c.name, option),
    )
    menu_handle = menu.window.handle
    _ = app.act(control.ref, Action.INVOKE)
    _ = events.changes.until(
        lambda: True if all(
            w.handle != menu_handle for w in app.windows()
        ) else None,
        TRANSITION_SECONDS,
    )


def _file_dialog(
    app: Capstone, events: WindowEvents, before: set[int],
    *, filename_id: str = "1001",
) -> Snapshot:
    return events.changes.until(
        lambda: _new_snapshot(
            app, before,
            lambda s: any(
                c.control_type == "Edit" and c.automation_id == filename_id
                for c in s.controls
            ),
            depth=16,
        ),
        TRANSITION_SECONDS,
    )


def _save_dialog(  # noqa: PLR0913
    app: Capstone, files: FileEvents,
    dialog: Snapshot, path: Path, allowed_windows: set[int],
    *, filename_id: str = "1001",
) -> None:
    field = _one(
        dialog, lambda c: c.control_type == "Edit" and c.automation_id == filename_id,
    )
    _ = app.set_value(field.ref, str(path))
    snapshot = app.snapshot(dialog.window.handle, 16, 10_000)
    save = _one(
        snapshot, lambda c: c.control_type == "Button" and c.automation_id == "1",
    )
    if path.exists():
        msg = "Output appeared before Save; overwrite was not authorized."
        raise AutomationError(msg)
    _ = app.act(save.ref, Action.INVOKE)
    _ = files.changes.until(
        lambda: True if files.ready(path) and {
            w.handle for w in app.windows()
        }.issubset(allowed_windows) else None,
        TRANSITION_SECONDS,
    )


def _workflow_window(app: Capstone, handle: int) -> Window:
    windows = [window for window in app.windows() if window.handle == handle]
    if len(windows) != 1:
        msg = "The target Capstone window is not available."
        raise AutomationError(msg)
    app.require_input_ready(handle)
    return windows[0]


def _new_output_path(destination: str, suffix: str) -> Path:
    path = Path(destination)
    for part in path.parts:
        if part in {path.anchor, ".."}:
            continue
        if (
            Path(part).is_reserved() or part.endswith((" ", "."))
            or any(c in '<>:"|?*' or ord(c) < 32 for c in part)  # noqa: PLR2004
        ):
            msg = "Choose an ordinary Windows file name for the output."
            raise AutomationError(msg)
    if path.suffix.lower() != suffix or path.exists(follow_symlinks=False):
        msg = f"Choose a new {suffix} path; existing files are never overwritten."
        raise AutomationError(msg)
    path = path.parent.resolve() / path.name
    if not path.parent.is_dir():
        msg = "Output directory must already exist."
        raise AutomationError(msg)
    return path


def _prepare(
    app: Capstone, handle: int, destination: str, suffix: str,
    *, allow_foreground: bool,
) -> tuple[Path, str, int]:
    if not allow_foreground:
        msg = "Saving/exporting uses native dialog input; foreground input is disabled."
        raise AutomationError(msg)
    path = _new_output_path(destination, suffix)
    window = _workflow_window(app, handle)
    return path, window.title, window.process_id


def settled_title(
    app: Capstone, handle: int, path: Path, kind: Literal["cap", "csv"],
) -> str:
    """Read the title after Save As renamed the document, within a short bound.

    Capstone retitles the window shortly after the file is closed; an immediate
    read returned the previous name. Export never renames the document.
    """
    deadline = time.monotonic() + TITLE_SECONDS
    while True:
        title = next((w.title for w in app.windows() if w.handle == handle), None)
        renamed = title is not None and _title_matches_path(title, path)
        if title is not None and (
            kind != "cap" or renamed or time.monotonic() >= deadline
        ):
            return title
        if time.monotonic() >= deadline:
            msg = "Saved output exists but the target window title is unavailable."
            raise AutomationError(msg)
        time.sleep(TITLE_POLL_SECONDS)


def _title_matches_path(title: str, path: Path) -> bool:
    return unicodedata.normalize("NFC", title).startswith(
        unicodedata.normalize("NFC", path.name),
    )


def _artifact(
    app: Capstone, handle: int, path: Path, before: str,
    kind: Literal["cap", "csv"],
) -> FileArtifact:
    size = path.stat().st_size
    if size > MAX_OUTPUT_BYTES:
        msg = "Output was created but exceeds the 64 MiB extraction limit."
        raise AutomationError(msg)
    after = settled_title(app, handle, path, kind)
    return FileArtifact(
        path=str(path), format=kind, size_bytes=size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        document_title_before=before, document_title_after=after,
        precision="native-cache" if kind == "cap" else "capstone-export",
    )


def save_experiment(
    app: Capstone, handle: int, destination: str, *, allow_foreground: bool = True,
    workflow_labels: FileWorkflowLabels | None = None,
) -> FileArtifact:
    """Save As to a new explicit path and verify the resulting Capstone archive."""
    labels = _workflow_labels(workflow_labels)
    path, before, pid = _prepare(
        app, handle, destination, ".cap", allow_foreground=allow_foreground,
    )
    with WindowEvents(pid) as events, FileEvents(path.parent, events.changes) as files:
        previous = _open_command(
            app, events, handle, "mActionSaveAs", file_menu_label=labels.file_menu,
        )
        dialog = _file_dialog(app, events, previous, filename_id=labels.filename_id)
        _save_dialog(
            app, files, dialog, path, previous, filename_id=labels.filename_id,
        )
    _ = read_cap_configuration(path)
    return _artifact(app, handle, path, before, "cap")


def export_data(
    app: Capstone, handle: int, destination: str, *, allow_foreground: bool = True,
    workflow_labels: FileWorkflowLabels | None = None,
) -> FileArtifact:
    """Select all data and export by index as CSV without saving the .cap document."""
    labels = _workflow_labels(workflow_labels)
    path, before, pid = _prepare(
        app, handle, destination, ".csv", allow_foreground=allow_foreground,
    )
    with WindowEvents(pid) as events, FileEvents(path.parent, events.changes) as files:
        previous = _open_command(
            app, events, handle, "mActionExportData", file_menu_label=labels.file_menu,
        )
        baseline_windows = previous.copy()
        dialog = events.changes.until(
            lambda: _new_snapshot(
                app, previous,
                lambda s: bool(s.controls)
                and s.controls[0].automation_id == "DataExportDialog",
                depth=16,
            ),
            TRANSITION_SECONDS,
        )
        export_handle = dialog.window.handle
        try:
            _choose_export_option(
                app, events, export_handle, labels.export_format, labels.csv_format,
            )
            _choose_export_option(
                app, events, export_handle,
                labels.alignment_options, labels.align_by_index,
            )
            select = _named_button(app, export_handle, labels.select_all)
            _ = app.act(select.ref, Action.INVOKE)
            export = _named_button(app, export_handle, labels.export_to_file)
            previous = {w.handle for w in app.windows()}
            _ = app.act(export.ref, Action.INVOKE)
            file_dialog = _file_dialog(
                app, events, previous, filename_id=labels.filename_id,
            )
            _save_dialog(
                app, files, file_dialog, path, baseline_windows | {export_handle},
                filename_id=labels.filename_id,
            )
        finally:
            _close_export_dialog(
                app, events, export_handle, failing=sys.exception() is not None,
                close_label=labels.close,
            )
    return _artifact(app, handle, path, before, "csv")


def _close_export_dialog(
    app: Capstone, events: WindowEvents, handle: int, *, failing: bool,
    close_label: str = _DEFAULT_CLOSE,
) -> None:
    """Close only the export dialog observed by this workflow, if still present."""
    original = sys.exception()
    try:
        if not any(window.handle == handle for window in app.windows()):
            return
        close = _named_button(app, handle, close_label)
        _ = app.act(close.ref, Action.INVOKE)
        _ = events.changes.until(
            lambda: True if all(w.handle != handle for w in app.windows()) else None,
            TRANSITION_SECONDS,
        )
    except Exception as cleanup_error:
        if not failing:
            raise
        msg = (
            f"Export dialog {handle} could not be closed; an unresolved native "
            "dialog may still block Capstone. Inspect the current windows before "
            f"retrying. Cleanup failure: {cleanup_error}."
        )
        if original is not None:
            msg = f"{original} {msg}"
        raise AutomationError(msg) from original or cleanup_error


def _is_open_field(control: Control, field_id: str = OPEN_FIELD_ID) -> bool:
    return control.control_type == "Edit" and control.automation_id == field_id


def _is_discard(control: Control, label: str = "Discard") -> bool:
    return control.control_type == "Button" and control.name == label


def await_opened(app: Capstone, handle: int, path: Path) -> str:
    """Wait until the target window is input-ready and carries the file name.

    The loading progress window can appear after the file dialog closes, so the
    title must stay confirmed for a short stable period before it is accepted.
    """
    deadline = time.monotonic() + OPEN_SECONDS
    stable_since: float | None = None
    while time.monotonic() < deadline:
        windows = app.windows()
        title = next((w.title for w in windows if w.handle == handle), "")
        ready = False
        if title and _title_matches_path(title, path):
            try:
                app.require_input_ready(handle)
                ready = True
            except AutomationError:
                pass
        if ready:
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= OPEN_STABLE_SECONDS:
                return title
        else:
            stable_since = None
        time.sleep(TITLE_POLL_SECONDS)
    msg = (
        "Open was requested but the experiment title did not confirm it in time. "
        "Capstone may still be loading; inspect capstone_windows before more input."
    )
    raise AutomationError(msg)


def _open_preconditions(
    app: Capstone, handle: int, source: str, *, discard_unsaved: bool,
) -> tuple[Path, str, int]:
    path = Path(source).resolve()
    if path.suffix.lower() != ".cap" or not path.is_file():
        msg = "Choose an existing .cap file to open."
        raise AutomationError(msg)
    window = _workflow_window(app, handle)
    before = window.title
    if before.endswith("*") and not discard_unsaved:
        msg = (
            f"The open experiment has unsaved changes ({before}). Save it with "
            "capstone_save_experiment first, or pass discard_unsaved=true to "
            "drop them."
        )
        raise AutomationError(msg)
    return path, before, window.process_id


def open_experiment(  # noqa: PLR0913
    app: Capstone, handle: int, source: str,
    *, discard_unsaved: bool = False, allow_foreground: bool = True,
    workflow_labels: FileWorkflowLabels | None = None,
) -> OpenedExperiment:
    """Open an existing .cap through File > Open Experiment, replacing the document."""
    if not allow_foreground:
        msg = "Opening uses native dialog input; foreground input is disabled."
        raise AutomationError(msg)
    path, before, pid = _open_preconditions(
        app, handle, source, discard_unsaved=discard_unsaved,
    )
    labels = _workflow_labels(workflow_labels)
    def is_field(control: Control) -> bool:
        return _is_open_field(control, labels.open_filename_id)

    def is_discard(control: Control) -> bool:
        return _is_discard(control, labels.discard)

    discarded = False
    with WindowEvents(pid) as events:
        previous = _open_command(
            app, events, handle, "mActionOpenExperiment",
            file_menu_label=labels.file_menu,
        )
        dialog = events.changes.until(
            lambda: _new_snapshot(
                app, previous,
                lambda s: any(is_field(c) or is_discard(c) for c in s.controls),
                depth=16,
            ),
            TRANSITION_SECONDS, description="Open Experiment dialog",
        )
        if any(is_discard(c) for c in dialog.controls):
            if not discard_unsaved:
                msg = (
                    "Capstone asks whether to save the current experiment. Answer "
                    "that prompt deliberately; nothing was opened or discarded."
                )
                raise AutomationError(msg)
            _ = app.act(_one(dialog, is_discard).ref, Action.INVOKE)
            discarded = True
            dialog = events.changes.until(
                lambda: _new_snapshot(
                    app, previous,
                    lambda s: any(is_field(c) for c in s.controls),
                    depth=16,
                ),
                TRANSITION_SECONDS, description="Open Experiment file dialog",
            )
        _ = app.set_value(_one(dialog, is_field).ref, str(path))
        confirm = _one(
            app.snapshot(dialog.window.handle, 16, 10_000),
            lambda c: c.control_type == "Button" and c.automation_id == "1",
        )
        _ = app.act(confirm.ref, Action.INVOKE)
        after = await_opened(app, handle, path)
    return OpenedExperiment(
        path=str(path), document_title_before=before, document_title_after=after,
        discarded_unsaved_changes=discarded,
    )
