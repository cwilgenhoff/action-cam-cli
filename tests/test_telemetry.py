"""Tests for the telemetry core: TCX parsing and the pure speed transforms (ADR 0003).

The smoothing/resampling functions are pure (no I/O) and tested directly; the TCX
parser is tested against the committed synthetic fixture in tests/fixtures/.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from action_cam_cli.telemetry.speed import resample_to_frames, smooth
from action_cam_cli.telemetry.tcx import parse_track

FIXTURE = Path(__file__).parent / "fixtures" / "short_ride.tcx"


class TestParseTcx:
    """parse_track: reads device speed from TCX, skipping points without a value."""

    def test_skips_points_without_speed(self):
        # Fixture has 4 trackpoints; the last has no <Speed> and must be dropped.
        track = parse_track(FIXTURE)
        assert len(track.samples) == 3

    def test_start_is_first_utc_timestamp(self):
        track = parse_track(FIXTURE)
        assert track.start == datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_speed_converted_to_kmh_and_time_relative(self):
        # 5/10/10 m/s -> 18/36/36 km/h, at t = 0/10/20 s from the start.
        track = parse_track(FIXTURE)
        assert track.samples[0] == pytest.approx((0.0, 18.0))
        assert track.samples[1] == pytest.approx((10.0, 36.0))
        assert track.samples[2] == pytest.approx((20.0, 36.0))


class TestSmooth:
    """smooth: time-based moving average."""

    def test_constant_series_unchanged(self):
        samples = [(0.0, 30.0), (1.0, 30.0), (2.0, 30.0)]
        assert [round(v, 6) for _, v in smooth(samples, 2.0)] == [30.0, 30.0, 30.0]

    def test_zero_window_is_noop(self):
        samples = [(0.0, 10.0), (1.0, 40.0)]
        assert smooth(samples, 0) == samples

    def test_spike_is_attenuated(self):
        samples = [(0.0, 0.0), (1.0, 60.0), (2.0, 0.0)]
        smoothed = dict(smooth(samples, 10.0))  # window covers all three
        assert smoothed[1.0] == pytest.approx(20.0)  # mean of 0, 60, 0


class TestResampleToFrames:
    """resample_to_frames: linear interpolation onto the frame grid."""

    def test_frame_count(self):
        frames = resample_to_frames([(0.0, 0.0), (10.0, 36.0)], fps=30, duration_s=2)
        assert len(frames) == 60

    def test_linear_midpoint(self):
        # 0 -> 36 over 0..10 s; at t=5 s expect 18.
        frames = resample_to_frames([(0.0, 0.0), (10.0, 36.0)], fps=2, duration_s=10)
        assert frames[10] == pytest.approx(18.0)  # k=10 -> t=5s

    def test_holds_endpoints_outside_range(self):
        frames = resample_to_frames([(5.0, 25.0), (6.0, 25.0)], fps=1, duration_s=8)
        assert frames[0] == 25.0   # before first sample -> first value
        assert frames[-1] == 25.0  # after last sample -> last value

    def test_empty_inputs(self):
        assert resample_to_frames([], fps=30, duration_s=10) == []
        assert resample_to_frames([(0.0, 1.0)], fps=0, duration_s=10) == []
