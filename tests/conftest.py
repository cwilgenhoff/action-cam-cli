"""Shared pytest fixtures for the test suite."""

from datetime import datetime
from pathlib import Path

import pytest

from action_cam_cli.core.models import Clip


@pytest.fixture
def make_clip():
    """Factory fixture producing mock `Clip`s with a given sequence counter.

    Only the counter varies; the stamp/created/path are fixed defaults, which is
    all the grading and command-building logic needs.
    """

    def _generator(counter: int) -> Clip:
        return Clip(
            path=Path(f"/in/DJI_20260101000000_{counter:04d}_D.MP4"),
            counter=counter,
            created=datetime(2026, 1, 1),
            stamp="20260101000000",
        )

    return _generator
