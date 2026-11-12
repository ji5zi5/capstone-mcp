# Copyright 2026 Capstone MCP contributors.
"""Input and attachment preconditions that fail before touching Capstone."""

from typing import TYPE_CHECKING, cast
from unittest.mock import Mock

import psutil
import pytest
import win32gui
import win32process
from pywinauto.application import ProcessNotFoundError

from capstone_mcp import desktop
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Bounds, Window

if TYPE_CHECKING:
    from pywinauto.controls.uiawrapper import UIAWrapper

MAIN = 1
DIALOG = 2
SHADOW = 11
BOUNDS = Bounds(left=0, top=0, right=5, bottom=5)


def _only_dialog_enabled(handle: int) -> bool:
    return handle == DIALOG


def _window_class(handle: int) -> str:
    return "SysShadow" if handle == SHADOW else "QtPopup"


def _blocked_app(monkeypatch: pytest.MonkeyPatch) -> tuple[Capstone, Mock]:
    app = Capstone()
    windows = [
        Window(handle=DIALOG, title="About", process_id=7, bounds=BOUNDS),
        Window(handle=MAIN, title="experiment.cap", process_id=7, bounds=BOUNDS),
    ]
    monkeypatch.setattr(app, "windows", Mock(return_value=windows))
    monkeypatch.setattr(app, "window", Mock(return_value=Mock()))
    monkeypatch.setattr(app, "require_foreground", Mock())
    activate = Mock()
    monkeypatch.setattr(desktop, "HwndWrapper", activate)
    return app, activate


def test_modal_dialog_blocks_keyboard_input_and_names_the_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an About dialog has disabled the experiment window.
    app, activate = _blocked_app(monkeypatch)
    monkeypatch.setattr(win32gui, "IsWindowEnabled", _only_dialog_enabled)
    # When / Then: the shortcut is refused instead of landing in the dialog.
    with pytest.raises(AutomationError, match=r"modal dialog.*2: About"):
        _ = app.keys(MAIN, "^o")
    activate.assert_not_called()


def test_enabled_window_is_activated_before_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app, activate = _blocked_app(monkeypatch)
    monkeypatch.setattr(win32gui, "IsWindowEnabled", Mock(return_value=True))
    # When
    _ = app.focus_window(MAIN)
    # Then
    activate.assert_called_once_with(MAIN)


def test_menu_shadow_windows_are_not_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a Qt popup menu and the system shadow window that follows it.
    app = Capstone()
    app.pid = 7
    monkeypatch.setattr(psutil, "pid_exists", Mock(return_value=True))
    monkeypatch.setattr(desktop, "find_windows", Mock(return_value=[10, SHADOW]))
    monkeypatch.setattr(win32gui, "GetClassName", _window_class)
    monkeypatch.setattr(win32gui, "GetWindowRect", Mock(return_value=(0, 0, 5, 5)))
    monkeypatch.setattr(win32gui, "GetWindowText", Mock(return_value="Capstone"))
    # When / Then
    assert [window.handle for window in app.windows()] == [10]


def test_attach_explains_an_unsupported_build_when_installed_capstone_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: only the Microsoft Store edition is running.
    store = "13340: C:/Program Files/WindowsApps/PASCO/Capstone/Capstone.exe"
    monkeypatch.setattr(desktop, "capstone_processes", Mock(return_value=([], [store])))
    start = Mock()
    application = Mock(
        connect=Mock(side_effect=ProcessNotFoundError("not found")), start=start,
    )
    monkeypatch.setattr(desktop, "Application", Mock(return_value=application))
    # When / Then
    with pytest.raises(AutomationError, match=r"not running.*launch=true.*13340"):
        _ = Capstone().attach()
    start.assert_not_called()


def test_attach_requires_a_process_id_when_several_instances_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setattr(desktop, "capstone_processes", Mock(return_value=([4, 9], [])))
    connect = Mock()
    monkeypatch.setattr(
        desktop, "Application", Mock(return_value=Mock(connect=connect)),
    )
    # When / Then: no instance is chosen on the caller's behalf.
    with pytest.raises(AutomationError, match="process_id: 4, 9"):
        _ = Capstone().attach()
    connect.assert_not_called()


