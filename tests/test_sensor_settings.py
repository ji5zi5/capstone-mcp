# Copyright 2026 Capstone MCP contributors.
"""Test exact sensor selection and bounded native rate traversal."""

from collections.abc import Callable
from typing import override

import pytest

from capstone_mcp import acquisition, sensor_settings
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Bounds, Control, Result, Snapshot, Window


class SettingsAdapter(Capstone):
    """Mutable UI fake whose actions synchronously update observed state."""

    def __init__(
        self, *, recording: bool = False, duplicate_sensor: bool = False,
    ) -> None:
        super().__init__()
        self.recording: bool = recording
        self.duplicate_sensor: bool = duplicate_sensor
        self.sensor: str = "Blue"
        self.rates: list[str] = ["25 widget/s", "50 widget/s", "100 widget/s"]
        self.rate_index: int = 1
        self.menu_open: bool = False
        self.rate_inputs: int = 0

    @property
    def rate(self) -> str:
        return self.rates[self.rate_index]

    @override
    def windows(self) -> list[Window]:
        windows = [self._window(1, "scratch")]
        if self.menu_open:
            windows.append(self._window(2, "PASCO Capstone"))
        return windows

    @override
    def snapshot(self, handle: int, depth: int, limit: int) -> Snapshot:
        del depth, limit
        controls = self._menu_controls() if handle == 2 else self._main_controls()
        return Snapshot(
            window=self._window(handle, "popup" if handle == 2 else "scratch"),
            controls=controls,
            truncated=False,
        )

    @override
    def act(
        self, ref: str, action: Action, *, allow_foreground: bool = False,
    ) -> Result:
        assert action == Action.INVOKE
        assert allow_foreground
        match ref:
            case "selector":
                self.menu_open = True
            case "sensor-red" | "sensor-red-duplicate":
                self.sensor = "Red"
                self.rate_index = 0
                self.menu_open = False
            case "sensor-blue":
                self.sensor = "Blue"
                self.rate_index = 1
                self.menu_open = False
            case "increase":
                self.rate_index += 1
                self.rate_inputs += 1
            case "decrease":
                self.rate_index -= 1
                self.rate_inputs += 1
            case unreachable:
                raise AssertionError(unreachable)
        return Result(detail="state changed")

    @override
    def keys(
        self, handle: int, keys: str, *, allow_foreground: bool = True,
        unicode_input: bool = False,
    ) -> Result:
        assert handle == 1
        assert keys == "{ESC}"
        assert allow_foreground
        assert not unicode_input
        self.menu_open = False
        return Result(detail="menu closed")

    @staticmethod
    def _window(handle: int, title: str) -> Window:
        return Window(
            handle=handle,
            title=title,
            process_id=1,
            bounds=Bounds(left=0, top=0, right=100, bottom=100),
        )

    def _main_controls(self) -> list[Control]:
        return [
            self._control(
                "selector", self.sensor, "SamplingRateTargetSelector", "Button",
            ),
            self._control("rate", self.rate, "SamplingRateLabel", "Text"),
            self._control(
                "increase", "", "IncreaseSampleRateButton", "Button",
                enabled=self.rate_index < len(self.rates) - 1,
            ),
            self._control(
                "decrease", "", "DecreaseSampleRateButton", "Button",
                enabled=self.rate_index > 0,
            ),
        ]

    def _menu_controls(self) -> list[Control]:
        controls = [
            self._control("sensor-red", "Red", "", "MenuItem"),
            self._control("sensor-blue", "Blue", "", "MenuItem"),
        ]
        if self.duplicate_sensor:
            controls.append(
                self._control(
                    "sensor-red-duplicate", "Red", "", "MenuItem",
                ),
            )
        return controls

    @staticmethod
    def _control(
        ref: str, name: str, suffix: str, control_type: str, *,
        enabled: bool = True,
    ) -> Control:
        return Control(
            ref=ref,
            parent=None,
            name=name,
            control_type=control_type,
            automation_id="control." + suffix,
            enabled=enabled,
            visible=True,
            bounds=Bounds(left=0, top=0, right=10, bottom=10),
        )


def install_observer(
    monkeypatch: pytest.MonkeyPatch, adapter: SettingsAdapter,
) -> None:
    def observed(
        _app: Capstone, _handle: int,
    ) -> tuple[acquisition.RecordingStatus, str]:
        return acquisition.RecordingStatus(
            window_handle=1,
            process_id=1,
            recording=adapter.recording,
            control_enabled=True,
            time_display="00:00.00",
            sampling_rate_display=adapter.rate,
        ), "record"

    monkeypatch.setattr(sensor_settings, "observe_recording", observed)


def test_select_sensor_reports_exact_observed_before_and_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = SettingsAdapter()
    install_observer(monkeypatch, app)
    # When
    result = sensor_settings.select_sensor(
        app,
        1,
        sensor_settings.SensorSelectionRequest(sensor="Red"),
    )
    # Then
    assert result.model_dump() == {
        "requested_sensor": "Red",
        "before_sensor": "Blue",
        "after_sensor": "Red",
        "before_sampling_rate": "50 widget/s",
        "after_sampling_rate": "25 widget/s",
        "changed": True,
    }


