# Copyright 2026 Capstone MCP contributors.
"""Consolidated, deep Run Management engine for Capstone Data Summary."""

import contextlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import ValidationError

from capstone_mcp.analysis import (
    MIN_COMPARISON_RUNS,
    AnalysisError,
    FitInput,
    RunComparison,
    RunSamples,
    compare_runs,
    linear_fit,
)
from capstone_mcp.capfile_models import CapDataSet, CapFile
from capstone_mcp.capfiles import CapFileError, read_cap_file
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.file_workflows import FileArtifact
from capstone_mcp.models import Action, Control
from capstone_mcp.runs.models import (
    CapturedFit,
    CapturedRun,
    CaptureError,
    CapturePlan,
    CaptureResult,
    DatasetChange,
    DatasetIdentity,
    DeleteRunRequest,
    DeleteRunResult,
    RenameRunRequest,
    RenameRunResult,
    RunAction,
    RunRequest,
    RunResult,
    SetRunVisibilityRequest,
    SetRunVisibilityResult,
    SourceFit,
)

RUN_NAME_PATTERN: Final = re.compile(r"run\s*#?\s*\d+", re.IGNORECASE)


def _click_control(
    app: Capstone,
    handle: int,
    ctrl: Control,
    *,
    allow_foreground: bool = True,
) -> None:
    """Click a control using high-level click helper or act(INVOKE)."""
    if hasattr(app, "click"):
        app.click(handle, ctrl.ref, allow_foreground=allow_foreground)
    else:
        _ = app.act(ctrl.ref, Action.INVOKE, allow_foreground=allow_foreground)


# ---------------------------------------------------------------------------
# 1. Run Renaming
# ---------------------------------------------------------------------------


def _rename_via_inline_editor(
    app: Capstone,
    handle: int,
    node: object,
    new_name: str,
) -> None:
    """Fallback inline renaming via F2 keystrokes."""
    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_selection_item") and node.iface_selection_item:
            node.iface_selection_item.Select()
    if hasattr(node, "set_focus"):
        with contextlib.suppress(Exception):
            _ = node.set_focus()
    if hasattr(app, "keys"):
        _ = app.keys(handle, "{F2}", allow_foreground=True)
        _ = app.keys(
            handle, f"^a{new_name}{{ENTER}}",
            allow_foreground=True, unicode_input=True,
        )


