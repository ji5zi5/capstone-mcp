# Copyright 2026 Capstone MCP contributors.
"""Tool router for desktop UI inspection, window attachment, and emergency interaction."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal

from mcp.server.fastmcp import Image
from mcp.types import ToolAnnotations
from pydantic import Field, TypeAdapter

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.models import (
    Action,
    Button,
    Point,
    Result,
    Snapshot,
    Window,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP

    type NativeCaller = Callable[..., Awaitable[Any]]

WINDOWS: Final = TypeAdapter(list[Window])
TEXT: Final = TypeAdapter(str)


async def capstone_action(
    native: NativeCaller,
    ref: str,
    action: Action,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Activate by click (invoke), or use UIA toggle/select/expand/collapse/focus."""
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="action",
                ref=ref,
                action=action,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


async def capstone_read_value(native: NativeCaller, ref: str) -> str:
    """Read literal current text from a control's UIA Value pattern."""
    return TEXT.validate_python(
        await native(
            NativeRequest(
                operation="read_value",
                ref=ref,
            ),
        ),
    )


async def capstone_set_value(native: NativeCaller, ref: str, value: str) -> Result:
    """Set literal text in a control supporting the UIA Value pattern."""
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="set_value",
                ref=ref,
                value=value,
            ),
            mutates=True,
        ),
    )


async def capstone_click(  # noqa: PLR0913
    native: NativeCaller,
    handle: int,
    point: Point,
    button: Button = Button.LEFT,
    *,
    double: bool = False,
    allow_foreground: bool = True,
) -> Result:
    """Click window-relative pixels; foreground input is enabled by default."""
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="click",
                handle=handle,
                point=point,
                button=button,
                double=double,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