def test_select_sensor_rejects_duplicate_exact_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = SettingsAdapter(duplicate_sensor=True)
    install_observer(monkeypatch, app)
    # When / Then
    with pytest.raises(AutomationError, match="not unique"):
        _ = sensor_settings.select_sensor(
            app,
            1,
            sensor_settings.SensorSelectionRequest(sensor="Red"),
        )
    assert app.sensor == "Blue"
    assert not app.menu_open


def test_target_sampling_rate_attains_exact_native_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = SettingsAdapter()
    install_observer(monkeypatch, app)
    # When
    result = sensor_settings.target_sampling_rate(
        app,
        1,
        sensor_settings.SamplingRateRequest(
            sensor="Blue",
            target="100.00 widget/s",
        ),
    )
    # Then
    assert (result.before, result.after, result.inputs_delivered) == (
        "50 widget/s",
        "100 widget/s",
        1,
    )


def test_unsupported_sampling_rate_restores_original_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = SettingsAdapter()
    install_observer(monkeypatch, app)
    # When / Then
    with pytest.raises(AutomationError, match="unsupported"):
        _ = sensor_settings.target_sampling_rate(
            app,
            1,
            sensor_settings.SamplingRateRequest(
                sensor="Blue",
                target="75 widget/s",
            ),
        )
    assert app.rate == "50 widget/s"
    assert app.rate_inputs == 2


def test_lower_sampling_rate_does_not_search_higher_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = SettingsAdapter()
    install_observer(monkeypatch, app)
    # When
    result = sensor_settings.target_sampling_rate(
        app, 1,
        sensor_settings.SamplingRateRequest(sensor="Blue", target="25 widget/s"),
    )
    # Then
    assert result.after == "25 widget/s"
    assert app.rate_inputs == 1


def test_rate_unit_mismatch_does_not_deliver_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    app = SettingsAdapter()
    install_observer(monkeypatch, app)
    # When / Then
    with pytest.raises(AutomationError):
        _ = sensor_settings.target_sampling_rate(
            app, 1,
            sensor_settings.SamplingRateRequest(sensor="Blue", target="100 Hz"),
        )
    assert app.rate_inputs == 0


@pytest.mark.parametrize("fail_on_input", [1, 2])
def test_post_click_read_failure_reports_uncertainty_without_reverse_input(
    monkeypatch: pytest.MonkeyPatch, fail_on_input: int,
) -> None:
    app = SettingsAdapter()
    app.rates = ["25 widget/s", "50 widget/s", "100 widget/s", "200 widget/s"]
    install_observer(monkeypatch, app)
    original_snapshot = app.snapshot

    def snapshot(handle: int, depth: int, limit: int) -> Snapshot:
        if app.rate_inputs == fail_on_input:
            msg = "read failed after delivered input"
            raise AutomationError(msg)
        return original_snapshot(handle, depth, limit)

    monkeypatch.setattr(app, "snapshot", snapshot)
    with pytest.raises(AutomationError, match="Restoration was not verified") as exc:
        _ = sensor_settings.target_sampling_rate(
            app, 1,
            sensor_settings.SamplingRateRequest(sensor="Blue", target="175 widget/s"),
        )
    assert app.rate_inputs == fail_on_input
    assert app.rate_index == 1 + fail_on_input
    assert isinstance(exc.value.__cause__, AutomationError)


def test_failed_restore_reports_unverified_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = SettingsAdapter()
    install_observer(monkeypatch, app)
    original_act = app.act

    def act(
        ref: str, action: Action, *, allow_foreground: bool = False,
    ) -> Result:
        if ref == "decrease":
            msg = "reverse input failed"
            raise AutomationError(msg)
        return original_act(ref, action, allow_foreground=allow_foreground)

    monkeypatch.setattr(app, "act", act)
    with pytest.raises(
        AutomationError, match=r"restoration .* failed or is unverified",
    ):
        _ = sensor_settings.target_sampling_rate(
            app, 1,
            sensor_settings.SamplingRateRequest(sensor="Blue", target="75 widget/s"),
        )
    assert app.rate == "100 widget/s"
    assert app.rate_inputs == 1


def select_red(app: SettingsAdapter) -> sensor_settings.SensorSelection:
    return sensor_settings.select_sensor(
        app,
        1,
        sensor_settings.SensorSelectionRequest(sensor="Red"),
    )


def target_high_rate(
    app: SettingsAdapter,
) -> sensor_settings.SamplingRateSelection:
    return sensor_settings.target_sampling_rate(
        app,
        1,
        sensor_settings.SamplingRateRequest(
            sensor="Blue",
            target="100 widget/s",
        ),
    )


@pytest.mark.parametrize(
    "action",
    [select_red, target_high_rate],
)
def test_sensor_settings_require_stopped_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    action: Callable[
        [SettingsAdapter],
        sensor_settings.SensorSelection | sensor_settings.SamplingRateSelection,
    ],
) -> None:
    # Given
    app = SettingsAdapter(recording=True)
    install_observer(monkeypatch, app)
    # When / Then
    with pytest.raises(AutomationError, match="Stop recording"):
        _ = action(app)
    assert app.sensor == "Blue"
    assert app.rate == "50 widget/s"
