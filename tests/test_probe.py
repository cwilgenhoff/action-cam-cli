"""Tests for the ffmpeg capability probe.

`has_nvenc_encoder` shells out to ffmpeg, so the subprocess call is stubbed to keep
these unit tests hermetic (no GPU or ffmpeg required).
"""

import subprocess

from action_cam_cli.core import probe


class TestNvencProbe:
    """has_nvenc_encoder: True only on a clean exit; False on any failure."""

    def test_true_when_probe_encode_succeeds(self, monkeypatch):
        monkeypatch.setattr(probe.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0))
        assert probe.has_nvenc_encoder() is True

    def test_false_when_probe_encode_fails(self, monkeypatch):
        monkeypatch.setattr(probe.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1))
        assert probe.has_nvenc_encoder() is False

    def test_false_when_ffmpeg_missing(self, monkeypatch):
        def _missing(*a, **k):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(probe.subprocess, "run", _missing)
        assert probe.has_nvenc_encoder() is False
