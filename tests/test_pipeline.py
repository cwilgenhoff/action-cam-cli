"""Behavioral tests for environment validation (ADR 0002).

The refactor made `validate_environment` testable by having it raise
`PipelineError` instead of calling `sys.exit()`. These tests confirm it raises for
each fatal condition (missing binaries, missing LUT, bad input dir) and succeeds —
creating the output directory — for a valid environment.

External dependencies are monkeypatched (`check_dependencies`, `LUT_PATH`) so the
tests are hermetic and don't require ffmpeg or the real asset on the machine.
"""

import pytest

from action_cam_cli.core.errors import PipelineError
from action_cam_cli.grading import pipeline
from action_cam_cli.grading.pipeline import validate_environment


@pytest.fixture
def deps_ok(monkeypatch):
    """Pretend ffmpeg/ffprobe are present so later checks can be reached."""
    monkeypatch.setattr(pipeline, "check_dependencies", lambda *a, **k: [])


@pytest.fixture
def env_ok(deps_ok, monkeypatch, tmp_path):
    """deps_ok + a real (temp) LUT file, so only the dir checks remain in play."""
    lut = tmp_path / "fake.cube"
    lut.write_text("LUT")
    monkeypatch.setattr(pipeline, "LUT_PATH", lut)


class TestEnvironmentValidation:
    """validate_environment: fatal conditions raise PipelineError; success returns the output dir."""

    def test_missing_binaries_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "check_dependencies", lambda *a, **k: ["ffmpeg", "ffprobe"])
        with pytest.raises(PipelineError, match="Required binaries not found"):
            validate_environment(tmp_path, None)

    def test_missing_lut_raises(self, deps_ok, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "LUT_PATH", tmp_path / "missing.cube")
        with pytest.raises(PipelineError, match="Required LUT not found"):
            validate_environment(tmp_path, None)

    def test_missing_input_dir_raises(self, env_ok, tmp_path):
        with pytest.raises(PipelineError, match="does not exist"):
            validate_environment(tmp_path / "nope", None)

    def test_input_path_not_a_directory_raises(self, env_ok, tmp_path):
        a_file = tmp_path / "afile.mp4"
        a_file.touch()
        with pytest.raises(PipelineError, match="not a directory"):
            validate_environment(a_file, None)

    def test_output_path_not_a_directory_raises(self, env_ok, tmp_path):
        out_file = tmp_path / "out.txt"
        out_file.touch()
        with pytest.raises(PipelineError, match="not a directory"):
            validate_environment(tmp_path, out_file)

    def test_defaults_output_to_input(self, env_ok, tmp_path):
        assert validate_environment(tmp_path, None) == tmp_path

    def test_creates_missing_output_dir(self, env_ok, tmp_path):
        out = tmp_path / "masters"
        result = validate_environment(tmp_path, out)
        assert result == out
        assert out.is_dir()


class TestNvencPreflight:
    """validate_environment(check_encoder=...): NVENC is a hard prerequisite for renders."""

    def test_raises_when_nvenc_unavailable(self, env_ok, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "has_nvenc_encoder", lambda: False)
        with pytest.raises(PipelineError, match="NVENC"):
            validate_environment(tmp_path, None, check_encoder=True)

    def test_passes_when_nvenc_available(self, env_ok, monkeypatch, tmp_path):
        monkeypatch.setattr(pipeline, "has_nvenc_encoder", lambda: True)
        assert validate_environment(tmp_path, None, check_encoder=True) == tmp_path

    def test_skipped_when_not_requested(self, env_ok, monkeypatch, tmp_path):
        # e.g. --dry-run: no GPU needed, so an unavailable encoder must not block.
        monkeypatch.setattr(pipeline, "has_nvenc_encoder", lambda: False)
        assert validate_environment(tmp_path, None, check_encoder=False) == tmp_path
