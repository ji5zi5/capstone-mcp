# Copyright 2026 Capstone MCP contributors.
"""Tests for screenshot scaling and cropping."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Window


def test_screenshot_invalid_scale_rejected() -> None:
    app = Capstone()
    with pytest.raises(AutomationError, match="scale"):
        _ = app.screenshot(0, scale=0.0)

    with pytest.raises(AutomationError, match="scale"):
        _ = app.screenshot(0, scale=1.5)

    with pytest.raises(AutomationError, match="scale"):
        _ = app.screenshot(0, scale=-0.5)


def test_screenshot_invalid_crop_region_rejected() -> None:
    app = Capstone()
    with pytest.raises(AutomationError, match="crop_region"):
        _ = app.screenshot(0, crop_region=[0, 0, 100])


def test_screenshot_scaling_and_cropping() -> None:
    app = Capstone()
    mock_window = Window(
        handle=12345, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=500),
    )
    app.window = MagicMock(return_value=mock_window)

    # Create dummy 1000x500 image
    original_img = Image.new("RGB", (1000, 500), color="blue")

    with patch("capstone_mcp.desktop.ImageGrab.grab", return_value=original_img):
        # 1. Scaling only: scale=0.5 -> 500x250
        raw_scaled = app.screenshot(12345, scale=0.5)
        scaled_img = Image.open(BytesIO(raw_scaled))
        assert scaled_img.size == (500, 250)

        # 2. Cropping only: crop_region=[100, 50, 500, 350] -> 400x300
        raw_cropped = app.screenshot(12345, crop_region=[100, 50, 500, 350])
        cropped_img = Image.open(BytesIO(raw_cropped))
        assert cropped_img.size == (400, 300)

        # 3. Cropping and scaling: crop to 400x300 then scale 0.5 -> 200x150
        raw_crop_scale = app.screenshot(
            12345, scale=0.5, crop_region=[100, 50, 500, 350],
        )
        crop_scale_img = Image.open(BytesIO(raw_crop_scale))
        assert crop_scale_img.size == (200, 150)
