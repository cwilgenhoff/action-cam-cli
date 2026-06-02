"""Behavioral tests for FFmpeg command construction (ADR 0002).

These exercise the public builders (`build_filter_graph`, `build_ffmpeg_command`)
and assert *contract* properties — input-scaling, LUT path quoting/escaping across
platforms, and the presence of the critical encode flags — rather than matching an
exact command string. They target the real regressions we've hit (Windows path
parsing, the 10-bit `p010le` pixel format) without coupling to incidental details
like internal filtergraph pad labels.

`make_clip` is the factory fixture from conftest.py.
"""

from pathlib import Path, PureWindowsPath

import pytest

from action_cam_cli.grading.ffmpeg import build_ffmpeg_command, build_filter_graph


class TestFilterGraph:
    """build_filter_graph: input scaling and the applied filters."""

    @pytest.mark.parametrize("n", [1, 2, 3, 5])
    def test_concats_every_input_with_audio(self, n):
        graph = build_filter_graph(n, Path("/luts/x.cube"))
        # Every input contributes both its video and audio pad to the concat...
        for i in range(n):
            assert f"[{i}:v][{i}:a]" in graph
        # ...and no phantom (n-th, zero-based) input is generated.
        assert f"[{n}:v]" not in graph
        # concat over N inputs, carrying audio (a=1) — audio must never be dropped.
        assert f"concat=n={n}:v=1:a=1" in graph

    def test_applies_lut_and_audio_filter(self):
        graph = build_filter_graph(2, Path("/luts/x.cube"))
        assert "lut3d=file=" in graph              # color conversion applied
        assert "bass=g=-6:f=150" in graph          # mic low-shelf cut applied


class TestLutPathQuoting:
    """LUT path quoting/escaping across platforms (the Windows regression)."""

    @pytest.mark.parametrize(
        "lut_path, expected_fragment",
        [
            # POSIX path: untouched, just single-quoted.
            (Path("/home/u/luts/dji.cube"), "lut3d=file='/home/u/luts/dji.cube'"),
            # Windows path: backslashes -> '/', drive-letter colon escaped, quoted.
            (PureWindowsPath(r"C:\luts\dji.cube"), "lut3d=file='C\\:/luts/dji.cube'"),
            # Spaces in the path are preserved inside the quotes.
            (Path("/clips/My Footage/dji.cube"), "lut3d=file='/clips/My Footage/dji.cube'"),
        ],
    )
    def test_path_is_quoted_and_escaped(self, lut_path, expected_fragment):
        graph = build_filter_graph(1, lut_path)
        assert expected_fragment in graph
        # The escaped path is always wrapped in single quotes (required by ffmpeg's
        # two-pass filtergraph parser on Windows).
        assert "lut3d=file='" in graph


class TestFfmpegCommand:
    """build_ffmpeg_command: critical flags and overall structure."""

    def test_pixel_format_is_10bit_nvenc(self, make_clip):
        # Guards the p010le (not yuv420p10le) and hevc_nvenc pairing — a real past bug.
        cmd = build_ffmpeg_command([make_clip(12)], Path("/out/m.mp4"), lut_path=Path("/l/x.cube"))
        assert cmd[cmd.index("-pix_fmt") + 1] == "p010le"
        assert cmd[cmd.index("-c:v") + 1] == "hevc_nvenc"

    @pytest.mark.parametrize("flag", ["-c:v", "hevc_nvenc", "-preset", "p6", "-cq", "19", "-pix_fmt", "p010le"])
    def test_contains_critical_encode_flags(self, make_clip, flag):
        cmd = build_ffmpeg_command([make_clip(12), make_clip(13)], Path("/out/m.mp4"), lut_path=Path("/l/x.cube"))
        assert flag in cmd

    @pytest.mark.parametrize("n", [1, 2, 4])
    def test_one_input_flag_per_clip(self, make_clip, n):
        cmd = build_ffmpeg_command([make_clip(i) for i in range(n)], Path("/out/m.mp4"), lut_path=Path("/l/x.cube"))
        assert cmd.count("-i") == n

    def test_maps_both_video_and_audio_outputs(self, make_clip):
        cmd = build_ffmpeg_command([make_clip(12)], Path("/out/m.mp4"), lut_path=Path("/l/x.cube"))
        assert cmd.count("-map") == 2
        assert "[vout]" in cmd and "[aout]" in cmd

    def test_output_path_is_last_argument(self, make_clip):
        out = Path("/out/master.mp4")
        cmd = build_ffmpeg_command([make_clip(12)], out, lut_path=Path("/l/x.cube"))
        # str(out) — not a hardcoded "/..." — so the assertion holds on Windows too,
        # where Path renders with backslashes.
        assert cmd[-1] == str(out)

    @pytest.mark.parametrize("force, y_present", [(False, False), (True, True)])
    def test_force_controls_overwrite_flag(self, make_clip, force, y_present):
        cmd = build_ffmpeg_command([make_clip(12)], Path("/out/m.mp4"), lut_path=Path("/l/x.cube"), force=force)
        assert ("-y" in cmd) is y_present
