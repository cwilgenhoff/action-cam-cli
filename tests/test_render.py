"""Tests for telemetry overlay rendering and encoding (ADR 0003, Phase 3).

Frame rendering and the ffmpeg command builder are pure (Pillow in-memory / string
building) and tested directly. The actual `.mov` encode is an integration test,
skipped when ffmpeg is unavailable (so CI stays ffmpeg-free).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from action_cam_cli.telemetry.encode import build_overlay_encode_cmd, render_overlay_mov
from action_cam_cli.telemetry.render import format_speed, render_frame


class TestFormatSpeed:
    """format_speed: one decimal place plus the unit."""

    @pytest.mark.parametrize(
        "kmh, text",
        [
            (0.0, "0.0 km/h"),
            (24.54, "24.5 km/h"),   # rounds down
            (9.96, "10.0 km/h"),    # rounds up
            (36.0, "36.0 km/h"),
        ],
    )
    def test_formatting(self, kmh, text):
        assert format_speed(kmh) == text


class TestRenderFrame:
    """render_frame: a transparent RGBA frame with the gauge drawn in."""

    def test_size_and_mode(self):
        img = render_frame(24.5, (320, 180))
        assert img.size == (320, 180)
        assert img.mode == "RGBA"

    def test_corners_are_transparent(self):
        img = render_frame(24.5, (320, 180))
        assert img.getpixel((0, 0))[3] == 0          # top-left
        assert img.getpixel((319, 0))[3] == 0        # top-right (away from text)

    def test_text_is_actually_drawn(self):
        # The alpha channel must contain opaque pixels (the text + stroke).
        img = render_frame(24.5, (320, 180))
        assert img.getchannel("A").getextrema()[1] == 255


class TestOverlayEncodeCommand:
    """build_overlay_encode_cmd: raw RGBA in, alpha-preserving ProRes out."""

    def test_raw_rgba_input_and_alpha_codec(self):
        cmd = build_overlay_encode_cmd((1920, 1080), 30, Path("/out/o.mov"))
        assert "rawvideo" in cmd and "rgba" in cmd            # raw RGBA stdin
        assert "prores_ks" in cmd
        assert cmd[cmd.index("-pix_fmt") + 1] == "yuva444p10le"  # alpha preserved
        assert "1920x1080" in cmd
        assert cmd[-1] == str(Path("/out/o.mov"))

    @pytest.mark.parametrize("force, has_y", [(False, False), (True, True)])
    def test_force_controls_overwrite(self, force, has_y):
        cmd = build_overlay_encode_cmd((64, 64), 30, Path("/o.mov"), force=force)
        assert ("-y" in cmd) is has_y


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
class TestOverlayMovIntegration:
    """render_overlay_mov: end-to-end produces a real alpha .mov (needs ffmpeg)."""

    def test_produces_alpha_mov(self, tmp_path):
        out = tmp_path / "overlay.mov"
        render_overlay_mov([10.0, 20.0, 30.0], (64, 64), 30, out, force=True)
        assert out.exists() and out.stat().st_size > 0

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,pix_fmt", "-of", "default=nk=1", str(out)],
            capture_output=True, text=True,
        )
        assert "64" in probe.stdout
        assert "yuva" in probe.stdout  # alpha-bearing pixel format
