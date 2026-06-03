"""Garmin TCX parsing — the thin standard-library XML adapter.

Reads the device-measured speed (``<ns3:Speed>``, m/s) and timestamp from each
``<Trackpoint>`` of a Training Center XML export. No third-party parser: TCX is
plain XML, so ``xml.etree.ElementTree`` suffices (see ADR 0003).
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from action_cam_cli.telemetry.models import TelemetryTrack

# Namespace-qualified tag prefixes used by Garmin TCX exports.
_TCDB = "{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}"
_ACTEXT = "{http://www.garmin.com/xmlschemas/ActivityExtension/v2}"


def _parse_utc(text: str) -> datetime:
    """Parse a TCX ISO-8601 timestamp (e.g. '2026-06-01T17:20:38.000Z') as UTC."""
    s = text.strip()
    iso = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        # Fallback for stricter fromisoformat builds (e.g. 3-digit fractions on 3.10).
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def parse_track(path: Path) -> TelemetryTrack:
    """Parse a TCX file into a TelemetryTrack of (seconds_from_start, km/h) samples.

    Reads device speed directly; track points lacking a ``<Speed>`` value are
    skipped (they get interpolated over downstream). Returns an empty track
    (start=None) if the file contains no usable speed data.
    """
    root = ET.parse(path).getroot()

    timed: list[tuple[datetime, float]] = []
    for trackpoint in root.iter(f"{_TCDB}Trackpoint"):
        time_el = trackpoint.find(f"{_TCDB}Time")
        speed_el = trackpoint.find(f".//{_ACTEXT}Speed")
        if time_el is None or time_el.text is None:
            continue
        if speed_el is None or not speed_el.text:
            continue
        timed.append((_parse_utc(time_el.text), float(speed_el.text) * 3.6))

    if not timed:
        return TelemetryTrack(start=None, samples=[])

    start = timed[0][0]
    samples = [((t - start).total_seconds(), kmh) for t, kmh in timed]
    return TelemetryTrack(start=start, samples=samples)
