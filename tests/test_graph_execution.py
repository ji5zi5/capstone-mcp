# Copyright 2026 Capstone MCP contributors.
"""Deterministic stale-frame and partial-execution checks without desktop input."""

from io import BytesIO
from typing import override

import pytest
from PIL import Image

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.graph_execution import GraphCapture, GraphOperationError
from capstone_mcp.models import Bounds, Window
from capstone_mcp.native_dispatch import NativeDesktop


class FrameDesktop(Capstone):
    """An observed window whose pixels and position change only when a test says so."""

    def __init__(self) -> None:
        super().__init__()
        self.bounds: Bounds = Bounds(left=0, top=0, right=20, bottom=20)
        self.color: str = "white"

    @override
    def flush_paint(self, handle: int) -> None:
        assert handle == 1

    @override
    def windows(self) -> list[Window]:
        return [Window(handle=1, title="graph", process_id=1, bounds=self.bounds)]

    @override
    def screenshot(self, handle: int) -> bytes:
        assert handle == 1
        with BytesIO() as output, Image.new("RGB", (20, 20), self.color) as image:
            image.save(output, format="PNG")
            return output.getvalue()

    @override
    def graph_screenshot(self, handle: int, *, activate: bool = False) -> bytes:
        del activate
        return self.screenshot(handle)


@pytest.mark.parametrize("change", ["pixels", "window"])
def test_stale_frame_refuses_input(change: str) -> None:
    # Given: a real issued frame from the deterministic adapter.
    runtime = NativeDesktop()
    app = FrameDesktop()
    runtime.app = app
    calls: list[str] = []
    runtime.handlers = {
        **runtime.handlers,
        "select_graph_measurement": lambda _r: calls.append("input"),
    }
    capture = GraphCapture.model_validate(runtime.dispatch(
        NativeRequest(operation="observe_graph", handle=1),
    ))
    if change == "pixels":
        app.color = "black"
    else:
        app.bounds = Bounds(left=10, top=0, right=30, bottom=20)
    # When
    with pytest.raises(GraphOperationError) as error:
        _ = runtime.dispatch(NativeRequest(
            operation="select_graph_measurement", handle=1,
            frame_id=capture.frame.frame_id,
        ))
    # Then: a moved window or changed graph cannot receive the old coordinate.
    assert error.value.failure.code == "STALE_FRAME"
    assert not error.value.failure.graph_input_may_have_been_sent
    assert calls == []


def test_matching_frame_is_consumed_once() -> None:
    # Given
    runtime = NativeDesktop()
    runtime.app = FrameDesktop()
    calls: list[str] = []
    runtime.handlers = {
        **runtime.handlers,
        "select_graph_measurement": lambda _r: calls.append("input"),
    }
    capture = GraphCapture.model_validate(runtime.dispatch(
        NativeRequest(operation="observe_graph", handle=1),
    ))
    request = NativeRequest(
        operation="select_graph_measurement", handle=1,
        frame_id=capture.frame.frame_id,
    )
    # When
    _ = runtime.dispatch(request)
    with pytest.raises(GraphOperationError) as error:
        _ = runtime.dispatch(request)
    # Then
    assert calls == ["input"]
    assert error.value.failure.code == "FRAME_REQUIRED"


def test_failure_after_confirmed_step_preserves_partial_progress() -> None:
    # Given: a handler that has confirmed one change before a later UI failure.
    runtime = NativeDesktop()
    runtime.app = FrameDesktop()

    def partially_applied(_request: NativeRequest) -> None:
        progress = runtime.graph_progress
        assert progress is not None
        progress.confirmed("fit_1_verified")
        progress.begin_input("select_fit_2")
        msg = "provider disconnected"
        raise AutomationError(msg)

    runtime.handlers = {**runtime.handlers, "set_graph_fits": partially_applied}
    capture = GraphCapture.model_validate(runtime.dispatch(
        NativeRequest(operation="observe_graph", handle=1),
    ))
    # When
    with pytest.raises(GraphOperationError) as error:
        _ = runtime.dispatch(NativeRequest(
            operation="set_graph_fits", handle=1, frame_id=capture.frame.frame_id,
        ))
    # Then: recovery cannot claim that no input was sent or blindly retry.
    failure = error.value.failure
    assert failure.completed_steps == ["fit_1_verified"]
    assert failure.stage == "select_fit_2"
    assert failure.graph_input_may_have_been_sent
    assert failure.next_action == "read_graph"
    assert runtime.last_frame is None
