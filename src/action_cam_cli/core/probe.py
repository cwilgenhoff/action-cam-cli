"""ffprobe wrappers for extracting stream and format metadata.

Domain-agnostic: usable by any pipeline (grading today, telemetry next).
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path


def probe_video_params(path: Path):
    """Return (width, height, r_frame_rate) for a clip's first video stream.

    Raises RuntimeError if ffprobe fails or the expected fields are missing.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed for {path.name}: {exc.stderr.strip()}") from exc

    try:
        streams = json.loads(result.stdout).get("streams", [])
        stream = streams[0]
        return (stream["width"], stream["height"], stream["r_frame_rate"])
    except (json.JSONDecodeError, IndexError, KeyError) as exc:
        raise RuntimeError(f"Could not read video params from {path.name}") from exc


def probe_duration(path: Path):
    """Return the clip duration in seconds (float), or 0.0 if unavailable."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(json.loads(result.stdout)["format"]["duration"])
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError):
        return 0.0


def probe_creation_time(path: Path) -> datetime | None:
    """Return the container's ``creation_time`` (from format tags) or None.

    Provided ahead of the telemetry feature, whose GPX↔video alignment relies on
    the recording's UTC start time (see ADR 0002 / CLAUDE.md "Data Synchronization").
    Not used by the grading pipeline. Returns None when the tag is absent or
    unparseable rather than raising.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format_tags=creation_time",
        "-of", "json",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        value = json.loads(result.stdout).get("format", {}).get("tags", {}).get("creation_time")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    if not value:
        return None
    try:
        # ISO 8601, commonly with a trailing 'Z' for UTC.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
