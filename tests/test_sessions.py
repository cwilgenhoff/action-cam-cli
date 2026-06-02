"""Behavioral tests for DJI clip discovery and session grouping (ADR 0002).

`group_into_sessions` encodes the core chaptering rule (consecutive sequence
counters belong to one recording; a gap starts a new one), and `discover_clips`
encodes the ingestion rules (ignore `.LRF` proxies and non-DJI files, parse the
filename, sort by counter). Both are pure filename logic — no ffprobe — so these
tests are fast and hermetic.

`make_clip` is the factory fixture from conftest.py.
"""

from datetime import datetime

import pytest

from action_cam_cli.grading.sessions import discover_clips, group_into_sessions


class TestSessionGrouping:
    """group_into_sessions: the chaptering rule."""

    @pytest.mark.parametrize(
        "counters, expected",
        [
            ([12, 13, 14], [[12, 13, 14]]),              # one contiguous recording
            ([12, 13, 20, 21], [[12, 13], [20, 21]]),    # a gap splits into two
            ([5], [[5]]),                                # single clip
            ([], []),                                    # nothing
            ([1, 2, 4, 5, 6, 9], [[1, 2], [4, 5, 6], [9]]),  # multiple gaps
            ([10, 10], [[10], [10]]),                    # duplicate counter is not "+1" -> new session
        ],
    )
    def test_groups_by_consecutive_counter(self, make_clip, counters, expected):
        sessions = group_into_sessions([make_clip(c) for c in counters])
        assert [[clip.counter for clip in s] for s in sessions] == expected


class TestClipDiscovery:
    """discover_clips: ingestion rules."""

    def test_ignores_lrf_proxies_and_non_dji_files(self, tmp_path):
        (tmp_path / "DJI_20260101080000_0012_D.MP4").touch()
        (tmp_path / "DJI_20260101080000_0012_D.LRF").touch()   # low-res proxy
        (tmp_path / "DJI_20260101083000_0013_D.MP4").touch()
        (tmp_path / "holiday.mp4").touch()                     # non-DJI .mp4
        (tmp_path / "notes.txt").touch()                       # unrelated file

        clips = discover_clips(tmp_path)

        assert [c.counter for c in clips] == [12, 13]
        assert all(c.path.suffix.lower() == ".mp4" for c in clips)
        assert all("DJI_" in c.path.name for c in clips)

    def test_matches_lowercase_extension(self, tmp_path):
        (tmp_path / "DJI_20260101080000_0014_D.mp4").touch()   # lowercase .mp4
        clips = discover_clips(tmp_path)
        assert [c.counter for c in clips] == [14]

    def test_sorts_by_counter(self, tmp_path):
        for counter in (20, 12, 15):
            (tmp_path / f"DJI_20260101080000_{counter:04d}_D.MP4").touch()
        clips = discover_clips(tmp_path)
        assert [c.counter for c in clips] == [12, 15, 20]

    def test_parses_stamp_counter_and_datetime(self, tmp_path):
        (tmp_path / "DJI_20260601083000_0012_D.MP4").touch()
        (clip,) = discover_clips(tmp_path)
        assert clip.counter == 12
        assert clip.stamp == "20260601083000"
        assert clip.created == datetime(2026, 6, 1, 8, 30, 0)

    def test_warns_about_non_dji_mp4(self, tmp_path, capsys):
        (tmp_path / "holiday.mp4").touch()
        clips = discover_clips(tmp_path)
        assert clips == []
        err = capsys.readouterr().err
        assert "did not match the DJI" in err
        assert "holiday.mp4" in err

    def test_empty_directory(self, tmp_path):
        assert discover_clips(tmp_path) == []