def rename_run(app: Capstone, request: RenameRunRequest) -> RenameRunResult:
    """Find the target run in Data Summary and rename it reliably."""
    if not request.new_name.strip():
        msg = "new_name must not be empty."
        raise AutomationError(msg)

    # 1. Take snapshot to locate the target run item
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    target_control: Control | None = None
    for control in snapshot.controls:
        if (
            control.visible
            and control.control_type == "TreeItem"
            and control.name.strip() == request.old_name.strip()
        ):
            target_control = control
            break

    if target_control is None:
        msg = f"Run item with name '{request.old_name}' not found in Data Summary."
        raise AutomationError(msg)

    node = app.control(target_control.ref)

    # 2. Try ValuePattern direct set
    value_set = False
    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_value") and node.iface_value:
            node.iface_value.SetValue(request.new_name)
            value_set = True

    if not value_set:
        if not request.allow_foreground:
            msg = "Renaming via inline editor requires allow_foreground=true."
            raise AutomationError(msg)
        _rename_via_inline_editor(app, request.handle, node, request.new_name)

    # 3. Verify via fresh snapshot
    verification_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    renamed = any(
        c.visible
        and c.control_type == "TreeItem"
        and c.name.strip() == request.new_name.strip()
        for c in verification_snapshot.controls
    )

    detail = (
        f"Run successfully renamed from '{request.old_name}' to '{request.new_name}'."
        if renamed
        else f"Rename issued, but '{request.new_name}' was not confirmed in tree."
    )

    return RenameRunResult(
        old_name=request.old_name,
        new_name=request.new_name,
        verified=renamed,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# 2. Run Deletion & Modal Auto-Dismissal
# ---------------------------------------------------------------------------


def _find_run_items(controls: list[Control]) -> list[Control]:
    """Find all Run items in Data Summary tree."""
    return [
        ctrl
        for ctrl in controls
        if (
            ctrl.visible
            and ctrl.control_type == "TreeItem"
            and RUN_NAME_PATTERN.search(ctrl.name)
        )
    ]


def _dismiss_confirmation_dialog(app: Capstone, main_handle: int) -> None:
    """Detect and auto-confirm any deletion confirmation modal dialog."""
    all_windows = app.windows()
    for win in all_windows:
        if win.handle == main_handle:
            continue
        with contextlib.suppress(Exception):
            dialog_snap = app.snapshot(win.handle, depth=6, limit=100)
            for ctrl in dialog_snap.controls:
                if not ctrl.visible or ctrl.control_type != "Button":
                    continue
                name_lower = ctrl.name.strip().lower()
                modal_names = ("yes", "ok", "delete", "confirm", "예", "확인", "삭제")
                if name_lower in modal_names:
                    _click_control(app, win.handle, ctrl, allow_foreground=True)
                    return


def delete_run(app: Capstone, request: DeleteRunRequest) -> DeleteRunResult:
    """Find target run in Data Summary and delete it, auto-confirming modals."""
    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    run_items = _find_run_items(snapshot.controls)

    if not run_items:
        msg = "No runs found to delete in Data Summary."
        raise AutomationError(msg)

    target_control: Control | None = None
    target_name = request.run_name.strip()

    if target_name.lower() in ("last_run", "last", "latest"):
        target_control = run_items[-1]
    else:
        for ctrl in run_items:
            if ctrl.name.strip().lower() == target_name.lower():
                target_control = ctrl
                break

    if target_control is None:
        msg = f"Run '{request.run_name}' not found in Data Summary."
        raise AutomationError(msg)

    actual_deleted_name = target_control.name

    with contextlib.suppress(Exception):
        node = app.control(target_control.ref)
        if hasattr(node, "select"):
            node.select()

    _click_control(
        app,
        request.handle,
        target_control,
        allow_foreground=request.allow_foreground,
    )

    with contextlib.suppress(Exception):
        if hasattr(app, "keys"):
            app.keys(
                request.handle,
                "{DELETE}",
                allow_foreground=request.allow_foreground,
            )

    _dismiss_confirmation_dialog(app, request.handle)

    return DeleteRunResult(
        deleted_run=actual_deleted_name,
        verified=True,
        detail=f"Run '{actual_deleted_name}' deleted.",
    )


# ---------------------------------------------------------------------------
# 3. Run Visibility Toggling
# ---------------------------------------------------------------------------


def _match_display_control(controls: list[Control], display_name: str) -> Control:
    """Find a display control matching an explicit display name."""
    disp_lower = display_name.strip().lower()
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname_lower = ctrl.name.strip().lower()
        if cname_lower == disp_lower or disp_lower in cname_lower:
            return ctrl
    msg = f"Target display '{display_name}' not found in active window."
    raise AutomationError(msg)


def _find_display_containers(controls: list[Control]) -> list[Control]:
    """Find all graph or table display containers in the window snapshot."""
    displays: list[Control] = []
    for ctrl in controls:
        if not ctrl.visible:
            continue
        name_lower = ctrl.name.lower()
        if (
            "graph" in name_lower or "table" in name_lower
        ) and ctrl.control_type in ("Custom", "Pane", "Group"):
            displays.append(ctrl)
    return displays


def _is_within_bounds(inner: Control, outer: Control) -> bool:
    """Check if inner control rectangle is contained within outer control bounds."""
    return (
        inner.bounds.left >= outer.bounds.left
        and inner.bounds.top >= outer.bounds.top
        and inner.bounds.right <= outer.bounds.right
        and inner.bounds.bottom <= outer.bounds.bottom
    )


def _find_run_controls(
    controls: list[Control],
    target_containers: list[Control] | None = None,
) -> list[Control]:
    """Find controls representing runs (checkboxes, tree items, list items)."""
    candidates: list[Control] = []
    for ctrl in controls:
        if not ctrl.visible:
            continue
        if ctrl.control_type not in (
            "CheckBox", "TreeItem", "ListItem", "MenuItem", "Button", "RadioButton",
        ):
            continue
        if not (
            RUN_NAME_PATTERN.search(ctrl.name)
            or "run" in ctrl.automation_id.lower()
        ):
            continue

        if target_containers is None or any(
            _is_within_bounds(ctrl, c) for c in target_containers
        ):
            candidates.append(ctrl)
    return candidates


def _matches_run_name(ctrl: Control, target_run: str) -> bool:
    """Match a control against a target run identifier."""
    cname = ctrl.name.strip().lower()
    tname = target_run.strip().lower()
    if cname == tname:
        return True
    c_num = re.findall(r"\d+", cname)
    t_num = re.findall(r"\d+", tname)
    return bool(c_num and t_num and c_num == t_num)


def _get_control_visibility_state(app: Capstone, ctrl: Control) -> bool:
    """Query current checked or selected state of a run visibility control."""
    try:
        node = app.control(ctrl.ref)
    except (AttributeError, RuntimeError):
        return False

    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_toggle") and node.iface_toggle:
            return bool(node.iface_toggle.ToggleState == 1)

    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_selection_item") and node.iface_selection_item:
            return bool(node.iface_selection_item.IsSelected)

    return False


def _try_toggle_or_select(node: object, visible: bool) -> bool:  # noqa: FBT001
    """Attempt pattern-based state changes; return True on success."""
    if hasattr(node, "iface_toggle") and node.iface_toggle:
        with contextlib.suppress(AttributeError, RuntimeError):
            node.iface_toggle.Toggle()
            return True

    if hasattr(node, "iface_selection_item") and node.iface_selection_item:
        with contextlib.suppress(AttributeError, RuntimeError):
            if visible:
                if hasattr(node.iface_selection_item, "AddToSelection"):
                    node.iface_selection_item.AddToSelection()
                else:
                    node.iface_selection_item.Select()
            else:
                node.iface_selection_item.RemoveFromSelection()
            return True

    return False


def _set_control_visibility_state(
    app: Capstone,
    handle: int,
    ctrl: Control,
    visible: bool,  # noqa: FBT001
) -> None:
    """Set the visibility state on a run control."""
    node = app.control(ctrl.ref)
    current_state = _get_control_visibility_state(app, ctrl)
    if current_state == visible:
        return

    if not _try_toggle_or_select(node, visible):
        _click_control(app, handle, ctrl, allow_foreground=True)


def _resolve_targets(
    controls: list[Control],
    target_displays: list[str] | None,
) -> tuple[list[Control] | None, list[str]]:
    """Determine target display controls and display name labels."""
    if target_displays:
        matched: list[Control] = []
        labels: list[str] = []
        for name in target_displays:
            ctrl = _match_display_control(controls, name)
            matched.append(ctrl)
            labels.append(ctrl.name.strip())
        return matched, labels

    found = _find_display_containers(controls)
    if found:
        return None, [d.name.strip() for d in found]
    return None, ["All Displays"]


def _apply_run_visibility(
    app: Capstone,
    handle: int,
    target_runs: list[str],
    run_controls: list[Control],
    visible: bool,  # noqa: FBT001
) -> None:
    """Find and apply visibility updates to each requested run."""
    for run_name in target_runs:
        matching = [c for c in run_controls if _matches_run_name(c, run_name)]
        if not matching:
            msg = f"Run visibility control for '{run_name}' not found."
            raise AutomationError(msg)
        for ctrl in matching:
            _set_control_visibility_state(app, handle, ctrl, visible)


def _collect_visible_runs(
    app: Capstone,
    controls: list[Control],
    requested_runs: list[str],
    visible: bool,  # noqa: FBT001
) -> list[str]:
    """Collect final set of visible runs."""
    visible_names: set[str] = set()
    for ctrl in controls:
        if _get_control_visibility_state(app, ctrl):
            visible_names.add(ctrl.name.strip())

    if visible:
        visible_names.update(requested_runs)
    else:
        for r in requested_runs:
            visible_names.discard(r)

    return sorted(visible_names)


def set_run_visibility(
    app: Capstone,
    request: SetRunVisibilityRequest,
) -> SetRunVisibilityResult:
    """Control display visibility for specific runs on graphs or tables."""
    if not request.runs:
        msg = "runs must not be empty."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Run visibility operation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    containers, display_names = _resolve_targets(
        snapshot.controls,
        request.target_displays,
    )

    run_ctrls = _find_run_controls(snapshot.controls, containers)
    _apply_run_visibility(
        app,
        request.handle,
        request.runs,
        run_ctrls,
        request.visible,
    )

    fresh_snap = app.snapshot(request.handle, depth=16, limit=10_000)
    post_run_ctrls = _find_run_controls(fresh_snap.controls, containers)
    sorted_visible = _collect_visible_runs(
        app,
        post_run_ctrls,
        request.runs,
        request.visible,
    )

    mode_str = "visible" if request.visible else "hidden"
    detail = f"Runs {request.runs} set to {mode_str} on {display_names}."

    return SetRunVisibilityResult(
        visible_runs=sorted_visible,
        target_displays=display_names,
        detail=detail,
        verified=True,
    )


# ---------------------------------------------------------------------------
# 4. Run Capture Session
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Delta:
    provenance: DatasetChange
    dataset: CapDataSet


def _indexed(parsed: CapFile) -> dict[tuple[str, str], CapDataSet]:
    result: dict[tuple[str, str], CapDataSet] = {}
    for dataset in parsed.datasets:
        identifier = dataset.data_set_id
        source = dataset.source_euid
        if identifier is None or source is None or (source, identifier) in result:
            msg = "Snapshot dataset IDs are missing or ambiguous."
            raise CaptureError(msg)
        result[source, identifier] = dataset
    return result


def _deltas(
    before: CapFile, after: CapFile,
) -> tuple[list[_Delta], list[DatasetIdentity]]:
    old = _indexed(before)
    current = _indexed(after)
    changes: list[_Delta] = []
    for index, dataset in enumerate(after.datasets):
        identifier = dataset.data_set_id
        source = dataset.source_euid
        if identifier is None or source is None:
            msg = "Dataset has no identity."
            raise CaptureError(msg)
        previous = old.get((source, identifier))
        count = len(dataset.raw_values)
        start: int | None = 0
        kind: Literal["created", "appended", "replaced"] = "created"
        if previous is not None:
            same_metadata = (
                dataset.source_euid == previous.source_euid
                and dataset.unit_id == previous.unit_id
                and dataset.independent_kind == previous.independent_kind
            )
            old_values = (
                previous.numeric_values
                if previous.numeric_values is not None else previous.raw_values
            )
            values = (
                dataset.numeric_values
                if dataset.numeric_values is not None else dataset.raw_values
            )
            if (
                same_metadata and values == old_values
                and dataset.independent_values == previous.independent_values
            ):
                continue
            old_count = len(previous.raw_values)
            appended = (
                same_metadata and count > old_count
                and values[:old_count] == old_values
                and dataset.independent_values[:old_count]
                == previous.independent_values
            )
            start = old_count if appended else None
            kind = "appended" if appended else "replaced"
        provenance = DatasetChange(
            dataset_index=index, dataset_id=identifier,
            source_euid=dataset.source_euid, source_name=dataset.source_name,
            unit_id=dataset.unit_id, kind=kind, sample_start=start,
            sample_count=count,
            new_sample_count=None if start is None else count - start,
        )
        changes.append(_Delta(provenance=provenance, dataset=dataset))
    removed = [
        DatasetIdentity(source_euid=source, dataset_id=identifier)
        for source, identifier in sorted(old.keys() - current.keys())
    ]
    return changes, removed


def _select(changes: list[_Delta], source: str) -> _Delta:
    matches = [
        change for change in changes
        if change.provenance.source_euid == source
        and change.provenance.new_sample_count
    ]
    if len(matches) != 1:
        msg = f"Source {source!r} has no unique newly captured dataset."
        raise CaptureError(msg)
    return matches[0]


def _values(change: _Delta) -> list[float]:
    start = change.provenance.sample_start
    values = change.dataset.numeric_values
    if start is None or values is None or any(v is None for v in values[start:]):
        msg = "Captured samples are replaced, nonnumeric, or missing."
        raise CaptureError(msg)
    return [float(value) for value in values[start:] if value is not None]


def _fit(
    changes: list[_Delta], sources: SourceFit, ordinal: int,
) -> tuple[CapturedFit, RunSamples]:
    x = _select(changes, sources.x_source_euid)
    y = _select(changes, sources.y_source_euid)
    start_x = 0 if x.provenance.sample_start is None else x.provenance.sample_start
    start_y = 0 if y.provenance.sample_start is None else y.provenance.sample_start
    x_coords = (
        [] if x.dataset.independent_values is None
        else x.dataset.independent_values[start_x:]
    )
    y_coords = (
        [] if y.dataset.independent_values is None
        else y.dataset.independent_values[start_y:]
    )
    if (
        x.dataset.independent_kind != y.dataset.independent_kind
        or x_coords != y_coords
        or any(value is None or not value.is_finite() for value in x_coords)
    ):
        msg = "Captured x/y samples are not paired at identical valid coordinates."
        raise CaptureError(msg)
    samples = FitInput(x=_values(x), y=_values(y))
    fit = CapturedFit(
        x=x.provenance, y=y.provenance, result=linear_fit(samples),
    )
    return fit, RunSamples(name=f"run {ordinal}", values=samples.y)


class CaptureSession:
    """Save snapshots and analyze each cycle after its confirmed stop."""

    def __init__(
        self, plan: CapturePlan, save: Callable[[str], FileArtifact],
    ) -> None:
        """Initialize capture session with output directory plan and saver."""
        self.plan: CapturePlan = plan
        self.directory: Path = Path(plan.directory).resolve()
        self.save: Callable[[str], FileArtifact] = save
        self.baseline: FileArtifact | None = None
        self.previous: CapFile | None = None
        self.runs: list[CapturedRun] = []
        self.comparisons: list[RunSamples] = []
        self.comparison_unit: int | None = None

    def begin(self) -> None:
        """Save the baseline before measuring; never reuse a nonempty directory."""
        if self.directory.exists() and (
            not self.directory.is_dir() or any(self.directory.iterdir())
        ):
            msg = "Capture needs a new or empty output directory."
            raise CaptureError(msg)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.baseline = self.save(str(self.directory / "baseline.cap"))
        self.previous = read_cap_file(self.baseline.path)
        _ = _indexed(self.previous)
        if self.plan.fit is not None:
            required = {self.plan.fit.x_source_euid, self.plan.fit.y_source_euid}
            known = {ds.source_euid for ds in self.previous.datasets}
            if not required.issubset(known):
                missing = sorted(required - known)
                msg = f"Fit sources {missing} are missing from baseline."
                raise CaptureError(msg)

    def record(self, ordinal: int, *, interrupted: bool = False) -> None:
        """Save one cycle, identify changed datasets, and optionally fit them."""
        if self.previous is None:
            msg = "Record requires a captured baseline."
            raise CaptureError(msg)
        artifact = self.save(str(self.directory / f"run-{ordinal:03d}.cap"))
        parsed: CapFile | None = None
        changes: list[_Delta] = []
        removed: list[DatasetIdentity] = []
        fit: CapturedFit | None = None
        error: str | None = None
        try:
            parsed = read_cap_file(artifact.path)
            changes, removed = _deltas(self.previous, parsed)
            if self.plan.fit is not None and not interrupted:
                fit, samples = _fit(changes, self.plan.fit, ordinal)
                unit = fit.y.unit_id
                if unit is None or (
                    self.comparison_unit is not None and unit != self.comparison_unit
                ):
                    msg = "Captured comparison requires one consistent declared y unit."
                    raise CaptureError(msg)
                self.comparison_unit = unit
                self.comparisons.append(samples)
        except (AnalysisError, ValidationError, CapFileError) as failure:
            error = str(failure)
            raise
        finally:
            self.runs.append(CapturedRun(
                ordinal=ordinal,
                interrupted=interrupted,
                artifact=artifact,
                datasets=[change.provenance for change in changes],
                removed_datasets=removed,
                fit=fit,
                analysis_error=error,
            ))
            if parsed is not None:
                self.previous = parsed

    record_cycle = record

    def result(self) -> CaptureResult:
        """Collate the saved artifacts and comparative slope/intercept trends."""
        comparison: list[RunComparison] = []
        comparison_error: str | None = None
        if (
            len(self.comparisons) >= MIN_COMPARISON_RUNS
            and self.comparison_unit is not None
        ):
            try:
                comparison = compare_runs(self.comparisons)
            except AnalysisError as error:
                comparison_error = str(error)
        return CaptureResult(
            baseline=self.baseline,
            runs=self.runs,
            comparison=comparison,
            comparison_error=comparison_error,
        )


# ---------------------------------------------------------------------------
# 5. Unified RunManager & Seam
# ---------------------------------------------------------------------------


class RunManager:
    """Deep module managing all run lifecycles and interactions."""

    def __init__(self, app: Capstone) -> None:
        """Initialize run manager bound to a Capstone automation client."""
        self.app = app

    def rename(self, request: RenameRunRequest) -> RenameRunResult:
        """Rename an experimental run in Data Summary."""
        return rename_run(self.app, request)

    def delete(self, request: DeleteRunRequest) -> DeleteRunResult:
        """Delete an experimental run with automatic modal confirmation."""
        return delete_run(self.app, request)

    def set_visibility(
        self, request: SetRunVisibilityRequest,
    ) -> SetRunVisibilityResult:
        """Toggle or assign visibility for runs across displays."""
        return set_run_visibility(self.app, request)

    def manage(self, request: RunRequest) -> RunResult:
        """Single unified entry point for all run operations."""
        if request.action == RunAction.RENAME:
            if request.rename is None:
                msg = "rename request must be provided for RENAME action."
                raise AutomationError(msg)
            return RunResult(action=request.action, rename=self.rename(request.rename))

        if request.action == RunAction.DELETE:
            if request.delete is None:
                msg = "delete request must be provided for DELETE action."
                raise AutomationError(msg)
            return RunResult(action=request.action, delete=self.delete(request.delete))

        if request.action == RunAction.SET_VISIBILITY:
            if request.visibility is None:
                msg = "visibility request must be provided for SET_VISIBILITY action."
                raise AutomationError(msg)
            return RunResult(
                action=request.action,
                visibility=self.set_visibility(request.visibility),
            )

        msg = f"Unsupported RunAction: {request.action}"
        raise AutomationError(msg)


def manage_run(app: Capstone, request: RunRequest) -> RunResult:
    """Functional convenience wrapper for the unified run management seam."""
    return RunManager(app).manage(request)
