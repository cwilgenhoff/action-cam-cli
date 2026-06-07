"""Telemetry data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TelemetryTrack:
    """Parsed telemetry: the track's UTC start plus its speed samples.

    ``start`` is the absolute UTC time of the first sample (used later for
    aligning to the video's creation_time); it is None for an empty track.
    Each sample is ``(seconds_from_start, speed_kmh)``.
    """

    start: datetime | None
    samples: list[tuple[float, float]]
