"""Generic filesystem discovery helpers (domain-agnostic).

Deliberately knows nothing about DJI naming or sessions — that lives in
``grading/sessions.py``. This keeps ``core`` reusable by the upcoming telemetry
pipeline (which will scan for ``.gpx`` files), per ADR 0002.
"""

from collections.abc import Iterable
from pathlib import Path


def scan_files(directory: Path, suffixes: Iterable[str]) -> list[Path]:
    """Return files directly in ``directory`` whose extension is in ``suffixes``.

    Matching is case-insensitive; subdirectories are ignored. Results are sorted by
    path for deterministic ordering.
    """
    wanted = {s.lower() for s in suffixes}
    return sorted(
        entry
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix.lower() in wanted
    )
