# Copyright 2026 Capstone MCP contributors.
"""Filtered snapshots return only matching controls with usable references."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import pytest

from capstone_mcp.desktop import Capstone

if TYPE_CHECKING:
    from pywinauto.controls.uiawrapper import UIAWrapper


class FakeNode:
    def __init__(
        self, name: str, control_type: str, automation_id: str = "",
        children: tuple["FakeNode", ...] = (),
    ) -> None:
        self.handle: int = 0
        self.element_info: SimpleNamespace = SimpleNamespace(
            name=name, control_type=control_type, automation_id=automation_id,
        )
        self.children: tuple[FakeNode, ...] = children

    def iter_children(self) -> Iterator["FakeNode"]:
        return iter(self.children)

    def is_enabled(self) -> bool:
        return True

    def is_visible(self) -> bool:
        return True

    def rectangle(self) -> SimpleNamespace:
        return SimpleNamespace(left=0, top=0, right=4, bottom=4)

    def window_text(self) -> str:
        return "experiment.cap"

    def process_id(self) -> int:
        return 7


def _app(monkeypatch: pytest.MonkeyPatch) -> Capstone:
    root = FakeNode("experiment.cap", "Window", children=(
        FakeNode("Record", "Button", "RecordButton"),
        FakeNode("Calculator", "CheckBox", "Palette.ObjNameCalculator"),
        FakeNode("Ready", "Text"),
    ))
    app = Capstone()
    window = cast("UIAWrapper", cast("object", root))
    monkeypatch.setattr(app, "window", Mock(return_value=window))
    return app


def test_unfiltered_snapshot_lists_every_visited_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _app(monkeypatch).snapshot(1, 12, 800)
    assert [c.name for c in snapshot.controls] == [
        "experiment.cap", "Record", "Calculator", "Ready",
    ]


def test_query_matches_names_case_insensitively_and_keeps_usable_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = _app(monkeypatch)
    # When
    snapshot = app.matching_snapshot(1, 12, 800, query="calc")
    # Then: only the match is returned and only its reference can be acted on.
    assert [c.name for c in snapshot.controls] == ["Calculator"]
    assert list(app.refs) == [snapshot.controls[0].ref]
    assert not snapshot.truncated


def test_query_also_matches_automation_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _app(monkeypatch).matching_snapshot(1, 12, 800, query="RECORDBUTTON")
    assert [c.name for c in snapshot.controls] == ["Record"]


def test_control_types_restrict_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _app(monkeypatch).matching_snapshot(
        1, 12, 800, control_types=["Button", "Text"],
    )
    assert [c.name for c in snapshot.controls] == ["Record", "Ready"]


def test_limit_bounds_the_visit_so_an_unvisited_match_is_reported_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # When: the traversal stops before reaching the matching control.
    snapshot = _app(monkeypatch).matching_snapshot(1, 12, 2, query="ready")
    # Then
    assert snapshot.controls == []
    assert snapshot.truncated
