"""Tests for the CLI layer: argument parsing and routing.

`cli.main` holds no business logic — it parses args, delegates to
`pipeline.run`, and translates a `PipelineError` into exit code 1. These tests
stub `run` (patched on the `cli` namespace) so they're fast and don't touch the
pipeline or ffmpeg.
"""

from pathlib import Path

import pytest

from action_cam_cli import __version__, cli
from action_cam_cli.core.errors import PipelineError


class TestArgumentParsing:
    """parse_args: defaults, flags, and required positional."""

    @pytest.mark.parametrize("flag", ["-V", "--version"])
    def test_version_flag_prints_and_exits_zero(self, flag, capsys):
        # argparse's "version" action prints to stdout and exits with code 0.
        with pytest.raises(SystemExit) as exc:
            cli.parse_args([flag])
        assert exc.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_defaults(self):
        args = cli.parse_args(["/in"])
        assert args.input_dir == Path("/in")
        assert args.output_dir is None
        assert args.force is False
        assert args.dry_run is False

    def test_all_flags(self):
        args = cli.parse_args(["/in", "-o", "/out", "--force", "--dry-run"])
        assert args.input_dir == Path("/in")
        assert args.output_dir == Path("/out")
        assert args.force is True
        assert args.dry_run is True

    def test_missing_input_dir_exits(self):
        # argparse exits (code 2) when the required positional is absent.
        with pytest.raises(SystemExit):
            cli.parse_args([])


class TestMainRouting:
    """main: delegate to run, propagate its exit code, translate PipelineError."""

    def test_delegates_to_run_with_parsed_args(self, monkeypatch):
        captured = {}

        def fake_run(input_dir, output_dir, *, force, dry_run):
            captured.update(input_dir=input_dir, output_dir=output_dir, force=force, dry_run=dry_run)
            return 0

        monkeypatch.setattr(cli, "run", fake_run)
        rc = cli.main(["/in", "-o", "/out", "--force"])

        assert rc == 0
        assert captured == {
            "input_dir": Path("/in"),
            "output_dir": Path("/out"),
            "force": True,
            "dry_run": False,
        }

    def test_returns_run_exit_code(self, monkeypatch):
        monkeypatch.setattr(cli, "run", lambda *a, **k: 130)
        assert cli.main(["/in"]) == 130

    def test_pipeline_error_becomes_exit_1_and_prints_to_stderr(self, monkeypatch, capsys):
        def boom(*a, **k):
            raise PipelineError("ERROR: kaboom\n       a helpful hint")

        monkeypatch.setattr(cli, "run", boom)
        rc = cli.main(["/in"])

        assert rc == 1
        err = capsys.readouterr().err
        assert "ERROR: kaboom" in err
        assert "a helpful hint" in err