async def capstone_drag(
    native: NativeCaller,
    handle: int,
    start: Point,
    end: Point,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Drag between window-relative pixels; hard timeout leaves outcome uncertain."""
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="drag",
                handle=handle,
                point=start,
                end=end,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


async def capstone_scroll(
    native: NativeCaller,
    handle: int,
    point: Point,
    notches: int,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Scroll at window-relative pixels; positive notches scroll upward."""
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="scroll",
                handle=handle,
                point=point,
                notches=notches,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


async def capstone_keys(
    native: NativeCaller,
    handle: int,
    keys: str,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Send pywinauto key syntax: ^o, {ESC}, {ENTER}, %{F4}. Changes focus."""
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="keys",
                handle=handle,
                value=keys,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


async def capstone_type_text(
    native: NativeCaller,
    handle: int,
    text: str,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Type literal Unicode text in the focused field, escaping shortcut syntax."""
    escaped = "".join(
        "{" + char + "}" if char in "+^%~(){}" else char for char in text
    )
    return Result.model_validate(
        await native(
            NativeRequest(
                operation="keys",
                handle=handle,
                value=escaped,
                allow_foreground=allow_foreground,
                unicode_input=True,
            ),
            mutates=True,
        ),
    )


async def _dispatch_mouse_ui(  # noqa: PLR0913, PLR0917
    native: NativeCaller,
    action: str,
    handle: int,
    point: Point | None,
    start: Point | None,
    end: Point | None,
    *,
    button: Button,
    notches: int,
    allow_foreground: bool,
) -> Result:
    if action in ("click", "double_click"):
        target_point = point or Point(x=0, y=0)
        return await capstone_click(
            native,
            handle,
            target_point,
            button=button,
            double=(action == "double_click"),
            allow_foreground=allow_foreground,
        )
    if action == "drag":
        if start is None or end is None:
            msg = "Action 'drag' requires both start and end points."
            raise ValueError(msg)
        return await capstone_drag(
            native, handle, start, end, allow_foreground=allow_foreground,
        )
    target_point = point or Point(x=0, y=0)
    return await capstone_scroll(
        native, handle, target_point, notches, allow_foreground=allow_foreground,
    )


async def _dispatch_control_ui(  # noqa: PLR0913
    native: NativeCaller,
    action: str,
    ref: str | None,
    value: str | None,
    ui_action: Action | None,
    *,
    allow_foreground: bool,
) -> Result:
    if ref is None:
        msg = f"Action '{action}' requires ref."
        raise ValueError(msg)
    if action == "action":
        if ui_action is None:
            msg = "Action 'action' requires both ref and ui_action."
            raise ValueError(msg)
        return await capstone_action(
            native, ref, ui_action, allow_foreground=allow_foreground,
        )
    if action == "read_value":
        detail = await capstone_read_value(native, ref)
        return Result(detail=detail, delivered=True)
    return await capstone_set_value(native, ref, value or "")


def register_ui_tools(
    mcp: FastMCP[None],
    native: NativeCaller,
) -> dict[str, Any]:
    """Register all desktop UI inspection and interaction tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Attach to installed Capstone",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_attach(
        *,
        launch: bool = False,
        process_id: Annotated[int, Field(gt=0)] | None = None,
    ) -> list[Window]:
        """Attach to installed Capstone, optionally selecting an exact process ID."""
        return WINDOWS.validate_python(
            await native(
                NativeRequest(
                    operation="attach",
                    launch=launch,
                    process_id=process_id,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Capstone windows",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_windows() -> list[Window]:
        """List Capstone windows, including file dialogs and modal dialogs."""
        return WINDOWS.validate_python(
            await native(NativeRequest(operation="windows")),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Inspect window controls and action references",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_snapshot(
        handle: int,
        depth: Annotated[int, Field(ge=1, le=30)] = 12,
        limit: Annotated[int, Field(ge=1, le=3000)] = 800,
        query: Annotated[str, Field(max_length=200)] = "",
        control_types: Annotated[list[str], Field(max_length=20)] | None = None,
    ) -> Snapshot:
        """Read control names, roles, bounds, and fresh action references.

        A full experiment window holds hundreds of controls. Pass query, a
        case-insensitive substring of a control's name or automation_id, and/or
        control_types such as ["Button", "CheckBox"] to return only the matches.
        depth and limit still bound the traversal, so truncated=true means an
        unvisited control may match. Custom-drawn graph toolbars are not exposed.
        """
        return Snapshot.model_validate(
            await native(
                NativeRequest(
                    operation="snapshot",
                    handle=handle,
                    depth=depth,
                    limit=limit,
                    query=query,
                    control_types=control_types or [],
                ),
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Capture window pixels",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_screenshot(
        handle: int,
        *,
        scale: float = 1.0,
        crop_region: list[int] | None = None,
    ) -> Image:
        """Capture PNG pixels at native resolution, optionally scaled or cropped.

        Does not raise the target window to the foreground.
        """
        encoded = TEXT.validate_python(
            await native(
                NativeRequest(
                    operation="screenshot",
                    handle=handle,
                    scale=scale,
                    crop_region=crop_region,
                ),
            ),
        )
        return Image(data=base64.b64decode(encoded, validate=True), format="png")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Emergency UI interaction escape hatch",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_interact_ui(  # noqa: PLR0913
        action: Annotated[
            Literal[
                "click",
                "double_click",
                "drag",
                "scroll",
                "keys",
                "type",
                "action",
                "read_value",
                "set_value",
            ],
            Field(description="Low-level UI action to perform."),
        ],
        handle: Annotated[
            int,
            Field(description="Target window handle (for mouse/keyboard actions)."),
        ] = 0,
        *,
        ref: Annotated[
            str | None,
            Field(
                description=(
                    "Control ref from capstone_snapshot "
                    "(for action, read_value, set_value)."
                ),
            ),
        ] = None,
        point: Annotated[
            Point | None,
            Field(description="Target coordinate for click or scroll."),
        ] = None,
        start: Annotated[
            Point | None,
            Field(description="Start coordinate for drag."),
        ] = None,
        end: Annotated[
            Point | None,
            Field(description="End coordinate for drag."),
        ] = None,
        button: Annotated[
            Button,
            Field(description="Mouse button (left, right, middle)."),
        ] = Button.LEFT,
        notches: Annotated[
            int,
            Field(ge=-100, le=100, description="Wheel scroll notches (positive=up)."),
        ] = 0,
        keys: Annotated[
            str | None,
            Field(description="Pywinauto key shortcut string, e.g. '{ENTER}', '^o'."),
        ] = None,
        text: Annotated[
            str | None,
            Field(description="Literal text to type into focused control."),
        ] = None,
        value: Annotated[
            str | None,
            Field(description="Literal text value to set via UIA Value pattern."),
        ] = None,
        ui_action: Annotated[
            Action | None,
            Field(
                description=(
                    "UIA action for 'action' type: invoke, toggle, select, "
                    "expand, collapse, focus."
                ),
            ),
        ] = None,
        allow_foreground: Annotated[
            bool,
            Field(description="Whether to bring window to foreground for physical input."),
        ] = True,
    ) -> Result:
        """Consolidated UI interaction escape hatch for unmodeled modals and controls.

        Dispatches low-level mouse, keyboard, and UIA primitives:
        - click / double_click: Physical click at point coordinates
        - drag: Drag mouse from start to end coordinates
        - scroll: Wheel scroll by specified notches at point
        - keys: Send pywinauto shortcut key sequences ({ENTER}, {ESC}, etc.)
        - type: Type literal Unicode text into focused field
        - action: Perform UIA action (invoke, toggle, select, expand, collapse, focus)
          on control ref
        - read_value: Read current text value of control ref (returned in Result.detail)
        - set_value: Set current text value of control ref
        """
        if action in ("click", "double_click", "drag", "scroll"):
            return await _dispatch_mouse_ui(
                native,
                action,
                handle,
                point,
                start,
                end,
                button=button,
                notches=notches,
                allow_foreground=allow_foreground,
            )
        if action == "keys":
            return await capstone_keys(
                native, handle, keys or "", allow_foreground=allow_foreground,
            )
        if action == "type":
            return await capstone_type_text(
                native, handle, text or "", allow_foreground=allow_foreground,
            )
        if action in ("action", "read_value", "set_value"):
            return await _dispatch_control_ui(
                native,
                action,
                ref,
                value,
                ui_action,
                allow_foreground=allow_foreground,
            )
        msg = f"Unknown action: {action}"
        raise ValueError(msg)

    return {
        "capstone_attach": capstone_attach,
        "capstone_windows": capstone_windows,
        "capstone_snapshot": capstone_snapshot,
        "capstone_screenshot": capstone_screenshot,
        "capstone_interact_ui": capstone_interact_ui,
    }


__all__ = [
    "register_ui_tools",
]
