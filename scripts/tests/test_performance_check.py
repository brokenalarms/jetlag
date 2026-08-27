"""Unit tests for the performance gate's regression-threshold math (fast, no subprocess).

Proves jetlag-3y8: the gate compares interleaved baseline/candidate medians
against REGRESSION_THRESHOLD, so a single slow (or fast) outlier run — the
kind a busy shared CI runner produces — cannot flip the result on its own.
"""
import pytest

from test_performance import TestPerformance, REGRESSION_THRESHOLD


class _FakeConfig:
    def __init__(self):
        self._perf_results = []


class _FakeRequest:
    def __init__(self):
        self.config = _FakeConfig()


def test_check_passes_within_threshold():
    request = _FakeRequest()
    candidate = [1.0 + REGRESSION_THRESHOLD - 0.01, 1.0, 1.0]
    TestPerformance()._check("media_pipeline", [1.0, 1.0, 1.0], candidate, request)
    assert request.config._perf_results[0]["regression"] is False


def test_check_fails_beyond_threshold():
    request = _FakeRequest()
    slower = 1.0 + REGRESSION_THRESHOLD + 0.5
    with pytest.raises(AssertionError, match="regression"):
        TestPerformance()._check("media_pipeline", [1.0, 1.0, 1.0], [slower, slower, slower], request)
    assert request.config._perf_results[0]["regression"] is True


def test_check_uses_medians_not_a_single_outlier_run():
    """One outlier candidate run (a runner hiccup) must not fail the gate on its own."""
    request = _FakeRequest()
    TestPerformance()._check("media_pipeline", [1.0, 1.0, 1.0], [1.0, 1.0, 5.0], request)
    assert request.config._perf_results[0]["regression"] is False