def _control(handle: int, parent: Mock | None, top: Mock | None = None) -> Mock:
    node = Mock(handle=handle)
    node.parent = Mock(return_value=parent)
    node.top_level_parent = Mock(return_value=top or node)
    node.rectangle = Mock(return_value=Mock(left=0, top=0, right=4, bottom=4))
    node.process_id = Mock(return_value=7)
    return node


def test_dialog_button_is_clicked_through_its_own_enabled_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Qt lists the modal dialog beneath the experiment window it disables.
    app, activate = _blocked_app(monkeypatch)
    app.pid = 7
    monkeypatch.setattr(win32gui, "IsWindowEnabled", _only_dialog_enabled)
    owner = _control(MAIN, None)
    dialog = _control(DIALOG, owner, owner)
    button = _control(0, dialog, owner)
    app.refs["ref"] = cast("UIAWrapper", button)
    monkeypatch.setattr(win32gui, "WindowFromPoint", Mock(return_value=DIALOG))
    monkeypatch.setattr(win32gui, "GetAncestor", Mock(return_value=DIALOG))
    # When
    _ = app.act("ref", Action.INVOKE)
    # Then: the dialog, not its disabled owner, is activated and clicked.
    activate.assert_called_once_with(DIALOG)
    click = cast("Mock", button.click_input)
    click.assert_called_once()


def test_control_behind_a_modal_dialog_is_not_clicked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a toolbar button of the disabled experiment window.
    app, activate = _blocked_app(monkeypatch)
    app.pid = 7
    monkeypatch.setattr(win32gui, "IsWindowEnabled", _only_dialog_enabled)
    owner = _control(MAIN, None)
    button = _control(0, owner, owner)
    app.refs["ref"] = cast("UIAWrapper", button)
    # When / Then
    with pytest.raises(AutomationError, match=r"modal dialog.*2: About"):
        _ = app.act("ref", Action.INVOKE)
    activate.assert_not_called()
    click = cast("Mock", button.click_input)
    click.assert_not_called()


def test_dialog_button_under_a_second_dialog_is_not_clicked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a captioned window lies over the dialog button's click point.
    app, _activate = _blocked_app(monkeypatch)
    app.pid = 7
    monkeypatch.setattr(win32gui, "IsWindowEnabled", _only_dialog_enabled)
    owner = _control(MAIN, None)
    dialog = _control(DIALOG, owner, owner)
    button = _control(0, dialog, owner)
    app.refs["ref"] = cast("UIAWrapper", button)
    monkeypatch.setattr(win32gui, "WindowFromPoint", Mock(return_value=99))
    monkeypatch.setattr(win32gui, "GetAncestor", Mock(return_value=99))
    monkeypatch.setattr(win32gui, "GetWindowLong", Mock(return_value=0x00C00000))
    # When / Then
    with pytest.raises(AutomationError, match="covered by another window"):
        _ = app.act("ref", Action.INVOKE)
    click = cast("Mock", button.click_input)
    click.assert_not_called()


def test_exited_capstone_is_reported_instead_of_an_empty_window_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the attached process ended, for example because the user closed it.
    app = Capstone()
    app.pid = 7
    monkeypatch.setattr(psutil, "pid_exists", Mock(return_value=False))
    find = Mock()
    monkeypatch.setattr(desktop, "find_windows", find)
    # When / Then
    with pytest.raises(AutomationError, match=r"has exited.*capstone_attach"):
        _ = app.windows()
    find.assert_not_called()


def _foreground(monkeypatch: pytest.MonkeyPatch, owner: int) -> Capstone:
    app = Capstone()
    app.pid = 7
    monkeypatch.setattr(win32gui, "GetForegroundWindow", Mock(return_value=55))
    monkeypatch.setattr(win32gui, "GetWindowText", Mock(return_value="Other App"))
    monkeypatch.setattr(
        win32process, "GetWindowThreadProcessId", Mock(return_value=(1, owner)),
    )
    return app


def test_input_is_refused_when_another_application_keeps_the_foreground(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Windows declined to activate Capstone.
    app = _foreground(monkeypatch, owner=99)
    # When / Then: the keys would otherwise reach the other application.
    with pytest.raises(AutomationError, match=r"foreground.*Other App"):
        app.require_foreground()


def test_input_proceeds_when_a_capstone_window_is_in_front(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _foreground(monkeypatch, owner=7)
    app.require_foreground()
