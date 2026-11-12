# Copyright 2026 Capstone MCP contributors.
"""Deterministic summaries of native graph fits without cross-binding ranking."""

import pytest

from capstone_mcp.graph_report import (
    DuplicateNativeModelError,
    LimitationCode,
    summarize_graph,
)
from capstone_mcp.graph_state import (
    FitMetric,
    FitParameter,
    GraphInput,
    GraphSeries,
    GraphState,
    NativeFit,
)


def _fit(
    native_type: int,
    name: str,
    *,
    status: int = 0,
    metrics: tuple[FitMetric, ...] = (),
    locked: tuple[bool, ...] = (False,),
) -> NativeFit:
    return NativeFit(
        native_type=native_type,
        name=name,
        expression="native expression",
        error_status=status,
        parameters=[
            FitParameter(
                name=f"p{index}",
                value=None if status > 3 else str(index + 1),
                uncertainty=None if status > 3 else f"0.{index + 1}",
                locked=is_locked,
            )
            for index, is_locked in enumerate(locked)
        ],
        metrics=list(metrics),
    )


def _metric(
    name: str,
    abbreviation: str,
    value: str | None,
    *,
    valid: bool = True,
) -> FitMetric:
    return FitMetric(
        name=name,
        abbreviation=abbreviation,
        value=value,
        valid=valid,
    )


def _series(
    renderer_id: str,
    *,
    dataset_id: str,
    unit_id: int | None,
    fits: tuple[NativeFit, ...],
    inputs: tuple[GraphInput, ...] | None = None,
) -> GraphSeries:
    provenance = inputs or (
        GraphInput(
            index=0,
            source_id=f"source-{renderer_id}",
            dataset_id=dataset_id,
            unit_id=unit_id,
        ),
    )
    return GraphSeries(
        renderer_id=renderer_id,
        inputs=list(provenance),
        fits=list(fits),
    )


def test_report_groups_by_renderer_and_reports_tied_mse_minima() -> None:
    # Given: a lower error belongs to a different run and unit.
    mse = ("Mean Squared Error", "MSE")
    state = GraphState(
        fit_enabled=True,
        selected_types=[2, 1],
        series=[
            _series(
                "renderer-b",
                dataset_id="run-b",
                unit_id=900,
                fits=(_fit(1, "Linear", metrics=(
                    _metric(*mse, "0.1"),
                )),),
            ),
            _series(
                "renderer-a",
                dataset_id="run-a",
                unit_id=100,
                inputs=(
                    GraphInput(
                        index=1,
                        source_id="y",
                        dataset_id="run-a",
                        unit_id=200,
                    ),
                    GraphInput(
                        index=0,
                        source_id="x",
                        dataset_id="run-a",
                        unit_id=100,
                    ),
                ),
                fits=(
                    _fit(2, "Quadratic", metrics=(
                        _metric(*mse, "1.00"),
                        _metric("Coefficient of Determination", "R²", "0.9"),
                    )),
                    _fit(1, "Linear", locked=(True, False), metrics=(
                        _metric(*mse, "1.0"),
                        _metric("Correlation Coefficient", "r", "0.8"),
                    )),
                ),
            ),
        ],
    )
    # When
    report = summarize_graph(state)
    # Then
    assert [group.renderer_id for group in report.groups] == [
        "renderer-a", "renderer-b",
    ]
    first = report.groups[0]
    assert [
        (item.source_id, item.dataset_id, item.unit_id, item.index)
        for item in first.provenance
    ] == [
        ("x", "run-a", 100, 0),
        ("y", "run-a", 200, 1),
    ]
    assert [row.native_type for row in first.rows] == [1, 2]
    assert first.rows[0].parameter_count == 2
    assert first.rows[0].free_parameter_count == 1
    assert [(m.name, m.abbreviation) for m in first.common_metrics] == [mse]
    assert first.descriptive_minima[0].smallest_value == "1.0"
    assert first.descriptive_minima[0].tied_model_ids == [
        "renderer-a:1", "renderer-a:2",
    ]
    assert report.groups[1].descriptive_minima == []
    assert LimitationCode.DIFFERENT_BINDINGS_NOT_COMPARED in report.limitations
    assert LimitationCode.NO_AUTOMATIC_MODEL_SELECTION in first.limitations


