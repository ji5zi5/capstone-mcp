# Copyright 2026 Capstone MCP contributors.
"""Clean ASCII sparklines and standalone SVG chart generation."""

import math
from collections.abc import Sequence
from typing import Final

MIN_FIT_POINTS: Final[int] = 2


def render_ascii_sparkline(
    x: Sequence[float],
    y: Sequence[float],
    width: int = 40,
    height: int = 10,
    title: str = "",
) -> str:
    """Render a clean 2D ASCII scatter/line plot for terminal and markdown display.

    Args:
        x: Independent variable series.
        y: Dependent variable series.
        width: Character width of plot area.
        height: Character height of plot area.
        title: Optional plot title header.

    Returns:
        Formatted ASCII plot string.
    """
    pairs = [
        (float(xi), float(yi))
        for xi, yi in zip(x, y, strict=False)
        if not (math.isnan(xi) or math.isnan(yi))
    ]
    if not pairs:
        return "[Empty data series for ASCII plot]"

    min_x = min(p[0] for p in pairs)
    max_x = max(p[0] for p in pairs)
    min_y = min(p[1] for p in pairs)
    max_y = max(p[1] for p in pairs)

    span_x = max_x - min_x if max_x > min_x else 1.0
    span_y = max_y - min_y if max_y > min_y else 1.0

    # Grid init
    grid = [[" " for _ in range(width)] for _ in range(height)]

    for xi, yi in pairs:
        col = int(((xi - min_x) / span_x) * (width - 1))
        row = int(((max_y - yi) / span_y) * (height - 1))
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))
        grid[row][col] = "*"

    lines: list[str] = []
    if title:
        lines.append(f"  {title}")
    lines.append(f"  +{'-' * width}+")
    for r in range(height):
        y_val = max_y - (r / max(height - 1, 1)) * span_y
        row_str = "".join(grid[r])
        lines.append(f"{y_val:6.2f} |{row_str}|")
    lines.append(f"  +{'-' * width}+")
    lines.append(f"       {min_x:<10.2f}{' ' * max(0, width - 20)}{max_x:>10.2f}")

    return "\n".join(lines)


def render_svg_sparkline(
    x: Sequence[float],
    y: Sequence[float],
    fit_x: Sequence[float] | None = None,
    fit_y: Sequence[float] | None = None,
    width: int = 500,
    height: int = 250,
    title: str = "",
) -> str:
    """Render a clean, responsive standalone vector SVG chart.

    Args:
        x: Independent variable series.
        y: Dependent variable series.
        fit_x: Optional fitted line X coordinates.
        fit_y: Optional fitted line Y coordinates.
        width: ViewBox pixel width.
        height: ViewBox pixel height.
        title: Chart title.

    Returns:
        Valid SVG XML markup string.
    """
    pairs = [
        (float(xi), float(yi))
        for xi, yi in zip(x, y, strict=False)
        if not (math.isnan(xi) or math.isnan(yi))
    ]
    if not pairs:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><text x="20" y="30">No data</text></svg>'

    pad_left = 60
    pad_right = 30
    pad_top = 40
    pad_bottom = 40

    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    all_x = [p[0] for p in pairs] + (list(fit_x) if fit_x else [])
    all_y = [p[1] for p in pairs] + (list(fit_y) if fit_y else [])

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)

    span_x = max_x - min_x if max_x > min_x else 1.0
    span_y = max_y - min_y if max_y > min_y else 1.0

    def to_svg(px: float, py: float) -> tuple[float, float]:
        sx = pad_left + ((px - min_x) / span_x) * plot_w
        sy = pad_top + ((max_y - py) / span_y) * plot_h
        return sx, sy

    elements: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" style="background:#ffffff; border-radius:6px;">',
    ]

    if title:
        elements.append(
            f'<text x="{pad_left}" y="25" font-family="sans-serif" font-size="14" font-weight="bold" fill="#1e293b">{title}</text>',
        )

    # Axes
    elements.append(
        f'<line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top + plot_h}" stroke="#94a3b8" stroke-width="1.5"/>',
    )
    elements.append(
        f'<line x1="{pad_left}" y1="{pad_top + plot_h}" x2="{pad_left + plot_w}" y2="{pad_top + plot_h}" stroke="#94a3b8" stroke-width="1.5"/>',
    )

    # Fitted line if present
    if (
        fit_x
        and fit_y
        and len(fit_x) == len(fit_y)
        and len(fit_x) >= MIN_FIT_POINTS
    ):
        path_data: list[str] = []
        for i, (fx, fy) in enumerate(zip(fit_x, fit_y, strict=True)):
            sx, sy = to_svg(fx, fy)
            cmd = "M" if i == 0 else "L"
            path_data.append(f"{cmd} {sx:.1f} {sy:.1f}")
        elements.append(
            f'<path d="{" ".join(path_data)}" fill="none" stroke="#dc2626" stroke-width="2" stroke-dasharray="4 2"/>',
        )

    # Scatter points
    for xi, yi in pairs:
        sx, sy = to_svg(xi, yi)
        elements.append(
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="3.5" fill="#2563eb" opacity="0.85"/>',
        )

    # Axis tick labels
    elements.append(
        f'<text x="{pad_left}" y="{pad_top + plot_h + 20}" font-family="sans-serif" font-size="10" fill="#64748b" text-anchor="middle">{min_x:.2f}</text>',
    )
    elements.append(
        f'<text x="{pad_left + plot_w}" y="{pad_top + plot_h + 20}" font-family="sans-serif" font-size="10" fill="#64748b" text-anchor="middle">{max_x:.2f}</text>',
    )
    elements.append(
        f'<text x="{pad_left - 8}" y="{pad_top + plot_h}" font-family="sans-serif" font-size="10" fill="#64748b" text-anchor="end">{min_y:.2f}</text>',
    )
    elements.append(
        f'<text x="{pad_left - 8}" y="{pad_top + 10}" font-family="sans-serif" font-size="10" fill="#64748b" text-anchor="end">{max_y:.2f}</text>',
    )

    elements.append("</svg>")
    return "\n".join(elements)
