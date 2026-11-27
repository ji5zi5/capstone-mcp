# Copyright 2026 Capstone MCP contributors.
"""Malus's Law optical polarization experiment recipe."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final

from capstone_mcp.recipes.base import ExperimentRecipe, RecipePhaseResult

if TYPE_CHECKING:
    from capstone_mcp.desktop import Capstone

MIN_POLARIZATION_POINTS: Final[int] = 4
SINGULAR_SOLVE_EPSILON: Final[float] = 1e-15


def _solve_3x3(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a 3x3 linear system with partial pivoting."""
    aug = [[*row, val] for row, val in zip(matrix, rhs, strict=True)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        diag = aug[col][col]
        if abs(diag) <= SINGULAR_SOLVE_EPSILON:
            msg = "Polarization angles do not span linearly independent phases."
            raise ValueError(msg)
        for j in range(col, 4):
            aug[col][j] /= diag
        for row in range(3):
            if row == col or aug[row][col] == 0.0:
                continue
            factor = aug[row][col]
            for j in range(col, 4):
                aug[row][j] -= factor * aug[col][j]
    return [aug[i][3] for i in range(3)]


def fit_malus_law(
    angles_deg: list[float],
    intensities: list[float],
) -> dict[str, float]:
    """Fit I(theta) = I_bg + I_max * cos^2(theta - theta_0) via 2*theta basis."""
    if len(angles_deg) != len(intensities):
        msg = "Angle and intensity arrays must have matching lengths."
        raise ValueError(msg)
    if len(angles_deg) < MIN_POLARIZATION_POINTS:
        msg = f"At least {MIN_POLARIZATION_POINTS} samples required for Malus fit."
        raise ValueError(msg)
    if not all(math.isfinite(v) for v in (*angles_deg, *intensities)):
        msg = "Polarization measurements must be finite."
        raise ValueError(msg)

    cos2 = [math.cos(2.0 * math.radians(theta)) for theta in angles_deg]
    sin2 = [math.sin(2.0 * math.radians(theta)) for theta in angles_deg]
    ones = [1.0] * len(angles_deg)
    basis = (ones, cos2, sin2)

    normal = [
        [math.fsum(a * b for a, b in zip(row_a, row_b, strict=True)) for row_b in basis]
        for row_a in basis
    ]
    rhs = [
        math.fsum(b * y for b, y in zip(row_b, intensities, strict=True))
        for row_b in basis
    ]
    c0, c1, c2 = _solve_3x3(normal, rhs)
    i_max = 2.0 * math.hypot(c1, c2)
    i_bg = c0 - 0.5 * i_max
    theta0_deg = math.degrees(0.5 * math.atan2(c2, c1))

    mean_y = math.fsum(intensities) / len(intensities)
    ss_tot = math.fsum((y - mean_y) ** 2 for y in intensities)
    ss_res = math.fsum(
        (
            y
            - (
                i_bg
                + i_max * (math.cos(math.radians(theta - theta0_deg)) ** 2)
            )
        )
        ** 2
        for theta, y in zip(angles_deg, intensities, strict=True)
    )
    r_squared = max(0.0, min(1.0, 1.0 - ss_res / ss_tot)) if ss_tot > 0 else 1.0
    rmse = math.sqrt(ss_res / len(intensities))
    return {
        "max_intensity": i_max,
        "background_intensity": i_bg,
        "axis_offset_deg": theta0_deg,
        "r_squared": r_squared,
        "rmse": rmse,
    }


class PolarizationRecipe(ExperimentRecipe):
    """Macro recipe fitting Malus's Law I = I_bg + I_max * cos^2(theta - theta_0)."""

    experiment_id = "polarization"
    title = "Optical Polarization & Malus's Law (빛의 편광과 말루스의 법칙)"
    description = (
        "Rotary polarizer angle vs transmitted light intensity measurement and "
        "exact Malus's Law cos^2(theta - theta_0) fitting."
    )

    def setup(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Report that automatic hardware configuration is not implemented."""
        del parameters, app
        return RecipePhaseResult(
            phase="setup",
            status="failed",
            message="Automatic hardware setup is not implemented. Configure the "
            "experiment manually and provide recorded data for analysis.",
        )

    def acquire(
        self,
        parameters: dict[str, Any] | None = None,
        app: Capstone | None = None,
    ) -> RecipePhaseResult:
        """Validate caller-supplied polarizer angle and light intensity samples."""
        del app
        params = parameters or {}
        if "angles_deg" in params and "intensities" in params:
            angles = [float(a) for a in params["angles_deg"]]
            intensities = [float(i) for i in params["intensities"]]
        elif "angles_rad" in params and "intensities" in params:
            angles = [math.degrees(float(a)) for a in params["angles_rad"]]
            intensities = [float(i) for i in params["intensities"]]
        else:
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Live acquisition is not implemented. Provide recorded "
                "angles and intensities; synthetic data is not generated.",
            )
        if (
            not angles
            or len(angles) != len(intensities)
            or not all(math.isfinite(v) for v in (*angles, *intensities))
        ):
            return RecipePhaseResult(
                phase="acquire",
                status="failed",
                message="Provide nonempty, matching, finite angle/intensity arrays.",
            )
        return RecipePhaseResult(
            phase="acquire",
            status="completed",
            message=f"Accepted {len(angles)} caller-provided polarization samples.",
            details={
                "data": {"angles_deg": angles, "intensities": intensities},
                "points_count": len(angles),
            },
        )

    def analyze(
        self,
        parameters: dict[str, Any] | None = None,
    ) -> RecipePhaseResult:
        """Fit Malus's Law cos^2 curve against measured polarization samples."""
        params = parameters or {}
        data = params.get("data", {})
        raw_angles = (
            params.get("angles_deg")
            or data.get("angles_deg")
            or params.get("angles_rad")
        )
        raw_int = params.get("intensities") or data.get("intensities")
        if not raw_angles or not raw_int:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message="Missing angle or intensity data for polarization analysis.",
            )
        angles_deg = [float(a) for a in raw_angles]
        if "angles_rad" in params and not (
            params.get("angles_deg") or data.get("angles_deg")
        ):
            angles_deg = [math.degrees(a) for a in angles_deg]
        intensities = [float(i) for i in raw_int]

        try:
            fit = fit_malus_law(angles_deg, intensities)
        except ValueError as exc:
            return RecipePhaseResult(
                phase="analyze",
                status="failed",
                message=str(exc),
            )
        return RecipePhaseResult(
            phase="analyze",
            status="completed",
            message=(
                f"Fitted Malus's Law: I_max = {fit['max_intensity']:.4f}, "
                f"offset = {fit['axis_offset_deg']:.2f} deg, "
                f"R^2 = {fit['r_squared']:.4f}."
            ),
            details={
                "model": "malus_cos2",
                "points_count": len(angles_deg),
                **{key: round(val, 6) for key, val in fit.items()},
            },
        )