def test_report_marks_failed_and_unavailable_native_metrics() -> None:
    # Given
    state = GraphState(
        fit_enabled=True,
        selected_types=[1, 2],
        series=[_series(
            "renderer",
            dataset_id="run",
            unit_id=10,
            fits=(
                _fit(1, "Linear", metrics=(
                    _metric("Invalid flag", "bad", "99", valid=False),
                    _metric("Invalid text", "text", "not-a-number"),
                    _metric("Nonfinite", "nan", "NaN"),
                    _metric("Mean Squared Error", "MSE", "2.5"),
                )),
                _fit(2, "Quadratic", status=5, metrics=(
                    _metric("Mean Squared Error", "MSE", None, valid=False),
                )),
            ),
        )],
    )
    # When
    report = summarize_graph(state)
    # Then
    successful, failed = report.groups[0].rows
    assert [metric.value for metric in successful.metrics] == ["2.5"]
    assert successful.limitations == [
        LimitationCode.INVALID_NATIVE_METRIC,
        LimitationCode.NONFINITE_NATIVE_METRIC,
    ]
    assert failed.successful is False
    assert failed.status == "FAIL_MAX_ITERATONS"
    assert failed.parameters[0].value is None
    assert failed.limitations == [
        LimitationCode.INVALID_NATIVE_METRIC,
        LimitationCode.NATIVE_FIT_FAILURE,
    ]
    assert report.groups[0].common_metrics == []
    assert LimitationCode.NATIVE_FIT_FAILURE in report.limitations
    assert LimitationCode.SAMPLE_COUNT_UNAVAILABLE in report.limitations
    assert LimitationCode.RESIDUALS_UNAVAILABLE in report.limitations


def test_report_exposes_common_non_error_metric_without_ranking_it() -> None:
    # Given
    correlation = ("Correlation Coefficient", "r")
    state = GraphState(
        fit_enabled=True,
        selected_types=[1, 2],
        series=[_series(
            "renderer",
            dataset_id="run",
            unit_id=None,
            fits=(
                _fit(1, "Linear", metrics=(_metric(*correlation, "0.80"),)),
                _fit(2, "Quadratic", metrics=(_metric(*correlation, "0.85"),)),
            ),
        )],
    )
    # When
    group = summarize_graph(state).groups[0]
    # Then
    assert [
        (metric.name, metric.abbreviation) for metric in group.common_metrics
    ] == [correlation]
    assert group.descriptive_minima == []
    assert LimitationCode.NO_AUTOMATIC_MODEL_SELECTION in group.limitations


def test_duplicate_native_model_type_is_rejected_as_ambiguous() -> None:
    # Given
    state = GraphState(
        fit_enabled=True,
        selected_types=[1],
        series=[_series(
            "renderer",
            dataset_id="run",
            unit_id=10,
            fits=(_fit(1, "Linear"), _fit(1, "Linear copy")),
        )],
    )
    # When / Then
    with pytest.raises(
        DuplicateNativeModelError,
        match="duplicate native type 1",
    ):
        _ = summarize_graph(state)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            GraphState(fit_enabled=False, selected_types=[], series=[]),
            {
                LimitationCode.EMPTY_GRAPH,
                LimitationCode.NO_NATIVE_FITS,
            },
        ),
        (
            GraphState(
                fit_enabled=False,
                selected_types=[],
                series=[_series(
                    "renderer",
                    dataset_id="run",
                    unit_id=None,
                    fits=(),
                )],
            ),
            {LimitationCode.NO_NATIVE_FITS},
        ),
    ],
)
def test_report_handles_empty_graphs_and_renderers_without_fits(
    state: GraphState,
    expected: set[LimitationCode],
) -> None:
    # Given / When
    report = summarize_graph(state)
    # Then
    assert set(report.limitations) == expected
    assert all(group.rows == [] for group in report.groups)
