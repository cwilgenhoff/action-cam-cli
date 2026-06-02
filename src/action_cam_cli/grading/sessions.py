"""DJI Action 4 clip discovery, filename parsing, and session grouping.

This is grading-domain logic: it understands the DJI naming convention and the
sequence-counter chaptering rule. (The generic "scan a directory for files with
these extensions" part lives in ``core.discovery``.)
"""

import re
from datetime import datetime
from pathlib import Path

from action_cam_cli.core.config import eprint
from action_cam_cli.core.discovery import scan_files
from action_cam_cli.core.models import Clip

# DJI Action 4 naming convention: DJI_YYYYMMDDHHMMSS_XXXX_D.MP4
#   group 1: 14-digit datetime stamp
#   group 2: 4-digit sequential counter
# Matched case-insensitively; only the .mp4 extension is accepted (proxies are .LRF).
DJI_NAME_RE = re.compile(r"^DJI_(\d{14})_(\d{4})_D\.mp4$", re.IGNORECASE)
DJI_DATETIME_FMT = "%Y%m%d%H%M%S"


def discover_clips(input_dir: Path):
    """Scan input_dir for DJI .mp4 clips, ignoring .LRF proxies and other files.

    Returns a list of Clip objects parsed from matching filenames. Files with an
    .mp4 extension that do not match the DJI naming convention are logged and
    skipped (they cannot be grouped by sequence counter). Returns the clips
    sorted by their sequence counter.
    """
    clips = []
    skipped_unparsed = []

    for entry in scan_files(input_dir, (".mp4",)):
        match = DJI_NAME_RE.match(entry.name)
        if not match:
            skipped_unparsed.append(entry.name)
            continue

        stamp, counter_str = match.group(1), match.group(2)
        try:
            created = datetime.strptime(stamp, DJI_DATETIME_FMT)
        except ValueError:
            skipped_unparsed.append(entry.name)
            continue

        clips.append(
            Clip(path=entry, counter=int(counter_str), created=created, stamp=stamp)
        )

    if skipped_unparsed:
        eprint(
            f"WARNING: {len(skipped_unparsed)} .mp4 file(s) did not match the DJI "
            f"naming convention and were skipped:"
        )
        for name in skipped_unparsed:
            eprint(f"           {name}")

    # Sort strictly by sequence counter so grouping can walk consecutive runs.
    clips.sort(key=lambda c: c.counter)
    return clips


def group_into_sessions(clips):
    """Group counter-sorted clips into recording sessions.

    Clips with perfectly consecutive sequence counters (e.g. 0012, 0013, 0014)
    belong to the same continuous recording and are merged into one session. Any
    break in the sequence starts a new session. Assumes `clips` is already sorted
    by counter (as returned by discover_clips).
    """
    sessions = []
    current = []

    for clip in clips:
        if current and clip.counter == current[-1].counter + 1:
            current.append(clip)
        else:
            if current:
                sessions.append(current)
            current = [clip]
    if current:
        sessions.append(current)

    return sessions


def output_name_for_session(session):
    """Derive the planned output filename for a session from its earliest clip."""
    earliest = min(session, key=lambda c: c.counter)
    return f"{earliest.stamp}_merged_graded.mp4"
